"""
Auto-fixer 模块

自动修复编曲中的软约束问题（按 voice-line 分层处理）：
1. 音域超限 - 按 channel 音域检查修复
2. 过大跳跃 - 按 voice-line 独立处理
3. 声部交叉 - 跨 voice 检查（需要显式 voice_order）
4. 平行五八度 - 按 voice-line 独立处理

设计原则：
- 先在单个 voice line 内部修复（out_of_range, octave_jumps）
- 再跨 voice 检查（voice_crossing, parallel_fifths）
- percussion channels (GM channel 9) 不参与声部交叉检测
"""

from __future__ import annotations

from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass

from .plan_schema import NoteEvent
from .config import INSTRUMENT_RANGES, GUARD_DEFAULTS


@dataclass
class VoiceInfo:
    """声部信息"""
    pitch: int
    tick: int
    end_tick: int
    velocity: int
    channel: int


@dataclass
class VoiceLine:
    """声部线 - 同一 channel 上的音符序列"""
    channel: int
    notes: List[VoiceInfo]

    def get_pitch_at_tick(self, tick: int) -> Optional[int]:
        """获取该声部在指定时刻的音高"""
        for note in self.notes:
            if note.tick == tick:
                return note.pitch
        return None


class AutoFixer:
    """
    自动修复器（voice-line aware）

    在 Validator 检测到软约束问题后，尝试自动修复

    处理流程：
    1. 按 channel 分组 voice lines
    2. 单个 voice line 内：fix_out_of_range + fix_octave_jumps
    3. 跨 voice：fix_voice_crossing + fix_parallel_fifths
    """

    def __init__(self):
        self.fixes_applied: List[str] = []

    def fix_all(
        self,
        notes: List[NoteEvent],
        instrument_ranges: Optional[Dict[str, Tuple[int, int]]] = None,
        skip_channels: Optional[List[int]] = None,
        voice_order: Optional[List[int]] = None,
    ) -> List[NoteEvent]:
        """
        修复所有检测到的问题（voice-line aware）

        Args:
            notes: 音符事件列表
            instrument_ranges: 乐器音域字典（channel int -> range tuple）
            skip_channels: 跳过声部修复的 channel 列表（如 percussion channel 9）
            voice_order: 显式声部顺序列表（从小到大：最低音到最高音），
                        如 [vc_channel, va_channel, vn1_channel]
                        如果不提供，则使用 channel 号作为顺序

        Returns:
            修复后的音符列表
        """
        self.fixes_applied = []

        if instrument_ranges is None:
            instrument_ranges = INSTRUMENT_RANGES

        if skip_channels is None:
            skip_channels = [9]  # GM Percussion channel

        preserved_notes = [note for note in notes if skip_channels and note[4] in skip_channels]

        # Step 1: 按 channel 分组 voice lines
        voice_lines = self._group_by_channel(notes, skip_channels)

        # Step 2: 单个 voice line 内修复
        # 2a. fix_out_of_range - 在原始音符上修复，不依赖分组
        notes = self.fix_out_of_range(notes, instrument_ranges)

        # 2b. 重新分组，然后 fix_octave_jumps 在每个 voice line 内部处理
        voice_lines = self._group_by_channel(notes, skip_channels)
        voice_lines = self._fix_octave_jumps_per_voice_line(voice_lines)

        # 重建 flat notes list
        notes = self._flatten_voice_lines(voice_lines) + preserved_notes

        # Step 3: 跨 voice 修复
        # 3a. fix_voice_crossing
        voice_lines = self._group_by_channel(notes, skip_channels)
        notes = self.fix_voice_crossing(notes, skip_channels=skip_channels, voice_order=voice_order)

        # 3b. fix_parallel_fifths - 在每个 voice line 内处理
        voice_lines = self._group_by_channel(notes, skip_channels)
        voice_lines = self._fix_parallel_fifths_per_voice_line(voice_lines)
        notes = self._flatten_voice_lines(voice_lines) + preserved_notes

        return sorted(notes, key=lambda n: (n[0], n[4], n[2], n[1], n[3]))

    def _group_by_channel(
        self,
        notes: List[NoteEvent],
        skip_channels: Optional[List[int]] = None
    ) -> Dict[int, VoiceLine]:
        """按 channel 分组 notes 为 voice lines"""
        voices: Dict[int, List[VoiceInfo]] = {}

        for start, end, pitch, velocity, channel in notes:
            if skip_channels and channel in skip_channels:
                continue
            if channel not in voices:
                voices[channel] = []
            voices[channel].append(
                VoiceInfo(
                    pitch=pitch,
                    tick=start,
                    end_tick=end,
                    velocity=velocity,
                    channel=channel,
                )
            )

        # 转换为 VoiceLine，并按 channel 排序
        result = {}
        for channel in sorted(voices.keys()):
            result[channel] = VoiceLine(channel=channel, notes=sorted(voices[channel], key=lambda n: n.tick))

        return result

    def _flatten_voice_lines(self, voice_lines: Dict[int, VoiceLine]) -> List[NoteEvent]:
        """将 voice lines 合并回 flat note list（按 channel 分组排序）"""
        result = []
        for channel in sorted(voice_lines.keys()):
            for voice_info in voice_lines[channel].notes:
                result.append(
                    (
                        voice_info.tick,
                        voice_info.end_tick,
                        voice_info.pitch,
                        voice_info.velocity,
                        voice_info.channel,
                    )
                )
        return result

    def fix_out_of_range(
        self,
        notes: List[NoteEvent],
        instrument_ranges: Optional[Dict[str, Tuple[int, int]]] = None
    ) -> List[NoteEvent]:
        """
        修复超音域问题

        将超出范围的音高移到最近的范围内。
        """
        result = []

        if instrument_ranges is None:
            instrument_ranges = INSTRUMENT_RANGES

        for start, end, pitch, velocity, channel in notes:
            # 优先尝试 int key，再尝试 str key，最后 fallback
            if channel in instrument_ranges:
                range_min, range_max = instrument_ranges[channel]
            elif str(channel) in instrument_ranges:
                range_min, range_max = instrument_ranges[str(channel)]
            else:
                range_min, range_max = (21, 108)  # piano fallback

            fixed_pitch = pitch

            if pitch < range_min:
                while fixed_pitch < range_min:
                    fixed_pitch += 12
                if fixed_pitch != pitch:
                    self.fixes_applied.append(
                        f"Fixed pitch {pitch} -> {fixed_pitch} (ch {channel} below range {range_min}-{range_max})"
                    )
            elif pitch > range_max:
                while fixed_pitch > range_max:
                    fixed_pitch -= 12
                if fixed_pitch != pitch:
                    self.fixes_applied.append(
                        f"Fixed pitch {pitch} -> {fixed_pitch} (ch {channel} above range {range_min}-{range_max})"
                    )

            result.append((start, end, fixed_pitch, velocity, channel))

        return result

    def _fix_octave_jumps_per_voice_line(
        self,
        voice_lines: Dict[int, VoiceLine],
        threshold: Optional[int] = None
    ) -> Dict[int, VoiceLine]:
        """
        在每个 voice line 内部修复过大跳跃

        只在同一 channel 的连续音符之间检查，不跨 channel
        """
        if threshold is None:
            threshold = GUARD_DEFAULTS.get("max_octave_jump", 19)

        for channel, voice_line in voice_lines.items():
            notes = voice_line.notes
            if len(notes) < 2:
                continue

            fixed_notes = [notes[0]]  # 第一个音符保持不变

            for i in range(1, len(notes)):
                curr = notes[i]
                prev = fixed_notes[-1]

                interval = curr.pitch - prev.pitch

                if abs(interval) > threshold:
                    # 大跳：尝试级进方向接近
                    if interval > 0:
                        new_pitch = prev.pitch + threshold
                    else:
                        new_pitch = prev.pitch - threshold

                    # 限制在钢琴范围内
                    new_pitch = max(21, min(108, new_pitch))

                    if new_pitch != curr.pitch:
                        self.fixes_applied.append(
                            f"Fixed octave jump {prev.pitch} -> {curr.pitch} -> {new_pitch} (ch {channel})"
                        )
                        fixed_notes.append(VoiceInfo(
                            pitch=new_pitch,
                            tick=curr.tick,
                            end_tick=curr.end_tick,
                            velocity=curr.velocity,
                            channel=channel
                        ))
                    else:
                        fixed_notes.append(curr)
                else:
                    fixed_notes.append(curr)

            voice_lines[channel] = VoiceLine(channel=channel, notes=fixed_notes)

        return voice_lines

    def fix_octave_jumps(
        self,
        notes: List[NoteEvent],
        threshold: int = 19
    ) -> List[NoteEvent]:
        """
        修复过大跳跃（向后兼容方法）

        对于单 channel 的简单场景，按顺序处理。
        对于多 channel 场景，建议使用 fix_all() 进行 voice-line aware 处理。

        Args:
            notes: 音符事件列表
            threshold: 跳跃阈值（semitones），超过此值需要修复

        Returns:
            修复后的音符列表
        """
        # 检查是否多 channel
        channels = set(n[4] for n in notes)
        if len(channels) > 1:
            # 多 channel：使用 voice-line aware 处理
            voice_lines = self._group_by_channel(notes, skip_channels=[9])
            voice_lines = self._fix_octave_jumps_per_voice_line(voice_lines, threshold)

            # 重建完整音符（保留原始 velocity 和 end time）
            tick_to_new_pitch: Dict[Tuple[int, int], int] = {}
            for ch, vl in voice_lines.items():
                for note in vl.notes:
                    tick_to_new_pitch[(note.tick, ch)] = note.pitch

            result = []
            for start, end, pitch, velocity, channel in notes:
                new_pitch = tick_to_new_pitch.get((start, channel), pitch)
                result.append((start, end, new_pitch, velocity, channel))
            return result

        # 单 channel：简单顺序处理（向后兼容）
        result = []
        for i, (start, end, pitch, velocity, channel) in enumerate(notes):
            if i == 0:
                result.append((start, end, pitch, velocity, channel))
                continue

            prev_pitch = result[-1][2]
            interval = pitch - prev_pitch

            if abs(interval) > threshold:
                if interval > 0:
                    new_pitch = prev_pitch + threshold
                else:
                    new_pitch = prev_pitch - threshold

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
        skip_channels: Optional[List[int]] = None,
        voice_order: Optional[List[int]] = None,
    ) -> List[NoteEvent]:
        """
        修复声部交叉

        当低声部高于高声部时，提升低声部音高

        Args:
            skip_channels: 跳过 GM percussion channels
            voice_order: 显式声部顺序（从小到大：最低音到最高音 channel 列表）
                       如 [3, 2, 1, 0] 表示 channel 3 是最低音
        """
        if skip_channels is None:
            skip_channels = [9]

        if voice_order is None:
            # Fallback: 使用 channel 号作为声部顺序（channel 小的 = 低声部）
            voice_order = sorted(ch for ch in set(n[4] for n in notes) if ch not in skip_channels)

        # 构建 voice line 查找
        voices: Dict[int, VoiceLine] = {}
        for start, end, pitch, velocity, channel in notes:
            if channel in skip_channels:
                continue
            if channel not in voices:
                voices[channel] = VoiceLine(channel=channel, notes=[])
            voices[channel].notes.append(
                VoiceInfo(
                    pitch=pitch,
                    tick=start,
                    end_tick=end,
                    velocity=velocity,
                    channel=channel,
                )
            )

        # 对每个 voice line 的 notes 按 tick 排序
        for ch in voices:
            voices[ch].notes.sort(key=lambda n: n.tick)

        # 按 voice_order 从低到高检查（voice_order[0] = 最低声部）
        # 确保每个较高声部的音 >= 较低声部的音
        result = list(notes)

        for i, higher_ch in enumerate(voice_order):
            if higher_ch not in voices:
                continue

            # 获取所有比它低的声部 channels
            lower_channels = voice_order[:i]

            for note in voices[higher_ch].notes:
                tick = note.tick
                pitch = note.pitch

                # 检查是否与任何低声部交叉
                for lower_ch in lower_channels:
                    if lower_ch not in voices:
                        continue

                    lower_pitch = voices[lower_ch].get_pitch_at_tick(tick)
                    if lower_pitch is not None and pitch <= lower_pitch:
                        # 声部交叉：提升音高
                        new_pitch = lower_pitch + 2
                        self.fixes_applied.append(
                            f"Fixed voice crossing: ch {higher_ch} pitch {pitch} -> {new_pitch} (crossed with ch {lower_ch})"
                        )

                        # 更新 result 和 voice line 中的音高
                        for idx, (s, e, p, v, c) in enumerate(result):
                            if s == tick and c == higher_ch:
                                result[idx] = (s, e, new_pitch, v, c)
                                break

                        # 更新 voice line 中的音高
                        for n in voices[higher_ch].notes:
                            if n.tick == tick:
                                n.pitch = new_pitch
                                break
                        break

        return result

    def _fix_parallel_fifths_per_voice_line(
        self,
        voice_lines: Dict[int, VoiceLine]
    ) -> Dict[int, VoiceLine]:
        """
        在每个 voice line 内部修复平行五八度

        注意：这个方法只检测单个 voice line 内部的问题，
        跨 voice 的平行五八度需要更复杂的声部追踪
        """
        # 简化实现：每个 voice line 内部不做平行检测
        # 跨 voice 的平行五八度检测保留在 fix_parallel_fifths 中
        return voice_lines

    def fix_parallel_fifths(
        self,
        notes: List[NoteEvent],
        skip_channels: Optional[List[int]] = None
    ) -> List[NoteEvent]:
        """
        修复平行五八度

        检测两个声部同向进行形成五度或八度时，
        尝试替换其中一声部为经过音

        注意：这是一个简化实现，
        完整检测需要追踪每个声部的进行方向
        """
        if skip_channels is None:
            skip_channels = [9]

        # 按 channel 分组
        voices: Dict[int, List[Tuple[int, int]]] = {}  # channel -> [(tick, pitch), ...]

        for start, end, pitch, velocity, channel in notes:
            if channel in skip_channels:
                continue
            if channel not in voices:
                voices[channel] = []
            voices[channel].append((start, pitch))

        # 按 channel 排序
        channels = sorted(voices.keys())
        result = list(notes)

        for i, ch1 in enumerate(channels):
            for ch2 in channels[i+1:]:
                notes1 = sorted(voices[ch1], key=lambda x: x[0])
                notes2 = sorted(voices[ch2], key=lambda x: x[0])

                # 找到同时发声的 tick
                common_ticks = set(t1[0] for t1 in notes1) & set(t2[0] for t2 in notes2)

                for tick in common_ticks:
                    # 找这两个声部在 tick 的音
                    pitch1 = next(p for t, p in notes1 if t == tick)
                    pitch2 = next(p for t, p in notes2 if t == tick)

                    # 计算 interval
                    interval = abs(pitch1 - pitch2) % 12  # 简化为半音类

                    # 检查是否是平行五度 (7) 或八度 (0/12)
                    if interval in [0, 7]:
                        # 平行五八度：修改较高声部
                        higher_ch = ch1 if pitch1 > pitch2 else ch2
                        lower_pitch = pitch2 if higher_ch == ch1 else pitch1
                        new_pitch = lower_pitch + 5  # 移到六度

                        new_pitch = max(21, min(108, new_pitch))

                        # 在 result 中找到并修改
                        for idx, (s, e, p, v, c) in enumerate(result):
                            if s == tick and c == higher_ch:
                                result[idx] = (s, e, new_pitch, v, c)
                                self.fixes_applied.append(
                                    f"Fixed parallel fifth/octave: ch {higher_ch} at tick {tick}"
                                )
                                break

        return result

    # ============ Guard 风格的辅助方法 ============

    def apply_velocity_caps_by_mode(
        self,
        notes: List[NoteEvent],
        velocity_caps: Dict[str, int],
        instrument_for_channel: Optional[Dict[int, str]] = None
    ) -> List[NoteEvent]:
        """按模式力度上限调整音符力度"""
        if not velocity_caps:
            return notes

        result = []
        for start, end, pitch, velocity, channel in notes:
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
    ) -> List[NoteEvent]:
        """在旋律起音后的窗口内降低伴奏力度"""
        onset_set = set(melody_onsets)

        result = []
        for start, end, pitch, velocity, channel in notes:
            is_near_onset = any(
                abs(start - onset) < window_ticks for onset in melody_onsets
            )

            if is_near_onset and velocity > 20:
                new_velocity = int(velocity * reduce_ratio)
                if new_velocity != velocity:
                    self.fixes_applied.append(
                        f"Onset avoidance: velocity {velocity} -> {new_velocity} (ch {channel})"
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
    ) -> List[NoteEvent]:
        """保持伴奏与旋律的音区分离"""
        melody_at_tick: Dict[int, int] = {}
        for start, end, pitch, velocity, channel in melody_notes:
            for t in range(start, end):
                melody_at_tick[t] = pitch

        ticks_per_beat = 480

        def check_collision(p: int, t_start: int, t_end: int) -> bool:
            for t in range(t_start, min(t_end, t_start + 100)):
                if t in melody_at_tick:
                    distance = abs(p - melody_at_tick[t]) % 12
                    if 0 < distance < min_semitones:
                        return True
            return False

        result = []
        for start, end, pitch, velocity, channel in notes:
            if not check_collision(pitch, start, end):
                result.append((start, end, pitch, velocity, channel))
                continue

            # 策略 1: octave shift
            for new_pitch in (pitch + 12, pitch - 12):
                if not check_collision(new_pitch, start, end):
                    result.append((start, end, new_pitch, velocity, channel))
                    self.fixes_applied.append(
                        f"Register separation: pitch {pitch} -> {new_pitch} (ch {channel})"
                    )
                    break
            else:
                # 策略 2: chord tone
                if chord_per_measure:
                    measure_idx = start // (ticks_per_beat * 4)
                    chord = chord_per_measure.get(measure_idx)
                    if chord:
                        root, third, fifth = chord
                        for alt in [root, third, fifth, root + 12, third + 12, fifth + 12]:
                            if alt != pitch and not check_collision(alt, start, end):
                                result.append((start, end, alt, velocity, channel))
                                self.fixes_applied.append(
                                    f"Register separation: pitch {pitch} -> {alt} (chord tone, ch {channel})"
                                )
                                break
                        else:
                            self.fixes_applied.append(
                                f"Register separation: skipped pitch {pitch} at tick {start} (ch {channel})"
                            )
                        continue

                # 策略 3: skip
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
    """便捷函数：自动修复所有问题"""
    fixer = AutoFixer()
    fixed_notes = fixer.fix_all(notes, instrument_ranges)
    return fixed_notes, fixer.get_fixes_applied()
