"""
Winds: Clarinet Sustain 模板

单簧管持续音模板 - 绵延的持续音
"""

from __future__ import annotations

from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class ClarinetSustainTemplate(BaseTemplate):
    """
    单簧管持续音模板

    适用于：单簧管
    适用于角色：sustain_support, inner_voice

    参数：
    - velocity: 力度值
    - voicing: 排列方式 (close/open)
    - add_third: 是否加三音
    """

    name = "clarinet_sustain"
    description = "单簧管持续音"
    applicable_instruments = ["clarinet", "saxophone", "tenor_sax", "sax"]
    applicable_roles = ["sustain_support", "inner_voice", "counter_melody", "melody"]

    default_params = {
        "velocity": 55,
        "voicing": "close",
        "add_third": True,
    }

    # 单簧管音域
    CLARINET_RANGE = (50, 72)  # Eb3-D6

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成单簧管持续音

        在每个小节放置持续的和弦音
        """
        p = {**self.default_params, **params}
        velocity = p["velocity"]
        voicing = p["voicing"]
        add_third = p["add_third"]

        measure_len = context.measure_len
        notes: List[NoteEvent] = []
        channel = 6  # Clarinet channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * measure_len

            # 调整到单簧管音域
            root_pitch = self._adjust_to_range(root, self.CLARINET_RANGE)
            third_pitch = self._adjust_to_range(third, self.CLARINET_RANGE)
            fifth_pitch = self._adjust_to_range(fifth, self.CLARINET_RANGE)

            if voicing == "close":
                pitches = [root_pitch]
                if add_third:
                    pitches.append(third_pitch)
                pitches.append(fifth_pitch)
            else:
                pitches = [root_pitch, fifth_pitch]
                if add_third:
                    pitches.append(third_pitch)

            # 去除重复
            pitches = list(dict.fromkeys(pitches))

            duration = measure_len

            for pitch in pitches:
                notes.append((measure_start, measure_start + duration, pitch, velocity, channel))

        return notes

    def _adjust_to_range(self, pitch: int, range_tuple: tuple) -> int:
        """调整音高到指定范围"""
        min_pitch, max_pitch = range_tuple

        if min_pitch <= pitch <= max_pitch:
            return pitch

        while pitch < min_pitch:
            pitch += 12
        while pitch > max_pitch:
            pitch -= 12

        return pitch
