"""
Timebase utilities - 统一的时间基准计算

提供 MIDI 小节/拍子相关的精确计算
"""

from typing import Tuple, List, Literal


def beats_per_measure(time_signature: Tuple[int, int]) -> float:
    """
    计算每小节的拍数（可以是浮点数）

    公式: numerator * (4 / denominator)

    Args:
        time_signature: (numerator, denominator), 例如 (4, 4) 或 (6, 8)

    Returns:
        每小节的拍数（浮点数）

    Examples:
        4/4: 4 * (4/4) = 4.0
        3/4: 3 * (4/4) = 3.0
        6/8: 6 * (4/8) = 3.0 (compound duple)
        9/8: 9 * (4/8) = 4.5 (compound triple)
        2/2: 2 * (4/2) = 4.0
    """
    n, d = time_signature
    return n * (4.0 / d)


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


def meter_grid(
    ticks_per_beat: int,
    time_signature: Tuple[int, int],
    kind: Literal["quarter", "eighth", "pulse"],
    measure_start: int = 0,
    measure_count: int = 1,
    clip_to_measure: bool = True
) -> List[int]:
    """
    生成分辨率对齐的网格位置列表

    Args:
        ticks_per_beat: TPB
        time_signature: (numerator, denominator)
        kind:
            - "quarter": quarter-note grid (beat divisions)
            - "eighth": eighth-note grid (beat/2 divisions)
            - "pulse": compound meter pulse (dotted-quarter for 6/8, 9/8, 12/8)
        measure_start: 起始小节的 tick 位置
        measure_count: 要生成的小节数
        clip_to_measure: 是否裁剪到小节边界内

    Returns:
        tick 位置列表（已排序，无重复）

    Examples:
        4/4 quarter grid: [0, 480, 960, 1440] per measure
        6/8 pulse grid: [0, 720, 1440] per measure (dotted-quarter = 3*eighth)
        3/4 quarter grid: [0, 480, 960] per measure
    """
    ml = measure_len(ticks_per_beat, time_signature)
    n, d = time_signature

    if kind == "quarter":
        # Quarter-note grid: one position per beat
        beat_ticks = ticks_per_beat
        positions_per_measure = int(round(n * (4.0 / d)))
    elif kind == "eighth":
        # Eighth-note grid: two positions per beat
        beat_ticks = ticks_per_beat // 2
        positions_per_measure = int(round(n * (8.0 / d)))
    elif kind == "pulse":
        # Compound meter pulse: dotted-quarter (3 eighth-notes)
        # For simple meter, this falls back to quarter
        if n % 3 == 0 and d == 8:
            # Compound meter (6/8, 9/8, 12/8): pulse = dotted-quarter
            beat_ticks = int(ticks_per_beat * 1.5)  # 3 * (tpb/2)
            positions_per_measure = int(round(n / 3))  # number of pulses
        else:
            # Simple meter fallback to quarter
            beat_ticks = ticks_per_beat
            positions_per_measure = int(round(n * (4.0 / d)))
    else:
        raise ValueError(f"Unknown grid kind: {kind}")

    result = []
    for m in range(measure_count):
        base = measure_start + m * ml
        for i in range(positions_per_measure):
            pos = base + i * beat_ticks
            if clip_to_measure and pos >= base + ml:
                break
            result.append(pos)

    return sorted(set(result))
