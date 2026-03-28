"""
Strings: Ensemble Tutti 模板

弦乐合奏全奏模板 - 全体弦乐的齐奏
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class EnsembleTuttiTemplate(BaseTemplate):
    """
    弦乐合奏全奏模板

    适用于：小提琴，中提琴，大提琴，低音提琴
    适用于角色：tutti

    参数：
    - density: 密度 (0.0-1.0)
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - include_violin1: 是否包含第一小提琴
    - include_violin2: 是否包含第二小提琴
    - include_viola: 是否包含中提琴
    - include_cello: 是否包含大提琴
    - include_bass: 是否包含低音提琴
    """

    name = "ensemble_tutti"
    description = "弦乐合奏全奏"
    applicable_instruments = ["violin", "viola", "cello", "double_bass"]
    applicable_roles = ["tutti"]

    default_params = {
        "density": 0.8,
        "velocity_base": 70,
        "velocity_range": 10,
        "include_violin1": True,
        "include_violin2": True,
        "include_viola": True,
        "include_cello": True,
        "include_bass": True,
    }

    # 各声部的音区和channel
    INSTRUMENT_RANGES = {
        "violin1": (60, 84),   # G4-C7
        "violin2": (55, 79),   # G3-C7
        "viola": (48, 69),     # C3-A4
        "cello": (36, 60),     # C2-C4
        "bass": (28, 48),      # E1-C3
    }

    INSTRUMENT_CHANNELS = {
        "violin1": 0,
        "violin2": 1,
        "viola": 3,
        "cello": 2,
        "bass": 4,
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成弦乐合奏全奏

        多个弦乐声部同时演奏和弦
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]

        # 各声部的开关
        instruments_enabled = {
            "violin1": p.get("include_violin1", True),
            "violin2": p.get("include_violin2", True),
            "viola": p.get("include_viola", True),
            "cello": p.get("include_cello", True),
            "bass": p.get("include_bass", True),
        }

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat

        notes: List[NoteEvent] = []

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth
            seventh = getattr(chord_info, 'seventh', None)

            # 和弦音列表
            chord_tones = [root, third, fifth]
            if seventh is not None:
                chord_tones.append(seventh)

            measure_start = measure_idx * measure_len

            # 在第一拍和第三拍全奏
            strong_beats = [0, 2]

            for beat in strong_beats:
                if random.random() > density:
                    continue

                tick = measure_start + beat * quarter_note

                # 为每个启用的声部添加音符
                for inst_name, enabled in instruments_enabled.items():
                    if not enabled:
                        continue

                    pitch_min, pitch_max = self.INSTRUMENT_RANGES[inst_name]
                    channel = self.INSTRUMENT_CHANNELS[inst_name]

                    # 计算力度（低声部应该更突出）
                    # 传统管弦乐中，低音是基础，应该比高音更突出
                    if inst_name in ["bass"]:
                        velocity = velocity_base + 10  # 低音更突出
                    elif inst_name in ["cello"]:
                        velocity = velocity_base + 5
                    elif inst_name in ["viola"]:
                        velocity = velocity_base
                    else:
                        velocity = velocity_base - 5  # 小提琴稍弱，形成金字塔

                    velocity += random.randint(-velocity_range // 2, velocity_range // 2)
                    velocity = max(35, min(90, velocity))

                    # 时值
                    duration = int(quarter_note * 0.85)

                    # 为每个声部选择合适的音高
                    # 低音部只演奏根音，中高音部演奏完整和弦
                    chord_tones_for_voice = chord_tones
                    if inst_name in ["bass"]:
                        chord_tones_for_voice = [chord_tones[0]]  # 只演奏根音

                    for i, pitch in enumerate(chord_tones_for_voice):
                        # 调整到声部音区
                        adjusted_pitch = pitch
                        while adjusted_pitch < pitch_min:
                            adjusted_pitch += 12
                        while adjusted_pitch > pitch_max:
                            adjusted_pitch -= 12

                        note_velocity = velocity - (i * 2)
                        note_velocity = max(25, note_velocity)

                        notes.append((tick, tick + duration, adjusted_pitch, note_velocity, channel))

        return notes
