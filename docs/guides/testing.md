# 测试运行指南

<!-- status: active -->

> 最后更新: 2026-04-18

本文档介绍如何运行和管理项目测试。

---

## 概述

项目使用 pytest 作为测试框架，包含以下测试类型：
- **单元测试**：测试单一模块的行为
- **组件集成测试**：测试多组件协作
- **集成测试**：测试真实环境下的端到端行为

---

## 快速开始

### 运行所有测试

```bash
pixi run pytest tests/ -v
```

### 运行单元测试（快速）

```bash
pixi run pytest tests/ -m "not integration" -v
```

### 运行集成测试

```bash
pixi run pytest tests/ -m "integration" -v
```

---

## 按 Marker 过滤

```bash
# 仅运行单元测试
pixi run pytest tests/ -m "unit" -v

# 排除集成测试
pixi run pytest tests/ -m "not integration" -v

# 仅运行集成测试（需运行环境 + API key）
pixi run pytest tests/ -m "integration" -v

# 运行慢速测试
pixi run pytest tests/ -m "slow" -v
```

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
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  Layer 2: Component Integration（组件集成测试）        │
│  多组件协作，mock 外部依赖                            │
│  Marker: @pytest.mark.unit                          │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│  Layer 1: Unit Tests（单元测试）                      │
│  单一模块，mock 所有依赖                             │
│  Marker: @pytest.mark.unit                          │
└─────────────────────────────────────────────────────┘
```

---

## 测试选择策略

| 场景 | 推荐命令 |
|------|---------|
| 日常开发 | `pixi run pytest tests/ -m "not integration" -v` |
| 新功能开发 | `pixi run pytest tests/test_<module>.py -v` |
| 版本发布 | `pixi run pytest tests/ -v` |
| CI 环境 | `pixi run pytest tests/ -m "not integration" -v` |

---

## 常见问题

### Q: 集成测试跳过了怎么办？

A: 集成测试需要设置环境变量 `RUN_INTEGRATION_TESTS=true` 并配置 API key。

### Q: 如何运行单个测试方法？

A: 使用 `pixi run pytest tests/test_file.py::TestClass::test_method -v`

---

## 相关文档

- [系统架构](../architecture.md)
- [CLI 参考](../cli-reference.md)
