"""
Plan Linter - Plan 执行前校验

职责：
1. 检查 melody part 是否存在
2. 检查所有 part 是否有 template_name
3. 检查 instrument/role/template 兼容性
4. 检查 channel 是否有重复
5. 检查 percussion 是否在合理 channel
6. 检查 target_size 与 parts 数量是否一致
7. 检查 channel 范围是否合法 (0-15)
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from .templates import get_registry

logger = logging.getLogger(__name__)


@dataclass
class LintIssue:
    """Lint 问题"""
    severity: str  # "error" | "warning"
    code: str     # 问题代码，如 "MISSING_MELODY"
    message: str  # 人类可读描述
    location: Optional[str] = None  # 问题位置，如 "part:vn1"
    suggestion: Optional[str] = None  # 修复建议


@dataclass
class LintResult:
    """Lint 结果"""
    passed: bool
    errors: List[LintIssue] = field(default_factory=list)
    warnings: List[LintIssue] = field(default_factory=list)

    def add_error(self, code: str, message: str, location: Optional[str] = None, suggestion: Optional[str] = None):
        self.errors.append(LintIssue(
            severity="error",
            code=code,
            message=message,
            location=location,
            suggestion=suggestion
        ))
        self.passed = False

    def add_warning(self, code: str, message: str, location: Optional[str] = None, suggestion: Optional[str] = None):
        self.warnings.append(LintIssue(
            severity="warning",
            code=code,
            message=message,
            location=location,
            suggestion=suggestion
        ))

    def get_summary(self) -> str:
        """获取人类可读的汇总"""
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts) if parts else "OK"


# 乐器与角色的已知不兼容组合
UNSUPPORTED_COMbos = [
    # percussion 角色不应该用非打击乐器
    ("percussion", "violin"),
    ("percussion", "viola"),
    ("percussion", "cello"),
    ("percussion", "double_bass"),
    ("percussion", "flute"),
    ("percussion", "oboe"),
    ("percussion", "clarinet"),
    ("percussion", "bassoon"),
    ("percussion", "horn"),
    ("percussion", "trumpet"),
    ("percussion", "trombone"),
    ("percussion", "tuba"),
    # 非 percussion 乐器用 percussion role 可能不合理（但 timpani 例外）
]

# GM Percussion 应该用的 channel
PERCUSSION_CHANNELS = {9}  # GM Percussion standard channel


class PlanLinter:
    """
    Plan Linter

    在执行前对 plan 进行全面校验
    """

    def __init__(self):
        self._template_registry = None

    @property
    def template_registry(self):
        """延迟加载 template registry"""
        if self._template_registry is None:
            self._template_registry = get_registry()
        return self._template_registry

    def lint(self, plan_dict: Dict[str, Any]) -> LintResult:
        """
        对 plan 进行 lint

        Args:
            plan_dict: Plan dict（规范化前或后都可以）

        Returns:
            LintResult
        """
        result = LintResult(passed=True)

        ensemble = plan_dict.get("ensemble", {})
        parts = ensemble.get("parts", [])

        # 1. 基本结构检查
        self._check_basic_structure(plan_dict, result)

        # 2. Melody part 检查
        self._check_melody_part(parts, result)

        # 3. Parts 完整性检查
        self._check_parts_completeness(parts, result)

        # 4. Channel 冲突检查
        self._check_channel_conflicts(parts, result)

        # 5. Template 兼容性检查
        self._check_template_compatibility(parts, result)

        # 6. Percussion 检查
        self._check_percussion_config(parts, result)

        # 7. Target size 一致性检查
        self._check_target_size(ensemble, parts, result)

        return result

    def _check_basic_structure(self, plan_dict: Dict[str, Any], result: LintResult):
        """检查基本结构"""
        if "ensemble" not in plan_dict:
            result.add_error(
                "MISSING_ENSEMBLE",
                "Plan 缺少 ensemble 字段",
                suggestion="确保 LLM 输出包含完整的 ensemble 配置"
            )
            return

        if "parts" not in plan_dict.get("ensemble", {}):
            result.add_error(
                "MISSING_PARTS",
                "Ensemble 缺少 parts 字段",
                suggestion="确保 ensemble.parts 包含声部列表"
            )

    def _check_melody_part(self, parts: List[Dict], result: LintResult):
        """检查 melody part 是否存在"""
        if not parts:
            return  # 空 parts 会被其他检查捕获

        melody_parts = [p for p in parts if p.get("role") == "melody"]

        if not melody_parts:
            result.add_error(
                "MISSING_MELODY",
                "没有找到 melody 角色的声部",
                location="ensemble.parts",
                suggestion="确保有一个 role='melody' 的声部"
            )
            return

        if len(melody_parts) > 1:
            result.add_warning(
                "MULTIPLE_MELODY",
                f"存在 {len(melody_parts)} 个 melody 角色声部，通常应该只有一个",
                location="ensemble.parts",
                suggestion="考虑只保留一个 melody，其余改为 inner_voice 或 counter_melody"
            )

        # Melody 不应该有多个 channel
        melody_channels = set(p.get("midi", {}).get("channel") for p in melody_parts)
        if len(melody_channels) > 1:
            result.add_error(
                "MELODY_MULTIPLE_CHANNELS",
                "Melody 声部使用了多个不同的 channel",
                location="ensemble.parts[melody]",
                suggestion="Melody 应该只用一个 channel"
            )

    def _check_parts_completeness(self, parts: List[Dict], result: LintResult):
        """检查 parts 完整性"""
        if not parts:
            result.add_error(
                "EMPTY_PARTS",
                "parts 列表为空",
                suggestion="至少需要一个声部"
            )
            return

        for i, part in enumerate(parts):
            part_id = part.get("id", f"index_{i}")

            # 检查必填字段
            if not part.get("id"):
                result.add_warning(
                    "PART_MISSING_ID",
                    f"第 {i} 个声部缺少 id 字段",
                    location=f"parts[{i}]",
                    suggestion=f"自动生成了 id: {part_id}"
                )

            if not part.get("instrument"):
                result.add_error(
                    "PART_MISSING_INSTRUMENT",
                    f"声部 {part_id} 缺少 instrument 字段",
                    location=f"part:{part_id}",
                    suggestion="指定乐器名称，如 'violin', 'piano', 'flute'"
                )

            if not part.get("role"):
                result.add_error(
                    "PART_MISSING_ROLE",
                    f"声部 {part_id} 缺少 role 字段",
                    location=f"part:{part_id}",
                    suggestion="指定角色，如 'melody', 'inner_voice', 'bass'"
                )

            # 检查 template_name
            template_name = part.get("template_name") or part.get("template")
            if not template_name or template_name == "unknown":
                result.add_warning(
                    "PART_MISSING_TEMPLATE",
                    f"声部 {part_id} 没有指定 template_name",
                    location=f"part:{part_id}",
                    suggestion=f"根据 instrument={part.get('instrument')} 和 role={part.get('role')} 选择合适模板"
                )

            # 检查 MIDI 配置
            midi = part.get("midi", {})
            if not midi:
                result.add_error(
                    "PART_MISSING_MIDI",
                    f"声部 {part_id} 缺少 midi 字段",
                    location=f"part:{part_id}",
                    suggestion="指定 midi.channel 和 midi.program"
                )
                continue

            channel = midi.get("channel")
            if channel is None:
                result.add_error(
                    "PART_MISSING_CHANNEL",
                    f"声部 {part_id} 缺少 midi.channel",
                    location=f"part:{part_id}",
                    suggestion="指定 0-15 之间的 channel"
                )
            elif not isinstance(channel, int) or not (0 <= channel <= 15):
                result.add_error(
                    "INVALID_CHANNEL",
                    f"声部 {part_id} 的 channel={channel} 超出范围 (0-15)",
                    location=f"part:{part_id}",
                    suggestion="channel 必须在 0-15 之间"
                )

            program = midi.get("program")
            if program is None:
                result.add_warning(
                    "PART_MISSING_PROGRAM",
                    f"声部 {part_id} 缺少 midi.program，使用默认值 0",
                    location=f"part:{part_id}",
                    suggestion="指定 0-127 之间的 program number"
                )

    def _check_channel_conflicts(self, parts: List[Dict], result: LintResult):
        """检查 channel 冲突"""
        channel_to_parts: Dict[int, List[str]] = {}

        for part in parts:
            part_id = part.get("id", "unknown")
            channel = part.get("midi", {}).get("channel")

            if channel is None:
                continue  # 已在 completeness 检查中标记

            if channel not in channel_to_parts:
                channel_to_parts[channel] = []
            channel_to_parts[channel].append(part_id)

        # 检查冲突
        for channel, part_ids in channel_to_parts.items():
            if len(part_ids) > 1:
                result.add_error(
                    "CHANNEL_CONFLICT",
                    f"Channel {channel} 被多个声部使用: {', '.join(part_ids)}",
                    location=f"channel:{channel}",
                    suggestion="每个声部应该使用不同的 channel"
                )

    def _check_template_compatibility(self, parts: List[Dict], result: LintResult):
        """检查 template 与 instrument/role 兼容性"""
        for part in parts:
            part_id = part.get("id", "unknown")
            instrument = part.get("instrument", "").lower()
            role = part.get("role", "")
            template_name = part.get("template_name") or part.get("template", "")

            if not template_name:
                continue

            # 获取模板
            template = self.template_registry.get(template_name)
            if not template:
                result.add_warning(
                    "TEMPLATE_NOT_FOUND",
                    f"声部 {part_id} 的模板 '{template_name}' 未找到",
                    location=f"part:{part_id}",
                    suggestion="检查模板名称是否正确"
                )
                continue

            # 检查 instrument 兼容性
            applicable_instruments = getattr(template, 'applicable_instruments', [])
            if applicable_instruments and instrument not in applicable_instruments:
                result.add_warning(
                    "TEMPLATE_INSTRUMENT_MISMATCH",
                    f"声部 {part_id}: instrument '{instrument}' 不在模板 {template_name} 的适用乐器列表中: {applicable_instruments}",
                    location=f"part:{part_id}",
                    suggestion=f"考虑更换模板或调整 instrument"
                )

            # 检查 role 兼容性
            applicable_roles = getattr(template, 'applicable_roles', [])
            if applicable_roles and role not in applicable_roles:
                result.add_warning(
                    "TEMPLATE_ROLE_MISMATCH",
                    f"声部 {part_id}: role '{role}' 不在模板 {template_name} 的适用角色列表中: {applicable_roles}",
                    location=f"part:{part_id}",
                    suggestion=f"考虑更换模板或调整 role"
                )

            # 检查 unsupported combos
            combo = (role, instrument)
            if combo in UNSUPPORTED_COMbos:
                result.add_error(
                    "UNSUPPORTED_COMBO",
                    f"声部 {part_id}: role '{role}' 和 instrument '{instrument}' 组合不支持",
                    location=f"part:{part_id}",
                    suggestion=f"percussion 角色应该使用 timpani 等打击乐器"
                )

    def _check_percussion_config(self, parts: List[Dict], result: LintResult):
        """检查 percussion 配置"""
        for part in parts:
            part_id = part.get("id", "unknown")
            instrument = part.get("instrument", "").lower()
            role = part.get("role", "")
            channel = part.get("midi", {}).get("channel")

            # 如果是打击乐器或 percussion 角色
            is_percussion_instrument = instrument in ("timpani", "cymbal", "percussion", "drums")
            is_percussion_role = role in ("percussion", "bass_rhythm", "accent")

            if is_percussion_role or is_percussion_instrument:
                # GM percussion 应该在 channel 9
                if channel is not None and channel != 9 and is_percussion_instrument:
                    # 但 timpani 通常在独立 channel，这里只警告
                    if instrument == "timpani":
                        pass  # timpani 可以不在 channel 9
                    else:
                        result.add_warning(
                            "PERCUSSION_CHANNEL",
                            f"声部 {part_id}: {instrument} 不在 GM percussion channel (9)",
                            location=f"part:{part_id}",
                            suggestion="打击乐器通常应该使用 channel 9"
                        )

                # Timpani 应该用 bass_rhythm role
                if instrument == "timpani" and role == "percussion":
                    result.add_warning(
                        "TIMPANI_ROLE",
                        f"声部 {part_id}: timpani 建议使用 role='bass_rhythm' 而非 'percussion'",
                        location=f"part:{part_id}",
                        suggestion="timpani 在这里是节奏性低音角色"
                    )

    def _check_target_size(self, ensemble: Dict, parts: List[Dict], result: LintResult):
        """检查 target_size 与实际 parts 数量是否一致"""
        declared_target = ensemble.get("target_size")
        actual_count = len(parts)

        if declared_target is not None and declared_target != actual_count:
            result.add_warning(
                "TARGET_SIZE_MISMATCH",
                f"ensemble.target_size={declared_target} 与实际 parts 数量 {actual_count} 不一致",
                location="ensemble.target_size",
                suggestion=f"将 target_size 设置为 {actual_count}"
            )


def lint_plan(plan_dict: Dict[str, Any]) -> LintResult:
    """
    便捷函数：Lint plan

    Args:
        plan_dict: Plan dict

    Returns:
        LintResult
    """
    linter = PlanLinter()
    return linter.lint(plan_dict)
