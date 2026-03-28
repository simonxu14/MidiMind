"""
Piano: Piano Melody 模板

钢琴旋律模板 - 演奏主旋律
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class PianoMelodyTemplate(BaseTemplate):
    """
    钢琴旋律模板

    适用于：钢琴
    适用于角色：melody, counter_melody

    参数：
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - density: 密度 (0.0-1.0)
    """

    name = "piano_melody"
    description = "钢琴旋律"
    applicable_instruments = ["piano"]
    applicable_roles = ["melody", "counter_melody"]

    default_params = {
        "velocity_base": 75,
        "velocity_range": 20,
        "density": 0.8,
    }

    # 钢琴音域
    PIANO_RANGE = (48, 84)  # C3-C6

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成钢琴旋律

        基于旋律 onset 生成主旋律线条
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        density = p["density"]

        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 0  # Piano channel

        # 基于旋律 onset 生成音符
        for onset in context.melody_onsets:
            if random.random() > density:
                continue

            measure_idx = onset // context.measure_len

            # 获取当前小节和弦
            chord = context.chord_per_measure.get(measure_idx)
            if not chord:
                continue

            # 旋律音候选：根音、三音、五音
            melody_tones = [chord.root, chord.third, chord.fifth]

            # 选择音高
            pitch = random.choice(melody_tones)

            # 调整到钢琴音区
            while pitch < self.PIANO_RANGE[0]:
                pitch += 12
            while pitch > self.PIANO_RANGE[1]:
                pitch -= 12

            # 计算力度
            velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
            velocity = max(40, min(100, velocity))

            # 时值 - 跟随旋律 onset
            duration = int(quarter_note * 0.9)

            notes.append((onset, onset + duration, pitch, velocity, channel))

        return notes