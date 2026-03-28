"""
Percussion: Timpani Rhythm 模板

定音鼓节奏模板 - 低音鼓的节奏支持
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class TimpaniRhythmTemplate(BaseTemplate):
    """
    定音鼓节奏模板

    适用于：timpani
    适用于角色：bass_rhythm

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - pattern: 节奏模式 (quarter/eighth/mixed)
    - accent_first: 是否强调第一拍
    """

    name = "timpani_rhythm"
    description = "定音鼓节奏"
    applicable_instruments = ["timpani", "percussion", "drums", "drum_set"]
    applicable_roles = ["bass_rhythm", "accent", "percussion"]

    default_params = {
        "density": 0.8,
        "velocity_base": 70,
        "velocity_range": 12,
        "pattern": "quarter",
        "accent_first": True,
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成定音鼓节奏

        在低音区演奏节奏型
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        pattern = p["pattern"]
        accent_first = p["accent_first"]

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 11  # Timpani channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * measure_len

            # 根据模式决定演奏位置
            if pattern == "quarter":
                positions = [0, 1, 2, 3]
            elif pattern == "eighth":
                positions = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]
            else:  # mixed
                positions = [0, 1, 2, 3]
                # 随机添加一些八分音符位置
                if random.random() < 0.5:
                    positions.append(0.5)
                if random.random() < 0.5:
                    positions.append(2.5)

            for pos in positions:
                if random.random() > density:
                    continue

                tick = measure_start + int(pos * quarter_note)

                # 计算力度
                beat_num = int(pos)
                if accent_first and beat_num == 0:
                    velocity = velocity_base + velocity_range // 2
                else:
                    velocity = velocity_base - velocity_range // 4

                velocity += random.randint(-velocity_range // 3, velocity_range // 3)
                velocity = max(40, min(95, velocity))

                # 定音鼓没有明确音高，用根音表示
                pitch = 36  # C2

                # 时值
                duration = int(quarter_note * 0.5)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
