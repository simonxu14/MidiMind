"""
测试 MIDI IO 模块
"""

import pytest
from arranger.midi_io import MidiWriter, MidiReader


class TestMidiWriter:
    """测试 MidiWriter"""

    def test_write_midi_basic(self):
        """测试基本 MIDI 写入"""
        # 创建简单的单轨 MIDI
        tracks = [
            [
                ("note_on", {"channel": 0, "note": 60, "velocity": 64, "time": 0}),
                ("note_off", {"channel": 0, "note": 60, "velocity": 0, "time": 480}),
            ]
        ]

        midi_data = MidiWriter.write_midi(
            tracks=tracks,
            ticks_per_beat=480,
            tempo=120,
            time_signature=(4, 4),
        )

        assert isinstance(midi_data, bytes)
        assert len(midi_data) > 0
        # MIDI 文件以 MThd 开头
        assert midi_data[:4] == b"MThd"

    def test_write_midi_empty_tracks(self):
        """测试写入空轨道"""
        tracks = []
        midi_data = MidiWriter.write_midi(tracks=tracks)

        assert isinstance(midi_data, bytes)
        assert len(midi_data) > 0

    def test_write_midi_multiple_tracks(self):
        """测试写入多轨道"""
        tracks = [
            [
                ("note_on", {"channel": 0, "note": 60, "velocity": 64, "time": 0}),
                ("note_off", {"channel": 0, "note": 60, "velocity": 0, "time": 480}),
            ],
            [
                ("note_on", {"channel": 1, "note": 48, "velocity": 64, "time": 0}),
                ("note_off", {"channel": 1, "note": 48, "velocity": 0, "time": 480}),
            ],
        ]

        midi_data = MidiWriter.write_midi(tracks=tracks)

        assert isinstance(midi_data, bytes)
        assert len(midi_data) > 0

    def test_write_midi_different_tempos(self):
        """测试不同速度"""
        tracks = [[]]

        for tempo in [60, 90, 120, 180]:
            midi_data = MidiWriter.write_midi(
                tracks=tracks,
                tempo=tempo,
            )
            assert isinstance(midi_data, bytes)


class TestMidiWriterCreateTrack:
    """测试 MidiWriter.create_track_from_note_events"""

    def test_create_track_empty(self):
        """测试创建空轨道"""
        track_data = MidiWriter.create_track_from_note_events(
            track_name="Empty Track",
            note_events=[],
            program=0,
            channel=0,
        )

        assert isinstance(track_data, list)

    def test_create_track_with_notes(self):
        """测试创建带音符的轨道"""
        note_events = [
            (0, 480, 60, 64, 0),  # start, end, pitch, velocity, channel
            (480, 960, 64, 62, 0),
            (960, 1440, 67, 60, 0),
        ]

        track_data = MidiWriter.create_track_from_note_events(
            track_name="Melody",
            note_events=note_events,
            program=40,  # Violin
            channel=0,
        )

        assert isinstance(track_data, list)
        assert len(track_data) > 0

    def test_create_track_sets_program(self):
        """测试轨道设置了 program change"""
        note_events = [(0, 480, 60, 64, 0)]

        track_data = MidiWriter.create_track_from_note_events(
            track_name="Test",
            note_events=note_events,
            program=0,
            channel=0,
        )

        # 应该有 program_change 消息
        program_changes = [msg for msg in track_data if msg[0] == "program_change"]
        assert len(program_changes) == 1


class TestMidiWriterTempoTrack:
    """测试 MidiWriter tempo track 创建"""

    def test_create_tempo_track(self):
        """测试创建 tempo track"""
        tempo_track = MidiWriter._create_tempo_track(
            tempo=120,
            time_signature=(4, 4),
        )

        assert isinstance(tempo_track, list)
        # 应该有消息
        assert len(tempo_track) > 0

    def test_create_tempo_track_different_time_signatures(self):
        """测试不同拍号"""
        for numerator, denominator in [(4, 4), (3, 4), (6, 8), (2, 4)]:
            tempo_track = MidiWriter._create_tempo_track(
                tempo=120,
                time_signature=(numerator, denominator),
            )
            assert isinstance(tempo_track, list)
            assert len(tempo_track) > 0
