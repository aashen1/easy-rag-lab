# RAGAS 集成完整性分析计划

## 一、当前项目 RAGAS 集成现状

### 已实现的指标（6个）

| 指标名称                | 类型              | 用途                |
| ------------------- | --------------- | ----------------- |
| Faithfulness        | LLM-based       | 衡量回答是否基于检索上下文，无幻觉 |
| Answer Relevancy    | LLM-based       | 衡量回答与问题的相关性       |
| Context Precision   | LLM-based       | 衡量检索上下文的精确度       |
| Context Recall      | LLM-based       | 衡量检索上下文的召回率       |
| Factual Correctness | LLM-based       | 衡量回答的事实正确性        |
| Semantic Similarity | Embedding-based | 衡量回答与参考答案的语义相似度   |

### 当前实现特点

* 使用 `LangchainLLMWrapper` 包装 `ChatAnthropic` 兼容 LongCat API

* 支持单样本和批量评估

* 配置文件位于 `exp_configs/ragas_evaluation/`

***

## 二、RAGAS 官方文档完整指标列表

### 1. RAG（检索增强生成）指标

| 指标名称                        | 项目状态  | 说明                        |
| --------------------------- | ----- | ------------------------- |
| Context Precision           | ✅ 已实现 | 检索上下文精确度                  |
| Context Recall              | ✅ 已实现 | 检索上下文召回率                  |
| **Context Entities Recall** | ❌ 未实现 | 基于实体的上下文召回率               |
| **Noise Sensitivity**       | ❌ 未实现 | 噪声敏感度，衡量模型对无关信息的敏感程度      |
| Response Relevancy          | ✅ 已实现 | 回答相关性（即 Answer Relevancy） |
| Faithfulness                | ✅ 已实现 | 忠实度                       |
| **Multimodal Faithfulness** | ❌ 未实现 | 多模态忠实度                    |
| **Multimodal Relevance**    | ❌ 未实现 | 多模态相关性                    |

### 2. Nvidia Metrics（企业级指标）

| 指标名称                      | 项目状态  | 说明                          |
| ------------------------- | ----- | --------------------------- |
| **Answer Accuracy**       | ❌ 未实现 | 回答准确性                       |
| **Context Relevance**     | ❌ 未实现 | 上下文相关性                      |
| **Response Groundedness** | ❌ 未实现 | 回答基础性（类似 Faithfulness 但有区别） |

### 3. Agents/Tool Use Cases（智能体指标）

| 指标名称                    | 项目状态  | 说明         |
| ----------------------- | ----- | ---------- |
| **Topic adherence**     | ❌ 未实现 | 主题遵守度      |
| **Tool call Accuracy**  | ❌ 未实现 | 工具调用准确性    |
| **Tool Call F1**        | ❌ 未实现 | 工具调用 F1 分数 |
| **Agent Goal Accuracy** | ❌ 未实现 | 智能体目标准确性   |

### 4. Natural Language Comparison（自然语言对比指标）

| 指标名称                          | 项目状态  | 说明         |
| ----------------------------- | ----- | ---------- |
| Factual Correctness           | ✅ 已实现 | 事实正确性      |
| Semantic Similarity           | ✅ 已实现 | 语义相似度      |
| **Non LLM String Similarity** | ❌ 未实现 | 非LLM字符串相似度 |
| **BLEU Score**                | ❌ 未实现 | 机器翻译经典指标   |
| **CHRF Score**                | ❌ 未实现 | 字符级 F 分数   |
| **ROUGE Score**               | ❌ 未实现 | 文本摘要经典指标   |
| **String Presence**           | ❌ 未实现 | 字符串存在性检查   |
| **Exact Match**               | ❌ 未实现 | 精确匹配       |

### 5. SQL 指标

| 指标名称                                | 项目状态  | 说明          |
| ----------------------------------- | ----- | ----------- |
| **Execution based Datacompy Score** | ❌ 未实现 | 基于执行的数据对比分数 |
| **SQL query Equivalence**           | ❌ 未实现 | SQL 查询等价性   |

### 6. General Purpose（通用指标）

| 指标名称                                  | 项目状态  | 说明          |
| ------------------------------------- | ----- | ----------- |
| **Aspect critic**                     | ❌ 未实现 | 方面批评家，多维度评估 |
| **Simple Criteria Scoring**           | ❌ 未实现 | 简单标准评分      |
| **Rubrics based scoring**             | ❌ 未实现 | 基于评分标准的评分   |
| **Instance specific rubrics scoring** | ❌ 未实现 | 实例特定评分标准    |

### 7. Other Tasks（其他任务）

| 指标名称              | 项目状态  | 说明     |
| ----------------- | ----- | ------ |
| **Summarization** | ❌ 未实现 | 摘要评估指标 |

***

## 三、差距分析总结

### 覆盖率统计

* **已实现**：6 个指标

* **官方提供**：约 25+ 个指标

* **覆盖率**：约 24%

### 关键缺失分类

#### 高优先级（对 RAG 评测价值高）

1. **Noise Sensitivity** - 评估模型对噪声上下文的处理能力，对金融研报场景很重要
2. **Context Entities Recall** - 基于实体的召回评估，适合金融领域实体密集的特点
3. **BLEU/ROUGE/CHRF** - 传统 NLP 指标，无需 LLM 调用，成本低、速度快

#### 中优先级（增强评测维度）

1. **Aspect Critic** - 多维度评估，可自定义评估维度
2. **Rubrics based scoring** - 基于评分标准的评估，适合金融研报的专业性评估
3. **Answer Accuracy (Nvidia)** - 更准确的回答准确性评估

#### 低优先级（特定场景）

1. **Multimodal** 指标 - 项目当前不涉及多模态
2. **Agents/Tool Use** 指标 - 项目当前是纯 RAG 场景
3. **SQL** 指标 - 项目不涉及 SQL 生成

***

## 四、实施计划

### Phase 1: 补充高价值 RAG 指标（建议优先）

#### 1.1 添加 Noise Sensitivity

* **用途**：评估模型是否会被无关上下文误导

* **金融场景价值**：研报中常有大量背景信息，需要模型能识别真正相关的内容

* **实现方式**：在 `_create_metrics()` 中添加 `_NoiseSensitivity` 导入

#### 1.2 添加 Context Entities Recall

* **用途**：基于命名实体的召回评估

* **金融场景价值**：年报/研报中公司名、金额、日期等实体是关键信息

* **实现方式**：需要 NER 支持，可能需要额外的实体识别模型

#### 1.3 添加传统 NLP 指标（BLEU/ROUGE/CHRF）

* **用途**：快速、低成本的质量评估

* **优势**：不需要 LLM 调用，计算快速

* **实现方式**：RAGAS 已内置，直接导入即可

### Phase 2: 添加通用评估框架

#### 2.1 Aspect Critic

* **用途**：多维度评估回答质量

* **可定制维度**：专业性、完整性、准确性、可读性等

* **金融场景价值**：可针对金融研报特点定制评估维度

#### 2.2 Rubrics based scoring

* **用途**：基于预定义评分标准的评估

* **金融场景价值**：可定义金融专业评分标准

### Phase 3: 集成 Nvidia Metrics（可选）

如果需要更企业级的评估，可考虑集成：

* Answer Accuracy

* Context Relevance

* Response Groundedness

***

## 五、具体实现步骤

### Step 1: 更新 `ragas_evaluator.py` 添加新指标支持

```python
# 需要新增的导入
from ragas.metrics import (
    # 现有指标...
    _NoiseSensitivity as NoiseSensitivity,
    _ContextEntitiesRecall as ContextEntitiesRecall,
    _BleuScore as BleuScore,
    _RougeScore as RougeScore,
    _CHRF as CHRF,
    _NonLLMStringSimilarity as NonLLMStringSimilarity,
    _ExactMatch as ExactMatch,
    _AspectCritic as AspectCritic,
    _RubricsScore as RubricsScore,
)
```

### Step 2: 更新 `_generation_metrics` 列表

```python
self._generation_metrics = [
    # 现有指标
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "factual_correctness",
    "semantic_similarity",
    # 新增 RAG 指标
    "noise_sensitivity",
    "context_entities_recall",
    # 新增传统 NLP 指标
    "bleu_score",
    "rouge_score",
    "chrf_score",
    "non_llm_string_similarity",
    "exact_match",
    # 新增通用指标
    "aspect_critic",
    "rubrics_score",
]
```

### Step 3: 更新 `_create_metrics()` 方法

为新指标添加创建逻辑，特别是：

* `AspectCritic` 需要定义评估维度

* `RubricsScore` 需要定义评分标准

* `ContextEntitiesRecall` 可能需要 NER 模型

### Step 4: 更新配置文件

在 `exp_configs/ragas_evaluation/` 中添加新指标的配置示例。

### Step 5: 更新文档

更新 `docs/guides/ragas-evaluation.md` 说明新增指标。

### Step 6: 添加测试

在 `tests/test_evaluators.py` 中添加新指标的测试用例。

***

## 六、风险与注意事项

1. **API 版本兼容性**：RAGAS 更新频繁，需要确认当前 pixi.toml 中的 ragas 版本是否支持所有新指标
2. **LLM 调用成本**：部分新指标需要额外的 LLM 调用，可能增加评测成本
3. **实体识别依赖**：`Context Entities Recall` 可能需要额外的 NER 模型
4. **评分标准定义**：`Aspect Critic` 和 `Rubrics Score` 需要针对金融场景定义合适的标准

***

## 七、推荐实施顺序

1. **立即实施**：添加传统 NLP 指标（BLEU/ROUGE/CHRF/Exact Match）- 无需 LLM，成本低
2. **短期实施**：添加 Noise Sensitivity - 对 RAG 质量评估价值高
3. **中期实施**：添加 Aspect Critic/Rubrics Score - 需要定义金融场景评分标准
4. **长期考虑**：Context Entities Recall - 需要评估 NER 方案
5. **暂不实施**：多模态、Agent、SQL 相关指标（与当前场景不符）

