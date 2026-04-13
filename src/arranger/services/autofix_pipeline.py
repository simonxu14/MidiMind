from __future__ import annotations

from typing import Dict, List, Tuple

from ..auto_fixer import AutoFixer
from ..plan_schema import NoteEvent


def build_channel_ranges(ensemble, instrument_ranges: Dict[str, Tuple[int, int]]) -> Dict[int, Tuple[int, int]]:
    channel_ranges: Dict[int, Tuple[int, int]] = {}
    for part in ensemble.parts:
        if part.role == "melody":
            continue
        instrument = part.instrument.lower() if part.instrument else "piano"
        channel_ranges[part.midi.channel] = instrument_ranges.get(instrument, instrument_ranges.get("piano", (21, 108)))
    return channel_ranges


def regroup_notes_by_channel(notes: List[NoteEvent]) -> Dict[int, List[NoteEvent]]:
    channel_to_notes: Dict[int, List[NoteEvent]] = {}
    for note in notes:
        channel_to_notes.setdefault(note[4], []).append(note)
    return channel_to_notes


def apply_autofix_pipeline(
    accompaniment_tracks: Dict[str, List[NoteEvent]],
    ensemble,
    arrangement_context,
    plan,
    locked_melody_notes: List[NoteEvent],
    instrument_ranges: Dict[str, Tuple[int, int]],
    report_stats: Dict,
) -> Dict[str, List[NoteEvent]]:
    all_accompaniment_notes: List[NoteEvent] = []
    for notes in accompaniment_tracks.values():
        all_accompaniment_notes.extend(notes)

    if not all_accompaniment_notes:
        return accompaniment_tracks

    fixer = AutoFixer()
    fixed_notes = fixer.fix_all(
        all_accompaniment_notes,
        build_channel_ranges(ensemble, instrument_ranges),
        skip_channels=[9],
    )

    if plan.arrangement and getattr(plan.arrangement, "register_separation", False):
        min_semitones = getattr(plan.arrangement, "min_semitones", 5)
        chord_tuples = {
            measure: (chord.root, chord.third, chord.fifth)
            for measure, chord in arrangement_context.chord_per_measure.items()
        }
        fixed_notes = fixer.apply_register_separation(
            fixed_notes,
            locked_melody_notes,
            min_semitones=min_semitones,
            chord_per_measure=chord_tuples,
        )

    report_stats["fixes_applied"] = fixer.get_fixes_applied()
    channel_to_notes = regroup_notes_by_channel(fixed_notes)

    updated_tracks = dict(accompaniment_tracks)
    for part in ensemble.parts:
        if part.role == "melody":
            continue
        updated_tracks[part.id] = channel_to_notes.get(part.midi.channel, [])

    return updated_tracks
