"""
Piano: Arpeggio 模板

琶音伴奏型：和弦音逐个上升或下降
适合古典、浪漫风格
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class ArpeggioTemplate(BaseTemplate):
    """
    琶音伴奏模板

    适用于：钢琴
    适用于角色：accompaniment, inner_voice

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (low/middle/high)
    - direction: 琶音方向 (up/down)
    - rhythm_pattern: 节奏模式 (16ths/8ths/triplets)
    """

    name = "arpeggio"
    description = "琶音伴奏型"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment", "inner_voice"]

    default_params = {
        "density": 0.8,
        "velocity_base": 52,
        "velocity_range": 10,
        "register": "middle",
        "direction": "up",
        "rhythm_pattern": "16ths",
    }

    REGISTER_RANGES = {
        "low": (48, 64),
        "middle": (55, 72),
        "high": (60, 80),
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成琶音

        在一拍内快速演奏和弦音
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        direction = p["direction"]
        rhythm_pattern = p["rhythm_pattern"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["middle"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat

        # 根据节奏模式计算音符间距
        if rhythm_pattern == "16ths":
            note_spacing = ticks_per_beat // 4
            notes_per_beat = 4
        elif rhythm_pattern == "triplets":
            note_spacing = ticks_per_beat // 3
            notes_per_beat = 3
        else:  # 8ths
            note_spacing = ticks_per_beat // 2
            notes_per_beat = 2

        notes: List[NoteEvent] = []
        channel = 0

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth
            seventh = getattr(chord_info, 'seventh', None)

            # 和弦音列表
            chord_tones = [root, third, fifth]
            if seventh is not None:
                chord_tones.append(seventh)

            # 根据方向排序
            if direction == "down":
                chord_tones = list(reversed(chord_tones))

            measure_start = measure_idx * measure_len

            for beat in range(4):
                if random.random() > density:
                    continue

                beat_start = measure_start + beat * ticks_per_beat

                for i, pitch in enumerate(chord_tones):
                    tick = beat_start + i * note_spacing

                    # 调整到目标音区
                    adjusted_pitch = pitch
                    while adjusted_pitch < pitch_min:
                        adjusted_pitch += 12
                    while adjusted_pitch > pitch_max:
                        adjusted_pitch -= 12

                    # 计算力度（渐强或渐弱）
                    if direction == "up":
                        velocity = velocity_base + (i * velocity_range // len(chord_tones))
                    else:
                        velocity = velocity_base + ((len(chord_tones) - 1 - i) * velocity_range // len(chord_tones))

                    velocity += random.randint(-velocity_range // 3, velocity_range // 3)
                    velocity = max(25, min(80, velocity))

                    # 时值
                    duration = int(note_spacing * 0.8)

                    notes.append((tick, tick + duration, adjusted_pitch, velocity, channel))

        return notes
