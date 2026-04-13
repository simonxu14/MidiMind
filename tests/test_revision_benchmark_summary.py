from tests.revision_benchmark_runner import (
    build_revision_benchmark_summary,
    format_revision_benchmark_summary,
)


def test_build_revision_benchmark_summary_reports_totals():
    summary = build_revision_benchmark_summary()

    assert summary["metadata"] == {
        "suite": "revision",
        "mode": "heuristic_fallback",
    }
    assert summary["totals"] == {
        "cases": 12,
        "intent_passed": 12,
        "intent_failed": 0,
        "workflow_cases": 5,
        "workflow_passed": 5,
        "workflow_failed": 0,
    }

    add_horn = next(row for row in summary["cases"] if row["name"] == "add_horn")
    assert add_horn["intent"]["detected_type"] == "add"
    assert add_horn["workflow"]["part_ids"] == ["vn1", "piano", "vc", "hn"]
    assert add_horn["workflow"]["modified_parts"] == ["hn"]

    global_mood = next(row for row in summary["cases"] if row["name"] == "regenerate_global_mood")
    assert global_mood["intent"]["detected_revision"] is False
    assert global_mood["workflow"] is None


def test_format_revision_benchmark_summary_includes_totals_and_case_status():
    summary = build_revision_benchmark_summary()

    formatted = format_revision_benchmark_summary(summary)

    assert "Revision Benchmark Summary" in formatted
    assert "- Mode: heuristic_fallback" in formatted
    assert "- Intent: 12/12 passed" in formatted
    assert "- Workflow: 5/5 passed" in formatted
    assert "* add_horn: intent=PASS (add / none)" in formatted


def test_build_revision_benchmark_summary_accepts_metadata_overrides():
    summary = build_revision_benchmark_summary(
        metadata={"provider": "anthropic", "prompt_label": "baseline-v1"},
    )

    assert summary["metadata"] == {
        "suite": "revision",
        "mode": "heuristic_fallback",
        "provider": "anthropic",
        "prompt_label": "baseline-v1",
    }
