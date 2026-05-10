# INV-019: 测试并行化可行性评估报告

> 评估日期：2026-04-23
> 评估范围：tests/ 目录下全部测试文件，pytest-xdist 并行化兼容性
> 评估目标：评估启用 pytest-xdist 并行执行的可行性，识别阻塞项与风险

---

## 一、当前测试执行时间基线

### 1.1 总体概览

| 指标 | 数值 |
|------|------|
| 单元测试数量 | 1089 |
| 集成测试数量 | 10（已通过 `-m "not integration"` 排除） |
| 单元测试总耗时 | ~706s（11:46）~ 1160s（19:19），波动较大 |
| 测试文件数量 | 29 |

### 1.2 最慢的 20 个测试（按耗时降序）

| 排名 | 阶段 | 测试用例 | 耗时 |
|------|------|----------|------|
| 1 | teardown | `test_meal.py::TestExtendMeal::test_extend_meal_copies_source_artifacts` | 5.43s |
| 2 | teardown | `test_meal.py::TestMergeMeals::test_merge_meals_composition_metadata` | 4.69s |
| 3 | teardown | `test_e2e_experiment.py::TestEndToEndExperiment::test_compare_experiments` | 4.65s |
| 4 | teardown | `test_meal.py::TestMergeMeals::test_merge_meals_with_overlap` | 4.61s |
| 5 | teardown | `test_meal.py::TestMergeMeals::test_merge_two_meals_no_overlap` | 4.59s |
| 6 | teardown | `test_meal.py::TestExtendMeal::test_extend_meal_generates_timestamp_name` | 4.26s |
| 7 | teardown | `test_meal.py::TestMergeMeals::test_merge_meals_auto_timestamp_name` | 4.26s |
| 8 | teardown | `test_meal.py::TestExtendMeal::test_extend_meal_path_object` | 4.19s |
| 9 | teardown | `test_meal.py::TestExtendMeal::test_extend_meal_success` | 4.17s |
| 10 | teardown | `test_meal.py::TestMergeMeals::test_merge_meals_cache_reuse` | 4.17s |
| 11 | teardown | `test_meal.py::TestExtendMeal::test_extend_meal_composition_metadata` | 4.15s |
| 12 | teardown | `test_meal.py::TestExtendMeal::test_extend_meal_absolute_path` | 4.15s |
| 13 | teardown | `test_meal.py::TestExtendMeal::test_extend_meal_skips_existing_pdf` | 4.10s |
| 14 | teardown | `test_e2e_experiment.py::TestReproduceExperiment::test_reproduce_experiment_asset_verification` | 3.84s |
| 15 | teardown | `test_e2e_experiment.py::TestAssetVerificationExtended::test_verify_with_pdf_hash_mismatch` | 3.82s |
| 16 | teardown | `test_meal.py::TestMealManager::test_list_meals` | 3.74s |
| 17 | teardown | `test_e2e_experiment.py::TestEndToEndExperiment::test_verify_experiment_assets` | 3.73s |
| 18 | teardown | `test_e2e_experiment.py::TestAssetVerificationExtended::test_verify_with_missing_pdf` | 3.71s |
| 19 | teardown | `test_meal.py::TestMealManager::test_find_equivalent_meals` | 3.71s |
| 20 | **call** | `test_evaluators.py::TestRagasEvaluatorConfigReading::test_build_run_config_uses_configured_values` | 3.60s |

**关键发现**：最慢的 19/20 项均为 **teardown 阶段**，而非测试执行本身。teardown 慢的原因是 Windows 上 `tempfile.TemporaryDirectory` 清理大量临时文件耗时（每个 `temp_project_dir` 创建 8 个子目录，`test_meal.py` 的 `temp_dirs` fixture 还会创建 5 个假 PDF 文件及大量中间产物）。唯一进入 Top 20 的 call 阶段测试是 `test_evaluators.py` 中的 ragas 模块导入测试，耗时 3.60s。

### 1.3 测试分类耗时估算

| 分类 | 测试文件 | 估算耗时占比 | 说明 |
|------|----------|-------------|------|
| 纯计算/数据类 | `test_metrics.py`, `test_utils.py`, `test_token_tracker.py` | ~5% | 无 IO，极快 |
| 数据模型类 | `test_meal.py`(前半), `test_test_set_manager.py`(前半) | ~10% | 仅数据结构操作 |
| 文件系统依赖 | `test_meal.py`(MealManager/Merge/Extend), `test_e2e_experiment.py`, `test_parser.py`, `test_chunker.py`, `test_indexer.py` | ~60% | 依赖 temp 目录，teardown 慢 |
| Mock 依赖 | `test_evaluators.py`, `test_retriever.py`, `test_embedder.py`, `test_reranker.py` | ~20% | Mock 外部依赖 |
| 重导入类 | `test_evaluators.py`(RagasEvaluator 部分) | ~5% | ragas 模块首次导入慢 |

---

## 二、并行化兼容性分析

### 2.1 Fixture 隔离性分析

#### `temp_project_dir`（conftest.py:70）

```python
@pytest.fixture
def temp_project_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "data" / "raw").mkdir(parents=True)
        # ... 创建 8 个子目录
        yield temp_path
```

- **作用域**：function（默认），每个测试独立创建
- **隔离性**：✅ 完全隔离。每次调用 `tempfile.TemporaryDirectory()` 生成唯一路径
- **并行安全**：✅ 安全。不同 worker 的临时目录路径不同

#### `mock_embedder` / `mock_qdrant_client` / `mock_anthropic_client`（conftest.py:24-66）

- **作用域**：function（默认）
- **隔离性**：✅ 完全隔离。每次创建全新的 `MagicMock()` 实例
- **并行安全**：✅ 安全。无共享状态

#### `test_meal.py` 内部 `temp_dirs` fixture

- **作用域**：function（定义在 `TestMealManager`、`TestMergeMeals`、`TestExtendMeal` 三个类中）
- **隔离性**：✅ 完全隔离。基于 `tmp_path`（pytest 内置，每个测试独立）
- **并行安全**：✅ 安全

#### `test_e2e_experiment.py` 内部 fixtures

- `test_pdf_files(temp_project_dir)` — 依赖 `temp_project_dir`，在其子目录中创建 PDF 文件
- `test_system_config(temp_project_dir)` — 依赖 `temp_project_dir`，构建配置字典
- `test_experiment_config(temp_project_dir)` — 依赖 `temp_project_dir`
- **隔离性**：✅ 完全隔离。所有 fixture 均基于 function-scoped 的 `temp_project_dir`
- **并行安全**：✅ 安全

#### 无 session/module/class 作用域 fixture

经搜索确认，整个 `tests/` 目录中 **不存在** `scope="session"`、`scope="module"` 或 `scope="class"` 的 fixture 定义。这是并行化的有利条件。

### 2.2 文件系统竞争风险

#### `.pytest_tmp` 目录

`pytest.ini` 配置：

```ini
addopts = --basetemp=.pytest_tmp
tmp_path_retention_count = 0
tmp_path_retention_policy = failed
```

- **xdist 行为**：pytest-xdist 会为每个 worker 创建独立子目录 `.pytest_tmp/worker-gwN/`，不存在竞争
- **`pytest_configure` 清理逻辑**（conftest.py:11-21）：在 session 启动时清理 `.pytest_tmp` 目录。xdist 下此逻辑仅在 controller 进程执行一次，不会与 worker 冲突
- **风险等级**：🟢 低

#### `data/` 目录

- 测试代码 **不写入** 真实的 `data/` 目录，所有文件操作均在临时目录中进行
- `test_regression.py` 的集成测试通过 `load_config()` 读取真实 `config.yaml`，但这些测试标记为 `@pytest.mark.integration`，常规运行已排除
- **风险等级**：🟢 低

#### `tests/fixtures/` 目录

- `test_regression.py` 读取 `tests/fixtures/golden_qa.json`，为只读操作
- 并行 worker 同时读取同一文件不会冲突
- **风险等级**：🟢 低

### 2.3 集成测试的 Qdrant/LLM API 共享问题

集成测试（10 个，标记 `@pytest.mark.integration`）存在以下并行化风险：

| 资源 | 风险 | 说明 |
|------|------|------|
| Qdrant 向量数据库 | 🔴 高 | 多 worker 同时操作同一 collection 可能导致数据竞争 |
| LLM API（Anthropic） | 🟡 中 | 并发请求可能触发 rate limit；API 调用非幂等 |
| 真实文件系统 | 🔴 高 | `load_config()` 读取项目 `config.yaml`，`RAGPipeline` 写入 `data/` 目录 |

**结论**：集成测试 **不应纳入并行化范围**，继续使用 `-m "not integration"` 排除。

### 2.4 环境变量污染风险

- 搜索确认测试代码中 **未使用** `monkeypatch` 或直接修改 `os.environ`
- `test_regression.py` 中的 `load_dotenv()` 在模块级别调用，但仅读取环境变量，不修改
- **风险等级**：🟢 低

### 2.5 模块级状态风险

- `test_regression.py` 在模块级别加载 `golden_qa_data = _load_golden_qa()`，但这是只读数据
- 源码中的全局常量（`VALID_RETRIEVAL_METRICS`、`FACTUAL_PROMPT` 等）均为不可变对象
- **风险等级**：🟢 低

---

## 三、pytest-xdist 配置建议

### 3.1 Worker 数量

| 方案 | Worker 数 | 理由 |
|------|-----------|------|
| 保守方案 | 2 | Windows 文件系统 IO 是瓶颈，过多 worker 反而增加竞争 |
| 推荐方案 | `auto`（= CPU 核心数） | 瓶颈在 teardown IO 而非 CPU，但 xdist 可让不同 worker 交替执行，有效隐藏 IO 等待 |
| 激进方案 | CPU 核心数 × 1.5 | 适用于 IO 密集型测试，但 Windows 上可能因文件锁导致问题 |

**推荐**：初始使用 `-n auto`，观察实际加速比后调整。

### 3.2 分发策略

| 策略 | 说明 | 适用性 |
|------|------|--------|
| `--dist=load`（默认） | 按测试完成速度动态分配 | ✅ 推荐。测试耗时差异大，动态负载均衡最优 |
| `--dist=loadfile` | 同一文件的测试分配到同一 worker | ⚠️ 可选。减少同文件 fixture 重复创建，但可能导致负载不均 |
| `--dist=loadgroup` | 按 `xdist_group` 标记分组 | ❌ 不适用。当前无分组标记 |
| `--dist=each` | 每个 worker 执行全部测试 | ❌ 不适用 |

**推荐**：使用默认的 `--dist=load`。原因：
1. 测试文件间耗时差异大（`test_test_set_manager.py` 有 60+ 测试，`test_utils.py` 仅 20+）
2. `loadfile` 会导致 `test_test_set_manager.py` 全部分配到同一 worker，造成长尾
3. 动态分配可最大化 worker 利用率

### 3.3 推荐命令行

```bash
# 单元测试并行化
pixi run pytest tests/ -m "not integration" -n auto --dist=load -q

# 指定 worker 数量
pixi run pytest tests/ -m "not integration" -n 4 --dist=load -q

# 集成测试保持串行
pixi run pytest tests/ -m "integration" -q
```

### 3.4 pytest.ini 建议修改

```ini
[pytest]
markers =
    unit: marks tests as pure unit tests (no external dependencies)
    integration: marks tests that touch external systems (Qdrant, LLM API, real PDF files)
    slow: marks tests as slow (execution time >5s)

addopts = --basetemp=.pytest_tmp -n auto --dist=load -m "not integration"
tmp_path_retention_count = 0
tmp_path_retention_policy = failed
```

> 注意：将 `-n auto` 写入 `addopts` 需要先安装 pytest-xdist 并验证兼容性。建议初期仅在命令行指定，稳定后再写入配置。

---

## 四、风险点清单

| 编号 | 风险 | 等级 | 说明 | 缓解措施 |
|------|------|------|------|----------|
| R1 | Windows 临时目录清理慢 | 🔴 高 | teardown 占总耗时 60%+，并行化无法减少单测试 teardown 时间 | 优化 fixture：减少临时文件创建量；考虑用 `tmp_path` 替代 `tempfile.TemporaryDirectory` |
| R2 | pytest-xdist 未安装 | 🟡 中 | 当前 `pixi.toml` 依赖中无 `pytest-xdist` | 添加 `pytest-xdist` 到 pypi-dependencies |
| R3 | 首次 ragas 导入耗时 | 🟡 中 | `test_evaluators.py` 中 ragas 模块首次导入 3.6s，xdist 下每个 worker 均需导入一次 | 使用 `--dist=load` 动态分配，避免所有 ragas 测试集中到同一 worker |
| R4 | 集成测试误入并行 | 🟡 中 | 若忘记 `-m "not integration"`，集成测试并行执行会导致 Qdrant/API 竞争 | 在 pytest.ini 的 addopts 中固化 `-m "not integration"` |
| R5 | Windows 文件锁 | 🟡 中 | Windows 上文件删除可能因句柄未释放失败，并行时更易触发 | 确保 `tempfile.TemporaryDirectory` 在 yield 后正确清理；考虑 `tmp_path_retention_policy = failed` |
| R6 | 测试输出交错 | 🟢 低 | 多 worker 并行时日志/输出交错，难以调试 | 使用 `-q` 或 `--tb=short`；失败时用 `-n 0` 重跑 |
| R7 | 收集阶段耗时 | 🟢 低 | xdist 需先收集全部测试再分发，收集阶段本身需 ~84s | 可接受；收集只执行一次 |

---

## 五、推荐方案

### 5.1 总体结论

**✅ 建议启用 pytest-xdist 并行化**，但需分阶段实施。

理由：
1. **Fixture 隔离性优秀**：所有 fixture 均为 function-scoped，无共享状态
2. **无环境变量污染**：测试不修改全局环境
3. **文件系统操作隔离**：所有写操作在独立临时目录中
4. **预期加速比**：2-4x（受 teardown IO 瓶颈限制，无法达到理论 N 倍）

### 5.2 分阶段启用策略

#### 阶段一：基础设施准备（阻塞项）

1. **安装 pytest-xdist**
   - 在 `pixi.toml` 的 `[pypi-dependencies]` 中添加：`pytest-xdist = ">=3.6.0, <4"`
   - 运行 `pixi install` 安装依赖

2. **验证基线兼容性**
   ```bash
   # 串行运行，确认全部通过
   pixi run pytest tests/ -m "not integration" -q

   # 单 worker 并行模式，确认 xdist 不引入问题
   pixi run pytest tests/ -m "not integration" -n 1 -q
   ```

#### 阶段二：小规模验证

3. **2 worker 试运行**
   ```bash
   pixi run pytest tests/ -m "not integration" -n 2 --dist=load -q
   ```

4. **对比结果**
   - 确认测试通过率不变（0 失败 → 0 失败）
   - 记录实际耗时，计算加速比
   - 检查是否有 flaky test（偶发失败）

#### 阶段三：全量启用

5. **auto worker 正式运行**
   ```bash
   pixi run pytest tests/ -m "not integration" -n auto --dist=load -q
   ```

6. **固化配置**（验证稳定后）
   - 将 `-n auto --dist=load -m "not integration"` 写入 `pytest.ini` 的 `addopts`

#### 阶段四：性能优化（可选）

7. **优化 teardown 耗时**
   - 将 `test_meal.py` 和 `test_e2e_experiment.py` 中的 `temp_dirs` fixture 改用 `tmp_path`（pytest 内置，清理更高效）
   - 评估是否需要 `temp_project_dir` 创建全部 8 个子目录（部分测试可能不需要）
   - 考虑使用 `tmp_path_retention_count = 0` 避免保留临时目录

8. **ragas 导入优化**
   - 评估是否可在 `conftest.py` 中预导入 ragas，避免每个 worker 重复导入

### 5.3 需要先解决的阻塞项

| 编号 | 阻塞项 | 优先级 | 说明 |
|------|--------|--------|------|
| B1 | 安装 pytest-xdist | P0 | 未安装则无法并行 |
| B2 | 验证单 worker 兼容性 | P0 | 确认 xdist 不破坏现有测试 |
| B3 | 集成测试排除机制 | P1 | 确保 `-m "not integration"` 在并行模式下正确工作 |

### 5.4 预期收益估算

| 场景 | Worker 数 | 预估耗时 | 加速比 | 说明 |
|------|-----------|----------|--------|------|
| 当前串行 | 1 | ~710s | 1.0x | 基线 |
| 保守并行 | 2 | ~400s | 1.8x | teardown IO 限制 |
| 推荐并行 | auto（假设 8 核） | ~200s | 3.5x | IO 等待被其他 worker 计算覆盖 |
| 优化后并行 | auto + teardown 优化 | ~120s | 5.9x | 减少 teardown 耗时后 |

> 注：加速比受 Windows IO 瓶颈影响，实际值可能低于理论值。建议以实测数据为准。

---

## 六、附录

### A. 测试文件分布

| 文件 | 测试数量 | 主要 fixture | 文件系统依赖 |
|------|----------|-------------|-------------|
| test_test_set_manager.py | ~60 | tmp_path | 低 |
| test_meal.py | ~40 | tmp_path (temp_dirs) | 高 |
| test_evaluators.py | ~35 | 无 | 低（Mock） |
| test_e2e_experiment.py | ~15 | temp_project_dir | 高 |
| test_test_generator.py | ~50 | tmp_path | 低 |
| test_experiment.py | ~15 | 无 | 低 |
| test_chunker.py | ~20 | tmp_path | 中 |
| test_parser.py | ~15 | tmp_path | 中 |
| test_metrics.py | ~30 | 无 | 低 |
| test_indexer.py | ~15 | temp_project_dir + mock | 中 |
| 其他 19 个文件 | ~800 | 混合 | 混合 |

### B. 当前依赖状态

- **pytest**：`>=9.0.3, <10`（已安装）
- **pytest-xdist**：❌ 未安装
- **pytest-timeout**：❌ 未安装（建议后续添加，防止并行时单个测试挂起）

### C. 关键代码引用

- [conftest.py](file:///b:/project/w1-easy-rag/tests/conftest.py) — 全局 fixture 定义（temp_project_dir, mock_*)
- [pytest.ini](file:///b:/project/w1-easy-rag/pytest.ini) — pytest 配置（basetemp, markers）
- [pixi.toml](file:///b:/project/w1-easy-rag/pixi.toml#L104) — pytest 依赖声明
- [test_meal.py](file:///b:/project/w1-easy-rag/tests/test_meal.py) — teardown 最慢的测试文件
- [test_e2e_experiment.py](file:///b:/project/w1-easy-rag/tests/test_e2e_experiment.py) — teardown 第二慢的测试文件
