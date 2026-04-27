---
id: BUG-20260428-010-wt1
title: RAGAS answer_correctness/semantic_similarity 对 irrelevant 问题循环论证
type: BUG
status: done
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: completed\2026-04\BUG-20260428-010-wt1-ragas-answer-correctnesssemant.md
legacy_id: BUG-030
---
## BUG 描述

RAGAS answer_correctness/semantic_similarity 对 irrelevant 问题循环论证

## 来源

troubleshooting

## 备注

ragas_evaluator 仅 expect_retrieval=True 时回退到 expected_answer，run_experiment 过滤 irrelevant 问题的 reference-required 指标

## 迁移信息

- 原始 ID: BUG-030
- 迁移时间: 2026-04-28 00:48:30
