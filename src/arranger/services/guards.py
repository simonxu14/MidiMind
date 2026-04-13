from __future__ import annotations

from typing import Dict, List, Tuple

from ..plan_schema import GuardsConfig, NoteEvent, PartSpec


def apply_guards(
    notes: List[NoteEvent],
    part: PartSpec,
    guards: GuardsConfig,
    plan,
    instrument_ranges: Dict[str, Tuple[int, int]],
    melody_onsets: List[int],
    report_stats: Dict,
) -> List[NoteEvent]:
    """Apply velocity, onset-avoidance, and range guards while updating report stats."""
    if not notes:
        return notes

    instrument = part.instrument

    velocity_caps = guards.velocity_caps or {}
    max_velocity = velocity_caps.get(instrument, velocity_caps.get(part.id, 127))

    avoid_onsets = guards.avoid_melody_onsets
    onset_window = guards.onset_window_ticks
    range_min, range_max = instrument_ranges.get(instrument, (21, 108))

    guarded_notes: List[NoteEvent] = []
    part_id = part.id
    if part_id not in report_stats["exact_onset_collisions_by_part"]:
        report_stats["exact_onset_collisions_by_part"][part_id] = 0

    onset_set = set(melody_onsets)

    for start, end, pitch, velocity, channel in notes:
        original_start = start
        is_exact_collision = original_start in onset_set

        if velocity > max_velocity:
            report_stats["velocity_cap_hits"] += 1
        velocity = min(velocity, max_velocity)

        if avoid_onsets:
            in_onset_window = False
            for onset in melody_onsets:
                if onset <= start < onset + onset_window:
                    in_onset_window = True
                    break

            if in_onset_window:
                action = getattr(guards, "onset_avoidance_action", "scale_velocity")
                if action is None and plan.arrangement:
                    action = getattr(plan.arrangement, "onset_avoidance_action", "scale_velocity")
                if action is None:
                    action = "scale_velocity"

                if isinstance(action, dict):
                    lowered_part_id = part.id.lower() if part.id else ""
                    lowered_instrument = part.instrument.lower() if part.instrument else ""
                    action = action.get(
                        lowered_part_id,
                        action.get(lowered_instrument, action.get("default", "scale_velocity")),
                    )

                if action == "drop":
                    report_stats["onset_avoidance_hits"] += 1
                    report_stats["onset_drop_hits"] += 1
                    continue
                elif action == "delay":
                    import random

                    delay_ticks = random.randint(15, 30)
                    start = start + delay_ticks
                    end = end + delay_ticks
                    report_stats["onset_avoidance_hits"] += 1
                    report_stats["onset_delay_hits"] += 1
                else:
                    reduce_ratio = 0.6
                    if plan.arrangement and hasattr(plan.arrangement, "reduce_ratio"):
                        reduce_ratio = plan.arrangement.reduce_ratio
                    velocity = int(velocity * reduce_ratio)
                    report_stats["onset_avoidance_hits"] += 1
                    report_stats["onset_scale_velocity_hits"] += 1
                    if is_exact_collision:
                        report_stats["exact_onset_collisions_by_part"][part_id] += 1
        else:
            if is_exact_collision:
                report_stats["exact_onset_collisions_by_part"][part_id] += 1

        if pitch < range_min:
            pitch = range_min
        elif pitch > range_max:
            pitch = range_max

        guarded_notes.append((start, end, pitch, velocity, channel))

    return guarded_notes
