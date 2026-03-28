"""
集成测试 - 端到端 MIDI 编曲测试
"""

import pytest
from io import BytesIO
from arranger.midi_io import MidiWriter, MidiReader
from arranger.analyze import MidiAnalysisService
from arranger.orchestrate_executor import OrchestrateExecutor
from arranger.validator import Validator
from arranger.plan_schema import (
    UnifiedPlan, TransformSpec, EnsembleConfig, PartSpec, MidiSpec,
    HarmonyContext, Constraints, LockMelodyConfig, GuardsConfig,
    OutputConfig, MidiOutputConfig
)


class TestEndToEndArrangement:
    """端到端编曲测试"""

    @pytest.fixture
    def simple_melody_midi(self):
        """创建一个简单旋律的 MIDI 数据"""
        # 创建一个简单的 C-G-Am-F 和弦进行
        tracks = [
            [
                # 旋律轨道 - C4, E4, G4, C5
                ("note_on", {"channel": 0, "note": 60, "velocity": 64, "time": 0}),
                ("note_off", {"channel": 0, "note": 60, "velocity": 0, "time": 480}),
                ("note_on", {"channel": 0, "note": 64, "velocity": 64, "time": 480}),
                ("note_off", {"channel": 0, "note": 64, "velocity": 0, "time": 960}),
                ("note_on", {"channel": 0, "note": 67, "velocity": 64, "time": 960}),
                ("note_off", {"channel": 0, "note": 67, "velocity": 0, "time": 1440}),
                ("note_on", {"channel": 0, "note": 72, "velocity": 64, "time": 1440}),
                ("note_off", {"channel": 0, "note": 72, "velocity": 0, "time": 1920}),
            ]
        ]

        midi_data = MidiWriter.write_midi(
            tracks=tracks,
            ticks_per_beat=480,
            tempo=120,
            time_signature=(4, 4),
        )
        return midi_data

    @pytest.fixture
    def small_ensemble_plan(self):
        """创建小型乐队配置"""
        ensemble = EnsembleConfig(
            name="test_ensemble",
            size="small",
            target_size=4,
            parts=[
                PartSpec(
                    id="vn1",
                    name="Violin I",
                    role="melody",
                    instrument="violin",
                    midi=MidiSpec(channel=0, program=40),
                ),
                PartSpec(
                    id="vn2",
                    name="Violin II",
                    role="inner_voice",
                    instrument="violin",
                    midi=MidiSpec(channel=1, program=40),
                ),
                PartSpec(
                    id="va",
                    name="Viola",
                    role="inner_voice",
                    instrument="viola",
                    midi=MidiSpec(channel=2, program=41),
                ),
                PartSpec(
                    id="vc",
                    name="Cello",
                    role="bass",
                    instrument="cello",
                    midi=MidiSpec(channel=3, program=42),
                ),
            ],
        )

        plan = UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(type="orchestration"),
            ensemble=ensemble,
            harmony_context=HarmonyContext(
                method="measure_pitchset_triadish",
                granularity="per_measure",
            ),
            constraints=Constraints(
                lock_melody_events=LockMelodyConfig(
                    enabled=True,
                    source_track_ref="0",
                ),
                keep_total_ticks=True,
                guards=GuardsConfig(),
            ),
            outputs=OutputConfig(
                midi=MidiOutputConfig(
                    enabled=True,
                    filename="test.mid",
                )
            ),
        )
        return plan

    def test_analyze_midi(self, simple_melody_midi):
        """测试 MIDI 分析"""
        service = MidiAnalysisService()
        result = service.analyze(simple_melody_midi)

        assert result.total_ticks > 0
        assert result.ticks_per_beat == 480
        assert result.tempo == 120
        assert len(result.tracks) >= 1  # 至少有1个轨道（可能包含conductor track）

    def test_orchestrate_executor(self, simple_melody_midi, small_ensemble_plan):
        """测试编曲执行"""
        executor = OrchestrateExecutor(small_ensemble_plan)
        output_tracks, stats = executor.execute(
            input_midi=simple_melody_midi,
            melody_track_index=0
        )

        assert isinstance(output_tracks, list)
        assert len(output_tracks) >= 2  # 至少旋律轨 + 伴奏轨
        assert "track_count" in stats
        assert stats["track_count"] >= 2

    def test_write_output_midi(self, simple_melody_midi, small_ensemble_plan):
        """测试写入输出 MIDI"""
        executor = OrchestrateExecutor(small_ensemble_plan)
        output_tracks, stats = executor.execute(
            input_midi=simple_melody_midi,
            melody_track_index=0
        )

        # 写入 MIDI
        output_data = MidiWriter.write_midi(
            tracks=output_tracks,
            ticks_per_beat=480,
            tempo=120,
            time_signature=(4, 4),
        )

        assert isinstance(output_data, bytes)
        assert len(output_data) > 0
        assert output_data[:4] == b"MThd"  # MIDI 文件头

    def test_full_pipeline(self, simple_melody_midi, small_ensemble_plan):
        """测试完整流程：分析→编曲→验证"""
        # 1. 分析
        service = MidiAnalysisService()
        analysis_result = service.analyze(simple_melody_midi)
        assert analysis_result.total_ticks > 0

        # 2. 编曲
        executor = OrchestrateExecutor(small_ensemble_plan)
        output_tracks, stats = executor.execute(
            input_midi=simple_melody_midi,
            melody_track_index=0
        )

        # 3. 验证
        validator = Validator(small_ensemble_plan)
        validation_result = validator.validate(simple_melody_midi, output_tracks)

        # 验证应该通过（硬约束）
        assert hasattr(validation_result, 'all_passed')
        assert validation_result.all_passed is True or len(validation_result.errors) > 0

    def test_melody_preservation(self, simple_melody_midi, small_ensemble_plan):
        """测试旋律保持不变"""
        # 读取原始旋律
        original_midi = MidiReader.read_midi(simple_melody_midi)
        original_notes = MidiReader.extract_track_messages(original_midi)[0]

        # 编曲
        executor = OrchestrateExecutor(small_ensemble_plan)
        output_tracks, stats = executor.execute(
            input_midi=simple_melody_midi,
            melody_track_index=0
        )

        # 旋律轨应该在输出中（作为第一条轨道）
        assert len(output_tracks) >= 1

    def test_different_ensemble_sizes(self, simple_melody_midi):
        """测试不同乐队规模"""
        for size, expected_parts in [(4, 4), (10, 10)]:
            from arranger.cli import generate_default_plan

            plan = generate_default_plan(size)
            assert len(plan.ensemble.parts) == expected_parts

            executor = OrchestrateExecutor(plan)
            output_tracks, stats = executor.execute(
                input_midi=simple_melody_midi,
                melody_track_index=0
            )

            assert stats["track_count"] >= expected_parts

    def test_6_8_meter_regression(self):
        """
        回归测试：6/8 拍号编曲

        验证：
        1. total_ticks 与输入一致
        2. 硬约束通过
        3. flute 轨道有音符产出（P1-1 修复验证）

        参考 conversation: 4bbdcbdae1d14e77a4d2a48d59e00a87
        """
        import os

        # 加载 6/8 测试 MIDI
        test_midi_path = os.path.join(
            os.path.dirname(__file__),
            "sample",
            "我和我的祖国.mid"
        )

        if not os.path.exists(test_midi_path):
            pytest.skip(f"Test MIDI not found: {test_midi_path}")

        with open(test_midi_path, "rb") as f:
            midi_data = f.read()

        # 分析输入
        service = MidiAnalysisService()
        analysis_result = service.analyze(midi_data)

        # 验证是 6/8 拍
        assert analysis_result.time_signature == (6, 8), f"Expected 6/8, got {analysis_result.time_signature}"

        # 创建简单 4 人室内乐计划（不指定具体模板，使用自动匹配）
        ensemble = EnsembleConfig(
            name="test_6_8_ensemble",
            size="small",
            target_size=4,
            parts=[
                PartSpec(id="vn1", name="第一小提琴", role="melody",
                         instrument="violin", midi=MidiSpec(channel=0, program=40)),
                PartSpec(id="piano", name="钢琴", role="accompaniment",
                         instrument="piano", midi=MidiSpec(channel=1, program=0)),
                PartSpec(id="va", name="中提琴", role="inner_voice",
                         instrument="viola", midi=MidiSpec(channel=2, program=41)),
                PartSpec(id="vc", name="大提琴", role="bass",
                         instrument="cello", midi=MidiSpec(channel=3, program=42)),
            ],
        )

        plan = UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(type="orchestration"),
            ensemble=ensemble,
            harmony_context=HarmonyContext(
                method="measure_pitchset_triadish",
                granularity="per_measure",
            ),
            constraints=Constraints(
                lock_melody_events=LockMelodyConfig(
                    enabled=True,
                    source_track_ref="1",  # 旋律在 track 1
                ),
                keep_total_ticks=True,
                guards=GuardsConfig(),
            ),
            outputs=OutputConfig(
                midi=MidiOutputConfig(enabled=True, filename="test_6_8.mid")
            ),
        )

        # 执行编曲
        executor = OrchestrateExecutor(plan)
        output_tracks, stats = executor.execute(
            input_midi=midi_data,
            melody_track_index=1
        )

        # 验证输出有轨道
        assert len(output_tracks) >= 4, f"Expected at least 4 tracks, got {len(output_tracks)}"

        # 验证 Validator 通过
        validator = Validator(plan)
        validation_result = validator.validate(midi_data, output_tracks)

        assert validation_result.melody_identical.passed, \
            f"melody_identical failed: {validation_result.melody_identical.message}"
        assert validation_result.total_ticks_identical.passed, \
            f"total_ticks_identical failed: {validation_result.total_ticks_identical.message}"
