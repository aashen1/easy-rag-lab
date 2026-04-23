# Meal 数据管理系统使用指南

<!-- status: needs-update -->

> ⚠️ **文档状态**：本文档缺少 v0.1.8 新增功能的说明，包括：等价组（equivalence group）推断、meal 的 `composition` 元数据结构、TestSetManager 集成（`--merge-test-sets`）、以及 `document` 策略的问题生成。`--generate-test-set` 的 `--strategy` 默认值已变更为 `document`，但文档仍显示 `factual`。建议全面更新。

> 最后更新: 2026-04-18

本文档介绍 Meal 数据管理系统的使用方法。

---

## 概述

Meal（套餐）系统允许你从全量文档中创建一个**命名的、持久化的数据子集快照**，包含：
- 抽样配置和结果（哪些 PDF 被选中）
- 独立的向量索引（Qdrant collection）
- 关联的测试集（自动生成或手写）

### 核心优势

| 特性 | 说明 |
|------|------|
| **内容寻址** | 相同 PDF 合集 + 相同配置 = 相同索引，天然去重 |
| **缓存复用** | 解析和分块产物按内容哈希存储，避免重复计算 |
| **实验对比** | 同一数据搭配不同配置可创建多个 Meal，便于对比 |
| **完整生命周期** | 创建、复制、重命名、修复、删除、状态检查 |

---

## 快速开始

### 创建 Meal

```bash
# 按文档数采样
pixi run python main.py --create-meal my_meal --sample-count 10

# 按总页数采样
pixi run python main.py --create-meal my_meal --sample-pages 5000

# 按比例采样
pixi run python main.py --create-meal my_meal --sample-ratio 0.1

# 指定随机种子确保可复现
pixi run python main.py --create-meal my_meal --sample-count 10 --seed 42
```

### 使用 Meal 问答

```bash
# 单轮问答
pixi run python main.py --meal my_meal --query "问题"

# 交互式问答
pixi run python main.py --meal my_meal
```

### 列出所有 Meal

```bash
pixi run python main.py --list-meals
```

---

## 完整命令参考

### 创建 Meal

```bash
pixi run python main.py --create-meal [名称] --sample-count|--sample-pages|--sample-ratio [值] [选项]
```

| 参数 | 说明 |
|------|------|
| `--create-meal [名称]` | Meal 名称（可省略，自动生成时间戳名称） |
| `--sample-count N` | 抽样 N 个 PDF 文件 |
| `--sample-pages N` | 抽样直到总页数达到 N |
| `--sample-ratio R` | 抽样比例（0.0-1.0） |
| `--seed N` | 随机种子（确保可复现） |
| `--force-parse` | 强制重新解析 PDF |

### 查看 Meal

```bash
# 列出所有 Meal
pixi run python main.py --list-meals

# 查看 Meal 详情
pixi run python main.py --meal-info <meal_name>
```

### 管理 Meal

```bash
# 重命名
pixi run python main.py --rename-meal <old_name> <new_name>

# 复制（浅拷贝，共享向量索引）
pixi run python main.py --copy-meal <source> <target>

# 删除
pixi run python main.py --delete-meal <meal_name>

# 修复（当 PDF 文件缺失或变更时）
pixi run python main.py --repair-meal <meal_name>
```

### 合并 Meal

```bash
# 合并多个 meal 创建新 meal
pixi run python main.py --merge-meals A B C --name D
```

| 参数 | 说明 |
|------|------|
| `--merge-meals MEAL [MEAL...]` | 要合并的 meal 名称列表 |
| `--name NAME` | 新 meal 名称（可选，默认自动生成） |

**合并行为**：
- PDF 文件自动去重（基于路径）
- 复用已有的解析/分块缓存
- 在 `composition` 字段记录合并来源

### 扩充 Meal

```bash
# 在已有 meal 基础上添加新 PDF
pixi run python main.py --extend-meal A --add-pdfs path/to/new1.pdf path/to/new2.pdf --name B
```

| 参数 | 说明 |
|------|------|
| `--extend-meal MEAL` | 源 meal 名称 |
| `--add-pdfs PDF [PDF...]` | 要添加的 PDF 文件路径 |
| `--name NAME` | 新 meal 名称（可选，默认自动生成） |

**扩充行为**：
- 自动检测并跳过已存在的 PDF
- 仅对新 PDF 执行解析/分块
- 在 `composition` 字段记录扩充来源

### 生成测试集

```bash
pixi run python main.py --generate-test-set <meal_name> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--strategy` | 生成策略（factual/boundary/multi_hop） | factual |
| `--num-questions` | 问题数量 | 20 |
| `--seed` | 随机种子 | 随机 |

---

## 缓存行为

| 场景 | 行为 |
|------|------|
| 首次创建 | 解析 → 分块 → 建索引 |
| 相同数据 + 相同配置 | 全部缓存命中，秒级完成 |
| 相同数据 + 不同配置 | 解析缓存命中，重新分块和建索引 |
| 不同数据 | 全部重新执行 |

---

## Meal 状态

| 状态 | 说明 |
|------|------|
| `AVAILABLE` | 所有 PDF 文件存在且 SHA256 匹配 |
| `FILES_MISSING` | 部分 PDF 文件缺失 |
| `FILES_CHANGED` | 部分 PDF 文件 SHA256 变更 |
| `MIXED` | 同时存在缺失和变更的文件 |

---

## 相关文档

- [实验系统](experiment-system.md)
- [CLI 参考](../cli-reference.md)
