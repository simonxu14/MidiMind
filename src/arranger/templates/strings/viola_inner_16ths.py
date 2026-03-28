"""
Strings: Viola Inner 16ths 模板

中提琴内声部模板 - 快速的十六分音符内声部
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class ViolaInner16thsTemplate(BaseTemplate):
    """
    中提琴内声部十六分音符模板

    适用于：中提琴
    适用于角色：inner_voice

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (middle/high)
    """

    name = "viola_inner_16ths"
    description = "中提琴内声部十六分音符"
    applicable_instruments = ["viola"]
    applicable_roles = ["inner_voice"]

    default_params = {
        "density": 0.6,
        "velocity_base": 50,
        "velocity_range": 10,
        "register": "middle",
    }

    REGISTER_RANGES = {
        "low": (48, 62),
        "middle": (55, 69),
        "high": (60, 74),
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成中提琴内声部

        在中音区演奏十六分音符的流动织体
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["middle"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        sixteenth = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 3  # Viola channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            # 和弦音列表
            chord_tones = [root, third, fifth]

            measure_start = measure_idx * measure_len

            # 十六分音符模式
            for beat in range(4):
                beat_start = measure_start + beat * ticks_per_beat

                for sixteenth_idx in range(4):
                    tick = beat_start + sixteenth_idx * sixteenth

                    # 根据密度决定是否演奏
                    if random.random() > density:
                        continue

                    # 选择和弦音
                    pitch = random.choice(chord_tones)

                    # 调整到目标音区
                    while pitch < pitch_min:
                        pitch += 12
                    while pitch > pitch_max:
                        pitch -= 12

                    # 计算力度
                    velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                    velocity = max(30, min(75, velocity))

                    # 时值
                    duration = int(sixteenth * 0.7)

                    notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
