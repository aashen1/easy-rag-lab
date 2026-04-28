# RAG 泛超参数优化：功能实现与测试保障

<!-- status: needs-update -->

> ⚠️ **文档状态**：本文档声称介绍 "v0.2.0 新增"功能，但实际这些功能（BM25、混合检索、Reranker、查询改写、语义分块）已在 v0.1.8 实现并交付。文档中的版本引用和实现状态描述需要修正。

> 最后更新: 2026-04-19

本文档面向开发者，介绍 v0.2.0 新增的 RAG 优化模块的实现细节、设计决策和测试策略。

---

## 概述

本次迭代的核心目标是扩展 RAG 管道的"泛超参数"维度，使项目能够系统性探究不同技术选型对问答质量的影响。新增了 5 个核心模块，引入了 4 大类新的可调参数维度：

| 维度 | 新增模块 | 核心超参数 |
|------|---------|-----------|
| 检索方式 | BM25 检索器 + 混合检索器 | method, fusion, rrf_k, vector_weight, bm25_weight |
| 重排序 | Cross-Encoder Reranker | enabled, model_name, top_n |
| 查询改写 | Query Rewriter | enabled, strategy, num_queries |
| 分块策略 | Semantic Chunker | strategy, similarity_threshold, breakpoint_percentile |

---

## 模块实现详解

### 1. BM25 检索器 (`src/bm25_retriever.py`)

#### 设计决策

- **分词方案**：使用 `jieba` 进行中文分词，过滤长度 ≤1 的 token 以降低噪声
- **BM25 变体**：采用 Okapi BM25，支持 k1（词频饱和参数）和 b（长度归一化参数）两个核心参数
- **IDF 处理**：对负 IDF 值进行钳位（clamping），使用 `epsilon * avg_idf` 作为下界，防止高频词获得负权重
- **索引构建**：支持从 JSONL 文件目录直接构建索引，与现有 chunker 输出格式兼容
- **source_filter**：支持按文件路径过滤，与实验框架的采样机制联动

#### 关键实现细节

```python
# IDF 计算：标准 BM25 公式 + 负值钳位
idf = math.log((N - df + 0.5) / (df + 0.5) + 1)

# 评分：Okapi BM25 完整公式
score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
```

#### 与 LlamaIndex BM25 的关系

项目已依赖 `llama-index-retrievers-bm25`，但选择自行实现 BM25 而非使用 LlamaIndex 的封装，原因：

1. **参数透明**：k1、b 参数直接暴露，便于实验调参
2. **无额外依赖**：不引入 LlamaIndex 的数据抽象层，保持与项目 JSONL 格式的直接兼容
3. **可测试性**：纯 Python 实现，不依赖 LlamaIndex 的文档对象模型

---

### 2. 混合检索器 (`src/hybrid_retriever.py`)

#### 设计决策

- **双融合策略**：支持 RRF（Reciprocal Rank Fusion）和加权融合（Weighted）两种策略
- **RRF 优势**：对分数尺度不敏感，不需要归一化，适合合并来自不同检索器的结果
- **加权融合**：先对每个检索器的分数做 min-max 归一化到 [0, 1]，再加权合并
- **检索扩展**：混合检索时，BM25 检索 top_k * 3 个候选，确保融合后有足够的候选集

#### RRF 融合公式

```
score(d) = Σ_{r ∈ retrievers} 1 / (k + rank_r(d))
```

其中 k=60 是经验常数（原论文推荐值），k 越大则排名差异的影响越小。

#### 加权融合流程

```
1. 对每个检索器的分数做 min-max 归一化 → [0, 1]
2. combined_score = α * norm_vector_score + (1-α) * norm_bm25_score
3. 按 combined_score 降序取 top_k
```

---

### 3. Cross-Encoder Reranker (`src/reranker.py`)

#### 设计决策

- **模型选择**：默认使用 `BAAI/bge-reranker-large`，中文场景表现优秀
- **推理优化**：CUDA 上自动启用 FP16 半精度，批处理推理（batch_size=16）
- **插入位置**：在检索之后、生成之前，对检索结果进行精排
- **top_n 参数**：重排后保留的文档数，通常小于检索的 top_k，起到"精筛"作用

#### Bi-Encoder vs Cross-Encoder 的设计考量

| 特性 | Bi-Encoder（Embedder） | Cross-Encoder（Reranker） |
|------|----------------------|--------------------------|
| 输入 | 单条文本 | (query, document) 对 |
| 速度 | 快（预计算向量） | 慢（逐对打分） |
| 精度 | 较低 | 较高 |
| 用途 | 初筛（检索） | 精排（重排序） |

Reranker 模块遵循"先粗后精"的业界最佳实践：先用 Bi-Encoder 快速检索候选集，再用 Cross-Encoder 精排。

---

### 4. 查询改写器 (`src/query_rewriter.py`)

#### 设计决策

- **双策略支持**：HyDE 和 Multi-Query，覆盖两种主流查询改写范式
- **HyDE 原理**：让 LLM 生成"假设性回答"，用假设回答的 embedding 去检索。假设回答在语义空间中更接近真实文档，从而弥合 query-document 的语义鸿沟
- **Multi-Query 原理**：将原始查询改写为多个子查询，分别检索后合并去重。增加召回覆盖面
- **去重机制**：Multi-Query 合并结果时按 chunk_id 去重，避免同一文档被重复计入
- **Token 追踪**：查询改写的 LLM 调用纳入 TokenTracker，支持成本分析

#### HyDE 在 Pipeline 中的集成

```
原始查询 → HyDE 生成假设回答 → 用假设回答做 embedding → 检索 → 生成
```

注意：HyDE 的假设回答仅用于检索，不用于最终答案生成。生成阶段仍使用原始查询。

#### Multi-Query 在 Pipeline 中的集成

```
原始查询 → 改写为 N 个子查询 → 每个子查询分别检索 → 合并去重 → (可选 Rerank) → 生成
```

Multi-Query 模式下，如果启用了 Reranker，会对合并后的结果统一重排。

---

### 5. 语义分块器 (`src/semantic_chunker.py`)

#### 设计决策

- **断点检测**：计算相邻句子的 embedding 余弦相似度，在相似度低于阈值处插入断点
- **双阈值模式**：
  - 固定阈值模式：`similarity_threshold` 直接指定断点阈值
  - 百分位模式：`breakpoint_percentile` 取相似度分布的百分位作为阈值，自适应数据
- **小段合并**：token 数低于 `min_chunk_size` 的段会与前一个段合并，避免产生过小的 chunk
- **大段拆分**：超过 `chunk_size` 的段会回退到固定 token 数拆分，确保不会产生过大的 chunk
- **输出兼容**：JSONL 输出格式与固定分块完全一致，metadata 中额外增加 `strategy: "semantic"` 标记

#### 语义断点检测流程

```
1. 文本 → 按标点分句 → sentences[]
2. sentences → embedder.embed_texts() → embeddings[]
3. 计算相邻 embedding 的余弦相似度 → similarities[]
4. 低于阈值的相似度位置 → 断点 breakpoints[]
5. 按断点切分 → 语义段 segments[]
6. 小段合并 + 大段拆分 → 最终 chunks[]
```

---

### 6. 实验可视化 (`eval/visualize.py`)

#### 设计决策

- **双图表类型**：对比柱状图（bar chart）和趋势折线图（trend line）
- **按指标类别分组**：retrieval 和 generation 指标分别出图
- **自动标注**：柱状图顶部标注具体数值，折线图使用 marker 标记数据点
- **Agg 后端**：使用 matplotlib 的 Agg 后端，无需 GUI 环境即可生成图片

---

## Pipeline 集成架构

所有新模块通过 `pipeline.py` 的 `_setup_retrievers()` 方法统一管理：

```
RAGPipeline.__init__()
    └── _setup_retrievers()
            ├── Retriever (vector)        # 始终创建
            ├── BM25Retriever             # method ∈ {bm25, hybrid} 时创建
            ├── HybridRetriever           # method == hybrid 时创建
            ├── Reranker                  # reranker.enabled == true 时创建
            └── QueryRewriter             # query_rewrite.enabled == true 时创建
```

### Query 执行流程

```
query(question)
    │
    ├── query_rewrite.enabled?
    │   ├── HyDE: retrieval_query = 假设回答
    │   └── Multi-Query: 分别检索子查询 → 合并去重
    │       └── reranker.enabled? → 重排合并结果 → 直接生成
    │
    ├── retrieval_query → 检索
    │   ├── method=vector: Retriever.retrieve()
    │   ├── method=bm25: BM25Retriever.retrieve()
    │   └── method=hybrid: HybridRetriever.retrieve()
    │
    ├── reranker.enabled? → Reranker.rerank()
    │
    └── Generator.generate(question, contexts)
```

---

## 测试策略

### 测试分层

新增模块的测试遵循项目已有的三层测试体系：

| 层级 | Marker | 新增测试文件 | 测试数量 |
|------|--------|-------------|---------|
| 单元测试 | `@pytest.mark.unit` | 5 个 | 59 个 |
| 组件集成 | `@pytest.mark.unit` | 含在上述文件中 | - |
| 端到端 | `@pytest.mark.e2e` | 通过实验框架验证 | - |

### 各模块测试覆盖

#### BM25 检索器测试 (`tests/test_bm25_retriever.py`)

| 测试类别 | 测试项 | 验证目标 |
|---------|--------|---------|
| 索引构建 | `test_build_index` | 正常构建索引，corpus_size 正确 |
| 异常处理 | `test_build_index_empty_chunks_raises` | 空数据抛出 ValueError |
| 异常处理 | `test_retrieve_before_index_raises` | 未建索引时检索抛出 RuntimeError |
| 异常处理 | `test_retrieve_empty_query_raises` | 空查询抛出 ValueError |
| 检索质量 | `test_retrieve_relevance_ranking` | 茅台相关查询首条结果为茅台文档 |
| 参数约束 | `test_invalid_k1_raises` / `test_invalid_b_raises` | 参数越界抛出 ValueError |
| 文件加载 | `test_build_index_from_chunks` | 从 JSONL 目录正确加载 |
| 文件过滤 | `test_build_index_from_chunks_with_source_filter` | source_filter 正确过滤 |
| 参数影响 | `test_bm25_parameters_affect_scoring` | 不同 k1/b 参数产生不同分数 |

#### 混合检索器测试 (`tests/test_hybrid_retriever.py`)

| 测试类别 | 测试项 | 验证目标 |
|---------|--------|---------|
| 参数校验 | `test_invalid_fusion_method_raises` | 非法融合策略抛出 ValueError |
| 参数校验 | `test_zero_weights_raises` | 零权重抛出 ValueError |
| RRF 融合 | `test_rrf_fusion_returns_results` | RRF 返回有效结果 |
| RRF 融合 | `test_rrf_fusion_boosts_shared_documents` | 两检索器共有的文档得分更高 |
| 加权融合 | `test_weighted_fusion_returns_results` | 加权融合返回有效结果 |
| 加权融合 | `test_weighted_fusion_normalizes_scores` | 分数归一化到合理范围 |
| 结果限制 | `test_top_k_limits_results` | top_k 正确限制返回数量 |
| 归一化 | `test_normalize_scores_equal_values` | 等值分数归一化为 1.0 |
| 归一化 | `test_normalize_scores_range` | min-max 归一化正确映射到 [0, 1] |
| 参数影响 | `test_rrf_k_parameter_affects_scores` | 不同 rrf_k 产生不同分数 |

#### Reranker 测试 (`tests/test_reranker.py`)

| 测试类别 | 测试项 | 验证目标 |
|---------|--------|---------|
| 重排功能 | `test_rerank_returns_results` | 重排返回结果且按分数降序 |
| 结果限制 | `test_rerank_top_n_limits_results` | top_n 正确限制返回数量 |
| 异常处理 | `test_rerank_empty_query_raises` | 空查询抛出 ValueError |
| 空结果 | `test_rerank_empty_results_returns_empty` | 空输入返回空列表 |
| 元数据保留 | `test_rerank_preserves_metadata` | 重排后保留所有原始字段 |

**Mock 策略**：Reranker 测试通过 mock `AutoModelForSequenceClassification` 和 `AutoTokenizer`，避免加载真实模型（约 1.3GB），使测试可在无 GPU 环境下秒级完成。

#### 查询改写器测试 (`tests/test_query_rewriter.py`)

| 测试类别 | 测试项 | 验证目标 |
|---------|--------|---------|
| 参数校验 | `test_invalid_strategy_raises` | 非法策略抛出 ValueError |
| 异常处理 | `test_empty_query_raises` | 空查询抛出 ValueError |
| HyDE | `test_hyde_rewrite` | 返回假设性回答文本 |
| HyDE | `test_hyde_uses_correct_prompt` | 提示词包含关键指令 |
| Multi-Query | `test_multi_query_rewrite` | 返回子查询列表 |
| Multi-Query | `test_multi_query_strips_numbering` | 自动去除编号前缀 |
| Multi-Query | `test_multi_query_limits_num_queries` | 子查询数量不超过设定值 |
| Token 追踪 | `test_rewrite_with_token_tracker` | Token 使用量正确记录 |
| LLM 失败 | `test_llm_failure_raises` | LLM 调用失败时抛出异常 |

**Mock 策略**：查询改写器测试通过 mock `_call_llm` 方法，避免实际调用 LLM API。

#### 语义分块器测试 (`tests/test_semantic_chunker.py`)

| 测试类别 | 测试项 | 验证目标 |
|---------|--------|---------|
| 分句 | `test_split_into_sentences` | 中文标点正确分句 |
| 分段 | `test_split_into_paragraphs` | 双换行和标题正确分段 |
| 基本分块 | `test_chunk_text_semantic_basic` | 返回带 metadata 的 chunk |
| 异常处理 | `test_chunk_text_semantic_empty_text` | 空文本返回空列表 |
| 异常处理 | `test_chunk_text_semantic_none_embedder_raises` | 无 embedder 抛出 ValueError |
| 单句处理 | `test_chunk_text_semantic_single_sentence` | 单句文本正确处理 |
| 大小限制 | `test_chunk_text_semantic_respects_chunk_size` | chunk 不超过 chunk_size |
| 阈值模式 | `test_chunk_text_semantic_threshold_mode` | 固定阈值正确检测断点 |
| 百分位模式 | `test_chunk_text_semantic_percentile_mode` | 百分位阈值正确检测断点 |
| 元数据 | `test_chunk_text_semantic_metadata` | metadata 字段完整 |
| 小段合并 | `test_chunk_text_semantic_merges_small_chunks` | 小段正确合并 |

**Mock 策略**：语义分块器测试通过 mock Embedder 返回预设的 embedding 向量，控制相似度值以测试断点检测逻辑。

### 测试设计原则

1. **隔离性**：每个测试 mock 外部依赖（LLM API、模型加载），确保测试不依赖外部服务
2. **确定性**：测试数据固定，结果可复现
3. **边界条件**：覆盖空输入、非法参数、零值等边界情况
4. **参数影响验证**：验证不同参数值确实产生不同结果（如 k1/b 对 BM25 分数的影响）
5. **兼容性**：新模块的输出格式与现有模块一致（JSONL 格式、metadata 结构）

### 回归验证

所有 623 个既有测试全部通过，新增 59 个测试，总计 682 个测试无回归。

---

## 实验配置设计

为每个新维度设计了消融实验配置：

| 实验配置 | 变体数 | 探究维度 |
|---------|--------|---------|
| `retrieval_comparison.yaml` | 5 | vector / bm25 / hybrid-rrf / hybrid-weighted-70-30 / hybrid-weighted-50-50 |
| `reranker_comparison.yaml` | 4 | no-rerank / rerank-top3 / rerank-top5 / hybrid+rerank |
| `query_rewrite_comparison.yaml` | 4 | no-rewrite / hyde / multi-query-3 / hyde+hybrid |
| `chunking_strategy_comparison.yaml` | 4 | fixed-512 / semantic-threshold-50 / semantic-threshold-30 / semantic-percentile-25 |

每个实验配置遵循以下原则：

1. **单一变量**：每个变体只改变一个维度的参数
2. **基线对照**：包含一个不使用新优化的基线变体
3. **组合探索**：包含一个组合多个优化的变体（如 hybrid + rerank）
4. **足够数据量**：每个实验使用 20% 采样数据，65 个测试问题

---

## 相关文档

- [新增超参数使用指南](../user-guides/hyperparameter-guide.md) — 面向用户的参数配置指南
- [配置参考](../user-guides/config-reference.md) — config.yaml 完整说明
- [实验评测系统](../user-guides/experiment-system.md) — 实验运行方法
- [系统架构](architecture.md) — 整体架构说明
