---
id: RF-20260428-012-wt1
title: normalize_source 匹配精度提升（当前仅比较文件名 stem，过于宽松）
type: RF
status: done
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: completed\2026-04\RF-20260428-012-wt1-normalize-source-匹配精度提升当前仅比较文件.md
legacy_id: RF-014
---
## RF 描述

normalize_source 匹配精度提升（当前仅比较文件名 stem，过于宽松）

## 来源

pipeline-deep-audit.md

## 备注

已在 retrieval.py/dedup.py/builtin_evaluator.py 中统一使用 include_parent=True

## 规模

小

## 迁移信息

- 原始 ID: RF-014
- 迁移时间: 2026-04-28 00:48:31
