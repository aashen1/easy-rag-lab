# BUG-025: source_chunks 字段始终为空

> **状态**：📋 待处理
> **优先级**：高（阻塞 chunk-level 指标计算）
> **来源**：[TODO.md](../../../TODO.md)

---

## 问题描述

`source_chunks` 字段在评测结果中始终为空列表，文档级策略无法精确到页或 chunk。

---

## 现状分析

当前问题生成策略（document-based / hybrid）生成的测试集中：
- `source_files` 字段正常填充（文档级）
- `source_chunks` 字段始终为 `[]`
- `ground_truth_excerpt` 字段在 hybrid 策略中已实现

---

## 需要调研的问题

1. 文档级策略是否有办法精确到页或 chunk？
2. 是否需要恢复 chunk 级策略（factual/boundary/multi_hop）才能更好地做 chunk 定位？
3. `_locate_chunks_by_quote()` 的匹配精度如何？能否替代显式的 source_chunks？

---

## 修复方向

- **方案 A**：在 hybrid 策略中利用 `ground_truth_excerpt` 反向定位 chunks
- **方案 B**：恢复 chunk 级策略作为补充，保留 document 级策略作为主策略
- **方案 C**：在 chunker 输出中增加页码元数据，通过页码间接定位

---

## 关联 Issue

- BUG-024：Chunk JSONL 文本编码损坏
- FEAT-035：元数据增强（页码 + 标题层级）
- RF-012：旧格式 test_sets DeprecationWarning 清理
