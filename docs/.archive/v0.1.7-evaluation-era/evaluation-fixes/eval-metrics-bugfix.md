# 评测系统指标计算 Bug 修复与增强

<!-- status: active -->

> 发现日期: 2026-04-20
> 修复日期: 2026-04-20

---

## 一、问题概述

通过对实验报告 `exp_20260420_004941_smoke_quick` 的深入分析，发现评测系统存在以下问题：

| 问题 | 严重程度 | 影响范围 |
|------|----------|----------|
| NDCG 计算值超过 1.0 | 严重 | 所有使用 NDCG 的实验 |
| 缺少 Context Precision / Context Recall | 重要 | 无法对齐业界标准评测 |
| 测试集包含无效问题 | 中等 | 检索指标被人为拉低 |
| 报告缺少 LLM 检索指标展示 | 中等 | 新指标无法在报告中体现 |

---

## 二、Bug 详情：NDCG 计算值超过 1.0

### 2.1 现象

在实验报告 `exp_20260420_004941_smoke_quick` 中：

- 整体 NDCG = **0.9828**，而 Hit Rate 和 MRR 仅为 **0.3333**
- 单个问题 q001 的 NDCG 值为 **2.9485**，远超理论上限 1.0

### 2.2 根因分析

**问题根源**：当检索结果包含重复文档时，DCG 被多次累加。

以实验中的实际情况为例：

```
检索结果: ["2026年光伏行业分析.md", "2026年光伏行业分析.md",
           "2026年光伏行业分析.md", "2026年光伏行业分析.md",
           "2026年光伏行业分析.md"]

期望文档: ["2026年光伏行业分析.md"]
```

**旧代码逻辑**：

```python
# 旧代码：直接遍历所有检索结果
dcg = 0.0
for i, source in enumerate(retrieved_normalized):
    if source in expected_set and source in relevance_scores:
        rel = relevance_scores[source]
        dcg += (2**rel - 1) / math.log2(i + 2)
```

当同一文档出现 5 次时：
- DCG = 1/log2(2) + 1/log2(3) + 1/log2(4) + 1/log2(5) + 1/log2(6) = **2.9485**
- IDCG = 1/log2(2) = **1.0**
- NDCG = 2.9485 / 1.0 = **2.9485** ← 超过 1.0！

### 2.3 为什么会出现重复文档

在 RAG 系统中，同一文档的不同 chunk 可能被同时检索出来，而这些 chunk 的 `source` 字段都指向同一个文档。这在以下场景中尤其常见：

- 文档被切分为多个 chunk
- 多个 chunk 与查询高度相关
- 检索结果未按文档去重

### 2.4 修复方案

**核心思路**：对检索结果去重，只保留每个文档的首次出现位置。

```python
# 新代码：先去重再计算
seen: set = set()
unique_retrieved: List[str] = []
for source in retrieved_normalized:
    if source not in seen:
        seen.add(source)
        unique_retrieved.append(source)

dcg = 0.0
for i, source in enumerate(unique_retrieved):
    if source in expected_set and source in relevance_scores:
        rel = relevance_scores[source]
        dcg += (2**rel - 1) / math.log2(i + 2)

# ... 计算 IDCG ...

ndcg = dcg / ideal_dcg

# 防御性边界检查
return min(1.0, max(0.0, ndcg))
```

**修复后效果**：

```
检索结果: [doc1, doc1, doc1, doc1, doc1]  (去重后: [doc1])
期望文档: [doc1]

DCG = 1/log2(2) = 1.0
IDCG = 1/log2(2) = 1.0
NDCG = 1.0 / 1.0 = 1.0  ✓ 在 [0, 1] 范围内
```

---

## 三、新增指标：Context Precision 与 Context Recall

### 3.1 为什么需要这两个指标

参考 RAGAS 和 DeepEval 等生产级评测框架，传统的 Hit Rate / MRR / NDCG 只能衡量"是否检索到正确文档"，但无法回答：

1. **检索到的上下文是否真的与问题相关？**（Context Precision）
2. **Ground Truth 中的信息是否都能从检索上下文中推断出来？**（Context Recall）

这两个指标使用 **LLM-as-a-judge** 方式，更贴近真实场景。

### 3.2 Context Precision（上下文精确率）

**来源**：DeepEval

**公式**：

```
Context Precision = (1/N) × Σ(Precision@k × r_k)
```

其中：
- N = 相关上下文数量
- Precision@k = 前 k 个位置中相关上下文的比例
- r_k = 第 k 个上下文是否相关（1 或 0）

**含义**：衡量检索系统是否将相关上下文排在无关上下文之前。强调顶部结果的排序质量。

**示例**：

```
问题: "2025年光伏新增装机容量是多少？"
检索上下文: [相关, 无关, 相关, 无关, 无关]

Precision@1 = 1/1 = 1.0  (r_1=1)
Precision@2 = 1/2 = 0.5  (r_2=0, 不计入)
Precision@3 = 2/3 = 0.67 (r_3=1)

Context Precision = (1/2) × (1.0 + 0.67) = 0.835
```

### 3.3 Context Recall（上下文召回率）

**来源**：RAGAS

**公式**：

```
Context Recall = 可推断句子数 / Ground Truth 总句子数
```

**含义**：衡量 Ground Truth 中的信息是否都能从检索上下文中推断出来。

**示例**：

```
Ground Truth: "贵州茅台2023年实现营业收入1505.60亿元，同比增长18.04%。"

句子1: "贵州茅台2023年实现营业收入1505.60亿元" → 可推断 ✓
句子2: "同比增长18.04%" → 可推断 ✓

Context Recall = 2/2 = 1.0
```

---

## 四、问题有效性检查

> **注意**：此方案已在后续验收中被判定为方向错误并移除。详见 [评测系统验收修复报告](eval-system-acceptance-fix.md)。
>
> 正确做法：不是在评测时过滤无效问题，而是在问题生成阶段正确设置 `source_files`。
> - irrelevant 类型：`source_files = []`，`expect_retrieval = False`
> - missing 类型：保留 `source_files`，`expect_no_answer = True`

### 4.1 问题描述

在实验 `exp_20260420_004941_smoke_quick` 中，6 个测试问题中有 4 个（q003-q006）的 `expected_sources` 指向不在检索库中的文档。这些"不可能命中"的问题会人为拉低检索指标。

### 4.2 解决方案

新增 `validate_question()` 和 `filter_valid_questions()` 函数：

```python
from eval.metrics import validate_question, filter_valid_questions

# 验证单个问题
validity = validate_question(
    question={"source_files": ["doc1.pdf"]},
    corpus_sources={"doc1", "doc2", "doc3"}
)
# validity.is_valid = True

# 批量过滤
valid_questions = filter_valid_questions(questions, corpus_sources)
```

---

## 五、新系统使用指南

### 5.1 配置 LLM 检索指标

在实验配置中添加 `llm_retrieval_metrics`：

```yaml
evaluation:
  llm_preset: "default"
  llm_retrieval_metrics:
    - "context_precision"
    - "context_recall"
```

### 5.2 在代码中使用新指标

#### 方式一：通过 run_evaluation 函数

```python
from eval.run_eval import run_evaluation

summary = run_evaluation(
    pipeline=pipeline,
    test_data_path="data/meals/smoke_quick/test_sets/document_level_n6.json",
    output_dir="data/eval",
    metrics_config=["hit_rate", "mrr", "ndcg"],
    generation_metrics_config=["faithfulness", "answer_relevancy"],
    llm_retrieval_metrics_config=["context_precision", "context_recall"],
    llm_config={
        "api_key": "your-api-key",
        "base_url": "https://api.longcat.chat/anthropic",
        "model_name": "LongCat-Flash-Lite",
    },
)
```

#### 方式二：通过实验配置文件

```yaml
evaluation:
  llm_preset: "default"
  llm_retrieval_metrics:
    - "context_precision"
    - "context_recall"
```

### 5.3 使用问题有效性检查

```python
from eval.metrics import validate_question, filter_valid_questions

# 获取检索库中的文档列表
corpus_sources = {"2026年光伏行业分析", "光模块设备行业深度", "格力电器2024年年度报告"}

# 过滤无效问题
valid_questions = filter_valid_questions(test_questions, corpus_sources)

# 查看过滤结果
print(f"原始问题数: {len(test_questions)}")
print(f"有效问题数: {len(valid_questions)}")
```

### 5.4 指标选择建议

| 场景 | 推荐指标组合 | 说明 |
|------|-------------|------|
| 快速验证 | Hit Rate, MRR | 无需 LLM，速度快 |
| 标准评测 | Hit Rate, MRR, NDCG, Faithfulness | 覆盖检索+生成 |
| 深度评测 | 全部指标 | 含 Context Precision/Recall，对齐业界标准 |
| 检索调优 | Hit Rate, MRR, NDCG, Context Precision | 专注检索质量 |
| 生成调优 | Faithfulness, Answer Relevancy, Context Recall | 专注生成质量 |

### 5.5 指标成本参考

| 指标 | 是否需要 LLM | 单问题 Token 消耗 | 建议场景 |
|------|-------------|-------------------|----------|
| Hit Rate | 否 | 0 | 所有场景 |
| MRR | 否 | 0 | 所有场景 |
| NDCG | 否 | 0 | 所有场景 |
| Context Precision | 是 | ~500-1000 | 深度评测 |
| Context Recall | 是 | ~300-800/句子 | 深度评测 |
| Faithfulness | 是 | ~1000-2000 | 生成质量评测 |
| Answer Relevancy | 是 | ~500-1000 | 生成质量评测 |

---

## 六、修复前后对比

### 6.1 NDCG 修复效果

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 无重复文档 | 正确 | 正确 |
| 1 个文档重复 5 次 | **2.95** (错误) | **1.0** (正确) |
| 混合重复 | 可能 > 1.0 | 始终 ≤ 1.0 |

### 6.2 指标体系对比

| 指标类别 | 修复前 | 修复后 |
|----------|--------|--------|
| 检索指标 | Hit Rate, MRR, NDCG (有Bug) | Hit Rate, MRR, NDCG (修复), Context Precision, Context Recall |
| 生成指标 | Faithfulness, Answer Relevancy | Faithfulness, Answer Relevancy |
| 质量保障 | 无 | 问题有效性检查 |

### 6.3 实验报告展示对比

修复前报告表格：

```
| Variant | Hit Rate | MRR | NDCG | Faithfulness | Relevancy |
```

修复后报告表格（启用新指标时）：

```
| Variant | Hit Rate | MRR | NDCG | CP | CR | Faithfulness | Relevancy |
```

---

## 七、相关提交记录

| 提交 | 说明 |
|------|------|
| `46b5275` | fix: add deduplication to NDCG calculation to ensure value in [0,1] |
| `05d1d08` | test: add NDCG deduplication test cases |
| `d3368e5` | feat: add Context Precision and Context Recall metrics |
| `0e9a203` | test: add unit tests for Context Precision and Context Recall |
| `07ee01d` | feat: integrate Context Precision and Context Recall into evaluation pipeline |
| `320983c` | feat: update experiment reporter to display LLM retrieval metrics |
| `77963f1` | feat: add question validity check functionality |

---

## 八、相关文档

- [评测指标详解](../guides/evaluation-metrics.md)
- [实验系统指南](../guides/experiment-system.md)
- [RAGAS Documentation](https://docs.ragas.io/)
- [DeepEval Contextual Precision](https://www.deepeval.com/docs/metrics-contextual-precision)
