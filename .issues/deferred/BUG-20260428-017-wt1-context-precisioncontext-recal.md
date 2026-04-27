---
id: BUG-20260428-017-wt1
title: context_precision/context_recall 在 generation 下时聚合位置不一致
type: BUG
status: deferred
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: deferred\BUG-20260428-017-wt1-context-precisioncontext-recal.md
legacy_id: BUG-019
---
## BUG 描述

context_precision/context_recall 在 generation 下时聚合位置不一致

## 来源

RAGAS 指南

## 备注

旧写法放 generation 下时逐题结果在 generation 字典而非 llm_retrieval；建议统一用 retrieval

## 迁移信息

- 原始 ID: BUG-019
- 迁移时间: 2026-04-28 00:48:31
