"""
Piano: Arpeggio 16ths 模板

16分音符分解和弦，用于 B/C 段的高密度织体
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class Arpeggio16thsTemplate(BaseTemplate):
    """
    16分音符分解和弦模板

    适用于：钢琴
    适用于角色：accompaniment, inner_voice

    模式：根音+24 - 三音+24 - 五音+24 - 三音+24（16分音符）
    用于更明亮/流动的段落
    """

    name = "arpeggio_16ths"
    description = "16分音符分解和弦"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment", "inner_voice"]

    default_params = {
        "velocity_base": 45,
        "velocity_range": 6,
        "register_offset": 24,  # 音区偏移
        "syncopation": 0.0,
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成 16 分音符分解和弦
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register_offset = p["register_offset"]
        syncopation = p["syncopation"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        sixteenth = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 0

        # 获取旋律 active 时刻（用于避让）
        melody_active_set = set(context.melody_onsets)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            # 16分音符模式：上行分解
            base_pitches = [root + register_offset, third + register_offset,
                           fifth + register_offset, third + register_offset]

            measure_start = measure_idx * measure_len

            for sixteenth_idx in range(16):
                tick = measure_start + sixteenth_idx * sixteenth

                # 可选：避让旋律强点
                if syncopation > 0 and random.random() < syncopation:
                    # 随机跳过一些音符制造切分感
                    continue

                # 避开旋律 onset 附近
                if self._is_near_melody_onset(tick, melody_active_set, 30):
                    continue

                pitch = base_pitches[sixteenth_idx % 4]

                # 力度
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(25, min(65, velocity))

                duration = int(sixteenth * 0.85)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes

    def _is_near_melody_onset(self, tick: int, melody_onsets: set, window: int) -> bool:
        """检查是否在旋律 onset 附近"""
        for onset in melody_onsets:
            if abs(tick - onset) < window:
                return True
        return False


class RegisterShiftTemplate(BaseTemplate):
    """
    音区换位分解和弦

    适用于：钢琴
    适用于角色：accompaniment

    模式：前半小节低音区，后半小节高音区
    用于 C (明亮) 段的色彩变化
    """

    name = "register_shift"
    description = "音区换位分解和弦"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment"]

    default_params = {
        "velocity_base": 42,
        "velocity_range": 6,
        "low_offset": 24,   # 低音区偏移
        "high_offset": 36,  # 高音区偏移
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成音区换位分解和弦
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        low_offset = p["low_offset"]
        high_offset = p["high_offset"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        sixteenth = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 0

        melody_active_set = set(context.melody_onsets)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * measure_len
            mid_measure = measure_start + measure_len // 2

            for sixteenth_idx in range(16):
                tick = measure_start + sixteenth_idx * sixteenth

                # 决定当前音区
                if tick < mid_measure:
                    # 前半：低音区
                    base_pitches = [root + low_offset, third + low_offset,
                                   fifth + low_offset, third + low_offset]
                else:
                    # 后半：高音区
                    base_pitches = [root + high_offset, third + high_offset,
                                   fifth + high_offset, third + high_offset]

                pitch = base_pitches[sixteenth_idx % 4]

                # 避开旋律
                if self._is_near_melody_onset(tick, melody_active_set, 30):
                    continue

                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(25, min(60, velocity))

                duration = int(sixteenth * 0.85)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes

    def _is_near_melody_onset(self, tick: int, melody_onsets: set, window: int) -> bool:
        for onset in melody_onsets:
            if abs(tick - onset) < window:
                return True
        return False


class TremoloLikeTemplate(BaseTemplate):
    """
    类颤音/重复音型

    适用于：钢琴
    适用于角色：accompaniment

    模式：重复根音 + 低八度支撑（16分音符）
    用于 D (高潮) 段增加驱动感
    """

    name = "tremolo_like"
    description = "类颤音重复音型"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment"]

    default_params = {
        "velocity_base": 48,
        "velocity_range": 6,
        "hi_offset": 36,  # 高音根音偏移
        "lo_offset": 12,  # 低音八度偏移
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成类颤音重复音型
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        hi_offset = p["hi_offset"]
        lo_offset = p["lo_offset"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        sixteenth = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 0

        melody_active_set = set(context.melody_onsets)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * measure_len

            for sixteenth_idx in range(16):
                tick = measure_start + sixteenth_idx * sixteenth

                # 高音根音（每4个16分音符的第1个）
                if sixteenth_idx % 4 == 0:
                    pitch = root + hi_offset

                    # 避开旋律
                    if self._is_near_melody_onset(tick, melody_active_set, 30):
                        continue

                    velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                    velocity = max(30, min(70, velocity))

                    duration = int(sixteenth * 0.9)
                    notes.append((tick, tick + duration, pitch, velocity, channel))

                # 低音八度支撑（每2个16分音符的第1个）
                if sixteenth_idx % 2 == 0:
                    pitch_lo = root + lo_offset

                    velocity = velocity_base - 8 + random.randint(-velocity_range // 2, velocity_range // 2)
                    velocity = max(25, min(60, velocity))

                    duration = int(sixteenth * 0.85)
                    notes.append((tick, tick + duration, pitch_lo, velocity, channel))

        return notes

    def _is_near_melody_onset(self, tick: int, melody_onsets: set, window: int) -> bool:
        for onset in melody_onsets:
            if abs(tick - onset) < window:
                return True
        return False


class SustainArpeggioSparseTemplate(BaseTemplate):
    """
    稀疏持续分解和弦

    适用于：钢琴
    适用于角色：accompaniment

    模式：稀疏的分解和弦，用于 A (透明) 段
    比普通 arpeggio 更稀疏，力度更轻
    """

    name = "sustain_arpeggio_sparse"
    description = "稀疏持续分解和弦"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment"]

    default_params = {
        "velocity_base": 38,
        "velocity_range": 4,
        "register_offset": 24,
        "density": 0.5,  # 50% 的位置有音
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成稀疏持续分解和弦
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register_offset = p["register_offset"]
        density = p["density"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        eighth = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 0

        melody_active_set = set(context.melody_onsets)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            base_pitches = [root + register_offset, third + register_offset, fifth + register_offset]

            measure_start = measure_idx * measure_len

            for eighth_idx in range(8):
                # 稀疏：只在部分位置放音
                if random.random() > density:
                    continue

                tick = measure_start + eighth_idx * eighth

                # 避开旋律
                if self._is_near_melody_onset(tick, melody_active_set, 60):
                    continue

                pitch = base_pitches[eighth_idx % 3]

                velocity = velocity_base + random.randint(-velocity_range, velocity_range)
                velocity = max(25, min(55, velocity))

                duration = int(eighth * 1.5)  # 长一点更稀疏

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes

    def _is_near_melody_onset(self, tick: int, melody_onsets: set, window: int) -> bool:
        for onset in melody_onsets:
            if abs(tick - onset) < window:
                return True
        return False


class OctaveSupportTemplate(BaseTemplate):
    """
    八度支撑音型

    适用于：钢琴
    适用于角色：accompaniment

    模式：根音+八度的快速支撑
    用于 D (高潮) 段增加厚度
    """

    name = "octave_support"
    description = "八度支撑音型"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment"]

    default_params = {
        "velocity_base": 52,
        "velocity_range": 6,
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成八度支撑音型
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        eighth = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 0

        melody_active_set = set(context.melody_onsets)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * measure_len

            for eighth_idx in range(4):  # 每拍一次
                tick = measure_start + eighth_idx * eighth * 2

                # 避开旋律
                if self._is_near_melody_onset(tick, melody_active_set, 60):
                    continue

                # 根音
                pitch = root + 12  # 高八度

                velocity = velocity_base + random.randint(-velocity_range, velocity_range)
                velocity = max(30, min(72, velocity))

                duration = int(eighth * 1.2)
                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes

    def _is_near_melody_onset(self, tick: int, melody_onsets: set, window: int) -> bool:
        for onset in melody_onsets:
            if abs(tick - onset) < window:
                return True
        return False
