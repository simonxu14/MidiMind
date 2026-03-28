"""
Strings: Adaptive Bass 模板

自适应低音模板：根据风格和速度动态调整的低音
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class AdaptiveBassTemplate(BaseTemplate):
    """
    自适应低音模板

    适用于：大提琴、低音提琴、巴松管
    适用于角色：bass

    根据风格和速度调整低音模式：
    - ballad: 简化的根音
    - general: 平衡的根音加五度
    - upbeat: 根音+八度的活跃低音
    - dance: 强劲的节奏低音
    """

    name = "adaptive_bass"
    description = "自适应低音"
    applicable_instruments = ["cello", "double_bass", "bassoon"]
    applicable_roles = ["bass"]

    default_params = {
        "velocity_base": 58,
        "velocity_range": 8,
        "register": "low",
        "add_octave": True,
        "add_fifth": False,
        "syncopation": 0.0,  # 0-1, 切分程度
        "anchor_tones": True,  # 是否保持根音锚定
    }

    REGISTER_RANGES = {
        "cello": (36, 55),      # C2-G3
        "double_bass": (28, 45), # E1-B2
        "bassoon": (34, 55),     # Bb1-G3
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成自适应低音

        根据风格选择最佳低音模式
        """
        p = {**self.default_params, **params}
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        add_octave = p["add_octave"]
        add_fifth = p["add_fifth"]
        syncopation = p["syncopation"]
        anchor_tones = p["anchor_tones"]

        # 获取风格和速度
        style = getattr(context, 'style', 'general')
        tempo = getattr(context, 'tempo', 120)

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat
        eighth_note = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 4  # Cello channel

        prev_root = getattr(context, 'prev_chord_root', None)

        # 根据风格选择低音模式
        if style == "ballad":
            # Ballad: 每小节一个根音，在后半拍
            positions = [(quarter_note * 2, quarter_note * 1.5)]
            note_duration = measure_len * 0.7
            local_velocity_base = velocity_base - 5
        elif style == "dance":
            # Dance: 每拍都弹，强劲节奏
            positions = [
                (0, 0),
                (eighth_note, 0),
                (quarter_note, 0),
                (quarter_note + eighth_note, 0),
                (quarter_note * 2, 0),
                (quarter_note * 2 + eighth_note, 0),
                (quarter_note * 3, 0),
            ]
            note_duration = eighth_note * 0.6
            local_velocity_base = velocity_base + 5
        elif style == "upbeat":
            # Upbeat: 活跃的八分音符，在后半拍有切分
            positions = [
                (0, 0),
                (eighth_note, 0),
                (quarter_note, 0),
                (quarter_note + eighth_note, 0),
                (quarter_note * 2, 0),
                (quarter_note * 2 + eighth_note, 0),
                (quarter_note * 3, 0),
            ]
            note_duration = eighth_note * 0.7
            local_velocity_base = velocity_base
            # 随机添加切分
            if syncopation > 0.3:
                positions = [(p[0] + eighth_note // 2, p[1]) if random.random() > 0.5 else p for p in positions]
        else:
            # General: 平衡模式，每拍后半拍
            positions = [
                (0, 0),
                (quarter_note, 0),
                (quarter_note * 2, 0),
                (quarter_note * 3, 0),
            ]
            note_duration = quarter_note * 0.6
            local_velocity_base = velocity_base

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            fifth = chord_info.fifth

            # 调整根音到低音区
            instrument = "cello"
            for inst in ["cello", "double_bass", "bassoon"]:
                instr_param = params.get("instrument", "") or ""
                if inst in instr_param.lower():
                    instrument = inst
                    break

            pitch_range = self.REGISTER_RANGES.get(instrument, self.REGISTER_RANGES["cello"])
            pitch_min, pitch_max = pitch_range

            bass_pitch = root
            while bass_pitch > pitch_max:
                bass_pitch -= 12
            while bass_pitch < pitch_min:
                bass_pitch += 12

            measure_start = measure_idx * measure_len

            for i, (pos, offset) in enumerate(positions):
                tick = measure_start + pos + int(offset * syncopation)

                # 声部连接：如果有共同音则保持
                if anchor_tones and prev_root is not None and i == 0:
                    if (root - prev_root) % 12 in [0, 7, 5]:  # 根音、五度、三度
                        # 保持前面的音
                        continue

                # 计算力度
                if style == "dance" and i % 2 == 0:
                    velocity = local_velocity_base + velocity_range // 2
                elif i == 0:
                    velocity = local_velocity_base  # 强拍
                else:
                    velocity = local_velocity_base - velocity_range // 3

                velocity = max(35, min(85, velocity))

                notes.append((tick, tick + int(note_duration), bass_pitch, velocity, channel))

                # 添加八度低音
                if add_octave:
                    octave_pitch = bass_pitch - 12
                    if octave_pitch >= pitch_min:
                        notes.append((
                            tick,
                            tick + int(note_duration),
                            octave_pitch,
                            velocity - 8,
                            channel
                        ))

                # 添加五度音
                if add_fifth and fifth:
                    fifth_pitch = fifth
                    while fifth_pitch > pitch_max:
                        fifth_pitch -= 12
                    if fifth_pitch >= pitch_min:
                        notes.append((
                            tick,
                            tick + int(note_duration * 0.8),
                            fifth_pitch,
                            velocity - 12,
                            channel
                        ))

            prev_root = root

        return notes
