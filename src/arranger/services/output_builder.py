from __future__ import annotations

from typing import Dict, List, Tuple

from ..midi_io import MidiWriter
from ..plan_schema import CCConfig, NoteEvent


def add_cc_messages_to_track(
    messages: List[Tuple[str, Dict]],
    cc_config: CCConfig,
    channel: int,
    start_tick: int = 0,
) -> List[Tuple[str, Dict]]:
    if cc_config is None:
        return messages

    result = []
    cc_inserted = False
    for msg in messages:
        if not cc_inserted and msg[0] in ("note_on", "note_off"):
            if cc_config.cc7 is not None:
                result.append(("control_change", {"control": 7, "value": cc_config.cc7, "channel": channel, "time": 0}))
            if cc_config.cc11 is not None:
                result.append(("control_change", {"control": 11, "value": cc_config.cc11, "channel": channel, "time": 0}))
            if cc_config.cc91 is not None:
                result.append(("control_change", {"control": 91, "value": cc_config.cc91, "channel": channel, "time": 0}))
            if cc_config.cc93 is not None:
                result.append(("control_change", {"control": 93, "value": cc_config.cc93, "channel": channel, "time": 0}))
            cc_inserted = True
        result.append(msg)
    return result


def build_output_tracks(
    ensemble,
    locked_melody_notes: List[NoteEvent],
    accompaniment_tracks: Dict[str, List[NoteEvent]],
    melody_cc_config: CCConfig,
    other_cc_config: CCConfig,
) -> List[List[Tuple[str, Dict]]]:
    output_tracks = []

    melody_part = None
    for part in ensemble.parts:
        if part.role == "melody":
            melody_part = part
            break

    melody_program = melody_part.midi.program if melody_part else 0
    melody_channel = melody_part.midi.channel if melody_part else 0
    melody_track_data = MidiWriter.create_track_from_note_events(
        track_name=f"melody_{melody_part.id}" if melody_part else "melody",
        note_events=locked_melody_notes,
        program=melody_program,
        channel=melody_channel,
    )
    output_tracks.append(add_cc_messages_to_track(melody_track_data, melody_cc_config, melody_channel))

    for part in ensemble.parts:
        if part.role == "melody":
            continue
        part_track_data = MidiWriter.create_track_from_note_events(
            track_name=part.id,
            note_events=accompaniment_tracks.get(part.id, []),
            program=part.midi.program,
            channel=part.midi.channel,
        )
        output_tracks.append(add_cc_messages_to_track(part_track_data, other_cc_config, part.midi.channel))

    percussion_channel_map = {
        "auto_timpani": (11, 47),
        "auto_triangle": (12, 81),
    }
    for track_id, (channel, program) in percussion_channel_map.items():
        if track_id not in accompaniment_tracks:
            continue
        perc_track_data = MidiWriter.create_track_from_note_events(
            track_name=track_id,
            note_events=accompaniment_tracks[track_id],
            program=program,
            channel=channel,
        )
        perc_cc_config = other_cc_config.model_copy(deep=True)
        perc_cc_config.cc11 = None
        output_tracks.append(add_cc_messages_to_track(perc_track_data, perc_cc_config, channel))

    return output_tracks
