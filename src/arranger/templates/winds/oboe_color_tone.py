"""
Winds: Oboe Color Tone 模板

双簧管色彩音模板 - 带有装饰音的旋律
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class OboeColorToneTemplate(BaseTemplate):
    """
    双簧管色彩音模板

    适用于：双簧管
    适用于角色：melody, counter_melody

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (middle/high)
    - add_ornaments: 是否添加装饰音
    """

    name = "oboe_color_tone"
    description = "双簧管色彩音"
    applicable_instruments = ["oboe"]
    applicable_roles = ["melody", "counter_melody", "inner_voice"]

    default_params = {
        "density": 0.5,
        "velocity_base": 62,
        "velocity_range": 10,
        "register": "high",
        "add_ornaments": True,
    }

    REGISTER_RANGES = {
        "low": (55, 69),
        "middle": (60, 74),
        "high": (67, 79),
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成双簧管色彩音

        在中音区演奏带有装饰音的旋律
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        add_ornaments = p["add_ornaments"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["high"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat
        eighth_note = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 7  # Oboe channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * measure_len

            # 在第一拍和第三拍放置长音
            for beat in [0, 2]:
                if random.random() > density:
                    continue

                tick = measure_start + beat * quarter_note

                # 选择旋律音
                if random.random() < 0.6:
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

                # 时值
                duration = int(quarter_note * 1.5)

                notes.append((tick, tick + duration, pitch, velocity, channel))

                # 添加装饰音
                if add_ornaments and random.random() < 0.5:
                    ornament_pitch = pitch + random.choice([2, 4, 7])  # 上方二度、四度、五度
                    while ornament_pitch > pitch_max:
                        ornament_pitch -= 12

                    ornament_velocity = velocity - 8
                    ornament_duration = int(eighth_note * 0.5)

                    notes.append((tick + int(eighth_note * 0.3), tick + int(eighth_note * 0.3) + ornament_duration, ornament_pitch, ornament_velocity, channel))

        return notes
