# fix-eval 和 add-ragas 合并后项目状态分析与清理计划

## 一、合并历史回顾

```
* c2ae367 (HEAD -> dev) resolve: merge conflicts between builtin eval refactor and ragas integration
|\
| * 30db6ef (add-ragas) feat: replace factual_correctness with answer_correctness
... (add-ragas commits)
* | 2c59610 feat: merge fix-eval branch: prepare for v0.1.8
|\ \
| | (fix-eval commits)
```

**合并顺序**：
1. `fix-eval` 分支先合并 (commit 2c59610)
2. `add-ragas` 分支后合并 (commit c2ae367)，解决冲突

---

## 二、fix-eval 分支改动内容

### 核心改动
1. **新增 evaluator 抽象层**：
   - [base.py](file:///b/project/ash-easy-rag/eval/evaluators/base.py) - `BaseEvaluator` 抽象类和 `EvaluationResult` 数据类
   - [builtin_evaluator.py](file:///b/project/ash-easy-rag/eval/evaluators/builtin_evaluator.py) - 内置评测器封装

2. **新增评测指标** ([metrics.py](file:///b/project/ash-easy-rag/eval/metrics.py))：
   - Chunk级别指标：`calculate_chunk_hit_rate`, `calculate_chunk_mrr`, `calculate_chunk_ndcg`
   - 去重指标：`calculate_dedup_hit_rate`, `calculate_dedup_mrr`, `calculate_dedup_ndcg`
   - 误报率：`calculate_false_positive_rate`
   - LLM检索指标：`calculate_context_precision`, `calculate_context_recall`

3. **TestSetManager 系统** ([test_set_manager.py](file:///b/project/ash-easy-rag/src/test_set_manager.py))

---

## 三、add-ragas 分支改动内容

### 核心改动
1. **RAGAS 集成** ([ragas_evaluator.py](file:///b/project/ash-easy-rag/eval/evaluators/ragas_evaluator.py))：
   - 支持 RAGAS 框架的多种指标：faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness, semantic_similarity
   - 使用 LangchainLLMWrapper 适配 LongCat API

2. **实验配置更新**：
   - 新增 `exp_configs/ragas_evaluation/` 目录下的示例配置
   - 支持 `backends: ["builtin", "ragas"]` 配置

---

## 四、两部分配合情况评估

### 架构设计 ✅
- **Evaluator 抽象层设计良好**：`BaseEvaluator` 定义了统一接口，`BuiltinEvaluator` 和 `RagasEvaluator` 分别实现
- **配置驱动**：通过 `exp_config.evaluation.backends` 选择评测后端
- **指标分类清晰**：检索指标 vs 生成指标，builtin vs RAGAS

### 实际运行路径 ⚠️
- **主要路径**：当 `exp_config` 和 `system_config` 传入时，使用新的 evaluator 抽象层
- **遗留路径**：遗留代码 (`_evaluate_test_set_legacy`) 存在但不被主流程调用

### 问题发现

#### 严重问题 (Critical)
1. **_evaluate_test_set_legacy 函数有未定义变量**：
   - 函数签名只有 `(pipeline, test_set)` 两个参数
   - 但代码内部引用了 `llm_retrieval_metrics` (line 1072), `equivalence_groups` (line 1100) 等未定义变量
   - 如果 legacy 路径被触发，会抛出 `NameError`
   - **状态**：当前不被触发，但遗留代码存在风险

2. **run_eval.py 与新系统不兼容**：
   - `run_eval.py` 独立评测脚本仍然调用旧的指标计算函数
   - 它使用 `calculate_context_precision` 和 `calculate_context_recall` 从 `eval/metrics.py`
   - 这些指标与 RAGAS 的同名指标功能不同，容易混淆

#### 中等问题 (Medium)
3. **同名指标存在两个版本**：
   - `context_precision`:
     - builtin版本: `eval/metrics.py::calculate_context_precision` (基于 LLM-as-a-judge)
     - RAGAS版本: `eval/evaluators/ragas_evaluator.py` (RAGAS框架自带)
   - `context_recall` 同理
   - **建议**：添加明确的前缀或重命名以区分

4. **docstring 与实际签名不一致**：
   - `_evaluate_test_set_legacy` 的 docstring 列出了参数，但函数签名没有这些参数

---

## 五、可执行的清理工作

### 1. 修复遗留代码问题 (High Priority)

#### 清理 _evaluate_test_set_legacy
```python
# 选项 A: 完全移除遗留代码（如果确定不使用）
# 选项 B: 修复函数签名，添加缺失参数
```

### 2. 统一指标命名 (Medium Priority)
- 为避免混淆，可以考虑：
  - builtin 的 `context_precision` 改名为 `builtin_context_precision`
  - 或在文档中明确说明两者的区别

### 3. 更新 run_eval.py (Medium Priority)
- `run_eval.py` 可以选择：
  - 集成新的 evaluator 抽象层
  - 或者保持现状但在文档中说明它是独立脚本

### 4. 清理 docstring (Low Priority)
- 修正 `_evaluate_test_set_legacy` 的 docstring，使其与实际签名一致

### 5. 依赖和配置检查 (Low Priority)
- 检查 `pixi.lock` 和 `pixi.toml` 中的依赖是否一致
- 验证新增的 RAGAS 相关配置是否正确

---

## 六、推荐行动项

| 优先级 | 任务 | 预计工作量 |
|--------|------|-----------|
| High | 修复 `_evaluate_test_set_legacy` 未定义变量或移除 | 0.5h |
| Medium | 为 run_eval.py 添加使用说明或集成新系统 | 2h |
| Medium | 统一指标命名或加强文档区分 | 1h |
| Low | 清理过时 docstring | 0.5h |

---

## 七、总结

**整体状态：良好，但需清理**

- 架构设计合理，evaluator 抽象层实现清晰
- fix-eval 和 add-ragas 两部分可以很好地协同工作
- 主要风险在于遗留代码 (`_evaluate_test_set_legacy`) 的潜在bug
- 建议优先修复遗留代码问题，然后可以考虑统一指标命名或增强文档说明
