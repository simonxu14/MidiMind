"""
Piano: Offbeat Dyads 模板

弱拍双音伴奏型：在弱拍上演奏双音
适合爵士和声或现代风格
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class OffbeatDyadsTemplate(BaseTemplate):
    """
    弱拍双音模板

    适用于：钢琴
    适用于角色：accompaniment, inner_voice

    在弱拍位置演奏双音，创造有节奏感的伴奏织体
    """

    name = "offbeat_dyads"
    description = "弱拍双音"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment", "inner_voice"]

    default_params = {
        "density": 0.7,        # 0-1，密度
        "velocity_base": 48,
        "velocity_range": 10,
        "register": "middle",
        "dyad_interval": 3,    # 双音音程（3=小三度，4=大三度，5=纯四度）
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成弱拍双音

        在弱拍（第二、第四拍）演奏双音
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        dyad_interval = p["dyad_interval"]

        register_ranges = {
            "low": (48, 64),
            "middle": (55, 72),
            "high": (60, 80),
        }
        pitch_min, pitch_max = register_ranges.get(register, register_ranges["middle"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []
        channel = 0

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * measure_len

            # 在第二、四拍（弱拍）演奏
            offbeat_positions = [
                quarter_note + quarter_note // 2,  # 第二拍后半
                quarter_note * 3 + quarter_note // 2,  # 第四拍后半
            ]

            for pos in offbeat_positions:
                # 根据密度决定是否演奏
                if random.random() > density:
                    continue

                tick = measure_start + pos

                # 双音：第一音为根音或三音，第二音为指定音程
                dyad_type = random.choice(["root-third", "root-fifth", "third-fifth"])

                if dyad_type == "root-third":
                    pitch1 = root
                    pitch2 = third
                elif dyad_type == "root-fifth":
                    pitch1 = root
                    pitch2 = fifth
                else:
                    pitch1 = third
                    pitch2 = fifth

                # 调整到目标音区
                while pitch1 < pitch_min:
                    pitch1 += 12
                while pitch1 > pitch_max:
                    pitch1 -= 12

                pitch2 = pitch1 + dyad_interval
                while pitch2 > pitch_max:
                    pitch2 -= 12

                # 力度
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(25, min(70, velocity))

                # 时值
                duration = int(quarter_note * 0.4)

                notes.append((tick, tick + duration, pitch1, velocity, channel))
                notes.append((tick, tick + duration, pitch2, velocity - 3, channel))

        return notes
