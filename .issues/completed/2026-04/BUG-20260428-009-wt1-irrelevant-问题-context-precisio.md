---
id: BUG-20260428-009-wt1
title: irrelevant 问题 context_precision/context_recall 使用错误 ground truth
type: BUG
status: done
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: completed\2026-04\BUG-20260428-009-wt1-irrelevant-问题-context-precisio.md
legacy_id: BUG-029
---
## BUG 描述

irrelevant 问题 context_precision/context_recall 使用错误 ground truth

## 来源

troubleshooting

## 备注

builtin_evaluator 增加 expect_retrieval + expected_answer 守卫，irrelevant 问题不再计算

## 迁移信息

- 原始 ID: BUG-029
- 迁移时间: 2026-04-28 00:48:30
