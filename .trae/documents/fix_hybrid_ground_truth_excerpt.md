# 修复 Hybrid 策略问题集对全部评测指标的严格支持

## 问题根因

Hybrid 策略生成的测试集**缺少 `ground_truth_excerpt` 字段**，导致两条评测链路中 4 个指标无法严格计算：

| 指标 | 链路 | 严格定义所需 | 当前实际获得 | 状态 |
|------|------|------------|------------|------|
| context_precision | Builtin | 原文摘录作为 expected_output | LLM 生成的 answer | ⚠️ 偏差 |
| context_recall | Builtin | 原文摘录作为 ground_truth | LLM 生成的 answer | ⚠️ 偏差 |
| answer_correctness | RAGAS | 原文摘录作为 reference | LLM 生成的 answer | ❌ 循环论证 |
| semantic_similarity | RAGAS | 原文摘录作为 reference | LLM 生成的 answer | ❌ 循环论证 |

**数据流链路**：`ground_truth_excerpt` → `sample["ground_truth_excerpt"]` → `expected_answer`(Builtin) / `reference`(RAGAS) → 指标计算函数

**回退逻辑**：当 `ground_truth_excerpt` 缺失时，系统回退到 `question_data["answer"]`（LLM 生成的答案），这不是原文摘录，无法满足上述指标的严格定义。

## 修复方案

### Step 1: 在 `_generate_hybrid_question` 中生成 `ground_truth_excerpt`

**文件**: `src/test_generator.py` L1707-1808

在 `_generate_hybrid_question` 方法中，证据验证通过后、设置 `source_chunks` 之后，从验证通过的 evidence 中提取 quote 拼接为 `ground_truth_excerpt`：

```python
# 在 qa["source_chunks"] = source_chunks 之后添加：
verified_quotes = [
    e["quote"]
    for e in validation["verified_evidence"]
    if e.get("verified", False) and e.get("quote", "").strip()
]
qa["ground_truth_excerpt"] = "\n".join(verified_quotes) if verified_quotes else ""
```

对不同问题类型的处理：
- **single_fact/multi_fact/reasoning/comparative**：使用验证通过的 quote 拼接
- **missing**：`ground_truth_excerpt = ""`（文档确实不包含答案）
- **irrelevant**：`ground_truth_excerpt = ""`（与文档无关）

### Step 2: 在主循环和补充循环中确保 `ground_truth_excerpt` 被正确设置

**文件**: `src/test_generator.py` L1513-1530（主循环）和 L1580-1594（补充循环）

当前代码在主循环中对 irrelevant/missing 类型设置了 `source_files`、`source_chunks`、`expect_retrieval`、`expect_no_answer`，但未设置 `ground_truth_excerpt`。需要确保：

1. `_generate_hybrid_question` 返回的 qa 字典中已包含 `ground_truth_excerpt`
2. 对 irrelevant/missing 类型，显式设置 `ground_truth_excerpt = ""`

### Step 3: 在 `_generate_hybrid_question` 中对 irrelevant/missing 类型补充 `ground_truth_excerpt`

**文件**: `src/test_generator.py` L1755-1763

当前代码中，irrelevant 类型直接返回 qa（跳过证据验证），missing 类型在无 evidence 时也直接返回。这两个类型返回的 qa 字典中没有 `ground_truth_excerpt`。需要在这两个分支中添加：

```python
if question_type == "irrelevant":
    qa["ground_truth_excerpt"] = ""
    return qa

# missing 类型无 evidence 时：
if not evidence_list:
    if question_type == "missing":
        qa["ground_truth_excerpt"] = ""
        return qa
```

### Step 4: 创建 `baseline_500page` 实验配置

**文件**: `exp_configs/baseline/baseline_500page.yaml`（新建）

基于 `baseline_1kpage.yaml` 模板，创建 500 页配置，关键差异：
- `sample_pages: 500`
- `strategy: "hybrid"`（使用新策略）
- `num_questions: 20`
- `backends: ["builtin", "ragas"]`（双后端）
- 包含所有指标（含 context_precision、context_recall、answer_correctness、semantic_similarity）

### Step 5: 运行实验验证

```bash
pixi run exp baseline/baseline_500page
```

### Step 6: 分析实验结果

检查实验输出中：
1. 所有指标是否都有有效值（非 None/NaN）
2. context_precision/context_recall 的值是否合理（用原文摘录作 reference 应比用 LLM answer 更准确）
3. answer_correctness/semantic_similarity 是否正常计算
4. 检查 irrelevant/missing 类型问题是否正确跳过需要 reference 的指标

## 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `src/test_generator.py` | 编辑 | 在 `_generate_hybrid_question` 中生成 `ground_truth_excerpt` |
| `exp_configs/baseline/baseline_500page.yaml` | 新建 | 500 页实验配置 |

## 不需要修改的文件

- `eval/run_experiment.py`：已有 `ground_truth_excerpt` 的传递逻辑（L893, L922, L979）
- `eval/evaluators/builtin_evaluator.py`：已有 `expected_answer` 参数的使用逻辑
- `eval/evaluators/ragas_evaluator.py`：已有 `reference` 的获取逻辑（L233）
- 评测管线的数据流已完整，只需在源头（test_generator）生成 `ground_truth_excerpt` 即可

## 预期效果

修复后，两条链路所有指标的支持状态：

| 指标 | 链路 | 修复前 | 修复后 |
|------|------|--------|--------|
| hit_rate/mrr/ndcg | Builtin | ✅ | ✅ |
| chunk_hit_rate/mrr/ndcg | Builtin | ✅ | ✅ |
| dedup_hit_rate/mrr/ndcg | Builtin | ✅ | ✅ |
| false_positive_rate | Builtin | ✅ | ✅ |
| retrieval_diversity | Builtin | ✅ | ✅ |
| context_precision | Builtin | ⚠️ | ✅ |
| context_recall | Builtin | ⚠️ | ✅ |
| faithfulness | Builtin | ✅ | ✅ |
| answer_relevancy | Builtin | ✅ | ✅ |
| faithfulness | RAGAS | ✅ | ✅ |
| answer_relevancy | RAGAS | ✅ | ✅ |
| context_precision | RAGAS | ⚠️ | ✅ |
| context_recall | RAGAS | ⚠️ | ✅ |
| answer_correctness | RAGAS | ❌ | ✅ |
| semantic_similarity | RAGAS | ❌ | ✅ |
