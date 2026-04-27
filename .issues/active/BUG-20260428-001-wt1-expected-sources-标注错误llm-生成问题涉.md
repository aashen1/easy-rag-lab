---
id: BUG-20260428-001-wt1
title: expected_sources 标注错误（LLM 生成问题涉及文档中提到的其他实体，但 source_files 仅指向生成问题时的源文档）
type: BUG
status: todo
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: active\BUG-20260428-001-wt1-expected-sources-标注错误llm-生成问题涉.md
legacy_id: BUG-021
---
## BUG 描述

expected_sources 标注错误（LLM 生成问题涉及文档中提到的其他实体，但 source_files 仅指向生成问题时的源文档）

## 来源

pipeline-deep-audit.md

## 备注

需重新设计问题生成策略，使 source_files 反映问题实际涉及的文档

## 迁移信息

- 原始 ID: BUG-021
- 迁移时间: 2026-04-28 00:48:30
