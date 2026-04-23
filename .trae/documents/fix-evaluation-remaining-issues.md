# 修复评测系统剩余问题

## 问题诊断

修复 `source_chunks → expected_chunks` 管线映射后，重跑实验发现以下问题：

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| 1 | `source_chunks` 全部为空，chunk 级指标仍为 null | 致命 | `_locate_answer_chunks()` 直接读 `config["chunker"]["output_dir"]`（`data/chunks/`），但 chunks 实际存放在 ArtifactCache（`data/artifacts/{data_id}/chunks_{hash}/`），目录不存在所以返回空 |
| 2 | dedup 指标全部为 null | 高 | 实验配置 `metrics.retrieval` 只列了 `hit_rate, mrr, ndcg`，没包含 `dedup_*` |
| 3 | FPR 为 null，irrelevant 问题计数为 0 | 高 | 同上，配置未包含 `false_positive_rate`；且 FPR 计算条件 `not expected_sources` 对 irrelevant 类型正确但对 missing 类型可能不正确 |
| 4 | missing 类型问题仍被计入检索指标 | 中 | `builtin_evaluator.py` 的文档级检索指标只看 `expected_sources` 是否非空，不看 `expect_retrieval` |
| 5 | `adjacent_tolerance` 默认为 0 | 低 | `_locate_answer_chunks()` 的 `adjacent_tolerance` 参数默认为 0（不扩展相邻 chunk），docstring 说默认 1 但实际是 0 |

## 修复计划

### Step 1: 修复 `_locate_answer_chunks()` 使用 ArtifactCache 解析 chunks 目录

**文件**: `src/test_generator.py`

**改动**:
- 修改 `_locate_answer_chunks()` 方法签名，增加 `meal_config` 参数
- 在方法内部使用 `self._resolve_chunks_dir(meal_config)` 替代 `self.config.get("chunker", {}).get("output_dir", chunks_dir)`
- 修改所有调用点（3处：`generate_document_based_questions()` 主循环、补充循环、`supplement_document_based_questions()`），传入 `meal_config`
- 顺带修复 `adjacent_tolerance` 默认值从 0 改为 1（与 docstring 一致）

### Step 2: 修复 `expect_retrieval` 对文档级检索指标的控制

**文件**: `eval/evaluators/builtin_evaluator.py`

**改动**:
- 在文档级检索指标（hit_rate/mrr/ndcg）计算前，增加 `expect_retrieval` 检查
- 当 `expect_retrieval=False` 时，不计算文档级检索指标
- 这样 missing/irrelevant 类型问题不会被错误计入 hit_rate 等指标

### Step 3: 修复 FPR 计算条件

**文件**: `eval/evaluators/builtin_evaluator.py`

**改动**:
- 当前条件 `not expect_retrieval and not expected_sources` 过严
- 改为 `not expect_retrieval`（只要 `expect_retrieval=False` 就计算 FPR）
- irrelevant 类型 `expected_sources=[]`，missing 类型 `expected_sources=[source_path]`，两者都应计算 FPR

### Step 4: 更新实验配置模板，补全 metrics 列表

**文件**: `exp_configs/templates/_complete.yaml`

**改动**:
- `metrics.retrieval` 补充 `chunk_hit_rate, chunk_mrr, chunk_ndcg, dedup_hit_rate, dedup_mrr, dedup_ndcg, false_positive_rate`
- 这样使用完整模板的实验默认会计算所有指标

### Step 5: 更新测试

**文件**: `tests/test_test_generator.py`, `tests/test_builtin_evaluator.py`

**改动**:
- 为 `_locate_answer_chunks()` 使用 ArtifactCache 的修复添加测试
- 为 `expect_retrieval` 控制检索指标的修复添加测试
- 为 FPR 计算条件修复添加测试

### Step 6: 运行 lint 和测试验证

- `pixi run lint`
- `pixi run pytest tests/ -m "not integration" -v`

## 不在本次修复范围内

- **BUG-021**（expected_sources 标注错误）：需要重新设计问题生成策略，是架构级变更，不在本次范围
- **q019 类型标注错误**：LLM 生成质量问题，属于问题生成策略优化范畴
- **`_locate_answer_chunks()` 启发式匹配精度**：当前关键词+子串重叠方案可工作，精度优化后续迭代
