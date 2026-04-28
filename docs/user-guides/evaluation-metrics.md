# 评测指标详解

> 最后更新: 2026-04-27

本文档详细说明 RAG 评测系统中各个指标的含义、计算方法和改进建议。

---

## 概述

评测系统提供三类指标，支持两种评测后端（builtin 和 ragas），通过 **指标预设 + 解析策略** 两层架构管理：

| 类别 | 指标 | 评测对象 | 可用后端 | 需要 LLM |
|------|------|---------|---------|---------|
| **纯计算检索指标** | Hit Rate, MRR, NDCG, Recall@k, Chunk Hit/MRR/NDCG, Dedup Hit/MRR/NDCG, FPR, Diversity | 检索结果质量 | builtin | 否 |
| **LLM 检索指标** | Context Precision, Context Recall | 检索内容质量 | builtin, ragas | 是 |
| **生成质量指标** | Faithfulness, Answer Relevancy | 回答内容质量 | builtin, ragas | 是 |
| **RAGAS 专属指标** | Answer Correctness, Semantic Similarity | 端到端质量 | ragas | 是/Embedding |

> 关于指标预设（core/extended/full/custom）和解析策略（priority_fallback/comparison）的配置方法，请参阅 [配置参考](config-reference.md) 的 Evaluation 章节。关于 RAGAS 后端的详细使用方法，请参阅 [RAGAS 评测系统指南](ragas-evaluation.md)。

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

### Recall@k（召回率）

**定义**：检索结果中包含的相关文档占所有相关文档的比例。

**计算方法**：

```
Recall@k = |检索结果中相关文档| / |所有相关文档|
```

**取值范围**：0.0 - 1.0

系统提供 Recall@3、Recall@5、Recall@10 三个粒度：

| 指标 | 含义 | 适用场景 |
|------|------|---------|
| `recall_3` | top-3 中的召回率 | 评估精准检索能力 |
| `recall_5` | top-5 中的召回率 | 评估标准检索能力 |
| `recall_10` | top-10 中的召回率 | 评估广泛召回能力 |

**解读**：
- **0.8+**：检索召回充分
- **0.5-0.8**：部分相关文档未被检索到
- **< 0.5**：召回严重不足

**改进建议**：
- 增大 `top_k` 值
- 启用混合检索（BM25 + 向量）
- 优化 chunk 大小

---

### Chunk-level 检索指标

**定义**：与基础检索指标（hit_rate/mrr/ndcg）语义相同，但评估粒度为 chunk 级别而非文档级别。

| 指标 | 说明 |
|------|------|
| `chunk_hit_rate` | chunk 级别的命中率 |
| `chunk_mrr` | chunk 级别的平均倒数排名 |
| `chunk_ndcg` | chunk 级别的归一化折损累积增益 |

**与文档级指标的区别**：

| 维度 | 文档级指标 | Chunk 级指标 |
|------|-----------|-------------|
| 评估粒度 | 整篇文档 | 单个 chunk |
| ground truth | `expected_sources`（文档名列表） | `expected_chunks`（chunk ID 列表） |
| 适用场景 | 评估文档检索能力 | 评估精确段落定位能力 |

> **注意**：chunk 级指标需要测试数据中包含 `expected_chunks` 字段。使用 `document` 策略生成的测试集会自动包含此字段。

---

### Dedup 检索指标

**定义**：去除同一文档的重复检索结果后，再计算 hit_rate/mrr/ndcg。

| 指标 | 说明 |
|------|------|
| `dedup_hit_rate` | 去重后的命中率 |
| `dedup_mrr` | 去重后的平均倒数排名 |
| `dedup_ndcg` | 去重后的归一化折损累积增益 |

**与基础指标的区别**：当检索结果中同一文档的多个 chunk 都被返回时，dedup 指标只计一次，避免同一文档的多个 chunk 虚增检索分数。

**适用场景**：评估检索结果的文档多样性，避免检索结果被单一文档垄断。

---

### False Positive Rate（误检率）

**定义**：针对 irrelevant 类型问题，检索系统错误返回文档的比例。

**计算方法**：

```
FPR = 错误返回文档的 irrelevant 问题数 / 总 irrelevant 问题数
```

**取值范围**：0.0 - 1.0

**解读**：
- **0.0**：完美拒答，所有 irrelevant 问题均未返回文档
- **0.5+**：拒答能力不足，容易对无关问题产生幻觉

**改进建议**：
- 优化检索阈值
- 添加相关性过滤
- 优化 prompt 要求 LLM 在不确定时拒答

---

### Retrieval Diversity（检索多样性）

**定义**：检索结果中来自不同文档的比例，衡量检索结果是否覆盖了多个信息源。

**取值范围**：0.0 - 1.0

**解读**：
- **0.8+**：检索结果来源多样
- **0.5-0.8**：检索结果来源一般
- **< 0.5**：检索结果集中在少数文档

**改进建议**：
- 启用混合检索
- 调整 `top_k` 参数
- 考虑添加文档级去重

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

**来源**：builtin / RAGAS 双后端支持

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

**来源**：builtin / RAGAS 双后端支持

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

以下指标由 RAGAS 评测后端提供，需要在配置中启用 `ragas` 后端。在指标预设中，它们属于 `full` 预设。

### Answer Correctness（答案正确性）

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

| 指标 | 评测阶段 | 是否需要 LLM | 需要 Reference | 计算成本 | 可用后端 | 所属预设 |
|------|---------|-------------|---------------|---------|---------|---------|
| Hit Rate | 检索 | 否 | 否 | 低 | builtin | core |
| MRR | 检索 | 否 | 否 | 低 | builtin | core |
| NDCG | 检索 | 否 | 否 | 低 | builtin | core |
| Recall@3/5/10 | 检索 | 否 | 否 | 低 | builtin | core |
| Chunk Hit/MRR/NDCG | 检索 | 否 | 否 | 低 | builtin | extended |
| Dedup Hit/MRR/NDCG | 检索 | 否 | 否 | 低 | builtin | extended |
| Context Precision | 检索 | 是 | 是 | 高 | builtin, ragas | extended |
| Context Recall | 检索 | 是 | 是 | 高 | builtin, ragas | extended |
| Faithfulness | 生成 | 是 | 否 | 高 | builtin, ragas | core |
| Answer Relevancy | 生成 | 是 | 否 | 高 | builtin, ragas | core |
| False Positive Rate | 检索 | 否 | 否 | 低 | builtin | full |
| Retrieval Diversity | 检索 | 否 | 否 | 低 | builtin | full |
| Answer Correctness | 端到端 | 是 | 是 | 高 | ragas | full |
| Semantic Similarity | 端到端 | 否（需 Embedding） | 是 | 中 | ragas | full |

---

## 使用建议

### 通过指标预设快速配置（推荐）

评测系统提供四级指标预设，覆盖从日常实验到版本发布的全部场景：

```yaml
# 日常实验：core 预设，~3 次 LLM 调用/题
evaluation:
  backends: ["builtin"]
  metrics_preset: "core"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

```yaml
# 深度诊断：extended 预设，~11 次 LLM 调用/题
evaluation:
  backends: ["builtin"]
  metrics_preset: "extended"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

```yaml
# 版本发布：full 预设 + 双后端 priority_fallback
evaluation:
  backends: ["builtin", "ragas"]
  metrics_preset: "full"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

```yaml
# 版本发布对标：full 预设 + comparison 模式
evaluation:
  backends: ["builtin", "ragas"]
  metrics_preset: "full"
  resolution_strategy: "comparison"
```

### 自定义指标列表

如果预设不满足需求，可使用 `custom` 预设自行指定指标：

```yaml
evaluation:
  backends: ["builtin", "ragas"]
  metrics_preset: "custom"
  custom_metrics:
    retrieval: [hit_rate, mrr, ndcg, recall_3, recall_5, recall_10]
    generation: [faithfulness, answer_correctness, semantic_similarity]
  resolution_strategy: "priority_fallback"
  backend_priority: ["ragas", "builtin"]
```

> **提示**：`custom_metrics` 中的指标名必须与上表"指标"列中的名称完全匹配（如 `recall_3` 而非 `recall@3`）。如果某个指标没有后端可以计算，系统会记录 warning 并跳过。

### 指标优先级

1. **Hit Rate**：最基础，必须关注
2. **MRR**：反映排序质量，重要
3. **Faithfulness**：反映回答可信度，关键
4. **NDCG**：综合排序指标，进阶
5. **Recall@k**：检索召回充分性，进阶
6. **Context Precision**：检索内容相关性 + 排序质量，深度评测
7. **Context Recall**：信息覆盖完整性，深度评测
8. **Answer Relevancy**：反映用户体验，进阶
9. **Answer Correctness**：事实正确性（需参考答案），进阶
10. **Semantic Similarity**：语义相似度（需参考答案），进阶

---

## 相关文档

- [RAGAS 评测系统指南](ragas-evaluation.md)
- [实验系统指南](experiment-system.md)
- [配置参考](config-reference.md)
- [评测指标 Bug 修复报告](../.archive/v0.1.7-evaluation-era/evaluation-fixes/eval-metrics-bugfix.md)
- [评测系统验收修复报告](../.archive/v0.1.7-evaluation-era/evaluation-fixes/eval-system-acceptance-fix.md)
