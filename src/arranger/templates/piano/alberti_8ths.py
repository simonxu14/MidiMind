"""
Piano: Alberti 8ths 模板

阿尔贝蒂低音伴奏型：低-高-高-中的八分音符模式
贝多芬、莫扎特常用的伴奏音型
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class Alberti8thsTemplate(BaseTemplate):
    """
    阿尔贝蒂低音模板

    适用于：钢琴
    适用于角色：accompaniment, inner_voice

    模式：根音 - 五音 - 三音 - 五音（八分音符）
    这是一个经典的古典时期伴奏音型
    """

    name = "alberti_8ths"
    description = "阿尔贝蒂低音"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment", "inner_voice"]

    default_params = {
        "density": 1.0,        # 1.0 = 完整阿尔贝蒂模式
        "velocity_base": 50,
        "velocity_range": 8,
        "register": "middle",
    }

    # 阿尔贝蒂模式：根音-五音-三音-五音
    ALBERTI_PATTERN = [0, 4, 2, 4]  # 相对于根音的偏移

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成阿尔贝蒂低音

        模式：低-高-高-中
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]

        # 获取音区范围
        register_ranges = {
            "low": (48, 60),
            "middle": (55, 67),
            "high": (60, 72),
        }
        pitch_min, pitch_max = register_ranges.get(register, register_ranges["middle"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        eight_note = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 0

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            # 阿尔贝蒂模式：根音-五音-三音-五音
            base_pitches = [root, fifth, third, fifth]

            measure_start = measure_idx * measure_len

            for beat in range(4):  # 4个八分音符
                pos_in_measure = beat * eight_note
                tick = measure_start + pos_in_measure

                # 获取当前音高
                pitch_offset = self.ALBERTI_PATTERN[beat]
                pitch = base_pitches[beat % len(base_pitches)]

                # 调整到目标音区
                while pitch < pitch_min:
                    pitch += 12
                while pitch > pitch_max:
                    pitch -= 12

                # 计算力度（阿尔贝蒂模式通常力度较轻）
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(30, min(80, velocity))

                # 时值
                duration = int(eight_note * 0.85)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
