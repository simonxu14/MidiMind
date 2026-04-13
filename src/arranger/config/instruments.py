"""
Instrument Configuration - 乐器音域与默认音色配置

集中管理所有乐器的：
- 音域 (playable range)
- 舒适音区 (comfortable range)
- 表达性音区 (expressive sweet spot)
- 默认 program numbers
"""

from __future__ import annotations

from typing import Dict, Tuple, Optional


# ============ 乐器音域 ============

# (min_pitch, max_pitch) - MIDI pitch number (0-127)
# 数据来源：General MIDI Level 1 标准乐器范围

INSTRUMENT_RANGES: Dict[str, Tuple[int, int]] = {
    # 弦乐
    "violin": (55, 103),      # G3 - E7 (标准小提琴音域)
    "viola": (48, 91),        # C3 - A6 (中提琴音域)
    "cello": (36, 76),       # C2 - E5 (大提琴音域)
    "double_bass": (28, 67),  # E1 - G3 (低音提琴音域)
    "harp": (23, 103),       # A0 - E7 (竖琴音域，接近钢琴高音)

    # 木管
    "flute": (60, 96),       # C4 - C7 (长笛音域)
    "oboe": (58, 91),        # Bb3 - A6 (双簧管音域)
    "clarinet": (50, 99),    # E3 - Bb6 (单簧管音域)
    "bassoon": (34, 75),     # Bb1 - E5 (巴松管音域)
    "recorder": (60, 96),    # C4 - C7 (竖笛，参考长笛)

    # 铜管
    "horn": (40, 77),        # F2 - E5 (圆号音域)
    "french_horn": (40, 77), # 同圆号
    "trumpet": (52, 84),     # C4 - C6 (小号音域)
    "trombone": (40, 72),    # E2 - Bb4 (长号音域)
    "tuba": (27, 58),        # B0 - Eb3 (大号音域)

    # 键盘
    "piano": (21, 108),      # A0 - C8 (钢琴完整音域)

    # 打击乐
    "timpani": (45, 61),      # F2 - C#4 (定音鼓，标准 4 个鼓)
    "marimba": (48, 96),     # C3 - C7 (马林巴)
    "xylophone": (60, 108),  # C4 - C8 (木琴)
    "vibraphone": (48, 96),  # C3 - C7 (颤音琴)

    # GM Percussion (channel 9)
    # 标准映射见 percussion.py
}


# ============ 乐器舒适音区 (音色最好的区间) ============

# 这是乐器音色最自然、最容易演奏的区间
# 模板生成和 AutoFixer 应该优先落在这个区间

INSTRUMENT_COMFORTABLE_RANGES: Dict[str, Tuple[int, int]] = {
    "violin": (67, 98),       # G4 - B6 (小提琴最佳演奏区)
    "viola": (60, 84),       # Bb3 - C6 (中提琴最佳区)
    "cello": (48, 72),       # C3 - C5 (大提琴最佳区)
    "double_bass": (36, 55), # C2 - G3 (低音提琴最佳区)
    "flute": (72, 91),       # C5 - A6 (长笛最佳区)
    "oboe": (62, 84),        # D4 - C6 (双簧管最佳区)
    "clarinet": (55, 84),    # G3 - C6 (单簧管最佳区)
    "bassoon": (40, 62),     # Bb1 - D4 (巴松管最佳区)
    "horn": (48, 72),        # C3 - C5 (圆号最佳区)
    "trumpet": (60, 77),     # C4 - F#5 (小号最佳区)
    "trombone": (48, 67),   # C3 - G4 (长号最佳区)
    "tuba": (34, 50),        # Bb1 - D3 (大号最佳区)
    "piano": (36, 84),       # C2 - C6 (钢琴中央音区)
    "timpani": (45, 53),     # F2 - F3 (定音鼓中心)
}


# ============ GM Program Numbers ============

# General MIDI Level 1 标准 program numbers

INSTRUMENT_PROGRAMS: Dict[str, int] = {
    # 弦乐
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "double_bass": 43,

    # 木管
    "flute": 73,
    "oboe": 68,
    "clarinet": 71,
    "bassoon": 70,

    # 铜管
    "horn": 60,
    "french_horn": 60,
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,

    # 键盘
    "piano": 0,
    "harpsichord": 6,
    "organ": 19,
    "accordion": 22,

    # 打击乐 (注意：打击乐通常用 channel 9，program 固定为 0 或按音色选择)
    "timpani": 47,
    "marimba": 12,
    "xylophone": 13,
    "vibraphone": 11,
    "cymbal": 49,
    "snare": 38,
    "bass_drum": 36,
}


# ============ Role -> Register Target ============

# 各角色的标准音区目标
# 用于模板生成时决定音符应该落在哪个音区

ROLE_REGISTER_TARGETS: Dict[str, str] = {
    "melody": "high",          # 主旋律：高音区
    "counter_melody": "high_middle",  # 副旋律：中高音区
    "inner_voice": "middle",   # 内声部：中音区
    "bass": "low",             # 低音：低音区
    "bass_rhythm": "low",      # 低音节奏：低音区
    "anchor": "low",           # 锚固：低音区
    "accompaniment": "middle",  # 伴奏：中音区
    "sustain_support": "middle_low",  # 持续音支撑：中低音区
    "accent": "high",         # 强调：高音区
    "fanfare": "high",        # 号角性：高音区
    "percussion": "low",       # 打击乐：低音区
    "tutti": "full",          # 全奏：全音域
}


# ============ Velocity Caps By Mode ============

# 按段落模式的力度上限
# A=透明/克制, B=流动, C=明亮, D=高潮

VELOCITY_CAPS_BY_MODE: Dict[str, Dict[str, int]] = {
    "A": {
        "pf": 52,   # 钢琴
        "va": 56,   # 中提琴
        "vc": 62,   # 大提琴
        "winds": 58,  # 木管
        "hn": 56,   # 圆号
    },
    "B": {
        "pf": 56,
        "va": 60,
        "vc": 66,
        "winds": 60,
        "hn": 58,
    },
    "C": {
        "pf": 58,
        "va": 62,
        "vc": 70,
        "winds": 62,
        "hn": 60,
    },
    "D": {
        "pf": 62,
        "va": 66,
        "vc": 74,
        "winds": 64,
        "hn": 62,
    },
}


# ============ Section Mode Thresholds ============

# 段落模式检测阈值
# 基于 8 小节统计的旋律特征判定

SECTION_MODE_THRESHOLDS = {
    "D_av": 85,   # 高潮段：平均力度阈值
    "B_nn": 80,   # 流动段：音符密度阈值
    "C_ap": 72,   # 明亮段：平均音高阈值
}


# ============ Percussion Defaults ============

PERCUSSION_CONFIG = {
    "timpani": {
        "phrase_block_measures": 8,   # 每 8 小节乐句块
        "timp_vel_base": 35,          # 定音鼓基础力度
        "timp_dur_ticks": 240,         # 定音鼓持续时间
        "trigger_position": 0.875,    # 触发位置：第4拍后半拍 (7/8)
    },
    "triangle": {
        "phrase_block_measures": 8,
        "tri_vel_base": 25,           # 三角铁基础力度
        "tri_dur_ticks": 60,           # 三角铁持续时间
        "trigger_position": 0.0,       # 触发位置：乐句块开始 (第1拍)
    },
    "accent_cymbal": {
        "phrase_block_measures": 8,
        "vel_base": 40,
        "dur_ticks": 120,
    },
}


# ============ Guard Defaults ============

GUARD_DEFAULTS = {
    "onset_window_ticks": 120,          # 旋律 onset 避让窗口
    "reduce_ratio": 0.6,              # 力度折减比
    "min_semitones": 5,               # 音区最小分离半音数
    "max_octave_jump": 19,            # 最大八度跳跃 (超过此值需修复)
}


# ============ 便捷访问函数 ============

def get_instrument_range(instrument: str) -> Tuple[int, int]:
    """获取乐器演奏音域"""
    return INSTRUMENT_RANGES.get(instrument.lower(), (21, 108))


def get_instrument_comfortable_range(instrument: str) -> Tuple[int, int]:
    """获取乐器舒适音区"""
    return INSTRUMENT_COMFORTABLE_RANGES.get(instrument.lower(), get_instrument_range(instrument))


def get_instrument_program(instrument: str) -> int:
    """获取乐器 GM program number"""
    return INSTRUMENT_PROGRAMS.get(instrument.lower(), 0)


def get_role_register_target(role: str) -> str:
    """获取角色的音区目标"""
    return ROLE_REGISTER_TARGETS.get(role, "middle")


def get_velocity_cap(instrument_key: str, mode: str) -> int:
    """获取指定模式和乐器的力度上限"""
    mode_caps = VELOCITY_CAPS_BY_MODE.get(mode, {})
    return mode_caps.get(instrument_key, 127)


def get_section_mode_thresholds() -> Dict[str, int]:
    """获取段落模式检测阈值"""
    return SECTION_MODE_THRESHOLDS.copy()


def get_percussion_config(instrument: str) -> Optional[Dict]:
    """获取打击乐配置"""
    return PERCUSSION_CONFIG.get(instrument.lower())
