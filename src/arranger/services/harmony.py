from __future__ import annotations

from typing import Dict, List, Tuple

from ..harmony_analyzer import analyze_chord_quality, choose_triadish
from ..midi_io import ParsedNote, TrackInfo
from ..plan_schema import ChordInfo, HarmonyContext
from ..timebase import measure_len as calc_measure_len


def default_harmony(melody_track: TrackInfo, time_signature_den: int = 4) -> Dict[int, ChordInfo]:
    """Fallback harmony analysis based only on the melody track."""
    if not melody_track.notes:
        return {0: ChordInfo(root=60, third=64, fifth=67, quality="major")}

    ticks_per_beat = 480
    measure_notes: Dict[int, List[ParsedNote]] = {}

    for note in melody_track.notes:
        measure = note.start_tick // (ticks_per_beat * time_signature_den)
        measure_notes.setdefault(measure, []).append(note)

    harmony: Dict[int, ChordInfo] = {}
    for measure, notes in measure_notes.items():
        pitches = sorted(set(n.pitch for n in notes))

        if len(pitches) < 2:
            root = pitches[0] if pitches else 60
            harmony[measure] = ChordInfo(root=root, third=root + 4, fifth=root + 7, quality="major")
            continue

        root = pitches[0]
        third_candidates = [p for p in pitches if 3 <= (p - root) % 12 <= 4]
        third = third_candidates[0] if third_candidates else root + 4

        fifth_candidates = [p for p in pitches if 6 <= (p - root) % 12 <= 8]
        fifth = fifth_candidates[0] if fifth_candidates else root + 7

        seventh_candidates = [p for p in pitches if 10 <= (p - root) % 12 <= 12]
        seventh = seventh_candidates[0] if seventh_candidates else None

        third_interval = (third - root) % 12
        fifth_interval = (fifth - root) % 12
        quality = "unknown"

        if seventh is not None:
            seventh_interval = (seventh - root) % 12
            if seventh_interval == 11:
                if third_interval == 4:
                    quality = "dominant7"
                elif third_interval == 3:
                    quality = "minor7"
            elif seventh_interval == 10:
                if third_interval == 4:
                    quality = "major7"
        else:
            if fifth_interval == 7:
                if third_interval == 4:
                    quality = "major"
                elif third_interval == 3:
                    quality = "minor"
            elif fifth_interval == 6 and third_interval == 3:
                quality = "diminished"
            elif fifth_interval == 8 and third_interval == 4:
                quality = "augmented"

        harmony[measure] = ChordInfo(
            root=root,
            third=third,
            fifth=fifth,
            seventh=seventh,
            quality=quality,
        )

    return harmony


def analyze_harmony(
    tracks: List[TrackInfo],
    melody_track_index: int,
    harmony_ctx: HarmonyContext,
    ticks_per_beat: int = 480,
) -> Dict[int, ChordInfo]:
    """Analyze per-measure harmony from non-melody source tracks."""
    source_indices = [i for i in harmony_ctx.source_track_indices if i != melody_track_index]
    if not source_indices:
        source_indices = [i for i in range(len(tracks)) if i != melody_track_index]

    all_notes: List[ParsedNote] = []
    for idx in source_indices:
        if idx < len(tracks):
            all_notes.extend(tracks[idx].notes)

    if not all_notes:
        ts_den = harmony_ctx.time_signature_den if hasattr(harmony_ctx, "time_signature_den") else 4
        return default_harmony(tracks[melody_track_index], time_signature_den=ts_den)

    measure_notes: Dict[int, List[ParsedNote]] = {}
    ts_den = harmony_ctx.time_signature_den if hasattr(harmony_ctx, "time_signature_den") else 4
    ts_num = harmony_ctx.time_signature_num if hasattr(harmony_ctx, "time_signature_num") else 4
    measure_len_val = calc_measure_len(ticks_per_beat, (ts_num, ts_den))

    for note in all_notes:
        measure = note.start_tick // measure_len_val
        measure_notes.setdefault(measure, []).append(note)

    harmony: Dict[int, ChordInfo] = {}
    for measure, notes in measure_notes.items():
        if not notes:
            continue

        pitches = sorted(set(n.pitch for n in notes))
        if len(pitches) < 3:
            root = pitches[0] if pitches else 60
            third = root + 4
            fifth = root + 7
            quality = "unknown"
        else:
            triad = choose_triadish(pitches)
            if triad:
                root, third, fifth = triad
                quality = analyze_chord_quality(root, third, fifth)
            else:
                root = pitches[0]
                third = root + 4
                fifth = root + 7
                quality = "unknown"

        harmony[measure] = ChordInfo(root=root, third=third, fifth=fifth, quality=quality)

    return harmony
