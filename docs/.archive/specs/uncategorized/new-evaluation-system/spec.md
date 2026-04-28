# 新评测系统 Spec

## Why

当前的问题生成功能基于 chunk 实现，导致 chunk_size 参数被锁住，无法进行基本的 chunk-size 对比实验。此外，现有评测系统仅支持检索指标（hit_rate、mrr、ndcg），缺少生成质量指标（Faithfulness、Answer Relevancy），无法全面评估 RAG 系统性能。

需要一套与 chunk 解耦的评测系统，支持基于完整文档的问题生成，并引入生成质量指标，为后续 RAG 优化实验提供可靠的评测基础。

## What Changes

- **新增文档级问题生成策略**：基于完整 MD 文档生成问题，与 chunk 参数解耦
- **新增生成质量指标**：实现 Faithfulness 和 Answer Relevancy 指标
- **重构评测流程**：支持多种评测指标组合
- **标记旧系统为 deprecated**：保留 chunk-based 问题生成功能，标记为 deprecated
- **更新实验配置**：支持新的评测配置格式

## Impact

- **Affected specs**: 评测系统、实验系统
- **Affected code**:
  - `src/test_generator.py` - 新增文档级问题生成策略
  - `eval/metrics.py` - 新增生成质量指标
  - `eval/run_eval.py` - 支持新的评测指标
  - `src/experiment.py` - 更新实验配置结构
  - `exp_configs/*.yaml` - 更新实验配置示例

## ADDED Requirements

### Requirement: 文档级问题生成

系统应提供基于完整 MD 文档的问题生成功能，与 chunk 参数解耦，生成真实、多样化的问题。

#### Scenario: 基于完整文档生成问题

- **WHEN** 用户使用 `document` 策略生成测试集
- **THEN** 系统应基于完整的 MD 文档内容生成问题，而不是基于 chunk

#### Scenario: 问题生成与 chunk 参数无关

- **WHEN** 用户修改 chunk_size 或 chunk_overlap 参数
- **THEN** 使用 `document` 策略生成的测试集应保持不变

#### Scenario: 真实用户场景问题

- **WHEN** 系统生成问题时
- **THEN** 问题应贴近真实用户场景（如金融从业者的实际需求），而不是像考试题或练习题

#### Scenario: 多样化问题类型

- **WHEN** 系统生成测试集
- **THEN** 应覆盖多种问题类型：
  - 单知识点查询
  - 多知识点综合
  - 缺失知识点处理
  - 无关问题识别
  - 推理型问题
  - 对比分析问题

### Requirement: 生成质量指标 - Faithfulness

系统应提供 Faithfulness（忠实度）指标，评估回答是否基于检索到的上下文。

#### Scenario: 计算 Faithfulness 指标

- **WHEN** 评测系统评估一个问答对
- **THEN** 系统应计算回答内容与检索上下文的一致性得分

#### Scenario: 高忠实度回答

- **WHEN** 回答内容完全基于检索上下文
- **THEN** Faithfulness 得分应接近 1.0

#### Scenario: 低忠实度回答

- **WHEN** 回答内容包含上下文中不存在的信息
- **THEN** Faithfulness 得分应较低

### Requirement: 生成质量指标 - Answer Relevancy

系统应提供 Answer Relevancy（回答相关性）指标，评估回答是否切题。

#### Scenario: 计算 Answer Relevancy 指标

- **WHEN** 评测系统评估一个问答对
- **THEN** 系统应计算回答与问题的相关性得分

#### Scenario: 高相关性回答

- **WHEN** 回答直接针对问题，信息丰富
- **THEN** Answer Relevancy 得分应接近 1.0

#### Scenario: 低相关性回答

- **WHEN** 回答与问题无关或信息不足
- **THEN** Answer Relevancy 得分应较低

### Requirement: 评测指标组合

系统应支持灵活的评测指标组合配置。

#### Scenario: 仅检索指标

- **WHEN** 用户配置仅使用检索指标（hit_rate、mrr、ndcg）
- **THEN** 系统应仅计算检索相关指标

#### Scenario: 仅生成质量指标

- **WHEN** 用户配置仅使用生成质量指标（faithfulness、answer_relevancy）
- **THEN** 系统应仅计算生成质量相关指标

#### Scenario: 混合指标

- **WHEN** 用户配置同时使用检索指标和生成质量指标
- **THEN** 系统应计算所有配置的指标

### Requirement: 向后兼容

系统应保持对旧评测系统的向后兼容。

#### Scenario: 使用旧策略

- **WHEN** 用户使用旧的 chunk-based 策略（factual、boundary、multi_hop）
- **THEN** 系统应正常工作并输出 deprecation 警告

#### Scenario: 旧实验配置

- **WHEN** 用户使用旧的实验配置文件
- **THEN** 系统应正常解析和运行

## MODIFIED Requirements

### Requirement: 检索指标改进

系统应改进现有检索指标（hit_rate、mrr、ndcg）的实现，使其更加严格和准确。

#### Scenario: NDCG 多级相关性

- **WHEN** 计算检索结果的 NDCG 指标
- **THEN** 应支持多级相关性评分，而不是简单的二元相关性

#### Scenario: Hit Rate 标准定义

- **WHEN** 计算检索结果的 Hit Rate 指标
- **THEN** 应采用业界标准定义，确保指标的可比性和可信度

#### Scenario: 指标计算严格性

- **WHEN** 评测系统计算检索指标
- **THEN** 应采用更严格的判定逻辑，避免分数虚高

### Requirement: 实验配置格式

实验配置应支持新的评测指标配置。

#### 原格式

```yaml
evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
```

#### 新格式

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

### Requirement: 测试集配置格式

测试集配置应支持新的文档级策略。

#### 原格式

```yaml
test_sets:
  - strategy: "factual"
    num_questions: 20
    seed: 100
```

#### 新格式

```yaml
test_sets:
  - strategy: "document"
    num_questions: 20
    seed: 100
    question_types:
      - "factual"
      - "reasoning"
```

## REMOVED Requirements

无移除的需求。旧的 chunk-based 系统标记为 deprecated，但保留功能。
