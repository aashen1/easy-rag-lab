# BUG-024: Chunk JSONL 文本编码损坏 + 审查脚本缺少页码信息

> **状态**：📋 待处理
> **优先级**：高（阻塞 chunk-level 指标计算和审查脚本精确度）
> **来源**：[hybrid-metrics-fix.md](../guides/development/hybrid-metrics-fix.md#6-未修复问题chunk-jsonl-文本编码损坏) + [TODO.md](../../../TODO.md)

---

## 问题描述

两个相互关联的问题：

### 问题 A：Chunk JSONL 文本编码损坏

chunk text 字段中文字符为乱码（如 `鍦 浜` 而非 `地产`），导致：
- `source_chunks` 始终为空（无法匹配）
- chunk_hit_rate / MRR / NDCG 指标为 null
- 审查脚本无法定位 ground truth 出自哪个 chunk

### 问题 B：审查脚本缺少页码信息

审查脚本不会展示问题出自哪一页，如果 ground truth 位置搞错，用户审查时无法发现。

---

## 根因分析

1. **编码问题**：chunk JSONL 文件写入时可能使用了错误的编码（Latin-1 而非 UTF-8），或读取时编码不匹配
2. **source_chunks 未实装**：即使编码修复，`source_chunks` 字段的填充逻辑可能尚未实现

---

## 影响范围

- 所有 chunk-level 指标（chunk_hit_rate, chunk_mrr, chunk_ndcg）
- 审查脚本的精确度
- 评测系统的可信度

---

## 修复方向

1. 排查 chunker 输出编码，确保 JSONL 文件以 UTF-8 写入
2. 验证 `_locate_chunks_by_quote()` 在编码修复后能否正确匹配
3. 为审查脚本添加页码信息展示
4. 考虑是否需要恢复 chunk 级策略以获得更精确的定位

---

## 关联 Issue

- BUG-025：`source_chunks` 字段始终为空
- FEAT-035：元数据增强（页码 + 标题层级）
- FEAT-039：交互式审查脚本
