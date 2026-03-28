"""
Brass: Trumpet Fanfare 模板

小号号角性模板 - 强劲有力的节奏型
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class TrumpetFanfareTemplate(BaseTemplate):
    """
    小号号角性模板

    适用于：小号
    适用于角色：fanfare, accent

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - pattern: 节奏模式 (four_on_floor/offbeat_emphasis/synocopated)
    """

    name = "trumpet_fanfare"
    description = "小号号角性"
    applicable_instruments = ["trumpet"]
    applicable_roles = ["fanfare", "accent"]

    default_params = {
        "density": 0.7,
        "velocity_base": 75,
        "velocity_range": 8,
        "pattern": "four_on_floor",
    }

    # 小号音域
    TRUMPET_RANGE = (55, 77)  # G3-D6

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成小号号角性节奏

        在重拍演奏有力的节奏型
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        pattern = p["pattern"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 9  # Trumpet channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            # 和弦音
            chord_tones = [root, third, fifth]

            measure_start = measure_idx * measure_len

            # 根据模式决定演奏位置
            if pattern == "four_on_floor":
                positions = [0, 1, 2, 3]  # 每拍都演奏
            elif pattern == "offbeat_emphasis":
                positions = [0, 2]  # 只在第一、三拍
            else:  # syncopated
                positions = [0, 1, 3]  # 切分模式

            for beat in positions:
                if random.random() > density:
                    continue

                tick = measure_start + beat * quarter_note

                # 调整根音到小号音区
                pitch = chord_tones[beat % len(chord_tones)]
                while pitch > self.TRUMPET_RANGE[1]:
                    pitch -= 12
                while pitch < self.TRUMPET_RANGE[0]:
                    pitch += 12

                # 计算力度（强拍更强）
                if beat in [0, 2]:
                    velocity = velocity_base + velocity_range // 2
                else:
                    velocity = velocity_base - velocity_range // 4

                velocity += random.randint(-velocity_range // 3, velocity_range // 3)
                velocity = max(40, min(95, velocity))

                # 时值
                duration = int(quarter_note * 0.7)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
