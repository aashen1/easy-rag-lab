# 测试分层优化计划

## 现状分析

| 指标 | 数值 |
|---|---|
| 测试文件 | 37 个 |
| 测试函数 | ~1,735 个 |
| 代码行数 | ~29,747 行 |
| `pixi run test` 耗时 | ~60s |
| post-merge hook | 每次合并后跑 `pixi run test` |

### 核心问题

1. **Marker 形同虚设**：`-m "not integration"` 只排除了 1 个测试，实际跑了 ~1,734 个
2. **80% 测试无标记**：~1,383 个测试没有任何 marker，无法按层过滤
3. **配置冲突**：`pytest.ini` 和 `pyproject.toml` 都定义了 pytest markers，内容不一致
4. **ragas 重导入**：`test_evaluators.py` 和 `test_speed_optimization.py` 中 ragas 相关测试会拉起 torch/transformers 链，拖慢整体
5. **无并行执行**：未使用 `pytest-xdist`，1,735 个测试串行跑

---

## 优化方案：三层测试 + 并行加速

### 第一层：`test-unit`（快速反馈，目标 <15s）

只跑标记为 `unit` 的纯单元测试（~352 个），所有外部依赖均 mock。

```bash
pytest tests/ -m "unit" --tb=short -q
```

**适用场景**：开发中频繁运行，commit 前快速验证。

### 第二层：`test`（标准测试，目标 ~30s）

跑除 `integration` 和 `slow` 以外的所有测试（~1,600+ 个）。

```bash
pytest tests/ -m "not integration and not slow" --tb=short -q
```

**适用场景**：post-merge hook、功能完成后验证。

### 第三层：`test-all`（完整测试，~60s）

跑全部测试，包括 slow 和 integration。

```bash
pytest tests/ --tb=short -q
```

**适用场景**：CI、发版前验证。

---

## 实施步骤

### Step 1：统一 pytest 配置

- 将 `pytest.ini` 的内容合并到 `pyproject.toml` 的 `[tool.pytest.ini_options]`
- 补全所有 marker 定义（`unit`、`integration`、`slow`）
- 将 `addopts`、`tmp_path_retention_*` 迁移到 pyproject.toml
- 删除 `pytest.ini`（移入 `.trashbin/`）

**目标 pyproject.toml 配置**：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: marks tests as pure unit tests (no external dependencies)",
    "integration: marks tests that touch external systems (Qdrant, LLM API, real PDF files)",
    "slow: marks tests as slow (heavy imports like torch/ragas, or execution time >5s)",
]
addopts = "--basetemp=.pytest_tmp"
tmp_path_retention_count = 0
tmp_path_retention_policy = "failed"
```

### Step 2：为 ragas 相关测试添加 `slow` marker

以下测试涉及 ragas/torch 重导入，标记为 `slow`：

- `tests/test_evaluators.py`：`TestRagasEvaluator*` 系列（~6 个 class，约 40+ 个测试）
- `tests/test_speed_optimization.py`：`TestRagasParallelConfig`（3 个测试）

具体操作：
- 在 class 级别添加 `@pytest.mark.slow`
- 将 `try/except ImportError` 替换为 `pytest.importorskip("ragas")`（更惯用）

### Step 3：创建分层 pixi 任务

修改 `pixi.toml`，新增 `test-unit` 任务，调整现有 `test` 任务：

```toml
[tasks.test-unit]
cmd = "pytest tests/ -m \"unit\" --tb=short -q --durations=5"

[tasks.test]
cmd = "pytest tests/ -m \"not integration and not slow\" --tb=short -q --durations=10"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10"
```

### Step 4：更新 post-merge hook

`.pre-commit-config.yaml` 中的 `post-merge-test` 保持使用 `pixi run test`（已自动排除 slow 和 integration）。

### Step 5（可选）：添加 pytest-xdist 并行加速

- 在 `pixi.toml` 的 pypi-dependencies 中添加 `pytest-xdist`
- 在 `addopts` 中加入 `-n auto`（自动按 CPU 核心数并行）
- 预期可将第二层测试时间从 ~30s 降至 ~10-15s

**注意**：此步需要验证并行安全性（测试间无共享状态冲突），建议先跑一次 `pytest -n auto` 观察是否有失败。

---

## 预期效果

| 层级 | 命令 | 测试数 | 预期耗时 | 适用场景 |
|---|---|---|---|---|
| 快速 | `pixi run test-unit` | ~352 | <15s | 开发中频繁运行 |
| 标准 | `pixi run test` | ~1,600 | ~30s | post-merge、功能验证 |
| 完整 | `pixi run test-all` | ~1,735 | ~60s | CI、发版前 |

**日常开发工作流**：
1. 写代码 → `pixi run test-unit`（秒级反馈）
2. 功能完成 → `pixi run test`（分钟内验证）
3. 合并后 → post-merge hook 自动跑 `pixi run test`
4. 发版前 → `pixi run test-all`

---

## 不做的事

- **不给全部 1,383 个无标记测试逐个加 `unit` marker**：工作量巨大且收益低。这些测试虽然没标记，但大多数是 mock 的纯单元测试，通过 `-m "not slow and not integration"` 即可自然包含它们
- **不拆分测试文件**：当前文件组织合理，无需重构
