---
id: BUG-20260428-004-wt1
title: Chunk JSONL 文本编码损坏导致 chunk-level 指标无法计算
type: BUG
status: done
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: completed\2026-04\BUG-20260428-004-wt1-chunk-jsonl-文本编码损坏导致-chunk-lev.md
legacy_id: BUG-024
---
## BUG 描述

Chunk JSONL 文本编码损坏导致 chunk-level 指标无法计算

## 来源

hybrid-metrics-fix.md

## 备注

新增 `_build_token_char_offsets()` 构建 token→char 映射，`chunk_text()` 改用原文切片替代 `encoding.decode()`，彻底避免 UTF-8 多字节字符被 chunk 边界截断产生乱码；`chunk_text_page_aware()` cross_page_overlap 同步修复

## 迁移信息

- 原始 ID: BUG-024
- 迁移时间: 2026-04-28 00:48:30
