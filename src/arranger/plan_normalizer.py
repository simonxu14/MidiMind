"""
Plan Normalizer - 规范化和补全 LLM 输出的 Plan

职责：
1. 自动检测 source_track_ref
2. 补全缺失字段（arrangement、guards 等）
3. 标准化 part 格式（template vs template_name）
4. 修复 channel 冲突
5. 确保 melody 在 channel 0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, Set, List

from .plan_schema import AnalyzeResponse, PartSpec

logger = logging.getLogger(__name__)


# ============ 默认配置常量 ============

DEFAULT_ARRANGEMENT = {
    "reduce_ratio": 0.6,
    "onset_avoidance_action": "scale_velocity",
    "register_separation": True,
    "min_semitones": 5,
    "velocity_caps_by_mode": {},
    "cc_by_mode": {},
    "humanize": {"enabled": False},
    "percussion": {"enabled": True, "phrase_block": 8, "density": 0.5},
}

DEFAULT_GUARDS = {
    "velocity_caps": {},
    "avoid_melody_onsets": True,
    "onset_window_ticks": 120,
    "onset_avoidance_action": "scale_velocity",
    "register_separation": True,
}

# 角色 -> 默认模板的fallback映射
ROLE_DEFAULT_TEMPLATES = {
    "melody": "violin_cantabile",
    "inner_voice": "viola_inner_16ths",
    "bass": "cello_pedal_root",
    "accompaniment": "dense_accompaniment",
    "counter_melody": "flute_countermelody",
    "sustain_support": "root_pad",
    "bass_rhythm": "timpani_rhythm",
    "accent": "trumpet_fanfare",
    "percussion": "timpani_rhythm",
    "fanfare": "trumpet_fanfare",
    "tutti": "ensemble_tutti",
    "anchor": "cello_pedal_root",
}

# 乐器 -> 默认模板的fallback映射
INSTRUMENT_DEFAULT_TEMPLATES = {
    "violin": "violin_cantabile",
    "viola": "viola_inner_16ths",
    "cello": "cello_pedal_root",
    "double_bass": "adaptive_bass",
    "flute": "flute_countermelody",
    "oboe": "oboe_color_tone",
    "clarinet": "clarinet_sustain",
    "bassoon": "bassoon_bass_line",
    "horn": "root_pad",
    "french_horn": "root_pad",
    "trumpet": "trumpet_fanfare",
    "trombone": "trombone_anchor",
    "tuba": "adaptive_bass",
    "piano": "dense_accompaniment",
    "harp": "arpeggio",
    "timpani": "timpani_rhythm",
}


class PlanNormalizer:
    """
    Plan 规范化器

    将 LLM 输出的原始 plan 规范化为可执行的完整 plan
    """

    def __init__(self):
        pass

    def normalize(
        self,
        plan_dict: Dict[str, Any],
        analyze_result: Optional[AnalyzeResponse] = None
    ) -> Dict[str, Any]:
        """
        规范化 plan

        Args:
            plan_dict: LLM 输出的原始 plan dict
            analyze_result: 可选的 MIDI 分析结果，用于自动检测 melody track

        Returns:
            规范化后的 plan dict
        """
        # 1. 自动检测 source_track_ref
        auto_source_track = self._detect_source_track(plan_dict, analyze_result)

        # 2. 构建完整的 plan 结构
        complete_plan = self._build_complete_structure(plan_dict, auto_source_track)

        # 3. 规范化 parts
        used_channels: Set[int] = set()
        normalized_parts: List[Dict[str, Any]] = []

        raw_parts = plan_dict.get("ensemble", {}).get("parts", [])
        if not raw_parts and "parts" in plan_dict:
            raw_parts = plan_dict.get("parts", [])

        for i, part in enumerate(raw_parts):
            normalized = self._normalize_part(part, i, used_channels)
            normalized_parts.append(normalized)
            used_channels.add(normalized["midi"]["channel"])

        complete_plan["ensemble"]["parts"] = normalized_parts
        complete_plan["ensemble"]["target_size"] = len(normalized_parts)

        # 4. 确保 melody 在 channel 0
        complete_plan = self._ensure_melody_on_channel_zero(complete_plan)

        return complete_plan

    def _detect_source_track(
        self,
        plan_dict: Dict[str, Any],
        analyze_result: Optional[AnalyzeResponse]
    ) -> str:
        """自动检测 source_track_ref"""
        # 优先使用 LLM 指定的
        constraints = plan_dict.get("constraints", {})
        lock_melody = constraints.get("lock_melody_events", {})
        if lock_melody.get("source_track_ref"):
            return str(lock_melody["source_track_ref"])

        # 使用 analyze_result 中分数最高的候选
        if analyze_result and hasattr(analyze_result, 'melody_candidates') and analyze_result.melody_candidates:
            top_candidate = max(analyze_result.melody_candidates, key=lambda c: c.score)
            return str(top_candidate.track_index)

        return "0"

    def _build_complete_structure(
        self,
        plan_dict: Dict[str, Any],
        auto_source_track: str
    ) -> Dict[str, Any]:
        """构建完整的 plan 结构框架"""
        return {
            "schema_version": plan_dict.get("schema_version", "1.0"),
            "transform": {
                "type": plan_dict.get("transform", {}).get("type", "orchestration"),
                "preserve_structure": plan_dict.get("transform", {}).get("preserve_structure", True),
                "preserve_order": plan_dict.get("transform", {}).get("preserve_order", True),
            },
            "ensemble": {
                "name": plan_dict.get("ensemble", {}).get("name", "custom_ensemble"),
                "size": plan_dict.get("ensemble", {}).get("size", "medium"),
                "target_size": len(plan_dict.get("ensemble", {}).get("parts", [])),
                "parts": []
            },
            "harmony_context": plan_dict.get("harmony_context") or {
                "method": "measure_pitchset_triadish",
                "granularity": "per_measure"
            },
            "arrangement": plan_dict.get("arrangement") or DEFAULT_ARRANGEMENT.copy(),
            "constraints": {
                "lock_melody_events": {
                    "enabled": True,
                    "source_track_ref": auto_source_track,
                    "source_track_selection_mode": "auto"
                },
                "keep_total_ticks": plan_dict.get("constraints", {}).get("keep_total_ticks", True),
                "guards": plan_dict.get("constraints", {}).get("guards") or DEFAULT_GUARDS.copy(),
            },
            "outputs": {
                "midi": {
                    "enabled": True,
                    "filename": plan_dict.get("outputs", {}).get("midi", {}).get("filename", "arranged.mid")
                }
            }
        }

    def _normalize_part(
        self,
        part: Dict[str, Any],
        index: int,
        used_channels: Set[int]
    ) -> Dict[str, Any]:
        """
        规范化单个 part

        1. 补全必填字段
        2. 处理 template vs template_name
        3. 分配唯一 channel
        4. 补全缺失的 template_name
        """
        part_id = part.get("id", f"part_{index}")
        instrument = part.get("instrument", "piano").lower()
        role = part.get("role", "accompaniment")

        # 处理 template 字段（LLM 可能返回 template 而非 template_name）
        template_name = None
        if "template" in part:
            template_name = part["template"]
        elif "template_name" in part:
            template_name = part["template_name"]
        else:
            # 尝试根据 instrument 或 role 推断默认模板
            template_name = INSTRUMENT_DEFAULT_TEMPLATES.get(instrument)
            if not template_name:
                template_name = ROLE_DEFAULT_TEMPLATES.get(role)

        # 如果模板名为 "unknown" 或 None，尝试 fallback
        if template_name in ("unknown", None, ""):
            template_name = INSTRUMENT_DEFAULT_TEMPLATES.get(instrument)
            if not template_name:
                template_name = ROLE_DEFAULT_TEMPLATES.get(role, "dense_accompaniment")

        # 处理 MIDI channel
        raw_channel = part.get("midi", {}).get("channel", 0)
        if isinstance(raw_channel, str):
            try:
                channel = int(raw_channel)
            except ValueError:
                channel = 0
        else:
            channel = raw_channel

        # 确保 channel 不冲突
        if channel in used_channels:
            for c in range(16):
                if c not in used_channels:
                    channel = c
                    break

        # 处理 MIDI program
        program = part.get("midi", {}).get("program", 0)
        if program is None:
            program = 0

        return {
            "id": part_id,
            "name": part.get("name", f"Part {part_id}"),
            "role": role,
            "instrument": instrument,
            "midi": {
                "channel": channel,
                "program": program
            },
            "template_name": template_name,
            "template_params": part.get("template_params") or {}
        }

    def _ensure_melody_on_channel_zero(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """确保 melody role 的声部在 channel 0"""
        parts = plan["ensemble"]["parts"]

        melody_parts = [p for p in parts if p.get("role") == "melody"]
        if not melody_parts:
            return plan

        melody_part = melody_parts[0]
        if melody_part["midi"]["channel"] == 0:
            return plan

        # 找到当前在 channel 0 的声部并交换
        for p in parts:
            if p["midi"]["channel"] == 0:
                p["midi"]["channel"] = melody_part["midi"]["channel"]
                break

        melody_part["midi"]["channel"] = 0
        return plan


def normalize_plan(
    plan_dict: Dict[str, Any],
    analyze_result: Optional[AnalyzeResponse] = None
) -> Dict[str, Any]:
    """
    便捷函数：规范化 plan

    Args:
        plan_dict: LLM 输出的原始 plan
        analyze_result: 可选的 MIDI 分析结果

    Returns:
        规范化后的 plan dict
    """
    normalizer = PlanNormalizer()
    return normalizer.normalize(plan_dict, analyze_result)
