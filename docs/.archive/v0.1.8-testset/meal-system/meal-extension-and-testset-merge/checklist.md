# Checklist

## Phase 1: Meal 组合与扩充功能

- [x] MealConfig.composition 字段已添加并正确序列化
- [x] `MealManager.merge_meals()` 方法实现完成
  - [x] PDF 文件去重逻辑正确
  - [x] data_id 计算正确
  - [x] 缓存复用正常工作
  - [x] 组合元数据正确记录
- [x] `MealManager.extend_meal()` 方法实现完成
  - [x] 新 PDF 验证逻辑正确
  - [x] 重复检测和警告正常
  - [x] 增量解析/分块/索引正常
  - [x] 扩充元数据正确记录
- [x] 单元测试覆盖所有场景

## Phase 2: 测试集组合功能

- [x] TestSetMetadata.composition 字段已添加并正确序列化
- [x] `TestSetManager.merge_test_sets()` 方法实现完成
  - [x] 问题 ID 重分配正确
  - [x] 问题去重检测正常
  - [x] 有效性验证正确
  - [x] 组合元数据和 audit_log 正确记录
- [x] 单元测试覆盖所有场景

## Phase 3: CLI 支持

- [x] `--merge-meals` 命令正常工作
- [x] `--extend-meal` 命令正常工作
- [x] `--merge-test-sets` 命令正常工作
- [x] CLI 输出信息清晰完整

## Phase 4: 文档与验收

- [x] `docs/guides/meal-system.md` 已更新
- [x] `docs/guides/test-set-management.md` 已更新
- [x] 全量测试通过，无回归（187 passed）
- [x] 端到端手动验证通过

## 代码质量

- [x] 所有新增代码有类型标注
- [x] 所有公共方法有 docstring
- [x] IO 操作有 try/except 异常处理
- [x] 使用 loguru 记录日志
- [x] `pixi run lint` 检查通过（新增代码无错误，现有代码问题与本次修改无关）
