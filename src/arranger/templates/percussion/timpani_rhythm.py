"""
Percussion: Timpani Rhythm 模板

定音鼓节奏模板 - 低音鼓的节奏支持

P3 修复：
- pitch 范围约束到 45-53 (合理定音鼓音域)
- 降低 velocity_base 到更合理的范围
- 使用 melodic channel (不用 percussion channel 9)
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
    - velocity_base: 基础力度 (P3: 降低到 50)
    - velocity_range: 力度变化范围
    - pattern: 节奏模式 (quarter/eighth/mixed)
    - accent_first: 是否强调第一拍
    - pitch_range: (min, max) pitch 范围约束
    """

    name = "timpani_rhythm"
    description = "定音鼓节奏"
    applicable_instruments = ["timpani", "percussion", "drums", "drum_set"]
    applicable_roles = ["bass_rhythm", "accent", "percussion"]

    default_params = {
        "density": 0.8,
        "velocity_base": 50,  # P3: 降低力度
        "velocity_range": 12,
        "pattern": "quarter",
        "accent_first": True,
        "pitch_min": 45,  # P3: D2-C3 range
        "pitch_max": 53,  # P3: F3
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成定音鼓节奏

        P3: pitch 范围约束到 45-53
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        pattern = p["pattern"]
        accent_first = p["accent_first"]
        pitch_min = p.get("pitch_min", 45)
        pitch_max = p.get("pitch_max", 53)

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 0  # P3: Melodic channel (not percussion channel 9)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root

            measure_start = measure_idx * measure_len

            # P3: 将根音映射到 pitch_min-pitch_max 范围内
            # 根音通常在中音区，向下映射到定音鼓音域
            base_pitch = max(pitch_min, min(pitch_max, root - 12))  # 根音下移八度并 clamp

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
                velocity = max(35, min(75, velocity))  # P3: 限制范围

                # P3: pitch 约束在 pitch_min-pitch_max 范围内
                pitch = base_pitch

                # 时值
                duration = int(quarter_note * 0.5)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
