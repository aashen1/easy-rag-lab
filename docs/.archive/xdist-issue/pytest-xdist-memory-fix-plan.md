# pytest-xdist 内存问题根治计划

> Date: 2026-05-11
> Context: 阶段三方案仍出现 MemoryError，需重新评估并行策略

---

## 一、问题诊断

### 1.1 现象总结

| 阶段 | 配置 | 耗时 | 结果 | 问题 |
|------|------|------|------|------|
| 串行 | 无 `-n` | ~710s | 稳定 | 太慢 |
| 阶段一 | `-n auto` | ~35s | 频繁崩溃 | MemoryError、stack overflow |
| 阶段二 | `-n 4` | - | 偶尔稳定 | 仍可能 OOM |
| 阶段三 | `-n auto + loadgroup` | ~55s | **仍崩溃** | 最新调查发现 RAGAS 问题 |

### 1.2 根本原因

**内存墙问题**：

```
每个 worker 进程内存占用：
├─ Python 基础进程        ~50MB
├─ torch 模块            ~2-4GB
├─ transformers/RAGAS    ~1-2GB
├─ pytest + 依赖         ~100MB
└─ 总计                  ~3-6GB per worker

-n auto 在 8 核机器上：
8 workers × 3-6GB = 24-48GB 总内存需求
```

**阶段三方案的遗漏**：

1. 只对 torch 测试做了分组，RAGAS 测试可能未被纳入
2. `-n auto` 仍会根据 CPU 核心数开大量 worker
3. Windows 平台内存管理更脆弱

### 1.3 最新 MemoryError 分析

```
INTERNALERROR> MemoryError
INTERNALERROR>   File "_pytest/_code/source.py", line 191, in getstatementrange_ast
INTERNALERROR>     astnode = ast.parse(content, "source", "exec")
```

**触发链**：
1. 测试失败 → pytest 生成错误报告
2. `ast.parse()` 解析源文件 → 内存不足
3. 整个 worker 进程崩溃

**说明**：内存已经耗尽，连 AST 解析都无法完成。

---

## 二、解决方案对比

### 方案 A：完全放弃 xdist，回到串行

**配置**：
```toml
[tasks.test-unit]
cmd = "pytest tests/ -m 'unit' --tb=short -q --durations=5"

[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10"
```

**优点**：
- ✅ 100% 稳定，无内存问题
- ✅ 无需维护复杂的分组逻辑
- ✅ 调试简单，错误信息清晰

**缺点**：
- ❌ 耗时从 ~55s 回到 ~710s（13x 变慢）
- ❌ 开发反馈周期变长

**适用场景**：
- CI/CD 环境（稳定性优先）
- 内存受限的开发机器
- 不介意等待的开发者

---

### 方案 B：保守并行（-n 2 或 -n 3）

**配置**：
```toml
[tasks.test-unit]
cmd = "pytest tests/ -m 'unit' --tb=short -q --durations=5 -n 2 --dist loadgroup --max-worker-restart=0"

[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 -n 2 --dist loadgroup --max-worker-restart=0"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10 -n 2 --dist loadgroup --max-worker-restart=0"
```

**关键改动**：
- 固定 2 个 worker（而非 `-n auto`）
- `--max-worker-restart=0`（崩溃即失败，不重试）
- 保留 `--dist loadgroup` 和 `xdist_group("torch")`

**优点**：
- ✅ 仍有一定加速（预计 ~200-300s）
- ✅ 内存压力大幅降低（2 workers × 3-6GB = 6-12GB）
- ✅ 保留并行测试能力

**缺点**：
- ⚠️ 仍可能偶发 OOM（取决于系统内存）
- ⚠️ 需要维护分组逻辑

**适用场景**：
- 内存 >= 16GB 的开发机器
- 希望在稳定性和速度间平衡

---

### 方案 C：分层策略（串行 + 并行）

**配置**：
```toml
# 快速单元测试：串行（足够快）
[tasks.test-unit]
cmd = "pytest tests/ -m 'unit' --tb=short -q --durations=5"

# 常规测试：保守并行
[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 -n 2 --dist loadgroup"

# 全量测试：串行（CI 用）
[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10"
```

**优点**：
- ✅ 单元测试串行仍够快（~10s）
- ✅ 常规测试有加速
- ✅ 全量测试最稳定
- ✅ 灵活适配不同场景

**缺点**：
- ⚠️ 配置复杂度增加
- ⚠️ 需要维护分组逻辑

---

### 方案 D：隔离重测试（推荐）

**核心思路**：将 torch/RAGAS 等重导入测试完全隔离，其余测试并行。

**步骤**：

1. **扩展 `conftest.py` 分组**：

```python
# 重导入测试文件列表
_TORCH_DEP_FILES = frozenset({
    "test_reranker", "test_embedder", "test_pipeline",
    "test_indexer", "test_retriever", "test_hybrid_retriever",
    "test_interactive_qa", "test_run_eval", "test_checkpoint_resume",
    "test_regression", "test_agent", "test_e2e_experiment",
})

_RAGAS_DEP_FILES = frozenset({
    "test_evaluators",  # RAGAS 相关测试
})

def pytest_collection_modifyitems(items):
    for item in items:
        module_name = Path(item.module.__file__).stem
        if module_name in _TORCH_DEP_FILES:
            item.add_marker(pytest.mark.xdist_group("torch"))
        if module_name in _RAGAS_DEP_FILES:
            item.add_marker(pytest.mark.xdist_group("ragas"))
```

2. **配置保守并行**：

```toml
[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 -n 3 --dist loadgroup --max-worker-restart=0"
```

**优点**：
- ✅ torch 和 RAGAS 各占 1 个 worker（内存可控）
- ✅ 其余轻量测试可并行
- ✅ 保留大部分加速效果

**缺点**：
- ⚠️ 需要维护分组列表
- ⚠️ 新增测试时需判断是否加入分组

---

### 方案 E：pytest-forked 替代

**原理**：`pytest-forked` 为每个测试 fork 一个进程，测试完成后立即释放内存。

**配置**：
```toml
[tasks.test]
cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q --durations=10 --forked"
```

**优点**：
- ✅ 内存隔离更好（每个测试独立进程）
- ✅ 无需分组逻辑

**缺点**：
- ❌ 无并行加速（串行执行）
- ❌ Windows 上 fork 支持可能有问题

**适用场景**：
- Linux 环境
- 需要内存隔离但不需要并行

---

## 三、推荐方案

### 3.1 短期方案（立即实施）

**推荐：方案 A（回到串行）**

**理由**：
1. **稳定性优先**：反复崩溃严重影响开发体验，甚至卡崩其他应用
2. **实际加速存疑**：PROGRESS.md 中提到"沙箱让 pytest 极其缓慢"，并行加速可能被抵消
3. **简单可靠**：无需维护复杂配置，100% 稳定

**实施步骤**：
1. 移除所有 `-n` 参数
2. 移除 `conftest.py` 中的 `xdist_group` 逻辑
3. 更新文档，记录放弃原因

### 3.2 中期方案（可选优化）

如果串行确实太慢，可尝试**方案 D（隔离重测试 + 保守并行）**：

1. 扩展 `conftest.py` 分组，加入 RAGAS 测试
2. 固定 `-n 3`（torch 1 + ragas 1 + 轻量测试 1）
3. 持续监控稳定性

### 3.3 长期方案

1. **评估真实加速效果**：在非沙箱环境测试串行耗时
2. **优化测试本身**：减少重导入，使用 mock 替代真实加载
3. **考虑 Docker 隔离**：在容器中运行测试，避免影响宿主机

---

## 四、实施计划

### Phase 1：回到串行（立即）

**目标**：恢复 100% 稳定性

**步骤**：
1. 修改 `pixi.toml`，移除所有 `-n` 参数
2. 清理 `conftest.py` 中的 `xdist_group` 相关代码
3. 运行 `pixi run test-all` 验证稳定性
4. 更新 `pytest-xdist-PROGRESS.md`，记录放弃决策

**预期结果**：
- 测试耗时 ~710s
- 100% 稳定，无内存错误

### Phase 2：评估真实性能（可选）

**目标**：确认是否真的需要并行

**步骤**：
1. 在非沙箱环境（原生 Git Bash）运行串行测试
2. 对比沙箱 vs 非沙箱耗时
3. 如果非沙箱环境串行只需 ~60-120s，则并行意义不大

### Phase 3：优化测试本身（长期）

**目标**：从根本上减少内存占用

**步骤**：
1. 识别所有重导入测试
2. 使用 mock 替代真实加载 torch/RAGAS
3. 分离单元测试和集成测试

---

## 五、决策依据

### 为什么推荐回到串行？

1. **问题严重性**：内存错误不仅影响测试，还卡崩其他应用，这是不可接受的
2. **加速存疑**：PROGRESS.md 明确提到"沙箱让 pytest 极其缓慢"，并行加速可能被抵消
3. **维护成本**：阶段三方案需要持续维护分组逻辑，且仍不稳定
4. **开发体验**：反复崩溃比慢更糟糕

### 什么情况下重新考虑并行？

1. 确认非沙箱环境串行耗时 > 300s
2. 有足够的内存（>= 32GB）
3. 完成了测试本身的优化（减少重导入）
4. 在 Linux 环境开发（内存管理更健壮）

---

## 六、风险评估

### 回到串行的风险

- ⚠️ 开发反馈周期变长
- ⚠️ CI/CD 耗时增加

**缓解措施**：
- 使用 `test-unit` 快速验证（串行也只需 ~10s）
- CI 可使用更强大的机器

### 继续并行的风险

- ❌ 持续的内存错误
- ❌ 影响其他应用
- ❌ 开发体验极差
- ❌ 维护成本高

---

## 七、总结

**核心结论**：阶段三方案未能根治内存问题，继续并行化的收益不足以抵消其成本。

**推荐行动**：立即回到串行，恢复稳定性。在确认真实性能瓶颈后，再考虑是否需要优化。

**后续跟进**：
1. 评估非沙箱环境性能
2. 优化测试本身（减少重导入）
3. 在更健壮的环境（Linux/Docker）中重新评估并行化

---

## 附录：相关文档

- `pytest-xdist-PROGRESS.md`：完整演进历史
- `memory-error-investigation-260511.md`：最新调查报告
- `docs/reviews/inv-019-test-parallelization.md`：初始可行性评估
- `.trae/documents/pytest-xdist-stability-investigation.md`：阶段二调查
