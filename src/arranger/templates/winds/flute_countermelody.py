"""
Winds: Flute Countermelody 模板

长笛对位旋律模板 - 高音区的对位旋律

P2-2 修复：
- 只在旋律空隙 (rest >= 1 beat) 出现
- 使用 triad-relative motifs (3-5-1-5 等形状)

P3 修复：
- 使用 meter_grid API 支持任意拍号（不再硬编码 range(4)）
- 对于复合拍号（6/8 等）使用 pulse 网格
"""

from __future__ import annotations

import random
from typing import List, Dict, Any, Set

from ..base import BaseTemplate
from ...plan_schema import NoteEvent, ArrangementContext
from ...timebase import meter_grid, beats_per_measure


class FluteCountermelodyTemplate(BaseTemplate):
    """
    长笛对位旋律模板

    适用于：长笛
    适用于角色：counter_melody

    P2-2: 只在旋律空隙插入，使用 triad-relative motifs
    """

    name = "flute_countermelody"
    description = "长笛对位旋律"
    applicable_instruments = ["flute"]
    applicable_roles = ["counter_melody", "inner_voice"]

    default_params = {
        "density": 0.6,
        "velocity_base": 60,
        "velocity_range": 12,
        "register": "high",
        "min_rest_beats": 0.5,  # P2-2: 最少 rest 时长（拍），降低到0.5以适应连续旋律
    }

    REGISTER_RANGES = {
        "low": (60, 74),
        "middle": (67, 79),
        "high": (72, 84),
    }

    # P2-2: Triad-relative motifs (相对于根音的音程模式)
    MOTIFS = [
        [3, 5, 8, 5],      # 3-5-1-5 (小调进行)
        [4, 7, 12, 7],     # 4-5-8-5 (大调上行)
        [0, 4, 7, 4],      # 1-3-5-3
        [0, 3, 7, 3],      # 1-b3-5-b3
        [5, 8, 12, 8],     # 4-5-8-5 (转位)
        [7, 12, 16, 12],   # 5-8-12-8
    ]

    def _get_melody_gaps(self, context: ArrangementContext, min_rest_beats: int) -> Set[int]:
        """
        计算旋律的空隙位置 (tick)

        P2-2: 返回可以插入音符的 tick 位置集合

        P3: 使用 meter_grid API 支持任意拍号

        Args:
            context: 编排上下文
            min_rest_beats: 最少 rest 时长（拍）

        Returns:
            可以插入motif的 tick 位置集合
        """
        ticks_per_beat = context.ticks_per_beat
        measure_len = context.measure_len
        min_rest_ticks = int(min_rest_beats * ticks_per_beat)

        # 构建旋律占用时间段
        melody_occupied: Set[int] = set()
        for start, end, pitch, velocity, channel in context.melody_notes:
            for t in range(start, end):
                melody_occupied.add(t)

        # 找出所有满足条件的空隙起始位置
        valid_positions: Set[int] = set()

        # 获取总时间范围
        max_tick = max((end for _, end, _, _, _ in context.melody_notes), default=0)
        total_measures = max(1, max_tick // measure_len + 1)

        # P3: 使用 meter_grid 获取实际的 beat 网格（而不是硬编码 range(4)）
        # 对于 6/8，使用 pulse 网格（每小节 3 个位置）；对于 4/4，使用 quarter 网格
        n = context.time_signature_num
        d = context.time_signature_den
        if n % 3 == 0 and d == 8:
            grid_kind = "pulse"  # 6/8, 9/8, 12/8 使用 pulse 网格
        else:
            grid_kind = "quarter"  # 其他拍号使用 quarter 网格

        for measure_idx in range(total_measures):
            measure_start = measure_idx * measure_len
            grid_positions = meter_grid(
                ticks_per_beat,
                (n, d),
                kind=grid_kind,
                measure_start=measure_start,
                measure_count=1,
                clip_to_measure=True
            )

            for tick in grid_positions:
                # 检查从 tick 开始的 min_rest_beats 是否都是空的
                is_gap = True
                for rest_tick in range(tick, tick + min_rest_ticks):
                    if rest_tick in melody_occupied:
                        is_gap = False
                        break

                if is_gap:
                    valid_positions.add(tick)

        return valid_positions

    def generate(
        self,
        context: ArrangementContext,
        params: Dict[str, Any]
    ) -> List[NoteEvent]:
        """
        生成长笛对位旋律

        P2-2: 只在旋律空隙插入 triad-relative motifs
        """
        p = {**self.default_params, **params}
        density = p["density"]
        velocity_base = p["velocity_base"]
        velocity_range = p["velocity_range"]
        register = p["register"]
        min_rest_beats = p.get("min_rest_beats", 1)

        pitch_min, pitch_max = self.REGISTER_RANGES.get(register, self.REGISTER_RANGES["high"])

        measure_len = context.measure_len
        ticks_per_beat = context.ticks_per_beat
        eighth_note = ticks_per_beat // 2

        # P2-2: 计算旋律空隙位置
        valid_positions = self._get_melody_gaps(context, min_rest_beats)

        notes: List[NoteEvent] = []
        channel = 5  # Flute channel

        for measure_idx, chord_info in context.chord_per_measure.items():
            root = chord_info.root
            third = chord_info.third
            fifth = chord_info.fifth

            measure_start = measure_idx * measure_len

            # P3: 使用 meter_grid 获取实际的网格位置（而不是硬编码 range(4)）
            n = context.time_signature_num
            d = context.time_signature_den
            if n % 3 == 0 and d == 8:
                grid_kind = "pulse"
            else:
                grid_kind = "quarter"

            grid_positions = meter_grid(
                ticks_per_beat,
                (n, d),
                kind=grid_kind,
                measure_start=measure_start,
                measure_count=1,
                clip_to_measure=True
            )

            # P2-2: 遍历每个潜在插入位置
            for tick in grid_positions:
                # P2-2: 只在空隙位置插入
                if tick not in valid_positions:
                    continue

                if random.random() > density:
                    continue

                # P2-2: 选择一个 triad-relative motif
                motif = random.choice(self.MOTIFS)
                motif_pitches = [(root + interval) for interval in motif]

                # 调整到目标音区并创建 motif 音符
                current_tick = tick
                velocity = velocity_base + random.randint(-velocity_range // 2, velocity_range // 2)
                velocity = max(30, min(80, velocity))

                for i, interval in enumerate(motif):
                    pitch = motif_pitches[i]

                    # 调整到目标音区
                    while pitch < pitch_min:
                        pitch += 12
                    while pitch > pitch_max:
                        pitch -= 12

                    # 每个 motif 音符的时值 (八分音符)
                    duration = int(eighth_note * 0.8)

                    notes.append((current_tick, current_tick + duration, pitch, velocity, channel))
                    current_tick += eighth_note

        return notes
