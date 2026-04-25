# Irrelevant Question Metrics Fix

> 修复日期：2026-04-26
> 关联 BUG：BUG-029, BUG-030, BUG-031
> 关联优化：OPT-004（Recall@3/5/10 验证通过）

## 1. 问题描述

在运行 `pixi run exp quick_verify_metrics_tmp` 对 hybrid 策略生成的测试集进行全指标验收时，发现 irrelevant 类型问题（`expect_retrieval=False`）的多个评测指标产出了不可信的数值。

### 1.1 BUG-029：Builtin context_precision/context_recall 使用错误 ground truth

**现象**：irrelevant 问题的 `context_precision` 和 `context_recall` 产出了看似合理的数值（0.0~1.0），但这些数值毫无意义。

**根因**：`builtin_evaluator.py` 中 `context_precision` 和 `context_recall` 的计算条件仅检查 `llm_config and contexts`，未检查 `expect_retrieval`。对 irrelevant 问题，`ground_truth_excerpt=""` 是 falsy，通过 `expected_answer or ""` 的 `or` 运算回退到了 `expected_answer`（即测试集中 LLM 生成的答案），导致：

- q004 的 `context_recall=1.0`：LLM 答案"该问题与文档内容无关"被判定为可从上下文推断
- q005 的 `context_recall=0.5`：1/2 句子被判定可推断

这些数值完全无意义，因为 irrelevant 问题本就不应有 ground truth。

### 1.2 BUG-030：RAGAS answer_correctness/semantic_similarity 循环论证

**现象**：irrelevant 问题的 `answer_correctness` 高达 0.92~0.96，`semantic_similarity` 高达 0.69~0.86。

**根因**：`ragas_evaluator.py` 中 `reference = sample.get("ground_truth_excerpt") or sample.get("expected_answer")`，对 irrelevant 问题 `ground_truth_excerpt=""` 是 falsy，回退到 `expected_answer`（LLM 生成的答案）。这导致 RAGAS 用 LLM 答案评估 LLM 答案——循环论证，数值虚高。

### 1.3 BUG-031：expected_answer fallback 不区分问题类型

**现象**：上述两个 BUG 的共同根因。

**根因**：`run_experiment.py` 中 `expected_answer = sample.get("ground_truth_excerpt") or sample.get("expected_answer")`，使用 Python 的 `or` 运算做 fallback，不区分问题类型。对 irrelevant 问题，`ground_truth_excerpt=""` 是 falsy，无条件回退到 `expected_answer`。

## 2. 修复方案

### 2.1 BUG-029 修复

**文件**：`eval/evaluators/builtin_evaluator.py`

**修改**：将 context_precision/context_recall 的计算条件从 `if llm_config and contexts:` 改为 `if llm_config and contexts and expect_retrieval and expected_answer:`。

同时移除 `expected_answer or ""` 的 fallback，因为现在 `expected_answer` 为 None 时整个条件不满足，不会进入计算。

```python
# Before
if llm_config and contexts:
    if "context_precision" in retrieval_metrics:
        cp_score = calculate_context_precision(
            expected_output=expected_answer or "",  # ← 错误回退
            ...
        )

# After
if llm_config and contexts and expect_retrieval and expected_answer:
    if "context_precision" in retrieval_metrics:
        cp_score = calculate_context_precision(
            expected_output=expected_answer,  # ← 直接使用，无需 fallback
            ...
        )
```

### 2.2 BUG-030 修复

**文件**：`eval/evaluators/ragas_evaluator.py`

**修改**：仅在 `expect_retrieval=True` 时才回退到 `expected_answer`，并将空 reference 设为 `None`。

```python
# Before
reference = sample.get("ground_truth_excerpt") or sample.get("expected_answer")
ragas_sample = SingleTurnSample(..., reference=reference)

# After
reference = sample.get("ground_truth_excerpt")
if not reference and sample.get("expect_retrieval", True):
    reference = sample.get("expected_answer")
ragas_sample = SingleTurnSample(..., reference=reference if reference else None)
```

**文件**：`eval/run_experiment.py`

**修改**：在 RAGAS 结果处理中，过滤掉 irrelevant 问题的 reference-required 生成指标。

```python
for k, v in eval_result.generation_metrics.items():
    if k in retrieval_metric_names:
        if expect_retrieval:
            llm_retrieval_part[k] = v
    else:
        if not expect_retrieval and k in (
            "answer_correctness",
            "semantic_similarity",
        ):
            continue
        generation_part[k] = v
```

### 2.3 BUG-031 修复

**文件**：`eval/run_experiment.py`

**修改**：expected_answer 仅在 `expect_retrieval=True` 时回退。

```python
# Before
expected_answer = sample.get("ground_truth_excerpt") or sample.get("expected_answer")

# After
expected_answer = sample.get("ground_truth_excerpt")
if not expected_answer and sample.get("expect_retrieval", True):
    expected_answer = sample.get("expected_answer")
```

## 3. 验证方法

### 3.1 实验配置

使用 `exp_configs/quick_verify_metrics_tmp.yaml`，配置了 hybrid 策略、6 个问题、全指标验证。运行命令：

```bash
pixi run exp quick_verify_metrics_tmp
```

### 3.2 修复前后对比

#### Builtin 链路 — irrelevant 问题

| 问题 | 指标 | 修复前 | 修复后 | 判定 |
|------|------|--------|--------|------|
| q002 | context_precision | 0.0 | 未计算 | ✅ |
| q002 | context_recall | 0.0 | 未计算 | ✅ |
| q004 | context_precision | 0.0 | 未计算 | ✅ |
| q004 | context_recall | **1.0** | 未计算 | ✅ |
| q005 | context_precision | 0.0 | 未计算 | ✅ |
| q005 | context_recall | **0.5** | 未计算 | ✅ |
| q006 | context_precision | 0.0 | 未计算 | ✅ |
| q006 | context_recall | 0.0 | 未计算 | ✅ |

#### RAGAS 链路 — irrelevant 问题

| 问题 | 指标 | 修复前 | 修复后 | 判定 |
|------|------|--------|--------|------|
| q002 | answer_correctness | 0.9223 | 已过滤 | ✅ |
| q002 | semantic_similarity | 0.6894 | 已过滤 | ✅ |
| q004 | answer_correctness | 0.6483 | 已过滤 | ✅ |
| q004 | semantic_similarity | 0.5932 | 已过滤 | ✅ |
| q005 | answer_correctness | **0.9645** | 已过滤 | ✅ |
| q005 | semantic_similarity | **0.8579** | 已过滤 | ✅ |
| q006 | answer_correctness | 0.8951 | 已过滤 | ✅ |
| q006 | semantic_similarity | 0.5804 | 已过滤 | ✅ |

#### Builtin 链路 — relevant 问题（确认无回归）

| 指标 | q001 | q003 | 判定 |
|------|------|------|------|
| hit_rate | 1.0 | 1.0 | ✅ |
| mrr | 1.0 | 1.0 | ✅ |
| ndcg | 1.0 | 1.0 | ✅ |
| recall_3 | 1.0 | 1.0 | ✅ |
| recall_5 | 1.0 | 1.0 | ✅ |
| recall_10 | 1.0 | 1.0 | ✅ |
| chunk_hit_rate | 1.0 | 1.0 | ✅ |
| chunk_mrr | 1.0 | 1.0 | ✅ |
| chunk_ndcg | 1.0 | 0.6131 | ✅ |
| dedup_hit_rate | 1.0 | 1.0 | ✅ |
| dedup_mrr | 1.0 | 1.0 | ✅ |
| dedup_ndcg | 1.0 | 1.0 | ✅ |
| context_precision | 1.0 | 1.0 | ✅ |
| context_recall | 1.0 | 0.3333 | ✅ |
| faithfulness | 1.0 | 1.0 | ✅ |
| answer_relevancy | 0.97 | 0.93 | ✅ |

#### RAGAS 链路 — relevant 问题（确认无回归）

| 指标 | q001 | q003 | 判定 |
|------|------|------|------|
| faithfulness | 1.0 | 0.9524 | ✅ |
| answer_relevancy | 0.7656 | 0.5535 | ✅ |
| answer_correctness | 0.8092 | 0.5295 | ✅ |
| semantic_similarity | 0.8370 | 0.9179 | ✅ |
| context_precision | ~1.0 | 0.8333 | ✅ |
| context_recall | 1.0 | 0.6667 | ✅ |

### 3.3 判定标准

1. **irrelevant 问题**：context_precision/context_recall/answer_correctness/semantic_similarity 不应计算（或被过滤），不应出现数值
2. **relevant 问题**：所有指标数值与修复前一致，无回归
3. **FPR**：irrelevant 问题的 FPR=1.0 正确（5/5 检索结果均为误检）
4. **recall@3/5/10**：首次在实验中验证，数值合理

## 4. 附注

### 4.1 Recall@3/5/10 验证（OPT-004）

本次实验首次在配置中显式列出 `recall_3`/`recall_5`/`recall_10`，验证了这三个指标可以正确计算。注意：必须在 YAML 配置的 `evaluation.metrics.retrieval` 中显式列出，否则不会计算（不在 `BuiltinEvaluator._retrieval_metrics` 默认列表中）。

### 4.2 RAGAS KeyError 警告

修复后 RAGAS 对 irrelevant 问题（`reference=None`）会抛出 `KeyError('reference')` 内部异常，但不影响最终结果——RAGAS 返回 NaN，被 `run_experiment.py` 的过滤逻辑正确跳过。这是 RAGAS 框架行为，非我方 BUG。

### 4.3 测试集类型分布偏斜

6 题中 4 题为 irrelevant（66.7%），远超配置的 33%。原因是小样本下取整导致。正式实验应增大 `num_questions` 以获得更均衡的分布。
