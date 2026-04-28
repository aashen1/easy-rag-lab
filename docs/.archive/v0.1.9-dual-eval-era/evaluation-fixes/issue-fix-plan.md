# Issue 修复计划

## 背景

用户正在并行进行问题生成策略重构，本计划避开该领域，挑选独立、明确、可验证的 issue 进行修复。

## 排除范围

以下 issue 与问题生成策略强相关，**不做**：
- BUG-021（expected_sources 标注错误 — 需重新设计问题生成策略）
- BUG-022（_locate_answer_chunks 定位精度不足 — 与问题生成策略耦合）
- BUG-024/025（source_chunks 缺失 — 依赖问题生成策略重构后的 chunk 级信息）
- FEAT-031（golden_qa.json 重做 — 使用 document-based 策略重做，与问题生成策略强耦合）
- FEAT-030（实验报告 sources 字段细化 — 依赖问题生成策略产出）
- RF-012（旧格式 test_sets 清理 — 依赖 chunk-aware 策略升级）
- RF-019（answer_relevancy 评分稳定性 — 涉及伪问题生成）

## 选中修复的 Issue（5 个）

### 1. FEAT-042：实验成功后才生成 LLM 报告（小）

**问题**：当前即使所有 variant 都失败，仍会尝试生成 LLM 报告。LLM 报告消耗 token 但对纯 error 数据无意义。

**修复方案**：
- 在 `run_experiment.py` 报告生成前，检查 `all_variant_results` 中是否有成功的 variant（`"retrieval_metrics" in v`）
- 如果全部失败，跳过 LLM 报告生成，仅生成模板报告
- 添加日志说明跳过原因

**文件**：`eval/run_experiment.py`（约 L2030-2048）

### 2. BUG-027：Token 统计功能无法按 variant 区分消耗（中）

**问题**：`TokenTracker.get_summary_by_category()` 只按 category 聚合，不按 variant 维度聚合。多 variant 实验中无法看到每个 variant 的 token 消耗。

**修复方案**：
- 在 `run_experiment.py` 的 variant 循环中，为每个 variant_tracker 的记录添加 `variant_name` metadata
- 在 `TokenTracker` 中新增 `get_summary_by_variant()` 方法，按 `metadata["variant_name"]` 分组聚合
- 在实验报告的 token summary 部分展示按 variant 的消耗明细
- 添加对应的 pytest 测试

**文件**：`src/token_tracker.py`、`eval/run_experiment.py`、`eval/experiment_reporter.py`、`tests/test_token_tracker.py`

### 3. OPT-009：chunker 日志降噪（小）

**问题**：`chunker.py` 的 `chunk_text` 函数每次调用输出一条 INFO 日志（如 "Created 3 chunks from text with 1220 tokens"），处理大量文件时日志非常嘈杂。

**修复方案**：
- 将 `chunk_text` 中的 `logger.info` 改为 `logger.debug`
- 在 `process_parsed_files` 函数末尾添加一条汇总 INFO 日志（如 "Chunked 45 files into 312 chunks (avg 6.9 chunks/file)"）
- 保持关键信息不丢失，但减少噪音

**文件**：`src/chunker.py`（L245 附近 + process_parsed_files 末尾）

### 4. BUG-026：全量缓存 hash 计算问题导致缓存无法命中（中）

**问题**：全量测试时缓存无法命中，但手动 copy 文件到正确位置后可识别。

**根因**：`pipeline.py` 的 `build_index` 方法将 `parser_config["output_dir"]`（默认 `data/parsed`）作为 `artifacts_dir` 传给 `parse_all_pdfs_unified`，而 `MealManager` 使用 `data/artifacts` 作为 `artifacts_dir`。两套系统在不同根目录下查找和保存 manifest，导致全量缓存永远无法命中。

**修复方案**：
- 修改 `pipeline.py` 的 `build_index` 方法，从系统配置中读取正确的 `artifacts_dir`（`artifacts.dir`），而非使用 `parser_config["output_dir"]`
- 确保 `parse_all_pdfs_unified` 的 `artifacts_dir` 参数与 `MealManager` 的 `ArtifactCache` 使用同一个根目录
- 添加测试验证全量缓存路径一致性

**文件**：`src/pipeline.py`、`src/meal.py`（可能需要微调）、`tests/test_pipeline.py`

### 5. RF-014：normalize_source 匹配精度提升（小）

**问题**：当前 source 匹配仅比较文件名 stem（如 `annual_report`），过于宽松，可能误判不同版本的同名文档。

**修复方案**：
- 增强 `_normalize_source_path` 函数，在保留 `.pdf` 后缀归一化的基础上，比较时加入父目录路径
- 在 pipeline.py 的 source 匹配逻辑中，使用更精确的路径比较（相对路径而非仅 stem）
- 添加测试覆盖边界情况（同名不同目录、同名不同后缀等）

**文件**：`src/test_set_manager.py`（L19-34）、`src/pipeline.py`（L522 附近）、`tests/test_test_set_manager.py`

## 执行顺序

1. **OPT-009**（chunker 日志降噪）— 最简单，5 分钟搞定，热身
2. **FEAT-042**（实验成功才生成 LLM 报告）— 小改动，逻辑清晰
3. **RF-014**（normalize_source 精度提升）— 小改动，有明确测试方向
4. **BUG-026**（全量缓存 hash 路径不一致）— 中等，需要理解路径解析链路
5. **BUG-027**（Token 统计按 variant 区分）— 中等，需要新增方法和修改多处调用

每个 issue 完成后立即提交，遵循 atomic commit 规范。
