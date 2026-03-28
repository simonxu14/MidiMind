"""
和声分析模块

提供和弦分析、段落模式检测等功能
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .plan_schema import ChordInfo, SectionMode, NoteEvent


# ============ 和弦分析 ============

def choose_triadish(pitches: List[int]) -> Optional[Tuple[int, int, int]]:
    """
    从音高集合推导 triad-ish 和弦骨架

    算法：
    1. 去重并排序
    2. 最低音当根音
    3. 找与根音距离最接近 3/4 度的音作为三音
    4. 找与根音距离最接近 7 度的音作为五音

    Args:
        pitches: 小节内的音高列表

    Returns:
        (root, third, fifth) 或 None
    """
    if not pitches:
        return None

    # 去重并排序
    unique_pitches = sorted(set(pitches))
    root = unique_pitches[0]  # 最低音当根音

    # 找三音（距离根音 3 或 4 度）
    third = None
    min_third_dist = float('inf')
    for p in unique_pitches:
        if p == root:
            continue
        # 转换为 pitch class (mod 12)
        interval = (p - root) % 12
        # 目标：3度(m3)或4度(M3)
        dist = min(abs(interval - 3), abs(interval - 4))
        if dist < min_third_dist:
            min_third_dist = dist
            third = p

    # 如果找不到合适的三音，用默认
    if third is None or third == root:
        third = root + 4  # 默认大三度

    # 找五音（距离根音 7 度）
    fifth = None
    min_fifth_dist = float('inf')
    for p in unique_pitches:
        if p == root or p == third:
            continue
        interval = (p - root) % 12
        dist = abs(interval - 7)
        if dist < min_fifth_dist:
            min_fifth_dist = dist
            fifth = p

    # 如果找不到，用默认
    if fifth is None or fifth == root:
        fifth = root + 7  # 默认纯五度

    return (root, third, fifth)


def analyze_chord_quality(root: int, third: int, fifth: int) -> str:
    """
    分析和弦性质（大三/小三分）

    Args:
        root, third, fifth: 和弦音

    Returns:
        'major', 'minor', 或 'unknown'
    """
    third_interval = (third - root) % 12
    if third_interval == 4:
        return 'major'
    elif third_interval == 3:
        return 'minor'
    return 'unknown'


def build_chord_info(root: int, third: int, fifth: int) -> ChordInfo:
    """
    构建 ChordInfo 对象

    Args:
        root, third, fifth: 和弦音

    Returns:
        ChordInfo 对象
    """
    quality = analyze_chord_quality(root, third, fifth)
    return ChordInfo(
        root=root,
        third=third,
        fifth=fifth,
        quality=quality
    )


# ============ 段落模式检测 ============

@dataclass
class SectionFeatures:
    """段落特征"""
    note_count: int  # 旋律音符数量
    avg_velocity: float  # 平均力度
    avg_pitch: float  # 平均音高


def estimate_section_modes(
    melody_notes: List[NoteEvent],
    measures: int,
    measure_len: int,
    section_block: int = 8,
    D_av: int = 85,
    B_nn: int = 80,
    C_ap: int = 72
) -> Dict[int, str]:
    """
    按段落检测模式 (A/B/C/D/CODA)

    每 N 小节（默认8小节）统计旋律特征，判定模式：
    - D (高潮): avg_velocity >= D_av
    - B (流动): note_density > B_nn
    - C (明亮): avg_pitch > C_ap
    - A (透明): 其他情况
    - CODA: 无旋律音符

    Args:
        melody_notes: 旋律音符事件
        measures: 总小节数
        measure_len: 每小节 tick 数
        section_block: 段落块大小（默认8小节）
        D_av: 高潮力度阈值
        B_nn: 流动密度阈值
        C_ap: 明亮音高阈值

    Returns:
        Dict[小节索引, 模式]
    """
    # 按小节统计旋律特征
    section_modes: Dict[int, str] = {}

    # 统计每个 8 小节块的特征
    blocks = (measures + section_block - 1) // section_block

    for block_idx in range(blocks):
        block_start_measure = block_idx * section_block
        block_end_measure = min(block_start_measure + section_block, measures)

        # 收集该块的旋律音符
        block_notes: List[NoteEvent] = []
        for note in melody_notes:
            start_tick = note[0]
            measure_idx = start_tick // measure_len
            if block_start_measure <= measure_idx < block_end_measure:
                block_notes.append(note)

        # 计算特征
        if not block_notes:
            mode = "CODA"
        else:
            velocities = [n[3] for n in block_notes if n[3] > 0]
            pitches = [n[2] for n in block_notes]

            avg_vel = sum(velocities) / len(velocities) if velocities else 0
            avg_pitch = sum(pitches) / len(pitches) if pitches else 0
            note_count = len(block_notes)

            # 判定模式
            if avg_vel >= D_av:
                mode = "D"
            elif note_count > B_nn:
                mode = "B"
            elif avg_pitch > C_ap:
                mode = "C"
            else:
                mode = "A"

        # 避免连续同模式（加强变化感）
        if block_idx > 0:
            prev_mode = section_modes.get(block_start_measure - section_block)
            if prev_mode == mode == "B":
                mode = "C"

        # 赋值给块内每个小节
        for m in range(block_start_measure, block_end_measure):
            section_modes[m] = mode

    return section_modes


def get_velocity_cap_for_mode(
    mode: str,
    instrument_id: str,
    caps_by_mode: Dict[str, Dict[str, int]]
) -> int:
    """
    获取指定模式下某乐器的力度上限

    Args:
        mode: 段落模式 (A/B/C/D)
        instrument_id: 声部 ID
        caps_by_mode: 按模式的力度上限配置

    Returns:
        力度上限值
    """
    mode_caps = caps_by_mode.get(mode, {})
    return mode_caps.get(instrument_id, 60)  # 默认 60
