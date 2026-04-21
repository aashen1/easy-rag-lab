# 版本演进年轮

<!-- status: active -->

> 最后更新：2026-04-20

本文档记录项目的版本迭代历程，每个版本的关键决策、交付成果和经验教训。

---

## v0.1.8 (2026-04-20)

### 版本主题

TestSet 独立管理系统

### 关键决策

- 将 TestSet 提升为与 Meal 对等的独立可管理实体
- 引入 metadata 元数据结构，支持审计追踪
- 设计 on_missing 三种模式（auto / clean_only / strict）
- 用户定义集支持三种 invalid_policy（immutable / trim / regenerate）
- Archive 备份机制防止数据丢失

### 交付成果

- **TestSetManager 类**：CRUD 操作、有效性判定、自动清洗、Archive 备份
- **metadata 元数据结构**：name、meal_id、generation、user_defined、invalid_policy、audit_log
- **on_missing 路由逻辑**：三种模式控制查找失败时的兜底行为
- **自动清洗流程**：机器生成集和用户定义集分别处理
- **向后兼容**：旧格式测试集 JSON 自动迁移，旧配置触发 deprecation warning
- **CLI 增强**：--generate-test-set 支持 --name 参数
- **831 个测试全部通过**：无回归

### 版本验收

- [Spec 文档](../.trae/specs/test-set-independent-management/spec.md)
- [实现指南](guides/test-set-management.md)

---

## v0.1.7 (2026-04-19)

### 版本主题

评测系统增强

### 关键决策

- 采用文档级问题生成策略，与 chunk 参数解耦
- 引入生成质量指标（Faithfulness, Answer Relevancy）
- 改进检索指标实现，采用业界标准定义

### 交付成果

- **文档级问题生成**：基于完整 MD 文档生成真实场景问题，支持 6 种问题类型
- **生成质量指标**：Faithfulness（忠实度）、Answer Relevancy（回答相关性）
- **检索指标改进**：Hit Rate 采用业界标准定义，NDCG 支持多级相关性
- **真实性检查**：过滤学术化表述，确保问题贴近用户场景
- **向后兼容**：旧策略保留并显示 deprecation 警告

### 版本验收

- [交付对照](reviews/v0.1.7/outcome.md)
- [Spec 验收报告](archive/specs/new-evaluation-system/outcome.md)

---

## v0.1.6 (2026-04-18)

### 版本主题

项目卫生 + 文档系统重构

### 关键决策

- 建立四级文档目录结构（guides, reviews, archive, troubleshooting）
- 引入版本历史系统和 Backlog 系统
- 统一文档命名规范（英文文件名）

### 交付成果

- **文档系统重构**：新目录结构、版本历史、Backlog 系统、Review 系统
- **代码质量改进**：类型标注、Docstrings、代码重构
- **测试改进**：新增测试、测试修复、测试清理
- **功能增强**：动态 metric 配置、进度显示参数

### 版本验收

- [交付对照](reviews/v0.1.6/outcome.md)

### 下版本方向

- [v0.2.0 开发方向](reviews/v0.1.6/next-direction.md)

---

## v0.1.1~v0.1.5 (2026-04-16)

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

- 混合检索（BM25 + 向量）
- Reranker 重排
- 语义分块

### v0.3.0（计划中）

- 查询改写
- Prompt 工程优化
- 更多生成质量指标（Context Precision 等）
