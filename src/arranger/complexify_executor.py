"""
ComplexifyExecutor - 难度提升执行器

负责：
1. 在保持旋律轮廓的前提下添加装饰
2. 增加八度位移、和声丰富度
3. 添加对位旋律
"""

from __future__ import annotations

import random
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .plan_schema import UnifiedPlan, NoteEvent
from .midi_io import MidiReader, MidiFile, TrackInfo


# ============ 复杂化操作符定义 ============

COMPLEXIFY_OPERATIONS = {
    "octave_displacement": {
        "description": "添加八度位移",
        "probability": 0.3,  # 30% 的音符添加八度
    },
    "ornamental_figures": {
        "description": "添加装饰音型",
        "types": ["mordent", "turn", "trill", "appoggiatura"],
        "probability": 0.4,
    },
    "arpeggio_passages": {
        "description": "添加琶音经过句",
        "probability": 0.2,
        "min_chord_size": 3,  # 至少3个音才展开
    },
    "counter_melody": {
        "description": "添加对位旋律",
        "probability": 0.3,
        "voice_range": (48, 72),  # 中音区
    },
    "richer_texture": {
        "description": "丰富织体",
        "chord_thickness": 3,  # 和弦厚度
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


class ComplexifyExecutor:
    """
    难度提升执行器

    使用说明：
    1. 设置目标难度级别
    2. 指定要复杂化的元素
    3. execute() 返回复杂化后的 MIDI
    """

    def __init__(self, plan: UnifiedPlan):
        self.plan = plan
        self.difficulty = plan.difficulty
        self.complexify_elements = self.difficulty.complexify_elements if self.difficulty else []

    def execute(self, input_midi: bytes) -> bytes:
        """
        执行难度提升

        Args:
            input_midi: 输入 MIDI 二进制数据

        Returns:
            复杂化后的 MIDI 二进制数据
        """
        # 读取 MIDI
        midi = MidiReader.read_midi(input_midi)
        tracks = MidiReader.extract_track_messages(midi)

        # 转换为内部表示
        note_tracks = [self._track_to_notes(t) for t in tracks]

        # 应用复杂化操作
        for element in self.complexify_elements:
            if element in COMPLEXIFY_OPERATIONS:
                for i, notes in enumerate(note_tracks):
                    if notes:
                        complexified = self._apply_complexification(notes, element, note_tracks)
                        note_tracks[i] = complexified

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
                channel=note.channel
            ))
        return notes

    def _apply_complexification(
        self,
        notes: List[NoteWithContext],
        element: str,
        all_tracks: List[List[NoteWithContext]]
    ) -> List[NoteWithContext]:
        """应用指定的复杂化操作"""
        if element == "octave_displacement":
            return self._add_octave_displacement(notes)
        elif element == "ornamental_figures":
            return self._add_ornamental_figures(notes)
        elif element == "arpeggio_passages":
            return self._add_arpeggio_passages(notes)
        elif element == "counter_melody":
            return self._add_counter_melody(notes, all_tracks)
        elif element == "richer_texture":
            return self._enrich_texture(notes)
        else:
            return notes

    def _add_octave_displacement(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        添加八度位移

        随机选择一些音符添加八度双音
        """
        probability = COMPLEXIFY_OPERATIONS["octave_displacement"]["probability"]
        result = []

        for note in notes:
            result.append(note)

            # 随机决定是否添加八度
            if random.random() < probability:
                direction = random.choice([-1, 1])  # 上或下八度
                octave_pitch = note.pitch + (direction * 12)

                # 检查是否在钢琴范围内
                if 21 <= octave_pitch <= 108:
                    # 在原音符旁边添加八度音
                    octave_note = NoteWithContext(
                        start_tick=note.start_tick,
                        end_tick=note.end_tick,
                        pitch=octave_pitch,
                        velocity=note.velocity - 10,  # 八度音稍弱
                        channel=note.channel
                    )
                    result.append(octave_note)

        return result

    def _add_ornamental_figures(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        添加装饰音型

        在主要音符前添加倚音、回音、颤音等
        """
        types = COMPLEXIFY_OPERATIONS["ornamental_figures"]["types"]
        probability = COMPLEXIFY_OPERATIONS["ornamental_figures"]["probability"]
        result = []

        for i, note in enumerate(notes):
            result.append(note)

            # 随机决定是否添加装饰音
            if random.random() < probability:
                ornament_type = random.choice(types)
                ornament_notes = self._create_ornament(note, ornament_type)

                # 装饰音插入到主要音符之前
                for orn_note in ornament_notes:
                    result.append(orn_note)

        return result

    def _create_ornament(
        self,
        main_note: NoteWithContext,
        ornament_type: str
    ) -> List[NoteWithContext]:
        """
        创建指定类型的装饰音

        Args:
            main_note: 主要音符
            ornament_type: 装饰音类型

        Returns:
            装饰音列表
        """
        ornaments = []
        tick_gap = main_note.start_tick

        if ornament_type == "mordent":
            # 回音：从主音上方二度开始，回到主音，再到下方二度，再回主音
            upper = main_note.pitch + 1
            lower = main_note.pitch - 1
            duration = max(30, main_note.duration // 4)

            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration * 3,
                end_tick=tick_gap - duration * 2,
                pitch=upper,
                velocity=main_note.velocity - 5,
                channel=main_note.channel
            ))
            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration * 2,
                end_tick=tick_gap - duration,
                pitch=main_note.pitch,
                velocity=main_note.velocity - 5,
                channel=main_note.channel
            ))
            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration,
                end_tick=tick_gap,
                pitch=lower,
                velocity=main_note.velocity - 5,
                channel=main_note.channel
            ))

        elif ornament_type == "turn":
            # 回旋：主音-下方二度-主音-上方二度-主音
            upper = main_note.pitch + 2
            lower = main_note.pitch - 2
            duration = max(20, main_note.duration // 5)

            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration * 4,
                end_tick=tick_gap - duration * 3,
                pitch=main_note.pitch,
                velocity=main_note.velocity - 5,
                channel=main_note.channel
            ))
            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration * 3,
                end_tick=tick_gap - duration * 2,
                pitch=lower,
                velocity=main_note.velocity - 5,
                channel=main_note.channel
            ))
            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration * 2,
                end_tick=tick_gap - duration,
                pitch=main_note.pitch,
                velocity=main_note.velocity - 5,
                channel=main_note.channel
            ))
            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration,
                end_tick=tick_gap,
                pitch=upper,
                velocity=main_note.velocity - 5,
                channel=main_note.channel
            ))

        elif ornament_type == "trill":
            # 颤音：主音和上方二度快速交替，以主音结束
            upper = main_note.pitch + 1
            duration = max(10, main_note.duration // 8)

            # 计算结束时间，确保解决到主音
            trill_duration = main_note.duration // 2
            current_tick = tick_gap - trill_duration

            # 交替次数（确保奇数次，最后落在主音）
            num_alternations = (trill_duration // duration) // 2
            if num_alternations % 2 == 0:
                num_alternations += 1

            for i in range(num_alternations):
                # 主音
                ornaments.append(NoteWithContext(
                    start_tick=current_tick,
                    end_tick=current_tick + duration,
                    pitch=main_note.pitch,
                    velocity=main_note.velocity - 5,
                    channel=main_note.channel
                ))
                current_tick += duration

                # 上方音
                ornaments.append(NoteWithContext(
                    start_tick=current_tick,
                    end_tick=current_tick + duration,
                    pitch=upper,
                    velocity=main_note.velocity - 5,
                    channel=main_note.channel
                ))
                current_tick += duration

            # 确保结束在主音（填补剩余时间）
            if current_tick < tick_gap:
                ornaments.append(NoteWithContext(
                    start_tick=current_tick,
                    end_tick=tick_gap,
                    pitch=main_note.pitch,
                    velocity=main_note.velocity - 5,
                    channel=main_note.channel
                ))

        elif ornament_type == "appoggiatura":
            # 倚音：从上方或下方二度开始，解决到主音
            direction = random.choice([-1, 1])
            accented_pitch = main_note.pitch + direction
            duration = max(30, main_note.duration // 3)

            ornaments.append(NoteWithContext(
                start_tick=tick_gap - duration,
                end_tick=tick_gap,
                pitch=accented_pitch,
                velocity=main_note.velocity + 5,  # 倚音稍强
                channel=main_note.channel
            ))

        return ornaments

    def _add_arpeggio_passages(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        添加琶音经过句

        将和弦展开为上行或下行的琶音
        """
        min_chord_size = COMPLEXIFY_OPERATIONS["arpeggio_passages"]["min_chord_size"]
        probability = COMPLEXIFY_OPERATIONS["arpeggio_passages"]["probability"]
        result = []

        i = 0
        while i < len(notes):
            # 检查是否是和弦（同时开始的多个音符）
            start_tick = notes[i].start_tick
            chord_notes = [notes[i]]

            j = i + 1
            while j < len(notes) and notes[j].start_tick == start_tick:
                chord_notes.append(notes[j])
                j += 1

            if len(chord_notes) >= min_chord_size and random.random() < probability:
                # 将和弦展开为琶音
                pitches = sorted([n.pitch for n in chord_notes])
                direction = random.choice([1, -1])  # 上行或下行

                arpeggio_duration = chord_notes[0].duration // len(pitches)
                current_tick = start_tick

                for k, pitch in enumerate(pitches):
                    if direction == 1:
                        arp_pitch = pitches[k]
                    else:
                        arp_pitch = pitches[len(pitches) - 1 - k]

                    result.append(NoteWithContext(
                        start_tick=current_tick,
                        end_tick=current_tick + arpeggio_duration,
                        pitch=arp_pitch,
                        velocity=chord_notes[0].velocity,
                        channel=chord_notes[0].channel
                    ))
                    current_tick += arpeggio_duration

            else:
                for n in chord_notes:
                    result.append(n)

            i = j

        return result

    def _add_counter_melody(
        self,
        notes: List[NoteWithContext],
        all_tracks: List[List[NoteWithContext]]
    ) -> List[NoteWithContext]:
        """
        添加对位旋律

        在内声部创建一条对位旋律
        """
        probability = COMPLEXIFY_OPERATIONS["counter_melody"]["probability"]
        voice_range = COMPLEXIFY_OPERATIONS["counter_melody"]["voice_range"]

        result = list(notes)  # 保留原旋律

        if random.random() < probability:
            # 获取主旋律的音符时值信息
            if not notes:
                return result

            # 创建对位旋律（简化版本）
            ticks_per_beat = 480
            measure_len = ticks_per_beat * 4

            # 在主旋律的间隙添加对位音符
            prev_end = notes[0].start_tick
            for note in notes:
                gap = note.start_tick - prev_end

                if gap > ticks_per_beat * 2:  # 有足够的间隙
                    # 在间隙中间放置对位音符
                    counter_pitch = random.randint(voice_range[0], voice_range[1])
                    counter_duration = min(gap // 2, ticks_per_beat * 2)

                    result.append(NoteWithContext(
                        start_tick=prev_end + gap // 4,
                        end_tick=prev_end + gap // 4 + counter_duration,
                        pitch=counter_pitch,
                        velocity=note.velocity - 15,
                        channel=note.channel
                    ))

                prev_end = max(prev_end, note.end_tick)

        return result

    def _enrich_texture(
        self,
        notes: List[NoteWithContext]
    ) -> List[NoteWithContext]:
        """
        丰富织体

        在保持旋律的基础上，添加和声支撑
        """
        chord_thickness = COMPLEXIFY_OPERATIONS["richer_texture"]["chord_thickness"]
        result = []

        for note in notes:
            result.append(note)

            # 找到当前音符的和弦音
            # 简化：添加根音、三音、五音的八度移位
            root = note.pitch
            third = note.pitch + 4
            fifth = note.pitch + 7

            # 只在高音区添加和声支撑（不干扰主旋律）
            if note.pitch >= 60 and len(result) < 50:  # 限制添加数量
                pitches = [root, third, fifth]
                for p in pitches:
                    if p != note.pitch and p <= 84:  # 不超过高音C
                        result.append(NoteWithContext(
                            start_tick=note.start_tick,
                            end_tick=note.end_tick,
                            pitch=p,
                            velocity=note.velocity - 20,
                            channel=note.channel
                        ))

        return result

    def _notes_to_midi(
        self,
        midi: MidiFile,
        original_tracks: List[TrackInfo],
        note_tracks: List[List[NoteWithContext]]
    ) -> bytes:
        """将音符写回 MIDI

        使用 MidiWriter.create_track_from_note_events 正确处理 delta 时间
        """
        from .midi_io import MidiWriter

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

        return MidiWriter.write_midi(
            tracks=output_tracks,
            ticks_per_beat=midi.ticks_per_beat,
            tempo=120,
            time_signature=(4, 4)
        )
