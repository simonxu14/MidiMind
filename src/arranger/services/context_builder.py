from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..harmony_analyzer import estimate_section_modes
from ..midi_io import MidiFile, TrackInfo
from ..plan_schema import ArrangementContext, ChordInfo, EnsembleConfig, NoteEvent
from ..timebase import measure_len as calc_measure_len


def build_register_targets(ensemble: EnsembleConfig | None) -> Dict[str, str]:
    if not ensemble or not ensemble.parts:
        return {}

    register_targets = {}
    instrument_ranges = {
        "violin": "high",
        "viola": "middle",
        "cello": "low_middle",
        "double_bass": "low",
        "flute": "high",
        "oboe": "high_middle",
        "clarinet": "high_middle",
        "bassoon": "low",
        "horn": "middle",
        "trumpet": "high",
        "trombone": "middle_low",
        "tuba": "low",
        "piano": "full",
        "timpani": "low",
    }
    role_adjustments = {
        "melody": "high",
        "counter_melody": "high_middle",
        "inner_voice": "middle",
        "bass": "low",
        "bass_rhythm": "low",
        "anchor": "low",
        "accompaniment": "middle",
        "sustain_support": "middle_low",
        "accent": "high",
        "fanfare": "high",
        "percussion": "low",
        "tutti": "full",
    }

    for part in ensemble.parts:
        base_register = instrument_ranges.get(part.instrument, "middle")
        register_targets[part.id] = role_adjustments.get(part.role, base_register)

    return register_targets


def build_arrangement_context(
    midi: MidiFile,
    tracks: List[TrackInfo],
    harmony: Dict[int, ChordInfo],
    ensemble: EnsembleConfig | None,
    get_velocity_caps_for_mode,
    tempo: int = 120,
    melody_track_index: Optional[int] = None,
    time_signature: Tuple[int, int] = (4, 4),
) -> ArrangementContext:
    total_ticks = 0
    for track in tracks:
        if track.notes:
            track_end = max(n.end_tick for n in track.notes)
            total_ticks = max(total_ticks, track_end)

    melody_notes = []
    if melody_track_index is not None and melody_track_index < len(tracks):
        melody_notes = tracks[melody_track_index].notes
    else:
        best_track = None
        best_score = 0
        for track in tracks:
            if track.notes:
                avg_pitch = sum(n.pitch for n in track.notes) / len(track.notes)
                score = len(track.notes) * avg_pitch
                if score > best_score:
                    best_score = score
                    best_track = track
        if best_track:
            melody_notes = best_track.notes

    melody_onsets = sorted(set(n.start_tick for n in melody_notes)) if melody_notes else []
    melody_range = (
        (min(n.pitch for n in melody_notes), max(n.pitch for n in melody_notes))
        if melody_notes else (60, 72)
    )

    if tempo < 80:
        style = "ballad"
    elif tempo < 110:
        style = "general"
    elif tempo < 140:
        style = "upbeat"
    else:
        style = "dance"

    prev_chord_root = None
    sorted_measures = sorted(harmony.keys())
    if len(sorted_measures) > 1:
        prev_chord_root = harmony[sorted_measures[0]].root

    register_targets = build_register_targets(ensemble)
    measure_len = calc_measure_len(int(midi.ticks_per_beat), time_signature)
    total_measures = total_ticks // measure_len if total_ticks > 0 else 1

    melody_note_events: List[NoteEvent] = [
        (n.start_tick, n.end_tick, n.pitch, n.velocity, 0)
        for n in melody_notes
    ]

    section_modes = estimate_section_modes(
        melody_note_events,
        total_measures,
        measure_len,
        section_block=8,
        D_av=85,
        B_nn=80,
        C_ap=72,
    )
    current_mode = section_modes.get(0, "A")
    velocity_caps = get_velocity_caps_for_mode(current_mode)

    return ArrangementContext(
        measure_len=measure_len,
        ticks_per_beat=int(midi.ticks_per_beat),
        time_signature_num=time_signature[0],
        time_signature_den=time_signature[1],
        chord_per_measure=harmony,
        section_modes=section_modes,
        current_mode=current_mode,
        melody_onsets=melody_onsets,
        melody_notes=melody_note_events,
        melody_range=melody_range,
        tempo=int(tempo),
        style=style,
        register_targets=register_targets,
        prev_chord_root=prev_chord_root,
        velocity_caps=velocity_caps,
    )
