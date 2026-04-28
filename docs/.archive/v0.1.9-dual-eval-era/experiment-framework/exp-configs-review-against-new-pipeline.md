# 实验配置审查：对照新链路推荐行为的改动建议

## 审查基准

对照计划书 `rag-testset-system-review-and-optimization.md` 中提出的优化方案，核心推荐行为包括：

1. **指标预设系统**（`metrics_preset`）：用 `core`/`extended`/`full`/`custom` 替代逐条罗列指标
2. **多后端指标解析**（`resolution_strategy` + `backend_priority`）：双后端时避免重叠指标重复计算
3. **双链路融合**（`quality_level`）：替代 `golden: true`
4. **Golden 审核守卫**（`golden_require_reviewed`）：确保只有审核通过的题目参与评测
5. **类型分布优化**：adversarial 类型应纳入更多配置

当前 `config.yaml` 已实现 `metrics_preset`/`resolution_strategy`/`backend_priority` 字段，但所有实验配置仍使用旧式逐条罗列 `metrics` 的方式，未利用新系统。

***

## 一、全局性问题（影响所有配置）

### 1.1 所有配置均未使用 `metrics_preset`

**现状**：所有 30+ 份配置文件都在 `evaluation.metrics` 下逐条罗列 retrieval 和 generation 指标，冗长且难以维护。

**建议**：根据实验场景选用预设，删除 `metrics` 逐条罗列：

| 实验场景             | 推荐 `metrics_preset` | 包含指标                                                                                              |
| ---------------- | ------------------- | ------------------------------------------------------------------------------------------------- |
| 日常实验 / 冒烟测试      | `core`              | hit\_rate, mrr, ndcg, recall\_3/5/10, faithfulness, answer\_relevancy                             |
| 深度诊断 / 消融实验      | `extended`          | core + chunk\_*, dedup\_*, context\_precision, context\_recall                                    |
| 版本发布 / Golden 基准 | `full`              | extended + answer\_correctness, semantic\_similarity, false\_positive\_rate, retrieval\_diversity |
| 特殊需求             | `custom`            | 配合 `custom_metrics` 自定义                                                                           |

**影响范围**：全部 30+ 份配置文件

**收益**：

* 配置文件大幅精简（每个文件减少 15-20 行 metrics 罗列）

* 新增指标时只需更新预设定义，无需逐文件修改

* 自动配合 `resolution_strategy` 避免双后端重复计算

### 1.2 双后端配置未指定 `resolution_strategy`

**现状**：使用 `backends: ["builtin", "ragas"]` 的配置未指定 `resolution_strategy`，依赖 config.yaml 的默认值 `priority_fallback`。

**建议**：双后端配置应显式声明 `resolution_strategy`，明确意图：

* **日常双后端**（如 `ragas_builtin.yaml`）：`resolution_strategy: "priority_fallback"` + `backend_priority: ["builtin", "ragas"]`

* **对标验证**（如 `baseline_5kpage_ragas_and_builtin.yaml`）：`resolution_strategy: "comparison"`

**影响文件**：

* `baseline_500page.yaml`

* `ragas_evaluation/ragas_builtin.yaml`

* `backend_exp/baseline_5kpage_ragas_and_builtin.yaml`

* `smoke_tests/quick_verify_metrics.yaml`

***

## 二、逐文件审查与改动建议

### 2.1 模板文件（templates/）

#### `_minimal.yaml`

| 项目                      | 现状            | 建议                                                    |
| ----------------------- | ------------- | ----------------------------------------------------- |
| metrics                 | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（极简模板应展示预设用法，而非罗列全部指标） |
| 缺少 resolution\_strategy | 无             | 添加 `resolution_strategy: "priority_fallback"`         |

**理由**：极简模板应引导用户使用预设系统，而非复制粘贴长指标列表。`extended` 预设适合大多数实验场景。

#### `_complete.yaml`

| 项目                      | 现状            | 建议                                                                                       |
| ----------------------- | ------------- | ---------------------------------------------------------------------------------------- |
| metrics                 | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`，并添加注释说明其他预设选项                                            |
| 缺少 resolution\_strategy | 无             | 添加 `resolution_strategy: "priority_fallback"` 和 `backend_priority: ["builtin", "ragas"]` |
| 缺少 custom\_metrics 示例   | 无             | 添加注释掉的 `custom_metrics` 示例                                                               |

**理由**：完整模板应展示所有新配置字段的用法，包括预设切换和自定义指标。

#### `_preset_chunk.yaml`

| 项目      | 现状            | 建议                                                                  |
| ------- | ------------- | ------------------------------------------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（分块实验需要 chunk\_\* 指标，属于 extended 级别） |

#### `_preset_retrieval.yaml`

| 项目      | 现状            | 建议                                                                  |
| ------- | ------------- | ------------------------------------------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（检索实验需要 dedup\_\* 指标，属于 extended 级别） |

#### `_preset_reranker.yaml`

| 项目      | 现状            | 建议                                            |
| ------- | ------------- | --------------------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（重排实验需要精细排序指标） |

### 2.2 基线实验（baseline/）

#### `baseline_10percent.yaml`

| 项目                 | 现状            | 建议                                             |
| ------------------ | ------------- | ---------------------------------------------- |
| metrics            | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "core"`（日常基线实验，core 足够）    |
| type\_distribution | 未指定（使用默认）     | 建议显式添加，包含 `adversarial: 0.00`（保持当前行为，但显式声明更清晰） |

#### `baseline_1kpage.yaml`

| 项目          | 现状            | 建议                                              |
| ----------- | ------------- | ----------------------------------------------- |
| metrics     | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（1k 页基线需要更细粒度诊断） |
| llm\_report | true          | 保留（基线实验需要详细报告）                                  |

#### `baseline_1kpage_annotated.yaml`

| 项目      | 现状            | 建议                                          |
| ------- | ------------- | ------------------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`，并在注释中说明预设含义 |
| 注释      | 已有详细指标注释      | 更新注释，说明 `metrics_preset` 的用法和各预设的区别         |

**理由**：注释版是用户学习配置的入口，应展示新系统的用法。

#### `baseline_1kpage_no_ocr.yaml`

| 项目      | 现状                           | 建议                              |
| ------- | ---------------------------- | ------------------------------- |
| 存在价值    | 文件自身注释说明"实际上没什么意义"           | **建议删除或移入 deprecated/ 目录**      |
| metrics | 逐条罗列 10+2 个指标（缺少 recall\_\*） | 若保留，改为 `metrics_preset: "core"` |

#### `baseline_500page.yaml`

| 项目                  | 现状                                                                                   | 建议                                                                                              |
| ------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| backends            | `["builtin", "ragas"]`                                                               | 保留双后端，但添加 `resolution_strategy: "priority_fallback"` + `backend_priority: ["builtin", "ragas"]` |
| metrics             | 逐条罗列，含 context\_precision/context\_recall + answer\_correctness/semantic\_similarity | 改为 `metrics_preset: "full"`（双后端全指标 = full 预设的典型场景）                                              |
| test\_sets strategy | `"hybrid"`                                                                           | 保留（这是有意使用 hybrid 策略）                                                                            |

#### `baseline_5kpage.yaml`

| 项目             | 现状            | 建议                                            |
| -------------- | ------------- | --------------------------------------------- |
| metrics        | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（大规模基线需要细粒度诊断） |
| num\_questions | 100           | 考虑是否需要这么多，100 题 × extended 指标 = 较高 token 成本   |

#### `m1_10p.yaml`

| 项目                | 现状                                 | 建议                                |
| ----------------- | ---------------------------------- | --------------------------------- |
| metrics           | 逐条罗列 13+2 个指标                      | 改为 `metrics_preset: "core"`（日常基线） |
| config\_overrides | 显式指定 chunker strategy/size/overlap | 可简化为 `{}`（与基线一致）                  |

### 2.3 正式实验（experiments/）

#### `chunk_comparison.yaml`

| 项目          | 现状            | 建议                                                   |
| ----------- | ------------- | ---------------------------------------------------- |
| metrics     | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（分块实验需要 chunk\_\* 指标） |
| adversarial | 0.00          | 考虑加入 `adversarial: 0.05`，测试分块对对抗性问题的鲁棒性              |

#### `chunking_strategy_comparison.yaml`

| 项目                 | 现状            | 建议                              |
| ------------------ | ------------- | ------------------------------- |
| metrics            | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |
| type\_distribution | 未指定           | 建议显式添加，包含 adversarial           |

#### `overlap_comparison.yaml`

| 项目          | 现状            | 建议                              |
| ----------- | ------------- | ------------------------------- |
| metrics     | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |
| adversarial | 0.00          | 考虑加入 `adversarial: 0.05`        |

#### `query_rewrite_comparison.yaml`

| 项目      | 现状            | 建议                              |
| ------- | ------------- | ------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |

#### `reranker_comparison.yaml`

| 项目      | 现状            | 建议                              |
| ------- | ------------- | ------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |

#### `retrieval_comparison.yaml`

| 项目      | 现状            | 建议                              |
| ------- | ------------- | ------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |

#### `strategy_comparison.yaml`

| 项目          | 现状                   | 建议                                                                   |
| ----------- | -------------------- | -------------------------------------------------------------------- |
| metrics     | 逐条罗列 13+2 个指标        | 改为 `metrics_preset: "extended"`                                      |
| adversarial | 所有 test\_set 均为 0.00 | `balanced_document` 应加入 `adversarial: 0.06`（与计划书推荐的 standard 质量等级一致） |

### 2.4 Golden 测试（golden\_tests/）

#### `golden_150.yaml`

| 项目                           | 现状            | 建议                                                                                                                         |
| ---------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `golden: true`               | 使用旧式标记        | 迁移为 `quality_level: "golden"`（计划书 2.3.4 双链路融合方案）                                                                           |
| 缺少 `golden_require_reviewed` | 无             | **添加** **`golden_require_reviewed: true`**（计划书 2.3.2 建议：确保只有审核通过的 Golden 题目参与评测）                                           |
| backends                     | `["builtin"]` | 考虑改为 `["builtin", "ragas"]` + `metrics_preset: "full"` + `resolution_strategy: "priority_fallback"`（Golden 作为项目级基准应使用全量指标） |
| metrics                      | 逐条罗列 16+2 个指标 | 改为 `metrics_preset: "full"`                                                                                                |
| 缺少 resolution\_strategy      | 无             | 添加 `resolution_strategy: "priority_fallback"`                                                                              |

**优先级**：高。Golden 测试集是项目级基准，应率先适配新系统。

#### `golden_test.yaml`

| 项目             | 现状                                           | 建议                                                                    |
| -------------- | -------------------------------------------- | --------------------------------------------------------------------- |
| 定位模糊           | 既非 golden（无 `golden: true`），又名为 golden\_test | 明确定位：如果是快速回归测试，改为普通 test\_set；如果是 golden，添加 `quality_level: "golden"` |
| metrics        | 逐条罗列 13+2 个指标                                | 改为 `metrics_preset: "core"`（10 题规模不需要 extended）                       |
| num\_questions | 10                                           | 对于 golden 回归测试偏少，建议至少 20                                              |

### 2.5 RAGAS 评测（ragas\_evaluation/）

#### `ragas_builtin.yaml`

| 项目                      | 现状                     | 建议                                                                                                                                                  |
| ----------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| backends                | `["builtin", "ragas"]` | 保留，但添加 `resolution_strategy: "priority_fallback"` + `backend_priority: ["builtin", "ragas"]`                                                        |
| metrics                 | 逐条罗列，含重叠指标             | 改为 `metrics_preset: "full"` + `resolution_strategy: "priority_fallback"`（避免 faithfulness/answer\_relevancy/context\_precision/context\_recall 重复计算） |
| 缺少 resolution\_strategy | 无                      | **必须添加**（当前双后端会重复计算 4 个重叠指标，token 浪费严重）                                                                                                             |

**Token 节省估算**：20 题 × 4 个重叠指标 × 2 后端 = 160 次 LLM 调用 → 优先级降级后 = 80 次，节省 50%。

#### `ragas_only.yaml`

| 项目      | 现状   | 建议                                                                                                                                                                   |
| ------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| metrics | 逐条罗列 | 改为 `metrics_preset: "custom"` + `custom_metrics: {retrieval: [context_precision, context_recall], generation: [faithfulness, answer_relevancy, answer_correctness]}` |
| 或更简洁    | —    | 直接用 `metrics_preset: "full"` + `backends: ["ragas"]`（RAGAS 只会计算自己支持的指标）                                                                                              |

#### `ragas_quick.yaml`

| 项目      | 现状                            | 建议                                                                 |
| ------- | ----------------------------- | ------------------------------------------------------------------ |
| metrics | retrieval 为空数组，generation 2 个 | 改为 `metrics_preset: "core"` + `backends: ["ragas"]`（冒烟测试用 core 足够） |

### 2.6 冒烟测试（smoke\_tests/）

#### `smoke_quick.yaml`

| 项目             | 现状            | 建议                                                           |
| -------------- | ------------- | ------------------------------------------------------------ |
| metrics        | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "core"`（1 题冒烟测试不需要 chunk\_*/dedup\_* 指标） |
| num\_questions | 1             | 保留（冒烟测试目的就是最小验证）                                             |

**收益**：core 预设下 LLM 调用从 \~11 次/题降至 \~3 次/题，冒烟测试更快。

#### `smoke_full.yaml`

| 项目          | 现状            | 建议                                           |
| ----------- | ------------- | -------------------------------------------- |
| metrics     | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（完整冒烟需要细粒度指标） |
| adversarial | 0.00          | 添加 `adversarial: 0.10`（完整冒烟应覆盖所有类型）          |

#### `quick_verify_metrics.yaml`

| 项目                 | 现状                                           | 建议                                                                                   |
| ------------------ | -------------------------------------------- | ------------------------------------------------------------------------------------ |
| backends           | `["builtin", "ragas"]`                       | 保留，但添加 `resolution_strategy: "comparison"`（此配置目的是验证指标可计算性，comparison 模式可同时看到两个后端的结果） |
| metrics            | 逐条罗列全量指标                                     | 改为 `metrics_preset: "full"` + `resolution_strategy: "comparison"`                    |
| type\_distribution | 缺少 reasoning/comparative/missing/adversarial | 补全类型分布，确保所有指标都有对应问题类型可计算                                                             |

**理由**：此配置的目的是"验证全指标支持"，应使用 `comparison` 模式确保两个后端都能正常计算。

### 2.7 后端对比实验（backend\_exp/）

#### `baseline_5kpage_builtin.yaml`

| 项目      | 现状                                                  | 建议                              |
| ------- | --------------------------------------------------- | ------------------------------- |
| metrics | 逐条罗列 15+2 个指标（含 context\_precision/context\_recall） | 改为 `metrics_preset: "extended"` |

#### `baseline_5kpage_ragas_and_builtin.yaml`

| 项目                      | 现状                     | 建议                                                                              |
| ----------------------- | ---------------------- | ------------------------------------------------------------------------------- |
| backends                | `["builtin", "ragas"]` | 保留，但**必须添加** `resolution_strategy: "comparison"`（此配置目的是"交叉验证"，应用 comparison 模式） |
| metrics                 | 逐条罗列                   | 改为 `metrics_preset: "full"` + `resolution_strategy: "comparison"`               |
| 缺少 resolution\_strategy | 无                      | **必须添加**                                                                        |

**理由**：此配置描述为"完整指标交叉验证"，正是 `comparison` 模式的典型场景。

#### `baseline_5kpage_ragas_only.yaml`

| 项目      | 现状   | 建议                                                  |
| ------- | ---- | --------------------------------------------------- |
| metrics | 逐条罗列 | 改为 `metrics_preset: "full"` + `backends: ["ragas"]` |

### 2.8 系统性研究（systematic\_study/）

#### `progressive_enhancement.yaml`

| 项目      | 现状            | 建议                                                 |
| ------- | ------------- | -------------------------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"`（递进实验需要细粒度指标追踪每层增量） |

#### `ablation_retrieval.yaml`

| 项目      | 现状            | 建议                              |
| ------- | ------------- | ------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |

#### `ablation_chunking.yaml`

| 项目      | 现状            | 建议                              |
| ------- | ------------- | ------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |

#### `ablation_query_rewrite.yaml`

| 项目      | 现状            | 建议                              |
| ------- | ------------- | ------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |

#### `interaction_effects.yaml`

| 项目      | 现状            | 建议                              |
| ------- | ------------- | ------------------------------- |
| metrics | 逐条罗列 13+2 个指标 | 改为 `metrics_preset: "extended"` |

***

## 三、优先级排序

### P0：必须修改（影响正确性或 token 成本）

| 文件                                       | 改动                                            | 理由                       |
| ---------------------------------------- | --------------------------------------------- | ------------------------ |
| `golden_150.yaml`                        | 添加 `golden_require_reviewed: true`            | 防止 rejected 题目污染基准评测     |
| `ragas_builtin.yaml`                     | 添加 `resolution_strategy: "priority_fallback"` | 双后端重叠指标重复计算，token 浪费 50% |
| `baseline_5kpage_ragas_and_builtin.yaml` | 添加 `resolution_strategy: "comparison"`        | 交叉验证场景应用 comparison 模式   |
| `quick_verify_metrics.yaml`              | 添加 `resolution_strategy: "comparison"`        | 全指标验证场景                  |
| `baseline_500page.yaml`                  | 添加 `resolution_strategy: "priority_fallback"` | 双后端无策略声明                 |

### P1：推荐修改（提升配置可维护性和一致性）

| 文件                                 | 改动                                         | 理由           |
| ---------------------------------- | ------------------------------------------ | ------------ |
| 全部 30+ 文件                          | `metrics` 罗列 → `metrics_preset`            | 配置精简、可维护性提升  |
| `golden_150.yaml`                  | `golden: true` → `quality_level: "golden"` | 适配双链路融合方案    |
| `golden_test.yaml`                 | 明确定位并调整                                    | 消除命名与实际行为的歧义 |
| `smoke_quick.yaml`                 | metrics\_preset: "core"                    | 冒烟测试加速       |
| `_minimal.yaml` / `_complete.yaml` | 展示预设用法                                     | 模板应引导用户使用新系统 |

### P2：可选优化（提升实验覆盖度）

| 文件                            | 改动                                | 理由          |
| ----------------------------- | --------------------------------- | ----------- |
| `strategy_comparison.yaml`    | balanced\_document 加入 adversarial | 覆盖对抗性问题     |
| `smoke_full.yaml`             | 加入 adversarial: 0.10              | 完整冒烟应覆盖所有类型 |
| `baseline_1kpage_no_ocr.yaml` | 删除或标记 deprecated                  | 自身注释说明无实际意义 |

***

## 四、改动模板示例

### 改动前（当前写法）

```yaml
evaluation:
  backends: ["builtin"]
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
      - "chunk_hit_rate"
      - "chunk_mrr"
      - "chunk_ndcg"
      - "dedup_hit_rate"
      - "dedup_mrr"
      - "dedup_ndcg"
      - "false_positive_rate"
      - "recall_3"
      - "recall_5"
      - "recall_10"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

### 改动后（新写法 — 日常实验）

```yaml
evaluation:
  backends: ["builtin"]
  llm_preset: "default"
  metrics_preset: "core"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

### 改动后（新写法 — 双后端对标验证）

```yaml
evaluation:
  backends: ["builtin", "ragas"]
  llm_preset: "default"
  metrics_preset: "full"
  resolution_strategy: "comparison"
```

### 改动后（新写法 — Golden 基准）

```yaml
test_sets:
  - name: "golden_150"
    quality_level: "golden"
    golden_require_reviewed: true

evaluation:
  backends: ["builtin", "ragas"]
  llm_preset: "default"
  metrics_preset: "full"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

***

## 五、实施建议

1. **先改 P0 项**：5 个双后端配置添加 `resolution_strategy`，1 个 Golden 配置添加审核守卫
2. **批量改 P1 项**：用脚本批量将 `metrics` 罗列替换为 `metrics_preset`，根据文件场景选择 core/extended/full
3. **更新模板**：`_minimal.yaml` 和 `_complete.yaml` 应率先展示新写法
4. **更新 README**：`exp_configs/README.md` 中的示例应改用 `metrics_preset`
5. **向后兼容**：保留 `metrics` 字段的支持（`metrics_preset` 与 `metrics` 同时存在时，`metrics_preset` 优先）
