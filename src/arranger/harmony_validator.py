"""
Harmony Validator - 和声验证模块

负责检测和声问题：
1. 平行五八度
2. 隐伏五八度
3. 声部交叉
4. 声部超越
"""

from __future__ import annotations

from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

from .plan_schema import CheckResult


@dataclass
class VoiceState:
    """声部状态"""
    pitch: int
    tick: int


@dataclass
class HarmonyViolation:
    """和声违规"""
    type: str
    tick: int
    channel1: int
    channel2: int
    interval: int
    description: str


class HarmonyValidator:
    """
    和声验证器

    检测编曲中的和声问题
    """

    # 禁止的平行进行
    PARALLEL_INTERVALS = {7: "fifth", 12: "octave"}

    def __init__(self):
        self.violations: List[HarmonyViolation] = []

    def validate(
        self,
        notes: List[Tuple[int, int, int, int, int]]
    ) -> CheckResult:
        """
        验证和声

        Args:
            notes: 音符事件列表 (start_tick, end_tick, pitch, velocity, channel)

        Returns:
            CheckResult
        """
        self.violations = []

        # 按 channel 分组
        voice_lines = self._extract_voice_lines(notes)

        if len(voice_lines) < 2:
            # 少于两个声部，无法检测和声问题
            return CheckResult(passed=True, message="Not enough voices for harmony check")

        # 1. 检测平行五八度
        self._check_parallel_motion(voice_lines)

        # 2. 检测隐伏五八度
        self._check_hidden_motion(voice_lines)

        # 3. 检测声部交叉
        self._check_voice_crossing(voice_lines)

        # 4. 检测声部超越
        self._check_voice_overlap(voice_lines)

        if self.violations:
            messages = [v.description for v in self.violations[:5]]
            return CheckResult(
                passed=False,
                message="; ".join(messages)
            )

        return CheckResult(passed=True, message="Harmony check passed")

    def _extract_voice_lines(
        self,
        notes: List[Tuple[int, int, int, int, int]]
    ) -> Dict[int, List[Tuple[int, int, int]]]:
        """
        提取声部线（带结束时间）

        Returns:
            {channel: [(start_tick, end_tick, pitch), ...]}
        """
        voice_lines: Dict[int, List[Tuple[int, int, int]]] = {}

        for start, end, pitch, velocity, channel in notes:
            if channel not in voice_lines:
                voice_lines[channel] = []
            voice_lines[channel].append((start, end, pitch))

        # 按 start_tick 排序
        for ch in voice_lines:
            voice_lines[ch].sort(key=lambda x: x[0])

        return voice_lines

    def _check_parallel_motion(
        self,
        voice_lines: Dict[int, List[Tuple[int, int, int]]]
    ) -> None:
        """
        检测平行五八度

        两个声部同向进行形成五度或八度
        支持检查重叠音符（延留音）的情况
        """
        channels = sorted(voice_lines.keys())

        for i, ch1 in enumerate(channels):
            for ch2 in channels[i+1:]:
                line1 = voice_lines[ch1]
                line2 = voice_lines[ch2]

                # 双指针检查所有相邻音符对组合
                idx1 = 0
                idx2 = 0

                while idx1 < len(line1) - 1 and idx2 < len(line2) - 1:
                    start1, end1, pitch1 = line1[idx1]
                    start1_next, end1_next, pitch1_next = line1[idx1 + 1]
                    start2, end2, pitch2 = line2[idx2]
                    start2_next, end2_next, pitch2_next = line2[idx2 + 1]

                    # 计算重叠区间
                    overlap_start = max(start1, start2)
                    overlap_end = min(end1, end2)

                    # 如果两个音符在时间区间重叠
                    if overlap_end > overlap_start:
                        interval = abs(pitch1 - pitch2)

                        if interval in self.PARALLEL_INTERVALS:
                            # 检查下一个音符是否也形成平行
                            next_overlap_start = max(start1_next, start2_next)
                            next_overlap_end = min(end1_next, end2_next)

                            if next_overlap_end > next_overlap_start:
                                next_interval = abs(pitch1_next - pitch2_next)
                                if next_interval in self.PARALLEL_INTERVALS:
                                    # 同向进行检测
                                    direction1 = pitch1_next - pitch1
                                    direction2 = pitch2_next - pitch2

                                    if direction1 > 0 and direction2 > 0 or direction1 < 0 and direction2 < 0:
                                        interval_name = self.PARALLEL_INTERVALS.get(
                                            interval, f"interval_{interval}"
                                        )
                                        self.violations.append(HarmonyViolation(
                                            type="parallel_motion",
                                            tick=overlap_start,
                                            channel1=ch1,
                                            channel2=ch2,
                                            interval=interval,
                                            description=f"Parallel {interval_name} between channel {ch1} and {ch2} at tick {overlap_start}"
                                        ))

                    # 移动指针
                    if end1 < end2:
                        idx1 += 1
                    elif end2 < end1:
                        idx2 += 1
                    else:
                        idx1 += 1
                        idx2 += 1

    def _check_hidden_motion(
        self,
        voice_lines: Dict[int, List[Tuple[int, int, int]]]
    ) -> None:
        """
        检测隐伏五八度

        两个声部同向进入五度或八度
        支持检查重叠音符的情况
        """
        channels = sorted(voice_lines.keys())

        for i, ch1 in enumerate(channels):
            for ch2 in channels[i+1:]:
                line1 = voice_lines[ch1]
                line2 = voice_lines[ch2]

                # 双指针检查
                idx1 = 0
                idx2 = 0

                while idx1 < len(line1) - 1 and idx2 < len(line2) - 1:
                    start1, end1, pitch1 = line1[idx1]
                    start1_next, end1_next, pitch1_next = line1[idx1 + 1]
                    start2, end2, pitch2 = line2[idx2]
                    start2_next, end2_next, pitch2_next = line2[idx2 + 1]

                    # 计算重叠区间
                    overlap_start = max(start1, start2)
                    overlap_end = min(end1, end2)

                    if overlap_end > overlap_start:
                        interval = abs(pitch1 - pitch2)
                        next_interval = abs(pitch1_next - pitch2_next)

                        # 隐伏五八度：一个声部保持，一个声部跳进到五八度
                        if interval not in self.PARALLEL_INTERVALS and next_interval in self.PARALLEL_INTERVALS:
                            direction1 = pitch1_next - pitch1
                            direction2 = pitch2_next - pitch2

                            if direction1 > 0 and direction2 > 0 or direction1 < 0 and direction2 < 0:
                                voice1_motion = abs(pitch1_next - pitch1)
                                voice2_motion = abs(pitch2_next - pitch2)

                                if voice1_motion > 7 or voice2_motion > 7:
                                    interval_name = self.PARALLEL_INTERVALS.get(
                                        next_interval, f"interval_{next_interval}"
                                    )
                                    self.violations.append(HarmonyViolation(
                                        type="hidden_motion",
                                        tick=overlap_start,
                                        channel1=ch1,
                                        channel2=ch2,
                                        interval=next_interval,
                                        description=f"Hidden {interval_name} entering at tick {overlap_start}"
                                    ))

                    # 移动指针
                    if end1 < end2:
                        idx1 += 1
                    elif end2 < end1:
                        idx2 += 1
                    else:
                        idx1 += 1
                        idx2 += 1

    def _check_voice_crossing(
        self,
        voice_lines: Dict[int, List[Tuple[int, int, int]]]
    ) -> None:
        """
        检测声部交叉

        检查任意时刻是否低声部高于高声部
        支持双指针检查重叠音符
        """
        channels = sorted(voice_lines.keys())

        for i, ch1 in enumerate(channels):
            for ch2 in channels[i+1:]:
                line1 = voice_lines[ch1]  # 较高声部
                line2 = voice_lines[ch2]  # 较低声部

                # 双指针检查
                idx1 = 0
                idx2 = 0

                while idx1 < len(line1) and idx2 < len(line2):
                    start1, end1, pitch1 = line1[idx1]
                    start2, end2, pitch2 = line2[idx2]

                    # 计算重叠区间
                    overlap_start = max(start1, start2)
                    overlap_end = min(end1, end2)

                    if overlap_end > overlap_start and pitch1 < pitch2:
                        # 声部交叉：高声部的音高低于低声部
                        self.violations.append(HarmonyViolation(
                            type="voice_crossing",
                            tick=overlap_start,
                            channel1=ch1,
                            channel2=ch2,
                            interval=0,
                            description=f"Voice crossing: channel {ch1} ({pitch1}) below channel {ch2} ({pitch2})"
                        ))

                    # 移动指针
                    if end1 < end2:
                        idx1 += 1
                    elif end2 < end1:
                        idx2 += 1
                    else:
                        idx1 += 1
                        idx2 += 1

    def _check_voice_overlap(
        self,
        voice_lines: Dict[int, List[Tuple[int, int, int]]]
    ) -> None:
        """
        检测声部超越

        同一声部跳跃超过八度
        """
        channels = sorted(voice_lines.keys())

        for ch in channels:
            line = voice_lines[ch]

            for k in range(len(line) - 1):
                start1, end1, pitch1 = line[k]
                start2, end2, pitch2 = line[k + 1]

                # 检查是否有时间重叠
                if end1 > start2:
                    interval = abs(pitch2 - pitch1)
                    if interval > 12:  # 超过八度
                        self.violations.append(HarmonyViolation(
                            type="voice_overlap",
                            tick=start2,
                            channel1=ch,
                            channel2=ch,
                            interval=interval,
                            description=f"Voice overlap in channel {ch}: jump of {interval} semitones at tick {start2}"
                        ))

    def get_violations(self) -> List[HarmonyViolation]:
        """获取所有违规"""
        return self.violations


# ============ 便捷函数 ============

def validate_harmony(
    notes: List[Tuple[int, int, int, int, int]]
) -> CheckResult:
    """
    便捷函数：验证和声

    Args:
        notes: 音符事件列表

    Returns:
        CheckResult
    """
    validator = HarmonyValidator()
    return validator.validate(notes)
