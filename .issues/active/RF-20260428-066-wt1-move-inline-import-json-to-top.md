---
id: RF-20260428-066-wt1
title: move-inline-import-json-to-top-level-in-experiment-py
type: RF
status: todo
priority: low
labels:
- refactor
- cleanup
assignee: null
milestone: null
created_at: '2026-04-28T03:45:57.806621'
updated_at: '2026-04-28T03:45:57.806621'
source: active\RF-20260428-066-wt1-move-inline-import-json-to-top.md
legacy_id: null
---
## 重构目标

将 `src/experiment.py` 中方法内部的 `import json` 移至文件顶部统一导入。

## 问题分析

当前 `src/experiment.py` 中 `import json` 出现在以下方法内部：
- `save_snapshots`
- `_create_manifest`
- `load_experiment_result`
- `list_experiments`
- `update_manifest_status`
- `save_variant_result`

`json` 是标准库模块，无循环导入风险，不应在方法内部延迟导入。这种写法：
- 增加认知负担（读者会误以为有循环导入问题）
- 违反 PEP 8 导入规范
- 每次调用有微小的性能开销

## 重构范围

`src/experiment.py`

## 重构步骤

1. 在文件顶部添加 `import json`
2. 删除所有方法内部的 `import json`
3. 运行 `pixi run lint` 确认无问题
4. 运行相关测试

## 验收标准

- `import json` 只出现在文件顶部
- 所有现有测试通过
- ruff 检查通过

## 更新记录

- 2026-04-28：创建
