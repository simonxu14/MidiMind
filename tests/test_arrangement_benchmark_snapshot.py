import json
from pathlib import Path

from tests.arrangement_benchmark_runner import build_arrangement_benchmark_summary


BASELINE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "arrangement_benchmark_summary_baseline.json"
)


def test_arrangement_benchmark_summary_matches_baseline_snapshot():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert build_arrangement_benchmark_summary() == baseline
