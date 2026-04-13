from __future__ import annotations

from typing import List

from ..midi_io import TrackInfo
from ..plan_schema import EnsembleConfig, NoteEvent


def lock_melody(melody_track: TrackInfo, ensemble: EnsembleConfig | None) -> List[NoteEvent]:
    """Copy the melody track note-for-note onto the configured melody channel."""
    locked: List[NoteEvent] = []

    melody_channel = 0
    if ensemble and ensemble.parts:
        for part in ensemble.parts:
            if part.role == "melody":
                melody_channel = part.midi.channel
                break

    for note in melody_track.notes:
        locked.append((
            note.start_tick,
            note.end_tick,
            note.pitch,
            note.velocity,
            melody_channel,
        ))

    return locked
