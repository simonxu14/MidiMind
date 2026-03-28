"""
SimplifyExecutor - 难度降低执行器

负责：
1. 识别高难度技术元素
2. 应用简化规则
3. 保持整体结构不变
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Any
from dataclasses import dataclass

from .plan_schema import UnifiedPlan, NoteEvent
from .midi_io import MidiReader, MidiFile, TrackInfo


# ============ 难度规则定义 ============

# 简化操作符定义
SIMPLIFY_OPERATIONS = {
    "octave_jumps": {
        "description": "减少八度跳跃",
        "threshold_ticks": 12,  # 超过12个半音视为大跳
    },
    "tremolo": {
        "description": "将震音替换为持续音",
        "min_repeat_count": 3,  # 连续3次以上视为震音
    },
    "dense_arpeggio": {
        "description": "简化密集琶音为和弦",
        "min_notes_per_beat": 4,  # 每拍超过4个音视为密集
    },
    "rapid_repetitions": {
        "description": "减少快速重复音",
        "max_repetitions": 2,  # 最多重复2次
    },
    "extreme_register": {
        "description": "将极端音区移到舒适区",
        "piano_comfortable_range": (36, 84),  # C2-C6
    },
    "pedal_points": {
        "description": "简化延音踏板用法（保留音符但简化周围）",
    },
}


@dataclass
class NoteWithContext:
    """带上下文的音符"""
    start_tick: int
    end_tick: int
    pitch: int
    velocity: int
    channel: int
    duration: int  # 持续时间


class SimplifyExecutor:
    """
    难度降低执行器

    使用说明：
    1. 设置目标难度级别
    2. 指定要简化的元素
    3. execute() 返回简化后的 MIDI
    """

    def __init__(self, plan: UnifiedPlan):
        self.plan = plan
        self.difficulty = plan.difficulty
        self.simplify_elements = self.difficulty.simplify_elements if self.difficulty else []

    def execute(self, input_midi: bytes) -> bytes:
        """
        执行难度降低

        Args:
            input_midi: 输入 MIDI 二进制数据

        Returns:
            简化后的 MIDI 二进制数据
        """
        # 读取 MIDI
        midi = MidiReader.read_midi(input_midi)
        tracks = MidiReader.extract_track_messages(midi)

        # 转换为内部表示
        note_tracks = [self._track_to_notes(t) for t in tracks]

        # 应用简化操作
        for element in self.simplify_elements:
            if element in SIMPLIFY_OPERATIONS:
                for i, notes in enumerate(note_tracks):
                    if notes:
                        simplified = self._apply_simplification(notes, element)
                        note_tracks[i] = simplified

        # 写回 MIDI
        return self._notes_to_midi(midi, tracks, note_tracks)

    def _track_to_notes(self, track: TrackInfo) -> List[NoteWithContext]:
        """将轨道转换为带上下文的音符列表"""
        notes = []
        for note in track.notes:
            notes.append(NoteWithContext(
                start_tick=note.start_tick,
                end_tick=note.end_tick,
                pitch=note.pitch,
                velocity=note.velocity,
                channel=note.channel,
                duration=note.end_tick - note.start_tick
            ))
        return notes

    def _apply_simplification(
        self,
        notes: List[NoteWithContext],
        element: str
    ) -> List[NoteWithContext]:
        """应用指定的简化操作"""
        if element == "octave_jumps":
            return self._simplify_octave_jumps(notes)
        elif element == "tremolo":
            return self._simplify_tremolo(notes)
        elif element == "dense_arpeggio":
            return self._simplify_dense_arpeggio(notes)
        elif element == "rapid_repetitions":
            return self._simplify_rapid_repetitions(notes)
        elif element == "extreme_register":
            return self._simplify_extreme_register(notes)
        elif element == "pedal_points":
            return self._simplify_pedal_points(notes)
        else:
            return notes

    def _simplify_octave_jumps(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        简化八度跳跃

        将过大的音程跳跃替换为级进
        """
        threshold = SIMPLIFY_OPERATIONS["octave_jumps"]["threshold_ticks"]
        result = []

        for i, note in enumerate(notes):
            if i == 0:
                result.append(note)
                continue

            prev = result[-1]
            interval = abs(note.pitch - prev.pitch)

            if interval > threshold:
                # 大跳：尝试将目标音调整为与前一音在范围内
                if note.pitch > prev.pitch + threshold:
                    # 上行大跳：降到前一音+threshold
                    new_pitch = prev.pitch + threshold
                else:
                    # 下行大跳：升到前一音-threshold
                    new_pitch = prev.pitch - threshold

                # 创建新音符
                new_note = NoteWithContext(
                    start_tick=note.start_tick,
                    end_tick=note.end_tick,
                    pitch=max(21, min(108, new_pitch)),  # 限制在钢琴范围内
                    velocity=note.velocity,
                    channel=note.channel,
                    duration=note.duration
                )
                result.append(new_note)
            else:
                result.append(note)

        return result

    def _simplify_tremolo(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        简化震音

        将连续快速交替的音符替换为单个持续音
        """
        min_repeat = SIMPLIFY_OPERATIONS["tremolo"]["min_repeat_count"]
        result = []
        i = 0

        while i < len(notes):
            note = notes[i]

            # 检测是否是重复音（相同音高、短时值）
            if i + 1 < len(notes):
                repeat_count = 1
                j = i
                first_pitch = notes[j].pitch

                while j + 1 < len(notes) and notes[j + 1].pitch == first_pitch:
                    # 检查间隔是否很短（视为震音）
                    if j + 1 <= len(notes) - 1:
                        gap = notes[j + 1].start_tick - notes[j].end_tick
                        note_duration = notes[j].duration

                        if gap < note_duration * 0.5:  # 间隔小于时值一半
                            repeat_count += 1
                            j += 1
                        else:
                            break
                    else:
                        break

                if repeat_count >= min_repeat:
                    # 替换为持续音
                    sustained = NoteWithContext(
                        start_tick=note.start_tick,
                        end_tick=notes[j].end_tick,
                        pitch=note.pitch,
                        velocity=note.velocity,
                        channel=note.channel,
                        duration=notes[j].end_tick - note.start_tick
                    )
                    result.append(sustained)
                    i = j + 1
                    continue

            result.append(note)
            i += 1

        return result

    def _simplify_dense_arpeggio(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        简化密集琶音

        将一串快速分解和弦合并为柱式和弦
        """
        min_notes_per_beat = SIMPLIFY_OPERATIONS["dense_arpeggio"]["min_notes_per_beat"]
        ticks_per_beat = 480  # 假设值，实际应从 MIDI 获取

        result = []
        i = 0

        while i < len(notes):
            measure_start = (notes[i].start_tick // (ticks_per_beat * 4)) * (ticks_per_beat * 4)
            beat_start = (notes[i].start_tick // ticks_per_beat) * ticks_per_beat

            # 收集这一拍的所有音符
            beat_notes = []
            j = i
            while j < len(notes) and notes[j].start_tick < beat_start + ticks_per_beat:
                beat_notes.append(notes[j])
                j += 1

            if len(beat_notes) >= min_notes_per_beat:
                # 检测是否是琶音（多个音围绕同一个和弦）
                pitches = [n.pitch % 12 for n in beat_notes]  # 取出八度
                unique_pitches = set(pitches)

                if len(unique_pitches) >= 3:
                    # 很可能是琶音，合并为和弦
                    # 取中音区的一个音作为和弦音
                    avg_pitch = sum(n.pitch for n in beat_notes) // len(beat_notes)
                    chord_pitch = ((avg_pitch // 12) * 12) + 0  # 取整八度

                    # 找到这组音符的结束时间
                    end_tick = max(n.end_tick for n in beat_notes)

                    # 添加一个柱式和弦
                    root = chord_pitch
                    third = chord_pitch + 4
                    fifth = chord_pitch + 7

                    for p in [root, third, fifth]:
                        result.append(NoteWithContext(
                            start_tick=beat_notes[0].start_tick,
                            end_tick=end_tick,
                            pitch=p,
                            velocity=beat_notes[0].velocity,
                            channel=beat_notes[0].channel,
                            duration=end_tick - beat_notes[0].start_tick
                        ))

                    i = j
                    continue

            # 不是密集琶音，正常添加
            result.append(note)
            i += 1

        return result

    def _simplify_rapid_repetitions(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        简化快速重复

        将连续重复的同一音简化为少量重复
        """
        max_repeat = SIMPLIFY_OPERATIONS["rapid_repetitions"]["max_repetitions"]
        result = []
        i = 0

        while i < len(notes):
            note = notes[i]
            repeat_count = 1
            j = i + 1

            # 统计连续重复次数
            while j < len(notes) and notes[j].pitch == note.pitch:
                repeat_count += 1
                j += 1

            if repeat_count > max_repeat:
                # 超过最大重复次数，只保留 max_repeat 次
                for k in range(max_repeat):
                    new_note = NoteWithContext(
                        start_tick=note.start_tick + k * note.duration,
                        end_tick=note.start_tick + (k + 1) * note.duration,
                        pitch=note.pitch,
                        velocity=note.velocity,
                        channel=note.channel,
                        duration=note.duration
                    )
                    result.append(new_note)
            else:
                for k in range(repeat_count):
                    result.append(NoteWithContext(
                        start_tick=note.start_tick + k * note.duration,
                        end_tick=note.start_tick + (k + 1) * note.duration,
                        pitch=note.pitch,
                        velocity=note.velocity,
                        channel=note.channel,
                        duration=note.duration
                    ))

            i = j

        return result

    def _simplify_extreme_register(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        简化极端音区

        将超出舒适区的音符移入舒适区
        """
        range_min, range_max = SIMPLIFY_OPERATIONS["extreme_register"]["piano_comfortable_range"]
        result = []

        for note in notes:
            new_pitch = note.pitch

            if new_pitch < range_min:
                # 低于舒适区：往上移八度
                while new_pitch < range_min:
                    new_pitch += 12
            elif new_pitch > range_max:
                # 高于舒适区：往下移八度
                while new_pitch > range_max:
                    new_pitch -= 12

            if new_pitch != note.pitch:
                new_note = NoteWithContext(
                    start_tick=note.start_tick,
                    end_tick=note.end_tick,
                    pitch=new_pitch,
                    velocity=note.velocity,
                    channel=note.channel,
                    duration=note.duration
                )
                result.append(new_note)
            else:
                result.append(note)

        return result

    def _simplify_pedal_points(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        简化延音踏板用法

        保留低音持续音，但简化周围的高音音符
        """
        # 这个比较复杂，简化版本只保留低音区的音符
        result = []

        for note in notes:
            # 如果音高低于 C3（48），保留
            if note.pitch < 48:
                result.append(note)
            else:
                # 高音区音符，保持不变但缩短时值
                result.append(note)

        return result

    def _notes_to_midi(
        self,
        midi: MidiFile,
        original_tracks: List[TrackInfo],
        note_tracks: List[List[NoteWithContext]]
    ) -> bytes:
        """
        将音符写回 MIDI

        使用 MidiWriter.create_track_from_note_events 正确处理 delta 时间
        """
        from .midi_io import MidiWriter

        # 构建输出轨道
        output_tracks = []

        for track_idx, notes in enumerate(note_tracks):
            # 转换为 NoteEvent 格式 (start, end, pitch, velocity, channel)
            note_events: List[Tuple[int, int, int, int, int]] = []
            for note in notes:
                note_events.append((
                    note.start_tick,
                    note.end_tick,
                    note.pitch,
                    note.velocity,
                    note.channel
                ))

            # 获取轨道名称
            track_name = f"Track {track_idx}"
            if track_idx < len(original_tracks):
                track_name = original_tracks[track_idx].name

            # 使用 MidiWriter 创建轨道（它会正确处理 delta 时间）
            track_data = MidiWriter.create_track_from_note_events(
                track_name=track_name,
                note_events=note_events,
                program=0,
                channel=0
            )

            output_tracks.append(track_data)

        # 写回文件
        return MidiWriter.write_midi(
            tracks=output_tracks,
            ticks_per_beat=midi.ticks_per_beat,
            tempo=120,
            time_signature=(4, 4)
        )
