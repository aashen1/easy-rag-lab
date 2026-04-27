---
id: BUG-20260428-018-wt1
title: RAGAS evaluate() 的 raise_exceptions 行为差异
type: BUG
status: deferred
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: deferred\BUG-20260428-018-wt1-ragas-evaluate-的-raise-excepti.md
legacy_id: BUG-020
---
## BUG 描述

RAGAS evaluate() 的 raise_exceptions 行为差异

## 来源

RAGAS 指南

## 备注

evaluate_single 用 True 会抛异常中断，evaluate_batch 用 False 静默返回 NaN

## 迁移信息

- 原始 ID: BUG-020
- 迁移时间: 2026-04-28 00:48:31
