import random

from arranger.plan_schema import (
    ArrangementConfig,
    ArrangementContext,
    ChordInfo,
    Constraints,
    EnsembleConfig,
    GuardsConfig,
    HarmonyContext,
    MidiOutputConfig,
    MidiSpec,
    OutputConfig,
    PartSpec,
    PercussionPolicy,
    PianoTemplatePool,
    TransformSpec,
    UnifiedPlan,
)
from arranger.services.generation import generate_part_notes
from arranger.services.percussion import auto_add_percussion
from arranger.services.reporting import generate_arrangement_report, get_instrument_key_for_track
from arranger.templates.registry import get_registry

from arranger.auto_fixer import AutoFixer


def make_plan(parts, arrangement=None, guards=None):
    return UnifiedPlan(
        schema_version="1.0",
        transform=TransformSpec(type="orchestration"),
        ensemble=EnsembleConfig(name="test", size="small", target_size=len(parts), parts=parts),
        harmony_context=HarmonyContext(),
        arrangement=arrangement or ArrangementConfig(),
        constraints=Constraints(guards=guards or GuardsConfig()),
        outputs=OutputConfig(midi=MidiOutputConfig(enabled=True, filename="test.mid")),
    )


def make_context():
    return ArrangementContext(
        measure_len=1920,
        ticks_per_beat=480,
        chord_per_measure={
            0: ChordInfo(root=60, third=64, fifth=67, quality="major"),
            1: ChordInfo(root=62, third=65, fifth=69, quality="minor"),
        },
        section_modes={0: "A", 1: "A"},
        current_mode="A",
        melody_onsets=[0, 960],
        melody_notes=[(0, 480, 72, 90, 0)],
        melody_range=(72, 84),
        tempo=120,
        style="general",
        register_targets={"piano": "middle", "va": "middle", "vc": "low"},
        velocity_caps={"pf": 52, "va": 56, "vc": 62},
    )


class TestGenerationService:
    def test_generate_part_notes_auto_selects_regular_template_without_pool(self):
        part = PartSpec(
            id="va",
            name="Viola",
            role="inner_voice",
            instrument="viola",
            midi=MidiSpec(channel=2, program=41),
        )
        plan = make_plan(
            [
                PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
                part,
            ],
            arrangement=None,
        )
        context = make_context()
        report_stats = {"template_per_part": {}, "template_per_measure": {}}

        notes = generate_part_notes(part, context, plan, get_registry(), report_stats)

        assert notes
        assert "va#m0" in report_stats["template_per_measure"]
        assert "va#m1" in report_stats["template_per_measure"]

    def test_generate_part_notes_falls_back_to_default_when_template_missing(self):
        part = PartSpec(
            id="mystery",
            name="Mystery",
            role="accompaniment",
            instrument="glass_harmonica",
            midi=MidiSpec(channel=5, program=0),
        )
        plan = make_plan(
            [
                PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
                part,
            ]
        )
        context = make_context()
        report_stats = {"template_per_part": {}, "template_per_measure": {}}

        notes = generate_part_notes(part, context, plan, get_registry(), report_stats)

        assert len(notes) == 6
        assert all(note[4] == 5 for note in notes)
        assert report_stats["template_per_part"] == {}


class TestPercussionService:
    def test_auto_add_percussion_is_disabled_by_default(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
        ]
        plan = make_plan(parts, arrangement=ArrangementConfig(percussion=PercussionPolicy(phrase_block_measures=1)))
        context = make_context()
        report_stats = {"percussion_hits": {"timpani": 0, "triangle": 0}}

        tracks = auto_add_percussion({}, context, plan, plan.ensemble, report_stats)

        assert tracks == {}
        assert report_stats["percussion_hits"] == {"timpani": 0, "triangle": 0}

    def test_auto_add_percussion_adds_generated_tracks(self):
        random.seed(123)
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
        ]
        plan = make_plan(
            parts,
            arrangement=ArrangementConfig(
                percussion=PercussionPolicy(phrase_block_measures=1, auto_add_when_absent=True)
            ),
        )
        context = make_context()
        report_stats = {"percussion_hits": {"timpani": 0, "triangle": 0}}

        tracks = auto_add_percussion({}, context, plan, plan.ensemble, report_stats)

        assert "auto_timpani" in tracks
        assert "auto_triangle" in tracks
        assert all(45 <= note[2] <= 53 for note in tracks["auto_timpani"])
        assert all(note[2] == 81 and note[4] == 9 for note in tracks["auto_triangle"])
        assert report_stats["percussion_hits"]["timpani"] == len(tracks["auto_timpani"])
        assert report_stats["percussion_hits"]["triangle"] == len(tracks["auto_triangle"])

    def test_auto_add_percussion_skips_existing_percussion_part(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="timp", name="Timpani", role="percussion", instrument="timpani", midi=MidiSpec(channel=9, program=47)),
        ]
        plan = make_plan(
            parts,
            arrangement=ArrangementConfig(
                percussion=PercussionPolicy(auto_add_when_absent=True)
            ),
        )
        context = make_context()
        report_stats = {"percussion_hits": {"timpani": 0, "triangle": 0}}

        tracks = auto_add_percussion({}, context, plan, plan.ensemble, report_stats)

        assert "auto_timpani" not in tracks


class TestReportingService:
    def test_get_instrument_key_for_track_uses_ensemble_and_fallback(self):
        parts = [
            PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
            PartSpec(id="va", name="Viola", role="inner_voice", instrument="viola", midi=MidiSpec(channel=2, program=41)),
        ]
        ensemble = EnsembleConfig(name="test", size="small", target_size=2, parts=parts)

        assert get_instrument_key_for_track("va", ensemble) == "va"
        assert get_instrument_key_for_track("pf_layer", ensemble) == "pf"

    def test_generate_arrangement_report_collects_template_and_percussion_stats(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
        ]
        ensemble = EnsembleConfig(name="test", size="small", target_size=2, parts=parts)
        context = make_context()
        accompaniment_tracks = {
            "piano": [
                (0, 480, 60, 50, 1),
                (960, 1440, 64, 48, 1),
            ],
            "auto_triangle": [(0, 60, 81, 25, 9)],
        }
        output_tracks = [
            [("track_name", {"name": "auto_triangle"}), ("note_on", {"note": 81, "velocity": 25, "channel": 9})],
            [("track_name", {"name": "piano"}), ("note_on", {"note": 60, "velocity": 50, "channel": 1})],
        ]
        report_stats = {
            "template_per_measure": {"piano#m0": "broken_8ths", "piano#m1": "broken_8ths"},
            "template_per_part": {"piano": "broken_8ths"},
            "onset_avoidance_hits": 1,
            "onset_scale_velocity_hits": 1,
            "onset_delay_hits": 0,
            "onset_drop_hits": 0,
            "exact_onset_collisions_by_part": {"piano": 1},
            "velocity_cap_hits": 2,
            "percussion_hits": {"timpani": 0, "triangle": 1},
            "fixes_applied": ["voice_crossing"],
        }

        report = generate_arrangement_report(context, accompaniment_tracks, output_tracks, ensemble, report_stats)

        assert report["template_usage"]["piano"] == "broken_8ths"
        assert report["piano_template_per_measure"]["measure_0"]["template"] == "broken_8ths"
        assert report["piano_template_per_measure"]["measure_0"]["note_count"] == 2
        assert report["guards_stats"]["velocity_cap_hits"] == 2
        assert report["percussion_hits"]["triangle"] == 1
        assert report["fixes_applied"] == ["voice_crossing"]
from arranger.plan_schema import CCConfig
from arranger.services.output_builder import add_cc_messages_to_track, build_output_tracks


class TestOutputBuilderService:
    def test_add_cc_messages_to_track_inserts_before_first_note(self):
        messages = [
            ("track_name", {"name": "piano"}),
            ("program_change", {"program": 0, "channel": 1, "time": 0}),
            ("note_on", {"note": 60, "velocity": 50, "channel": 1, "time": 0}),
        ]

        result = add_cc_messages_to_track(messages, CCConfig(cc7=100, cc11=90), 1)

        assert result[2][0] == "control_change"
        assert result[2][1]["control"] == 7
        assert result[3][1]["control"] == 11
        assert result[4][0] == "note_on"

    def test_build_output_tracks_creates_melody_part_and_auto_percussion_tracks(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
        ]
        ensemble = EnsembleConfig(name="test", size="small", target_size=2, parts=parts)
        output_tracks = build_output_tracks(
            ensemble,
            [(0, 480, 72, 90, 0)],
            {
                "piano": [(0, 480, 60, 50, 1)],
                "auto_triangle": [(0, 60, 81, 25, 9)],
            },
            CCConfig(cc7=100, cc11=90),
            CCConfig(cc91=25, cc11=80),
        )

        track_names = []
        triangle_cc11_values = []
        for track in output_tracks:
            name = None
            for msg_type, params in track:
                if msg_type == "track_name":
                    name = params["name"]
                    track_names.append(name)
                if name == "auto_triangle" and msg_type == "control_change" and params["control"] == 11:
                    triangle_cc11_values.append(params["value"])

        assert "melody_vn1" in track_names
        assert "piano" in track_names
        assert "auto_triangle" in track_names
        assert triangle_cc11_values == []
from arranger.services.autofix_pipeline import apply_autofix_pipeline, build_channel_ranges, regroup_notes_by_channel


class TestAutofixPipelineService:
    def test_build_channel_ranges_uses_instrument_defaults_and_piano_fallback(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=3, program=42)),
            PartSpec(id="mystery", name="Mystery", role="accompaniment", instrument="unknown", midi=MidiSpec(channel=5, program=0)),
        ]
        ensemble = EnsembleConfig(name="test", size="small", target_size=3, parts=parts)
        instrument_ranges = {"cello": (36, 72), "piano": (21, 108)}

        channel_ranges = build_channel_ranges(ensemble, instrument_ranges)

        assert channel_ranges == {3: (36, 72), 5: (21, 108)}

    def test_regroup_notes_by_channel_groups_notes(self):
        notes = [(0, 120, 60, 50, 1), (120, 240, 64, 55, 1), (0, 240, 48, 60, 2)]

        grouped = regroup_notes_by_channel(notes)

        assert len(grouped[1]) == 2
        assert len(grouped[2]) == 1

    def test_apply_autofix_pipeline_preserves_tracks_and_updates_fixes(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=3, program=42)),
        ]
        ensemble = EnsembleConfig(name="test", size="small", target_size=2, parts=parts)
        plan = make_plan(parts)
        context = make_context()
        accompaniment_tracks = {"vc": [(0, 480, 48, 60, 3)]}
        report_stats = {"fixes_applied": []}
        instrument_ranges = {"cello": (36, 72), "piano": (21, 108)}

        updated_tracks = apply_autofix_pipeline(
            accompaniment_tracks,
            ensemble,
            context,
            plan,
            [(0, 480, 72, 90, 0)],
            instrument_ranges,
            report_stats,
        )

        assert "vc" in updated_tracks
        assert updated_tracks["vc"]
        assert report_stats["fixes_applied"] == []

    def test_apply_autofix_pipeline_preserves_note_duration_and_velocity(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
            PartSpec(id="va", name="Viola", role="inner_voice", instrument="viola", midi=MidiSpec(channel=2, program=41)),
        ]
        ensemble = EnsembleConfig(name="test", size="small", target_size=3, parts=parts)
        plan = make_plan(parts)
        context = make_context()
        accompaniment_tracks = {
            "piano": [(0, 360, 60, 44, 1)],
            "va": [(0, 420, 67, 38, 2)],
        }
        report_stats = {"fixes_applied": []}
        instrument_ranges = {"piano": (21, 108), "viola": (48, 81)}

        updated_tracks = apply_autofix_pipeline(
            accompaniment_tracks,
            ensemble,
            context,
            plan,
            [(0, 480, 72, 90, 0)],
            instrument_ranges,
            report_stats,
        )

        assert updated_tracks["piano"][0][1] == 360
        assert updated_tracks["piano"][0][3] == 44
        assert updated_tracks["va"][0][1] == 420
        assert updated_tracks["va"][0][3] == 38

    def test_apply_autofix_pipeline_keeps_channels_isolated_per_part(self):
        parts = [
            PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
            PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
            PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=3, program=42)),
        ]
        ensemble = EnsembleConfig(name="test", size="small", target_size=3, parts=parts)
        plan = make_plan(parts)
        context = make_context()
        accompaniment_tracks = {
            "piano": [(0, 240, 60, 45, 1), (240, 480, 95, 45, 1)],
            "vc": [(0, 240, 84, 52, 3), (240, 480, 36, 52, 3)],
        }
        report_stats = {"fixes_applied": []}
        instrument_ranges = {"piano": (21, 108), "cello": (36, 72)}

        updated_tracks = apply_autofix_pipeline(
            accompaniment_tracks,
            ensemble,
            context,
            plan,
            [(0, 480, 72, 90, 0)],
            instrument_ranges,
            report_stats,
        )

        assert all(note[4] == 1 for note in updated_tracks["piano"])
        assert all(note[4] == 3 for note in updated_tracks["vc"])
        assert len(updated_tracks["piano"]) == len(accompaniment_tracks["piano"])
        assert len(updated_tracks["vc"]) == len(accompaniment_tracks["vc"])


from arranger.services.executor_state import init_report_stats


class TestAutoFixerInvariants:
    def test_fix_octave_jumps_multi_channel_preserves_duration_velocity_and_channel(self):
        fixer = AutoFixer()
        notes = [
            (0, 300, 40, 55, 1),
            (240, 600, 88, 47, 1),
            (0, 360, 52, 62, 2),
            (240, 720, 79, 41, 2),
        ]

        fixed = fixer.fix_octave_jumps(notes, threshold=12)

        assert len(fixed) == len(notes)
        for original, updated in zip(notes, fixed):
            assert updated[0] == original[0]
            assert updated[1] == original[1]
            assert updated[3] == original[3]
            assert updated[4] == original[4]

        by_channel = {}
        for start, end, pitch, velocity, channel in fixed:
            by_channel.setdefault(channel, []).append((start, end, pitch, velocity, channel))

        for channel_notes in by_channel.values():
            for prev, curr in zip(channel_notes, channel_notes[1:]):
                assert abs(curr[2] - prev[2]) <= 12

    def test_fix_all_keeps_percussion_notes_unchanged(self):
        fixer = AutoFixer()
        notes = [
            (0, 240, 81, 24, 9),
            (480, 720, 81, 31, 9),
            (0, 480, 45, 60, 3),
        ]

        fixed = fixer.fix_all(notes, instrument_ranges={3: (36, 72), 9: (0, 127)}, skip_channels=[9])

        percussion_original = [note for note in notes if note[4] == 9]
        percussion_fixed = [note for note in fixed if note[4] == 9]
        assert percussion_fixed == percussion_original

    def test_fix_voice_crossing_respects_explicit_voice_order(self):
        notes = [
            (0, 480, 70, 50, 1),
            (0, 480, 60, 48, 2),
        ]

        fixed_default = AutoFixer().fix_voice_crossing(notes, skip_channels=[9])
        fixed_ordered = AutoFixer().fix_voice_crossing(notes, skip_channels=[9], voice_order=[2, 1])

        assert fixed_default[1][2] == 72
        assert fixed_ordered == notes

    def test_fix_all_preserves_note_count_for_non_skip_channels(self):
        fixer = AutoFixer()
        notes = [
            (0, 240, 24, 58, 3),
            (240, 480, 96, 51, 3),
            (0, 240, 50, 44, 2),
            (240, 480, 49, 46, 2),
        ]

        fixed = fixer.fix_all(notes, instrument_ranges={2: (48, 81), 3: (36, 72)}, skip_channels=[9], voice_order=[3, 2])

        original_non_skip = [note for note in notes if note[4] != 9]
        fixed_non_skip = [note for note in fixed if note[4] != 9]
        assert len(fixed_non_skip) == len(original_non_skip)

    def test_fix_all_never_generates_non_positive_note_durations(self):
        fixer = AutoFixer()
        notes = [
            (0, 360, 24, 58, 3),
            (360, 840, 96, 51, 3),
            (0, 420, 50, 44, 2),
            (360, 900, 53, 46, 2),
        ]

        fixed = fixer.fix_all(notes, instrument_ranges={2: (48, 81), 3: (36, 72)}, skip_channels=[9], voice_order=[3, 2])

        assert len(fixed) == len(notes)
        assert all(end > start for start, end, pitch, velocity, channel in fixed)


class TestExecutorStateService:
    def test_init_report_stats_returns_expected_shape(self):
        report_stats = init_report_stats()

        assert report_stats["template_per_part"] == {}
        assert report_stats["template_per_measure"] == {}
        assert report_stats["percussion_hits"] == {"timpani": 0, "triangle": 0}
        assert report_stats["fixes_applied"] == []
        assert "section_modes" not in report_stats
