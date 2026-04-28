---
id: RF-20260428-060-wt1
title: split-test-generator-4610-lines-god-file
type: RF
status: done
priority: high
labels:
- refactor
- god-object
assignee: null
milestone: null
created_at: '2026-04-28T03:44:50.194657'
updated_at: '2026-04-28T03:44:50.194657'
source: active\RF-20260428-060-wt1-split-test-generator-4610-line.md
legacy_id: null
---
## 重构目标

将 `src/test_generator.py`（4610 行）拆分为多个职责单一的模块，消除 God Object 反模式。

## 问题分析

当前 `test_generator.py` 是全项目最大的单文件，承载了问题生成的所有策略：
- 多种问题生成策略（factual/hypothetical/adversarial/document 等）
- Golden test set 生成与验证
- 问题补充（supplement）逻辑
- 答案 chunk 定位（locate_answer_chunks）
- 数值精度校验
- 文档去重
- excerpt 验证

一个文件超过 2000 行就该拆了，4600 行是严重的代码坏味道，导致：
- 难以定位和修改特定策略
- 测试维护成本高
- 代码审查困难
- 合并冲突频繁

## 重构范围

`src/test_generator.py` → 拆分为 `src/test_generation/` 包

## 重构步骤

1. 创建 `src/test_generation/` 包目录
2. 提取数据模型到 `src/test_generation/models.py`（问题类型枚举、分布配置等）
3. 提取各策略为独立模块：
   - `src/test_generation/factual_strategy.py`
   - `src/test_generation/hypothetical_strategy.py`
   - `src/test_generation/adversarial_strategy.py`
   - `src/test_generation/document_strategy.py`
4. 提取验证逻辑到 `src/test_generation/validators.py`（数值精度校验、excerpt 验证、文档去重）
5. 提取 chunk 定位到 `src/test_generation/chunk_locator.py`
6. 保留 `src/test_generator.py` 作为 facade，从 `src/test_generation/` 重新导出 `TestSetGenerator`
7. 更新所有 import 路径
8. 运行全量测试确保行为不变

## 验收标准

- 每个文件不超过 500 行
- 所有现有测试通过
- `from src.test_generator import TestSetGenerator` 仍然可用

## 更新记录

- 2026-04-28：创建
