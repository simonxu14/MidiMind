# Revision Benchmark Notes

当前 revision benchmark 已经整理成共享 matrix + runner 的结构：

- case 定义在 [tests/revision_benchmark_cases.py](/Users/bytedance/MyProject/midimind/tests/revision_benchmark_cases.py)
- 共享执行与 summary 逻辑在 [tests/revision_benchmark_runner.py](/Users/bytedance/MyProject/midimind/tests/revision_benchmark_runner.py)
- intent benchmark 在 [tests/test_revision_intent_benchmarks.py](/Users/bytedance/MyProject/midimind/tests/test_revision_intent_benchmarks.py)
- workflow benchmark 在 [tests/test_revision_workflow_benchmarks.py](/Users/bytedance/MyProject/midimind/tests/test_revision_workflow_benchmarks.py)
- summary 输出稳定性在 [tests/test_revision_benchmark_summary.py](/Users/bytedance/MyProject/midimind/tests/test_revision_benchmark_summary.py)

目前 summary 会固定输出两层信息：

- `metadata`
  - `suite`
  - `mode`
  - 可选 `provider` / `prompt_label`
- `totals`
  - `cases`
  - `intent_passed` / `intent_failed`
  - `workflow_cases`
  - `workflow_passed` / `workflow_failed`
- `cases`
  - 每个 case 的 `intent` 结果
  - 如适用，对应的 `workflow` 结果

这样后面做 provider 切换、prompt 调整、heuristic 变更时，可以直接比较：

- intent 识别有没有漂
- 哪些 case 从 revision 退化成 regenerate
- workflow 是否仍满足结构约束和 lint 约束

当前也已经补了 JSON snapshot 基线：

- 基线文件在 [tests/fixtures/revision_benchmark_summary_baseline.json](/Users/bytedance/MyProject/midimind/tests/fixtures/revision_benchmark_summary_baseline.json)
- 严格对比测试在 [tests/test_revision_benchmark_snapshot.py](/Users/bytedance/MyProject/midimind/tests/test_revision_benchmark_snapshot.py)

如果要导出当前快照，可以直接在仓库根目录运行：

```bash
python3 tools/export_revision_benchmark_snapshot.py --format json
python3 tools/export_revision_benchmark_snapshot.py --format json --provider anthropic --prompt-label baseline-v1 --output /tmp/revision-benchmark.json
python3 tools/export_revision_benchmark_snapshot.py --format text
```

下一步如果继续扩，可以优先补：

- provider 维度的 summary 对比
- 更细的 warning 分类统计
