"""
自动化测试脚本 - 测试编曲系统

自动使用示例 MIDI 文件和生成的编曲意图来测试系统，
然后分析结果是否正确。
"""

import json
import sys
import os
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arranger.analyze import MidiAnalysisService
from arranger.llm_planner import LLMPlanner
from arranger.plan_schema import UnifiedPlan
from arranger.midi_io import MidiReader, MidiWriter


# 测试用例：MIDI 文件 + 编曲意图
TEST_CASES = [
    {
        "name": "稻香_古典室内乐",
        "midi": "examples/稻香.mid",
        "intent": """【输入素材】：周杰伦《稻香》钢琴独奏MIDI文件，核心主旋律已单独拆分轨道标注。
【最高优先级约束】
1. 原曲核心主旋律的音高、节奏、时长、段落结构完全保留
2. 全曲主旋律固定由第一小提琴担任独奏
3. 必须严格采用8人小型室内乐编制：弦乐3人(第一小提琴+中提琴+大提琴)、木管2人(长笛+单簧管)、铜管1人(圆号)、键盘1人(钢琴)、打击乐1人(定音鼓+三角铁)

【改编风格】：严谨的欧洲古典室内乐交响风格，织体清晰、层次分明
"""
    },
    {
        "name": "匆匆那年_流行改编",
        "midi": "examples/匆匆那年.mid",
        "intent": """【输入素材】：匆匆那年钢琴独奏MIDI
【改编要求】：
1. 主旋律由钢琴演奏
2. 6人流行乐队编制：钢琴、吉他、贝斯、小提琴、大提琴、鼓组
3. 风格：现代流行，温暖抒情
"""
    },
    {
        "name": "浏阳河_爵士风格",
        "midi": "examples/浏阳河.mid",
        "intent": """【输入素材】：浏阳河MIDI
【改编要求】：
1. 主旋律由钢琴和弦乐四重奏共同呈现
2. 爵士五重奏编制：钢琴、贝斯、鼓组、小号、萨克斯
3. 风格：Smooth Jazz，优雅轻松
"""
    },
    {
        "name": "我和我的祖国_交响编制",
        "midi": "examples/我和我的祖国.mid",
        "intent": """【输入素材】：我和我的祖国MIDI
【改编要求】：
1. 主旋律由小提琴和铜管共同演奏
2. 12人交响乐队编制：弦乐5人(第1小提琴、第2小提琴、中提琴、大提琴、低音提琴)、木管4人(长笛、双簧管、单簧管、巴松管)、铜管3人(圆号、小号、长号)
3. 风格：古典交响，庄严大气
"""
    }
]


def analyze_midi(midi_path: str) -> dict:
    """分析 MIDI 文件"""
    with open(midi_path, "rb") as f:
        midi_data = f.read()

    service = MidiAnalysisService()
    result = service.analyze(midi_data)

    return {
        "tracks_count": len(result.tracks),
        "tempo": result.tempo,
        "time_signature": str(result.time_signature),
        "total_ticks": result.total_ticks,
        "melody_candidates": [
            {"track_index": c.track_index, "score": c.score}
            for c in result.melody_candidates[:3]
        ]
    }


def check_plan(plan_dict: dict, test_name: str) -> list:
    """检查 Plan 是否有问题"""
    issues = []

    if not plan_dict.get("ensemble"):
        issues.append(f"[{test_name}] Plan 缺少 ensemble")
        return issues

    parts = plan_dict["ensemble"].get("parts", [])

    # 检查 channel 分配
    channels_used = set()
    for part in parts:
        ch = part.get("midi", {}).get("channel")
        if ch in channels_used:
            issues.append(f"[{test_name}] Channel 冲突: {part['id']} 使用了已占用的 channel {ch}")
        channels_used.add(ch)

    # 检查 template_name 是否为 unknown
    for part in parts:
        if part.get("template_name") == "unknown":
            issues.append(f"[{test_name}] Part {part['id']} 没有指定 template_name")

    # 检查模板是否匹配
    from arranger.templates import get_registry
    registry = get_registry()

    for part in parts:
        template_name = part.get("template_name")
        if template_name and template_name != "unknown":
            template = registry.get(template_name)
            if template:
                # 检查 instrument 匹配
                if part["instrument"] not in template.applicable_instruments:
                    issues.append(
                        f"[{test_name}] Part {part['id']}: instrument '{part['instrument']}' "
                        f"不匹配模板 {template_name} 的适用乐器 {template.applicable_instruments}"
                    )
                # 检查 role 匹配
                if part["role"] not in template.applicable_roles:
                    issues.append(
                        f"[{test_name}] Part {part['id']}: role '{part['role']}' "
                        f"不匹配模板 {template_name} 的适用角色 {template.applicable_roles}"
                    )

    return issues


def run_test(test_case: dict) -> dict:
    """运行单个测试"""
    name = test_case["name"]
    midi_path = test_case["midi"]
    intent = test_case["intent"]

    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"MIDI: {midi_path}")
    print(f"{'='*60}")

    # 1. 分析 MIDI
    print(f"\n[1] 分析 MIDI...")
    try:
        analysis = analyze_midi(midi_path)
        print(f"    轨道数: {analysis['tracks_count']}")
        print(f"    速度: {analysis['tempo']} BPM")
        print(f"    拍号: {analysis['time_signature']}")
        print(f"    旋律候选: {analysis['melody_candidates']}")
    except Exception as e:
        print(f"    错误: {e}")
        return {"name": name, "status": "error", "error": str(e)}

    # 2. 生成 Plan
    print(f"\n[2] 生成编曲方案...")
    try:
        from arranger.plan_schema import AnalyzeResponse, MelodyCandidate, TrackStats
        from arranger.conversation import conversation_manager

        # 先创建会话
        conversation_id = conversation_manager.create_conversation(
            user_intent=intent,
            metadata={"midi_file": midi_path, "test_name": name}
        )

        analyze_result = AnalyzeResponse(
            tracks=[
                TrackStats(
                    index=i,
                    name=f"Track {i}",
                    note_on_count=10,
                    pitch_range=(60, 80),
                    max_polyphony=3
                )
                for i in range(analysis['tracks_count'])
            ],
            melody_candidates=[
                MelodyCandidate(
                    track_index=c["track_index"],
                    score=c["score"],
                    reason="auto"
                )
                for c in analysis["melody_candidates"]
            ],
            total_ticks=analysis["total_ticks"],
            ticks_per_beat=480,
            tempo=int(analysis["tempo"]),
            time_signature=analysis["time_signature"]
        )

        planner = LLMPlanner(conversation_id=conversation_id)
        plan = planner.generate_plan(
            analyze_result=analyze_result,
            user_intent=intent,
            previous_feedback=None
        )

        plan_dict = plan.model_dump()

        # 3. 检查 Plan
        print(f"\n[3] 检查编曲方案...")
        issues = check_plan(plan_dict, name)

        if issues:
            print(f"    发现 {len(issues)} 个问题:")
            for issue in issues:
                print(f"      - {issue}")
        else:
            print(f"    检查通过!")

        # 打印声部信息
        parts = plan_dict.get("ensemble", {}).get("parts", [])
        print(f"\n    声部 ({len(parts)}个):")
        for p in parts:
            ch = p.get("midi", {}).get("channel")
            prog = p.get("midi", {}).get("program")
            print(f"      {p['id']}: {p['instrument']}+{p['role']} -> ch{ch} prog{prog} [{p.get('template_name', 'NONE')}]")

        return {
            "name": name,
            "status": "checked",
            "issues": issues,
            "plan": plan_dict
        }

    except Exception as e:
        import traceback
        print(f"    错误: {e}")
        traceback.print_exc()
        return {"name": name, "status": "error", "error": str(e)}


def main():
    print("=" * 60)
    print("自动化编曲测试")
    print("=" * 60)

    results = []
    for test_case in TEST_CASES:
        result = run_test(test_case)
        results.append(result)

    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)

    passed = sum(1 for r in results if r["status"] == "checked" and not r.get("issues"))
    failed = len(results) - passed

    print(f"总计: {len(results)} 个测试")
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    if failed > 0:
        print("\n失败详情:")
        for r in results:
            if r["status"] != "checked" or r.get("issues"):
                print(f"  - {r['name']}: {r.get('issues', [r.get('error')])}")


if __name__ == "__main__":
    main()
