"""
Brass: Trombone Anchor 模板

长号锚定音模板 - 低音区的持续锚定音
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class TromboneAnchorTemplate(BaseTemplate):
    """
    长号锚定音模板

    适用于：长号
    适用于角色：bass, anchor

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - anchor_beats: 锚定拍数 (1-4)
    """

    name = "trombone_anchor"
    description = "长号锚定音"
    applicable_instruments = ["trombone"]
    applicable_roles = ["bass", "anchor", "bass_rhythm"]

    default_params = {
        "density": 0.8,
        "velocity_base": 65,
        "velocity_range": 8,
        "anchor_beats": 2,
    }

    # 长号低音区
    TROMBONE_RANGE = (40, 58)  # E2-G3

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成长号锚定音

        在低音区演奏持续的低音
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        anchor_beats = p["anchor_beats"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 10  # Trombone channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * measure_len

            # 计算锚定音持续时长
            duration_ticks = ticks_per_beat * anchor_beats
            remaining_ticks = measure_len

            pos = 0
            while remaining_ticks > 0:
                if random.random() > density:
                    pos += 1
                    remaining_ticks -= ticks_per_beat
                    continue

                tick = measure_start + pos * ticks_per_beat

                # 调整根音到长号音区
                pitch = root
                while pitch > self.TROMBONE_RANGE[1]:
                    pitch -= 12
                while pitch < self.TROMBONE_RANGE[0]:
                    pitch += 12

                # 计算力度
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(35, min(85, velocity))

                # 时值
                actual_duration = min(duration_ticks, remaining_ticks)

                notes.append((tick, tick + actual_duration, pitch, velocity, channel))

                remaining_ticks -= ticks_per_beat
                pos += 1

        return notes
