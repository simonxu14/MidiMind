"""
Strings: Violin Cantabile 模板

小提琴如歌旋律模板 - 抒情性的旋律线条
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class ViolinCantabileTemplate(BaseTemplate):
    """
    小提琴如歌旋律模板

    适用于：小提琴
    适用于角色：melody, counter_melody

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (middle/high)
    - phrase_length: 乐句长度（小节数）
    """

    name = "violin_cantabile"
    description = "小提琴如歌旋律"
    applicable_instruments = ["violin"]
    applicable_roles = ["melody", "counter_melody", "inner_voice"]

    default_params = {
        "density": 0.5,
        "velocity_base": 65,
        "velocity_range": 15,
        "register": "high",
        "phrase_length": 4,
    }

    REGISTER_RANGES = {
        "low": (55, 69),
        "middle": (60, 74),
        "high": (67, 84),
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成小提琴如歌旋律

        在高音区演奏连贯的旋律线条
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        phrase_length = p["phrase_length"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["high"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 0  # Violin I channel

        # 按小节分组
        measures = sorted(context.chord_per_measure.items())

        measure_idx = 0
        while measure_idx < len(measures):
            # 检查是否是乐句开头
            if measure_idx % phrase_length == 0:
                # 乐句开始，生成旋律音
                for i in range(phrase_length):
                    if measure_idx + i >= len(measures):
                        break

                    chord_info = measures[measure_idx + i][1]
                    root = chord_info.root
                    third = chord_info.third
                    fifth = chord_info.fifth

                    measure_start = (measure_idx + i) * measure_len

                    # 在每小节的第一拍和第三拍放长音
                    long_notes_positions = [0, 2]

                    for pos in long_notes_positions:
                        if random.random() > density:
                            continue

                        tick = measure_start + pos * quarter_note

                        # 选择旋律音（根音或五音居多）
                        if random.random() < 0.7:
                            pitch = root
                        else:
                            pitch = random.choice([third, fifth])

                        # 调整到目标音区
                        while pitch < pitch_min:
                            pitch += 12
                        while pitch > pitch_max:
                            pitch -= 12

                        # 计算力度
                        velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                        velocity = max(35, min(85, velocity))

                        # 时值（长音）
                        duration = int(quarter_note * 1.8)

                        notes.append((tick, tick + duration, pitch, velocity, channel))

            measure_idx += 1

        return notes
