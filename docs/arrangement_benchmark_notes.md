# Arrangement Benchmark Notes

这套 benchmark 的目标，是让系统能对“编曲执行结果”做一轮稳定的自评，而不是只看单条单测。

当前结构：

- case/profile 生成在 [tests/arrangement_benchmark_cases.py](/Users/bytedance/MyProject/midimind/tests/arrangement_benchmark_cases.py)
- 共享执行与评分逻辑在 [tests/arrangement_benchmark_runner.py](/Users/bytedance/MyProject/midimind/tests/arrangement_benchmark_runner.py)
- summary 输出稳定性在 [tests/test_arrangement_benchmark_summary.py](/Users/bytedance/MyProject/midimind/tests/test_arrangement_benchmark_summary.py)
- JSON snapshot 基线在 [tests/fixtures/arrangement_benchmark_summary_baseline.json](/Users/bytedance/MyProject/midimind/tests/fixtures/arrangement_benchmark_summary_baseline.json)
- 导出工具在 [tools/export_arrangement_benchmark_snapshot.py](/Users/bytedance/MyProject/midimind/tools/export_arrangement_benchmark_snapshot.py)

当前 benchmark 会自动做两件事：

- 读取 [tests/sample](/Users/bytedance/MyProject/midimind/tests/sample) 下的真实 sample MIDI
- 生成一组 synthetic MIDI case，覆盖 `4/4`、`6/8`、`3/4`、syncopation、单轨复调钢琴等输入形态
- 为每个 sample 自动展开多个确定性编制 profile，形成 `sample x profile` 的 case matrix

每个 case 目前都会汇总：

- 输入样本信息
  - 轨道数、节拍、速度、总 tick
  - 自动选到的 melody track 和对应置信度
- 执行结果
  - 输出轨道摘要
  - 非旋律音符数
  - 自动 helper track 情况
- 校验结果
  - `Validator` 的硬约束和软约束
- 质量结果
  - `arrangement_report` 是否完整
  - `fixes_applied` 数量和 fix rate
  - 声部是否 inactive / underactive
  - melody prominence
- 自评
  - `status`: `pass / warn / fail`
  - `score`
  - `issues`

当前 summary 顶层会固定输出：

- `metadata`
- `totals`
- `issue_counts`
- `recommendations`
- `cases`

如果要导出当前快照，可以直接在仓库根目录运行：

```bash
python3 tools/export_arrangement_benchmark_snapshot.py --format json
python3 tools/export_arrangement_benchmark_snapshot.py --format text
python3 tools/export_arrangement_benchmark_snapshot.py --format json --provider minimax --prompt-label executor-baseline --output /tmp/arrangement-benchmark.json
```

这套 benchmark 目前更偏“执行层/质量层”，下一步适合继续补：

- style-specific rubric
- phrase / cadence / texture 维度的音乐学评分
- LLM planner 参与下的 prompt/provider 对比
