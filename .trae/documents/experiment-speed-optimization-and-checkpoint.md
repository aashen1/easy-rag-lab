# 实验速度优化 + 断点续跑 方案

## 一、现状分析

### 1.1 实验规模估算

6 套对比实验配置 + 1 套递进增强实验，总计 **31 个 variant**：

| 实验配置                           | variant 数 | 每题耗时(估) | 问题数 | 单实验耗时     |
| ------------------------------ | --------- | ------- | --- | --------- |
| chunk\_comparison              | 6         | \~3-5s  | 50  | \~3-5min  |
| overlap\_comparison            | 4         | \~3-5s  | 50  | \~3-4min  |
| chunking\_strategy\_comparison | 4         | \~3-5s  | 65  | \~4-5min  |
| retrieval\_comparison          | 5         | \~3-5s  | 65  | \~4-6min  |
| reranker\_comparison           | 4         | \~5-8s  | 65  | \~6-9min  |
| query\_rewrite\_comparison     | 4         | \~5-10s | 65  | \~6-11min |
| progressive\_enhancement       | 7         | \~3-10s | 65  | \~5-12min |

**纯 RAG 查询耗时估算**：约 30-50 分钟

但加上以下环节，实际总耗时会 **数倍膨胀**：

* **测试集生成**（LLM 生成 50-65 题 × 7 套实验 = 350-455 题，每题需多轮 LLM 调用）

* **向量索引构建**（31 个 variant，不同 chunker 配置需分别建索引，含 embedding 计算）

* **生成指标计算**（faithfulness / answer\_relevancy 需额外 LLM 调用）

* **RAGAS 评测**（如启用，每题额外 LLM 调用，且 RAGAS 本身较慢）

**预估总耗时：3-6 小时**（取决于 LLM API 速度和是否启用 RAGAS）

### 1.2 当前瓶颈定位（按耗时占比排序）

通过代码分析，识别出以下关键瓶颈：

| 瓶颈                    | 严重程度 | 代码位置                                                              | 说明                                                                                                               |
| --------------------- | ---- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **B1: 串行问题查询**        | 🔴 高 | `evaluation.py:80` `for i, question_data in enumerate(questions)` | 50-65 个问题逐个串行调用 `pipeline.query()`，每个涉及 LLM 生成                                                                   |
| **B2: 串行 variant 执行** | 🔴 高 | `core.py:431` `for i, variant in enumerate(exp_config.variants)`  | 31 个 variant 串行执行，每个 variant 需建索引+查+评                                                                            |
| **B3: 重复索引构建**        | 🟡 中 | `core.py:359` 每个 variant 独立建索引                                    | 不同 chunker 配置的 variant 确实需独立索引，但相同 chunker 的 variant（如 retrieval\_comparison 的 5 个 variant）共享同一 chunker 配置却重复建索引 |
| **B4: 生成指标串行计算**      | 🟡 中 | `builtin_evaluator.py:339` 逐样本串行                                  | faithfulness / answer\_relevancy 每题需额外 LLM 调用，串行执行                                                               |
| **B5: 测试集重复生成**       | 🟡 中 | 各实验独立生成测试集                                                        | 7 套实验如果共享同一 meal，测试集可以复用                                                                                         |
| **B6: 无断点续跑**         | 🔴 高 | 整个 `core.py` 无任何 checkpoint 机制                                    | 中断后从头开始，已完成的 variant 结果虽已落盘但不会跳过                                                                                 |

***

## 二、优化方案（按投入产出比排序）

### 优化 1：Variant 级断点续跑（解决 B6）⭐ 最高优先

**原理**：当前代码在 `core.py:450` 已经有 `exp_manager.save_variant_result()` 将每个 variant 结果落盘。只需在启动时检查已有结果，跳过已完成的 variant。

**改动范围**：`eval/runner/core.py` 的 `run_experiment()` 函数

**具体实现**：

1. 在 `run_experiment()` 的 variant 循环前，扫描 `exp_dir/results/` 目录下已有的 `*.json` 文件
2. 对每个 variant，检查其结果文件是否存在且有效（非 error 结果）
3. 如果存在，直接加载并 append 到 `all_variant_results`，跳过执行
4. 新增 CLI 参数 `--force-rerun` 强制重跑所有 variant（覆盖断点续跑）
5. 在 manifest.json 中记录实验进度状态

**预估提速**：不直接提速，但 **消除中断后重跑的浪费**，实际效果等价于提速 2-3x（假设中断概率 50%）

### 优化 2：问题级断点续跑（解决 B6 细粒度）⭐ 高优先

**原理**：在 `collect_rag_samples()` 中，逐题查询结果可以增量落盘。中断后从已完成的题目继续。

**改动范围**：`eval/runner/evaluation.py` 的 `collect_rag_samples()` 函数

**具体实现**：

1. 在 variant 结果目录下新增 `samples_checkpoint.json` 文件
2. 每完成一个问题查询后，将 sample 追加写入 checkpoint 文件
3. 重新启动时，先加载 checkpoint，从 `len(checkpoint_samples)` 处继续
4. 评测阶段（`evaluate_test_set`）基于 checkpoint 中的 samples 计算，无需重新查询
5. variant 完成后删除 checkpoint 文件

**预估提速**：配合优化 1，**彻底消除中断浪费**

### 优化 3：共享 chunker 配置的索引复用（解决 B3）⭐ 高优先

**原理**：同一实验内多个 variant 可能共享相同的 chunker 配置（如 retrieval\_comparison 的 5 个 variant 都用默认 chunker），它们的 chunks 和向量索引完全相同，无需重复构建。

**改动范围**：`eval/runner/core.py` 和 `eval/runner/preparation.py`

**具体实现**：

1. 在 `run_experiment()` 的 Step 2（prepare\_variant\_chunks）中，按 `chunker_hash` 分组
2. 相同 hash 的 variant 只构建一次 chunks
3. 在 Step 4 的 variant 循环中，相同 chunker\_hash 的 variant 共享同一个向量索引
4. 索引构建后缓存到 `indexer_cache: dict[str, VectorIndexer]`，按 chunker\_hash 索引

**预估提速**：

* retrieval\_comparison（5 variant 共享 chunker）：索引构建从 5 次降为 1 次，**省 \~4 次索引构建**

* reranker\_comparison（4 variant 共享 chunker）：**省 \~3 次**

* query\_rewrite\_comparison（4 variant 共享 chunker）：**省 \~3 次**

* 总计省 \~10 次索引构建，**预估省 15-30 分钟**

### 优化 4：测试集跨实验复用（解决 B5）

**原理**：7 套实验如果使用相同的 meal（采样相同），生成的测试集可以复用。当前每套实验独立生成测试集，但问题内容高度重叠。

**改动范围**：实验配置 YAML + `eval/runner/preparation.py`

**具体实现**：

1. 创建一个"共享测试集"实验配置，只生成一次测试集
2. 其他实验配置引用该测试集（通过 `test_sets.name` + `on_missing: "reuse"`）
3. 或更简单：所有实验配置使用相同的 test\_set name，TestSetManager 自动复用

**预估提速**：省 6 次测试集生成，**预估省 20-40 分钟**（测试集生成是最耗时的 LLM 调用之一）

### 优化 5：问题查询并发（解决 B1）⭐ 中优先

**原理**：当前 50-65 个问题串行查询，每个查询涉及 LLM API 调用（\~2-5s）。如果并发查询，可以显著缩短耗时。

**改动范围**：`eval/runner/evaluation.py` 的 `collect_rag_samples()` 函数

**具体实现**：

1. 使用 `concurrent.futures.ThreadPoolExecutor` 并发查询
2. 并发度可配置（默认 3-5，避免 API rate limit）
3. 保留串行模式作为 fallback（`--serial` 参数）
4. 注意：`pipeline.query()` 不是线程安全的，需要为每个线程创建独立 pipeline 或加锁
5. **更安全的方案**：只并发 LLM 生成步骤（检索是本地的，无需并发），但当前架构检索和生成耦合在 `pipeline.query()` 中

**预估提速**：并发度 5 时，查询阶段 **提速 3-4x**，整体 **提速 30-50%**

**风险**：API rate limit、线程安全、结果顺序一致性

### 优化 6：生成指标批量/并发计算（解决 B4）

**原理**：faithfulness 和 answer\_relevancy 每题需额外 LLM 调用，当前串行。

**改动范围**：`eval/evaluators/builtin_evaluator.py`

**具体实现**：

1. 在 `evaluate_batch()` 中，先批量计算所有检索指标（纯计算，无 LLM 调用）
2. 再并发计算生成指标（需 LLM 调用）
3. 使用 `ThreadPoolExecutor` 并发调用 LLM

**预估提速**：生成指标计算 **提速 3-5x**，整体 **提速 10-20%**

### 优化 7：部分评测支持（FEAT-013）

**原理**：对于调试/快速验证，不需要跑全部问题，支持只跑前 N 题。

**改动范围**：实验配置 YAML + `eval/runner/evaluation.py`

**具体实现**：

1. 在实验配置的 `evaluation` 段新增 `max_questions: N` 参数
2. `collect_rag_samples()` 中截取前 N 个问题
3. 报告中标注"部分评测"及实际评测题数

**预估提速**：线性缩减，50 题跑 10 题 = **提速 5x**

***

## 三、断点续跑详细设计

### 3.1 两级 Checkpoint 架构

```
实验级 Checkpoint (Variant 粒度)
├── manifest.json          ← 新增 completed_variants: [...], status: "in_progress" | "completed"
├── results/
│   ├── variant_a.json     ← 已完成的 variant 结果
│   ├── variant_b.json     ← 已完成的 variant 结果
│   └── ...
└── checkpoints/           ← 新增目录
    └── variant_c.json     ← 问题级 checkpoint（variant_c 正在跑）
```

### 3.2 执行流程（含断点续跑）

```
run_experiment():
  1. 加载配置
  2. 检查 exp_dir 是否已存在
     - 不存在 → 正常创建，从头开始
     - 已存在 → 加载 manifest.json
       - status == "completed" → 提示"实验已完成"，退出或 --force-rerun
       - status == "in_progress" → 进入断点续跑模式
  3. 断点续跑模式：
     a. 扫描 results/*.json，收集已完成的 variant_names
     b. 扫描 checkpoints/*.json，收集有部分结果的 variant
     c. 对每个 variant：
        - 已完成 → 加载结果，跳过
        - 有 checkpoint → 加载已有 samples，从断点继续查询
        - 未开始 → 正常执行
  4. 每完成一个 variant：
     a. 保存 variant 结果到 results/
     b. 删除该 variant 的 checkpoint（如有）
     c. 更新 manifest.json 的 completed_variants
  5. 所有 variant 完成后：
     a. 更新 manifest.json status = "completed"
     b. 生成综合报告
```

### 3.3 问题级 Checkpoint 数据结构

```json
{
  "variant_name": "chunk_512_overlap_0",
  "experiment_name": "chunk_comparison",
  "started_at": "2026-04-30T10:00:00",
  "last_updated": "2026-04-30T10:15:30",
  "completed_questions": 35,
  "total_questions": 50,
  "samples": [
    { "question_id": "q1", "question": "...", "answer": "...", ... },
    { "question_id": "q2", ... },
    ...
  ]
}
```

### 3.4 安全性考量

1. **基模变化 warning**：断点续跑时，检查当前 config.yaml 中的 LLM model\_name 是否与 checkpoint 记录的一致，不一致则发出 warning
2. **测试集一致性**：断点续跑时，校验测试集的 hash 是否与 checkpoint 记录一致
3. **强制重跑**：`--force-rerun` 参数忽略所有 checkpoint，从头开始
4. **部分报告**：即使实验未完成，也可基于已完成的 variant 生成部分报告（FEAT-038）

***

## 四、实施优先级与分步计划

### Phase 1：断点续跑（投入产出比最高）

| 步骤  | 内容                     | 涉及文件                       | 预估规模 |
| --- | ---------------------- | -------------------------- | ---- |
| 1.1 | Variant 级断点续跑          | `core.py`                  | 中    |
| 1.2 | 问题级 checkpoint         | `evaluation.py`            | 中    |
| 1.3 | CLI 参数 `--force-rerun` | `run_experiment.py`        | 小    |
| 1.4 | manifest.json 状态管理     | `experiment.py`            | 小    |
| 1.5 | 基模变化 warning           | `core.py`                  | 小    |
| 1.6 | 测试                     | `tests/test_checkpoint.py` | 中    |

### Phase 2：索引复用 + 测试集复用（结构性提速）

| 步骤  | 内容                   | 涉及文件                        | 预估规模 |
| --- | -------------------- | --------------------------- | ---- |
| 2.1 | chunker\_hash 分组索引复用 | `core.py`, `preparation.py` | 中    |
| 2.2 | 共享测试集实验配置            | YAML 配置文件                   | 小    |
| 2.3 | 测试                   | `tests/`                    | 中    |

### Phase 3：并发优化（性能提速，风险较高）

| 步骤  | 内容       | 涉及文件                   | 预估规模 |
| --- | -------- | ---------------------- | ---- |
| 3.1 | 问题查询并发   | `evaluation.py`        | 大    |
| 3.2 | 生成指标并发计算 | `builtin_evaluator.py` | 中    |
| 3.3 | 并发度配置    | `config.yaml`          | 小    |
| 3.4 | 测试       | `tests/`               | 中    |

### Phase 4：部分评测支持（灵活度提升）

| 步骤  | 内容                | 涉及文件                   | 预估规模 |
| --- | ----------------- | ---------------------- | ---- |
| 4.1 | max\_questions 参数 | YAML + `evaluation.py` | 小    |
| 4.2 | 部分评测标注            | `reporting.py`         | 小    |
| 4.3 | 测试                | `tests/`               | 小    |

***

## 五、预估提速效果汇总

| 优化            | 阶段      | 预估提速        | 风险 | 实施难度 |
| ------------- | ------- | ----------- | -- | ---- |
| Variant 级断点续跑 | Phase 1 | 消除中断重跑浪费    | 低  | 中    |
| 问题级断点续跑       | Phase 1 | 消除中断重跑浪费    | 低  | 中    |
| 索引复用          | Phase 2 | 省 15-30min  | 低  | 中    |
| 测试集复用         | Phase 2 | 省 20-40min  | 低  | 小    |
| 问题查询并发        | Phase 3 | 整体提速 30-50% | 中  | 大    |
| 生成指标并发        | Phase 3 | 整体提速 10-20% | 中  | 中    |
| 部分评测          | Phase 4 | 线性缩减        | 低  | 小    |

**综合预估**：

* Phase 1+2 完成后：3-6 小时 → **1.5-3 小时**（省去重复构建 + 断点续跑保障）

* Phase 1+2+3 完成后：**45-90 分钟**

* Phase 1+2+3+4（部分评测 10 题）：**10-20 分钟**（快速验证模式）

