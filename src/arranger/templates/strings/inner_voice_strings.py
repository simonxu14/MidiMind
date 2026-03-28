"""
Strings: Inner Voice 模板

中提琴 16 分内声部，大提琴 8 分低音行进
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class ViolaInner16thsTemplate(BaseTemplate):
    """
    中提琴 16 分内声部

    适用于：大提琴、中提琴
    适用于角色：inner_voice

    模式：[third+12, fifth+12, root+24, fifth+12] 循环
    用于 B/C 段的内声部滚动
    """

    name = "viola_inner_16ths"
    description = "中提琴16分内声部"
    applicable_instruments = ["viola", "cello"]
    applicable_roles = ["inner_voice"]

    default_params = {
        "velocity_base": 38,
        "velocity_range": 6,
        "register_offsets": [12, 12, 24, 12],  # third, fifth, root+octave, fifth
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成中提琴 16 分内声部
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        offsets = p["register_offsets"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        sixteenth = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 1  # Viola channel

        melody_active_set = set(context.melody_onsets)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            # 16分音符循环：[third, fifth, root+octave, fifth]
            base_pitches = [
                third + offsets[0],
                fifth + offsets[1],
                root + offsets[2],
                fifth + offsets[3]
            ]

            measure_start = measure_idx * measure_len

            for sixteenth_idx in range(16):
                tick = measure_start + sixteenth_idx * sixteenth

                # 避开旋律 onset
                if self._is_near_melody_onset(tick, melody_active_set, 30):
                    continue

                pitch = base_pitches[sixteenth_idx % 4]

                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(28, min(60, velocity))

                duration = int(sixteenth * 0.9)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes

    def _is_near_melody_onset(self, tick: int, melody_onsets: set, window: int) -> bool:
        for onset in melody_onsets:
            if abs(tick - onset) < window:
                return True
        return False


class CelloBassWalkTemplate(BaseTemplate):
    """
    大提琴 8 分低音行进

    适用于：大提琴、低音提琴
    适用于角色：bass

    模式：[root-12, fifth-12, third-12, fifth-12] 循环
    用于 B/D 段的低音行进
    """

    name = "cello_bass_walk"
    description = "大提琴8分低音行进"
    applicable_instruments = ["cello", "double_bass"]
    applicable_roles = ["bass"]

    default_params = {
        "velocity_base": 48,
        "velocity_range": 8,
        "min_pitch": 28,  # 低音提琴最低音
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成大提琴 8 分低音行进
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        min_pitch = p["min_pitch"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        eighth = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 2  # Cello channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * measure_len

            # Bass walk 模式：[root-12, fifth-12, third-12, fifth-12]
            bass_pitches = [root - 12, fifth - 12, third - 12, fifth - 12]

            for eighth_idx in range(8):
                tick = measure_start + eighth_idx * eighth

                pitch = bass_pitches[eighth_idx % 4]

                # 确保不低于乐器最低音
                while pitch < min_pitch:
                    pitch += 12

                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(35, min(70, velocity))

                duration = int(eighth * 0.85)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes


class FluteImitativeMotifTemplate(BaseTemplate):
    """
    木管模仿动机

    适用于：长笛、双簧管、单簧管
    适用于角色：countermelody

    在旋律空隙处插入短模仿动机
    Motif: [third+24, fifth+24, root+36, fifth+24]
    """

    name = "flute_imitative_motif"
    description = "木管模仿动机"
    applicable_instruments = ["flute", "oboe", "clarinet"]
    applicable_roles = ["countermelody"]

    default_params = {
        "velocity_base": 45,
        "velocity_range": 8,
        "motif_offsets": [24, 24, 36, 24],  # third, fifth, root+octave, fifth
        "min_rest_ticks": 480,  # 最小空隙长度（1拍）
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成木管模仿动机
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        offsets = p["motif_offsets"]
        min_rest = p["min_rest_ticks"]

        ticks_per_beat = context.ticks_per_beat
        eighth = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 5  # Default winds channel

        # 计算旋律区间
        melody_ranges = self._get_melody_ranges(context.melody_onsets, context.measure_len)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * context.measure_len

            # 在旋律空隙处插入动机
            motif = [third + offsets[0], fifth + offsets[1],
                    root + offsets[2], fifth + offsets[3]]

            # 查找该小节的空隙
            rest_start = measure_start
            while rest_start < measure_start + context.measure_len:
                # 找到下一个旋律音
                next_onset = self._next_melody_onset(rest_start, melody_ranges)

                if next_onset is None:
                    # 剩余都是空隙
                    rest_end = measure_start + context.measure_len
                else:
                    rest_end = next_onset

                rest_length = rest_end - rest_start

                # 如果空隙够长，插入动机
                if rest_length >= min_rest:
                    # 动机放在空隙开头
                    motif_start = rest_start + eighth // 2  # 稍微往后放

                    # 确保动机在空隙内
                    if motif_start + eighth * 4 <= rest_end - eighth // 2:
                        for i, offset in enumerate(motif):
                            tick = motif_start + i * eighth

                            velocity = velocity_base + random.randint(-velocity_range, velocity_range)
                            velocity = max(32, min(62, velocity))

                            duration = int(eighth * 0.9)
                            notes.append((tick, tick + duration, offset, velocity, channel))

                        # 跳过动机占据的区域
                        rest_start = motif_start + eighth * 4
                    else:
                        rest_start = rest_end
                else:
                    rest_start = rest_end

        return notes

    def _get_melody_ranges(self, onsets: List[int], measure_len: int) -> List[Tuple[int, int]]:
        """获取旋律区间列表"""
        ranges = []
        for onset in onsets:
            ranges.append((onset, onset + measure_len // 4))  # 假设每个音持续1/4小节
        return sorted(ranges)

    def _next_melody_onset(self, tick: int, ranges: List[Tuple[int, int]]) -> int:
        """找到下一个旋律音"""
        for start, end in ranges:
            if start >= tick:
                return start
        return None


class SustainPadTemplate(BaseTemplate):
    """
    持续垫底音型

    适用于：圆号、长笛、双簧管
    适用于角色：sustain_support

    长音垫底，不抢戏
    """

    name = "sustain_pad"
    description = "持续垫底长音"
    applicable_instruments = ["horn", "flute", "oboe"]
    applicable_roles = ["sustain_support"]

    default_params = {
        "velocity_base": 42,
        "velocity_range": 4,
        "root_offset": 0,
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成持续垫底音
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        root_offset = p["root_offset"]

        notes: List[NoteEvent] = []
        channel = 4  # Horn channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * context.measure_len

            # 持续音放在每小节第 2 拍后半拍
            tick = measure_start + context.ticks_per_beat + context.ticks_per_beat // 4

            pitch = root + root_offset

            velocity = velocity_base
            duration = int(context.measure_len * 0.6)

            notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
