from types import SimpleNamespace

import pytest

from arranger.llm_planner import LLMPlanner
from arranger.plan_schema import MidiSpec, PartSpec, RevisionIntent
from arranger.revision_executor import RevisionExecutor
from tests.revision_benchmark_cases import REVISION_BENCHMARK_CASES
from tests.revision_benchmark_runner import (
    make_base_plan,
    make_plan,
    run_revision_workflow_case,
)


WORKFLOW_CASES = [
    case
    for case in REVISION_BENCHMARK_CASES
    if case.expected_revision and case.expected_part_ids is not None
]


@pytest.mark.parametrize(
    "case",
    WORKFLOW_CASES,
    ids=[case.name for case in WORKFLOW_CASES],
)
def test_revision_workflow_benchmark_cases(case):
    summary = run_revision_workflow_case(case)

    assert summary["passed"] is True
    assert summary["success"] is True
    assert summary["modified_parts"] == case.expected_modified_parts
    assert summary["part_ids"] == case.expected_part_ids
    assert summary["lint_passed"] is True
    assert summary["lint_warning_count"] == 0


def test_revision_workflow_benchmark_rejects_modify_plan_that_touches_other_parts(monkeypatch):
    base_plan = make_base_plan()
    planner = LLMPlanner(api_key="test-key")
    executor = RevisionExecutor()

    monkeypatch.setattr(planner, "_call_llm", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm unavailable")))

    intent = planner.analyze_revision_intent("把钢琴写密一点", base_plan)
    assert intent.revision_type == "modify"
    assert intent.target_part_id == "piano"

    invalid_revised_plan = make_plan([
        PartSpec(
            id="vn1",
            name="Violin Solo",
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
            template_params={"density": 0.9},
        ),
        base_plan.ensemble.parts[2],
    ])

    result = executor.apply_revision(
        base_plan=base_plan,
        revision_intent=intent,
        user_instruction="把钢琴写密一点",
        llm_planner=SimpleNamespace(
            apply_revision_for_modify=lambda **kwargs: invalid_revised_plan,
        ),
    )

    assert result.success is False
    assert result.message == "修改声部只应影响目标声部，实际变更: vn1, piano"
    assert result.revised_plan == base_plan


def test_revision_workflow_benchmark_rejects_add_plan_without_actual_new_part():
    base_plan = make_base_plan()
    executor = RevisionExecutor()

    result = executor.apply_revision(
        base_plan=base_plan,
        revision_intent=RevisionIntent(is_revision=True, revision_type="add", target_part_id=None, instruction="加一个圆号"),
        user_instruction="加一个圆号",
        llm_planner=SimpleNamespace(
            apply_revision_for_add=lambda **kwargs: base_plan,
        ),
    )

    assert result.success is False
    assert result.message == "新增声部结果没有实际新增任何声部"
    assert result.revised_plan == base_plan
