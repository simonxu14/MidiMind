from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from arranger.llm_planner import LLMPlanner
from arranger.plan_linter import lint_plan
from arranger.plan_schema import (
    Constraints,
    EnsembleConfig,
    HarmonyContext,
    MidiOutputConfig,
    MidiSpec,
    OutputConfig,
    PartSpec,
    TransformSpec,
    UnifiedPlan,
)
from arranger.revision_executor import RevisionExecutor
from tests.revision_benchmark_cases import (
    REVISION_BENCHMARK_CASES,
    RevisionBenchmarkCase,
)

DEFAULT_BENCHMARK_METADATA = {
    "suite": "revision",
    "mode": "heuristic_fallback",
}


def make_plan(parts: list[PartSpec], name: str = "benchmark") -> UnifiedPlan:
    return UnifiedPlan(
        schema_version="1.0",
        transform=TransformSpec(type="orchestration"),
        ensemble=EnsembleConfig(name=name, size="small", target_size=len(parts), parts=parts),
        harmony_context=HarmonyContext(),
        constraints=Constraints(),
        outputs=OutputConfig(midi=MidiOutputConfig(enabled=True, filename="benchmark.mid")),
    )


def make_base_plan() -> UnifiedPlan:
    return make_plan([
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
    ])


def make_strings_duo_plan() -> UnifiedPlan:
    return make_plan([
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
            id="vc",
            name="Cello",
            role="bass",
            instrument="cello",
            midi=MidiSpec(channel=2, program=42),
            template_name="cello_pedal_root",
        ),
    ], name="strings_duo")


def build_plan_for_variant(plan_variant: str) -> UnifiedPlan:
    if plan_variant == "strings_duo":
        return make_strings_duo_plan()
    return make_base_plan()


def build_revised_plan_for_add(base_plan: UnifiedPlan) -> UnifiedPlan:
    return make_plan([
        *base_plan.ensemble.parts,
        PartSpec(
            id="hn",
            name="Horn",
            role="sustain_support",
            instrument="horn",
            midi=MidiSpec(channel=3, program=60),
            template_name="root_pad",
        ),
    ])


def build_revised_plan_for_modify(base_plan: UnifiedPlan) -> UnifiedPlan:
    return make_plan([
        base_plan.ensemble.parts[0],
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


def build_revised_plan_for_modify_second_violin(base_plan: UnifiedPlan) -> UnifiedPlan:
    return make_plan([
        base_plan.ensemble.parts[0],
        PartSpec(
            id="vn2",
            name="Violin II",
            role="inner_voice",
            instrument="violin",
            midi=MidiSpec(channel=1, program=40),
            template_name="adaptive_strings",
            template_params={"density": 0.8},
        ),
        base_plan.ensemble.parts[2],
    ])


def build_llm_planner_stub(case: RevisionBenchmarkCase, base_plan: UnifiedPlan) -> Optional[Any]:
    if case.workflow_stub == "add_horn":
        return SimpleNamespace(
            apply_revision_for_add=lambda **kwargs: build_revised_plan_for_add(base_plan),
        )
    if case.workflow_stub == "modify_piano_density":
        return SimpleNamespace(
            apply_revision_for_modify=lambda **kwargs: build_revised_plan_for_modify(base_plan),
        )
    if case.workflow_stub == "modify_second_violin":
        return SimpleNamespace(
            apply_revision_for_modify=lambda **kwargs: build_revised_plan_for_modify_second_violin(base_plan),
        )
    return None


def run_revision_intent_case(case: RevisionBenchmarkCase) -> dict[str, Any]:
    planner = LLMPlanner(api_key="test-key")
    plan = build_plan_for_variant(case.plan_variant)
    planner._call_llm = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm unavailable"))

    intent = planner.analyze_revision_intent(case.message, plan)
    passed = (
        intent.is_revision is case.expected_revision
        and intent.revision_type == case.expected_type
        and intent.target_part_id == case.expected_target
    )

    return {
        "name": case.name,
        "message": case.message,
        "plan_variant": case.plan_variant,
        "expected_revision": case.expected_revision,
        "expected_type": case.expected_type,
        "expected_target": case.expected_target,
        "detected_revision": intent.is_revision,
        "detected_type": intent.revision_type,
        "detected_target": intent.target_part_id,
        "passed": passed,
    }


def run_revision_workflow_case(case: RevisionBenchmarkCase) -> dict[str, Any]:
    base_plan = build_plan_for_variant(case.plan_variant)
    planner = LLMPlanner(api_key="test-key")
    executor = RevisionExecutor()
    planner._call_llm = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm unavailable"))

    intent = planner.analyze_revision_intent(case.message, base_plan)
    llm_planner = build_llm_planner_stub(case, base_plan)
    result = executor.apply_revision(
        base_plan=base_plan,
        revision_intent=intent,
        user_instruction=case.message,
        llm_planner=llm_planner,
    )

    if result.success:
        revised_plan = result.revised_plan
        lint_result = lint_plan(revised_plan.model_dump())
        part_ids = [part.id for part in revised_plan.ensemble.parts]
        warning_count = len(lint_result.warnings)
        passed = (
            result.modified_parts == case.expected_modified_parts
            and part_ids == case.expected_part_ids
            and revised_plan.ensemble.target_size == len(case.expected_part_ids or [])
            and lint_result.passed is True
            and warning_count <= 0
        )
    else:
        lint_result = None
        part_ids = None
        warning_count = None
        passed = False

    return {
        "name": case.name,
        "message": case.message,
        "workflow_stub": case.workflow_stub,
        "success": result.success,
        "message_detail": result.message,
        "modified_parts": result.modified_parts,
        "part_ids": part_ids,
        "expected_part_ids": case.expected_part_ids,
        "expected_modified_parts": case.expected_modified_parts,
        "lint_passed": lint_result.passed if lint_result else None,
        "lint_warning_count": warning_count,
        "passed": passed,
    }


def build_revision_benchmark_summary(
    cases: list[RevisionBenchmarkCase] = REVISION_BENCHMARK_CASES,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    rows = []
    workflow_passed = 0
    workflow_total = 0

    for case in cases:
        intent_summary = run_revision_intent_case(case)
        workflow_summary = None
        if case.expected_revision and case.expected_part_ids is not None:
            workflow_total += 1
            workflow_summary = run_revision_workflow_case(case)
            if workflow_summary["passed"]:
                workflow_passed += 1

        rows.append({
            "name": case.name,
            "message": case.message,
            "intent": intent_summary,
            "workflow": workflow_summary,
        })

    intent_passed = sum(1 for row in rows if row["intent"]["passed"])
    return {
        "metadata": {
            **DEFAULT_BENCHMARK_METADATA,
            **(metadata or {}),
        },
        "totals": {
            "cases": len(rows),
            "intent_passed": intent_passed,
            "intent_failed": len(rows) - intent_passed,
            "workflow_cases": workflow_total,
            "workflow_passed": workflow_passed,
            "workflow_failed": workflow_total - workflow_passed,
        },
        "cases": rows,
    }


def format_revision_benchmark_summary(summary: dict[str, Any]) -> str:
    metadata = summary.get("metadata", {})
    totals = summary["totals"]
    lines = [
        "Revision Benchmark Summary",
        f"- Mode: {metadata.get('mode', 'unknown')}",
        f"- Intent: {totals['intent_passed']}/{totals['cases']} passed",
        f"- Workflow: {totals['workflow_passed']}/{totals['workflow_cases']} passed",
    ]
    if metadata.get("provider"):
        lines.append(f"- Provider: {metadata['provider']}")
    if metadata.get("prompt_label"):
        lines.append(f"- Prompt: {metadata['prompt_label']}")
    for row in summary["cases"]:
        intent = row["intent"]
        workflow = row["workflow"]
        intent_status = "PASS" if intent["passed"] else "FAIL"
        lines.append(
            f"* {row['name']}: intent={intent_status} "
            f"({intent['detected_type'] or 'none'} / {intent['detected_target'] or 'none'})"
        )
        if workflow is not None:
            workflow_status = "PASS" if workflow["passed"] else "FAIL"
            lines.append(
                f"  workflow={workflow_status} "
                f"(parts={workflow['part_ids']}, modified={workflow['modified_parts']}, "
                f"warnings={workflow['lint_warning_count']})"
            )
    return "\n".join(lines)
