"""
Brass: Trumpet Melody 模板

小号旋律模板 - 演奏主旋律线条
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class TrumpetMelodyTemplate(BaseTemplate):
    """
    小号旋律模板

    适用于：小号
    适用于角色：melody

    参数：
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (middle/high)
    """

    name = "trumpet_melody"
    description = "小号旋律"
    applicable_instruments = ["trumpet"]
    applicable_roles = ["melody", "counter_melody", "accent"]

    default_params = {
        "velocity_base": 80,
        "velocity_range": 15,
        "register": "high",
    }

    # 小号音域
    TRUMPET_RANGE = (55, 82)  # G3-E7

    REGISTER_RANGES = {
        "low": (55, 70),
        "middle": (62, 77),
        "high": (70, 82),
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成小号旋律

        基于旋律 onset 生成主旋律线条
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["high"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 9  # Trumpet channel

        # 基于旋律 onset 生成音符
        for onset in context.melody_onsets:
            if random.random() > 0.7:  # 密度控制
                continue

            measure_idx = onset // measure_len
            beat_in_measure = (onset % measure_len) // quarter_note

            # 获取当前小节和弦
            chord = context.chord_per_measure.get(measure_idx)
            if not chord:
                continue

            # 旋律音候选：根音、三音、五音
            melody_tones = [chord.root, chord.third, chord.fifth]

            # 选择音高
            pitch = random.choice(melody_tones)

            # 调整到目标音区
            while pitch < pitch_min:
                pitch += 12
            while pitch > pitch_max:
                pitch -= 12

            # 计算力度
            velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
            velocity = max(50, min(100, velocity))

            # 时值 - 跟随旋律 onset
            duration = int(quarter_note * 0.9)

            notes.append((onset, onset + duration, pitch, velocity, channel))

        return notes