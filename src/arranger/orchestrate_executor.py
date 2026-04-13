"""
OrchestrateExecutor - 乐队编曲执行器

负责：
1. 主旋律锁定
2. 模板填充生成伴奏
3. 应用护栏策略
4. Auto-fixer 自动修复
"""

from __future__ import annotations

import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

from .midi_io import MidiReader, MidiAnalyzer
from .plan_schema import (
    UnifiedPlan,
    HarmonyContext,
    GuardsConfig,
    NoteEvent,
)
from .templates import get_registry
from .services import (
    analyze_harmony,
    apply_autofix_pipeline,
    apply_guards,
    apply_humanize,
    apply_per_measure_mode_adjustments,
    auto_add_percussion,
    build_arrangement_context,
    build_output_tracks,
    generate_arrangement_report,
    generate_part_notes,
    init_report_stats,
    get_instrument_key_for_track,
    lock_melody,
)
from .config import INSTRUMENT_RANGES


class OrchestrateExecutor:
    """
    乐队编曲执行器

    核心逻辑：
    1. 提取并锁定主旋律
    2. 分析和声上下文
    3. 使用模板生成各声部伴奏
    4. 应用护栏（guards）
    5. Auto-fixer 修复问题
    """

    def __init__(self, plan: UnifiedPlan):
        self.plan = plan
        self.constraints = plan.constraints
        self.ensemble = plan.ensemble
        self.harmony_context = plan.harmony_context or HarmonyContext()
        self.guards = plan.constraints.guards or GuardsConfig()
        self.template_registry = get_registry()
        self.melody_onsets: List[int] = []  # 存储旋律 onset 供 _generate_part 使用

        self._report_stats = init_report_stats()

    def execute(
        self,
        input_midi: bytes,
        melody_track_index: int
    ) -> Tuple[List[List[Tuple[str, Dict]]], Dict[str, any]]:
        """
        执行编曲

        Args:
            input_midi: 输入 MIDI 二进制数据
            melody_track_index: 旋律轨索引

        Returns:
            (tracks_data, stats) - 轨道数据和统计信息
        """
        # 1. 解析 MIDI
        midi = MidiReader.read_midi(input_midi)
        tracks = MidiReader.extract_track_messages(midi)

        # 提取 tempo
        analyzer = MidiAnalyzer(midi)
        midi_analysis = analyzer.analyze()
        tempo = midi_analysis.tempo

        # P0-1: 保存输入的真实 total_ticks，用于裁剪
        input_total_ticks = midi_analysis.total_ticks

        # 2. 提取并锁定主旋律
        if melody_track_index >= len(tracks):
            logger.warning(f"melody_track_index {melody_track_index} out of range, using 0. Available tracks: {len(tracks)}")
            melody_track_index = 0
        melody_track = tracks[melody_track_index]
        locked_melody_notes = lock_melody(melody_track, self.ensemble)

        # 3. 分析和声上下文
        harmony_analysis = analyze_harmony(
            tracks,
            melody_track_index,
            self.harmony_context,
            midi.ticks_per_beat
        )

        # 4. 构建 ArrangementContext
        arrangement_context = build_arrangement_context(
            midi,
            tracks,
            harmony_analysis,
            self.ensemble,
            self._get_velocity_caps_for_mode,
            tempo,
            melody_track_index,
            midi_analysis.time_signature if hasattr(midi_analysis, 'time_signature') else (4, 4)
        )

        # 存储 melody_onsets 供 _generate_part 使用
        self.melody_onsets = arrangement_context.melody_onsets

        # 5. 生成各声部
        accompaniment_tracks: Dict[str, List[NoteEvent]] = {}  # part.id -> notes
        instrument_list = [part.name for part in self.ensemble.parts]

        for part in self.ensemble.parts:
            if part.role == "melody":
                continue

            track_notes = generate_part_notes(
                part,
                arrangement_context,
                self.plan,
                self.template_registry,
                self._report_stats,
            )

            # 应用护栏
            track_notes = apply_guards(
                track_notes,
                part,
                self.guards,
                self.plan,
                INSTRUMENT_RANGES,
                self._get_melody_onsets(),
                self._report_stats,
            )

            # 应用人性化处理（可选）
            if self.plan.arrangement and self.plan.arrangement.humanize:
                humanize_config = self.plan.arrangement.humanize
                if humanize_config.enabled and part.role != "melody":
                    track_notes = apply_humanize(
                        track_notes,
                        part,
                        timing_jitter=humanize_config.timing_jitter_ticks,
                        velocity_jitter=humanize_config.velocity_jitter
                    )

            # 替换 channel 为 Plan 中指定的 channel（模板使用硬编码默认值）
            target_channel = part.midi.channel
            track_notes = [
                (start, end, pitch, velocity, target_channel)
                for start, end, pitch, velocity, _ in track_notes
            ]

            accompaniment_tracks[part.id] = track_notes

        # 6. 应用 AutoFixer 修复和声问题
        accompaniment_tracks = apply_autofix_pipeline(
            accompaniment_tracks,
            self.ensemble,
            arrangement_context,
            self.plan,
            locked_melody_notes,
            INSTRUMENT_RANGES,
            self._report_stats,
        )

        # 6.5 按小节模式调整力度
        accompaniment_tracks = apply_per_measure_mode_adjustments(
            accompaniment_tracks,
            arrangement_context,
            self._get_velocity_caps_for_mode,
            lambda track_id: get_instrument_key_for_track(track_id, self.ensemble),
        )

        # 6.6 自动添加打击乐
        accompaniment_tracks = auto_add_percussion(
            accompaniment_tracks,
            arrangement_context,
            self.plan,
            self.ensemble,
            self._report_stats,
        )

        # P0-1: 裁剪所有音符到 input_total_ticks
        locked_melody_notes = self._clip_note_events_to_total_ticks(
            locked_melody_notes, input_total_ticks
        )
        for part_id in accompaniment_tracks:
            accompaniment_tracks[part_id] = self._clip_note_events_to_total_ticks(
                accompaniment_tracks[part_id], input_total_ticks
            )

        # 7. 构建输出轨道
        current_mode = arrangement_context.current_mode
        melody_cc_config = self._get_cc_config_for_mode(current_mode, is_melody=True)
        other_cc_config = self._get_cc_config_for_mode(current_mode, is_melody=False)
        output_tracks = build_output_tracks(
            self.ensemble,
            locked_melody_notes,
            accompaniment_tracks,
            melody_cc_config,
            other_cc_config,
        )

        # 8. 统计信息
        total_notes = sum(len(t) for t in output_tracks if t)

        # P2-3: 生成 arrangement_report
        arrangement_report = generate_arrangement_report(
            arrangement_context,
            accompaniment_tracks,
            output_tracks,
            self.ensemble,
            self._report_stats,
        )

        stats = {
            "track_count": len(output_tracks),
            "parts_count": len(self.ensemble.parts),
            "instrument_list": instrument_list,
            "total_notes": total_notes,
            "arrangement_report": arrangement_report,
        }

        return output_tracks, stats

    def _clip_note_events_to_total_ticks(
        self,
        note_events: List[NoteEvent],
        max_tick: int
    ) -> List[NoteEvent]:
        """
        P0-1: 裁剪 NoteEvent 列表到 max_tick

        - start_tick >= max_tick 的音符直接丢弃
        - end_tick > max_tick 的音符 end_tick 截断到 max_tick
        - start_tick >= end_tick 的音符丢弃
        """
        clipped: List[NoteEvent] = []
        for start, end, pitch, velocity, channel in note_events:
            if start >= max_tick:
                continue
            if end > max_tick:
                end = max_tick
            if start >= end:
                continue
            clipped.append((start, end, pitch, velocity, channel))
        return clipped

    def _get_melody_onsets(self) -> List[int]:
        """获取旋律 onset 列表"""
        return self.melody_onsets

    def _get_velocity_caps_for_mode(self, mode: str) -> Dict[str, int]:
        """
        获取指定模式的力度上限

        Args:
            mode: 段落模式 (A/B/C/D)

        Returns:
            力度上限字典 {instrument_id: cap}
        """
        # 从 arrangement 配置获取，默认使用钢琴的力度上限
        default_caps = {
            "pf": 52, "va": 56, "vc": 62, "winds": 58, "hn": 56
        }

        if self.plan.arrangement and self.plan.arrangement.velocity_caps_by_mode:
            caps_by_mode = self.plan.arrangement.velocity_caps_by_mode
            mode_caps = getattr(caps_by_mode, mode, None)
            if mode_caps:
                return mode_caps

        # 默认值按模式调整
        defaults_by_mode = {
            "A": {"pf": 52, "va": 56, "vc": 62, "winds": 58, "hn": 56},
            "B": {"pf": 56, "va": 60, "vc": 66, "winds": 60, "hn": 58},
            "C": {"pf": 58, "va": 62, "vc": 70, "winds": 62, "hn": 60},
            "D": {"pf": 62, "va": 66, "vc": 74, "winds": 64, "hn": 62},
        }
        return defaults_by_mode.get(mode, default_caps)

    def _get_cc_config_for_mode(self, mode: str, is_melody: bool = False) -> 'CCConfig':
        """
        获取指定模式的 CC 配置

        Args:
            mode: 段落模式 (A/B/C/D)
            is_melody: 是否为主旋律轨道

        Returns:
            CCConfig 对象
        """
        from .plan_schema import CCConfig

        if self.plan.arrangement and self.plan.arrangement.cc_by_mode:
            cc_by_mode = self.plan.arrangement.cc_by_mode
            if is_melody:
                return cc_by_mode.melody.get(mode, CCConfig())
            else:
                return cc_by_mode.others.get(mode, CCConfig())

        # 默认配置
        if is_melody:
            defaults = {
                "A": CCConfig(cc7=102, cc11=100, cc91=35, cc93=8),
                "B": CCConfig(cc7=102, cc11=105, cc91=35, cc93=8),
                "C": CCConfig(cc7=102, cc11=108, cc91=35, cc93=8),
                "D": CCConfig(cc7=102, cc11=112, cc91=35, cc93=8),
            }
        else:
            defaults = {
                "A": CCConfig(cc91=25, cc93=6),
                "D": CCConfig(cc91=27, cc93=6),
            }

        return defaults.get(mode, CCConfig())
