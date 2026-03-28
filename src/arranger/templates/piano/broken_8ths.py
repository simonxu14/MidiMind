"""
Piano: Broken 8ths 模板

分解八分音符伴奏型：低-高-中-高 交替模式
"""

from __future__ import annotations

import random
from typing import List, Dict, Any

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext


class Broken8thsTemplate(BaseTemplate):
    """
    分解八分音符伴奏模板

    适用于：钢琴
    适用于角色：accompaniment, inner_voice

    参数：
    - density: 密度 (0.0-1.0)，越大越密
    - velocity_base: 基础力度
    - velocity_range: 力度变化范围
    - register: 音区 (low/middle/high)
    - syncopation: 切分程度 (0.0-1.0)
    """

    name = "broken_8ths"
    description = "分解八分音符伴奏型"
    applicable_instruments = ["piano", "harp"]
    applicable_roles = ["accompaniment", "inner_voice"]
    per_measure_select = True  # 模板内部自行按小节迭代生成

    default_params = {
        "density": 0.5,
        "velocity_base": 55,
        "velocity_range": 10,
        "register": "middle",
        "syncopation": 0.0,
    }

    # 各音区的和弦音范围
    REGISTER_RANGES = {
        "low": (48, 60),      # C3-C4
        "middle": (55, 67),   # G3-G4
        "high": (60, 72),     # C4-C5
    }

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成分解八分音符

        模式：根音 - 五音 - 三音 - 五音（在和弦内）

        Per-measure mode support:
        - A mode: 标准密度，保持清晰
        - B mode: 增加切分感
        - C mode: 增加密度，升高音区
        - D mode: 最大密度，强劲力度
        """
        # 合并默认参数
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        syncopation = p["syncopation"]

        # 获取音区范围
        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["middle"])

        # 计算小节长度
        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        eight_note = ticks_per_beat // 2

        notes: List[NoteEvent] = []
        channel = 0  # 默认 channel，后续由 caller 设置

        # Per-measure mode-driven adjustments
        section_modes = getattr(context, 'section_modes', {})

        # 遍历每个小节
        for measure_idx, chord_info in context.chord_per_measure.items():
            # P1: 获取该小节的 mode，驱动参数调整
            mode = section_modes.get(measure_idx, 'A')

            # 根据 mode 调整密度和力度（使用局部变量避免跨小节漂移）
            mode_density = density
            mode_velocity = velocity_base
            mode_syncopation = syncopation
            local_pitch_min = pitch_min
            local_pitch_max = pitch_max

            if mode == "B":
                # B mode: 增加切分感
                mode_syncopation = max(mode_syncopation, 0.3)
                mode_density = min(density * 1.1, 1.0)
            elif mode == "C":
                # C mode: 增加密度，升高音区
                mode_density = min(density * 1.3, 1.0)
                mode_velocity = min(velocity_base + 5, 70)
            elif mode == "D":
                # D mode: 最大密度，强劲力度
                mode_density = min(density * 1.5, 1.0)
                mode_velocity = min(velocity_base + 10, 80)
                # D mode 可以升高一个八度（使用局部变量）
                local_pitch_min = min(pitch_min + 12, 72)
                local_pitch_max = min(pitch_max + 12, 84)

            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            # 生成分解八分音符
            # 位置模式：根音(0) - 五音(1) - 三音(2) - 五音(3)
            positions = [root, fifth, third, fifth]

            measure_start = measure_idx * measure_len

            for beat in range(4):  # 4个八分音符
                pos_in_measure = beat * eight_note

                # 根据密度决定是否跳过
                if beat > 0 and mode_density < 1.0:
                    if random.random() > mode_density:
                        continue

                # 应用切分（改变重音位置）
                tick = measure_start + pos_in_measure
                if mode_syncopation > 0 and beat == 1:
                    # 切分：把弱拍音提前到前一拍的尾部
                    tick = measure_start + (beat - 1) * eight_note + eight_note - 1

                # 选择音高（在和弦音范围内）
                pitch = positions[beat % len(positions)]

                # 调整到目标音区（使用局部变量）
                while pitch < local_pitch_min:
                    pitch += 12
                while pitch > local_pitch_max:
                    pitch -= 12

                # 计算力度（强拍更强）
                if beat == 0:
                    velocity = mode_velocity + velocity_range // 2
                elif beat == 2:
                    velocity = mode_velocity + velocity_range // 4
                else:
                    velocity = mode_velocity - velocity_range // 4

                velocity = max(20, min(127, velocity))

                # 计算时长（八分音符或稍短）
                duration = int(eight_note * 0.9)

                notes.append((tick, tick + duration, pitch, velocity, channel))

        return notes
