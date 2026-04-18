# 版本演进年轮

<!-- status: active -->

> 最后更新: 2026-04-18

本文档记录项目的版本迭代历程，每个版本的关键决策、交付成果和经验教训。

---

## v0.1.5 (2026-04-16)

### 版本主题

MVP RAG + Baseline 评测 + 自动化实验系统

### 关键决策

- 采用固定长度分块策略（512 tokens, overlap=0）作为 baseline
- 使用 BAAI/bge-large-zh-v1.5 作为 Embedding 模型
- 使用 Qdrant 作为向量存储
- 通过 Anthropic SDK 调用 LongCat API

### 交付成果

- **Meal 数据管理系统**：数据集版本管理、采样策略、完整性验证
- **自动化评测系统**：多 Variant 对比实验、自动数据准备、实验复现
- **Token 追踪系统**：Token 消耗统计、成本估算
- **测试集生成器**：LLM 辅助问题生成、多种策略支持
- **356 个测试用例**：覆盖所有核心模块

### 版本验收

- [代码审查报告](reviews/v0.1.5/code-review.md)
- [交付对照](reviews/v0.1.5/outcome.md)

### 下版本方向

- [v0.1.6 开发方向](reviews/v0.1.5/next-direction.md)

---

## v0.1.0 (2026-04-15)

### 版本主题

MVP RAG 基础链路

### 关键决策

- 采用经典的 RAG 架构：PDF 解析 → 分块 → Embedding → 向量索引 → 检索 → LLM 生成
- 使用 pymupdf4llm 进行 PDF 解析
- 使用 tiktoken 进行 token 计数

### 交付成果

- **核心 RAG 链路**：6 个核心模块（parser, chunker, embedder, indexer, retriever, generator）
- **评测指标**：Hit Rate, MRR, NDCG
- **多 LLM preset 支持**：default, opus, sonnet, haiku
- **基础 CLI**：单次问答、交互式问答、索引构建

### 经验教训

- 评测指标需要统一 source 路径格式
- 测试覆盖需要尽早建立

---

## 版本规划

### v0.2.0（计划中）

- 实现生成质量指标（Faithfulness, Answer Relevancy）
- 混合检索（BM25 + 向量）
- Reranker 重排

### v0.3.0（计划中）

- 语义分块
- 查询改写
- Prompt 工程优化
