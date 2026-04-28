# Bug 修复计划：实验评估系统 6 项 Bug/缺陷

## 概览

| # | Bug | 优先级 | 修复难度 |
|---|-----|--------|---------|
| 1 | `missing` 类型 `expect_retrieval=False` 语义错误 | P0 | 中 |
| 2 | FPR 计算对 `missing` 类型语义错误（随 Bug 1 一起修） | P0 | 低 |
| 3 | `test_set` 字段始终 "unknown" | P1 | 低 |
| 4 | Chunk 级指标始终 null（改动流程） | P1 | 中 |
| 5 | `retrieval_applicable_questions` 计数可能偏高 | P2 | 低 |
| 6 | "No contexts" 误报警告 | P2 | 低 |

---

## Bug 1 + Bug 2：`missing` 类型 `expect_retrieval=False` 语义错误 + FPR 修复

### 问题

`missing` 类型问题（答案在文档中不存在）被设为 `expect_retrieval=False`，导致：
- 检索到了正确文档但被当作"误报"（FPR=1.0）
- hit_rate/MRR/NDCG 不被计算
- FPR 指标失真（`missing` 和 `irrelevant` 混在一起）

### 修复方案

**test_generator.py**（3 处，主循环/补充循环/增量补充循环）：
- `missing` 类型：`expect_retrieval` 改为 `True`（因为文档应该被检索到）
- 保留 `expect_no_answer = True`（答案不在文档中）

**builtin_evaluator.py**：
- FPR 仅在 `expect_retrieval=False` 时计算（当前逻辑不变）
- 由于 `missing` 现在是 `expect_retrieval=True`，FPR 自然只对 `irrelevant` 计算
- 新增：当 `expect_no_answer=True` 时，跳过 faithfulness 评估（答案本来就不在文档中，faithfulness 无意义）

**run_experiment.py**（聚合逻辑）：
- `missing` 类型现在会贡献 hit_rate/MRR/NDCG（因为 `expect_retrieval=True`）
- `missing` 类型不贡献 faithfulness（因为 `expect_no_answer=True`）

### 涉及文件

1. `src/test_generator.py`：3 处 `expect_retrieval` 赋值（L877, L935, L1088）
2. `eval/evaluators/builtin_evaluator.py`：增加 `expect_no_answer` 条件分支
3. `eval/run_experiment.py`：`_collect_rag_samples()` 传递 `expect_no_answer` 字段
4. `tests/test_evaluators.py`：新增 `missing` 类型测试用例
5. `tests/test_metrics.py`：如需

### 具体改动

#### 1. test_generator.py

3 处 `missing` 分支（L873-877, L931-935, L1084-1088）：
```python
# 改前
elif q_type == "missing":
    qa["source_files"] = [source_path]
    qa["source_chunks"] = []
    qa["expect_no_answer"] = True
    qa["expect_retrieval"] = False

# 改后
elif q_type == "missing":
    qa["source_files"] = [source_path]
    qa["source_chunks"] = []
    qa["expect_no_answer"] = True
    qa["expect_retrieval"] = True
```

#### 2. run_experiment.py `_collect_rag_samples()`

L799 附近，增加 `expect_no_answer` 字段传递：
```python
"expect_no_answer": question_data.get("expect_no_answer", False),
```

#### 3. builtin_evaluator.py `evaluate_single()`

增加 `expect_no_answer` 参数，当 `expect_no_answer=True` 时跳过 faithfulness：
- 方法签名增加 `expect_no_answer: bool = False`
- generation 指标计算处增加条件：当 `expect_no_answer=True` 时，faithfulness 设为 None 并跳过计算

#### 4. 测试

- 新增测试：`missing` 类型 `expect_retrieval=True`，hit_rate/MRR 被计算
- 新增测试：`missing` 类型 faithfulness 不被计算
- 新增测试：`irrelevant` 类型 FPR 仍正常计算
- 确认现有测试不受影响

---

## Bug 3：`test_set` 字段始终 "unknown"

### 问题

`_collect_rag_samples()` 中 `test_set.get("name", "unknown")` 对新格式测试集无效，因为 `name` 在 `metadata` 内部。

### 修复方案

修改 `eval/run_experiment.py` L761：
```python
# 改前
test_set_name = test_set.get("name", "unknown")

# 改后
test_set_name = test_set.get("name") or test_set.get("metadata", {}).get("name", "unknown")
```

### 涉及文件

1. `eval/run_experiment.py`：L761 一行改动

---

## Bug 4：Chunk 级指标始终 null（改动流程）

### 问题

`_locate_answer_chunks()` 通过 `ArtifactCache` 用 meal 的 `chunker_hash` 查找 chunks 目录，但 meal 创建时的 chunker 配置与当前 config.yaml 不同，导致找不到对应 chunks 目录（manifest 中 `chunker: "7fad4dde"`，但 artifacts 下只有 `chunks_4fdf68a4/` 和 `chunks_c40aba6e/`）。

### 根因

实验流程中，meal 在 Step 1 创建时用默认 chunker 配置生成 chunks。但后续 variant 评估时用不同 chunker 配置重新分块，产生了不同 hash 的 chunks 目录。test generation 在 Step 2 执行，此时只有 meal 默认配置的 chunks 可用，但 meal manifest 中记录的 chunker_hash 与实际存在的 chunks 目录不匹配。

### 修复方案：调整流程顺序

将实验流程从：
```
Step 1: prepare_meal (含默认 chunking)
Step 2: prepare_test_sets
Step 3: run_variant_evaluation (含 variant chunking)
```

改为：
```
Step 1: prepare_meal (不含 chunking，只解析 PDF)
Step 2: prepare_variant_chunks (为每个 variant 做 chunking)
Step 3: prepare_test_sets (使用第一个 variant 的 chunks 生成问题)
Step 4: run_variant_evaluation
```

**关键设计决策**：
- test set 是所有 variant 共享的，所以只需要用第一个 variant 的 chunks 来生成
- `_locate_answer_chunks()` 需要能接收外部传入的 chunks_dir，而非仅依赖 meal_config 的 chunker_hash
- `prepare_test_sets()` 需要接收 variant 的 chunker_hash 或 chunks_dir 参数

### 涉及文件

1. `eval/run_experiment.py`：调整 `run_experiment()` 主流程
2. `src/test_generator.py`：`_locate_answer_chunks()` 增加外部 chunks_dir 传入路径
3. `src/test_set_manager.py`：`resolve_test_set()` 增加 chunks_dir 参数传递
4. `tests/test_run_eval.py`：更新流程相关测试

### 具体改动

#### 1. run_experiment.py `run_experiment()` 主流程

```python
# Step 1: 准备 meal（仅解析 PDF，不 chunking 不建索引）
meal_info = prepare_meal(system_config, exp_config, skip_preprocessing)

# Step 2: 为所有 variant 预构建 chunks（确保 chunks 可用）
variant_chunks_dirs = {}
for variant in exp_config.variants:
    merged_config = merge_config(system_config, exp_config, variant)
    chunker_hash, chunks_dir = prepare_variant_chunks(merged_config, meal_info["config"])
    variant_chunks_dirs[variant.get("name")] = (chunker_hash, chunks_dir)

# Step 3: 准备 test sets（使用第一个 variant 的 chunks）
first_chunks_dir = list(variant_chunks_dirs.values())[0][1]
test_sets = prepare_test_sets(
    system_config, exp_config, meal_info, skip_preprocessing,
    chunks_dir=first_chunks_dir,
    token_tracker=test_generation_tracker,
)

# Step 4: 运行 variant evaluations（复用已构建的 chunks）
```

#### 2. 新增 `prepare_variant_chunks()` 函数

从 `prepare_index_for_variant()` 中提取 chunking 逻辑，只做分块不建索引：
```python
def prepare_variant_chunks(merged_config, meal_config):
    """Build chunks for a variant if not already cached. Returns (chunker_hash, chunks_dir)."""
    chunker_config = merged_config.get("chunker", {})
    chunker_hash = compute_chunker_config_hash(chunker_config)
    artifacts_config = merged_config.get("artifacts") or {}
    artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
    cache = ArtifactCache(artifacts_dir)
    parsed_dir = cache.get_parsed_dir(meal_config.data_id, ...)
    chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)
    build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config, ...)
    return chunker_hash, chunks_dir
```

#### 3. test_generator.py `_locate_answer_chunks()` 增加外部 chunks_dir

方法签名增加 `chunks_dir: Path | None = None` 参数。当外部传入 chunks_dir 时，直接使用该路径，不再通过 ArtifactCache 解析。

#### 4. prepare_test_sets() 增加 chunks_dir 参数

将 chunks_dir 传递给 TestSetManager 和 TestSetGenerator，最终传到 `_locate_answer_chunks()`。

---

## Bug 5：`retrieval_applicable_questions` 计数可能偏高

### 问题

`valid_retrieval` 过滤条件是 `"retrieval" in r and r["retrieval"]`（非空字典），但 `retrieval_diversity` 不受 `expect_retrieval` 守卫，导致 `expect_retrieval=False` 的问题可能被误计入。

### 修复方案

修改 `eval/run_experiment.py` `compute_aggregate_metrics()` 中的过滤条件：
```python
# 改前
valid_retrieval = [r for r in results if "retrieval" in r and r["retrieval"]]

# 改后
valid_retrieval = [r for r in results if r.get("retrieval", {}).get("hit_rate") is not None]
```

### 涉及文件

1. `eval/run_experiment.py`：`compute_aggregate_metrics()` 中 1 行改动

---

## Bug 6："No contexts" 误报警告

### 问题

test generation 阶段 LLM 生成问题时不需要 RAG 上下文，但 `generator.generate()` 在没有 contexts 时打印 WARNING，产生 20 条误报警告。

### 修复方案

在 `src/generator.py` 的 `generate()` 方法中增加 `allow_no_contexts: bool = False` 参数。当 `allow_no_contexts=True` 且 contexts 为空时，降级为 DEBUG 日志。

test_generator.py 调用 `generate()` 时传入 `allow_no_contexts=True`。

### 涉及文件

1. `src/generator.py`：`generate()` 方法增加参数
2. `src/test_generator.py`：调用 `generate()` 时传入 `allow_no_contexts=True`

---

## 实施顺序

1. **Bug 1 + Bug 2**（核心语义修复，其他 bug 依赖此修复）
2. **Bug 3**（一行改动，快速修复）
3. **Bug 5**（一行改动，快速修复）
4. **Bug 6**（简单改动）
5. **Bug 4**（流程调整，最复杂，放最后）
6. 每步完成后运行 `pixi run lint` 和相关测试
7. 每步完成后 git commit
