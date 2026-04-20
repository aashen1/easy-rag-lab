# 代码冲突解决计划

## 一、冲突概览

当前 `dev` 分支存在 3 个文件的合并冲突，来自两个并行开发的 feature 分支：

1. **builtin 评测系统重构分支**（HEAD）- 扩展了原有的 builtin 评测系统
2. **RAGAS 集成分支**（add-ragas）- 接入了 RAGAS 评测框架

### 冲突文件清单

| 文件 | 冲突行数 | 冲突类型 |
|------|---------|---------|
| `src/experiment.py` | ~45 行 | 常量定义冲突 |
| `eval/run_experiment.py` | ~150 行 | 导入 + 函数实现冲突 |
| `docs/guides/evaluation-metrics.md` | ~200 行 | 文档内容冲突 |

---

## 二、冲突分析

### 2.1 src/experiment.py

**冲突内容：**
- HEAD: 定义了 `VALID_ON_MISSING_VALUES` + `is_new_format()` / `get_test_set_name()` 函数
- add-ragas: 定义了 `VALID_EVALUATION_BACKENDS` + `VALID_RAGAS_METRICS` + `RAGAS_EXCLUSIVE_METRICS`

**分析：**
这两个改动是**完全独立且互补**的：
- HEAD 添加的是测试集格式处理工具函数
- add-ragas 添加的是评测后端和指标常量

**解决方案：** 保留两者，合并到一个代码块中

### 2.2 eval/run_experiment.py

**冲突内容：**
- HEAD: 导入大量 metrics 函数（chunk/dedup/fpr 相关），保留 legacy 评测流程，支持 equivalence_groups
- add-ragas: 导入 evaluators 模块，实现新的 evaluator-based 评测流程

**分析：**
- HEAD 扩展了 legacy 评测系统的功能（chunk-level metrics, dedup metrics, FPR, equivalence groups）
- add-ragas 引入了新的抽象层（BaseEvaluator, BuiltinEvaluator, RagasEvaluator）

**解决方案：**
需要**整合两个方案**：
1. 保留 HEAD 的 metrics 导入（用于 legacy 模式）
2. 保留 add-ragas 的 evaluators 导入（用于新 backend 模式）
3. 在 `evaluate_test_set()` 函数中，优先使用 evaluator 模式，但需要支持 equivalence_groups 等 HEAD 新增的功能
4. `compute_aggregate_metrics()` 需要合并两者的聚合逻辑

### 2.3 docs/guides/evaluation-metrics.md

**冲突内容：**
- HEAD: 添加了 "LLM 检索指标" 章节（Context Precision/Recall from DeepEval）
- HEAD: 添加了 "问题类型的检索指标适用性" 章节
- add-ragas: 添加了 "RAGAS 生成指标" 章节
- add-ragas: 更新了指标对比表格

**分析：**
文档冲突主要是**内容组织方式**的不同，而非技术冲突。

**解决方案：**
1. 保留概述中的双后端说明（builtin + ragas）
2. 保留 "LLM 检索指标" 章节（来自 HEAD）
3. 保留 "RAGAS 生成指标" 章节（来自 add-ragas）
4. 保留 "问题类型的检索指标适用性" 章节（来自 HEAD）
5. 合并指标对比表格，包含所有指标

---

## 三、解决策略

### 策略选择：功能整合（而非二选一）

两个分支的改动都是**有价值且互补**的：
- builtin 重构提供了更细粒度的检索指标（chunk-level, dedup, FPR）
- RAGAS 集成提供了业界标准的生成指标和灵活的 backend 切换

**目标：** 让用户可以同时使用两种评测方式

---

## 四、具体解决步骤

### Step 1: 解决 src/experiment.py

```python
# 合并后的常量定义（保留两者）
VALID_RETRIEVAL_METRICS = {"hit_rate", "mrr", "ndcg", "chunk_hit_rate", "chunk_mrr", "chunk_ndcg", "dedup_hit_rate", "dedup_mrr", "dedup_ndcg", "false_positive_rate"}
VALID_GENERATION_METRICS = {"faithfulness", "answer_relevancy"}
VALID_ON_MISSING_VALUES = {"auto", "clean_only", "strict"}
VALID_EVALUATION_BACKENDS = {"builtin", "ragas"}
VALID_RAGAS_METRICS = {
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
    "semantic_similarity",
}
RAGAS_EXCLUSIVE_METRICS = VALID_RAGAS_METRICS - VALID_GENERATION_METRICS

# 保留 HEAD 的函数
def is_new_format(test_set_config: Dict[str, Any]) -> bool:
    ...

def get_test_set_name(test_set_config: Dict[str, Any]) -> str:
    ...
```

### Step 2: 解决 eval/run_experiment.py

#### 2.1 导入部分
```python
# 保留 HEAD 的 metrics 导入（用于 legacy 模式）
from eval.metrics import (
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    calculate_context_precision,
    calculate_context_recall,
    calculate_chunk_hit_rate,
    calculate_chunk_mrr,
    calculate_chunk_ndcg,
    calculate_false_positive_rate,
    calculate_dedup_hit_rate,
    calculate_dedup_mrr,
    calculate_dedup_ndcg,
    normalize_source,
    normalize_source_with_equivalence,
)

# 保留 add-ragas 的 evaluators 导入
from eval.evaluators.base import BaseEvaluator, EvaluationResult
from eval.evaluators.builtin_evaluator import BuiltinEvaluator
from eval.evaluators.ragas_evaluator import RagasEvaluator
```

#### 2.2 evaluate_test_set() 函数
保留 add-ragas 的 evaluator-based 实现，但需要考虑如何传递 equivalence_groups。

**方案：** 在 exp_config 中支持传递 equivalence_groups，BuiltinEvaluator 接收并使用它。

#### 2.3 compute_aggregate_metrics() 函数
合并两者的聚合逻辑：
- 保留 HEAD 的 chunk_level_metrics, dedup_metrics, false_positive_rate 计算
- 保留 add-ragas 的 generation_metrics 聚合
- 保留 HEAD 的 llm_retrieval (context_precision, context_recall) 聚合

### Step 3: 解决 docs/guides/evaluation-metrics.md

按照以下结构重组文档：

1. **概述** - 保留双后端说明（合并两者）
2. **检索指标** - 保留 HEAD 的内容
3. **生成质量指标** - 保留 HEAD 的内容（builtin 的 Faithfulness/Answer Relevancy）
4. **LLM 检索指标** - 保留 HEAD 的内容（Context Precision/Recall from DeepEval）
5. **RAGAS 生成指标** - 保留 add-ragas 的内容
6. **问题类型的检索指标适用性** - 保留 HEAD 的内容
7. **指标对比** - 合并表格，包含所有指标
8. **使用建议** - 保留两种配置示例

---

## 五、验证计划

解决冲突后，需要验证：

1. **配置验证**
   ```bash
   pixi run python -c "from src.experiment import ExperimentConfig; print('OK')"
   ```

2. **导入验证**
   ```bash
   pixi run python -c "from eval.run_experiment import *; print('OK')"
   ```

3. **Evaluator 验证**
   ```bash
   pixi run python -c "from eval.evaluators import BuiltinEvaluator, RagasEvaluator; print('OK')"
   ```

4. **语法检查**
   ```bash
   pixi run python -m py_compile src/experiment.py
   pixi run python -m py_compile eval/run_experiment.py
   ```

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 合并后功能不兼容 | 中 | 高 | 逐步验证每个函数 |
| equivalence_groups 在新 evaluator 中失效 | 中 | 中 | 检查 BuiltinEvaluator 是否支持 |
| 文档结构混乱 | 低 | 低 | 仔细重组文档结构 |
| 测试失败 | 中 | 中 | 运行现有测试套件 |

---

## 七、实施顺序

1. **src/experiment.py** - 最简单，常量合并
2. **docs/guides/evaluation-metrics.md** - 纯文档，无代码风险
3. **eval/run_experiment.py** - 最复杂，需要仔细整合逻辑

---

## 八、提交计划

每解决一个文件的冲突，立即提交：

```bash
# 解决 src/experiment.py
git add src/experiment.py
git commit -m "resolve: merge conflict in src/experiment.py - combine constants from both branches"

# 解决 docs/guides/evaluation-metrics.md
git add docs/guides/evaluation-metrics.md
git commit -m "resolve: merge conflict in evaluation-metrics.md - reorganize docs structure"

# 解决 eval/run_experiment.py
git add eval/run_experiment.py
git commit -m "resolve: merge conflict in run_experiment.py - integrate evaluator abstraction with legacy metrics"
```

---

*计划创建时间: 2026-04-21*
*基于分支: dev (合并 add-ragas 到 builtin-refactored)*
