"""
Config Package - 集中管理编曲配置

从 config/instruments.py 导入所有配置，方便统一访问
"""

from .instruments import (
    INSTRUMENT_RANGES,
    INSTRUMENT_COMFORTABLE_RANGES,
    INSTRUMENT_PROGRAMS,
    ROLE_REGISTER_TARGETS,
    VELOCITY_CAPS_BY_MODE,
    SECTION_MODE_THRESHOLDS,
    PERCUSSION_CONFIG,
    GUARD_DEFAULTS,
    get_instrument_range,
    get_instrument_comfortable_range,
    get_instrument_program,
    get_role_register_target,
    get_velocity_cap,
    get_section_mode_thresholds,
    get_percussion_config,
)

__all__ = [
    "INSTRUMENT_RANGES",
    "INSTRUMENT_COMFORTABLE_RANGES",
    "INSTRUMENT_PROGRAMS",
    "ROLE_REGISTER_TARGETS",
    "VELOCITY_CAPS_BY_MODE",
    "SECTION_MODE_THRESHOLDS",
    "PERCUSSION_CONFIG",
    "GUARD_DEFAULTS",
    "get_instrument_range",
    "get_instrument_comfortable_range",
    "get_instrument_program",
    "get_role_register_target",
    "get_velocity_cap",
    "get_section_mode_thresholds",
    "get_percussion_config",
]
