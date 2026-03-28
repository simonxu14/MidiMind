"""
Piano: Chord Block 模板

和弦块伴奏型：同时演奏多个音
适合摇滚、流行风格
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class ChordBlockTemplate(BaseTemplate):
    """
    和弦块伴奏模板

    适用于：钢琴
    适用于角色：accompaniment, inner_voice

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (low/middle/high)
    - chord_tone_count: 同时演奏的音数 (3-5)
    """

    name = "chord_block"
    description = "和弦块伴奏型"
    applicable_instruments = ["piano"]
    applicable_roles = ["accompaniment", "inner_voice"]

    default_params = {
        "density": 0.5,
        "velocity_base": 60,
        "velocity_range": 12,
        "register": "middle",
        "chord_tone_count": 3,
    }

    REGISTER_RANGES = {
        "low": (48, 60),
        "middle": (55, 67),
        "high": (60, 72),
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成和弦块

        在重拍位置演奏完整的和弦
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        chord_tone_count = p["chord_tone_count"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["middle"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 0

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth
            seventh = getattr(chord_info, 'seventh', None)

            # 和弦音列表
            chord_tones = [root, third, fifth]
            if seventh is not None and chord_tone_count >= 4:
                chord_tones.append(seventh)
            chord_tones = chord_tones[:chord_tone_count]

            measure_start = measure_idx * measure_len

            # 在第一、三拍（重拍）演奏和弦
            strong_beats = [0, 2]

            for beat in strong_beats:
                if random.random() > density:
                    continue

                tick = measure_start + beat * quarter_note

                # 计算力度
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(30, min(90, velocity))

                # 时值
                duration = int(quarter_note * 0.9)

                for i, pitch in enumerate(chord_tones):
                    # 调整到目标音区
                    adjusted_pitch = pitch
                    while adjusted_pitch < pitch_min:
                        adjusted_pitch += 12
                    while adjusted_pitch > pitch_max:
                        adjusted_pitch -= 12

                    # 各声部力度略有差异
                    note_velocity = velocity - (i * 3)
                    note_velocity = max(25, note_velocity)

                    notes.append((tick, tick + duration, adjusted_pitch, note_velocity, channel))

        return notes
