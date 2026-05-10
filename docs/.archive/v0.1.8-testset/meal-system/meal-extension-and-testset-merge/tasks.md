# Tasks

## Phase 1: Meal 组合与扩充功能

- [x] Task 1: 扩展 MealConfig 数据结构
  - [x] SubTask 1.1: 在 MealConfig 中添加 `composition` 字段
  - [x] SubTask 1.2: 更新 `MealConfig.to_dict()` 和 `from_dict()` 方法
  - [x] SubTask 1.3: 编写单元测试验证序列化/反序列化

- [x] Task 2: 实现 `MealManager.merge_meals()` 方法
  - [x] SubTask 2.1: 设计合并逻辑：PDF 文件去重、data_id 计算
  - [x] SubTask 2.2: 实现缓存复用：检测已有解析/分块产物
  - [x] SubTask 2.3: 实现组合元数据记录
  - [x] SubTask 2.4: 编写单元测试覆盖合并场景

- [x] Task 3: 实现 `MealManager.extend_meal()` 方法
  - [x] SubTask 3.1: 设计扩充逻辑：验证新 PDF、检测重复
  - [x] SubTask 3.2: 实现增量解析/分块/索引构建
  - [x] SubTask 3.3: 实现扩充元数据记录
  - [x] SubTask 3.4: 编写单元测试覆盖扩充场景

## Phase 2: 测试集组合功能

- [x] Task 4: 扩展 TestSetMetadata 数据结构
  - [x] SubTask 4.1: 在 TestSetMetadata 中添加 `composition` 字段
  - [x] SubTask 4.2: 更新序列化/反序列化逻辑
  - [x] SubTask 4.3: 编写单元测试

- [x] Task 5: 实现 `TestSetManager.merge_test_sets()` 方法
  - [x] SubTask 5.1: 设计合并逻辑：问题 ID 重分配
  - [x] SubTask 5.2: 实现问题去重检测（基于文本相似度）
  - [x] SubTask 5.3: 实现有效性验证：检查 source_files 是否在新 meal 中
  - [x] SubTask 5.4: 实现组合元数据记录和 audit_log
  - [x] SubTask 5.5: 编写单元测试覆盖合并场景

## Phase 3: CLI 支持

- [x] Task 6: 添加 CLI 命令
  - [x] SubTask 6.1: 添加 `--merge-meals` 命令参数
  - [x] SubTask 6.2: 添加 `--extend-meal` 命令参数
  - [x] SubTask 6.3: 添加 `--merge-test-sets` 命令参数
  - [x] SubTask 6.4: 编写集成测试验证 CLI 功能

## Phase 4: 文档与验收

- [x] Task 7: 更新文档
  - [x] SubTask 7.1: 更新 `docs/guides/meal-system.md` 添加组合/扩充说明
  - [x] SubTask 7.2: 更新 `docs/guides/test-set-management.md` 添加测试集合并说明

- [x] Task 8: 验收测试
  - [x] SubTask 8.1: 运行全量测试确保无回归
  - [x] SubTask 8.2: 手动验证组合/扩充功能端到端流程

# Task Dependencies

- Task 2 依赖 Task 1（需要 MealConfig.composition 字段）
- Task 3 依赖 Task 1
- Task 5 依赖 Task 4（需要 TestSetMetadata.composition 字段）
- Task 5 依赖 Task 2（合并测试集需要关联到合并后的 meal）
- Task 6 依赖 Task 2, Task 3, Task 5（CLI 调用核心方法）
- Task 7 依赖 Task 6（文档需要反映 CLI 用法）
- Task 8 依赖所有前置任务
