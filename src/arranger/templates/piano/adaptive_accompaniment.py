"""
Piano: Adaptive Accompaniment 模板

自适应伴奏型：根据风格和速度动态调整的伴奏
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class AdaptiveAccompanimentTemplate(BaseTemplate):
    """
    自适应伴奏模板

    适用于：钢琴
    适用于角色：accompaniment, inner_voice

    根据 tempo 和 style 动态调整伴奏模式：
    - ballad: 稀疏、柔和的和弦
    - general: 平衡的分解和弦
    - upbeat: 活跃的八分音符
    - dance: 强劲的节奏型
    """

    name = "adaptive_accompaniment"
    description = "自适应钢琴伴奏"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment", "inner_voice"]

    default_params = {
        "density": 0.7,
        "velocity_base": 52,
        "velocity_range": 10,
        "register": "middle",
        "voicing": "close",  # close or open
        "rhythm_complexity": 0.5,  # 0-1, 节奏复杂度
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
        生成自适应伴奏

        根据风格和速度选择最佳伴奏模式
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        voicing = p["voicing"]
        rhythm_complexity = p["rhythm_complexity"]

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["middle"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat
        eighth_note = ticks_per_beat // 2
        sixteenth_note = ticks_per_beat // 4

        # 根据风格选择模式
        style = getattr(context, 'style', 'general')
        tempo = getattr(context, 'tempo', 120)

        notes: List[NoteEvent] = []
        channel = 0

        # 获取上一小节根音（用于声部连接）
        prev_root = getattr(context, 'prev_chord_root', None)

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth
            seventh = getattr(chord_info, 'seventh', None)

            measure_start = measure_idx * measure_len

            # 根据风格选择节奏模式
            if style == "ballad":
                # Ballad: 稀疏、慢节奏，每小节2-4个音
                positions = [(0, quarter_note * 2), (quarter_note * 2, quarter_note * 3)]
                note_duration = quarter_note * 1.5
                local_density = density * 0.5
            elif style == "dance":
                # Dance: 强劲节奏，每拍都弹
                positions = [(0, 0), (eighth_note, 0), (quarter_note, 0), (quarter_note + eighth_note, 0),
                            (quarter_note * 2, 0), (quarter_note * 2 + eighth_note, 0), (quarter_note * 3, 0)]
                note_duration = eighth_note * 0.7
                local_density = density
            else:
                # General/Upbeat: 平衡模式
                positions = [(0, 0), (eighth_note, 0), (quarter_note, 0), (quarter_note * 2 + eighth_note, 0),
                            (quarter_note * 3, 0)]
                note_duration = eighth_note * 0.8
                local_density = density * 0.7

            # 构建和弦音（根据voicing）
            if voicing == "close":
                chord_tones = [root, third, fifth]
                if seventh is not None:
                    chord_tones.append(seventh)
            else:  # open
                chord_tones = [root, fifth, third]
                if seventh is not None:
                    chord_tones.append(seventh)

            # 生成音符
            for i, (pos, offset) in enumerate(positions):
                if random.random() > local_density:
                    continue

                tick = measure_start + pos

                # 选择和弦音（循环使用）
                pitch_idx = i % len(chord_tones)
                pitch = chord_tones[pitch_idx]

                # 调整到目标音区（优化声部连接）
                while pitch < pitch_min:
                    pitch += 12
                while pitch > pitch_max:
                    pitch -= 12

                # 如果有上一小节根音，尽量保持共同音
                if prev_root is not None and i == 0:
                    # 检查是否是共同音
                    common_tone = self._find_common_tone(prev_root, root, chord_tones)
                    if common_tone is not None:
                        pitch = common_tone

                # 计算力度
                if style == "dance":
                    # Dance 风格强拍更强
                    if i % 2 == 0:
                        velocity = velocity_base + velocity_range // 2
                    else:
                        velocity = velocity_base - velocity_range // 4
                else:
                    velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)

                velocity = max(25, min(85, velocity))

                notes.append((tick, tick + note_duration, pitch, velocity, channel))

            # 更新 prev_root
            prev_root = root

        return notes

    def _find_common_tone(self, prev_root: int, curr_root: int, chord_tones: List[int]) -> int:
        """找两个和弦的共同音"""
        prev_intervals = [(n - prev_root) % 12 for n in chord_tones]
        curr_intervals = [(n - curr_root) % 12 for n in chord_tones]

        common = set(prev_intervals) & set(curr_intervals)
        if common:
            # 返回第一个共同音
            interval = list(common)[0]
            return chord_tones[curr_intervals.index(interval)]
        return None
