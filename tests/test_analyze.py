from arranger.analyze import MidiAnalysisService
from arranger.midi_io import MidiWriter


def test_single_note_bearing_track_gets_confidence_floor():
    midi_data = MidiWriter.write_midi(
        tracks=[
            [
                ("note_on", {"channel": 0, "note": 72, "velocity": 64, "time": 0}),
                ("note_on", {"channel": 0, "note": 67, "velocity": 54, "time": 10}),
                ("note_off", {"channel": 0, "note": 67, "velocity": 0, "time": 110}),
                ("note_off", {"channel": 0, "note": 72, "velocity": 0, "time": 0}),
            ],
            [],
        ],
        ticks_per_beat=480,
        tempo=120,
        time_signature=(4, 4),
    )

    result = MidiAnalysisService().analyze(midi_data)

    assert result.melody_candidates
    assert result.melody_candidates[0].track_index == 1
    assert result.melody_candidates[0].score >= 0.35
    assert "Only note-bearing track in file" in result.melody_candidates[0].reason
