# 评测粒度升级与虚高修复 Spec

## Why

基线 RAG 在 5kpage 数据集上的检索评测结果异常好（Hit Rate 0.9355, MRR 0.8251, NDCG 0.8591），排查发现根本原因是**评测粒度为文档级而非 chunk 级**——76 个文档被切成 9647 个 chunk，Top-5 检索只需命中同一文档的任意 chunk 即算成功，相当于"开卷考试只要求翻到正确的书，不要求翻到正确的页"。此外，irrelevant 问题被排除在指标之外、missing 问题评测逻辑不合理、同一文档多版本导致误判等问题也共同导致分数虚高或失真。

## What Changes

- **BREAKING**: 检索评测粒度从文档级升级为 chunk 级，新增 `source_chunks` ground truth
- **BREAKING**: pipeline.query() 返回值新增 `chunk_ids` 字段
- 新增 chunk 级匹配的 Hit Rate / MRR / NDCG 计算
- 新增文档去重后的检索指标（diversified metrics）
- 新增 irrelevant 问题的误检率指标（false_positive_rate）
- 修复 missing 类型问题的评测逻辑
- 新增文档版本等价组机制，解决"年报全文 vs 摘要"误判
- 保留文档级指标作为向后兼容的辅助指标

## Impact

- **Affected specs**: 评测系统、实验系统
- **Affected code**:
  - `src/pipeline.py` — query() 返回值新增 chunk_ids
  - `src/test_generator.py` — 文档级问题生成新增 source_chunks 定位
  - `eval/metrics.py` — 新增 chunk 级匹配、去重指标、误检率
  - `eval/run_eval.py` — 使用新指标
  - `eval/run_experiment.py` — 使用新指标，修复 missing/irrelevant 评测逻辑
  - `src/experiment.py` — 新增指标名注册
  - `config.yaml` — 新增 evaluation 配置项

---

## ADDED Requirements

### Requirement: Chunk 级 Ground Truth 定位

系统 SHALL 在文档级问题生成时，自动定位每个问题答案所在的 chunk ID 列表，记录为 `source_chunks`。

#### Scenario: 生成问题时自动定位答案 chunk

- **WHEN** 系统使用 `document` 策略生成问题
- **THEN** 每个问题的数据中应包含 `source_chunks` 字段，值为答案所在 chunk 的 chunk_id 列表
- **AND** `source_chunks` 的定位方式为：将 LLM 生成的 answer 与该文档的所有 chunk 文本进行内容匹配，找出包含答案关键信息的 chunk

#### Scenario: 答案跨 chunk 边界

- **WHEN** 答案信息分布在多个相邻 chunk 中
- **THEN** `source_chunks` 应包含所有涉及答案内容的 chunk ID
- **AND** 对于相邻 chunk（chunk_index 连续），应一并纳入

#### Scenario: irrelevant 类型问题

- **WHEN** 生成 irrelevant 类型问题
- **THEN** `source_chunks` 应为空列表 `[]`

#### Scenario: missing 类型问题

- **WHEN** 生成 missing 类型问题
- **THEN** `source_chunks` 应为空列表 `[]`（因为答案不在文档中）

### Requirement: Pipeline 返回 chunk_ids

系统 SHALL 在 pipeline.query() 的返回值中包含检索结果的 chunk_id 列表。

#### Scenario: 查询返回 chunk_ids

- **WHEN** 调用 pipeline.query(question) 并设置 return_contexts=True
- **THEN** 返回值中应包含 `chunk_ids` 字段，值为检索结果中每个 chunk 的 chunk_id 列表
- **AND** `chunk_ids` 的顺序与 `sources`、`contexts`、`scores` 一致

### Requirement: Chunk 级检索指标计算

系统 SHALL 提供 chunk 级粒度的检索指标计算函数。

#### Scenario: Chunk 级 Hit Rate

- **WHEN** 使用 chunk 级匹配计算 Hit Rate
- **THEN** 应检查检索结果的 chunk_ids 中是否包含 ground truth 中的任一 source_chunk
- **AND** 匹配时应支持相邻 chunk 容错：如果检索到的 chunk_index 与 ground truth chunk 的 chunk_index 差值 ≤ 1（同一文档内），也算命中

#### Scenario: Chunk 级 MRR

- **WHEN** 使用 chunk 级匹配计算 MRR
- **THEN** 应找到检索结果中第一个命中 ground truth chunk（含相邻容错）的位置，返回 1/rank

#### Scenario: Chunk 级 NDCG

- **WHEN** 使用 chunk 级匹配计算 NDCG
- **THEN** 应基于 chunk 级匹配计算 DCG 和 Ideal DCG
- **AND** 精确匹配的 chunk 相关性为 2，相邻容错匹配的相关性为 1

### Requirement: 文档去重检索指标（Diversified Metrics）

系统 SHALL 提供文档去重后的检索指标，以衡量检索结果的多样性。

#### Scenario: 计算去重 Hit Rate

- **WHEN** 计算文档去重后的 Hit Rate
- **THEN** 应先对检索结果按文档去重（每个文档只保留排名最高的 chunk），再计算文档级 Hit Rate

#### Scenario: 计算去重 MRR

- **WHEN** 计算文档去重后的 MRR
- **THEN** 应先对检索结果按文档去重，再计算文档级 MRR

#### Scenario: 计算去重 NDCG

- **WHEN** 计算文档去重后的 NDCG
- **THEN** 应先对检索结果按文档去重，再计算文档级 NDCG

### Requirement: Irrelevant 问题误检率指标

系统 SHALL 对 irrelevant 类型问题计算误检率（False Positive Rate）。

#### Scenario: 计算 irrelevant 问题的误检率

- **WHEN** 评测系统处理 irrelevant 类型问题
- **THEN** 应计算误检率 = 检索到的不相关文档数 / Top-K 检索结果数
- **AND** 由于 irrelevant 问题没有相关文档，所有检索到的文档均为不相关，因此 FPR = len(retrieved_sources) / k

#### Scenario: 聚合误检率

- **WHEN** 计算所有 irrelevant 问题的聚合误检率
- **THEN** 应取所有 irrelevant 问题误检率的平均值

### Requirement: Missing 问题评测逻辑修复

系统 SHALL 对 missing 类型问题采用正确的评测逻辑。

#### Scenario: Missing 问题不参与检索指标计算

- **WHEN** 评测系统处理 missing 类型问题
- **THEN** missing 问题不应参与 Hit Rate / MRR / NDCG 的计算
- **AND** 应设置 `expect_retrieval=False`

#### Scenario: Missing 问题单独统计

- **WHEN** 生成评测报告
- **THEN** 应单独统计 missing 类型问题的检索命中率和回答正确率

### Requirement: 文档版本等价组

系统 SHALL 支持将同一公司的多版本文档标记为等价，避免因文件名不同导致误判。

#### Scenario: 年报全文与摘要等价

- **WHEN** 检索结果中包含"中国建筑2023年年度报告.md"，而 ground truth 为"中国建筑2023年年度报告摘要.md"
- **THEN** 如果这两个文档属于同一等价组，应视为匹配成功

#### Scenario: 等价组的自动推断

- **WHEN** 系统构建 meal 时
- **THEN** 应自动推断等价组：提取文档路径中的公司名+年份，将同一公司同一年份的不同版本文档归入同一等价组
- **AND** 等价组信息存储在 meal_snapshot.json 中

#### Scenario: 等价组匹配优先级

- **WHEN** 进行文档级匹配时
- **THEN** 应先尝试精确匹配（stem 完全相同），再尝试等价组匹配
- **AND** 精确匹配的相关性分数高于等价组匹配

### Requirement: 评测指标配置扩展

系统 SHALL 支持配置使用哪种粒度的检索指标。

#### Scenario: 配置 chunk 级指标

- **WHEN** 用户在实验配置中指定 `retrieval_granularity: chunk`
- **THEN** 评测系统应使用 chunk 级匹配计算检索指标

#### Scenario: 配置文档级指标（向后兼容）

- **WHEN** 用户在实验配置中指定 `retrieval_granularity: document` 或未指定
- **THEN** 评测系统应使用文档级匹配计算检索指标（旧版行为）

#### Scenario: 同时计算两种粒度

- **WHEN** 用户在实验配置中指定 `retrieval_granularity: both`
- **THEN** 评测系统应同时计算 chunk 级和文档级指标，并在报告中分别展示

---

## MODIFIED Requirements

### Requirement: 评测报告格式

评测报告 SHALL 同时展示 chunk 级和文档级（含去重）的检索指标。

#### 原格式

```
| Variant | Hit Rate | MRR | NDCG |
```

#### 新格式

```
| Variant | Hit Rate (chunk) | Hit Rate (doc) | Hit Rate (dedup) | MRR (chunk) | MRR (doc) | NDCG (chunk) | NDCG (doc) | FPR | Questions |
```

### Requirement: 实验结果 JSON 格式

实验结果的 JSON SHALL 包含更丰富的检索评测信息。

#### 新增字段

```json
{
  "retrieval_metrics": {
    "avg_hit_rate": 0.9355,
    "avg_mrr": 0.8251,
    "avg_ndcg": 0.8591,
    "retrieval_applicable_questions": 93,
    "total_questions": 98,
    "avg_false_positive_rate": 0.0,
    "irrelevant_questions_count": 0
  },
  "chunk_level_metrics": {
    "avg_hit_rate": 0.55,
    "avg_mrr": 0.40,
    "avg_ndcg": 0.45,
    "retrieval_applicable_questions": 83
  },
  "dedup_metrics": {
    "avg_hit_rate": 0.80,
    "avg_mrr": 0.65,
    "avg_ndcg": 0.70
  }
}
```

### Requirement: 单条评测结果格式

每条评测结果 SHALL 包含 chunk 级和文档级的检索指标。

#### 新增字段

```json
{
  "id": "q001",
  "retrieval": {
    "hit_rate": 1.0,
    "mrr": 1.0,
    "ndcg": 1.0
  },
  "chunk_retrieval": {
    "hit_rate": 1.0,
    "mrr": 1.0,
    "ndcg": 1.0
  },
  "dedup_retrieval": {
    "hit_rate": 1.0,
    "mrr": 1.0,
    "ndcg": 1.0
  },
  "sources": [...],
  "chunk_ids": [...],
  "expected_sources": [...],
  "expected_chunks": [...]
}
```

---

## REMOVED Requirements

无移除的需求。旧的文档级指标保留作为向后兼容的辅助指标。
