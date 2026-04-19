# v0.1.7 交付对照

<!-- status: active -->

> 归档日期: 2026-04-19

---

## 版本主题

评测系统增强

---

## 主要变更

### 1. 文档级问题生成

- **新策略**：基于完整 MD 文档生成问题，与 chunk 参数解耦
- **6 种问题类型**：single_fact, multi_fact, reasoning, comparative, missing, irrelevant
- **真实性检查**：过滤学术化表述，确保问题贴近真实用户场景
- **向后兼容**：旧策略保留并显示 deprecation 警告

### 2. 生成质量指标

- **Faithfulness**：回答的事实陈述是否可从上下文推导
- **Answer Relevancy**：回答与问题的相关程度
- **LLM 评估集成**：使用 Anthropic 兼容 API

### 3. 检索指标改进

- **Hit Rate 标准定义**：采用业界标准 Hit Rate@k
- **NDCG 多级相关性**：支持 `relevance_scores` 参数
- **向后兼容**：保留旧版 recall 模式

### 4. 实验系统更新

- **新 metrics 配置格式**：支持 retrieval + generation 分组
- **实验报告更新**：包含生成质量指标

---

## 统计数据

| 指标 | 数值 |
|------|------|
| 新增测试 | 70+ |
| 文档更新 | 5+ |
| 核心模块变更 | 4 |

---

## 详细验收报告

详见 [Spec 验收报告](../../archive/specs/new-evaluation-system/outcome.md)。

---

## 下版本方向

参见 [v0.1.6 下版本方向](../v0.1.6/next-direction.md)。
