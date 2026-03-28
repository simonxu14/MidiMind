"""
Strings: Adaptive Strings 模板

自适应弦乐内声部：根据风格和速度动态调整的内声部
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class AdaptiveStringsTemplate(BaseTemplate):
    """
    自适应弦乐内声部模板

    适用于：小提琴、中提琴
    适用于角色：inner_voice, accompaniment

    根据风格和速度调整演奏法：
    - ballad: 柔和的连奏
    - general: 平衡的断奏
    - upbeat: 活跃的十六分音符
    - dance: 节奏感强的跳弓
    """

    name = "adaptive_strings"
    description = "自适应弦乐内声部"
    applicable_instruments = ["violin", "viola"]
    applicable_roles = ["inner_voice", "accompaniment"]

    default_params = {
        "density": 0.6,
        "velocity_base": 52,
        "velocity_range": 8,
        "register": "middle",
        "articulation": "detached",  # detached, legato, marcato
        "motion": "contrary",  # parallel, contrary, oblique
    }

    REGISTER_RANGES = {
        "violin": {
            "low": (55, 70),
            "middle": (60, 80),
            "high": (67, 96),
        },
        "viola": {
            "low": (48, 62),
            "middle": (53, 69),
            "high": (58, 74),
        }
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成自适应弦乐内声部

        根据风格选择最佳演奏模式
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        articulation = p["articulation"]
        motion = p["motion"]

        # 获取风格和速度
        style = getattr(context, 'style', 'general')
        tempo = getattr(context, 'tempo', 120)

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        quarter_note = ticks_per_beat
        eighth_note = ticks_per_beat // 2
        sixteenth_note = ticks_per_beat // 4

        notes: List[NoteEvent] = []
        channel = 1  # 默认 violin channel

        # 获取上一小节根音（用于声部连接）
        prev_root = getattr(context, 'prev_chord_root', None)

        # 根据风格选择节奏模式
        if style == "ballad":
            # Ballad: 柔和的连奏，每小节2-3个音
            positions = [(0, quarter_note), (quarter_note * 2, quarter_note * 3)]
            note_duration = int(quarter_note * 1.2)
            local_density = density * 0.4
        elif style == "dance":
            # Dance: 活跃节奏，每拍都弹
            positions = [(i * eighth_note, 0) for i in range(8)]
            note_duration = int(eighth_note * 0.5)
            local_density = density
        elif style == "upbeat":
            # Upbeat: 快速的十六分音符
            positions = []
            for beat in range(4):
                for sixteenth in range(2):
                    positions.append((beat * quarter_note + sixteenth * sixteenth_note, 0))
            note_duration = int(sixteenth_note * 0.6)
            local_density = density * 0.8
        else:
            # General: 平衡的八分音符
            positions = [(0, 0), (eighth_note, 0), (quarter_note, 0),
                        (quarter_note + eighth_note, 0), (quarter_note * 2, 0),
                        (quarter_note * 2 + eighth_note, 0), (quarter_note * 3, 0)]
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

            # 根据 motion 调整和弦排列
            if motion == "parallel":
                pass  # 和弦音顺序不变
            elif motion == "contrary":
                # 反向运动：一个声部向上时另一个向下
                if prev_root is not None:
                    if root < prev_root:
                        # 根音下行，三音上行扩展
                        chord_tones = [root, third + 12 if third + 12 <= 84 else third, fifth]
                    elif root > prev_root:
                        # 根音上行，三音下行扩展
                        chord_tones = [root, third - 12 if third - 12 >= 36 else third, fifth]
            elif motion == "oblique":
                # 斜向运动：保持共同音
                if prev_root is not None:
                    common = self._find_common_tone(prev_root, root, chord_tones)
                    if common:
                        # 共同音保持，其他音移动
                        pass

            # 选择音区范围
            instrument = "violin"  # 默认
            for inst in ["violin", "viola"]:
                p_instrument = p.get("instrument", "") or ""
                params_instrument = params.get("instrument", "") or ""
                if inst in p_instrument.lower() or inst in params_instrument.lower():
                    instrument = inst
                    break

            pitch_ranges = self.REGISTER_RANGES.get(instrument, self.REGISTER_RANGES["violin"])
            pitch_min, pitch_max = pitch_ranges.get(register, pitch_ranges["middle"])

            # 生成音符
            for i, (pos, offset) in enumerate(positions):
                if random.random() > local_density:
                    continue

                tick = measure_start + pos

                # 选择和弦音（循环使用，加入一些随机性）
                if articulation == "legato":
                    # 连奏时倾向于选择相邻音
                    pitch_idx = (i + random.randint(0, 2)) % len(chord_tones)
                else:
                    pitch_idx = i % len(chord_tones)

                pitch = chord_tones[pitch_idx]

                # 调整到目标音区
                while pitch < pitch_min:
                    pitch += 12
                while pitch > pitch_max:
                    pitch -= 12

                # 声部连接：保持共同音
                if prev_root is not None and i == 0:
                    common_tone = self._find_common_tone(prev_root, root, chord_tones)
                    if common_tone is not None:
                        pitch = common_tone

                # 计算力度
                if style == "dance" and i % 2 == 0:
                    velocity = velocity_base + velocity_range // 2
                elif articulation == "marcato":
                    velocity = velocity_base + velocity_range
                else:
                    velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)

                velocity = max(30, min(80, velocity))

                # 根据 articulation 调整时值
                if articulation == "detached":
                    actual_duration = note_duration
                elif articulation == "legato":
                    actual_duration = int(note_duration * 1.3)
                else:  # marcato
                    actual_duration = int(note_duration * 0.8)

                notes.append((tick, tick + actual_duration, pitch, velocity, channel))

            # 更新 prev_root
            prev_root = root

        return notes

    def _find_common_tone(self, prev_root: int, curr_root: int, chord_tones: List[int]) -> int:
        """
        找两个和弦的共同音（考虑八度等价）

        找出前一个小节和当前小节和弦中，音高级别相同（相差八度）的音。
        如果有多个可能，选择与 prev_root 音区最接近的那个。
        """
        # 计算前一个小节的音高级别集合（0-11）
        prev_pitch_classes = set()
        prev_notes_by_class: Dict[int, List[int]] = {}  # pitch_class -> list of pitches
        for n in chord_tones:
            pc = (n - prev_root) % 12
            prev_pitch_classes.add(pc)
            if pc not in prev_notes_by_class:
                prev_notes_by_class[pc] = []
            prev_notes_by_class[pc].append(n)

        # 计算当前小节的音高级别集合
        curr_pitch_classes = set()
        curr_notes_by_class: Dict[int, List[int]] = {}
        for n in chord_tones:
            pc = (n - curr_root) % 12
            curr_pitch_classes.add(pc)
            if pc not in curr_notes_by_class:
                curr_notes_by_class[pc] = []
            curr_notes_by_class[pc].append(n)

        # 找共同的音高级别
        common = prev_pitch_classes & curr_pitch_classes

        if not common:
            return None

        # 选择音区最接近的共同音
        best_pitch = None
        best_distance = float('inf')

        for pc in common:
            # 获取前一个小节该音高级别的所有音
            prev_pitches = prev_notes_by_class.get(pc, [])
            # 获取当前小节该音高级别的所有音
            curr_pitches = curr_notes_by_class.get(pc, [])

            for prev_p in prev_pitches:
                for curr_p in curr_pitches:
                    distance = abs(curr_p - prev_p)
                    if distance < best_distance:
                        best_distance = distance
                        best_pitch = curr_p

        return best_pitch
