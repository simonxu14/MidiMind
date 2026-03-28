"""
Piano: Dense Accompaniment 模板

密集钢琴伴奏模板 - 产生丰富、专业的钢琴伴奏织体
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class DenseAccompanimentTemplate(BaseTemplate):
    """
    密集钢琴伴奏模板

    适用于：钢琴
    适用于角色：accompaniment

    生成丰富多样的钢琴伴奏织体：
    - 阿尔贝蒂低音 (Alberti bass)
    - 分解和弦 (arpeggios)
    - 柱式和弦 (blocked chords)
    - 混合模式

    根据音乐风格和和弦进行动态调整
    """

    name = "dense_accompaniment"
    description = "密集钢琴伴奏"
    applicable_instruments = ["piano"]
    applicable_roles = ["accompaniment"]

    default_params = {
        "density": 0.85,  # 适中密度 - 85%
        "velocity_base": 50,
        "velocity_range": 20,
        "register": "full",  # full = C2-C6 (5 octaves)
        "style": "modern",  # modern, classical, ballad
        "voicing": "spread",  # close, open, spread
        "include_octaves": True,
        "left_hand_piano": True,  # 是否使用左手钢琴模式
        "alberti_octave_repeat": True,  # Alberti bass 八度重复
        "bass_octave_depth": 2,  # 低音扩展八度层数
    }

    REGISTER_RANGES = {
        "low": (36, 60),      # C2 - B3
        "middle": (48, 72),   # C3 - B4
        "high": (60, 84),     # C4 - C6
        "full": (36, 96),     # C2 - C7 (5 octaves, matching AnyGen)
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成密集钢琴伴奏

        产生丰富的钢琴织体，包括：
        - 阿尔贝蒂低音模式
        - 琶音模式
        - 节奏和弦
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        voicing = p.get("voicing", "spread")
        include_octaves = p.get("include_octaves", True)

        # 强制使用 modern 风格以获得最高密度
        # ballad 风格密度较低，modern 才是高密度伴奏
        style = "modern"
        tempo = p.get("tempo", getattr(context, 'tempo', 120))

        # 从 params 获取高级参数
        bass_depth = p.get("bass_octave_depth", 2)
        alberti_octave_repeat = p.get("alberti_octave_repeat", True)

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat
        eighth_note = ticks_per_beat // 2
        sixteenth_note = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 1  # Piano channel

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["middle"])

        # 预处理：获取所有小节的根音列表
        sorted_measures = sorted(context.chord_per_measure.items())

        prev_root = getattr(context, 'prev_chord_root', None)

        for measure_idx, chord_info in sorted_measures:
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth
            seventh = getattr(chord_info, 'seventh', None)

            measure_start = measure_idx * measure_len

            # 构建和弦音
            chord_tones = [root, third, fifth]
            if seventh is not None:
                chord_tones.append(seventh)

            # 根据风格选择主要模式
            if style == "ballad":
                patterns = self._ballad_patterns(measure_start, quarter_note, eighth_note, sixteenth_note, chord_tones, pitch_min, pitch_max, velocity_base, velocity_range, channel, density)
            elif style == "dance":
                patterns = self._dance_patterns(measure_start, quarter_note, eighth_note, chord_tones, pitch_min, pitch_max, velocity_base, velocity_range, channel, density)
            else:  # general, upbeat, modern
                patterns = self._modern_patterns(measure_start, quarter_note, eighth_note, sixteenth_note, chord_tones, pitch_min, pitch_max, velocity_base, velocity_range, channel, density, voicing, include_octaves, bass_depth, alberti_octave_repeat)

            notes.extend(patterns)
            prev_root = root

        return notes

    def _ballad_patterns(
        self,
        measure_start: int,
        quarter_note: int,
        eighth_note: int,
        sixteenth_note: int,
        chord_tones: List[int],
        pitch_min: int,
        pitch_max: int,
        velocity_base: int,
        velocity_range: int,
        channel: int,
        density: float
    ) -> List[NoteEvent]:
        """民谣风格：轻柔的分解和弦"""
        notes = []
        patterns = [
            (0, quarter_note * 1.5),
            (quarter_note * 2, quarter_note * 1.5),
        ]

        for i, (pos, duration) in enumerate(patterns):
            if random.random() > density:
                continue

            tick = measure_start + pos

            for j, pitch in enumerate(chord_tones):
                # 调整到音区
                p = pitch
                while p < pitch_min:
                    p += 12
                while p > pitch_max:
                    p -= 12

                # 错开的时值
                delay = j * eighth_note // 2
                vel = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                vel = max(30, min(70, vel))

                notes.append((tick + delay, tick + delay + int(duration * 0.8), p, vel, channel))

        return notes

    def _dance_patterns(
        self,
        measure_start: int,
        quarter_note: int,
        eighth_note: int,
        chord_tones: List[int],
        pitch_min: int,
        pitch_max: int,
        velocity_base: int,
        velocity_range: int,
        channel: int,
        density: float
    ) -> List[NoteEvent]:
        """舞曲风格：强劲的节奏型"""
        notes = []
        # 每拍都有和弦
        positions = [
            (0, 0),
            (eighth_note, 0),
            (quarter_note, 0),
            (quarter_note + eighth_note, 0),
            (quarter_note * 2, 0),
            (quarter_note * 2 + eighth_note, 0),
            (quarter_note * 3, 0),
        ]

        for i, (pos, offset) in enumerate(positions):
            if random.random() > density:
                continue

            tick = measure_start + pos

            # 柱式和弦
            for j, pitch in enumerate(chord_tones):
                p = pitch
                while p < pitch_min:
                    p += 12
                while p > pitch_max:
                    p -= 12

                vel = velocity_base + (velocity_range // 2 if i % 2 == 0 else -velocity_range // 4)
                vel = max(35, min(80, vel))

                duration = int(eighth_note * 0.7)
                notes.append((tick, tick + duration, p, vel, channel))

        return notes

    def _modern_patterns(
        self,
        measure_start: int,
        quarter_note: int,
        eighth_note: int,
        sixteenth_note: int,
        chord_tones: List[int],
        pitch_min: int,
        pitch_max: int,
        velocity_base: int,
        velocity_range: int,
        channel: int,
        density: float,
        voicing: str,
        include_octaves: bool,
        bass_depth: int,
        alberti_octave_repeat: bool
    ) -> List[NoteEvent]:
        """
        现代风格：最大化密度的钢琴伴奏

        策略：
        1. 16分音符阿尔贝蒂低音模式 - 每个位置都演奏（density控制）
        2. 低音区：每拍多个八度层的根音
        3. 中音区：每拍后半拍的和弦音
        4. 高音区：持续的和弦音点缀
        5. 增强八度展开 - 最大化音符数量
        """
        notes = []

        # 阿尔贝蒂低音模式
        alberti_order = [0, 2, 1, 2]  # root, fifth, third, fifth

        # ===== 1. 主阿尔贝蒂低音（16分音符）- 核心节奏 =====
        for i in range(16):
            if random.random() > density:
                continue

            tick = measure_start + i * sixteenth_note
            tone_idx = alberti_order[i % 4]
            if tone_idx < len(chord_tones):
                pitch = chord_tones[tone_idx]

                # 八度安排：根音和五音在高音区，三音在中音区
                if voicing == "spread":
                    if i % 4 == 0:  # 根音位置 - 高八度
                        pitch += 12
                    elif i % 4 == 2:  # 三音位置 - 保持或稍高
                        pitch += 6

                # 音区调整
                while pitch < pitch_min:
                    pitch += 12
                while pitch > pitch_max:
                    pitch -= 12

                vel = velocity_base + random.randint(-velocity_range // 3, velocity_range // 3)
                vel = max(40, min(80, vel))
                duration = int(sixteenth_note * 0.9)
                notes.append((tick, tick + duration, pitch, vel, channel))

        # ===== 2. 低音扩展（使用 bass_depth 参数）- 增强低音密度 =====
        if include_octaves:
            for depth in range(bass_depth):
                bass_pitch = chord_tones[0] - 12 * (depth + 1)
                while bass_pitch > pitch_max:
                    bass_pitch -= 12
                while bass_pitch < pitch_min:
                    bass_pitch += 12

                # 每拍（1和3拍）加低音，保持合理密度
                for beat in [0, 2]:  # 只在第1和第3拍
                    tick = measure_start + beat * quarter_note
                    vel = velocity_base - 3 - (depth * 3)
                    vel = max(35, min(70, vel))
                    duration = int(quarter_note * 0.9)
                    notes.append((tick, tick + duration, bass_pitch, vel, channel))

        # ===== 3. 和弦音高八度和弦（使用 alberti_octave_repeat） =====
        if alberti_octave_repeat:
            # 高八度和弦 - 每小节只在第1拍和第3拍添加
            for j, pitch in enumerate(chord_tones[:3]):
                p = pitch + 24
                while p < pitch_min:
                    p += 12
                while p > pitch_max:
                    p -= 12

                tick = measure_start
                vel = velocity_base - 5
                duration = int(quarter_note * 2)
                notes.append((tick, tick + duration, p, vel, channel))

        # ===== 4. 高音点缀（可选）- 减少密度 =====
        # 移除了高音点缀以保持合理密度

        return notes
