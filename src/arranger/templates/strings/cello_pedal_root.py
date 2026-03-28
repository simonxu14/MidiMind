"""
Strings: Cello Pedal Root 模板

大提琴持续音模板 - 在低音区保持根音持续音
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class CelloPedalRootTemplate(BaseTemplate):
    """
    大提琴持续根音模板

    适用于：大提琴
    适用于角色：bass

    参数：
    - velocity: 力度值
    - add_octave_bass: 是否在低音区加八度
    - sustain_legs: 每个根音持续的小节数
    """

    name = "cello_pedal_root"
    description = "大提琴持续根音"
    applicable_instruments = ["cello", "double_bass"]
    applicable_roles = ["bass", "inner_voice", "anchor", "bass_rhythm"]

    default_params = {
        "velocity": 60,
        "add_octave_bass": False,
        "sustain_legs": 2,
    }

    # 大提琴低音区
    BASS_RANGE = (36, 55)  # C2-G3

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成大提琴持续音

        在每个小节开始时放置根音，持续到下一小节
        """
        # 合并默认参数
        p = {**self.default_params, **params}
        velocity = p["velocity"]
        add_octave_bass = p["add_octave_bass"]
        sustain_legs = p["sustain_legs"]

        measure_len = context.measure_len
        notes: List[NoteEvent] = []
        channel = 2  # 大提琴默认 channel

        prev_root = None
        current_measure = 0

        # 遍历每个小节
        for measure_idx, chord_info in sorted(context.chord_per_measure.items()):
            root = chord_info.root

            # 调整根音到低音区
            pitch = root
            while pitch > self.BASS_RANGE[1]:
                pitch -= 12
            while pitch < self.BASS_RANGE[0]:
                pitch += 12

            measure_start = measure_idx * measure_len

            # 计算持续时长
            duration = measure_len * sustain_legs

            # 添加音符
            notes.append((measure_start, measure_start + duration, pitch, velocity, channel))

            # 如果需要，在低音区加八度
            if add_octave_bass:
                bass_pitch = pitch - 12
                if bass_pitch >= self.BASS_RANGE[0]:
                    notes.append((measure_start, measure_start + duration, bass_pitch, velocity - 5, channel))

            prev_root = root

        return notes
