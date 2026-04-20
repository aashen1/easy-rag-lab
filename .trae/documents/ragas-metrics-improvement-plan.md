# RAGAS 指标接入完善计划

## 需求分析

### 用户需要的 5 个指标

| 指标 | 需要 GT | 评测对象 | 核心问题 | 状态 |
|------|---------|----------|----------|------|
| Faithfulness | ❌ | 生成 | 答案有没有瞎编？ | ✅ 已实现 |
| Answer Relevancy | ❌ | 生成 | 答案有没有跑题？ | ✅ 已实现 |
| Context Precision | ✅ | 检索 | 检索结果精不精？ | ✅ 已实现 |
| Context Recall | ✅ | 检索 | 检索有没有漏？ | ✅ 已实现 |
| Answer Correctness | ✅ | 端到端 | 答案对不对？ | ❌ **当前错误实现为 FactualCorrectness** |

### 问题诊断

当前项目在 [ragas_evaluator.py](eval/evaluators/ragas_evaluator.py) 中：
- 实现了 `factual_correctness`（事实正确性）
- 但用户需要的是 `answer_correctness`（答案正确性）

**两者的区别**：
- **Factual Correctness**：仅评估 claim-level（声明级别）的事实重叠，使用 F1/Precision/Recall 模式
- **Answer Correctness**：综合评估 = **factual_correctness + semantic_similarity** 的加权组合，更全面

根据 [RAGAS 官方文档](https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/answer_correctness.md)：
> Answer correctness encompasses two critical aspects: semantic similarity between the generated answer and the ground truth, as well as factual similarity. These aspects are combined using a weighted scheme to formulate the answer correctness score.

---

## 实现计划

### 步骤 1：更新 RAGAS 评测器核心实现

**文件**: `eval/evaluators/ragas_evaluator.py`

修改内容：
1. 将 `_generation_metrics` 中的 `"factual_correctness"` 替换为 `"answer_correctness"`
2. 更新导入：将 `_FactualCorrectness` 替换为 `_AnswerCorrectness`
3. 更新 `metric_map` 映射

```python
# 修改前
"factual_correctness": FactualCorrectness,

# 修改后
"answer_correctness": AnswerCorrectness,
```

### 步骤 2：更新指标创建逻辑

由于 `answer_correctness` 既需要 LLM 也需要 embeddings（用于语义相似度计算），需要确保：
- 创建 `answer_correctness` 指标时，同时传入 `llm` 和 `embeddings` 参数
- 这与当前的 `factual_correctness`（仅需 LLM）不同

### 步骤 3：更新配置文件

需要更新的配置文件：
1. `eval/metrics.py` - 如果有指标定义
2. `exp_configs/ragas_evaluation/*.yaml` - 实验配置模板
3. `src/experiment.py` - 如果有硬编码的指标列表

### 步骤 4：更新文档

需要更新的文档：
1. `docs/guides/ragas-evaluation.md` - 更新指标说明
2. `docs/guides/evaluation-metrics.md` - 如果有指标对比表

### 步骤 5：运行测试验证

运行现有测试确保修改没有破坏功能：
```bash
pixi run test tests/test_evaluators.py
```

---

## 实施顺序

1. ✅ 分析完成（当前步骤）
2. ⏳ 用户确认计划
3. 实施步骤 1-4
4. 运行测试验证
5. 提交代码
