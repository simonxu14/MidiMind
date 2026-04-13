from __future__ import annotations

from typing import Dict, List, Tuple

from ..plan_schema import ArrangementContext, NoteEvent, PartSpec


def apply_humanize(
    notes: List[NoteEvent],
    part: PartSpec,
    timing_jitter: int = 0,
    velocity_jitter: int = 0,
    distribution: str = "trunc_normal",
) -> List[NoteEvent]:
    """Apply timing/velocity humanization while preserving chord coherence."""
    import random

    if part.role == "melody":
        return notes

    if timing_jitter <= 0 and velocity_jitter <= 0:
        return notes

    by_start: Dict[int, List[Tuple[int, int, int, int, int]]] = {}
    for note in notes:
        start, end, pitch, velocity, channel = note
        by_start.setdefault(start, []).append(note)

    def sample_jitter() -> int:
        if distribution == "trunc_normal":
            while True:
                z = random.gauss(0, timing_jitter / 2)
                if -timing_jitter <= z <= timing_jitter:
                    return int(z)
        return random.randint(-timing_jitter, timing_jitter)

    result = []
    for start, group in by_start.items():
        jitter = sample_jitter() if timing_jitter > 0 else 0
        for s, e, pitch, velocity, channel in group:
            new_start = max(0, s + jitter)
            new_end = max(0, e + jitter)

            new_velocity = velocity
            if velocity_jitter > 0:
                v_jitter = random.randint(-velocity_jitter, velocity_jitter)
                new_velocity = max(1, min(127, velocity + v_jitter))

            result.append((new_start, new_end, pitch, new_velocity, channel))

    return result


def apply_per_measure_mode_adjustments(
    accompaniment_tracks: Dict[str, List[NoteEvent]],
    arrangement_context: ArrangementContext,
    get_velocity_caps_for_mode,
    get_instrument_key_for_track,
) -> Dict[str, List[NoteEvent]]:
    """Apply per-measure velocity caps based on section modes."""
    section_modes = arrangement_context.section_modes
    measure_len = arrangement_context.measure_len

    measure_velocity_caps: Dict[int, Dict[str, int]] = {}
    for measure_idx, mode in section_modes.items():
        measure_velocity_caps[measure_idx] = get_velocity_caps_for_mode(mode)

    result: Dict[str, List[NoteEvent]] = {}
    for track_id, notes in accompaniment_tracks.items():
        if not notes:
            result[track_id] = notes
            continue

        instrument_key = get_instrument_key_for_track(track_id)
        adjusted_notes: List[NoteEvent] = []
        for start, end, pitch, velocity, channel in notes:
            measure_idx = start // measure_len
            caps = measure_velocity_caps.get(measure_idx, measure_velocity_caps.get(0, {}))
            cap = caps.get(instrument_key, 127)
            if velocity > cap:
                velocity = cap
            adjusted_notes.append((start, end, pitch, velocity, channel))

        result[track_id] = adjusted_notes

    return result
