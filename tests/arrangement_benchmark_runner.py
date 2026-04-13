from __future__ import annotations

import copy
import random
from collections import Counter
from functools import lru_cache
from typing import Any

from arranger.orchestrate_executor import OrchestrateExecutor
from arranger.timebase import measure_len
from arranger.validator import Validator
from tests.arrangement_benchmark_cases import (
    ArrangementBenchmarkCase,
    build_arrangement_benchmark_cases,
)


DEFAULT_BENCHMARK_METADATA = {
    "suite": "arrangement",
    "mode": "deterministic_profiles",
    "case_generation": "sample_profile_matrix",
}

EXPECTED_REPORT_FIELDS = (
    "section_modes",
    "guards_stats",
    "percussion_hits",
    "template_usage",
    "fixes_applied",
)

LOW_MELODY_CONFIDENCE_THRESHOLD = 0.25


def _extract_track_name(track_data: list[tuple[str, dict[str, Any]]]) -> str:
    for msg_type, params in track_data:
        if msg_type == "track_name":
            return params.get("name", "")
    return ""


def _count_note_on_events(track_data: list[tuple[str, dict[str, Any]]]) -> int:
    return sum(
        1
        for msg_type, params in track_data
        if msg_type == "note_on" and params.get("velocity", 0) > 0
    )


def _summarize_output_tracks(output_tracks: list[list[tuple[str, dict[str, Any]]]]) -> list[dict[str, Any]]:
    summaries = []
    for track_data in output_tracks:
        notes = [
            params
            for msg_type, params in track_data
            if msg_type == "note_on" and params.get("velocity", 0) > 0
        ]
        note_count = len(notes)
        summaries.append(
            {
                "track_name": _extract_track_name(track_data),
                "note_on_count": note_count,
                "avg_velocity": round(
                    sum(note["velocity"] for note in notes) / max(1, note_count),
                    2,
                ),
                "avg_pitch": round(
                    sum(note["note"] for note in notes) / max(1, note_count),
                    2,
                ),
            }
        )
    return summaries


def _min_note_threshold_for_role(role: str, measure_count: int) -> int:
    if role == "bass":
        return max(3, measure_count // 2)
    if role in ("counter_melody", "sustain_support"):
        return max(2, measure_count // 16)
    return max(4, measure_count // 4)


def _append_issue(
    issues: list[dict[str, Any]],
    issue_counts: Counter,
    code: str,
    severity: str,
    message: str,
    score: int,
    penalty: int,
) -> int:
    issues.append(
        {
            "code": code,
            "severity": severity,
            "message": message,
        }
    )
    issue_counts[code] += 1
    return score - penalty


def run_arrangement_case(case: ArrangementBenchmarkCase) -> dict[str, Any]:
    midi_data = case.sample.midi_data
    plan = case.profile.build_plan(case.sample)
    seed = f"arrangement-benchmark::{case.name}"
    random_state = random.getstate()
    random.seed(seed)
    try:
        output_tracks, stats = OrchestrateExecutor(plan).execute(
            midi_data,
            melody_track_index=case.sample.melody_track_index,
        )
        validation = Validator(plan).validate(midi_data, output_tracks)
    finally:
        random.setstate(random_state)

    track_summaries = _summarize_output_tracks(output_tracks)
    output_track_names = [track["track_name"] for track in track_summaries]
    auto_tracks = [name for name in output_track_names if name.startswith("auto_")]
    non_melody_note_count = sum(
        track["note_on_count"]
        for track in track_summaries
        if not track["track_name"].startswith("melody_")
    )
    ticks_per_measure = max(
        1,
        measure_len(case.sample.ticks_per_beat, case.sample.time_signature),
    )
    measure_count = max(
        1,
        (case.sample.total_ticks + ticks_per_measure - 1) // ticks_per_measure,
    )
    part_map = {part.id: part for part in plan.ensemble.parts}
    non_melody_track_summaries = [
        track for track in track_summaries if not track["track_name"].startswith("melody_")
    ]
    inactive_parts = [
        track["track_name"]
        for track in non_melody_track_summaries
        if track["note_on_count"] == 0
    ]
    underactive_parts = []
    for track in non_melody_track_summaries:
        part = part_map.get(track["track_name"])
        if part is None:
            continue
        min_threshold = _min_note_threshold_for_role(part.role, measure_count)
        if 0 < track["note_on_count"] < min_threshold:
            underactive_parts.append(
                {
                    "part_id": part.id,
                    "role": part.role,
                    "note_on_count": track["note_on_count"],
                    "min_threshold": min_threshold,
                }
            )

    melody_track_summary = next(
        (track for track in track_summaries if track["track_name"].startswith("melody_")),
        None,
    )
    accompaniment_avg_velocity = round(
        sum(track["avg_velocity"] for track in non_melody_track_summaries) / max(1, len(non_melody_track_summaries)),
        2,
    )
    melody_prominence_ratio = round(
        (melody_track_summary["avg_velocity"] / max(1.0, accompaniment_avg_velocity))
        if melody_track_summary
        else 0.0,
        2,
    )

    arrangement_report = stats.get("arrangement_report") or {}
    fixes_applied = arrangement_report.get("fixes_applied", [])
    fixes_count = len(fixes_applied)
    total_notes = max(stats.get("total_notes", 0), 1)
    fix_rate_per_100_notes = round((fixes_count / total_notes) * 100, 2)
    missing_report_fields = [
        field for field in EXPECTED_REPORT_FIELDS if field not in arrangement_report
    ]

    issues: list[dict[str, Any]] = []
    issue_counts: Counter = Counter()
    score = 100

    if case.sample.melody_confidence < LOW_MELODY_CONFIDENCE_THRESHOLD:
        score = _append_issue(
            issues,
            issue_counts,
            "low_melody_confidence",
            "warning",
            (
                f"Melody candidate confidence is only {case.sample.melody_confidence:.2f}; "
                "this sample is likely to need melody source confirmation."
            ),
            score,
            penalty=10,
        )

    if not validation.melody_identical.passed:
        score = _append_issue(
            issues,
            issue_counts,
            "melody_lock_failed",
            "error",
            validation.melody_identical.message,
            score,
            penalty=35,
        )

    if not validation.total_ticks_identical.passed:
        score = _append_issue(
            issues,
            issue_counts,
            "total_ticks_mismatch",
            "error",
            validation.total_ticks_identical.message,
            score,
            penalty=25,
        )

    if not validation.instrumentation_ok.passed:
        score = _append_issue(
            issues,
            issue_counts,
            "instrumentation_mismatch",
            "error",
            validation.instrumentation_ok.message,
            score,
            penalty=25,
        )

    if not validation.midi_valid.passed:
        score = _append_issue(
            issues,
            issue_counts,
            "midi_invalid",
            "error",
            validation.midi_valid.message,
            score,
            penalty=25,
        )

    if auto_tracks:
        score = _append_issue(
            issues,
            issue_counts,
            "unexpected_auto_tracks",
            "warning",
            f"System-generated helper tracks found: {', '.join(auto_tracks)}",
            score,
            penalty=20,
        )

    if non_melody_note_count == 0:
        score = _append_issue(
            issues,
            issue_counts,
            "empty_accompaniment",
            "error",
            "No accompaniment notes were generated outside the melody track.",
            score,
            penalty=20,
        )

    if inactive_parts:
        score = _append_issue(
            issues,
            issue_counts,
            "inactive_declared_parts",
            "warning",
            f"Declared parts with zero activity: {', '.join(inactive_parts)}",
            score,
            penalty=12,
        )

    if underactive_parts:
        score = _append_issue(
            issues,
            issue_counts,
            "underactive_declared_parts",
            "warning",
            (
                "Declared parts with suspiciously low activity: "
                + ", ".join(
                    f"{item['part_id']}({item['note_on_count']}<{item['min_threshold']})"
                    for item in underactive_parts
                )
            ),
            score,
            penalty=8,
        )

    if not validation.harmony_valid.passed:
        score = _append_issue(
            issues,
            issue_counts,
            "harmony_warning",
            "warning",
            validation.harmony_valid.message,
            score,
            penalty=10,
        )

    if not validation.instrument_range_valid.passed:
        score = _append_issue(
            issues,
            issue_counts,
            "instrument_range_warning",
            "warning",
            validation.instrument_range_valid.message,
            score,
            penalty=10,
        )

    if missing_report_fields:
        score = _append_issue(
            issues,
            issue_counts,
            "missing_arrangement_report_fields",
            "warning",
            f"Arrangement report is missing fields: {', '.join(missing_report_fields)}",
            score,
            penalty=10,
        )

    if fix_rate_per_100_notes > case.profile.max_fix_rate_per_100_notes:
        score = _append_issue(
            issues,
            issue_counts,
            "high_fix_rate",
            "warning",
            (
                f"Fix rate is {fix_rate_per_100_notes:.2f} per 100 notes, "
                f"above profile threshold {case.profile.max_fix_rate_per_100_notes:.2f}."
            ),
            score,
            penalty=8,
        )

    if melody_track_summary and melody_prominence_ratio < 0.9:
        score = _append_issue(
            issues,
            issue_counts,
            "weak_melody_prominence",
            "warning",
            (
                f"Melody average velocity ratio is {melody_prominence_ratio:.2f}, "
                "suggesting accompaniment may be too prominent."
            ),
            score,
            penalty=8,
        )

    score = max(0, score)
    if any(issue["severity"] == "error" for issue in issues):
        status = "fail"
    elif issues:
        status = "warn"
    else:
        status = "pass"

    return {
        "name": case.name,
        "sample": {
            "name": case.sample.name,
            "source_name": case.sample.source_name,
            "source_type": case.sample.source_type,
            "track_count": case.sample.track_count,
            "ticks_per_beat": case.sample.ticks_per_beat,
            "tempo": round(case.sample.tempo, 3),
            "time_signature": f"{case.sample.time_signature[0]}/{case.sample.time_signature[1]}",
            "total_ticks": case.sample.total_ticks,
            "melody_track_index": case.sample.melody_track_index,
            "melody_confidence": case.sample.melody_confidence,
        },
        "profile": {
            "name": case.profile.name,
            "description": case.profile.description,
            "expected_parts": case.profile.expected_parts,
            "max_fix_rate_per_100_notes": case.profile.max_fix_rate_per_100_notes,
        },
        "execution": {
            "track_count": stats.get("track_count"),
            "parts_count": stats.get("parts_count"),
            "instrument_list": stats.get("instrument_list"),
            "total_notes": stats.get("total_notes"),
            "non_melody_note_count": non_melody_note_count,
            "measure_count": measure_count,
            "output_tracks": track_summaries,
            "auto_tracks": auto_tracks,
        },
        "validation": validation.to_dict(),
        "quality": {
            "fixes_count": fixes_count,
            "fix_rate_per_100_notes": fix_rate_per_100_notes,
            "missing_report_fields": missing_report_fields,
            "inactive_parts": inactive_parts,
            "underactive_parts": underactive_parts,
            "melody_prominence_ratio": melody_prominence_ratio,
            "accompaniment_avg_velocity": accompaniment_avg_velocity,
        },
        "status": status,
        "score": score,
        "issues": issues,
        "issue_counts": dict(issue_counts),
    }


def _build_recommendations(issue_counts: Counter) -> list[str]:
    recommendations: list[str] = []

    if issue_counts["melody_lock_failed"]:
        recommendations.append(
            "Strengthen melody source selection for low-confidence inputs and consider forcing user confirmation on ambiguous files."
        )
    if issue_counts["harmony_warning"]:
        recommendations.append(
            "Review voice-leading and counterpoint templates; harmony warnings remain the most common soft failure."
        )
    if issue_counts["high_fix_rate"]:
        recommendations.append(
            "Reduce AutoFixer dependence by tightening template pitch ranges and default spacing before post-fix."
        )
    if issue_counts["inactive_declared_parts"] or issue_counts["underactive_declared_parts"]:
        recommendations.append(
            "Strengthen weak parts with role-aware fallback writing so declared ensemble members do not disappear in the texture."
        )
    if issue_counts["weak_melody_prominence"]:
        recommendations.append(
            "Keep melody clearly above accompaniment in average energy, especially on dense piano textures."
        )
    if issue_counts["unexpected_auto_tracks"]:
        recommendations.append(
            "Keep percussion and helper-track policies explicit so benchmarks do not drift from the declared ensemble."
        )

    return recommendations


@lru_cache(maxsize=1)
def _build_arrangement_benchmark_summary_cached() -> dict[str, Any]:
    cases = build_arrangement_benchmark_cases()
    rows = [run_arrangement_case(case) for case in cases]

    issue_counts: Counter = Counter()
    for row in rows:
        issue_counts.update(row["issue_counts"])

    passed = sum(1 for row in rows if row["status"] == "pass")
    warned = sum(1 for row in rows if row["status"] == "warn")
    failed = sum(1 for row in rows if row["status"] == "fail")
    validation_passed = sum(1 for row in rows if row["validation"]["all_passed"])
    low_confidence_cases = sum(
        1
        for row in rows
        if row["sample"]["melody_confidence"] < LOW_MELODY_CONFIDENCE_THRESHOLD
    )

    return {
        "metadata": DEFAULT_BENCHMARK_METADATA.copy(),
        "totals": {
            "cases": len(rows),
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "validation_passed": validation_passed,
            "validation_failed": len(rows) - validation_passed,
            "average_score": round(
                sum(row["score"] for row in rows) / max(1, len(rows)),
                2,
            ),
            "low_confidence_cases": low_confidence_cases,
        },
        "issue_counts": dict(sorted(issue_counts.items())),
        "recommendations": _build_recommendations(issue_counts),
        "cases": rows,
    }


def build_arrangement_benchmark_summary(
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = copy.deepcopy(_build_arrangement_benchmark_summary_cached())
    if metadata:
        summary["metadata"].update(metadata)
    return summary


def format_arrangement_benchmark_summary(summary: dict[str, Any]) -> str:
    lines = [
        "Arrangement Benchmark Summary",
        f"- Mode: {summary['metadata']['mode']}",
        f"- Case generation: {summary['metadata']['case_generation']}",
        (
            f"- Status: {summary['totals']['passed']} pass / "
            f"{summary['totals']['warned']} warn / {summary['totals']['failed']} fail"
        ),
        (
            f"- Validation: {summary['totals']['validation_passed']}/"
            f"{summary['totals']['cases']} hard checks passed"
        ),
        f"- Average score: {summary['totals']['average_score']}",
    ]

    if "provider" in summary["metadata"]:
        lines.append(f"- Provider: {summary['metadata']['provider']}")
    if "prompt_label" in summary["metadata"]:
        lines.append(f"- Prompt label: {summary['metadata']['prompt_label']}")

    if summary["issue_counts"]:
        lines.append("- Issues:")
        for code, count in summary["issue_counts"].items():
            lines.append(f"  - {code}: {count}")

    if summary["recommendations"]:
        lines.append("- Recommendations:")
        for item in summary["recommendations"]:
            lines.append(f"  - {item}")

    lines.append("- Cases:")
    for row in summary["cases"]:
        first_issue = row["issues"][0]["code"] if row["issues"] else "none"
        lines.append(
            (
                f"  * {row['name']}: {row['status'].upper()} "
                f"(score={row['score']}, validation={row['validation']['all_passed']}, "
                f"first_issue={first_issue})"
            )
        )

    return "\n".join(lines)
