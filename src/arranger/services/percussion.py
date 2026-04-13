from __future__ import annotations

from typing import Dict, List

from ..plan_schema import ArrangementContext, NoteEvent


def generate_timpani_notes(context: ArrangementContext, policy) -> List[NoteEvent]:
    import random

    notes: List[NoteEvent] = []
    channel = 11
    ticks_per_beat = context.ticks_per_beat
    measure_len = context.measure_len
    vel_base = policy.timp_vel_base if hasattr(policy, 'timp_vel_base') else 35
    dur = policy.timp_dur_ticks if hasattr(policy, 'timp_dur_ticks') else 240
    phrase_block = getattr(policy, 'phrase_block_measures', 8)

    for measure_idx, chord_info in context.chord_per_measure.items():
        if measure_idx % phrase_block != phrase_block - 1:
            continue
        measure_start = measure_idx * measure_len
        tick = measure_start + int(3.5 * ticks_per_beat)
        velocity = max(25, min(50, vel_base + random.randint(-8, 8)))
        pitch = max(45, min(53, chord_info.root))
        if pitch > 53:
            pitch -= 12
        if pitch < 45:
            pitch += 12
        notes.append((tick, tick + dur, pitch, velocity, channel))

    return notes


def generate_triangle_notes(context: ArrangementContext, policy) -> List[NoteEvent]:
    import random

    notes: List[NoteEvent] = []
    channel = 9
    measure_len = context.measure_len
    vel_base = policy.tri_vel_base if hasattr(policy, 'tri_vel_base') else 25
    dur = policy.tri_dur_ticks if hasattr(policy, 'tri_dur_ticks') else 60
    phrase_block = getattr(policy, 'phrase_block_measures', 8)

    for measure_idx in context.chord_per_measure.keys():
        if measure_idx % phrase_block != 0:
            continue
        measure_start = measure_idx * measure_len
        velocity = max(18, min(35, vel_base + random.randint(-5, 5)))
        notes.append((measure_start, measure_start + dur, 81, velocity, channel))

    return notes


def auto_add_percussion(
    accompaniment_tracks: Dict[str, List[NoteEvent]],
    arrangement_context: ArrangementContext,
    plan,
    ensemble,
    report_stats: Dict,
) -> Dict[str, List[NoteEvent]]:
    if not plan.arrangement or not plan.arrangement.percussion:
        return accompaniment_tracks

    percussion_policy = plan.arrangement.percussion
    if not getattr(percussion_policy, "auto_add_when_absent", False):
        return accompaniment_tracks

    existing_percussion = set()
    for part in ensemble.parts:
        if part.role in ("percussion", "bass_rhythm", "accent"):
            if part.instrument in ("timpani", "cymbal", "percussion", "drums"):
                existing_percussion.add(part.instrument)

    if percussion_policy.timpani_enabled and "timpani" not in existing_percussion:
        timpani_notes = generate_timpani_notes(arrangement_context, percussion_policy)
        if timpani_notes:
            accompaniment_tracks["auto_timpani"] = timpani_notes
            report_stats["percussion_hits"]["timpani"] = len(timpani_notes)

    if percussion_policy.triangle_enabled and "triangle" not in existing_percussion:
        triangle_notes = generate_triangle_notes(arrangement_context, percussion_policy)
        if triangle_notes:
            accompaniment_tracks["auto_triangle"] = triangle_notes
            report_stats["percussion_hits"]["triangle"] = len(triangle_notes)

    return accompaniment_tracks
