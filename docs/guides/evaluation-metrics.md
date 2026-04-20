# 评测指标详解

<!-- status: active -->

> 最后更新: 2026-04-21

本文档详细说明 RAG 评测系统中各个指标的含义、计算方法和改进建议。

---

## 概述

评测系统提供两类指标，并支持两种评测后端：

| 类别 | 指标 | 评测对象 | 可用后端 |
|------|------|---------|---------|
| **检索指标** | Hit Rate, MRR, NDCG | 检索结果质量 | builtin |
| **生成质量指标** | Faithfulness, Answer Relevancy | 回答内容质量 | builtin, ragas |
| **RAGAS 生成指标** | Context Precision, Context Recall, Factual Correctness, Semantic Similarity | 回答与检索质量 | ragas |

> 关于 RAGAS 后端的详细使用方法，请参阅 [RAGAS 评测系统指南](ragas-evaluation.md)。

---

## 检索指标

### Hit Rate（命中率）

**定义**：检索结果中是否包含至少一个相关文档。

**计算方法**：

```
Hit Rate@k = 1.0  (如果 top-k 结果中包含相关文档)
Hit Rate@k = 0.0  (否则)
```

**取值范围**：0.0 - 1.0

**示例**：

| 检索结果 | 相关文档 | Hit Rate@5 |
|---------|---------|------------|
| [doc1, doc2, doc3, doc4, doc5] | doc3 | 1.0 |
| [doc1, doc2, doc4, doc5, doc6] | doc3 | 0.0 |

**解读**：
- **0.8+**：检索效果优秀
- **0.5-0.8**：检索效果一般，有改进空间
- **< 0.5**：检索效果较差，需要优化

**改进建议**：
- 调整 `chunk_size` 和 `chunk_overlap`
- 尝试不同的 embedding 模型
- 增加 `top_k` 值
- 考虑混合检索（BM25 + 向量）

---

### MRR（平均倒数排名）

**定义**：第一个相关文档在检索结果中的排名的倒数。

**计算方法**：

```
RR = 1 / rank  (rank 为第一个相关文档的位置，从 1 开始)
MRR = 平均(RR)  (跨多个查询)
```

**取值范围**：0.0 - 1.0

**示例**：

| 检索结果 | 相关文档 | 第一个相关位置 | RR |
|---------|---------|---------------|-----|
| [doc1, doc2, doc3, doc4, doc5] | doc2 | 2 | 0.5 |
| [doc1, doc2, doc3, doc4, doc5] | doc1 | 1 | 1.0 |
| [doc1, doc2, doc3, doc4, doc5] | doc5 | 5 | 0.2 |

**解读**：
- **0.7+**：相关文档排名靠前，效果优秀
- **0.4-0.7**：相关文档排名中等
- **< 0.4**：相关文档排名靠后，需要优化

**改进建议**：
- 优化 embedding 模型
- 考虑添加 Reranker 重排
- 优化查询理解（查询改写、扩展）

---

### NDCG（归一化折损累积增益）

**定义**：综合考虑所有相关文档的排序位置，位置越靠前权重越高。

**计算方法**：

```
DCG@k = Σ (2^rel_i - 1) / log2(i + 2)
NDCG@k = DCG@k / IDCG@k
```

其中：
- `rel_i` 是第 i 个文档的相关性分数
- `IDCG@k` 是理想情况下的 DCG（所有相关文档排在最前面）

**取值范围**：0.0 - 1.0

**示例**：

假设有 3 个相关文档，相关性分数均为 1：

| 检索结果位置 | 文档 | 相关性 | DCG 贡献 |
|-------------|------|--------|---------|
| 1 | doc1 | 1 | 1.0 |
| 2 | doc2 | 0 | 0 |
| 3 | doc3 | 1 | 0.63 |
| 4 | doc4 | 0 | 0 |
| 5 | doc5 | 1 | 0.5 |

**解读**：
- **0.8+**：排序质量优秀
- **0.5-0.8**：排序质量中等
- **< 0.5**：排序质量较差

**改进建议**：
- 添加 Reranker 重排
- 优化相关性建模
- 考虑多级相关性标注

---

## 生成质量指标

### Faithfulness（忠实度）

**定义**：回答中的事实陈述是否可以从检索到的上下文中推导出来。

**计算方法**：

1. 从回答中提取所有事实陈述（statements）
2. 对每个陈述，判断是否可从上下文推导
3. 计算可推导陈述的比例

```
Faithfulness = 可推导陈述数 / 总陈述数
```

**取值范围**：0.0 - 1.0

**示例**：

**问题**：贵州茅台2023年营收是多少？

**上下文**：贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元，同比增长18.04%。

**回答**：贵州茅台2023年实现营业收入1505.60亿元，同比增长约18%。

**分析**：
- 陈述1："贵州茅台2023年实现营业收入1505.60亿元" → 可推导 ✓
- 陈述2："同比增长约18%" → 可推导 ✓

**Faithfulness = 1.0**

**解读**：
- **0.9+**：回答高度可信，几乎没有幻觉
- **0.7-0.9**：回答基本可信，有少量推断
- **0.5-0.7**：回答部分可信，存在明显推断
- **< 0.5**：回答可信度低，可能存在幻觉

**改进建议**：
- 优化 prompt，要求回答必须引用上下文
- 降低 LLM temperature
- 增加检索上下文的相关性
- 添加引用标注要求

---

### Answer Relevancy（回答相关性）

**定义**：回答与问题的相关程度，从多个维度评估。

**评估维度**：

| 维度 | 说明 | 评分标准 |
|------|------|---------|
| 直接相关性 | 回答是否直接针对问题 | 1-5 分 |
| 信息充分性 | 回答是否提供足够信息 | 1-5 分 |
| 简洁聚焦性 | 回答是否避免无关信息 | 1-5 分 |

**计算方法**：

通过 LLM 评估，综合三个维度得出 0.0-1.0 的分数。

**示例**：

**问题**：光模块行业2024年的市场规模是多少？

**回答 A**：根据报告，2024年全球光模块市场规模约为120亿美元。（相关性：0.9）

**回答 B**：光模块是一种用于光纤通信的器件，市场规模方面，2024年全球约为120亿美元，主要厂商包括...（相关性：0.7）

**回答 C**：光模块行业近年来发展迅速。（相关性：0.3）

**解读**：
- **0.8+**：回答高度相关，切中问题核心
- **0.5-0.8**：回答部分相关，存在偏题或冗余
- **< 0.5**：回答相关性低，答非所问

**改进建议**：
- 优化 prompt，要求回答简洁聚焦
- 提高检索结果的相关性
- 添加问题类型识别，针对性回答

---

## LLM 检索指标

### Context Precision（上下文精确率）

**定义**：衡量检索系统是否将相关上下文排在无关上下文之前。

**来源**：DeepEval / RAGAS

**计算方法**：

```
Context Precision = (1/N) × Σ(Precision@k × r_k)
```

其中：
- N = 相关上下文数量
- Precision@k = 前 k 个位置中相关上下文的比例
- r_k = 第 k 个上下文是否相关（1 或 0）

**取值范围**：0.0 - 1.0

**与 Hit Rate / NDCG 的区别**：

| 指标 | 评测对象 | 是否需要 LLM | 关注点 |
|------|---------|-------------|--------|
| Hit Rate | 文档是否命中 | 否 | 是否检索到 |
| NDCG | 文档排序质量 | 否 | 排序位置 |
| Context Precision | 上下文相关性与排序 | 是 | 内容是否相关 + 排序质量 |

**解读**：
- **0.8+**：检索结果高度相关且排序合理
- **0.5-0.8**：部分检索结果不相关或排序不佳
- **< 0.5**：检索结果相关性差或排序混乱

**改进建议**：
- 优化 Reranker 重排模型
- 提高 embedding 模型质量
- 优化 chunk 策略，提高 chunk 与查询的相关性

---

### Context Recall（上下文召回率）

**定义**：Ground Truth / 参考答案中的信息是否都能从检索上下文中推断出来。

**来源**：RAGAS

**计算方法**：

1. 将 Ground Truth 分割成句子/陈述
2. 对每个句子，判断是否可从检索上下文中推断
3. 计算可推断句子的比例

```
Context Recall = 可推断句子数 / Ground Truth 总句子数
```

**取值范围**：0.0 - 1.0

**示例**：

**Ground Truth**：贵州茅台2023年实现营业收入1505.60亿元，同比增长18.04%。

**检索上下文**：贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元。

**分析**：
- 句子1："贵州茅台2023年实现营业收入1505.60亿元" → 可推断 ✓
- 句子2："同比增长18.04%" → 不可推断 ✗

**Context Recall = 0.5**

**解读**：
- **0.9+**：检索上下文几乎覆盖所有需要的信息
- **0.7-0.9**：大部分信息可推断，有少量遗漏
- **0.5-0.7**：信息覆盖不足，需要增加检索量
- **< 0.5**：检索上下文严重不足

**改进建议**：
- 增加 `top_k` 值
- 优化 chunk 大小，确保关键信息完整
- 考虑混合检索（BM25 + 向量）

---

## RAGAS 特有生成指标

以下指标由 RAGAS 评测后端提供，需要在配置中启用 `ragas` 后端。

### Factual Correctness（事实正确性）

**定义**：回答与参考答案的事实一致性，基于 claim-level 对比。

**计算方法**：

1. 从回答和参考答案中分别提取事实声明（claims）
2. 计算回答 claims 相对于参考答案 claims 的覆盖度

**取值范围**：0.0 - 1.0

**所需输入**：response, **reference**（参考答案）

**解读**：
- **0.8+**：回答事实与参考高度一致
- **0.5-0.8**：部分事实存在偏差
- **< 0.5**：事实偏差较大

> 此指标高度依赖参考答案的质量。

---

### Semantic Similarity（语义相似度）

**定义**：回答与参考答案的语义相似度，基于 Embedding 向量的余弦相似度。

**计算方法**：

1. 将回答和参考答案分别编码为向量
2. 计算余弦相似度

**取值范围**：0.0 - 1.0

**所需输入**：response, **reference**（参考答案）

**解读**：
- **0.9+**：语义高度相似
- **0.7-0.9**：语义基本相似
- **< 0.7**：语义差异较大

---

## 问题类型的检索指标适用性

### 设计原则

评测系统生成 6 种问题类型，其中 irrelevant 和 missing 类型用于测试系统的拒答能力。不同类型对检索指标的适用性不同：

| 问题类型 | 检索指标 | 生成指标 | 标记 | 说明 |
|----------|---------|---------|------|------|
| single_fact | 适用 | 适用 | — | 标准评测 |
| multi_fact | 适用 | 适用 | — | 标准评测 |
| reasoning | 适用 | 适用 | — | 标准评测 |
| comparative | 适用 | 适用 | — | 标准评测 |
| missing | 适用 | 适用 | `expect_no_answer=True` | 测试"不知道"能力 |
| irrelevant | **不适用** | 适用 | `expect_retrieval=False` | 测试拒答能力 |

### irrelevant 类型

irrelevant 问题故意与文档主题无关，测试系统的拒答能力。这类问题：

- `source_files = []`：不期望检索到任何相关文档
- `expect_retrieval = False`：跳过检索指标计算
- 生成指标正常计算（关注是否正确拒答）

### missing 类型

missing 问题询问文档中没有的信息，测试系统处理"不知道"的能力。这类问题：

- `source_files = [source_path]`：文档主题相关，检索器可能正确返回该文档
- `expect_no_answer = True`：标记期望系统拒答
- 检索指标正常计算

### 聚合指标

聚合指标区分"适用检索指标的问题数"和"总问题数"：

```python
metrics = compute_aggregate_metrics(results)
# metrics["retrieval_applicable_questions"]  # 参与检索指标计算的问题数
# metrics["total_questions"]                  # 总问题数（含 irrelevant）
```

---

## 指标对比

| 指标 | 评测阶段 | 是否需要 LLM | 需要 reference | 计算成本 | 可用后端 |
|------|---------|-------------|---------------|---------|---------|
| Hit Rate | 检索 | 否 | 否 | 低 | builtin |
| MRR | 检索 | 否 | 否 | 低 | builtin |
| NDCG | 检索 | 否 | 否 | 低 | builtin |
| Context Precision | 生成/检索 | 是 | 可选 | 高 | builtin, ragas |
| Context Recall | 生成/检索 | 是 | 是 | 高 | ragas |
| Faithfulness | 生成 | 是 | 否 | 高 | builtin, ragas |
| Answer Relevancy | 生成 | 是 | 否 | 高 | builtin, ragas |
| Factual Correctness | 生成 | 是 | 是 | 高 | ragas |
| Semantic Similarity | 生成 | 否（需 Embedding） | 是 | 中 | ragas |

---

## 使用建议

### 快速评测

仅使用检索指标，快速评估检索效果：

```yaml
evaluation:
  backends: ["builtin"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
```

### 标准评测

同时使用检索和生成指标：

```yaml
evaluation:
  llm_preset: "default"
  backends: ["builtin"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

### 深度评测（对齐业界标准）

包含 LLM 检索指标，全面评估系统质量：

```yaml
evaluation:
  llm_preset: "default"
  llm_retrieval_metrics:
    - "context_precision"
    - "context_recall"
  backends: ["builtin"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

### RAGAS 评测

使用 RAGAS 后端获取更丰富的生成质量指标：

```yaml
evaluation:
  backends: ["builtin", "ragas"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
      - "context_precision"
      - "context_recall"
      - "answer_correctness"
      - "semantic_similarity"
```

### 指标优先级

1. **Hit Rate**：最基础，必须关注
2. **MRR**：反映排序质量，重要
3. **Faithfulness**：反映回答可信度，关键
4. **NDCG**：综合排序指标，进阶
5. **Context Precision**：检索内容相关性 + 排序质量，深度评测
6. **Context Recall**：信息覆盖完整性，深度评测
7. **Answer Relevancy**：反映用户体验，进阶
8. **Factual Correctness**：事实正确性（需参考答案），进阶
9. **Semantic Similarity**：语义相似度（需参考答案），进阶

---

## 相关文档

- [RAGAS 评测系统指南](ragas-evaluation.md)
- [实验系统指南](experiment-system.md)
- [配置参考](../config-reference.md)
- [评测指标 Bug 修复报告](../troubleshooting/eval-metrics-bugfix.md)
- [评测系统验收修复报告](../troubleshooting/eval-system-acceptance-fix.md)
