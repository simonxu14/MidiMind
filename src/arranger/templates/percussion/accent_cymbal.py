"""
Percussion: Accent Cymbal 模板

镲片重音模板 - 强调音上的镲片

P3 修复：
- 三角铁使用 GM percussion channel=9, note=81
- 降低 velocity_base 到更合理的范围
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class AccentCymbalTemplate(BaseTemplate):
    """
    镲片重音模板

    适用于：cymbal, percussion (triangle)
    适用于角色：accent, percussion

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度 (P3: 降低到 35)
    - velocity_range: 力度变化范围
    - accent_beats: 重音拍位 (list)
    """

    name = "accent_cymbal"
    description = "镲片/三角铁重音"
    applicable_instruments = ["cymbal", "percussion", "drum_set", "drums"]
    applicable_roles = ["accent", "percussion"]

    default_params = {
        "density": 0.5,
        "velocity_base": 35,  # P3: 降低力度，符合"弱奏点缀"
        "velocity_range": 10,
        "accent_beats": [0, 2],
    }

    # GM percussion map
    GM_TRIANGLE = 81  # Open Triangle
    GM_PERCUSSION_CHANNEL = 9

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成镲片/三角铁重音

        P3: 使用 GM percussion channel=9, triangle=81
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
        # P3: 使用 GM percussion channel
        channel = self.GM_PERCUSSION_CHANNEL  # = 9
        # P3: 使用 GM triangle note
        pitch = self.GM_TRIANGLE  # = 81 (Open Triangle)

        for measure_idx, chord_info in context.chord_per_measure.items():
            measure_start = measure_idx * measure_len

            for beat in accent_beats:
                if random.random() > density:
                    continue

                tick = measure_start + beat * quarter_note

                # 计算力度
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(25, min(50, velocity))  # P3: 限制在 25-50

                # 时值（短促）
                duration = int(quarter_note * 0.3)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
