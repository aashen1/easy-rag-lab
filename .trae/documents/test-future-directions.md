# 测试系统优化方向建议

> Date: 2026-04-17
> 前提：当前测试套件已完成重构，356 个测试全部通过，核心模块覆盖率达 100%

---

## 概述

当前测试体系已解决分析文档中提出的所有核心问题。若要继续优化，建议按以下四个方向推进，按投入产出比排序。

---

## 方向一：黄金测试集落地（最高优先级）

### 为什么重要

黄金测试集（Golden Test Suite）是当前测试体系中**唯一未完成**的关键组件。它提供了其他测试无法替代的价值：在真实 RAG 链路上验证检索和生成质量。

### 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| `exp_configs/golden_test.yaml` | ✅ 已创建 | 3 个 test_sets，1 个 baseline variant |
| `tests/fixtures/golden_qa.json` | ⚠️ 占位数据 | 仅 2 条，待填充实际数据 |
| `tests/test_regression.py` | ✅ 已创建 | 参数化驱动器，Mock + Integration 模式 |
| `golden_test` Meal | ❌ 未创建 | 需运行环境 |
| AI 质量评估 | ❌ 未完成 | 需运行环境 |

### 落地步骤

```
Step 1: 创建 golden_test Meal
  pixi run python main.py --create-meal golden_test --sample-ratio 0.03 --seed 42
  预期：ratio=0.03, seed=42 → 约 3-4 个 PDF, 300-500 chunks

Step 2: 运行实验配置生成问题集
  pixi run exp golden_test.yaml
  预期：10 个问题（factual:5 + boundary:3 + multi_hop:2）

Step 3: AI 质量评估
  对生成的问题进行质量评估，输出评估文档

Step 4: 人工审核
  审核评估文档，手动调整问题

Step 5: 固化到 golden_qa.json
  将审核通过的问题集写入 tests/fixtures/golden_qa.json

Step 6: 验证回归测试
  pixi run pytest tests/test_regression.py -v
```

### 预期收益

- **回归保护**：每次代码变更后可快速验证 RAG 链路未被破坏
- **性能基线**：建立 Hit Rate / MRR / NDCG 的基线值，用于后续优化对比
- **可扩展性**：新功能上线只需向 `golden_qa.json` 添加条目

---

## 方向二：Property-Based Testing（高优先级）

### 为什么重要

当前测试使用"例子驱动"（example-based）模式，即手动构造输入-输出对。这种方式对已知边界条件有效，但无法穷举所有可能的输入组合。Property-based testing 通过自动生成大量随机输入，验证函数的"性质"（property）而非具体输出。

### 适用模块

| 模块 | 函数 | 可验证的 Property |
|------|------|------------------|
| `eval/metrics.py` | `calculate_hit_rate` | 返回值始终在 [0, 1]；expected 为空时返回 0.0；retrieved ⊇ expected 时返回 1.0 |
| `eval/metrics.py` | `calculate_mrr` | 返回值始终在 [0, 1]；expected 为空时返回 0.0；retrieved[0] ∈ expected 时返回 1.0 |
| `eval/metrics.py` | `calculate_ndcg` | 返回值始终在 [0, 1]；expected 为空时返回 0.0；完美排序时返回 1.0 |
| `src/experiment.py` | `deep_merge` | 幂等性：`deep_merge(base, override) == deep_merge(deep_merge(base, override), override)` |
| `src/experiment.py` | `deep_merge` | 保持性：`deep_merge(base, {}) == base`（深拷贝） |
| `src/meal.py` | `compute_data_id` | 确定性：相同输入始终产生相同输出 |
| `src/meal.py` | `compute_data_id` | 顺序无关：`compute_data_id([a, b]) == compute_data_id([b, a])` |

### 实现方案

使用 `hypothesis` 库：

```python
from hypothesis import given, strategies as st

@given(
    retrieved=st.lists(st.text(min_size=1), max_size=20),
    expected=st.lists(st.text(min_size=1), max_size=20),
)
def test_hit_rate_always_in_range(retrieved, expected):
    result = calculate_hit_rate(retrieved, expected)
    assert 0.0 <= result <= 1.0

@given(
    base=st.dictionaries(st.text(), st.integers()),
    override=st.dictionaries(st.text(), st.integers()),
)
def test_deep_merge_idempotent(base, override):
    first = deep_merge(base, override)
    second = deep_merge(first, override)
    assert second == first
```

### 预期收益

- **发现未知边界条件**：自动生成人类不会想到的输入组合
- **数学正确性保证**：对 metrics 函数提供比例子测试更强的保证
- **文档化函数性质**：property 本身就是函数行为的精确规格

### 投入评估

- **依赖引入**：需添加 `hypothesis` 到开发依赖
- **编写成本**：约 10-15 个 property 测试，每个 5-10 行
- **运行成本**：每个 property 测试默认运行 100-1000 个用例，总运行时间增加约 10-30 秒

---

## 方向三：测试覆盖率量化（中优先级）

### 为什么重要

当前"100% 模块覆盖"是指每个源文件都有对应的测试文件，而非行级覆盖率（line coverage）。行级覆盖率能精确指出哪些代码路径从未被执行。

### 实现方案

```bash
# 安装 pytest-cov（如尚未安装）
# 在 pixi.toml 中添加 pytest-cov 为开发依赖

# 生成终端覆盖率报告
pixi run pytest tests/ --cov=src --cov=eval --cov-report=term-missing -v

# 生成 HTML 覆盖率报告（更直观）
pixi run pytest tests/ --cov=src --cov=eval --cov-report=html -v
# 然后在浏览器中打开 htmlcov/index.html
```

### 目标指标

| 模块 | 目标行覆盖率 | 说明 |
|------|------------|------|
| `eval/metrics.py` | 100% | 纯函数，应完全覆盖 |
| `src/utils.py` | >90% | 部分 fallback 路径可能难以触发 |
| `src/retriever.py` | >85% | 异常路径已覆盖 |
| `src/generator.py` | >85% | 异常路径已覆盖 |
| `src/indexer.py` | >80% | 部分 build_index 降级路径未覆盖 |
| `src/pipeline.py` | >80% | build_index 方法未测试 |
| 整体 | >80% | 合理的行业基准 |

### 预期收益

- **精确定位覆盖缺口**：不再依赖"模块有无测试文件"的粗粒度判断
- **CI 集成**：可在 CI 中设置覆盖率阈值，低于阈值则构建失败
- **回归保护**：覆盖率下降时自动告警

---

## 方向四：CI/CD 集成与自动化（中优先级）

### 为什么重要

当前测试完全依赖手动运行。如果能在每次提交时自动运行测试，可以更早发现回归问题。

### 建议的 CI 流水线

```yaml
# .github/workflows/test.yml（示例）
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install pixi
        uses: prefix-dev/setup-pixi@v0.8.1
      - name: Run unit tests
        run: pixi run pytest tests/ -m "not integration" -v --tb=short
      - name: Check coverage
        run: pixi run pytest tests/ -m "not integration" --cov=src --cov=eval --cov-fail-under=80

  integration-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Install pixi
        uses: prefix-dev/setup-pixi@v0.8.1
      - name: Run integration tests
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
        run: pixi run pytest tests/ -m "integration" -v
```

### 分阶段实施

| 阶段 | 内容 | 前置条件 |
|------|------|---------|
| Phase 1 | GitHub Actions + 单元测试自动运行 | 仓库迁移至 GitHub |
| Phase 2 | 覆盖率阈值检查 | pytest-cov 集成 |
| Phase 3 | Integration 测试（main 分支） | API key 配置 |
| Phase 4 | 黄金测试集自动运行 | Meal 数据固化 |

---

## 方向五：测试性能优化（低优先级）

### 为什么提及

当前 356 个测试运行时间约 2.5 分钟，对于日常开发尚可接受。但随着测试数量增长（特别是黄金测试集落地后），运行时间可能成为瓶颈。

### 优化策略

| 策略 | 预期效果 | 实施难度 |
|------|---------|---------|
| **测试并行化**：`pixi run pytest tests/ -n auto`（需 pytest-xdist） | 运行时间降低 50-70% | 低 |
| **测试分层执行**：开发时只跑 `unit`，提交前跑 `not integration` | 日常反馈时间 <30s | 已具备基础设施 |
| **慢测试标记**：对 >5s 的测试标记 `@pytest.mark.slow`，日常跳过 | 日常反馈时间更短 | 低 |
| **Fixture 作用域优化**：将 `scope="session"` 用于昂贵的 fixture | 减少重复初始化 | 中 |

### 当前瓶颈分析

```
总运行时间：~150s
├── test_experiment.py:        ~30s（大量文件 I/O）
├── test_e2e_experiment.py:    ~25s（文件 I/O + 多 fixture）
├── test_experiment_reporter.py: ~20s
├── test_meal.py:              ~15s
├── 其他:                      ~60s
```

主要瓶颈是文件 I/O（临时目录创建/清理）和 mock 初始化。并行化是最直接的优化手段。

---

## 方向六：测试文档与开发者体验（低优先级）

### 建议内容

| 项目 | 说明 |
|------|------|
| **测试命名规范文档** | 统一 `test_<模块>_<场景>_<预期结果>` 命名模式 |
| **Fixture 使用指南** | 说明何时用 conftest fixture、何时用本地 fixture |
| **Mock 策略指南** | 说明何时用 `@patch`、何时用 `MagicMock`、何时用真实对象 |
| **测试模板** | 为新增模块提供测试文件模板 |
| **PR 检查清单** | 提交 PR 时的测试相关检查项 |

### 预期收益

- 降低新开发者编写测试的学习成本
- 保持测试风格一致性
- 减少代码审查中的反复沟通

---

## 总结：优化路线图

```
当前状态 ────────────────────────────────────────────────→ 目标状态

[✅ 已完成]                                              [🎯 目标]
核心模块 100% 覆盖                                       行级覆盖率 >80%
356 个测试全部通过                                       CI 自动运行
Marker 规范建立                                          Property-based testing
黄金测试集框架就位                                       黄金测试集完整落地

优先级排序：
1. 🥇 黄金测试集落地（补全唯一未完成的关键组件）
2. 🥈 Property-Based Testing（强化数学正确性保证）
3. 🥉 测试覆盖率量化（从模块级精确到行级）
4.    CI/CD 集成（自动化质量保障）
5.    测试性能优化（提升开发者体验）
6.    测试文档（降低维护成本）
```

每个方向均可独立推进，无强依赖关系。建议按优先级逐步实施，每完成一个方向后在 `notes/` 中记录成果和发现。
