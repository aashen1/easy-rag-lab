---
id: RF-20260428-062-wt1
title: split-meal-py-2203-lines-mixed-responsibilities
type: RF
status: todo
priority: high
labels:
- refactor
assignee: null
milestone: null
created_at: '2026-04-28T03:45:11.806335'
updated_at: '2026-04-28T03:45:11.806335'
source: active\RF-20260428-062-wt1-split-meal-py-2203-lines-mixed.md
legacy_id: null
---
## 重构目标

将 `src/meal.py`（2203 行）按职责拆分为多个模块，消除混合职责问题。

## 问题分析

当前 `meal.py` 同时包含：
- 数据模型（`MealFile`、`MealConfig`、`MealStatus` 枚举）
- 哈希计算（6 个 `compute_*` 函数：`compute_file_sha256`、`compute_data_id`、`compute_parser_config_hash`、`compute_chunker_config_hash`、`compute_embedding_config_hash`、`compute_index_key`）
- 缓存管理（`ArtifactCache` 类，含 10+ 个方法）
- Meal CRUD（`MealManager` 类，含 15+ 个方法：create/load/delete/rename/copy/merge/extend/repair/check_status 等）
- 构建辅助（`build_chunks_if_needed`、`build_index_from_chunks`）
- 工具函数（`generate_collection_name`、`validate_meal_name`、`generate_timestamp_name`、`_infer_equivalence_groups`）

违反单一职责原则，修改缓存逻辑可能影响 Meal 管理逻辑，反之亦然。

## 重构范围

`src/meal.py` → 拆分为 `src/meal/` 包

## 重构步骤

1. 创建 `src/meal/` 包目录
2. 提取数据模型到 `src/meal/models.py`（`MealFile`、`MealConfig`、`MealStatus`）
3. 提取哈希计算到 `src/meal/hashes.py`（6 个 `compute_*` 函数 + `generate_collection_name`）
4. 提取缓存管理到 `src/meal/cache.py`（`ArtifactCache` 类）
5. 提取构建辅助到 `src/meal/builders.py`（`build_chunks_if_needed`、`build_index_from_chunks`）
6. 保留 `MealManager` 在 `src/meal/manager.py`
7. 提取工具函数到 `src/meal/utils.py`（`validate_meal_name`、`generate_timestamp_name`、`_infer_equivalence_groups`）
8. `src/meal/__init__.py` 重新导出所有公共 API
9. 保留 `src/meal.py` 作为 facade（`from src.meal import *`）
10. 更新所有 import 路径
11. 运行全量测试确保行为不变

## 验收标准

- 每个文件不超过 500 行
- 所有现有测试通过
- `from src.meal import MealManager, ArtifactCache, MealConfig` 仍然可用

## 更新记录

- 2026-04-28：创建
