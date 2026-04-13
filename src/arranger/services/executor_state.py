from __future__ import annotations


def init_report_stats() -> dict:
    return {
        "template_per_part": {},
        "template_per_measure": {},
        "onset_avoidance_hits": 0,
        "onset_scale_velocity_hits": 0,
        "onset_delay_hits": 0,
        "onset_drop_hits": 0,
        "exact_onset_collisions_by_part": {},
        "velocity_cap_hits": 0,
        "percussion_hits": {"timpani": 0, "triangle": 0},
        "fixes_applied": [],
    }
