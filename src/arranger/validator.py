"""
Validator 模块

负责验证编曲结果是否满足约束

硬约束（必须通过）：
1. melody_identical - 主旋律逐事件一致
2. total_ticks_identical - 总 tick 数一致
3. instrumentation_ok - 编制符合 Plan
4. midi_valid - MIDI 格式有效

软约束（警告 + Auto-fixer）：
1. harmony_valid - 无平行五八度等
2. instrument_range_valid - 音符在音域内
3. style_conformance - 符合目标风格
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

from .midi_io import MidiReader, MidiWriter, MidiFile, TrackInfo, ParsedNote
from .plan_schema import (
    UnifiedPlan,
    CheckResult,
    NoteEvent,
)
from .harmony_validator import HarmonyValidator


# ============ Validator 结果 ============

@dataclass
class ValidationResult:
    """验证结果"""

    # 硬约束
    melody_identical: CheckResult
    total_ticks_identical: CheckResult
    instrumentation_ok: CheckResult
    midi_valid: CheckResult

    # 软约束（警告）
    harmony_valid: CheckResult
    instrument_range_valid: CheckResult

    # 总体结果
    all_passed: bool

    # 错误信息
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "melody_identical": {"passed": self.melody_identical.passed, "message": self.melody_identical.message},
            "total_ticks_identical": {"passed": self.total_ticks_identical.passed, "message": self.total_ticks_identical.message},
            "instrumentation_ok": {"passed": self.instrumentation_ok.passed, "message": self.instrumentation_ok.message},
            "midi_valid": {"passed": self.midi_valid.passed, "message": self.midi_valid.message},
            "harmony_valid": {"passed": self.harmony_valid.passed, "message": self.harmony_valid.message},
            "instrument_range_valid": {"passed": self.instrument_range_valid.passed, "message": self.instrument_range_valid.message},
            "all_passed": self.all_passed,
            "errors": self.errors,
        }


# ============ 乐器音域 ============

INSTRUMENT_RANGES = {
    "violin": (55, 96),
    "viola": (48, 81),
    "cello": (36, 72),
    "double_bass": (28, 52),
    "harp": (23, 103),
    "flute": (60, 96),
    "oboe": (58, 89),
    "clarinet": (50, 99),
    "bassoon": (34, 64),
    "horn": (40, 65),
    "french_horn": (40, 65),
    "trumpet": (52, 84),
    "trombone": (40, 72),
    "tuba": (27, 53),
    "piano": (21, 108),
    "timpani": (45, 53),
}


# ============ 主 Validator ============

class Validator:
    """
    编曲结果验证器
    """

    def __init__(self, plan: UnifiedPlan):
        self.plan = plan
        self.constraints = plan.constraints
        self.ensemble = plan.ensemble

    def validate(
        self,
        input_midi: bytes,
        output_tracks: List[List[Tuple[str, Dict]]]
    ) -> ValidationResult:
        """
        验证编曲结果

        Args:
            input_midi: 输入 MIDI 二进制数据
            output_tracks: 输出轨道数据

        Returns:
            ValidationResult
        """
        errors: List[str] = []

        # 解析输入 MIDI
        input_midi_obj = MidiReader.read_midi(input_midi)
        input_tracks = MidiReader.extract_track_messages(input_midi_obj)

        # 1. melody_identical
        melody_identical = self._check_melody_identical(input_tracks, output_tracks)
        if not melody_identical.passed:
            errors.append(f"melody_identical: {melody_identical.message}")

        # 2. total_ticks_identical
        total_ticks = self._check_total_ticks(input_tracks, output_tracks)
        if not total_ticks.passed:
            errors.append(f"total_ticks_identical: {total_ticks.message}")

        # 3. instrumentation_ok
        instrumentation = self._check_instrumentation(output_tracks)
        if not instrumentation.passed:
            errors.append(f"instrumentation_ok: {instrumentation.message}")

        # 4. midi_valid
        midi_valid = self._check_midi_valid(output_tracks)
        if not midi_valid.passed:
            errors.append(f"midi_valid: {midi_valid.message}")

        # 5. harmony_valid（软约束）
        harmony_valid = self._check_harmony(output_tracks)
        # 不加入 errors，只作为警告

        # 6. instrument_range_valid（软约束）
        range_valid = self._check_instrument_ranges(output_tracks)
        # 不加入 errors，只作为警告

        all_passed = (
            melody_identical.passed
            and total_ticks.passed
            and instrumentation.passed
            and midi_valid.passed
        )

        return ValidationResult(
            melody_identical=melody_identical,
            total_ticks_identical=total_ticks,
            instrumentation_ok=instrumentation,
            midi_valid=midi_valid,
            harmony_valid=harmony_valid,
            instrument_range_valid=range_valid,
            all_passed=all_passed,
            errors=errors
        )

    def _check_melody_identical(
        self,
        input_tracks: List[TrackInfo],
        output_tracks: List[List[Tuple[str, Dict]]]
    ) -> CheckResult:
        """
        检查主旋律是否逐事件一致

        对比输入的旋律轨和输出的旋律轨
        """
        if not self.constraints.lock_melody_events.enabled:
            return CheckResult(passed=True, message="Melody lock not enabled")

        # 获取源轨道索引
        source_ref = self.constraints.lock_melody_events.source_track_ref
        if not source_ref:
            return CheckResult(passed=True, message="No source track specified")

        # 解析轨道索引
        try:
            source_index = int(source_ref)
        except ValueError:
            # 可能是轨道名称
            source_index = None
            for i, track in enumerate(input_tracks):
                if track.name == source_ref:
                    source_index = i
                    break
            if source_index is None:
                return CheckResult(passed=False, message=f"Source track not found: {source_ref}")

        if source_index >= len(input_tracks):
            return CheckResult(passed=False, message=f"Source track index out of range: {source_index}")

        input_melody = input_tracks[source_index]

        # 找到输出的旋律轨
        output_melody_track = None
        for track_data in output_tracks:
            for msg_type, params in track_data:
                if msg_type == 'track_name':
                    track_name = params.get('name', '')
                    if 'melody' in track_name.lower() or track_name == self.constraints.lock_melody_events.target_track_name:
                        output_melody_track = track_data
                        break

        if output_melody_track is None:
            return CheckResult(passed=False, message="Output melody track not found")

        # 提取输出旋律轨的音符（需要计算 delta -> abs 时间）
        # 使用列表来支持同一 pitch+channel 的重复音符（如 rapid re-attack）
        output_notes: List[Tuple[int, int, int, int]] = []
        pending_notes: List[Tuple[int, int, int, int]] = []  # [(pitch, channel, start_tick, velocity)]

        current_time = 0
        for msg_type, params in output_melody_track:
            if 'time' in params:
                current_time += params['time']

            if msg_type == 'note_on':
                note = params.get('note', 0)
                velocity = params.get('velocity', 0)
                channel = params.get('channel', 0)
                if velocity > 0:
                    # note_on 开始一个音符
                    pending_notes.append((note, channel, current_time, velocity))
                else:
                    # note_on with velocity 0 = note_off - 找到并移除最旧的匹配音符
                    matched_idx = None
                    for idx, (n, ch, start, vel) in enumerate(pending_notes):
                        if n == note and ch == channel:
                            matched_idx = idx
                            output_notes.append((start, current_time, note, vel))
                            break
                    if matched_idx is not None:
                        pending_notes.pop(matched_idx)
            elif msg_type == 'note_off':
                note = params.get('note', 0)
                channel = params.get('channel', 0)
                # 找到并移除最旧的匹配音符
                matched_idx = None
                for idx, (n, ch, start, vel) in enumerate(pending_notes):
                    if n == note and ch == channel:
                        matched_idx = idx
                        output_notes.append((start, current_time, note, vel))
                        break
                if matched_idx is not None:
                    pending_notes.pop(matched_idx)

        # 处理未配对的 note_on（使用 track 结束时间）
        if pending_notes:
            for (note, channel, start_tick, velocity) in pending_notes:
                output_notes.append((start_tick, current_time, note, velocity))

        # 逐事件比对
        compare_fields = self.constraints.lock_melody_events.compare_fields

        input_notes = [
            (n.start_tick, n.end_tick, n.pitch, n.velocity)
            for n in input_melody.notes
        ]

        # 如果源轨道没有音符但 melody lock 被启用，这是错误
        if len(input_notes) == 0:
            return CheckResult(
                passed=False,
                message=f"Source track {source_index} has no notes - cannot lock melody"
            )

        if len(input_notes) != len(output_notes):
            return CheckResult(
                passed=False,
                message=f"Note count mismatch: input={len(input_notes)}, output={len(output_notes)}"
            )

        for i, (in_note, out_note) in enumerate(zip(input_notes, output_notes)):
            if in_note != out_note:
                return CheckResult(
                    passed=False,
                    message=f"Note {i} mismatch: input={in_note}, output={out_note}"
                )

        return CheckResult(passed=True, message="Melody identical")

    def _check_total_ticks(
        self,
        input_tracks: List[TrackInfo],
        output_tracks: List[List[Tuple[str, Dict]]]
    ) -> CheckResult:
        """检查总 tick 数是否一致"""
        # 计算输入总 tick
        input_total = 0
        for track in input_tracks:
            if track.notes:
                track_end = max(n.end_tick for n in track.notes)
                input_total = max(input_total, track_end)

        # 计算输出总 tick
        output_total = 0
        for track_data in output_tracks:
            track_end = 0
            current_time = 0
            for msg_type, params in track_data:
                if 'time' in params:
                    current_time += params['time']
                    if msg_type == 'note_off':
                        track_end = max(track_end, current_time)
            output_total = max(output_total, track_end)

        if not self.constraints.keep_total_ticks:
            return CheckResult(passed=True, message="Total ticks check skipped")

        # 允许小误差（小于 1 beat = 480 ticks）
        TICK_TOLERANCE = 480
        diff = abs(input_total - output_total)
        if diff > TICK_TOLERANCE:
            return CheckResult(
                passed=False,
                message=f"Total ticks mismatch: input={input_total}, output={output_total}, diff={diff}"
            )

        return CheckResult(passed=True, message="Total ticks within tolerance")

    def _check_instrumentation(
        self,
        output_tracks: List[List[Tuple[str, Dict]]]
    ) -> CheckResult:
        """检查编制是否符合 Plan"""
        if not self.ensemble:
            return CheckResult(passed=True, message="No ensemble specified")

        # 期望的轨道数（不含 conductor track，因为 output_tracks 不包含它）
        expected_parts = len([p for p in self.ensemble.parts if p.role != "melody"]) + 1  # +1 for melody
        actual_parts = len(output_tracks)  # output_tracks 不包含 conductor track

        if actual_parts != expected_parts:
            return CheckResult(
                passed=False,
                message=f"Track count mismatch: expected={expected_parts}, actual={actual_parts}"
            )

        # 检查每个声部的 program 和 channel
        # 使用 part.id 进行匹配（ASCII，不会冲突）
        for part in self.ensemble.parts:
            found = False
            for track_data in output_tracks:
                track_name = None
                program = None
                channel = None

                for msg_type, params in track_data:
                    if msg_type == 'track_name':
                        track_name = params.get('name', '')
                    elif msg_type == 'program_change':
                        program = params.get('program')
                        channel = params.get('channel')

                # 使用 part.id 进行匹配
                if track_name == part.id:
                    found = True
                    if program != part.midi.program:
                        return CheckResult(
                            passed=False,
                            message=f"Program mismatch for {part.id}: expected={part.midi.program}, actual={program}"
                        )
                    if channel != part.midi.channel:
                        return CheckResult(
                            passed=False,
                            message=f"Channel mismatch for {part.id}: expected={part.midi.channel}, actual={channel}"
                        )
                    break

            if not found and part.role != "melody":
                return CheckResult(
                    passed=False,
                    message=f"Part not found: {part.id}"
                )

        return CheckResult(passed=True, message="Instrumentation OK")

    def _check_midi_valid(
        self,
        output_tracks: List[List[Tuple[str, Dict]]]
    ) -> CheckResult:
        """检查 MIDI 格式是否有效"""
        for i, track_data in enumerate(output_tracks):
            # 检查是否有 end_of_track
            has_end = any(
                (msg_type == 'track_name' and i > 0) or msg_type == 'end_of_track'
                for msg_type, params in track_data
            )

            if not has_end and i > 0:  # Conductor track 可能没有
                return CheckResult(
                    passed=False,
                    message=f"Track {i} missing end_of_track"
                )

            # 检查 delta time 非负
            for msg_type, params in track_data:
                if 'time' in params and params['time'] < 0:
                    return CheckResult(
                        passed=False,
                        message=f"Negative delta time in track {i}"
                    )

        return CheckResult(passed=True, message="MIDI valid")

    def _check_harmony(
        self,
        output_tracks: List[List[Tuple[str, Dict]]]
    ) -> CheckResult:
        """
        检查和声（软约束）

        检测平行五八度、声部交叉等
        """
        # 提取所有音符事件（正确追踪 start/end tick）
        all_notes: List[Tuple[int, int, int, int, int]] = []

        for track_data in output_tracks:
            current_time = 0
            pending_notes: Dict[Tuple[int, int], Tuple[int, int, int, int]] = {}  # (pitch, channel) -> (start, pitch, velocity, channel)

            for msg_type, params in track_data:
                if 'time' in params:
                    current_time += params['time']

                if msg_type == 'note_on':
                    velocity = params.get('velocity', 64)
                    pitch = params.get('pitch', 60)
                    channel = params.get('channel', 0)
                    if velocity > 0:  # 真正的 note_on（不是 note_off）
                        pending_notes[(pitch, channel)] = (current_time, pitch, velocity, channel)
                    else:  # velocity=0 是 note_off
                        key = (pitch, channel)
                        if key in pending_notes:
                            start, p, v, ch = pending_notes.pop(key)
                            all_notes.append((start, current_time, p, v, ch))

                elif msg_type == 'note_off':
                    pitch = params.get('pitch', 60)
                    channel = params.get('channel', 0)
                    key = (pitch, channel)
                    if key in pending_notes:
                        start, p, v, ch = pending_notes.pop(key)
                        all_notes.append((start, current_time, p, v, ch))

        # 使用 HarmonyValidator 检测
        validator = HarmonyValidator()
        return validator.validate(all_notes)

    def _check_instrument_ranges(
        self,
        output_tracks: List[List[Tuple[str, Dict]]]
    ) -> CheckResult:
        """
        检查音符是否在乐器音域内（软约束）
        """
        warnings = []

        for track_data in output_tracks:
            track_name = None
            instrument = None
            channel = None

            # 确定乐器
            for msg_type, params in track_data:
                if msg_type == 'track_name':
                    track_name = params.get('name', '')
                elif msg_type == 'program_change':
                    channel = params.get('channel')

            # 查找对应的 ensemble part
            if self.ensemble:
                for part in self.ensemble.parts:
                    if part.name == track_name:
                        instrument = part.instrument
                        break

            if not instrument or instrument not in INSTRUMENT_RANGES:
                continue

            range_min, range_max = INSTRUMENT_RANGES[instrument]

            # 检查每个音符
            for msg_type, params in track_data:
                if msg_type == 'note_on':
                    pitch = params.get('pitch', 60)
                    if pitch < range_min or pitch > range_max:
                        warnings.append(
                            f"{track_name}: pitch {pitch} out of range [{range_min}, {range_max}]"
                        )

        if warnings:
            return CheckResult(
                passed=False,
                message="; ".join(warnings[:3])  # 只显示前3个警告
            )

        return CheckResult(passed=True, message="All notes in range")
