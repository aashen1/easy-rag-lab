---
id: RF-20260428-065-wt1
title: replace-experiment-config-validate-with-pydantic
type: RF
status: done
priority: medium
labels:
- refactor
- pydantic
assignee: null
milestone: null
created_at: '2026-04-28T03:45:45.040520'
updated_at: '2026-04-28T03:45:45.040520'
source: active\RF-20260428-065-wt1-replace-experiment-config-vali.md
legacy_id: null
---
## 重构目标

用 Pydantic 模型替代 `ExperimentConfig.validate()` 中的 236 行手动验证代码。

## 问题分析

当前 `src/experiment.py` 中 `ExperimentConfig.validate()` 方法（L191-L426）长达 236 行，包含：
- 字段类型检查（isinstance 链）
- 字段值范围检查（if-elif 链）
- 字段间依赖关系检查
- 嵌套配置验证（parser/chunker/retriever/ragas 等）
- 错误消息拼接

问题：
- 手动验证代码与配置结构不同步风险高
- 新增配置字段需要手动添加验证逻辑
- 错误消息格式不统一
- 无法自动生成 JSON Schema

## 重构范围

`src/experiment.py` 的 `ExperimentConfig` 类

## 重构步骤

1. 定义 Pydantic 模型替代 `ExperimentConfig`：
   - `ParserConfig(BaseModel)`
   - `ChunkerConfig(BaseModel)`
   - `RetrieverConfig(BaseModel)`
   - `RagasConfig(BaseModel)`
   - `ExperimentConfig(BaseModel)`（顶层）
2. 利用 Pydantic 的 `field_validator` 和 `model_validator` 实现字段间依赖检查
3. 保留 `validate()` 方法作为兼容层，内部调用 `model.model_validate()`
4. 利用 Pydantic 的 `model_json_schema()` 生成 JSON Schema
5. 运行全量测试确保行为不变

## 验收标准

- `validate()` 方法不超过 30 行（委托给 Pydantic）
- 所有现有测试通过
- 新增配置字段只需修改 Pydantic 模型定义
- 可生成 JSON Schema 供外部工具使用

## 更新记录

- 2026-04-28：创建
