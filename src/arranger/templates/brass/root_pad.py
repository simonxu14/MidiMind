"""
Brass: Root Pad 模板

圆号根音 PAD 模板 - 柔和的根音和声
"""

from __future__ import annotations

from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class RootPadTemplate(BaseTemplate):
    """
    圆号根音 PAD 模板

    适用于：horn
    适用于角色：sustain_support

    参数：
    - velocity: 力度值
    - voicing: 排列方式 (close/open)
    - add_third: 是否加三音
    - add_fifth: 是否加五音
    """

    name = "root_pad"
    description = "圆号根音PAD"
    applicable_instruments = ["horn", "french_horn"]
    applicable_roles = ["sustain_support", "inner_voice", "melody"]

    default_params = {
        "velocity": 50,
        "voicing": "close",
        "add_third": True,
        "add_fifth": True,
    }

    # 圆号音域
    HORN_RANGE = (40, 65)  # E2-F4

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成圆号 PAD

        在每个小节放置根音及可选的三音、五音
        """
        # 合并默认参数
        p = {**self.default_params, **params}
        velocity = p["velocity"]
        voicing = p["voicing"]
        add_third = p["add_third"]
        add_fifth = p["add_fifth"]

        measure_len = context.measure_len
        notes: List[NoteEvent] = []
        channel = 4  # 圆号默认 channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * measure_len

            # 调整到圆号音域
            root_pitch = self._adjust_to_range(root, self.HORN_RANGE)
            third_pitch = self._adjust_to_range(third, self.HORN_RANGE)
            fifth_pitch = self._adjust_to_range(fifth, self.HORN_RANGE)

            # 密排列 vs 开放排列
            if voicing == "close":
                # 密排列：根音-三音-五音紧密
                pitches = [root_pitch]
                if add_third:
                    pitches.append(third_pitch)
                if add_fifth:
                    pitches.append(fifth_pitch)
            else:
                # 开放排列：根音-五音-三音（或再加根音）
                pitches = [root_pitch]
                if add_fifth:
                    pitches.append(fifth_pitch)
                if add_third:
                    pitches.append(third_pitch)

            # 去除重复音高
            pitches = list(dict.fromkeys(pitches))

            # 每个音持续一小节
            duration = measure_len

            for pitch in pitches:
                notes.append((measure_start, measure_start + duration, pitch, velocity, channel))

        return notes

    def _adjust_to_range(self, pitch: int, range_tuple: tuple) -> int:
        """调整音高到指定范围"""
        min_pitch, max_pitch = range_tuple

        # 如果在范围内，直接返回
        if min_pitch <= pitch <= max_pitch:
            return pitch

        # 调整
        while pitch < min_pitch:
            pitch += 12
        while pitch > max_pitch:
            pitch -= 12

        return pitch
