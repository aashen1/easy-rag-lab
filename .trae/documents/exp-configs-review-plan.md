# 实验配置文件审查与同步计划

## 背景

项目在 v0.1.8 和 v0.1.9 版本中引入了多项新功能和变更，部分实验配置文件可能需要更新以同步最新推荐写法。

### 近期关键变更

1. **Artifact 路径体系迁移**（v0.1.8）
   - `parser.output_dir`、`chunker.input_dir`、`chunker.output_dir` 已从 config.yaml 删除
   - 所有中间产物由 ArtifactCache 自动管理
   - **影响**：实验配置中不应再包含这些字段

2. **新增 `adversarial` 问题类型**（v0.1.9）
   - 对抗性问题支持，测试 RAG 系统边界场景
   - 默认分布为 0%（不影响现有实验）
   - TYPE_DISTRIBUTION 定义已更新

3. **Builtin 后端支持 `context_precision`/`context_recall`**（v0.1.8）
   - 这两个指标不再仅限 RAGAS 后端
   - `VALID_RETRIEVAL_METRICS` 已包含

4. **新增 Recall@K 指标**（v0.1.9）
   - `recall_3`、`recall_5`、`recall_10` 已实装验证

---

## 发现的问题

### 问题 1：`type_distribution` 缺少 `adversarial` 类型

**严重程度**：低（不影响运行，默认 0%）

**涉及文件**：
- `templates/_complete.yaml`
- `templates/_preset_chunk.yaml`
- `experiments/chunk_comparison.yaml`
- `experiments/overlap_comparison.yaml`
- `experiments/query_rewrite_comparison.yaml`
- `experiments/retrieval_comparison.yaml`
- `experiments/reranker_comparison.yaml`
- `experiments/strategy_comparison.yaml`
- `experiments/chunking_strategy_comparison.yaml`
- `systematic_study/` 下所有配置

**推荐修改**：在 `type_distribution` 中添加 `adversarial: 0.00`，保持与默认值一致，但显式声明以增强可读性。

---

### 问题 2：部分配置缺少 `backends` 字段

**严重程度**：低（默认为 `["builtin"]`，功能正常）

**涉及文件**：
- `baseline/baseline_1kpage.yaml`
- `baseline/baseline_5kpage.yaml`
- `baseline/baseline_10percent.yaml`
- `baseline/baseline_500page.yaml`
- `baseline/baseline_1kpage_no_ocr.yaml`
- `baseline/baseline_1kpage_annotated.yaml`
- `baseline/m1_10p.yaml`
- `smoke_tests/smoke_quick.yaml`
- `smoke_tests/smoke_full.yaml`
- `smoke_tests/quick_verify_metrics.yaml`
- `golden_tests/golden_test.yaml`
- `golden_tests/golden_150.yaml`
- `experiments/` 下所有配置
- `systematic_study/` 下所有配置
- `templates/_minimal.yaml`
- `templates/_preset_chunk.yaml`
- `templates/_preset_reranker.yaml`
- `templates/_preset_retrieval.yaml`

**推荐修改**：显式添加 `backends: ["builtin"]`，增强配置可读性和明确性。

---

### 问题 3：部分配置缺少 `context_precision`/`context_recall` 指标

**严重程度**：低（可选指标，不影响现有功能）

**涉及文件**：所有使用 builtin 后端的配置

**当前状态**：
- `backend_exp/baseline_5kpage_builtin.yaml` ✅ 已包含
- `backend_exp/baseline_5kpage_ragas_and_builtin.yaml` ✅ 已包含
- 其他 builtin 配置 ❌ 未包含

**推荐修改**：根据实验需求决定是否添加。这两个指标对 irrelevant 问题有特殊处理（需要 `expect_retrieval=True`），建议在需要精确评估检索质量的实验中添加。

---

### 问题 4：`llm_report` 字段不一致

**严重程度**：低（默认 `false`）

**涉及文件**：
- `baseline/baseline_5kpage.yaml`：有 `llm_report: true`
- `baseline/baseline_1kpage.yaml`：有 `llm_report: true`
- `backend_exp/` 下所有配置：有 `llm_report: true`
- 其他配置：缺少该字段

**推荐修改**：根据实验目的显式指定。正式实验建议 `true`，快速验证建议 `false`。

---

### 问题 5：模板文件需要更新

**严重程度**：中（模板是用户参考的基础）

**涉及文件**：
- `templates/_complete.yaml`：缺少 `adversarial` 类型、缺少 `backends` 字段
- `templates/_minimal.yaml`：缺少 `backends` 字段
- `templates/_preset_chunk.yaml`：缺少 `adversarial` 类型、缺少 `backends` 字段
- `templates/_preset_reranker.yaml`：缺少 `backends` 字段
- `templates/_preset_retrieval.yaml`：缺少 `backends` 字段

**推荐修改**：更新所有模板文件以反映最新推荐写法。

---

### 问题 6：README.md 示例代码需要更新

**严重程度**：中（文档是用户入门的第一参考）

**涉及文件**：
- `exp_configs/README.md`

**需要更新**：
- 快速开始示例中添加 `backends` 字段
- 问题类型分布示例中添加 `adversarial` 类型
- 更新指标列表说明

---

## 实施计划

### Phase 1：模板文件更新（优先级最高）

1. 更新 `templates/_complete.yaml`
   - 添加 `adversarial: 0.00` 到 `type_distribution`
   - 添加 `backends: ["builtin"]` 到 `evaluation`
   - 确保所有指标列表完整

2. 更新 `templates/_minimal.yaml`
   - 添加 `backends: ["builtin"]` 到 `evaluation`

3. 更新 `templates/_preset_chunk.yaml`
   - 添加 `adversarial: 0.00` 到 `type_distribution`
   - 添加 `backends: ["builtin"]` 到 `evaluation`

4. 更新 `templates/_preset_reranker.yaml`
   - 添加 `backends: ["builtin"]` 到 `evaluation`

5. 更新 `templates/_preset_retrieval.yaml`
   - 添加 `backends: ["builtin"]` 到 `evaluation`

### Phase 2：README.md 更新

1. 更新快速开始示例
2. 更新问题类型分布说明
3. 更新指标列表说明

### Phase 3：baseline 配置更新

1. 为所有 baseline 配置添加 `backends: ["builtin"]`
2. 根据实验目的决定是否添加 `llm_report` 字段

### Phase 4：experiments 配置更新

1. 为所有 experiments 配置添加 `backends: ["builtin"]`
2. 更新 `type_distribution` 添加 `adversarial: 0.00`

### Phase 5：systematic_study 配置更新

1. 为所有 systematic_study 配置添加 `backends: ["builtin"]`
2. 更新 `type_distribution` 添加 `adversarial: 0.00`

### Phase 6：smoke_tests 和 golden_tests 更新

1. 为所有测试配置添加 `backends: ["builtin"]`

---

## 不需要修改的内容

1. **`data.create_if_missing.sample_pages` vs `sample_ratio`**：两种方式都有效，保持现状
2. **RAGAS 相关配置**：`ragas_evaluation/` 和 `backend_exp/` 下的 RAGAS 配置已正确设置 `backends`
3. **Artifact 路径相关**：实验配置中无硬编码路径，无需修改

---

## 验证方法

1. **静态检查**：运行 `pixi run lint` 确保格式正确
2. **功能验证**：运行 `smoke_quick.yaml` 确保基本流程正常
3. **对比验证**：对比修改前后的实验结果，确保行为一致

---

## 总结

| 问题类型 | 严重程度 | 涉及文件数 | 是否影响运行 |
|---------|---------|-----------|-------------|
| 缺少 `adversarial` 类型 | 低 | ~20 | 否 |
| 缺少 `backends` 字段 | 低 | ~25 | 否 |
| 缺少 `context_*` 指标 | 低 | ~20 | 否 |
| `llm_report` 不一致 | 低 | ~15 | 否 |
| 模板文件过时 | 中 | 5 | 否 |
| README 示例过时 | 中 | 1 | 否 |

**建议**：优先更新模板文件和 README，其他配置可根据需要逐步更新。
