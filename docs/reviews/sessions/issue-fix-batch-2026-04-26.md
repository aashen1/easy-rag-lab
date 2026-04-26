# Issue Batch Fix Report — 2026-04-26

## Overview

本次会话批量修复了 5 个 issue（1 个确认已完成 + 4 个实际修复），均与问题生成策略无关，可独立验证。

| # | ID | Type | Title | Status |
|---|-----|------|-------|--------|
| 1 | OPT-009 | Optimization | chunker 逐文件日志降噪 | ✅ 已修复 |
| 2 | FEAT-042 | Feature | 实验全部失败时跳过 LLM 报告生成 | ✅ 已修复 |
| 3 | RF-014 | Refactor | normalize_source 匹配精度确认 | ✅ 确认已完成 |
| 4 | BUG-026 | Bug | 全量缓存 hash 路径不一致导致缓存无法命中 | ✅ 已修复 |
| 5 | BUG-027 | Bug | Token 统计无法按 variant 区分消耗 | ✅ 已修复 |

---

## 1. OPT-009：chunker 逐文件日志降噪

### 问题描述

`src/chunker.py` 的 `chunk_text` 函数每次调用输出一条 INFO 日志（如 `Created 3 chunks from text with 1220 tokens`），处理大量文件时日志非常嘈杂。`process_parsed_files` 和 `process_parsed_files_page_aware` 中也有逐文件的 `logger.success` 日志。

### 修复方案

- 将 `chunk_text` 中的 `logger.info` 改为 `logger.debug`
- 将 `process_parsed_files` 和 `process_parsed_files_page_aware` 中的逐文件 `logger.success` 改为 `logger.debug`
- 保留 `process_parsed_files` 末尾的汇总 INFO 日志（如 `Chunked 45 files into 312 chunks`）

### 修改文件

- `src/chunker.py`：3 处日志级别调整

### 验证方法

1. 运行 `pixi run pytest tests/ -m "not integration" -q` — 1357 passed
2. 运行 `pixi run lint` — All checks passed
3. 功能验证：chunker 处理文件时，控制台不再逐文件输出 INFO 日志，仅在 DEBUG 级别可见；汇总日志仍在 INFO 级别输出

---

## 2. FEAT-042：实验全部失败时跳过 LLM 报告生成

### 问题描述

`eval/run_experiment.py` 中，即使所有 variant 都失败（`all_variant_results` 中全部是 `error_result`），仍会尝试调用 LLM 生成增强报告，浪费 token 且对纯 error 数据无意义。

### 修复方案

在 LLM 报告生成前，检查 `all_variant_results` 中是否有成功的 variant（`"retrieval_metrics" in v`）。如果全部失败，跳过 LLM 报告生成，仅生成模板报告，并输出 warning 日志。

```python
has_successful = any("retrieval_metrics" in v for v in all_variant_results)
if not has_successful:
    logger.warning("All variants failed — skipping LLM report generation")
else:
    # 正常生成 LLM 报告
```

### 修改文件

- `eval/run_experiment.py`：LLM 报告生成逻辑（约 L2030）

### 验证方法

1. 运行 `pixi run pytest tests/ -m "not integration" -q` — 1357 passed
2. 运行 `pixi run lint` — All checks passed
3. 功能验证：构造一个所有 variant 都失败的实验场景，确认不会生成 `experiment_report_llm.md`，且日志中出现 `skipping LLM report generation` 警告

---

## 3. RF-014：normalize_source 匹配精度确认

### 问题描述

backlog 中记录"当前仅比较文件名 stem，过于宽松，可能误判不同版本的同名文档"。

### 调查结论

经代码审查确认，此问题已在之前的版本中修复：

- `eval/metrics/utils.py` 中的 `normalize_source` 函数支持 `include_parent=True` 参数
- `eval/metrics/retrieval.py`、`eval/metrics/dedup.py`、`eval/metrics/builtin_evaluator.py` 中所有调用均已使用 `include_parent=True`
- `src/test_set_manager.py` 中的 `_normalize_source_path` 做的是完整相对路径的后缀归一化，本身已是精确匹配

### 修改文件

无代码修改。更新 backlog.md 状态为 ✅ 已完成。

### 验证方法

1. 代码审查：`grep -n "include_parent=True" eval/metrics/` 确认所有调用点
2. 确认 `_normalize_source_path` 比较的是完整相对路径而非仅 stem

---

## 4. BUG-026：全量缓存 hash 路径不一致导致缓存无法命中

### 问题描述

全量测试时缓存无法命中，但手动将文件 copy 到正确位置后可正常识别。

### 根因分析

`src/pipeline.py` 的 `build_index` 方法将 `parser_config["output_dir"]`（默认 `data/parsed`）作为 `artifacts_dir` 传给 `parse_all_pdfs_unified`。而 `MealManager` 使用 `config["artifacts"]["dir"]`（默认 `data/artifacts`）作为 `artifacts_dir`。

两套系统在不同根目录下查找和保存 manifest：
- `parse_all_pdfs_unified` 保存到 `data/parsed/<data_id[:16]>/manifest.json`
- `MealManager` 在 `data/artifacts/<data_id[:16]>/manifest.json` 查找

路径完全不同，缓存永远无法命中。手动 copy 到 `data/artifacts` 后自然就能识别。

### 修复方案

将 `pipeline.py` 的 `build_index` 方法从硬编码路径改为通过 `ArtifactCache` 动态计算：

1. 从 `config["artifacts"]["dir"]` 读取 `artifacts_dir`
2. 使用 `ArtifactCache` 计算 `data_id`、`parser_hash`、`chunker_hash`
3. 通过 `cache.get_parsed_dir(data_id, parser_hash)` 和 `cache.get_chunks_dir(data_id, chunker_hash)` 获取正确路径
4. 将 parse/chunk/index 三步的输入输出路径全部改为使用动态计算的路径

### 修改文件

- `src/pipeline.py`：`build_index` 方法全面重构路径计算逻辑
- `tests/test_pipeline.py`：4 个测试更新以适配新的路径计算方式（mock ArtifactCache 和 hash 函数）

### 验证方法

1. 运行 `pixi run pytest tests/test_pipeline.py -v` — 12 passed
2. 运行 `pixi run pytest tests/ -m "not integration" -q` — 1357 passed
3. 运行 `pixi run lint` — All checks passed
4. 功能验证：使用 `RAGPipeline.build_index()` 构建索引后，`MealManager` 的 `is_full_parsed_valid()` 应返回 True（之前返回 False）
5. 路径一致性验证：`parse_all_pdfs_unified` 的输出目录与 `ArtifactCache.get_parsed_dir()` 返回的目录应为同一路径

---

## 5. BUG-027：Token 统计无法按 variant 区分消耗

### 问题描述

`TokenTracker.get_summary_by_category()` 只按 `category`（如 `rag_qa`、`test_generation`）聚合，不按 `variant_name` 维度聚合。多 variant 实验中无法看到每个 variant 的 token 消耗明细。

### 修复方案

1. 在 `TokenTracker` 中新增 `get_summary_by_variant()` 方法，按 `metadata["variant_name"]` 分组聚合 token 消耗，返回 `dict[str, dict[str, TokenUsage]]`（variant→category→usage）
2. 在 `run_experiment.py` 的 variant 循环中，反序列化 `variant_result["token_usage"]` 时为每条记录添加 `variant_name=variant_name` metadata
3. 无 `variant_name` 的记录归入 `"__none__"` 组

### 修改文件

- `src/token_tracker.py`：新增 `get_summary_by_variant()` 方法
- `eval/run_experiment.py`：variant_tracker.record() 调用添加 `variant_name=variant_name`
- `tests/test_token_tracker.py`：4 个新测试覆盖空 tracker、单 variant、多 variant、无 variant_name 场景

### 验证方法

1. 运行 `pixi run pytest tests/test_token_tracker.py -v` — 36 passed（含 4 个新增测试）
2. 运行 `pixi run pytest tests/ -m "not integration" -q` — 1357 passed
3. 运行 `pixi run lint` — All checks passed
4. 功能验证：运行多 variant 实验后，`experiment_tracker.get_summary_by_variant()` 应返回按 variant 分组的 token 消耗明细

---

## Overall Verification

### Test Results

```
1357 passed, 10 deselected in 27.36s
```

All non-integration tests pass. No regressions introduced.

### Lint Results

```
ruff check --fix: All checks passed!
ruff format: 82 files left unchanged
```

### Commits

| Commit | Message |
|--------|---------|
| `76a99c5` | fix: use ArtifactCache for pipeline paths to fix full-dataset cache miss (BUG-026) |
| `a4d3a0f` | feat: add get_summary_by_variant to TokenTracker for multi-variant token tracking (BUG-027) |
| (earlier) | fix: reduce chunker per-file log noise to debug level (OPT-009) |
| (earlier) | feat: skip LLM report when all variants failed (FEAT-042) |
| (earlier) | chore: mark RF-014 as completed |

### Backlog Stats After Fix

| 类型 | 待处理 | 已完成 | 完成率 |
|------|--------|--------|--------|
| Bug | 7 | 18 | 72% |
| Feature | 27 | 20 | 43% |
| Refactor | 8 | 14 | 64% |
| Optimization | 7 | 2 | 22% |
| Investigation | 3 | 17 | 85% |
| Test | 0 | 8 | 100% |
