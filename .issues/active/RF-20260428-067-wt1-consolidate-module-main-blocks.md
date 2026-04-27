---
id: RF-20260428-067-wt1
title: consolidate-module-main-blocks-into-unified-cli
type: RF
status: todo
priority: low
labels:
- refactor
- cleanup
assignee: null
milestone: null
created_at: '2026-04-28T03:46:07.961182'
updated_at: '2026-04-28T03:46:07.961182'
source: active\RF-20260428-067-wt1-consolidate-module-main-blocks.md
legacy_id: null
---
## 重构目标

清理各模块的 `if __name__ == "__main__"` 块，统一到 CLI 入口或移除。

## 问题分析

以下模块都有各自的 `__main__` 块：
- `src/pipeline.py`
- `src/generator.py`
- `src/retriever.py`
- `src/chunker.py`
- `src/indexer.py`

问题：
- 与业务逻辑混在一起，增加文件长度
- 无法被测试覆盖
- 重复了配置加载逻辑（每个 `__main__` 都自己加载 config.yaml）
- 容易与正式 CLI（`eval/run_experiment.py`）行为不一致

## 重构范围

`src/pipeline.py`、`src/generator.py`、`src/retriever.py`、`src/chunker.py`、`src/indexer.py`

## 重构步骤

1. 审查每个 `__main__` 块的功能，确认是否有独立使用价值
2. 如果有独立使用价值：将逻辑移入 `src/cli/` 目录下的独立 CLI 模块
3. 如果无独立使用价值（功能已被 `eval/run_experiment.py` 覆盖）：直接移除
4. 运行 `pixi run lint` 确认无问题
5. 运行全量测试

## 验收标准

- `src/` 下的核心模块不再包含 `__main__` 块
- 如需独立运行某模块，通过 `src/cli/` 入口
- 所有现有测试通过

## 更新记录

- 2026-04-28：创建
