# 测试运行指南

<!-- status: up-to-date -->

> 最后更新: 2026-05-02

本文档介绍如何运行和管理项目测试。

---

## 概述

项目使用 pytest 作为测试框架，测试通过三层 marker 分层，并使用 pytest-xdist 并行加速：

- **单元测试**（`@pytest.mark.unit`）：单一模块，mock 所有依赖
- **慢速测试**（`@pytest.mark.slow`）：涉及重导入（ragas/torch）的测试
- **集成测试**（`@pytest.mark.integration`）：触及外部系统（Qdrant、LLM API、真实 PDF）

---

## 快速开始

### 三层测试命令

| 命令 | 跑什么 | 排除什么 | 预期耗时 |
|------|--------|---------|---------|
| `pixi run test-unit` | `@pytest.mark.unit` | integration + slow + 无标记 | ~10s |
| `pixi run test` | 排除 integration 和 slow | integration + slow | ~35s |
| `pixi run test-all` | 全量 | 无 | ~60s |

```bash
# 开发中快速反馈（只跑 unit marker）
pixi run test-unit

# 功能完成后验证（排除 integration 和 slow）
pixi run test

# 发版前全量验证
pixi run test-all
```

---

## 按 Marker 过滤

```bash
# 仅运行 unit 标记的测试
pixi run pytest tests/ -m "unit" -v

# 排除 integration 和 slow
pixi run pytest tests/ -m "not integration and not slow" -v

# 仅运行集成测试（需运行环境 + API key）
pixi run pytest tests/ -m "integration" -v

# 仅运行慢速测试（ragas/torch 相关）
pixi run pytest tests/ -m "slow" -v
```

### Marker 定义

| Marker | 含义 | 典型场景 |
|--------|------|---------|
| `unit` | 纯单元测试，无外部依赖 | mock 测试、参数校验、数据转换 |
| `slow` | 重导入或耗时 >5s 的测试 | ragas/torch 加载、大文件解析 |
| `integration` | 触及外部系统 | Qdrant、LLM API、真实 PDF |

---

## 按模块过滤

```bash
# 仅运行核心 RAG 模块测试
pixi run pytest tests/test_parser.py tests/test_chunker.py tests/test_embedder.py -v

# 仅运行评测相关测试
pixi run pytest tests/test_metrics.py tests/test_experiment.py -v

# 仅运行回归测试
pixi run pytest tests/test_regression.py -v
```

---

## 并行化

所有 pixi 任务默认使用 `-n auto`（pytest-xdist），自动按 CPU 核心数并行执行。如需串行调试：

```bash
# 串行运行（方便调试）
pixi run pytest tests/ -m "unit" -v -n 0

# 指定并行进程数
pixi run pytest tests/ -m "unit" -v -n 4
```

---

## 调试与诊断

```bash
# 失败时显示完整 traceback
pixi run pytest tests/test_metrics.py -v --tb=long

# 失败时进入 pdb 调试器
pixi run pytest tests/test_metrics.py -v --pdb

# 显示测试中 print 输出
pixi run pytest tests/test_metrics.py -v -s

# 遇到第一个失败就停止
pixi run pytest tests/ -x -v

# 只运行上次失败的测试
pixi run pytest tests/ --lf -v
```

---

## 覆盖率报告

```bash
# 生成覆盖率报告
pixi run pytest tests/ --cov=src --cov=eval --cov-report=term-missing -v

# 生成 HTML 覆盖率报告
pixi run pytest tests/ --cov=src --cov=eval --cov-report=html -v
```

---

## 测试分层

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Integration Tests（集成测试）               │
│  触及外部系统：Qdrant、LLM API、真实 PDF              │
│  Marker: @pytest.mark.integration                   │
│  命令: pixi run test-all                            │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  Layer 2: Standard Tests（标准测试）                  │
│  多组件协作，mock 外部依赖，排除重导入                  │
│  Marker: not integration and not slow               │
│  命令: pixi run test                                │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  Layer 1: Unit Tests（纯单元测试）                    │
│  单一模块，mock 所有依赖                             │
│  Marker: @pytest.mark.unit                          │
│  命令: pixi run test-unit                           │
└─────────────────────────────────────────────────────┘
```

---

## 测试选择策略

| 场景 | 推荐命令 |
|------|---------|
| 开发中频繁运行 | `pixi run test-unit` |
| 功能完成后验证 | `pixi run test` |
| 新功能开发（单模块） | `pixi run pytest tests/test_<module>.py -v` |
| post-merge 验证 | `pixi run test`（自动触发） |
| 版本发布 | `pixi run test-all` |

---

## 常见问题

### Q: 集成测试跳过了怎么办？

A: 集成测试需要设置环境变量 `RUN_INTEGRATION_TESTS=true` 并配置 API key。

### Q: 如何运行单个测试方法？

A: 使用 `pixi run pytest tests/test_file.py::TestClass::test_method -v`

### Q: 什么时候用 test-unit vs test？

A: 开发中写完一个函数/类后用 `test-unit` 快速验证；完成一个功能模块后用 `test` 做更全面的检查。post-merge hook 自动跑 `test`。

---

## 相关文档

- [测试分层与耗时预算](test-layering-and-time-budgets.md) — 分层原则与耗时预算
- [Lint 与 pre-commit 入门](lint-and-precommit.md) — 钩子配置详解
- [CLI 参考](../user-guides/cli-reference.md) — 命令行参考
