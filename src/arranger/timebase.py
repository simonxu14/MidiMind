"""
Timebase utilities - 统一的时间基准计算

提供 MIDI 小节/拍子相关的精确计算
"""

from typing import Tuple


def measure_len(ticks_per_beat: int, ts: Tuple[int, int]) -> int:
    """
    计算每小节的 tick 数

    公式: ticks_per_beat * numerator * (4 / denominator)

    Args:
        ticks_per_beat: TPB (ticks per beat), 通常是 480
        ts: 时间签名 (numerator, denominator), 例如 (4, 4) 或 (3, 8)

    Returns:
        每小节的 tick 数

    Examples:
        4/4: 480 * 4 * (4/4) = 1920
        3/4: 480 * 3 * (4/4) = 1440
        6/8: 480 * 6 * (4/8) = 1440
        2/2: 480 * 2 * (4/2) = 1920
    """
    n, d = ts
    return int(round(ticks_per_beat * n * (4.0 / d)))


def ticks_per_measure(ticks_per_beat: int, time_signature: Tuple[int, int]) -> int:
    """measure_len 的别名，更语义化的名称"""
    return measure_len(ticks_per_beat, time_signature)


def beat_to_tick(beat: float, ticks_per_beat: int) -> int:
    """
    将拍数转换为 tick

    Args:
        beat: 拍数 (可以是小数)
        ticks_per_beat: TPB

    Returns:
        对应的 tick 数
    """
    return int(round(beat * ticks_per_beat))


def tick_to_beat(tick: int, ticks_per_beat: int) -> float:
    """
    将 tick 转换为拍数

    Args:
        tick: tick 数
        ticks_per_beat: TPB

    Returns:
        对应的拍数
    """
    return tick / ticks_per_beat


def measure_of_tick(tick: int, ticks_per_beat: int, time_signature: Tuple[int, int]) -> int:
    """
    获取指定 tick 的小节索引 (从 0 开始)

    Args:
        tick: tick 位置
        ticks_per_beat: TPB
        time_signature: 时间签名

    Returns:
        小节索引 (0-based)
    """
    ml = measure_len(ticks_per_beat, time_signature)
    return tick // ml


def tick_in_measure(tick: int, ticks_per_beat: int, time_signature: Tuple[int, int]) -> int:
    """
    获取 tick 在小节内的偏移 (ticks)

    Args:
        tick: tick 位置
        ticks_per_beat: TPB
        time_signature: 时间签名

    Returns:
        小节内的 tick 偏移
    """
    ml = measure_len(ticks_per_beat, time_signature)
    return tick % ml


def beat_in_measure(tick: int, ticks_per_beat: int, time_signature: Tuple[int, int]) -> float:
    """
    获取 tick 在小节内的偏移 (拍)

    Args:
        tick: tick 位置
        ticks_per_beat: TPB
        time_signature: 时间签名

    Returns:
        小节内的拍偏移
    """
    offset = tick_in_measure(tick, ticks_per_beat, time_signature)
    return offset / ticks_per_beat
