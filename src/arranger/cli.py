"""
CLI 模块

本地可运行的命令行工具
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from .plan_schema import UnifiedPlan
from .analyze import MidiAnalysisService
from .orchestrate_executor import OrchestrateExecutor
from .validator import Validator
from .midi_io import MidiWriter


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description="可控 MIDI 编曲 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 分析 MIDI 文件
  %(prog)s analyze input.mid

  # 执行编曲
  %(prog)s arrange input.mid --plan plan.json --output arranged.mid

  # 使用内置示例 Plan
  %(prog)s arrange input.mid --ensemble 10 --output arranged.mid
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # analyze 命令
    analyze_parser = subparsers.add_parser("analyze", help="分析 MIDI 文件")
    analyze_parser.add_argument("input", type=Path, help="输入 MIDI 文件")
    analyze_parser.add_argument("--output", type=Path, help="输出 JSON 文件")

    # arrange 命令
    arrange_parser = subparsers.add_parser("arrange", help="执行编曲")
    arrange_parser.add_argument("input", type=Path, help="输入 MIDI 文件")
    arrange_parser.add_argument("--plan", type=Path, help="Plan JSON 文件")
    arrange_parser.add_argument("--ensemble", type=int, help="乐队人数（自动生成 Plan）")
    arrange_parser.add_argument("--melody-track", type=int, default=0, help="旋律轨索引")
    arrange_parser.add_argument("--output", type=Path, default=Path("arranged.mid"), help="输出 MIDI 文件")

    # validate 命令
    validate_parser = subparsers.add_parser("validate", help="验证 MIDI 文件")
    validate_parser.add_argument("input", type=Path, help="输入 MIDI 文件")
    validate_parser.add_argument("output", type=Path, help="输出 MIDI 文件")
    validate_parser.add_argument("--plan", type=Path, help="Plan JSON 文件")

    # 解析参数
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    try:
        if args.command == "analyze":
            return cmd_analyze(args)
        elif args.command == "arrange":
            return cmd_arrange(args)
        elif args.command == "validate":
            return cmd_validate(args)
        else:
            parser.print_help()
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_analyze(args) -> int:
    """分析 MIDI 文件"""
    print(f"Analyzing MIDI: {args.input}")

    # 读取文件
    with open(args.input, "rb") as f:
        midi_data = f.read()

    # 分析
    service = MidiAnalysisService()
    result = service.analyze(midi_data)

    # 输出
    output = {
        "tracks": [
            {
                "index": t.index,
                "name": t.name,
                "note_count": len(t.notes),
                "pitch_range": (
                    min(n.pitch for n in t.notes) if t.notes else 0,
                    max(n.pitch for n in t.notes) if t.notes else 0
                )
            }
            for t in result.tracks
        ],
        "melody_candidates": [
            {
                "track_index": c.track_index,
                "track_name": c.track_name,
                "score": c.score,
                "reason": c.reason
            }
            for c in result.melody_candidates
        ],
        "total_ticks": result.total_ticks,
        "ticks_per_beat": result.ticks_per_beat,
        "tempo": result.tempo,
        "time_signature": f"{result.time_signature[0]}/{result.time_signature[1]}"
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Analysis saved to: {args.output}")
    else:
        print(json.dumps(output, indent=2))

    return 0


def cmd_arrange(args) -> int:
    """执行编曲"""
    print(f"Arranging MIDI: {args.input}")

    # 读取输入文件
    with open(args.input, "rb") as f:
        midi_data = f.read()

    # 加载或生成 Plan
    if args.plan and args.plan.exists():
        with open(args.plan) as f:
            plan_data = json.load(f)
        plan = UnifiedPlan(**plan_data)
    elif args.ensemble:
        plan = generate_default_plan(args.ensemble)
    else:
        print("Error: Must specify either --plan or --ensemble", file=sys.stderr)
        return 1

    print(f"Using Plan: {plan.transform.type}")
    print(f"Ensemble: {plan.ensemble.name if plan.ensemble else 'N/A'}")
    if plan.ensemble:
        for part in plan.ensemble.parts:
            print(f"  - {part.name} ({part.role}): {part.instrument}")

    # 执行编曲
    executor = OrchestrateExecutor(plan)
    output_tracks, stats = executor.execute(
        input_midi=midi_data,
        melody_track_index=args.melody_track
    )

    print(f"Generated {stats['track_count']} tracks")
    print(f"Instruments: {', '.join(stats['instrument_list'])}")

    # 写入输出文件
    output_data = MidiWriter.write_midi(
        tracks=output_tracks,
        tempo=120,
        time_signature=(4, 4)
    )

    with open(args.output, "wb") as f:
        f.write(output_data)

    print(f"Output saved to: {args.output}")

    return 0


def cmd_validate(args) -> int:
    """验证 MIDI 文件"""
    print(f"Validating: input={args.input}, output={args.output}")

    # 读取文件
    with open(args.input, "rb") as f:
        input_data = f.read()

    with open(args.output, "rb") as f:
        output_data = f.read()

    # 加载 Plan（如果提供）
    if args.plan and args.plan.exists():
        with open(args.plan) as f:
            plan_data = json.load(f)
        plan = UnifiedPlan(**plan_data)
    else:
        # 使用默认 Plan
        plan = generate_default_plan(10)

    # 验证
    validator = Validator(plan)
    # 注意：这里需要 output_tracks，实际实现需要修改
    print("Validation not fully implemented in CLI")

    return 0


def generate_default_plan(ensemble_size: int) -> UnifiedPlan:
    """生成默认编曲 Plan"""
    parts = []

    if ensemble_size <= 4:
        # 弦乐四重奏
        parts = [
            {"id": "vn1", "name": "Violin I", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}},
            {"id": "vn2", "name": "Violin II", "role": "inner_voice", "instrument": "violin", "midi": {"channel": 1, "program": 40}},
            {"id": "va", "name": "Viola", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 2, "program": 41}},
            {"id": "vc", "name": "Cello", "role": "bass", "instrument": "cello", "midi": {"channel": 3, "program": 42}},
        ]
    elif ensemble_size <= 10:
        # 小型室内乐团
        parts = [
            {"id": "vn1", "name": "Violin I", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}},
            {"id": "vn2", "name": "Violin II", "role": "inner_voice", "instrument": "violin", "midi": {"channel": 1, "program": 40}},
            {"id": "va1", "name": "Viola I", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 2, "program": 41}},
            {"id": "va2", "name": "Viola II", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 3, "program": 41}},
            {"id": "vc1", "name": "Cello I", "role": "bass", "instrument": "cello", "midi": {"channel": 4, "program": 42}},
            {"id": "vc2", "name": "Cello II", "role": "bass", "instrument": "cello", "midi": {"channel": 5, "program": 42}},
            {"id": "fl", "name": "Flute", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 6, "program": 73}},
            {"id": "ob", "name": "Oboe", "role": "counter_melody", "instrument": "oboe", "midi": {"channel": 7, "program": 68}},
            {"id": "cl", "name": "Clarinet", "role": "inner_voice", "instrument": "clarinet", "midi": {"channel": 8, "program": 71}},
            {"id": "hn", "name": "Horn", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 9, "program": 60}},
        ]
    else:
        # 大型乐团（15人）
        parts = [
            {"id": "vn1", "name": "Violin I", "role": "melody", "instrument": "violin", "midi": {"channel": 0, "program": 40}},
            {"id": "vn2", "name": "Violin II", "role": "inner_voice", "instrument": "violin", "midi": {"channel": 1, "program": 40}},
            {"id": "va1", "name": "Viola I", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 2, "program": 41}},
            {"id": "va2", "name": "Viola II", "role": "inner_voice", "instrument": "viola", "midi": {"channel": 3, "program": 41}},
            {"id": "vc1", "name": "Cello I", "role": "bass", "instrument": "cello", "midi": {"channel": 4, "program": 42}},
            {"id": "vc2", "name": "Cello II", "role": "bass", "instrument": "cello", "midi": {"channel": 5, "program": 42}},
            {"id": "db", "name": "Double Bass", "role": "bass", "instrument": "double_bass", "midi": {"channel": 6, "program": 43}},
            {"id": "fl", "name": "Flute", "role": "counter_melody", "instrument": "flute", "midi": {"channel": 7, "program": 73}},
            {"id": "ob", "name": "Oboe", "role": "counter_melody", "instrument": "oboe", "midi": {"channel": 8, "program": 68}},
            {"id": "cl", "name": "Clarinet", "role": "inner_voice", "instrument": "clarinet", "midi": {"channel": 9, "program": 71}},
            {"id": "bn", "name": "Bassoon", "role": "bass", "instrument": "bassoon", "midi": {"channel": 10, "program": 70}},
            {"id": "hn1", "name": "Horn I", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 11, "program": 60}},
            {"id": "hn2", "name": "Horn II", "role": "sustain_support", "instrument": "horn", "midi": {"channel": 12, "program": 60}},
            {"id": "tp", "name": "Trumpet", "role": "accent", "instrument": "trumpet", "midi": {"channel": 13, "program": 56}},
            {"id": "timp", "name": "Timpani", "role": "percussion", "instrument": "timpani", "midi": {"channel": 14, "program": 47}},
        ]

    from .plan_schema import (
        EnsembleConfig, PartSpec, MidiSpec, Constraints,
        LockMelodyConfig, HarmonyContext, GuardsConfig,
        OutputConfig, MidiOutputConfig, TransformSpec
    )

    ensemble = EnsembleConfig(
        name=f"ensemble_{ensemble_size}",
        size="small" if ensemble_size <= 10 else "medium",
        target_size=ensemble_size,
        parts=[PartSpec(**p) for p in parts]
    )

    plan = UnifiedPlan(
        schema_version="1.0",
        transform=TransformSpec(
            type="orchestration",
            preserve_structure=True,
            preserve_order=True
        ),
        ensemble=ensemble,
        harmony_context=HarmonyContext(
            method="measure_pitchset_triadish",
            granularity="per_measure"
        ),
        constraints=Constraints(
            lock_melody_events=LockMelodyConfig(
                enabled=True,
                source_track_ref="0",
                source_track_selection_mode="auto",
                user_confirm_required=True,
                target_track_name="Melody"
            ),
            keep_total_ticks=True,
            guards=GuardsConfig(
                velocity_caps={"piano": 58, "viola": 62, "cello": 70, "flute": 64, "horn": 60},
                avoid_melody_onsets=True,
                onset_window_ticks=120
            )
        ),
        outputs=OutputConfig(
            midi=MidiOutputConfig(
                enabled=True,
                filename="arranged.mid",
                format="type1",
                track_grouping="by_instrument"
            )
        )
    )

    return plan


if __name__ == "__main__":
    sys.exit(main())
