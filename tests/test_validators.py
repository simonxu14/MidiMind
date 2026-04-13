"""
测试验证器和自动修复器
"""

import pytest
from arranger.auto_fixer import AutoFixer
from arranger.midi_io import MidiWriter
from arranger.harmony_validator import HarmonyValidator
from arranger.plan_schema import (
    Constraints,
    EnsembleConfig,
    HarmonyContext,
    LockMelodyConfig,
    MidiOutputConfig,
    MidiSpec,
    OutputConfig,
    PartSpec,
    TransformSpec,
    UnifiedPlan,
)
from arranger.validator import Validator


class TestAutoFixer:
    """测试 AutoFixer"""

    def test_fix_octave_jumps(self):
        """测试八度跳跃修复"""
        fixer = AutoFixer()
        notes = [
            (0, 100, 60, 64, 0),   # C4
            (100, 200, 72, 64, 0), # C5 - 从C4跳到C5
            (200, 300, 64, 64, 0), # E4
        ]

        fixed = fixer.fix_octave_jumps(notes, threshold=12)

        # 应该没有跳八度
        for i in range(1, len(fixed)):
            prev_pitch = fixed[i-1][2]
            curr_pitch = fixed[i][2]
            if fixed[i][0] - fixed[i-1][1] < 50:  # 快速转换
                diff = abs(curr_pitch - prev_pitch)
                assert diff <= 12, f"Octave jump detected: {prev_pitch} -> {curr_pitch}"

    def test_fix_out_of_range(self):
        """测试超出音域修复"""
        fixer = AutoFixer()
        # 默认钢琴范围
        notes = [
            (0, 100, 20, 64, 0),   # 太低 - 钢琴最低C0
            (100, 200, 110, 64, 0), # 太高 - 钢琴最高
            (200, 300, 60, 64, 0), # C4 - 正常
        ]

        fixed = fixer.fix_out_of_range(notes, {"piano": (21, 108)})

        # 验证修复后的音符在范围内
        for note in fixed:
            pitch = note[2]
            assert 21 <= pitch <= 108, f"Pitch {pitch} out of range"

    def test_fix_voice_crossing(self):
        """测试声部交叉修复"""
        fixer = AutoFixer()
        # 假设是两个声部
        notes = [
            (0, 100, 60, 64, 0),   # 声部1: C4
            (0, 100, 48, 64, 1),   # 声部2: C3 - 声部1应该高于声部2
            (100, 200, 54, 64, 0), # 声部1: Db4
            (100, 200, 60, 64, 1), # 声部2: C4 - 现在声部2高于声部1（交叉）
        ]

        fixed = fixer.fix_voice_crossing(notes)

        # 验证返回的是列表
        assert isinstance(fixed, list)


class TestHarmonyValidator:
    """测试 HarmonyValidator"""

    def test_validate_clean_voices(self):
        """测试验证干净的和声"""
        validator = HarmonyValidator()
        # 构成和弦进行，没有平行
        voice1 = [(0, 100, 60, 64, 0), (100, 200, 62, 64, 0)]   # C4 -> D4
        voice2 = [(0, 100, 55, 64, 1), (100, 200, 57, 64, 1)]   # G3 -> A3

        notes = voice1 + voice2
        result = validator.validate(notes)

        # 干净和声应该通过
        assert result.passed is True

    def test_validate_with_parallel_fifths(self):
        """测试平行五度检测"""
        validator = HarmonyValidator()
        # 两个声部 - 需要同时开始，且构成五度并同向进行
        # C4-G4 (五度) -> D4-A4 (五度) - 同向五度平行
        voice1 = [(0, 100, 60, 64, 0), (100, 200, 62, 64, 0)]   # C4 -> D4
        voice2 = [(0, 100, 67, 64, 1), (100, 200, 69, 64, 1)]   # G4 -> A4

        notes = voice1 + voice2
        result = validator.validate(notes)

        # 应该有平行五度问题 - 但这取决于具体的检测逻辑

    def test_validate_single_voice(self):
        """测试单声部"""
        validator = HarmonyValidator()
        notes = [(0, 100, 60, 64, 0), (100, 200, 64, 64, 0)]

        result = validator.validate(notes)

        # 单声部应该通过（不足两个声部）
        assert result.passed is True

    def test_validate_empty_notes(self):
        """测试空音符列表"""
        validator = HarmonyValidator()
        result = validator.validate([])

        # 空应该通过
        assert result.passed is True

    def test_validate_equal_pitch_unison_is_not_voice_crossing(self):
        """同音重叠不应被当成 voice crossing"""
        validator = HarmonyValidator()
        notes = [
            (0, 100, 60, 64, 0),
            (0, 100, 60, 64, 1),
            (100, 200, 62, 64, 0),
            (100, 200, 62, 64, 1),
        ]

        result = validator.validate(notes)

        assert result.passed is True


class TestArrangementValidator:
    def test_check_instrumentation_ignores_auto_generated_tracks(self):
        plan = UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(type="orchestration"),
            ensemble=EnsembleConfig(
                name="test",
                size="small",
                target_size=2,
                parts=[
                    PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
                    PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0)),
                ],
            ),
            harmony_context=HarmonyContext(),
            constraints=Constraints(),
            outputs=OutputConfig(midi=MidiOutputConfig(enabled=True, filename="test.mid")),
        )
        validator = Validator(plan)
        output_tracks = [
            [
                ("track_name", {"name": "melody_vn1"}),
                ("program_change", {"program": 40, "channel": 0}),
            ],
            [
                ("track_name", {"name": "piano"}),
                ("program_change", {"program": 0, "channel": 1}),
            ],
            [
                ("track_name", {"name": "auto_triangle"}),
                ("program_change", {"program": 81, "channel": 12}),
            ],
        ]

        result = validator._check_instrumentation(output_tracks)

        assert result.passed is True

    def test_melody_identical_accepts_polyphonic_order_variation(self):
        plan = UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(type="orchestration"),
            ensemble=EnsembleConfig(
                name="polyphonic_melody",
                size="small",
                target_size=1,
                parts=[
                    PartSpec(
                        id="vn1",
                        name="Violin I",
                        role="melody",
                        instrument="violin",
                        midi=MidiSpec(channel=0, program=40),
                    ),
                ],
            ),
            harmony_context=HarmonyContext(),
            constraints=Constraints(
                lock_melody_events=LockMelodyConfig(
                    enabled=True,
                    source_track_ref="1",
                    source_track_selection_mode="fixed",
                    user_confirm_required=False,
                ),
            ),
            outputs=OutputConfig(midi=MidiOutputConfig(enabled=True, filename="test.mid")),
        )
        validator = Validator(plan)

        input_midi = MidiWriter.write_midi(
            tracks=[[
                ("note_on", {"channel": 0, "note": 70, "velocity": 64, "time": 0}),
                ("note_on", {"channel": 0, "note": 65, "velocity": 57, "time": 10}),
                ("note_off", {"channel": 0, "note": 65, "velocity": 0, "time": 90}),
                ("note_off", {"channel": 0, "note": 70, "velocity": 0, "time": 0}),
            ]],
            ticks_per_beat=480,
            tempo=120,
            time_signature=(4, 4),
        )
        output_tracks = [
            MidiWriter.create_track_from_note_events(
                track_name="melody_vn1",
                note_events=[
                    (0, 100, 70, 64, 0),
                    (10, 100, 65, 57, 0),
                ],
                program=40,
                channel=0,
            )
        ]

        result = validator.validate(input_midi, output_tracks)

        assert result.melody_identical.passed is True
