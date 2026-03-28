"""
Winds: Bassoon Bass Line 模板

低音巴松管低音线模板 - 低音区的独立低音线
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class BassoonBassLineTemplate(BaseTemplate):
    """
    低音巴松管低音线模板

    适用于：bassoon
    适用于角色：bass

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - add_octave: 是否在低音区加八度
    """

    name = "bassoon_bass_line"
    description = "低音巴松管低音线"
    applicable_instruments = ["bassoon", "double_bass", "contrabass"]
    applicable_roles = ["bass", "inner_voice", "bass_rhythm"]

    default_params = {
        "density": 0.7,
        "velocity_base": 58,
        "velocity_range": 10,
        "add_octave": False,
    }

    # 巴松管低音区
    BASSOON_RANGE = (34, 52)  # Bb0-F3

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成低音巴松管低音线

        在低音区演奏四分音符的低音线
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        add_octave = p["add_octave"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 8  # Bassoon channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * measure_len

            for beat in range(4):
                if random.random() > density:
                    continue

                tick = measure_start + beat * quarter_note

                # 调整根音到低音区
                pitch = root
                while pitch > self.BASSOON_RANGE[1]:
                    pitch -= 12
                while pitch < self.BASSOON_RANGE[0]:
                    pitch += 12

                # 计算力度
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(30, min(80, velocity))

                # 时值
                duration = int(quarter_note * 0.85)

                notes.append((tick, tick + duration, pitch, velocity, channel))

                # 添加八度低音
                if add_octave:
                    bass_pitch = pitch - 12
                    if bass_pitch >= self.BASSOON_RANGE[0]:
                        notes.append((tick, tick + duration, bass_pitch, velocity - 5, channel))

        return notes
