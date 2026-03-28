"""
测试 Plan Schema 模型
"""

import pytest
from arranger.plan_schema import (
    UnifiedPlan,
    TransformSpec,
    EnsembleConfig,
    PartSpec,
    MidiSpec,
    HarmonyContext,
    Constraints,
    LockMelodyConfig,
    GuardsConfig,
    OutputConfig,
    MidiOutputConfig,
    ChordInfo,
    ArrangementContext,
    StyleSpecification,
)


class TestUnifiedPlan:
    """测试 UnifiedPlan 模型"""

    def test_create_minimal_plan(self):
        """创建最小化 Plan"""
        plan = UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(type="orchestration"),
            constraints=Constraints(),
            outputs=OutputConfig(),
        )
        assert plan.schema_version == "1.0"
        assert plan.transform.type == "orchestration"

    def test_create_full_plan(self):
        """创建完整 Plan"""
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
                )
            ],
        )

        plan = UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(
                type="orchestration",
                preserve_structure=True,
            ),
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
                guards=GuardsConfig(
                    velocity_caps={"piano": 58},
                    avoid_melody_onsets=True,
                ),
            ),
            outputs=OutputConfig(
                midi=MidiOutputConfig(
                    enabled=True,
                    filename="test.mid",
                )
            ),
        )

        assert plan.schema_version == "1.0"
        assert plan.transform.type == "orchestration"
        assert plan.ensemble.name == "test_ensemble"
        assert len(plan.ensemble.parts) == 1
        assert plan.constraints.lock_melody_events.enabled is True

    def test_transform_types(self):
        """测试 transform 类型（MVP 只支持 orchestration）"""
        # MVP 只支持 orchestration
        plan = UnifiedPlan(
            schema_version="1.0",
            transform=TransformSpec(type="orchestration"),
            constraints=Constraints(),
            outputs=OutputConfig(),
        )
        assert plan.transform.type == "orchestration"


class TestEnsembleConfig:
    """测试 EnsembleConfig 模型"""

    def test_create_ensemble(self):
        """创建乐团配置"""
        ensemble = EnsembleConfig(
            name="string_quartet",
            size="small",
            target_size=4,
            parts=[
                PartSpec(
                    id=f"part{i}",
                    name=f"Part {i}",
                    role="inner_voice",
                    instrument="violin",
                    midi=MidiSpec(channel=i, program=40),
                )
                for i in range(4)
            ],
        )

        assert ensemble.name == "string_quartet"
        assert ensemble.size == "small"
        assert ensemble.target_size == 4
        assert len(ensemble.parts) == 4

    def test_part_roles(self):
        """测试不同的声部角色"""
        valid_roles = [
            "melody",
            "inner_voice",
            "bass",
            "accompaniment",
            "percussion",
            "counter_melody",
            "sustain_support",
            "fanfare",
            "tutti",
            "bass_rhythm",
            "anchor",
            "accent",
        ]

        for role in valid_roles:
            part = PartSpec(
                id="test",
                name="Test",
                role=role,
                instrument="piano",
                midi=MidiSpec(channel=0, program=0),
            )
            assert part.role == role


class TestChordInfo:
    """测试 ChordInfo 模型"""

    def test_create_chord_info(self):
        """创建和弦信息"""
        chord = ChordInfo(
            root=60,  # C4
            third=64,  # E4
            fifth=67,  # G4
            quality="major",
        )

        assert chord.root == 60
        assert chord.third == 64
        assert chord.fifth == 67
        assert chord.quality == "major"

    def test_chord_quality_types(self):
        """测试和弦性质类型"""
        for quality in ["major", "minor", "diminished", "augmented", "unknown"]:
            chord = ChordInfo(
                root=60, third=64, fifth=67, quality=quality
            )
            assert chord.quality == quality


class TestStyleSpecification:
    """测试 StyleSpecification 模型"""

    def test_create_style(self):
        """创建风格规范"""
        style = StyleSpecification(
            era="classical",
            period="high_classical",
            key_characteristics={"cadence": "perfect"},
        )

        assert style.era == "classical"
        assert style.period == "high_classical"
        assert style.key_characteristics["cadence"] == "perfect"

    def test_style_eras(self):
        """测试不同时代"""
        for era in ["baroque", "classical", "romantic", "impressionist", "modern"]:
            style = StyleSpecification(era=era)
            assert style.era == era
