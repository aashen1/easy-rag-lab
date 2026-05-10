# Phase 1 止血修复计划

> 基于 `code-quality-audit-report-260509.md` Phase 1 问题，经逐项验证后制定的修复计划

---

## 调研结论总览

| # | 原报告问题 | 验证结果 | 是否需要修复 |
|---|-----------|---------|------------|
| 1 | 假测试 `test_dual_backend_results_have_namespace_prefix` | ✅ **确认存在** — `tests/test_run_experiment.py:1130-1132`，方法体只有 `pass` | 是 |
| 2a | 死代码 `safe_metric_calculation()` 装饰器 | ✅ **确认存在** — `eval/evaluators/error_handler.py:28-49`，全项目无任何调用 | 是 |
| 2b | 死代码 `_compute_config_hash()` | ✅ **确认存在** — `eval/parser_benchmark/runner.py:195-208`，全项目无任何调用 | 是 |
| 2c | 死代码 `pdf_viewer.py` 仅 2 行重导出 | ⚠️ **部分确认** — 虽然只有 2 行，但被 `review.py` 和 `__init__.py` 引用，是有效的包 API 桥接 | 否（保留） |
| 3 | 拼写错误 `pymupdf4llllm` | ✅ **确认存在** — `eval/runner/asset_verifier.py:244`，应为 `pymupdf4llm` | 是 |
| 4 | `ExperimentManager` 5 处 manifest 读写重复 | ✅ **确认存在** — 5 个方法均包含相同的读-改-写模板 | 是 |
| 5 | `token_tracker` 重建逻辑重复 | ✅ **确认存在** — `eval/runner/core.py:829-852` 与 `909-926`，逻辑完全相同，仅数据源变量名不同 | 是 |

---

## 修复步骤

### Step 1：删除假测试

**文件**：`tests/test_run_experiment.py`
**位置**：第 1130-1132 行
**操作**：删除 `test_dual_backend_results_have_namespace_prefix` 方法。检查其所属的 `TestDualBackendEvaluation` 类是否还有其他测试方法，若该类变空则一并删除整个类。

**验证**：运行 `pixi run test` 确认无破坏性影响。

**提交信息**：`fix: remove fake test that only passes without asserting anything`

---

### Step 2：删除死代码 `safe_metric_calculation()`

**文件**：`eval/evaluators/error_handler.py`
**位置**：第 28-49 行
**操作**：删除 `safe_metric_calculation` 函数及其相关导入（`Callable`、`wraps` 如果仅被此函数使用）。保留同文件中的 `execute_metric_safely()`，因为它是实际被使用的替代方案。

**验证**：
1. 全项目搜索 `safe_metric_calculation` 确认无引用
2. 运行 `pixi run test` 确认无破坏

**提交信息**：`chore: remove unused safe_metric_calculation decorator`

---

### Step 3：删除死代码 `_compute_config_hash()`

**文件**：`eval/parser_benchmark/runner.py`
**位置**：第 195-208 行
**操作**：删除 `_compute_config_hash` 静态方法。检查是否需要移除 `hashlib` 导入（如果仅被此方法使用）。

**验证**：
1. 全项目搜索 `_compute_config_hash` 确认无引用
2. 运行 `pixi run test` 确认无破坏

**提交信息**：`chore: remove unused _compute_config_hash static method`

---

### Step 4：修复拼写错误 `pymupdf4llllm` → `pymupdf4llm`

**文件**：`eval/runner/asset_verifier.py`
**位置**：第 244 行
**操作**：将 `"pymupdf4llllm"` 修改为 `"pymupdf4llm"`

**验证**：运行 `pixi run test` 确认无破坏

**提交信息**：`fix: correct typo pymupdf4llllm -> pymupdf4llm in asset_verifier`

---

### Step 5：提取 `ExperimentManager._update_manifest()` 辅助方法

**文件**：`src/experiment.py`
**涉及方法**（5 个）：
1. `update_manifest_status()` — 行 875-905
2. `mark_variant_completed()` — 行 907-953
3. `update_manifest_field()` — 行 955-985
4. `mark_resumed()` — 行 987-1022
5. `invalidate_variant()` — 行 1069-1107

**操作**：

1. 在 `ExperimentManager` 类中新增私有方法：

```python
def _update_manifest(
    self,
    exp_dir: Path,
    updater: Callable[[dict[str, Any]], None],
    *,
    not_found_msg: str = "Manifest not found, skipping update",
    error_msg: str = "Failed to update manifest",
) -> None:
    manifest_path = exp_dir / "manifest.json"
    if not manifest_path.exists():
        logger.warning(not_found_msg)
        return
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        updater(manifest)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"{error_msg}: {str(e)}")
        raise
```

2. 重构 5 个方法，将 manifest 读写模板替换为调用 `_update_manifest()`，每个方法只保留各自的业务修改逻辑作为 `updater` 回调。

3. 确保需要 `raise` 的方法（如 `update_manifest_status`）在 `_update_manifest` 中正确传播异常，不需要 `raise` 的方法（如 `invalidate_variant`）在调用时捕获异常。

**验证**：
1. 运行 `pixi run test` 确认所有实验管理相关测试通过
2. 手动检查 5 个重构后方法的行为与原逻辑一致

**提交信息**：`refactor: extract _update_manifest helper to eliminate 5x duplicated read-modify-write pattern`

---

### Step 6：提取 `token_tracker` 重建逻辑为独立函数

**文件**：`eval/runner/core.py`
**位置**：第 829-852 行 和 第 909-926 行

**操作**：

1. 在 `core.py` 模块级别（或作为 `run_experiment` 所在类的私有方法，视代码结构而定）新增辅助函数：

```python
def _rebuild_and_merge_token_tracker(
    token_usage_data: dict,
    variant_name: str,
    experiment_tracker: TokenTracker,
) -> None:
    variant_tracker = TokenTracker()
    for rec_data in token_usage_data.get("records", []):
        usage = DetailedTokenUsage(
            input_tokens=rec_data["usage"]["input_tokens"],
            output_tokens=rec_data["usage"]["output_tokens"],
            system_prompt_tokens=rec_data["usage"].get("system_prompt_tokens", 0),
            contexts_tokens=rec_data["usage"].get("contexts_tokens", 0),
            query_tokens=rec_data["usage"].get("query_tokens", 0),
        )
        variant_tracker.record(
            category=rec_data["category"],
            model_name=rec_data["model_name"],
            usage=usage,
            variant_name=variant_name,
        )
    experiment_tracker.merge(variant_tracker)
```

2. 将第 829-852 行替换为：
```python
_rebuild_and_merge_token_tracker(existing_result["token_usage"], variant_name, experiment_tracker)
```

3. 将第 909-926 行替换为：
```python
_rebuild_and_merge_token_tracker(variant_result["token_usage"], variant_name, experiment_tracker)
```

**验证**：
1. 运行 `pixi run test` 确认 eval 相关测试通过
2. 确认 `TokenTracker` 和 `DetailedTokenUsage` 的导入路径正确

**提交信息**：`refactor: extract _rebuild_and_merge_token_tracker to eliminate duplicated token tracking logic`

---

### Step 7：最终验证

**操作**：
1. 运行 `pixi run lint` 确保代码风格合规
2. 运行 `pixi run test` 确保全部测试通过
3. 运行 `pixi run ruff-check` 确认无静态检查问题

---

## 关于 `pdf_viewer.py` 的决策

原报告建议删除 `src/testset_review/pdf_viewer.py`（仅 2 行重导出），但经验证：
- 该文件被 `src/testset_cli/review.py` 和 `src/testset_review/__init__.py` 引用
- 作为包的公共 API 桥接层有实际用途
- 删除它需要同步修改引用方的 import 路径，收益不大

**决定**：Phase 1 不处理此文件，留待后续 Phase 考虑是否将引用方直接改为从 `scripts.pdf_viewer` 导入。

---

## 风险与注意事项

1. **`_update_manifest` 异常传播**：原代码中 `update_manifest_status()` 和部分方法在异常时 `raise`，而 `invalidate_variant()` 不 `raise`。提取辅助方法后需确保异常传播行为与原逻辑一致。建议 `_update_manifest` 默认 `raise`，不需要 raise 的调用方自行 try/except。

2. **`_update_manifest` 的 `not_found_msg`**：原代码中 `invalidate_variant()` 在 manifest 不存在时直接 `return`（无 warning 日志），而其他方法会 `logger.warning`。需在重构时保留此差异。

3. **测试覆盖**：Phase 1 的修改主要是删除和提取，不改变外部行为。但 `ExperimentManager` 的 manifest 操作可能缺少单元测试覆盖，重构后建议补充测试。

4. **每步独立提交**：遵循项目 commit 规范，每个逻辑单元完成后立即提交，不批量提交。
