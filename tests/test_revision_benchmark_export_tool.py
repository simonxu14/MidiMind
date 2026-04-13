import json
import subprocess
import sys
from pathlib import Path


def test_export_revision_benchmark_snapshot_writes_json_with_metadata(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    output_path = tmp_path / "revision-benchmark.json"

    subprocess.run(
        [
            sys.executable,
            "tools/export_revision_benchmark_snapshot.py",
            "--format",
            "json",
            "--provider",
            "anthropic",
            "--prompt-label",
            "baseline-v1",
            "--output",
            str(output_path),
        ],
        cwd=repo_root,
        check=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["metadata"] == {
        "suite": "revision",
        "mode": "heuristic_fallback",
        "provider": "anthropic",
        "prompt_label": "baseline-v1",
    }
    assert payload["totals"]["intent_passed"] == 12
    assert payload["totals"]["workflow_passed"] == 5
