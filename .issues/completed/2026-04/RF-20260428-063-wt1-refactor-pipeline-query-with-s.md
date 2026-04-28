---
id: RF-20260428-063-wt1
title: refactor-pipeline-query-with-strategy-pattern
type: RF
status: done
priority: medium
labels:
- refactor
- design-pattern
assignee: null
milestone: null
created_at: '2026-04-28T03:45:22.920588'
updated_at: '2026-04-28T03:45:22.920588'
source: active\RF-20260428-063-wt1-refactor-pipeline-query-with-s.md
legacy_id: null
---
## 重构目标

用策略模式重构 `RAGPipeline.query()` 方法，消除深层嵌套的 if-elif 控制流。

## 问题分析

当前 `pipeline.py:query()` 方法（L457-L605）存在严重的控制流问题：
- 三种检索路径（vector/bm25/hybrid）× 两种查询改写（hyde/multi_query）的分支组合
- multi_query 路径在方法中间就 `return`，跳过了后续的通用逻辑
- scores 计算逻辑重复（multi_query 分支和正常分支各写一遍）
- 嵌套 if-elif 达 4 层

具体代码路径：
1. 检查 query_rewriter → 如果是 multi_query → 循环检索 → 合并去重 → rerank → 生成答案 → **提前 return**
2. 否则 → 正常检索 → rerank → 生成答案 → return

两条路径的"rerank + 生成答案"逻辑几乎完全重复。

## 重构范围

`src/pipeline.py` 的 `query()` 方法

## 重构步骤

1. 定义检索策略基类 `RetrievalStrategy`，接口为 `retrieve(query, config) -> list[Result]`
2. 实现三个策略：
   - `VectorStrategy`：纯向量检索
   - `BM25Strategy`：纯 BM25 检索
   - `HybridStrategy`：混合检索
3. 定义查询改写策略基类 `QueryRewriteStrategy`，接口为 `rewrite(query) -> RewrittenQuery`
4. 实现：
   - `NoRewriteStrategy`：直接透传
   - `HyDEStrategy`：假设性文档嵌入
   - `MultiQueryStrategy`：多查询扩展（内含结果合并去重逻辑）
5. `query()` 方法简化为：rewrite → retrieve → rerank → generate
6. 移除提前 return，统一流程
7. 运行全量测试确保行为不变

## 验收标准

- `query()` 方法不超过 50 行
- 无嵌套超过 2 层的 if-elif
- 所有现有测试通过
- 新增策略只需实现接口，无需修改 `query()` 方法

## 更新记录

- 2026-04-28：创建
