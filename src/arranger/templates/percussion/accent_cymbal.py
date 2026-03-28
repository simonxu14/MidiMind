"""
Percussion: Accent Cymbal 模板

镲片重音模板 - 强调音上的镲片
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class AccentCymbalTemplate(BaseTemplate):
    """
    镲片重音模板

    适用于：cymbal
    适用于角色：accent

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - accent_beats: 重音拍位 (list)
    """

    name = "accent_cymbal"
    description = "镲片重音"
    applicable_instruments = ["cymbal", "percussion", "drum_set", "drums"]
    applicable_roles = ["accent", "percussion"]

    default_params = {
        "density": 0.5,
        "velocity_base": 80,
        "velocity_range": 10,
        "accent_beats": [0, 2],
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成镲片重音

        在指定拍位演奏镲片
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        accent_beats = p["accent_beats"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 12  # Percussion channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            measure_start = measure_idx * measure_len

            for beat in accent_beats:
                if random.random() > density:
                    continue

                tick = measure_start + beat * quarter_note

                # 计算力度
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(50, min(100, velocity))

                # 镲片音高
                pitch = 76  # 高音

                # 时值（短促）
                duration = int(quarter_note * 0.3)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
