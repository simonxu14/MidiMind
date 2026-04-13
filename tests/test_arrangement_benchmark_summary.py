from tests.arrangement_benchmark_runner import (
    build_arrangement_benchmark_summary,
    format_arrangement_benchmark_summary,
)


def test_build_arrangement_benchmark_summary_reports_totals_and_known_case_findings():
    summary = build_arrangement_benchmark_summary()

    assert summary["metadata"] == {
        "suite": "arrangement",
        "mode": "deterministic_profiles",
        "case_generation": "sample_profile_matrix",
    }
    assert summary["totals"]["cases"] == 24
    assert summary["totals"] == {
        "cases": 24,
        "passed": 24,
        "warned": 0,
        "failed": 0,
        "validation_passed": 24,
        "validation_failed": 0,
        "average_score": 100.0,
        "low_confidence_cases": 0,
    }
    assert summary["issue_counts"] == {}

    low_conf_case = next(
        row for row in summary["cases"] if row["name"] == "匆匆那年__piano_trio"
    )
    assert low_conf_case["status"] == "pass"
    assert low_conf_case["validation"]["melody_identical"]["passed"] is True

    stable_case = next(
        row for row in summary["cases"] if row["name"] == "我和我的祖国__piano_trio"
    )
    assert stable_case["validation"]["all_passed"] is True
    assert stable_case["score"] == 100


def test_format_arrangement_benchmark_summary_includes_totals_and_case_status():
    summary = build_arrangement_benchmark_summary()

    formatted = format_arrangement_benchmark_summary(summary)

    assert "Arrangement Benchmark Summary" in formatted
    assert "- Mode: deterministic_profiles" in formatted
    assert "- Case generation: sample_profile_matrix" in formatted
    assert "- Status: 24 pass / 0 warn / 0 fail" in formatted
    assert "* 匆匆那年__piano_trio: PASS" in formatted
    assert "* generated_polyphonic_piano_4_4__chamber_mixed: PASS" in formatted


def test_build_arrangement_benchmark_summary_accepts_metadata_overrides():
    summary = build_arrangement_benchmark_summary(
        metadata={"provider": "minimax", "prompt_label": "executor-baseline"},
    )

    assert summary["metadata"] == {
        "suite": "arrangement",
        "mode": "deterministic_profiles",
        "case_generation": "sample_profile_matrix",
        "provider": "minimax",
        "prompt_label": "executor-baseline",
    }
