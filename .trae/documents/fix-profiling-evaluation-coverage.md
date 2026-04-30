# Plan: 修复 Profiling 覆盖率 — 将评估阶段纳入阶段追踪

## 问题分析

实验报告显示 S1-S8 阶段耗时合计约 681s，但 Pipeline 总耗时 2,866s，差值约 2,185s (76.2%) 未被 profiling 覆盖。

**根因**：当前 profiling 仅追踪 S1-S8 阶段，但 `evaluate_test_set()` 中的 **LLM 评估调用**（Faithfulness、Answer Relevancy、Context Precision、Context Recall）未被任何阶段覆盖。

### 代码追踪

在 [core.py:222-234](file:///b:/project/w0-easy-rag/eval/runner/core.py#L222-L234) 中：

```python
for test_set in test_sets:
    results = evaluate_test_set(
        pipeline, test_set, ...
    )
```

`evaluate_test_set()` 内部做了两件事：

1. `collect_rag_samples()` → 调用 `pipeline.query()` → **S6+S7 已被追踪**
2. `evaluate_with_builtin()` / `evaluate_with_ragas()` → **未被追踪** ← 这就是 2,185s 的来源

评估阶段的 LLM 调用量（builtin, core preset）：

* Faithfulness: 2 次 LLM 调用（extract statements + verify statements）

* Answer Relevancy: 1 次 LLM 调用

* Context Precision: N 次 LLM 调用（每个 context 一次）

* Context Recall: M 次 LLM 调用（每个 GT 句子一次）

***

## 实施步骤

### Step 1: 在 `pipeline_profiler.py` 中添加 S9 阶段定义

* 在 `STAGE_NAMES` 中添加 `"S9": "评估计算"`

* 在 `get_normalized_metrics()` 中将 S9 纳入 QA 处理归一化（与 S6/S7 同组）

* 在 `generate_markdown_report()` 中添加"未追踪时间"计算行，显示 `total_duration - sum(stages)` 的差值

### Step 2: 在 `evaluation.py` 中添加 profiler 参数和 S9 追踪

* `evaluate_test_set()` 增加 `profiler: PipelineProfiler | None = None` 参数

* 在评估循环（`for backend_name, metrics in allocation.items()`）外层包裹 S9 profiling

* 使用 `profiler.profile_stage("S9", metadata)` 上下文管理器

### Step 3: 在 `core.py` 中传递 profiler

* `run_variant_evaluation()` 中调用 `evaluate_test_set()` 时传入 `profiler=profiler`

### Step 4: 更新 Markdown 报告

* 在 [pipeline\_profiler.py](file:///b:/project/w0-easy-rag/eval/pipeline_profiler.py) 的 `generate_markdown_report()` 中：

  * 在总览表格后添加"未追踪时间"行（如果差值 > 0）

  * 在优化建议中添加对 S9 耗时过高的建议

### Step 5: 更新测试

* 在 `test_profiler_all_stages` 中将 S9 加入遍历列表

* 添加 `test_profiler_untracked_time` 测试未追踪时间计算

### Step 6: 运行 lint 验证

* `pixi run lint` 确保代码质量

***

## 修改文件清单

| 文件                                 | 修改内容                              |
| ---------------------------------- | --------------------------------- |
| `eval/pipeline_profiler.py`        | 添加 S9 定义、更新归一化、更新报告               |
| `eval/runner/evaluation.py`        | 添加 profiler 参数、S9 追踪              |
| `eval/runner/core.py`              | 传递 profiler 到 evaluate\_test\_set |
| `tests/test_speed_optimization.py` | 更新测试                              |

## 不修改的文件

* `eval/visualize_profiler.py` — 已通用化，自动适配新阶段

* `eval/evaluators/` — 评估器内部不需要感知 profiler

* `src/pipeline.py` — S6/S7 追踪逻辑不变

