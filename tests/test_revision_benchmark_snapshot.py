import json
from pathlib import Path

from tests.revision_benchmark_runner import build_revision_benchmark_summary


BASELINE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "revision_benchmark_summary_baseline.json"
)


def test_revision_benchmark_summary_matches_baseline_snapshot():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert build_revision_benchmark_summary() == baseline
