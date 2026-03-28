"""
Winds: Flute Countermelody 模板

长笛对位旋律模板 - 高音区的对位旋律
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class FluteCountermelodyTemplate(BaseTemplate):
    """
    长笛对位旋律模板

    适用于：长笛
    适用于角色：counter_melody

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (middle/high)
    """

    name = "flute_countermelody"
    description = "长笛对位旋律"
    applicable_instruments = ["flute"]
    applicable_roles = ["counter_melody", "inner_voice"]

    default_params = {
        "density": 0.6,
        "velocity_base": 60,
        "velocity_range": 12,
        "register": "high",
    }

    REGISTER_RANGES = {
        "low": (60, 74),
        "middle": (67, 79),
        "high": (72, 84),
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成长笛对位旋律

        在高音区演奏对位旋律线条
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["high"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        eighth_note = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 5  # Flute channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            # 旋律音候选
            melody_tones = [root, third, fifth]

            measure_start = measure_idx * measure_len

            for beat in range(4):
                # 每个八分音符位置
                for sub_beat in range(2):
                    tick = measure_start + beat * ticks_per_beat + sub_beat * eighth_note

                    if random.random() > density:
                        continue

                    # 选择旋律音
                    pitch = random.choice(melody_tones)

                    # 调整到目标音区
                    while pitch < pitch_min:
                        pitch += 12
                    while pitch > pitch_max:
                        pitch -= 12

                    # 计算力度
                    velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                    velocity = max(30, min(80, velocity))

                    # 时值
                    duration = int(eighth_note * 0.85)

                    notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
