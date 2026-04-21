# RAGAS 五大指标审查与修复计划

## 审查结论

### 五大指标可计算性（假设存在标注良好的 Ground Truth）

| 指标 | 需要 GT | 评测对象 | 当前可计算? | 数据流完整性 |
|------|---------|---------|------------|-------------|
| Faithfulness | ❌ | 生成 | ✅ 可以 | `user_input` + `response` + `retrieved_contexts` 均正确映射 |
| Answer Relevancy | ❌ | 生成 | ✅ 可以 | `user_input` + `response` 正确映射 |
| Context Precision | ✅ | 检索 | ⚠️ 有条件 | `reference` 映射正确，但必须放在 `generation` 下而非 `retrieval` |
| Context Recall | ✅ | 检索 | ⚠️ 有条件 | 同上 |
| Answer Correctness | ✅ | 端到端 | ⚠️ 有条件 | `reference` 映射正确，但必须放在 `generation` 下 |

**核心结论**：假设 GT 存在，五个指标在 RAGAS 后端均可计算，但存在若干设计缺陷和 bug 需要修复，否则用户体验差且容易踩坑。

---

## 发现的问题

### 问题 1（通用·高优先级）：`context_precision` / `context_recall` 无法放在 `retrieval` 配置项下

**现象**：
- `VALID_RETRIEVAL_METRICS` 不包含 `context_precision` 和 `context_recall`
- 实验配置验证（[experiment.py:230-238](file:///b:/project/ash-easy-rag/src/experiment.py#L230-L238)）会拒绝将它们放在 `retrieval` 下
- 用户必须将它们放在 `generation` 下才能通过验证，但它们概念上是检索指标

**影响**：
- 配置语义混乱：检索指标必须写在生成指标区域
- 与 Builtin 后端不一致：Builtin 将它们归类为 `retrieval_metrics`
- 用户容易配错导致验证失败

**修复方案**：
- 在 `VALID_RETRIEVAL_METRICS` 中增加 `context_precision` 和 `context_recall`
- 修改 `evaluate_test_set()` 中 RAGAS 路径，同时从 `retrieval_metrics` 和 `generation_metrics` 中收集 RAGAS 支持的指标
- 更新实验配置模板，将 `context_precision` / `context_recall` 移到 `retrieval` 下

### 问题 2（通用·高优先级）：`compute_aggregate_metrics` 对 RAGAS 和 Builtin 的同类指标聚合路径不一致

**现象**：
- Builtin 后端：`context_precision` / `context_recall` 走 `r["llm_retrieval"]` 路径，聚合为顶层 `avg_context_precision` / `avg_context_recall`
- RAGAS 后端：`context_precision` / `context_recall` 走 `r["generation"]` 路径，聚合为 `generation_metrics.avg_context_precision` / `generation_metrics.avg_context_recall`
- 双后端时，同一指标出现在两个不同位置，值可能不同

**影响**：
- 跨后端对比困难
- 报告生成和实验对比功能无法统一处理这些指标

**修复方案**：
- 在 `compute_aggregate_metrics` 中统一处理：无论来自哪个后端，`context_precision` / `context_recall` 都聚合到统一的顶层位置
- 从 `generation_metrics` 中提取这些指标并移到 `llm_retrieval_metrics` 区域

### 问题 3（通用·中优先级）：`reference` 为 None 时无警告，RAGAS 静默产出 NaN

**现象**：
- `_build_ragas_dataset` 中 `reference=sample.get("expected_answer")` 无默认值
- 当 `expected_answer` 缺失时，`reference=None`
- `evaluate_batch` 使用 `raise_exceptions=False`，RAGAS 静默返回 NaN
- `evaluate_single` 使用 `raise_exceptions=True`，会直接抛异常

**影响**：
- 用户无法知道为什么某些指标缺失
- `evaluate_single` 模式下会崩溃

**修复方案**：
- 在 `_build_ragas_dataset` 或 `evaluate_batch` 开始前检查：如果请求的指标需要 `reference` 但 `reference` 为 None，记录 warning
- 在 `evaluate_single` 中对缺少 `reference` 的情况做优雅降级

### 问题 4（通用·低优先级）：死代码 `llm_retrieval_metrics`

**现象**：
- [run_experiment.py:1277](file:///b:/project/ash-easy-rag/eval/run_experiment.py#L1277) 读取 `exp_config.evaluation.get("llm_retrieval_metrics", [])` 但从未使用

**修复方案**：删除该行

### 问题 5（RAGAS·中优先级）：使用私有类导入（`_Faithfulness` 等）

**现象**：
- [ragas_evaluator.py:203-210](file:///b:/project/ash-easy-rag/eval/evaluators/ragas_evaluator.py#L203-L210) 使用 `from ragas.metrics import _Faithfulness as Faithfulness`
- RAGAS 0.4.x 的公开 API 是 `from ragas.metrics.collections import ContextPrecision` 等
- 私有 API 随时可能变更

**影响**：RAGAS 升级时可能 break

**修复方案**：
- 优先从 `ragas.metrics.collections` 导入，fallback 到 `ragas.metrics` 的私有类
- 添加版本兼容性处理

### 问题 6（RAGAS·低优先级）：`evaluate()` 调用传递冗余的 `llm` 和 `embeddings` 参数

**现象**：
- `_create_metrics` 已经将 `llm` 和 `embeddings` 设置到每个 metric 实例上
- `evaluate()` 调用时又传了 `llm=self._llm, embeddings=self._embeddings`
- RAGAS 0.4.x 中这些参数是冗余的

**修复方案**：移除 `evaluate()` 调用中的 `llm` 和 `embeddings` 参数

---

## 实施步骤

### Step 1：修复 `VALID_RETRIEVAL_METRICS` 和配置验证（问题 1）

1. 在 `src/experiment.py` 中将 `context_precision` 和 `context_recall` 加入 `VALID_RETRIEVAL_METRICS`
2. 更新 `RAGAS_EXCLUSIVE_METRICS` 计算：从 `VALID_RAGAS_METRICS - VALID_GENERATION_METRICS` 改为 `VALID_RAGAS_METRICS - VALID_GENERATION_METRICS - VALID_RETRIEVAL_METRICS`（避免重复）
3. 修改验证逻辑：当 `context_precision` / `context_recall` 出现在 `retrieval` 下且 `ragas` 在 backends 中时，不报错
4. 更新 `ragas_only.yaml` 和 `ragas_builtin.yaml` 模板，将 `context_precision` / `context_recall` 移到 `retrieval` 下

### Step 2：修复 `evaluate_test_set` 的 RAGAS 指标收集逻辑（问题 1 续）

1. 修改 `evaluate_test_set()` 中 RAGAS 路径的指标收集：同时从 `retrieval_metrics` 和 `generation_metrics` 中收集 RAGAS 支持的指标
2. 确保 `context_precision` / `context_recall` 无论放在 `retrieval` 还是 `generation` 下都能被 RAGAS 后端计算

### Step 3：统一 `compute_aggregate_metrics` 聚合路径（问题 2）

1. 在 `compute_aggregate_metrics` 中，从 `generation` 字典中提取 `context_precision` / `context_recall` / `answer_correctness`
2. 将它们统一聚合到 `llm_retrieval_metrics` 区域（`context_precision` / `context_recall`）和 `generation_metrics` 区域（`answer_correctness`）
3. 确保双后端场景下不重复计算

### Step 4：添加 `reference` 缺失警告（问题 3）

1. 在 `RagasEvaluator.evaluate_batch` 中，检查请求的指标是否需要 `reference`
2. 如果 `reference` 为 None 但指标需要它，记录 warning 并从指标列表中移除该指标
3. 在 `evaluate_single` 中做同样处理，避免 `raise_exceptions=True` 导致崩溃

### Step 5：修复 RAGAS 私有类导入（问题 5）

1. 修改 `_create_metrics` 中的导入逻辑：优先使用 `ragas.metrics.collections` 的公开 API
2. 添加 fallback 到 `ragas.metrics` 的私有类导入
3. 添加对应的测试

### Step 6：清理冗余代码（问题 4、6）

1. 删除 `run_experiment.py:1277` 的死代码 `llm_retrieval_metrics`
2. 移除 `evaluate()` 调用中的冗余 `llm` 和 `embeddings` 参数

### Step 7：补充测试

1. 为 `context_precision` / `context_recall` 在 `retrieval` 配置下的验证添加测试
2. 为 `reference` 缺失时的警告行为添加测试
3. 为 `compute_aggregate_metrics` 的统一聚合路径添加测试
4. 为 RAGAS 指标从 `retrieval_metrics` 收集的路径添加测试

---

## 不在本次修复范围内

- Builtin 后端的 bug（已有其他分支处理）
- Builtin 后端 `contexts` 参数传入 filenames 而非 text content 的问题
- RAGAS 版本升级（当前锁定 `>=0.4.3, <0.5`）
- Ground Truth 手动标注功能（用户尚未开始）
