"""Service layer helpers for arranger executors."""

from .melody import lock_melody
from .harmony import analyze_harmony, default_harmony
from .context_builder import build_arrangement_context, build_register_targets
from .guards import apply_guards
from .postprocess import apply_humanize, apply_per_measure_mode_adjustments
from .generation import generate_default_accompaniment, generate_part_notes
from .percussion import auto_add_percussion
from .reporting import generate_arrangement_report, get_instrument_key_for_track
from .output_builder import add_cc_messages_to_track, build_output_tracks
from .autofix_pipeline import apply_autofix_pipeline, build_channel_ranges, regroup_notes_by_channel
from .executor_state import init_report_stats

__all__ = [
    "lock_melody",
    "analyze_harmony",
    "default_harmony",
    "build_arrangement_context",
    "build_register_targets",
    "apply_guards",
    "apply_humanize",
    "apply_per_measure_mode_adjustments",
    "generate_default_accompaniment",
    "generate_part_notes",
    "auto_add_percussion",
    "generate_arrangement_report",
    "get_instrument_key_for_track",
    "add_cc_messages_to_track",
    "build_output_tracks",
    "apply_autofix_pipeline",
    "build_channel_ranges",
    "regroup_notes_by_channel",
    "init_report_stats",
]
