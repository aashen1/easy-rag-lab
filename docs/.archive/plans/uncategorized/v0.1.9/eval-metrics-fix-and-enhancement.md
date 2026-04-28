# 评估指标修复与增强计划

## 问题溯源

审查基线实验报告发现 4 类"结果有误"问题，根本原因均指向代码层面的逻辑缺口：

| 问题 | 表现 | 根因 |
|------|------|------|
| 问题3: 幻觉未充分反映 | q001 faithfulness=0.0 但报告称"答案严格基于检索内容" | 报告模板只看均值，不标红低分个案 |
| 问题4: 检索失败被低估 | 3/20 完全失败但结论称"检索优异" | missing 类型问题所有检索指标都不计算；无按类型分组的聚合 |
| 问题5: 检索多样性差 | top-5 全部来自同一文档 | dedup 指标因数据结构错位永远为 null，无法暴露问题 |
| 问题6: 缺失指标 | chunk/dedup/FPR 全部 N/A | `_evaluate_with_builtin` 未传递关键参数 + 结果字典键名不匹配 |

## 代码根因分析

### 缺口 A: 参数传递断裂（最严重）

`_evaluate_with_builtin()` (run_experiment.py L864-877) 调用 `evaluator.evaluate_single()` 时**缺少 3 个关键参数**：

```python
eval_result = evaluator.evaluate_single(
    ...
    chunk_ids=sample.get("chunk_ids"),
    question_type=sample.get("question_type"),
    retrieved_sources=sample.get("retrieved_sources", []),
    # ❌ 缺少: expected_chunks, equivalence_groups, expect_retrieval
)
```

而 `_collect_rag_samples()` (L780-796) 已经收集了 `expect_retrieval`，`BuiltinEvaluator.evaluate_single()` 也接收这些参数。只是中间没有传递。

**后果**：
- `expect_retrieval` 默认 True → irrelevant 问题仍计算 hit_rate/mrr/ndcg（不应计算）
- `expected_chunks` 默认 None → chunk 级指标永远不计算
- `equivalence_groups` 默认 None → 等价组归一化永远不生效

### 缺口 B: 结果字典键名不匹配

`_evaluate_with_builtin()` (L879-891) 将所有检索指标放入 `result["retrieval"]`：

```python
result = {
    "retrieval": eval_result.retrieval_metrics,  # 包含 chunk_*, dedup_*, false_positive_rate
    ...
}
```

但 `compute_aggregate_metrics()` (L1185-1223) 期望它们在独立键下：

```python
chunk_results = [r for r in results if r.get("chunk_retrieval") is not None]  # 永远为空
dedup_results = [r for r in results if r.get("dedup_retrieval") is not None]  # 永远为空
fpr_results = [r for r in results if r.get("false_positive_rate") is not None]  # 永远为空
```

**后果**：chunk 级、dedup、FPR 的聚合指标永远为 None。

### 缺口 C: missing 类型评估逻辑矛盾

`BuiltinEvaluator.evaluate_single()` 中的条件判断：

- L160: `if expected_sources and expect_retrieval:` → missing 类型因 `expect_retrieval=False` 跳过
- L212: `if not expect_retrieval and not expected_sources:` → missing 类型因 `expected_sources` 非空跳过

**后果**：missing 类型问题**所有检索指标都不计算**，既不算命中也不算误检。

### 缺口 D: 报告模板不标红异常个案

模板报告和 LLM 报告都只关注均值，不突出低分个案（如 faithfulness=0.0 的问题）。

---

## 实施步骤

### Step 1: 修复参数传递断裂（缺口 A）

**文件**: `eval/run_experiment.py`

在 `_evaluate_with_builtin()` 中补充传递 3 个缺失参数：

```python
eval_result = evaluator.evaluate_single(
    question_id=question_id,
    question=sample["question"],
    answer=sample["answer"],
    contexts=sample.get("contexts", []),
    expected_sources=sample.get("expected_sources"),
    expected_answer=sample.get("expected_answer"),
    llm_config=llm_config,
    retrieval_metrics=retrieval_metrics,
    generation_metrics=generation_metrics,
    chunk_ids=sample.get("chunk_ids"),
    question_type=sample.get("question_type"),
    retrieved_sources=sample.get("retrieved_sources", []),
    # ✅ 新增:
    expected_chunks=sample.get("expected_chunks"),
    equivalence_groups=sample.get("equivalence_groups"),
    expect_retrieval=sample.get("expect_retrieval", True),
)
```

同时确保 `_collect_rag_samples()` 收集 `expected_chunks` 和 `equivalence_groups`（当前已收集 `expect_retrieval`，需补充另外两个）。

### Step 2: 修复结果字典键名不匹配（缺口 B）

**文件**: `eval/run_experiment.py`

在 `_evaluate_with_builtin()` 中，将 `eval_result.retrieval_metrics` 按类别拆分到不同键：

```python
retrieval_metrics = eval_result.retrieval_metrics

# 拆分检索指标到不同类别
doc_metrics = {}
chunk_metrics = {}
dedup_metrics = {}
fpr_value = None

for k, v in retrieval_metrics.items():
    if k.startswith("chunk_"):
        chunk_metrics[k.replace("chunk_", "")] = v
    elif k.startswith("dedup_"):
        dedup_metrics[k.replace("dedup_", "")] = v
    elif k == "false_positive_rate":
        fpr_value = v
    else:
        doc_metrics[k] = v

result = {
    "id": question_id,
    "question": sample["question"],
    "answer": sample["answer"],
    "retrieval": doc_metrics,
    "chunk_retrieval": chunk_metrics if chunk_metrics else None,
    "dedup_retrieval": dedup_metrics if dedup_metrics else None,
    "false_positive_rate": fpr_value,
    ...
}
```

### Step 3: 修复 missing 类型评估逻辑（缺口 C）

**文件**: `eval/evaluators/builtin_evaluator.py`

修改 `evaluate_single()` 中的条件判断，让 missing 类型问题也能计算检索指标：

当前逻辑：
- `expect_retrieval=True` → 计算 doc/chunk/dedup 指标
- `expect_retrieval=False and expected_sources=[]` → 计算 FPR

新增逻辑：
- `expect_retrieval=True` → 计算 doc/chunk/dedup 指标（不变）
- `expect_retrieval=False and expected_sources=[]` → 计算 FPR（不变，irrelevant 类型）
- `expect_retrieval=False and expected_sources` → 计算 doc 级指标（新增，missing 类型）
  - 此时 hit_rate=0 表示正确（没检索到关联文档也是对的，因为答案不在文档中）
  - hit_rate=1 表示检索到了关联文档但答案不在其中（检索到了但无法回答）

具体修改：在 L160 的条件中，将 `if expected_sources and expect_retrieval:` 改为 `if expected_sources:`，并在计算结果中标记 `expect_retrieval` 状态，以便聚合时区分。

### Step 4: 补充 _collect_rag_samples 中的数据收集

**文件**: `eval/run_experiment.py`

在 `_collect_rag_samples()` 中补充 `expected_chunks` 和 `equivalence_groups` 的收集：

```python
sample = {
    ...
    "expected_chunks": question_data.get("source_chunks", []),
    "equivalence_groups": meal_info.get("equivalence_groups") if meal_info else None,
    ...
}
```

需要确认 `meal_info` 在调用链中是否可获取。查看 `evaluate_test_set()` 的签名和调用方式来确定数据来源。

### Step 5: 新增检索多样性指标

**文件**: `eval/metrics/retrieval.py`（或新建 `eval/metrics/diversity.py`）

新增 `calculate_retrieval_diversity()` 函数：

```python
def calculate_retrieval_diversity(retrieved_sources: list[str], k: int = 5) -> float:
    """
    计算检索结果的文档多样性：唯一文档数 / min(k, 总结果数)。

    值为 1.0 表示 top-k 全部来自不同文档，
    值接近 0 表示所有结果来自同一文档。

    Args:
        retrieved_sources: 检索到的文档路径列表。
        k: top-k 截断位置。

    Returns:
        多样性比率 [0, 1]。
    """
    top_k = retrieved_sources[:k]
    if not top_k:
        return 0.0
    unique = len(set(normalize_source(s, include_parent=True) for s in top_k))
    return unique / len(top_k)
```

在 `BuiltinEvaluator` 中注册该指标，在 `compute_aggregate_metrics()` 中聚合。

### Step 6: 新增幻觉率指标

**文件**: `eval/metrics/generation.py`

新增 `calculate_hallucination_rate()` 函数：

```python
def calculate_hallucination_rate(faithfulness_scores: list[float], threshold: float = 0.5) -> float:
    """
    计算幻觉率：faithfulness 低于阈值的问题占比。

    Args:
        faithfulness_scores: 各问题的 faithfulness 分数列表。
        threshold: 幻觉判定阈值，默认 0.5。

    Returns:
        幻觉率 [0, 1]。
    """
    if not faithfulness_scores:
        return 0.0
    hallucinated = sum(1 for s in faithfulness_scores if s is not None and s < threshold)
    return hallucinated / len(faithfulness_scores)
```

在 `compute_aggregate_metrics()` 中调用，聚合到报告。

### Step 7: 增强聚合指标——按问题类型分组

**文件**: `eval/run_experiment.py`

在 `compute_aggregate_metrics()` 中新增按问题类型（question_type）分组的指标聚合：

```python
# 按 question_type 分组聚合
type_groups = {}
for r in results:
    qtype = r.get("question_type", "unknown")
    if qtype not in type_groups:
        type_groups[qtype] = []
    type_groups[qtype].append(r)

type_metrics = {}
for qtype, group in type_groups.items():
    type_metrics[qtype] = {
        "count": len(group),
        "avg_hit_rate": ...,
        "avg_mrr": ...,
        "avg_faithfulness": ...,
        ...
    }
metrics["by_question_type"] = type_metrics
```

需要在 `_evaluate_with_builtin()` 的 result dict 中保留 `question_type` 字段。

### Step 8: 增强报告模板——标红异常个案

**文件**: `eval/experiment_reporter.py`

在模板报告的 Recommendations 章节中，新增"异常个案"子章节：

- 列出 faithfulness < 0.5 的问题（幻觉警告）
- 列出 hit_rate = 0 的问题（检索失败）
- 列出 retrieval_diversity < 0.4 的问题（多样性不足）

在 LLM 报告的 prompt 中，增加对异常个案的强调指令。

### Step 9: 编写测试

为所有新增和修改的代码编写 pytest 测试：

1. `tests/test_metrics_diversity.py` — 测试 `calculate_retrieval_diversity`
2. `tests/test_metrics_hallucination.py` — 测试 `calculate_hallucination_rate`
3. 更新 `tests/test_builtin_evaluator.py` — 测试 missing/irrelevant 类型的评估逻辑
4. 更新 `tests/test_run_experiment.py` — 测试参数传递和结果字典结构

### Step 10: 运行 lint 和现有测试

- `pixi run lint` 确保代码格式
- `pixi run pytest` 确保所有测试通过

---

## 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `eval/run_experiment.py` | 修改 | 修复参数传递、结果字典结构、聚合逻辑 |
| `eval/evaluators/builtin_evaluator.py` | 修改 | 修复 missing 类型评估条件 |
| `eval/metrics/retrieval.py` | 修改 | 新增 `calculate_retrieval_diversity` |
| `eval/metrics/generation.py` | 修改 | 新增 `calculate_hallucination_rate` |
| `eval/metrics/__init__.py` | 修改 | 导出新函数 |
| `eval/experiment_reporter.py` | 修改 | 增强报告模板 |
| `tests/test_metrics_diversity.py` | 新建 | 多样性指标测试 |
| `tests/test_metrics_hallucination.py` | 新建 | 幻觉率指标测试 |
| `tests/test_builtin_evaluator.py` | 修改 | 补充 missing/irrelevant 测试 |
| `tests/test_run_experiment.py` | 修改 | 补充参数传递测试 |

---

## 预期效果

修复后重新运行基线实验，报告中将出现：

1. **chunk 级指标**：显示 chunk 粒度的检索精度（不再 N/A）
2. **dedup 指标**：暴露检索结果多样性问题（如去重后 hit_rate 大幅下降）
3. **FPR 指标**：显示 irrelevant 问题的误检率
4. **retrieval_diversity**：直接量化多样性（如 q001 的 0.2 = 5个结果仅1个文档）
5. **hallucination_rate**：标红幻觉问题（如 1/20 = 5%）
6. **by_question_type**：按类型分组，暴露 missing/reasoning 等类型的薄弱环节
7. **异常个案列表**：报告正文中明确列出低分问题
