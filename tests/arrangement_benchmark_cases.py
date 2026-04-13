from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from arranger.analyze import MidiAnalysisService
from arranger.midi_io import MidiWriter
from arranger.plan_schema import (
    ArrangementConfig,
    Constraints,
    EnsembleConfig,
    GuardsConfig,
    HarmonyContext,
    LockMelodyConfig,
    MidiOutputConfig,
    MidiSpec,
    OutputConfig,
    PartSpec,
    PercussionPolicy,
    TransformSpec,
    UnifiedPlan,
)


SAMPLE_DIR = Path(__file__).resolve().parent / "sample"


@dataclass(frozen=True)
class SampleMidiSpec:
    name: str
    source_name: str
    source_type: str
    midi_data: bytes
    melody_track_index: int
    melody_confidence: float
    track_count: int
    ticks_per_beat: int
    tempo: float
    time_signature: tuple[int, int]
    total_ticks: int


@dataclass(frozen=True)
class ArrangementBenchmarkProfile:
    name: str
    description: str
    expected_parts: int
    max_fix_rate_per_100_notes: float
    build_plan: Callable[[SampleMidiSpec], UnifiedPlan]


@dataclass(frozen=True)
class ArrangementBenchmarkCase:
    name: str
    sample: SampleMidiSpec
    profile: ArrangementBenchmarkProfile


def _make_plan(sample: SampleMidiSpec, name: str, parts: list[PartSpec]) -> UnifiedPlan:
    return UnifiedPlan(
        schema_version="1.0",
        transform=TransformSpec(type="orchestration"),
        ensemble=EnsembleConfig(
            name=name,
            size="small",
            target_size=len(parts),
            parts=parts,
        ),
        harmony_context=HarmonyContext(
            method="measure_pitchset_triadish",
            granularity="per_measure",
        ),
        constraints=Constraints(
            lock_melody_events=LockMelodyConfig(
                enabled=True,
                source_track_ref=str(sample.melody_track_index),
                source_track_selection_mode="fixed",
                user_confirm_required=False,
            ),
            keep_total_ticks=True,
            guards=GuardsConfig(
                velocity_caps={},
                avoid_melody_onsets=True,
                onset_window_ticks=120,
                onset_avoidance_action="scale_velocity",
                register_separation=True,
            ),
        ),
        arrangement=ArrangementConfig(
            reduce_ratio=0.6,
            onset_avoidance_action="scale_velocity",
            register_separation=True,
            min_semitones=5,
            humanize={"enabled": False},
            percussion=PercussionPolicy(
                auto_add_when_absent=False,
                timpani_enabled=False,
                triangle_enabled=False,
            ),
        ),
        outputs=OutputConfig(
            midi=MidiOutputConfig(enabled=True, filename=f"{name}.mid"),
        ),
    )


def _build_piano_trio_plan(sample: SampleMidiSpec) -> UnifiedPlan:
    return _make_plan(
        sample,
        name="piano_trio",
        parts=[
            PartSpec(
                id="vn1",
                name="Violin I",
                role="melody",
                instrument="violin",
                midi=MidiSpec(channel=0, program=40),
                template_name="violin_cantabile",
            ),
            PartSpec(
                id="piano",
                name="Piano",
                role="accompaniment",
                instrument="piano",
                midi=MidiSpec(channel=1, program=0),
                template_name="dense_accompaniment",
                template_params={"density": 0.5},
            ),
            PartSpec(
                id="vc",
                name="Cello",
                role="bass",
                instrument="cello",
                midi=MidiSpec(channel=2, program=42),
                template_name="cello_pedal_root",
            ),
        ],
    )


def _build_string_quartet_plan(sample: SampleMidiSpec) -> UnifiedPlan:
    return _make_plan(
        sample,
        name="string_quartet",
        parts=[
            PartSpec(
                id="vn1",
                name="Violin I",
                role="melody",
                instrument="violin",
                midi=MidiSpec(channel=0, program=40),
                template_name="violin_cantabile",
            ),
            PartSpec(
                id="vn2",
                name="Violin II",
                role="inner_voice",
                instrument="violin",
                midi=MidiSpec(channel=1, program=40),
                template_name="adaptive_strings",
                template_params={"density": 0.4},
            ),
            PartSpec(
                id="va",
                name="Viola",
                role="inner_voice",
                instrument="viola",
                midi=MidiSpec(channel=2, program=41),
                template_name="viola_inner_16ths",
            ),
            PartSpec(
                id="vc",
                name="Cello",
                role="bass",
                instrument="cello",
                midi=MidiSpec(channel=3, program=42),
                template_name="cello_pedal_root",
            ),
        ],
    )


def _build_chamber_mixed_plan(sample: SampleMidiSpec) -> UnifiedPlan:
    return _make_plan(
        sample,
        name="chamber_mixed",
        parts=[
            PartSpec(
                id="vn1",
                name="Violin I",
                role="melody",
                instrument="violin",
                midi=MidiSpec(channel=0, program=40),
                template_name="violin_cantabile",
            ),
            PartSpec(
                id="piano",
                name="Piano",
                role="accompaniment",
                instrument="piano",
                midi=MidiSpec(channel=1, program=0),
                template_name="dense_accompaniment",
                template_params={"density": 0.4},
            ),
            PartSpec(
                id="vc",
                name="Cello",
                role="bass",
                instrument="cello",
                midi=MidiSpec(channel=2, program=42),
                template_name="cello_pedal_root",
            ),
            PartSpec(
                id="fl",
                name="Flute",
                role="counter_melody",
                instrument="flute",
                midi=MidiSpec(channel=3, program=73),
                template_name="flute_countermelody",
            ),
            PartSpec(
                id="cl",
                name="Clarinet",
                role="sustain_support",
                instrument="clarinet",
                midi=MidiSpec(channel=4, program=71),
                template_name="clarinet_sustain",
            ),
        ],
    )


def build_arrangement_profiles() -> list[ArrangementBenchmarkProfile]:
    return [
        ArrangementBenchmarkProfile(
            name="piano_trio",
            description="Melody-led piano trio with stable bass support.",
            expected_parts=3,
            max_fix_rate_per_100_notes=22.0,
            build_plan=_build_piano_trio_plan,
        ),
        ArrangementBenchmarkProfile(
            name="string_quartet",
            description="String quartet texture with explicit inner voices.",
            expected_parts=4,
            max_fix_rate_per_100_notes=18.0,
            build_plan=_build_string_quartet_plan,
        ),
        ArrangementBenchmarkProfile(
            name="chamber_mixed",
            description="Mixed chamber ensemble with winds layered on top of strings and piano.",
            expected_parts=5,
            max_fix_rate_per_100_notes=28.0,
            build_plan=_build_chamber_mixed_plan,
        ),
    ]


def _build_simple_ballad_4_4() -> bytes:
    note_events = []
    absolute_tick = 0
    notes = [
        67, 69, 71, 72,
        71, 69, 67, 64,
        65, 67, 69, 71,
        69, 67, 65, 64,
    ]
    for pitch in notes:
        note_events.append((absolute_tick, absolute_tick + 480, pitch, 68, 0))
        absolute_tick += 480
    return MidiWriter.write_midi(
        tracks=[MidiWriter.create_track_from_note_events("Lead", note_events, program=0, channel=0)],
        ticks_per_beat=480,
        tempo=84,
        time_signature=(4, 4),
    )


def _build_compound_6_8_lilt() -> bytes:
    note_events = []
    absolute_tick = 0
    pattern = [
        (72, 360), (74, 360), (76, 720),
        (74, 360), (72, 360), (69, 720),
    ] * 4
    for pitch, duration in pattern:
        note_events.append((absolute_tick, absolute_tick + duration, pitch, 66, 0))
        absolute_tick += duration
    return MidiWriter.write_midi(
        tracks=[MidiWriter.create_track_from_note_events("Lead", note_events, program=0, channel=0)],
        ticks_per_beat=480,
        tempo=78,
        time_signature=(6, 8),
    )


def _build_waltz_3_4() -> bytes:
    note_events = []
    absolute_tick = 0
    pattern = [72, 74, 76, 77, 76, 74, 72, 69, 71, 72, 74, 76]
    for pitch in pattern:
        note_events.append((absolute_tick, absolute_tick + 480, pitch, 64, 0))
        absolute_tick += 480
    return MidiWriter.write_midi(
        tracks=[MidiWriter.create_track_from_note_events("Lead", note_events, program=0, channel=0)],
        ticks_per_beat=480,
        tempo=96,
        time_signature=(3, 4),
    )


def _build_syncopated_pop_4_4() -> bytes:
    note_events = []
    absolute_tick = 240
    pattern = [
        (67, 240), (69, 480), (71, 240), (72, 480),
        (71, 240), (69, 480), (67, 240), (64, 480),
    ] * 2
    for pitch, duration in pattern:
        note_events.append((absolute_tick, absolute_tick + duration, pitch, 70, 0))
        absolute_tick += duration
        absolute_tick += 240
    return MidiWriter.write_midi(
        tracks=[MidiWriter.create_track_from_note_events("Lead", note_events, program=0, channel=0)],
        ticks_per_beat=480,
        tempo=108,
        time_signature=(4, 4),
    )


def _build_polyphonic_single_track_piano() -> bytes:
    note_events = []
    absolute_tick = 0
    chord_patterns = [
        (60, 64, 67, 72),
        (62, 65, 69, 74),
        (64, 67, 71, 76),
        (65, 69, 72, 77),
    ] * 3
    for chord in chord_patterns:
        for pitch in chord:
            note_events.append((absolute_tick, absolute_tick + 480, pitch, 60 if pitch < 72 else 74, 0))
        absolute_tick += 480
    return MidiWriter.write_midi(
        tracks=[MidiWriter.create_track_from_note_events("PianoLead", note_events, program=0, channel=0)],
        ticks_per_beat=480,
        tempo=92,
        time_signature=(4, 4),
    )


def _build_generated_samples() -> list[tuple[str, bytes]]:
    return [
        ("generated_ballad_4_4", _build_simple_ballad_4_4()),
        ("generated_compound_6_8", _build_compound_6_8_lilt()),
        ("generated_waltz_3_4", _build_waltz_3_4()),
        ("generated_syncopated_pop_4_4", _build_syncopated_pop_4_4()),
        ("generated_polyphonic_piano_4_4", _build_polyphonic_single_track_piano()),
    ]


def _make_sample_spec(name: str, source_name: str, source_type: str, midi_data: bytes) -> SampleMidiSpec:
    analyzer = MidiAnalysisService()
    result = analyzer.analyze(midi_data)
    candidate = result.melody_candidates[0] if result.melody_candidates else None
    return SampleMidiSpec(
        name=name,
        source_name=source_name,
        source_type=source_type,
        midi_data=midi_data,
        melody_track_index=candidate.track_index if candidate else 0,
        melody_confidence=round(candidate.score, 3) if candidate else 0.0,
        track_count=len(result.tracks),
        ticks_per_beat=result.ticks_per_beat,
        tempo=result.tempo,
        time_signature=result.time_signature,
        total_ticks=result.total_ticks,
    )


def build_sample_midi_specs() -> list[SampleMidiSpec]:
    sample_specs: list[SampleMidiSpec] = []

    for path in sorted(SAMPLE_DIR.glob("*.mid")):
        sample_specs.append(
            _make_sample_spec(
                name=path.stem,
                source_name=path.name,
                source_type="fixture",
                midi_data=path.read_bytes(),
            )
        )

    for name, midi_data in _build_generated_samples():
        sample_specs.append(
            _make_sample_spec(
                name=name,
                source_name=f"{name}.generated",
                source_type="synthetic",
                midi_data=midi_data,
            )
        )

    return sample_specs


def build_arrangement_benchmark_cases() -> list[ArrangementBenchmarkCase]:
    cases: list[ArrangementBenchmarkCase] = []
    profiles = build_arrangement_profiles()
    for sample in build_sample_midi_specs():
        for profile in profiles:
            cases.append(
                ArrangementBenchmarkCase(
                    name=f"{sample.name}__{profile.name}",
                    sample=sample,
                    profile=profile,
                )
            )
    return cases
