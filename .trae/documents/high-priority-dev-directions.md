# 高优开发方向分析：让项目充分体现"RAG泛超参数对问答效果影响"的理解

## 核心诊断

**目标**：简历上体现"充分理解RAG中各种泛超参数对问答效果的影响"

**现状**：项目实验框架完备，但"实验素材"严重不足——RAG管道只实现了最基础的固定分块+纯向量检索+直接生成，缺少行业主流优化手段，且没有系统性的消融实验数据。

**核心差距**：你有了"实验室"（实验框架），但缺少"实验对象"（多种RAG优化技术）和"实验数据"（系统性消融结果）。简历要讲的故事是"我探究了X对Y的影响"，但现在X只有chunk_size/overlap两个变量，Y的实证数据也几乎为空。

---

## 五大高优差距（按简历价值排序）

### 差距1：检索方式单一——缺少混合检索（最高优）

**现状**：只有纯向量语义检索（Qdrant cosine search）

**为什么关键**：
- 混合检索（BM25 + 向量）是RAG领域最经典的优化之一，面试必问
- 它引入了全新的泛超参数维度：**融合策略**（RRF vs 加权）、**BM25权重**、**向量权重**
- 这是"稀疏检索 vs 稠密检索 vs 混合"这条技术选型线的核心实验

**需要实现**：
- BM25检索器（项目已依赖 `llama-index-retrievers-bm25` 和 `jieba`）
- 混合检索器：支持 RRF 融合和加权融合两种策略
- 新增配置项：`retrieval.method`（vector/bm25/hybrid）、`retrieval.hybrid.fusion`（rrf/weighted）、`retrieval.hybrid.weights` 等
- 实验配置：`retrieval_comparison.yaml`，对比 vector-only / bm25-only / hybrid-rrf / hybrid-weighted

**简历价值**：★★★★★ "对比了稀疏检索、稠密检索、混合检索对问答质量的影响，发现混合检索在XX类型问题上提升XX%"

---

### 差距2：缺少Reranker重排（高优）

**现状**：检索结果直接送LLM，无重排序

**为什么关键**：
- Reranker是RAG管道中"检索→生成"之间的关键优化层
- 引入新超参数维度：**是否重排**、**重排模型选择**、**重排后取top_n**
- 面试高频话题：bi-encoder vs cross-encoder 的区别

**需要实现**：
- Reranker模块（使用 BAAI/bge-reranker-large 或类似cross-encoder）
- 在 Retriever 和 Generator 之间插入 rerank 步骤
- 新增配置项：`retrieval.reranker.enabled`、`retrieval.reranker.model_name`、`retrieval.reranker.top_n`
- 实验配置：`reranker_comparison.yaml`，对比 no-rerank / with-rerank / rerank-different-topn

**简历价值**：★★★★☆ "引入Cross-Encoder重排后，MRR从XX提升到XX，证明语义精排对检索质量的关键作用"

---

### 差距3：缺少查询改写（高优）

**现状**：用户原始查询直接用于检索

**为什么关键**：
- 查询改写是RAG中"用户侧"最重要的优化，解决查询-文档语义鸿沟
- 引入新超参数维度：**改写策略**（HyDE / Multi-Query / 原始查询）、**改写温度**
- HyDE（假设性文档嵌入）是RAG论文中的经典方法

**需要实现**：
- 查询改写模块，支持至少两种策略：
  - **HyDE**：先让LLM生成"假设性回答"，再用假设回答的embedding去检索
  - **Multi-Query**：将原始查询改写为多个子查询，分别检索后合并
- 新增配置项：`retrieval.query_rewrite.enabled`、`retrieval.query_rewrite.strategy`（hyde/multi_query）、`retrieval.query_rewrite.num_queries`
- 实验配置：`query_rewrite_comparison.yaml`

**简历价值**：★★★★☆ "对比了HyDE和Multi-Query两种查询改写策略，发现HyDE在推理型问题上效果更优"

---

### 差距4：分块策略单一——缺少语义分块（中高优）

**现状**：只有固定token数分块

**为什么关键**：
- 分块策略是RAG中影响最大的"上游"决策
- 当前只能实验 chunk_size/overlap 两个参数，缺少策略层面的对比
- 语义分块（按语义边界切分）vs 固定分块是经典的trade-off：语义完整性 vs 可控性

**需要实现**：
- 语义分块器：基于embedding相似度检测语义断点
- 递归分块器：按文档结构（标题层级）递归切分
- 新增配置项：`chunker.strategy`（fixed/semantic/recursive）
- 实验配置：`chunking_strategy_comparison.yaml`

**简历价值**：★★★☆☆ "对比了固定分块、语义分块、递归分块三种策略，发现语义分块在多跳推理问题上表现更优"

---

### 差距5：缺少系统性实验数据与可视化（高优）

**现状**：
- exp_reports/ 下有约20个实验目录，但几乎都是调试/冒烟测试
- 唯一有意义的 chunk_size_validation 实验只有3个问题、1个成功变体
- **没有一份完整的、可展示的消融实验报告**
- 没有可视化（图表）

**为什么关键**：
- 简历上最有说服力的是**数据**，不是代码
- "我探究了X对Y的影响"需要具体的数字和趋势图
- 面试时能展示一张"chunk_size vs Hit Rate"的折线图，比说"我实现了实验框架"强10倍

**需要实现**：
- 运行完整的 chunk_comparison 实验（6个变体，70个问题）
- 运行新设计的 retrieval/reranker/query_rewrite 对比实验
- 实验结果可视化：生成对比图表（matplotlib/plotly）
- 撰写一份综合分析文档，总结各泛超参数的影响规律

**简历价值**：★★★★★ "系统性实验表明：chunk_size从256增至1024时，Hit Rate提升XX%但Faithfulness下降XX%，存在最优区间"

---

## 开发路线图（按优先级排序）

### Phase 1：混合检索（预计2-3天）
1. 实现 BM25 检索器
2. 实现混合检索器（RRF + 加权融合）
3. 扩展配置和实验框架
4. 编写测试
5. 设计并运行 retrieval_comparison 实验

### Phase 2：Reranker 重排（预计1-2天）
1. 实现 Reranker 模块
2. 集成到 RAG 管道
3. 扩展配置和实验框架
4. 编写测试
5. 设计并运行 reranker_comparison 实验

### Phase 3：查询改写（预计1-2天）
1. 实现 HyDE 策略
2. 实现 Multi-Query 策略
3. 集成到检索流程
4. 扩展配置和实验框架
5. 编写测试
6. 设计并运行 query_rewrite_comparison 实验

### Phase 4：语义分块（预计1-2天）
1. 实现语义分块器
2. 实现递归分块器（可选）
3. 扩展配置和实验框架
4. 编写测试
5. 设计并运行 chunking_strategy_comparison 实验

### Phase 5：实验数据产出与可视化（预计1-2天）
1. 运行所有完整实验（确保数据量充足）
2. 实现实验结果可视化（图表生成）
3. 撰写综合分析文档
4. 整理可用于简历的量化结论

---

## 简历叙事框架

完成上述开发后，简历可以这样写：

> **金融研报RAG问答系统**：独立设计并实现完整的RAG管道，系统性探究6大类泛超参数对问答质量的影响：
> - **分块策略**：对比固定/语义/递归分块，发现语义分块在多跳推理上提升XX%
> - **检索方式**：对比稀疏/稠密/混合检索，混合检索Hit Rate提升XX%
> - **重排序**：引入Cross-Encoder重排，MRR从XX提升至XX
> - **查询改写**：对比HyDE/Multi-Query，HyDE在推理型问题上更优
> - **分块参数**：chunk_size从256→1024，存在质量-效率最优区间
> - **检索参数**：top_k从3→10，边际收益递减拐点在k=XX

---

## 总结

| 差距 | 简历价值 | 开发量 | 优先级 |
|------|---------|--------|--------|
| 混合检索 | ★★★★★ | 中 | P0 |
| Reranker | ★★★★☆ | 中小 | P0 |
| 查询改写 | ★★★★☆ | 中 | P1 |
| 语义分块 | ★★★☆☆ | 中 | P1 |
| 实验数据+可视化 | ★★★★★ | 小 | P0（贯穿全程） |

**核心建议**：先实现混合检索+Reranker+查询改写（这三个是面试最高频、简历最亮点的RAG优化），然后跑出系统性实验数据，最后如果有时间再加语义分块。实验数据产出要贯穿全程，每实现一个优化就跑一次对比实验。
