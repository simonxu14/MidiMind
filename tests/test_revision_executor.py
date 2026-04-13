from types import SimpleNamespace

from arranger.plan_schema import (
    Constraints,
    EnsembleConfig,
    HarmonyContext,
    MidiOutputConfig,
    MidiSpec,
    OutputConfig,
    PartSpec,
    RevisionIntent,
    TransformSpec,
    UnifiedPlan,
)
from arranger.revision_executor import RevisionExecutor


def make_plan(parts):
    return UnifiedPlan(
        schema_version="1.0",
        transform=TransformSpec(type="orchestration"),
        ensemble=EnsembleConfig(name="test", size="small", target_size=len(parts), parts=parts),
        harmony_context=HarmonyContext(),
        constraints=Constraints(),
        outputs=OutputConfig(midi=MidiOutputConfig(enabled=True, filename="test.mid")),
    )


def test_apply_add_revision_accepts_plan_with_new_part_only():
    base_plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=1, program=42)),
    ])
    revised_plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=1, program=42)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=2, program=0)),
    ])

    result = RevisionExecutor().apply_revision(
        base_plan=base_plan,
        revision_intent=RevisionIntent(is_revision=True, revision_type="add", target_part_id=None, instruction="加一个钢琴"),
        user_instruction="加一个钢琴",
        llm_planner=SimpleNamespace(
            apply_revision_for_add=lambda **kwargs: revised_plan,
        ),
    )

    assert result.success is True
    assert result.modified_parts == ["piano"]


def test_apply_add_revision_rejects_changes_to_existing_parts():
    base_plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=1, program=42)),
    ])
    revised_plan = make_plan([
        PartSpec(id="vn1", name="Violin Solo", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="vc", name="Cello", role="bass", instrument="cello", midi=MidiSpec(channel=1, program=42)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=2, program=0)),
    ])

    result = RevisionExecutor().apply_revision(
        base_plan=base_plan,
        revision_intent=RevisionIntent(is_revision=True, revision_type="add", target_part_id=None, instruction="加一个钢琴"),
        user_instruction="加一个钢琴",
        llm_planner=SimpleNamespace(
            apply_revision_for_add=lambda **kwargs: revised_plan,
        ),
    )

    assert result.success is False
    assert result.message == "新增声部不应修改已有声部: vn1"
    assert result.revised_plan == base_plan


def test_apply_modify_revision_accepts_target_only_change():
    base_plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0), template_params={"density": 0.5}),
    ])
    revised_plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0), template_params={"density": 0.9}),
    ])

    result = RevisionExecutor().apply_revision(
        base_plan=base_plan,
        revision_intent=RevisionIntent(is_revision=True, revision_type="modify", target_part_id="piano", instruction="把钢琴写密一点"),
        user_instruction="把钢琴写密一点",
        llm_planner=SimpleNamespace(
            apply_revision_for_modify=lambda **kwargs: revised_plan,
        ),
    )

    assert result.success is True
    assert result.modified_parts == ["piano"]


def test_apply_modify_revision_rejects_changes_to_non_target_parts():
    base_plan = make_plan([
        PartSpec(id="vn1", name="Violin I", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0), template_params={"density": 0.5}),
    ])
    revised_plan = make_plan([
        PartSpec(id="vn1", name="Violin Solo", role="melody", instrument="violin", midi=MidiSpec(channel=0, program=40)),
        PartSpec(id="piano", name="Piano", role="accompaniment", instrument="piano", midi=MidiSpec(channel=1, program=0), template_params={"density": 0.9}),
    ])

    result = RevisionExecutor().apply_revision(
        base_plan=base_plan,
        revision_intent=RevisionIntent(is_revision=True, revision_type="modify", target_part_id="piano", instruction="把钢琴写密一点"),
        user_instruction="把钢琴写密一点",
        llm_planner=SimpleNamespace(
            apply_revision_for_modify=lambda **kwargs: revised_plan,
        ),
    )

    assert result.success is False
    assert result.message == "修改声部只应影响目标声部，实际变更: vn1, piano"
    assert result.revised_plan == base_plan
