"""
Auto-fixer 模块

自动修复编曲中的软约束问题：
1. 平行五八度
2. 声部交叉
3. 音域超限
4. 过大跳跃
"""

from __future__ import annotations

from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

from .plan_schema import NoteEvent


# ============ 乐器音域表 ============

INSTRUMENT_RANGES = {
    "violin": (55, 96),
    "viola": (48, 81),
    "cello": (36, 72),
    "double_bass": (28, 52),
    "harp": (23, 103),
    "flute": (60, 96),
    "oboe": (58, 89),
    "clarinet": (50, 99),
    "bassoon": (34, 64),
    "horn": (40, 65),
    "french_horn": (40, 65),
    "trumpet": (52, 84),
    "trombone": (40, 72),
    "tuba": (27, 53),
    "piano": (21, 108),
    "timpani": (45, 53),
}


@dataclass
class VoiceInfo:
    """声部信息"""
    pitch: int
    tick: int
    channel: int


@dataclass
class VoiceLine:
    """声部线"""
    channel: int
    notes: List[VoiceInfo]


class AutoFixer:
    """
    自动修复器

    在 Validator 检测到软约束问题后，尝试自动修复
    """

    def __init__(self):
        self.fixes_applied: List[str] = []

    def fix_all(
        self,
        notes: List[NoteEvent],
        instrument_ranges: Optional[Dict[str, Tuple[int, int]]] = None,
        skip_channels: Optional[List[int]] = None
    ) -> List[NoteEvent]:
        """
        修复所有检测到的问题

        Args:
            notes: 音符事件列表
            instrument_ranges: 乐器音域字典
            skip_channels: 跳过声部修复的 channel 列表（如 percussion channel 9）

        Returns:
            修复后的音符列表
        """
        self.fixes_applied = []

        if instrument_ranges is None:
            instrument_ranges = INSTRUMENT_RANGES

        # 1. 修复音域问题
        notes = self.fix_out_of_range(notes, instrument_ranges)

        # 2. 修复过大跳跃
        notes = self.fix_octave_jumps(notes)

        # 3. 修复声部交叉（跳过 percussion channels）
        notes = self.fix_voice_crossing(notes, skip_channels=skip_channels)

        # 4. 修复平行五八度
        notes = self.fix_parallel_fifths(notes)

        return notes

    def fix_out_of_range(
        self,
        notes: List[NoteEvent],
        instrument_ranges: Optional[Dict[str, Tuple[int, int]]] = None
    ) -> List[NoteEvent]:
        """
        修复超音域问题

        将超出范围的音高移到最近的范围内。
        注意：如果没有提供 instrument_ranges，则使用钢琴范围。
        在 OrchestrateExecutor 中应该传入基于 channel 的乐器音域。
        """
        result = []

        # 默认使用钢琴范围（向后兼容）
        if instrument_ranges is None:
            instrument_ranges = INSTRUMENT_RANGES

        for start, end, pitch, velocity, channel in notes:
            # 尝试通过 channel 查找对应乐器的音域
            # P4-Fix: channel_ranges 使用 int key，但 instrument_ranges 用 str key
            # 优先尝试 int，再尝试 str，最后 fallback 到钢琴范围
            if channel in instrument_ranges:
                range_min, range_max = instrument_ranges[channel]
            elif str(channel) in instrument_ranges:
                range_min, range_max = instrument_ranges[str(channel)]
            else:
                range_min, range_max = (21, 108)

            fixed_pitch = pitch

            if pitch < range_min:
                # 低于最低音：往上移八度
                while fixed_pitch < range_min:
                    fixed_pitch += 12
                if fixed_pitch != pitch:
                    self.fixes_applied.append(
                        f"Fixed pitch {pitch} -> {fixed_pitch} (ch {channel} below range {range_min}-{range_max})"
                    )
            elif pitch > range_max:
                # 高于最高音：往下移八度
                while fixed_pitch > range_max:
                    fixed_pitch -= 12
                if fixed_pitch != pitch:
                    self.fixes_applied.append(
                        f"Fixed pitch {pitch} -> {fixed_pitch} (ch {channel} above range {range_min}-{range_max})"
                    )

            result.append((start, end, fixed_pitch, velocity, channel))

        return result

    def fix_octave_jumps(
        self,
        notes: List[NoteEvent],
        threshold: int = 19
    ) -> List[NoteEvent]:
        """
        修复过大跳跃

        将超过阈值的跳跃改为级进
        注意：阈值为 19 semitones（小三度+八度），允许普通八度跳跃存在
        """
        result = []

        for i, (start, end, pitch, velocity, channel) in enumerate(notes):
            if i == 0:
                result.append((start, end, pitch, velocity, channel))
                continue

            prev_pitch = result[-1][2]
            interval = pitch - prev_pitch

            if abs(interval) > threshold:
                # 大跳：尝试级进方向接近
                if interval > 0:
                    # 上行跳跃：先级进到前一音+threshold
                    new_pitch = prev_pitch + threshold
                else:
                    # 下行跳跃：先级进到前一音-threshold
                    new_pitch = prev_pitch - threshold

                # 限制在钢琴范围内
                new_pitch = max(21, min(108, new_pitch))

                if new_pitch != pitch:
                    self.fixes_applied.append(
                        f"Fixed octave jump {prev_pitch} -> {pitch} -> {new_pitch}"
                    )
                    result.append((start, end, new_pitch, velocity, channel))
                else:
                    result.append((start, end, pitch, velocity, channel))
            else:
                result.append((start, end, pitch, velocity, channel))

        return result

    def fix_voice_crossing(
        self,
        notes: List[NoteEvent],
        skip_channels: Optional[List[int]] = None
    ) -> List[NoteEvent]:
        """
        修复声部交叉

        当低声部高于高声部时，交换它们的音高

        P4-Fix: 排除打击乐 channel（9=GM percussion, 以及其他打击乐）不参与声部交叉修复
        """
        # P4-Fix: 默认跳过 GM percussion channel 9
        if skip_channels is None:
            skip_channels = [9]

        # 按 channel 分组，但跳过 percussion channels
        voices: Dict[int, List[VoiceInfo]] = {}

        for start, end, pitch, velocity, channel in notes:
            # P4-Fix: 跳过 percussion channels
            if channel in skip_channels:
                continue
            if channel not in voices:
                voices[channel] = []
            voices[channel].append(VoiceInfo(pitch=pitch, tick=start, channel=channel))

        # 检测并修复交叉
        channels = sorted(voices.keys())

        result = []
        for start, end, pitch, velocity, channel in notes:
            # P4-Fix: percussion channel 直接不过滤（保持原样）
            if channel in skip_channels:
                result.append((start, end, pitch, velocity, channel))
                continue

            # 检测是否与低声部交叉
            crossing_fixed = False
            for other_ch in channels:
                if other_ch >= channel:
                    # No more lower channels to check
                    break

                # 获取其他声部在此时刻的音高
                other_pitch = self._get_pitch_at_tick(voices[other_ch], start)
                if other_pitch is not None:
                    if pitch <= other_pitch:
                        # 与低声部交叉：提升音高
                        new_pitch = other_pitch + 2
                        self.fixes_applied.append(
                            f"Fixed voice crossing: channel {channel} pitch {pitch} -> {new_pitch}"
                        )
                        result.append((start, end, new_pitch, velocity, channel))
                        crossing_fixed = True
                        break

            if not crossing_fixed:
                # No crossing detected - append original note
                result.append((start, end, pitch, velocity, channel))

        return result

    def _get_pitch_at_tick(
        self,
        voice_notes: List[VoiceInfo],
        tick: int
    ) -> Optional[int]:
        """获取声部在指定时刻的音高"""
        for note in voice_notes:
            if note.tick == tick:
                return note.pitch
        return None

    def fix_parallel_fifths(
        self,
        notes: List[NoteEvent],
        window_ticks: int = 480
    ) -> List[NoteEvent]:
        """
        修复平行五八度

        检测两个声部同向进行形成五度或八度时，
        尝试替换其中一声部为经过音

        注意：这是一个简化实现，完整检测需要追踪每个声部
        """
        # 简化版本：按 channel 分组后检测
        voices: Dict[int, List[Tuple[int, int]]] = {}  # channel -> [(tick, pitch), ...]

        for start, end, pitch, velocity, channel in notes:
            if channel not in voices:
                voices[channel] = []
            voices[channel].append((start, pitch))

        # 按 channel 检测
        channels = sorted(voices.keys())
        result = list(notes)

        for i, ch1 in enumerate(channels):
            for ch2 in channels[i+1:]:
                notes1 = voices[ch1]
                notes2 = voices[ch2]

                # 检测连续的五八度
                for k in range(min(len(notes1), len(notes2)) - 1):
                    tick1, pitch1 = notes1[k]
                    tick1_next, pitch1_next = notes1[k+1]
                    tick2, pitch2 = notes2[k]
                    tick2_next, pitch2_next = notes2[k+1]

                    # 计算音程
                    interval1 = abs(pitch1_next - pitch1)
                    interval2 = abs(pitch2_next - pitch2)

                    # 检测是否是平行五度（7）或八度（12）
                    if tick1 == tick1_next == tick2 == tick2_next:
                        current_interval = abs(pitch1 - pitch2)
                        next_interval = abs(pitch1_next - pitch2_next)

                        if current_interval in [7, 12] and next_interval in [7, 12]:
                            # 平行五八度：尝试修改一声部
                            # 选择修改较高声部
                            if pitch1_next > pitch2_next:
                                # 修改通道1的下一个音
                                new_pitch = pitch2_next + 5  # 移到六度
                                new_pitch = max(21, min(108, new_pitch))

                                # 在 result 中找到并修改
                                for idx, (s, e, p, v, c) in enumerate(result):
                                    if s == tick1_next and c == ch1:
                                        result[idx] = (s, e, new_pitch, v, c)
                                        self.fixes_applied.append(
                                            f"Fixed parallel fifth/octave at tick {tick1}"
                                        )
                                        break
                            else:
                                # 修改通道2的下一个音
                                new_pitch = pitch1_next + 5
                                new_pitch = max(21, min(108, new_pitch))

                                for idx, (s, e, p, v, c) in enumerate(result):
                                    if s == tick1_next and c == ch2:
                                        result[idx] = (s, e, new_pitch, v, c)
                                        self.fixes_applied.append(
                                            f"Fixed parallel fifth/octave at tick {tick1}"
                                        )
                                        break

        return result

    # ============ AnyGen 风格护栏 (Guards) ============

    def apply_velocity_caps_by_mode(
        self,
        notes: List[NoteEvent],
        velocity_caps: Dict[str, int],
        instrument_for_channel: Optional[Dict[int, str]] = None
    ) -> List[NoteEvent]:
        """
        按模式力度上限调整音符力度

        Args:
            notes: 音符事件列表
            velocity_caps: 力度上限字典，如 {'piano': 58, 'viola': 62}
            instrument_for_channel: channel -> instrument_id 映射

        Returns:
            调整后的音符列表
        """
        if not velocity_caps:
            return notes

        result = []
        for start, end, pitch, velocity, channel in notes:
            # 查找该 channel 对应的力度上限
            cap = velocity_caps.get(str(channel), velocity_caps.get('default', 127))

            if velocity > cap:
                self.fixes_applied.append(
                    f"Velocity capped {velocity} -> {cap} (ch {channel})"
                )
                velocity = cap

            result.append((start, end, pitch, velocity, channel))

        return result

    def avoid_melody_onsets(
        self,
        notes: List[NoteEvent],
        melody_onsets: List[int],
        window_ticks: int = 120,
        reduce_ratio: float = 0.6,
        instrument_for_channel: Optional[Dict[int, str]] = None
    ) -> List[NoteEvent]:
        """
        避让旋律起音

        在旋律起音后的 window_ticks 窗口内，降低伴奏力度

        Args:
            notes: 音符事件列表
            melody_onsets: 旋律起音时间列表
            window_ticks: 避让窗口大小
            reduce_ratio: 力度折减比

        Returns:
            调整后的音符列表
        """
        # 构建 onset 集合便于查找
        onset_set = set(melody_onsets)

        result = []
        for start, end, pitch, velocity, channel in notes:
            # 检查是否在旋律 onset 附近
            is_near_onset = any(
                abs(start - onset) < window_ticks for onset in melody_onsets
            )

            if is_near_onset and velocity > 20:
                new_velocity = int(velocity * reduce_ratio)
                if new_velocity != velocity:
                    self.fixes_applied.append(
                        f"Onset avoidance: velocity {velocity} -> {new_velocity} (ch {channel}, near onset)"
                    )
                velocity = new_velocity

            result.append((start, end, pitch, velocity, channel))

        return result

    def apply_register_separation(
        self,
        notes: List[NoteEvent],
        melody_notes: List[NoteEvent],
        min_semitones: int = 5,
        chord_per_measure: Optional[Dict[int, Tuple[int, int, int]]] = None,
        instrument_for_channel: Optional[Dict[int, str]] = None
    ) -> List[NoteEvent]:
        """
        保持伴奏与旋律的音区分离

        P2-1 完整策略：
        1) 先 octave shift（上下八度）
        2) 不行就 swap chord tone（替换为 root/third/fifth）
        3) 再不行 skip event

        Args:
            notes: 伴奏音符列表
            melody_notes: 旋律音符列表
            min_semitones: 最小音程距离
            chord_per_measure: 可选的每小节和弦信息 {measure_idx: (root, third, fifth)}

        Returns:
            调整后的音符列表
        """
        # 构建每个 tick 的旋律音高
        melody_at_tick: Dict[int, int] = {}
        for start, end, pitch, velocity, channel in melody_notes:
            for t in range(start, end):
                melody_at_tick[t] = pitch

        # 默认 ticks_per_beat
        ticks_per_beat = 480

        def check_collision(p: int, t_start: int, t_end: int) -> bool:
            """检查给定音高在时间范围内是否与旋律冲突"""
            for t in range(t_start, min(t_end, t_start + 100)):
                if t in melody_at_tick:
                    melody_pitch = melody_at_tick[t]
                    distance = abs(p - melody_pitch) % 12
                    if distance < min_semitones and distance != 0:
                        return True
            return False

        result = []
        for start, end, pitch, velocity, channel in notes:
            # 检查该音符时间段是否与旋律重叠
            if not check_collision(pitch, start, end):
                # 没有冲突，保留原音符
                result.append((start, end, pitch, velocity, channel))
                continue

            # 策略 1: Octave shift
            new_pitch_up = pitch + 12
            new_pitch_down = pitch - 12

            if not check_collision(new_pitch_up, start, end):
                result.append((start, end, new_pitch_up, velocity, channel))
                self.fixes_applied.append(
                    f"Register separation: pitch {pitch} -> {new_pitch_up} (octave up, ch {channel})"
                )
                continue
            elif not check_collision(new_pitch_down, start, end):
                result.append((start, end, new_pitch_down, velocity, channel))
                self.fixes_applied.append(
                    f"Register separation: pitch {pitch} -> {new_pitch_down} (octave down, ch {channel})"
                )
                continue

            # 策略 2: Swap chord tone
            if chord_per_measure:
                measure_idx = start // (ticks_per_beat * 4)  # 假设 4/4
                chord = chord_per_measure.get(measure_idx)
                if chord:
                    root, third, fifth = chord
                    # 尝试用 chord tones 替换
                    for alt_pitch in [root, third, fifth, root + 12, third + 12, fifth + 12]:
                        if alt_pitch != pitch and not check_collision(alt_pitch, start, end):
                            result.append((start, end, alt_pitch, velocity, channel))
                            self.fixes_applied.append(
                                f"Register separation: pitch {pitch} -> {alt_pitch} (chord tone, ch {channel})"
                            )
                            break
                    else:
                        # 所有 chord tones 都不行，跳过
                        self.fixes_applied.append(
                            f"Register separation: skipped pitch {pitch} at tick {start} (ch {channel})"
                        )
                    continue

            # 策略 3: Skip event（没有 chord_per_measure 或 chord tones 也不行）
            self.fixes_applied.append(
                f"Register separation: skipped pitch {pitch} at tick {start} (ch {channel})"
            )

        return result

    def get_fixes_applied(self) -> List[str]:
        """获取已应用的修复列表"""
        return self.fixes_applied


# ============ 便捷函数 ============

def auto_fix(
    notes: List[NoteEvent],
    instrument_ranges: Optional[Dict[str, Tuple[int, int]]] = None
) -> Tuple[List[NoteEvent], List[str]]:
    """
    便捷函数：自动修复所有问题

    Args:
        notes: 音符事件列表
        instrument_ranges: 乐器音域字典

    Returns:
        (修复后的音符, 已应用的修复列表)
    """
    fixer = AutoFixer()
    fixed_notes = fixer.fix_all(notes, instrument_ranges)
    return fixed_notes, fixer.get_fixes_applied()
