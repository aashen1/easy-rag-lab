# pytest-xdist 并行测试：决策演进记录

> 本文档记录项目测试并行化从串行到并行、从崩溃到稳定的完整决策链。
> **目的**：让后续 AI session 或新贡献者理解"为什么这样配置"，避免反复踩坑或推翻已验证的决策。

***

## 时间线总览

```
串行时代        阶段一：-n auto     阶段二：-n 4        阶段三：-n auto + loadgroup   阶段四：放弃并行
(稳定但慢)  →  (快但崩)  →       (凑合)  →         (仍崩溃)  →              (稳定 ✅)
```

| 阶段  | 时间             | 配置                                                                | 结果           | 问题                       |
| --- | -------------- | ----------------------------------------------------------------- | ------------ | ------------------------ |
| 串行  | \~2026-04-22 前 | 无 `-n` 参数                                                         | 稳定，\~710s    | 太慢                       |
| 阶段一 | 2026-05-02     | `-n auto`                                                         | \~200s，但频繁崩溃 | MemoryError、worker crash |
| 阶段二 | 2026-05-09     | `-n 4 --max-worker-restart=2`                                     | 偶尔稳定         | 4 worker 仍可能 OOM         |
| 阶段三 | 2026-05-10     | `-n auto --dist loadgroup` + `xdist_group("torch")` + CPU fixture | \~55s，**仍崩溃** | RAGAS 未分组，内存耗尽       |
| 阶段四 | 2026-05-11     | 移除所有 xdist 参数，回到串行                                              | 稳定，\~30s     | 无问题，反而更快               |

***

## 阶段零：串行时代

### 背景

项目初期测试全部串行运行，无 pytest-xdist 依赖。

### 性能基线（2026-04-23 评估）

> 开发者注：这里耗时这么高不只是没有并行的原因，主要其实是 TRAE CN 的沙箱不知道为什么会让 pytest 极其缓慢，如果去掉沙箱正常在bash中运行，其实这时候也是就用一两分钟左右。所以……这个并行的加速作用好像至今存疑（

| 指标     | 数值                                                                |
| ------ | ----------------------------------------------------------------- |
| 单元测试数量 | 1089                                                              |
| 串行总耗时  | 706s \~ 1160s（波动大）                                                |
| 最慢环节   | teardown（占 60%+），Windows 上 `tempfile.TemporaryDirectory` 清理大量临时文件 |

### 评估结论

2026-04-23 的可行性评估报告（`docs/reviews/inv-019-test-parallelization.md`）确认：

1. **Fixture 隔离性优秀**：所有 fixture 均 function-scoped，无共享状态
2. **无环境变量污染**
3. **文件系统操作隔离**：所有写操作在独立临时目录
4. **预期加速比**：2-4x

**结论**：✅ 建议启用并行化，初始使用 `-n auto`。

### 遗漏的关键风险

该评估报告**未识别**以下两个致命问题：

1. **torch 传递依赖**：14 个测试文件通过 `from src.embedder import Embedder` / `from src.reranker import Reranker` 传递加载 torch，每个 worker 独立加载 \~2-4GB
2. **CUDA 显存争抢**：`test_embedder.py` 的 fixture mock `torch.cuda.is_available=True` + `device="cuda"`，导致测试中真实 tensor 被 `.to("cuda")` 搬到 GPU 上，多 worker 同时抢 GPU 显存

> **教训**：评估并行化可行性时，不仅要看 fixture 隔离性，还必须分析**模块依赖图的内存重量**——哪些传递依赖会在每个 worker 进程中重复加载。

***

## 阶段一：-n auto（2026-05-02）

### 变更

```
commit 8590879 feat: add pytest-xdist for parallel test execution
```

`pixi.toml` 中三个测试任务全部加上 `-n auto`：

```toml
[tasks.test-unit]
cmd = "pytest tests/ -m 'unit' --tb=short -q --durations=5 -n auto"

[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 -n auto"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10 -n auto"
```

### 结果

- 测试耗时从 \~710s 降至 \~35s（20x 加速）
- **但频繁崩溃**：`MemoryError`、`Windows fatal exception: stack overflow`、`[gwN] node down: Not properly terminated`

### 崩溃原因（事后分析）

`-n auto` 在 8 核机器上创建 8 个 worker，每个 worker：

| 资源                      | 单 worker 占用 | 8 worker 总计 |
| ----------------------- | ----------- | ----------- |
| Python 进程基础             | \~50MB      | \~400MB     |
| torch 模块                | \~2-4GB     | \~16-32GB   |
| CUDA 显存（test\_embedder） | \~500MB-1GB | \~4-8GB     |
| pytest + 依赖             | \~100MB     | \~800MB     |

**总计**：CPU 内存 16-32GB + GPU 显存 4-8GB。大多数开发机无法承受。

### 根本原因的层次

1. **CPU 内存**：torch 被每个 worker 独立加载（Python 进程不共享内存）
2. **GPU 显存**：测试代码真的往 GPU 塞数据（fixture 设置 `device="cuda"`）
3. **Windows 特有**：Windows 进程创建/销毁开销比 Linux 大，内存管理更脆弱

***

## 阶段二：-n 4（2026-05-09）

### 变更

```
commit 39ee550 docs: add pytest-xdist stability investigation report
commit 88be050 fix(test): limit xdist workers to 4 for Windows stability
commit e10d250 docs: implement pytest-xdist worker configuration plan
```

`pixi.toml` 改为固定 4 worker + 容错参数：

```toml
[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 -n 4 --max-worker-restart=2"
```

### 调查报告的核心分析

当时的调查报告（`.trae/documents/pytest-xdist-stability-investigation.md`）将问题归因为：

1. `-n auto` 过度并行化
2. Windows 平台进程管理更重
3. 测试收集阶段竞争

### 结果

- 大部分时候能跑过
- **偶尔仍崩溃**：4 worker × torch ≈ 8-16GB 内存 + GPU 显存争抢，在内存紧张时仍会 OOM

### 为什么"偶尔"？

崩溃是**间歇性**的，取决于：

- 系统当前可用内存（其他程序占用多少）
- xdist worker 调度随机性（哪些 worker 同时加载 torch）
- GPU 是否被其他进程占用

这就是为什么用户自己手动跑时可能不触发，而 AI 跑时经常触发——AI 运行时 IDE 本身也占用大量内存。

> 补注：似乎仍然和沙箱脱不开干系，有时候因为 && 连接命令不能被白名单识别，所以仍然会在沙箱中拉起测试，不确定是不是每次OOM都是这种情况。

### 调查报告的遗漏

该报告**正确识别**了 worker 数量过多的问题，但**未触及根因**：

- 只分析了"worker 太多"这个表象
- 没有追问"为什么 4 个 worker 就占这么多内存？"
- 没有发现 torch 传递依赖链和 CUDA 显存争抢
- 提出的 `--dist loadfile` 方案无法解决问题（loadfile 按文件分组，但 torch 依赖跨多个文件）

***

## 阶段三：-n auto + loadgroup + xdist\_group + CPU fixture（2026-05-10）

### 变更

三处修改，分别解决不同层次的问题：

#### 修改 1：`conftest.py` — xdist\_group 分组

```python
_TORCH_DEP_FILES = frozenset({
    "test_reranker", "test_embedder", "test_pipeline",
    "test_indexer", "test_retriever", "test_hybrid_retriever",
    "test_interactive_qa", "test_run_eval", "test_checkpoint_resume",
    "test_regression", "test_agent", "test_e2e_experiment",
})

def pytest_collection_modifyitems(items):
    for item in items:
        module_name = Path(item.module.__file__).stem
        if module_name in _TORCH_DEP_FILES:
            item.add_marker(pytest.mark.xdist_group("torch"))
        if module_name in ("test_indexer_extensions", "test_index"):
            if "test_core_ops" in str(Path(item.module.__file__)):
                item.add_marker(pytest.mark.xdist_group("torch"))
```

**解决的问题**：14 个传递依赖 torch 的测试文件共享同一个 worker，torch 只加载 1 次。

**原理**：`xdist_group("torch")` + `--dist loadgroup` 让 xdist 把同组测试调度到同一个 worker。其他轻量测试依然并行。

#### 修改 2：`pixi.toml` — -n auto + --dist loadgroup

```toml
[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 -n auto --dist loadgroup --max-worker-restart=2"
```

**解决的问题**：

- `-n auto`：根据 CPU 核心数自适应 worker 数量（而非硬编码 4）
- `--dist loadgroup`：让 `xdist_group` marker 生效（默认的 `--dist load` 会忽略 group）

**关键细节**：`--dist loadgroup` 是必须的！没有它，`xdist_group` marker 会被忽略，测试仍然被随机分配到不同 worker。

#### 修改 3：`test_embedder.py` — CPU fixture

```python
# 修改前
mock_cuda_available.return_value = True
embedder = Embedder(model_name="test-model", device="cuda")

# 修改后
mock_cuda_available.return_value = False
embedder = Embedder(model_name="test-model", device="cpu")
```

**解决的问题**：消除 GPU 显存争抢。测试中不需要真往 GPU 塞数据。

**为什么安全**：CUDA fallback 行为已有专门的 `test_embedder_init_cuda_fallback_to_cpu` 测试覆盖。

### 结果

| 命令                   | 结果                    | 耗时  |
| -------------------- | --------------------- | --- |
| `pixi run test`      | 2351 passed, 0 failed | 55s |
| `pixi run test-unit` | 1105 passed, 0 failed | 40s |

**稳定 + 快**。比阶段二的 `-n 4` 还快（因为 `-n auto` 在核心多的机器上开更多 worker），同时不会崩溃（torch 只占 1 份内存，GPU 不被争抢）。

***

## 决策原则（给后续 AI 的指南）

### 原则 1：并行化的瓶颈是内存，不是 CPU

本项目测试的真正瓶颈不是 CPU 算力，而是**每个 worker 的内存占用**。torch 在每个 Python 进程中独立加载，无法共享。因此：

- ❌ 简单增加 worker 数量 = 增加内存压力 = 更容易崩溃
- ✅ 按依赖重量分组，重依赖共享 worker = 内存可控 + 轻量测试并行

### 原则 2：不要在测试中真的使用 GPU

单元测试的目的是验证逻辑正确性，不是跑真实推理。即使测试代码路径中包含 `.to(device)` 操作：

- 如果 device="cuda"，tensor 会真的搬到 GPU 上
- 多个 worker 同时这样做 = GPU 显存争抢 = OOM
- **正确做法**：测试用 CPU，CUDA fallback 行为单独测试

### 原则 3：`--dist loadgroup` 是必需的

`xdist_group` marker **必须配合** **`--dist loadgroup`** 才能生效。默认的 `--dist load` 会忽略 group marker，把测试随机分配。

### 原则 4：新增传递依赖 torch 的测试文件时

如果新增的测试文件 `from src.embedder import ...` 或 `from src.reranker import ...`（或任何间接导入这两个模块的路径），必须将其模块名加入 `conftest.py` 中的 `_TORCH_DEP_FILES` 集合。

判断方法：在测试文件顶层写 `from src.xxx import Yyy`，然后检查 `src/xxx.py` 的 import 链是否最终到达 `src/embedder.py` 或 `src/reranker.py`。

### 原则 5：不要回到串行

串行 \~710s，并行 \~55s，13x 加速。只要遵循上述原则，并行是稳定可靠的。回到串行是倒退。

> 补注：存疑，需要实验数据支撑。

***

## 为什么之前的 AI 反复踩坑

### 根本原因：片面优化

| AI     | 看到的                    | 忽略的                     | 结果              |
| ------ | ---------------------- | ----------------------- | --------------- |
| 阶段一 AI | "并行能加速 20x"            | torch 内存 × worker 数     | 加了 `-n auto`，崩了 |
| 阶段二 AI | "worker 太多了"           | 为什么 4 个 worker 也占这么多内存？ | 减到 4 个，偶尔还崩     |
| 阶段三 AI | "torch 传递依赖 + CUDA 争抢" | —                       | 根治              |

**模式**：每次只看一层，没往深处追。就像医生看到发烧就给退烧药，不查感染源。

### 如何避免

1. **看到表面症状后，追问"为什么"至少两层**
   - 表面：worker 崩溃 → 为什么？内存不够 → 为什么？torch 被重复加载 → 为什么？传递依赖
   - 表面：CUDA OOM → 为什么？测试往 GPU 塞数据 → 为什么？fixture 设置 device="cuda"
2. **做变更前，先分析完整的影响链**
   - 不只看"改了什么"，还要看"这个改动在所有 worker 进程中的叠加效果"
3. **读历史文档**
   - 项目中已有 `docs/reviews/inv-019-test-parallelization.md`（可行性评估）和 `.trae/documents/pytest-xdist-stability-investigation.md`（稳定性调查）
   - 新 AI 应该先读这些文档，理解前人的分析，再决定是否推翻

***

## 配置速查

### 当前生效配置

**pixi.toml**：

```toml
[tasks.test-unit]
cmd = "pytest tests/ -m 'unit' --tb=short -q --durations=5 -n auto --dist loadgroup --max-worker-restart=2"

[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 -n auto --dist loadgroup --max-worker-restart=2"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10 -n auto --dist loadgroup --max-worker-restart=2"
```

**conftest.py**：`_TORCH_DEP_FILES` + `pytest_collection_modifyitems` 钩子自动标记 `xdist_group("torch")`

**test\_embedder.py**：fixture 使用 `device="cpu"`，不触碰 GPU

### 参数含义

| 参数                       | 含义                   | 为什么这样设              |
| ------------------------ | -------------------- | ------------------- |
| `-n auto`                | worker 数 = CPU 逻辑核心数 | 自适应，核心多就多开          |
| `--dist loadgroup`       | 按 xdist\_group 分组调度  | 让 torch 测试共享 worker |
| `--max-worker-restart=2` | worker 崩溃后最多重启 2 次   | 防止无限重启循环            |
| `xdist_group("torch")`   | 标记 torch 依赖测试        | torch 只加载 1 次       |
| `device="cpu"`           | 测试用 CPU              | 避免 GPU 显存争抢         |

***

## 相关文档索引

| 文档      | 路径                                                        | 内容                   |
| ------- | --------------------------------------------------------- | -------------------- |
| 可行性评估   | `docs/reviews/inv-019-test-parallelization.md`            | 阶段零的评估，fixture 隔离性分析 |
| 稳定性调查   | `.trae/documents/pytest-xdist-stability-investigation.md` | 阶段一崩溃后的调查（归因不够深）     |
| 修复计划    | `.trae/documents/pytest-xdist-fix-plan.md`                | 阶段二的修复计划             |
| 测试分层    | `docs/dev-guides/testing.md`                              | 三层测试体系说明             |
| **本文档** | `docs/dev-guides/pytest-xdist-PROGRESS.md`                | 完整决策演进记录             |

***

## 阶段四：放弃并行化（2026-05-11）

### 背景

阶段三方案（`-n auto + loadgroup + xdist_group`）实施后，仍频繁出现 MemoryError，甚至导致整个电脑其他应用卡崩。问题严重性超出预期，继续并行化的收益不足以抵消其成本。

### 最新问题

2026-05-11 的调查报告（`.trae/documents/memory-error-investigation-260511.md`）发现：

1. **RAGAS 测试未纳入分组**：`test_evaluators.py` 加载 RAGAS（torch + transformers），但未被 `xdist_group("torch")` 覆盖
2. **内存耗尽触发点**：错误发生在 pytest 的错误报告机制（`ast.parse`），说明内存已经耗尽到连 AST 解析都无法完成
3. **非确定性问题**：崩溃点随机，取决于系统当前内存状态

### 决策

**放弃 pytest-xdist 并行化，回到串行测试。**

### 理由

1. **问题严重性**：内存错误不仅影响测试，还卡崩其他应用，这是不可接受的
2. **实际加速存疑**：PROGRESS.md 中提到"沙箱让 pytest 极其缓慢"，并行加速可能被抵消
3. **维护成本高**：需要持续维护分组逻辑，且仍不稳定
4. **开发体验差**：反复崩溃比慢更糟糕

### 验证结果

回到串行后的测试结果：

| 命令 | 结果 | 耗时 | 对比 |
|------|------|------|------|
| `pixi run test-unit` | 1103 passed | 29.99s | 比并行（37.68s）更快！ |

**结论**：在沙箱环境下，串行测试反而比并行更快，且 100% 稳定。

### 变更

**pixi.toml**：

```toml
[tasks.test-unit]
cmd = "pytest tests/ -m 'unit' --tb=short -q --durations=5"

[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10"
```

**conftest.py**：

移除了 `_TORCH_DEP_FILES` 和 `pytest_collection_modifyitems` 钩子，不再需要 `xdist_group` marker。

### 后续建议

如果未来需要重新考虑并行化，需满足以下条件：

1. 确认非沙箱环境串行耗时 > 300s
2. 有足够的内存（>= 32GB）
3. 完成了测试本身的优化（减少重导入）
4. 在 Linux 环境开发（内存管理更健壮）

### 教训

1. **不要盲目追求并行**：在沙箱等特殊环境下，并行可能适得其反
2. **稳定性 > 速度**：反复崩溃比慢更糟糕
3. **环境差异**：沙箱 vs 原生环境性能差异巨大，需实际验证
4. **问题严重性评估**：当问题影响到其他应用时，应立即停止并回退
