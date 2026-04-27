# 评测系统整合状态分析与清洗计划

## 一、项目现状综合评价

### 1. 两个分支的整合成果

**fix-eval分支**（原有评测系统深度重构）：
- 创建了统一的Evaluator抽象基类 `BaseEvaluator`
- 实现了 `EvaluationResult` 标准化结果格式
- 重构了评测流程，采用Evaluator架构模式
- 增加了大量增强指标：Context Precision、Context Recall、Chunk-level、Dedup、FPR

**add-ragas分支**（RAGAS评测框架集成）：
- 实现了 `RagasEvaluator` 类，继承自 `BaseEvaluator`
- 集成了6个RAGAS指标：faithfulness、answer_relevancy、context_precision、context_recall、answer_correctness、semantic_similarity
- 使用LangchainLLMWrapper适配LongCat API
- 支持批量评估，性能更优

**整合后的架构**：
```
eval/evaluators/
├── base.py              # 抽象基类 BaseEvaluator + EvaluationResult
├── builtin_evaluator.py # 原有指标的统一封装
└── ragas_evaluator.py   # RAGAS框架集成
```

### 2. 两个系统的配合情况

#### ✅ 良好配合的方面：

1. **统一的抽象接口**
   - 两个Evaluator都继承自 `BaseEvaluator`
   - 都实现了 `evaluate_single()` 和 `evaluate_batch()` 方法
   - 使用统一的 `EvaluationResult` 返回格式

2. **实验系统支持双后端**
   - `run_experiment.py` 的 `_create_evaluators()` 函数可以创建多个evaluator
   - 配置中通过 `evaluation.backends: ["builtin", "ragas"]` 控制
   - 评测结果可以合并（builtin提供retrieval metrics，ragas提供generation metrics）

3. **指标分工明确**
   - **BuiltinEvaluator**: 负责 retrieval metrics (hit_rate, mrr, ndcg)
   - **RagasEvaluator**: 负责 generation metrics (faithfulness, answer_relevancy等)
   - 两者通过 `_evaluate_with_builtin()` 和 `_evaluate_with_ragas()` 分别运行

4. **实验配置模板完善**
   - `ragas_builtin.yaml`: 双后端评测
   - `ragas_only.yaml`: 纯RAGAS评测
   - 支持灵活的指标组合

#### ⚠️ 存在的问题和冗余：

## 二、需要清洗的问题清单

### 问题1：两套评测流程并存，逻辑混乱

**严重程度**: 🔴 高

**现状**：
- `run_eval.py` 使用旧的评测流程（直接调用metrics函数）
- `run_experiment.py` 使用新的Evaluator架构
- 两者功能重叠，但实现方式完全不同

**具体问题**：
1. `run_eval.py` 的 `run_evaluation()` 函数（L34-305）直接调用metrics函数
2. `run_experiment.py` 的 `evaluate_test_set()` 函数使用Evaluator架构
3. `run_experiment.py` 中还保留了 `_evaluate_test_set_legacy()` 函数（L1046-1248）作为向后兼容
4. 两套流程的指标计算逻辑重复，维护成本高

**清洗方案**：
- 方案A：完全废弃 `run_eval.py`，统一使用 `run_experiment.py`
- 方案B：重构 `run_eval.py` 使用Evaluator架构
- **推荐方案A**：因为 `run_experiment.py` 的架构更完善，支持多后端

### 问题2：`run_experiment.py` 中的Legacy代码

**严重程度**: 🟡 中

**现状**：
- `_evaluate_test_set_legacy()` 函数有200多行代码
- 使用直接调用metrics函数的方式，与Evaluator架构并存
- 只在 `exp_config is None or system_config is None` 时调用（向后兼容）

**清洗方案**：
- 确认所有实验配置都使用新的Evaluator架构后
- 移除 `_evaluate_test_set_legacy()` 函数
- 简化 `evaluate_test_set()` 函数，移除兼容逻辑

### 问题3：Metrics函数重复调用路径

**严重程度**: 🟡 中

**现状**：
- `BuiltinEvaluator.evaluate_single()` 调用 `calculate_faithfulness()` 和 `calculate_answer_relevancy()`
- `run_eval.py` 也直接调用这些函数
- `run_experiment.py` 的legacy流程也调用这些函数
- 导致同一套metrics被多处调用，容易不一致

**清洗方案**：
- 统一通过Evaluator调用metrics
- 保留metrics.py作为底层实现，但只通过Evaluator暴露

### 问题4：指标配置的碎片化

**严重程度**: 🟡 中

**现状**：
- `run_eval.py` 使用 `metrics_config`, `generation_metrics_config`, `llm_retrieval_metrics_config`
- `run_experiment.py` 使用 `evaluation.metrics.retrieval` 和 `evaluation.metrics.generation`
- `evaluation.backends` 控制使用哪些evaluator
- 配置项名称和结构不一致

**具体问题**：
1. Context Precision/Recall在两个地方都有实现：
   - `metrics.py` 中的 `calculate_context_precision()` 和 `calculate_context_recall()`
   - RAGAS框架也提供这些指标
2. 两套实现可能产生不同的结果

**清洗方案**：
- 统一指标命名和配置
- 明确哪些指标使用builtin实现，哪些使用RAGAS实现
- 或者提供配置选项让用户选择

### 问题5：Evaluator的方法签名不一致

**严重程度**: 🟢 低

**现状**：
- `BuiltinEvaluator.evaluate_single()` 接受 `retrieval_metrics` 和 `generation_metrics` 参数
- `RagasEvaluator.evaluate_single()` 只接受 `generation_metrics` 参数
- `BaseEvaluator.evaluate_single()` 的抽象签名没有这些参数

**清洗方案**：
- 统一方法签名，都接受可选的metrics参数
- 或者在文档中明确说明各evaluator的参数差异

### 问题6：测试覆盖不完整

**严重程度**: 🟡 中

**现状**：
- `test_evaluators.py` 测试了BuiltinEvaluator
- 但没有完整的RagasEvaluator测试（因为需要真实的API）
- 缺少集成测试验证两个evaluator的配合

**清洗方案**：
- 为RagasEvaluator添加mock测试
- 添加集成测试验证双后端配合
- 测试Evaluator结果合并逻辑

### 问题7：`run_eval.py` 中硬编码的默认指标

**严重程度**: 🟢 低

**现状**：
```python
DEFAULT_RETRIEVAL_METRICS = ["hit_rate", "mrr", "ndcg"]
DEFAULT_GENERATION_METRICS = ["faithfulness", "answer_relevancy"]
DEFAULT_LLM_RETRIEVAL_METRICS = ["context_precision", "context_recall"]
```

**清洗方案**：
- 如果采用方案A废弃run_eval.py，则无需处理
- 如果保留，则应与实验配置模板保持一致

## 三、推荐的清洗优先级

### Phase 1: 立即执行（高优先级）

1. **统一评测流程入口**
   - 决定废弃 `run_eval.py` 或完全重构它
   - 所有评测都通过 `run_experiment.py` 进行
   - 更新文档和脚本引用

2. **清理Legacy代码**
   - 移除 `_evaluate_test_set_legacy()`
   - 简化 `evaluate_test_set()` 函数

### Phase 2: 短期内执行（中优先级）

3. **统一指标实现**
   - 决定context_precision/Recall使用builtin还是RAGAS
   - 或者保留两套但明确区分
   - 更新配置文档

4. **完善测试**
   - 添加RagasEvaluator的mock测试
   - 添加双后端集成测试
   - 确保所有测试通过

5. **统一配置格式**
   - 标准化所有评测相关的配置项
   - 更新实验模板

### Phase 3: 长期优化（低优先级）

6. **优化Evaluator接口**
   - 统一方法签名
   - 添加更多文档

7. **性能优化**
   - RAGAS批量评估的性能调优
   - 缓存LLM调用结果

## 四、验证当前状态的建议步骤

1. **运行现有测试**
   ```bash
   pixi run pytest tests/test_evaluators.py -v
   pixi run pytest tests/test_run_experiment.py -v
   pixi run pytest tests/test_metrics.py -v
   ```

2. **检查配置一致性**
   - 对比所有实验配置文件的evaluation部分
   - 确保使用统一的配置格式

3. **验证双后端配合**
   - 使用 `ragas_builtin.yaml` 运行一个小规模测试
   - 检查输出结果中是否同时包含builtin和RAGAS指标
   - 验证结果合并逻辑是否正确

## 五、总结

两个分支的整合总体上是成功的：
- ✅ 架构设计合理，Evaluator抽象层统一了两个系统
- ✅ 指标分工明确，builtin负责检索，RAGAS负责生成
- ✅ 实验系统支持灵活的双后端配置

主要问题在于：
- 🔴 两套评测流程并存（run_eval.py vs run_experiment.py）
- 🟡 Legacy代码未清理，增加了维护成本
- 🟡 指标实现有重复（context_precision/Recall）
- 🟡 测试覆盖不完整

**建议立即开始Phase 1的清洗工作**，特别是统一评测流程入口和清理Legacy代码。
