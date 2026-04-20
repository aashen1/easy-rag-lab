# 评测系统验收修复报告

<!-- status: active -->

> 发现日期: 2026-04-20
> 修复日期: 2026-04-20

---

## 一、问题概述

对上一轮评测系统修复（`eval-metrics-bugfix.md`）进行验收时，发现以下遗留和新引入的问题：

| 问题 | 严重程度 | 来源 | 影响范围 |
|------|----------|------|----------|
| filter_valid_questions 设计方向错误 | 严重 | 上轮修复引入 | 评测逻辑、问题生成 |
| irrelevant 问题 source_files 设置错误 | 严重 | 原始设计缺陷 | 所有包含无关问题的实验 |
| config_snapshot 信息不完整 | 重要 | 原始设计缺陷 | 实验可复现性 |
| 通用配置与实验配置杂糅 | 重要 | 原始设计缺陷 | 实验对比的清晰度 |
| 报告配置渲染不直观 | 中等 | 原始设计缺陷 | 报告可读性 |

---

## 二、问题详情与修复

### 2.1 filter_valid_questions 设计方向错误

#### 现象

上轮修复新增了 `validate_question()` 和 `filter_valid_questions()` 函数，用于在评测时过滤掉"期望源不在语料库中"的问题。但：

1. **实际未集成**：`run_eval.py` 和 `run_experiment.py` 都没有调用这些函数，等于是摆设
2. **方向错误**：过滤问题会导致评测使用的问题数低于预期，影响统计显著性

#### 根因分析

经过对问题生成流程的完整追踪，发现：

- **正常问题类型**（single_fact/multi_fact/reasoning/comparative）：`_load_full_documents()` 通过 `meal_config.pdf_files` 过滤文档，只加载属于 meal 的文档 → 生成的 `source_files` 一定属于 meal → **不存在"生成的问题不在 meal 中"的问题**
- **irrelevant 类型**（5%占比）：故意与文档主题无关，测试拒答能力 → 但 `source_files` 仍被设为 `[source_path]` → **这才是真正的 Bug**
- **missing 类型**（10%占比）：询问文档中没有的信息 → `source_files` 保留是合理的（文档主题相关），但需要标记"不期望有答案"

#### 修复方案

**核心思路**：不是"过滤无效问题"，而是"让问题生成时就正确设置 source_files"

| 问题类型 | 修复前 source_files | 修复后 source_files | 新增标记 |
|----------|--------------------|--------------------|---------|
| single_fact | `[source_path]` | `[source_path]` | — |
| multi_fact | `[source_path]` | `[source_path]` | — |
| reasoning | `[source_path]` | `[source_path]` | — |
| comparative | `[source_path]` | `[source_path]` | — |
| missing | `[source_path]` | `[source_path]` | `expect_no_answer=True` |
| irrelevant | `[source_path]` | `[]` | `expect_retrieval=False` |

**代码变更**：

```python
# src/test_generator.py - generate_document_based_questions()

# 修复前
qa["source_files"] = [source_path]
qa["category"] = "document"

# 修复后
if q_type == "irrelevant":
    qa["source_files"] = []
    qa["expect_retrieval"] = False
elif q_type == "missing":
    qa["source_files"] = [source_path]
    qa["expect_no_answer"] = True
else:
    qa["source_files"] = [source_path]
```

**评测流程变更**：

```python
# eval/run_experiment.py - evaluate_test_set()

# 修复前：对所有问题计算检索指标
hit_rate = calculate_hit_rate(retrieved_sources, expected_sources)
mrr = calculate_mrr(retrieved_sources, expected_sources)
ndcg = calculate_ndcg(retrieved_sources, expected_sources, k=5)

# 修复后：跳过不适用检索指标的问题
if expect_retrieval and expected_sources:
    hit_rate = calculate_hit_rate(retrieved_sources, expected_sources)
    mrr = calculate_mrr(retrieved_sources, expected_sources)
    ndcg = calculate_ndcg(retrieved_sources, expected_sources, k=5)
else:
    hit_rate = None
    mrr = None
    ndcg = None
```

**聚合指标变更**：

```python
# eval/run_experiment.py - compute_aggregate_metrics()

# 修复前
valid_results = [r for r in results if "retrieval" in r]

# 修复后：区分"有检索结果"和"不适用检索指标"
retrieval_results = [r for r in results if r.get("retrieval") is not None]
metrics["retrieval_applicable_questions"] = len(retrieval_results)
metrics["total_questions"] = len(results)
```

**删除的代码**：

- `eval/metrics.py`：删除 `QuestionValidity`、`validate_question()`、`filter_valid_questions()`
- `tests/test_metrics.py`：删除 `TestValidateQuestion`（6 个测试）、`TestFilterValidQuestions`（5 个测试）

---

### 2.2 config_snapshot 信息不完整

#### 现象

实验报告目录下的 `config_snapshot.yaml` 只包含 `data`、`evaluation`、`llm`、`test_sets` 四个字段，完全没有技术选型信息。变体级快照只包含 `chunker`、`embedding`、`retrieval` 三个段落，缺少 `parser`、`vector_store`、`llm_presets` 等。

用户阅读报告时无法确定实验使用了哪些技术选型，容易造成误解。

#### 修复方案

**实验级 config_snapshot**：增加 `system_config` 字段，保存完整的基线配置

```python
# 修复前
config_snapshot = {
    "data": exp_config.data,
    "test_sets": exp_config.test_sets,
    "evaluation": exp_config.evaluation,
    "llm": exp_config.llm,
}

# 修复后
config_snapshot = {
    "data": exp_config.data,
    "test_sets": exp_config.test_sets,
    "evaluation": exp_config.evaluation,
    "llm": exp_config.llm,
    "system_config": sanitize_config(system_config),
}
```

**变体级 config_snapshot**：保存完整的 merged_config

```python
# 修复前
"merged": {
    "chunker": merged_config.get("chunker", {}),
    "embedding": merged_config.get("embedding", {}),
    "retrieval": merged_config.get("retrieval", {}),
}

# 修复后
"merged": sanitize_config(merged_config)
```

**脱敏处理**：新增 `sanitize_config()` 函数，将所有 `api_key` 替换为 `***`

---

### 2.3 通用配置与实验配置杂糅

#### 现象

`config.yaml` 中包含 bm25/hybrid/reranker/query_rewrite 等高级功能的参数配置，虽然默认关闭（`enabled: false`），但用户容易误以为这些功能默认开启。做对比实验时，不清楚基线到底用了哪些技术。

#### 根因

功能上没有问题（默认值确实是关闭的），问题在于**认知上的混淆**——缺少明确的声明说明这是最小基线。

#### 修复方案

1. **config.yaml 增加顶部注释**：明确声明"最小基线"原则，说明 RAG 管线流程，给出通过 config_overrides 开启高级功能的示例
2. **检索配置子段落增加中文注释**：说明各功能何时生效
3. **实验报告增加"Technology Summary"**：在配置详情前，用简洁列表展示技术选型

**Technology Summary 示例**：

```
Technology Summary:
- Retrieval: Vector (dense)
- Top-K: 5
- Reranker: Disabled
- Query Rewrite: Disabled
- Chunking: fixed (size=512, overlap=0)
- Embedding: BAAI/bge-large-zh-v1.5
- Vector Store: qdrant (Cosine)
```

---

### 2.4 报告配置渲染不直观

#### 现象

实验报告中配置段落的嵌套字典被渲染为 Python dict 字符串（如 `{'enabled': False, 'model_name': 'BAAI/bge-reranker-large'}`），只支持 2 层嵌套。

#### 修复方案

新增 `_dict_to_yaml_lines()` 方法，支持任意深度嵌套的 YAML 格式渲染：

```python
# 修复前（2 层限制）
for section, config in merged.items():
    lines.append(f"{section}:")
    if isinstance(config, dict):
        for k, v in config.items():
            lines.append(f"  {k}: {v}")  # 嵌套 dict 显示为字符串

# 修复后（任意深度）
lines.extend(self._dict_to_yaml_lines(merged))
```

---

## 三、修复前后对比

### 3.1 问题类型处理对比

| 问题类型 | 修复前 | 修复后 |
|----------|--------|--------|
| irrelevant (5%) | source_files=[doc], 参与检索指标计算 → hit_rate=0 拉低整体 | source_files=[], 跳过检索指标 |
| missing (10%) | source_files=[doc], 正常计算 | source_files=[doc], expect_no_answer=True |
| 其他类型 (85%) | 正常 | 不变 |

### 3.2 config_snapshot 对比

| 内容 | 修复前 | 修复后 |
|------|--------|--------|
| 实验级 | data/evaluation/llm/test_sets | + system_config（完整基线配置） |
| 变体级 merged | chunker/embedding/retrieval | 完整 merged_config（所有段落） |
| api_key | 明文存储 | 脱敏为 *** |

### 3.3 报告展示对比

修复前：

```
Configuration:
```yaml
chunker:
  input_dir: data/parsed
  semantic: {'similarity_threshold': 0.5, ...}  ← 不直观
retrieval:
  reranker: {'enabled': False, ...}  ← 不直观
```

修复后：

```
Technology Summary:
- Retrieval: Vector (dense)
- Reranker: Disabled
- Chunking: fixed (size=512, overlap=0)

Configuration:
```yaml
chunker:
  input_dir: data/parsed
  semantic:
    similarity_threshold: 0.5  ← 正确缩进
retrieval:
  reranker:
    enabled: false  ← 正确缩进
```

---

## 四、新系统使用指南

### 4.1 问题类型的检索指标适用性

| 问题类型 | 检索指标 | 生成指标 | 说明 |
|----------|---------|---------|------|
| single_fact | 适用 | 适用 | 标准评测 |
| multi_fact | 适用 | 适用 | 标准评测 |
| reasoning | 适用 | 适用 | 标准评测 |
| comparative | 适用 | 适用 | 标准评测 |
| missing | 适用 | 适用（需关注拒答） | 测试"不知道"能力 |
| irrelevant | **不适用** | 适用（需关注拒答） | 测试拒答能力 |

### 4.2 聚合指标中的新字段

```python
metrics = compute_aggregate_metrics(results)
# 新增字段：
# - retrieval_applicable_questions: 参与检索指标计算的问题数
# - total_questions: 总问题数（含 irrelevant）
```

### 4.3 配置最小基线原则

`config.yaml` 定义 RAG 管线的最小基线：

```
PDF → MD → 固定长度无重叠切块 → 向量化 → 纯向量检索 → 生成回答
```

高级功能通过实验配置的 `config_overrides` 显式开启：

```yaml
# exp_configs/experiments/reranker_comparison.yaml
variants:
  - name: "no_rerank"
    description: "基线（无重排序）"
    config_overrides: {}  # 使用 config.yaml 默认值

  - name: "with_reranker"
    description: "开启重排序"
    config_overrides:
      retrieval:
        reranker:
          enabled: true
          model_name: "BAAI/bge-reranker-large"
          top_n: 3
```

---

## 五、相关提交记录

| 提交 | 说明 |
|------|------|
| `bed9fb3` | refactor: remove validate_question and filter_valid_questions from metrics |
| `eb6e665` | fix: correct source_files for irrelevant/missing question types |
| `069e763` | feat: save full merged config in experiment snapshots |
| `16c412f` | feat: add technology summary and improve YAML rendering in reports |
| `91675ed` | docs: clarify minimal baseline principle in config.yaml and template |

---

## 六、相关文档

- [评测指标 Bug 修复报告（上轮）](eval-metrics-bugfix.md)
- [评测指标详解](../guides/evaluation-metrics.md)
- [实验系统指南](../guides/experiment-system.md)
