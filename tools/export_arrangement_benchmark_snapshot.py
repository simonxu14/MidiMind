#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tests.arrangement_benchmark_runner import (  # noqa: E402
    build_arrangement_benchmark_summary,
    format_arrangement_benchmark_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the current arrangement benchmark summary as JSON or text.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file path. Defaults to stdout.",
    )
    parser.add_argument(
        "--provider",
        help="Optional provider label to include in metadata.",
    )
    parser.add_argument(
        "--prompt-label",
        help="Optional prompt label to include in metadata.",
    )
    parser.add_argument(
        "--mode",
        default="deterministic_profiles",
        help="Benchmark mode label stored in metadata.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata = {"mode": args.mode}
    if args.provider:
        metadata["provider"] = args.provider
    if args.prompt_label:
        metadata["prompt_label"] = args.prompt_label

    summary = build_arrangement_benchmark_summary(metadata=metadata)
    if args.format == "text":
        payload = format_arrangement_benchmark_summary(summary)
    else:
        payload = json.dumps(summary, ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            payload + ("\n" if not payload.endswith("\n") else ""),
            encoding="utf-8",
        )
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
