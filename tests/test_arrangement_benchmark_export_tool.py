import json
import subprocess
import sys
from pathlib import Path


def test_export_arrangement_benchmark_snapshot_writes_json_with_metadata(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    output_path = tmp_path / "arrangement-benchmark.json"

    subprocess.run(
        [
            sys.executable,
            "tools/export_arrangement_benchmark_snapshot.py",
            "--format",
            "json",
            "--provider",
            "minimax",
            "--prompt-label",
            "executor-baseline",
            "--output",
            str(output_path),
        ],
        cwd=repo_root,
        check=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["metadata"] == {
        "suite": "arrangement",
        "mode": "deterministic_profiles",
        "case_generation": "sample_profile_matrix",
        "provider": "minimax",
        "prompt_label": "executor-baseline",
    }
    assert payload["totals"]["cases"] == 24
    assert payload["totals"]["passed"] == 24
    assert "average_score" in payload["totals"]
