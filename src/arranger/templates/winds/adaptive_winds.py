"""
Winds: Adaptive Winds 模板

自适应木管内声部：根据风格和速度动态调整的木管内声部
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class AdaptiveWindsTemplate(BaseTemplate):
    """
    自适应木管内声部模板

    适用于：单簧管、双簧管、巴松管、长笛
    适用于角色：inner_voice, sustain_support

    根据风格调整演奏法：
    - ballad: 柔和的连奏
    - general: 流畅的八分音符
    - upbeat: 活跃的十六分音符
    - dance: 节奏感强的跳音
    """

    name = "adaptive_winds"
    description = "自适应木管内声部"
    applicable_instruments = ["clarinet", "oboe", "flute", "bassoon"]
    applicable_roles = ["inner_voice", "sustain_support"]

    default_params = {
        "density": 0.5,
        "velocity_base": 52,
        "velocity_range": 10,
        "register": "middle",
        "articulation": "legato",  # legato, detached, mixed
    }

    REGISTER_RANGES = {
        "flute": (60, 84),      # C4-A6
        "oboe": (58, 75),        # Bb3-G5
        "clarinet": (50, 72),    # Eb3-D6
        "bassoon": (34, 55),      # Bb1-G3
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成自适应木管内声部

        根据风格选择最佳演奏模式
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        articulation = p["articulation"]

        # 优先使用传入的 style/tempo
        style = p.get("style", getattr(context, 'style', 'general'))
        tempo = p.get("tempo", getattr(context, 'tempo', 120))
        instrument = p.get("instrument", "clarinet")

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat
        eighth_note = ticks_per_beat // 2
        sixteenth_note = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 6  # Default clarinet channel

        # 获取上一小节根音
        prev_root = getattr(context, 'prev_chord_root', None)

        # 选择音区范围
        pitch_ranges = self.REGISTER_RANGES.get(instrument, self.REGISTER_RANGES["clarinet"])
        pitch_min, pitch_max = pitch_ranges

        # 根据风格选择节奏模式
        if style == "ballad":
            # Ballad: 柔和的长音
            positions = [(0, quarter_note * 1.5), (quarter_note * 2.5, quarter_note * 1.2)]
            note_duration = int(quarter_note * 1.2)
            local_density = density * 0.4
            articulation = "legato"
        elif style == "dance":
            # Dance: 活跃的跳音
            positions = [(i * eighth_note, 0) for i in range(8)]
            note_duration = int(eighth_note * 0.4)
            local_density = density
            articulation = "detached"
        elif style == "upbeat":
            # Upbeat: 快速的十六分音符
            positions = []
            for beat in range(4):
                for sixteenth in range(4):
                    positions.append((beat * quarter_note + sixteenth * sixteenth_note, 0))
            note_duration = int(sixteenth_note * 0.5)
            local_density = density * 0.8
        else:
            # General: 流畅的八分音符
            positions = [
                (0, 0),
                (eighth_note, 0),
                (quarter_note, 0),
                (quarter_note + eighth_note, 0),
                (quarter_note * 2, 0),
                (quarter_note * 2 + eighth_note, 0),
                (quarter_note * 3, 0),
            ]
            note_duration = int(eighth_note * 0.6)
            local_density = density * 0.6

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth
            seventh = getattr(chord_info, 'seventh', None)

            measure_start = measure_idx * measure_len

            # 构建和弦音
            chord_tones = [root, third, fifth]
            if seventh is not None:
                chord_tones.append(seventh)

            # 生成音符
            for i, (pos, offset) in enumerate(positions):
                if random.random() > local_density:
                    continue

                tick = measure_start + pos + int(offset)

                # 选择和弦音
                pitch_idx = i % len(chord_tones)
                pitch = chord_tones[pitch_idx]

                # 调整到目标音区
                while pitch < pitch_min:
                    pitch += 12
                while pitch > pitch_max:
                    pitch -= 12

                # 声部连接
                if prev_root is not None and i == 0:
                    common_tone = self._find_common_tone(prev_root, root, chord_tones)
                    if common_tone is not None:
                        pitch = common_tone

                # 计算力度
                if articulation == "detached" or style == "dance":
                    velocity = velocity_base + random.randint(0, velocity_range // 2)
                else:
                    velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)

                velocity = max(30, min(80, velocity))

                # 根据 articulation 调整时值
                if articulation == "legato":
                    actual_duration = int(note_duration * 1.3)
                elif articulation == "detached":
                    actual_duration = int(note_duration * 0.5)
                else:
                    actual_duration = note_duration

                notes.append((tick, tick + actual_duration, pitch, velocity, channel))

            prev_root = root

        return notes

    def _find_common_tone(self, prev_root: int, curr_root: int, chord_tones: List[int]) -> int:
        """找两个和弦的共同音"""
        prev_intervals = [(n - prev_root) % 12 for n in chord_tones]
        curr_intervals = [(n - curr_root) % 12 for n in chord_tones]

        common = set(prev_intervals) & set(curr_intervals)
        if common:
            interval = list(common)[0]
            return chord_tones[curr_intervals.index(interval)]
        return None
