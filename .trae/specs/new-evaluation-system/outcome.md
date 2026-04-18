# 新评测系统验收报告

<!-- status: active -->

> 验收日期: 2026-04-18

---

## 功能概述

本次更新实现了全新的评测系统，主要包括：
- 文档级问题生成策略
- 生成质量指标（Faithfulness、Answer Relevancy）
- 检索指标改进
- 实验系统更新

---

## 需求完成情况

### Phase 1: 文档级问题生成

| 需求 | 状态 | 说明 |
|------|------|------|
| 基于完整文档生成问题 | ✅ 完成 | `generate_document_based_questions` 方法实现 |
| 问题生成与 chunk 参数解耦 | ✅ 完成 | 使用 `_load_full_documents` 加载完整 MD 文档 |
| 真实用户场景问题 | ✅ 完成 | 内置真实性检查，过滤学术化表述 |
| 6 种问题类型 | ✅ 完成 | single_fact, multi_fact, reasoning, comparative, missing, irrelevant |
| 旧策略 deprecation 警告 | ✅ 完成 | factual/boundary/multi_hop 策略显示警告 |

**实现细节**：

- 新增 `DOCUMENT_LEVEL_PROMPT` 提示词模板，模拟金融从业者提问风格
- 新增 6 种问题类型的补充提示词（`QUESTION_TYPE_SUPPLEMENTS`）
- 实现 `_check_authenticity_rules` 真实性检查，过滤"根据文档"等学术化表述
- 实现 `_calculate_quality_metrics` 质量指标计算

### Phase 2: 检索指标改进

| 需求 | 状态 | 说明 |
|------|------|------|
| NDCG 多级相关性 | ✅ 完成 | 支持 `relevance_scores` 参数 |
| Hit Rate 标准定义 | ✅ 完成 | 新增 `mode="standard"` 业界标准模式 |
| 指标计算严格性 | ✅ 完成 | 默认使用 standard mode |

**实现细节**：

- `calculate_hit_rate` 新增 `mode` 参数：
  - `standard`: 业界标准 Hit Rate@k（推荐）
  - `recall`: 旧版 recall 模式（向后兼容）
- `calculate_ndcg` 支持 `relevance_scores` 参数实现多级相关性

### Phase 3: 生成质量指标

| 需求 | 状态 | 说明 |
|------|------|------|
| Faithfulness 指标 | ✅ 完成 | `calculate_faithfulness` 函数实现 |
| Answer Relevancy 指标 | ✅ 完成 | `calculate_answer_relevancy` 函数实现 |
| LLM 评估集成 | ✅ 完成 | 使用 Anthropic 兼容 API |

**实现细节**：

- `calculate_faithfulness`:
  - 从回答中提取事实陈述
  - 验证每个陈述是否可从上下文推导
  - 返回可推导陈述比例

- `calculate_answer_relevancy`:
  - 三维度评估：直接相关性、信息充分性、简洁聚焦性
  - 返回综合相关性得分

### Phase 4: 实验系统更新

| 需求 | 状态 | 说明 |
|------|------|------|
| 新 metrics 配置格式 | ✅ 完成 | 支持 retrieval + generation 分组 |
| run_eval.py 集成 | ✅ 完成 | 支持生成质量指标配置 |
| 实验报告更新 | ✅ 完成 | 报告包含生成质量指标 |

### Phase 5: 测试与文档

| 需求 | 状态 | 说明 |
|------|------|------|
| 单元测试 | ✅ 完成 | `tests/test_metrics.py` 完整覆盖 |
| 文档更新 | ✅ 完成 | `docs/guides/evaluation-metrics.md` 已创建 |
| 实验系统文档 | ✅ 完成 | `docs/guides/experiment-system.md` 已更新 |

---

## 新旧系统对比

### 问题生成对比

| 维度 | 旧系统 (chunk-based) | 新系统 (document-based) |
|------|---------------------|------------------------|
| 输入 | 单个/多个 chunk | 完整 MD 文档 |
| 与 chunk_size 关系 | 强耦合 | 完全解耦 |
| 问题类型 | 3 种 | 6 种 |
| 问题风格 | 学术化、考试题风格 | 口语化、真实用户场景 |
| 质量控制 | 无 | 真实性检查 + 质量指标 |

### 评测指标对比

| 维度 | 旧系统 | 新系统 |
|------|--------|--------|
| 检索指标 | Hit Rate, MRR, NDCG | 同上 + 改进实现 |
| 生成指标 | 无 | Faithfulness, Answer Relevancy |
| Hit Rate 定义 | recall 模式 | standard 模式（推荐） |
| NDCG 相关性 | 二元 | 多级支持 |

### 配置格式对比

**旧格式**:
```yaml
evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
```

**新格式**:
```yaml
evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

---

## 向后兼容性

| 场景 | 兼容性 | 说明 |
|------|--------|------|
| 旧策略 (factual/boundary/multi_hop) | ✅ 兼容 | 显示 DeprecationWarning |
| 旧实验配置 | ✅ 兼容 | 自动使用默认指标 |
| 旧测试集 | ✅ 兼容 | 正常加载使用 |
| Hit Rate recall 模式 | ✅ 兼容 | 通过 `mode="recall"` 参数 |

---

## 测试覆盖

### 检索指标测试

- `TestNormalizeSource`: 6 个测试用例
- `TestCalculateHitRateStandard`: 12 个测试用例
- `TestCalculateHitRateRecall`: 8 个测试用例
- `TestCalculateMRR`: 16 个测试用例
- `TestCalculateNDCG`: 8 个测试用例
- `TestCalculateNDCGMultilevel`: 10 个测试用例

### 生成指标测试

- `TestParseRelevancyResponse`: 5 个测试用例
- `TestCalculateAnswerRelevancy`: 12 个测试用例
- `TestCreateLLMClient`: 2 个测试用例
- `TestExtractStatements`: 5 个测试用例
- `TestVerifyStatements`: 6 个测试用例
- `TestCalculateFaithfulness`: 12 个测试用例

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/test_generator.py` | 修改 | 新增文档级问题生成 |
| `eval/metrics.py` | 修改 | 新增生成质量指标、改进检索指标 |
| `eval/run_eval.py` | 修改 | 支持生成质量指标配置 |
| `tests/test_metrics.py` | 新增 | 完整的指标测试覆盖 |
| `docs/guides/evaluation-metrics.md` | 新增 | 评测指标详解文档 |
| `docs/guides/experiment-system.md` | 更新 | 实验系统使用指南 |

---

## 验收结论

**状态**: ✅ 通过验收

**评价**: 新评测系统完整实现了 spec 中定义的所有需求，代码质量高，测试覆盖充分，文档完善。新旧系统对比显示显著改进：

1. **问题生成质量提升**: 从学术化问题转变为真实用户场景问题
2. **评测维度扩展**: 从单一检索指标扩展到检索+生成双维度
3. **指标实现改进**: Hit Rate 采用业界标准，NDCG 支持多级相关性
4. **向后兼容性良好**: 旧策略和配置均可正常使用

**建议**: 
- 后续可考虑添加更多生成质量指标（如 Context Precision）
- 可探索自动化问题质量评估流程
