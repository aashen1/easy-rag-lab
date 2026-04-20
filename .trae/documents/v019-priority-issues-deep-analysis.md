# v0.1.9 积压 Issue 优先推荐与深度分析

> 生成日期：2026-04-21
> 对齐版本目标：v0.1.9（透明报告 + 确认实验系统合理性 + 跑基线测试）

---

## 一、当前积压统计

| 类型 | 待处理 | 已延期 | 总计 |
|------|--------|--------|------|
| Bug | 1 | 2 | 3 |
| Feature | 9 | 0 | 9 |
| Refactor | 8 | 0 | 8 |
| Optimization | 4 | 0 | 4 |
| Investigation | 9 | 0 | 9 |

共 **31 条待处理** issue。

---

## 二、🔴 高优先级（v0.1.9 核心路径）

### 1. FEAT-014 — 透明版完整实验报告

**对齐 v0.1.9 第一项任务**："修改逻辑以生成完全透明的verbose版本实验报告"

**规模**：大 | **依赖**：无 | **紧迫性**：极高

#### 现状分析

当前实验报告系统（[experiment_reporter.py](file:///b:/project/w1-easy-rag/eval/experiment_reporter.py)）生成 8 章模板报告，但存在大量**数据流断点**——数据在管线中产生却在传递过程中丢失：

| 断点位置 | 丢失的数据 |
|----------|-----------|
| `pipeline.query()` → `_collect_rag_samples()` | `scores`（相似度分数）、`chunk_ids` |
| `_collect_rag_samples()` → `_evaluate_with_builtin()` | `contexts` 文本内容、`expected_sources`、`expected_answer` 未回写到 result |
| `BuiltinEvaluator.evaluate_single()` → result | `contexts`、`expected_sources`、`expected_answer`、`chunk_ids`、`expected_chunks` 构建结果字典时未写入 |
| 各指标计算函数 → 返回值 | faithfulness 的 statements/verdicts、context_precision 的 verdicts、answer_relevancy 的维度分数等中间产物全部丢弃，只返回最终浮点数 |

#### 需要补齐的透明性信息

**A. 核心可复现性（高优先）**

| 缺失信息 | 当前状态 | 修复方案 |
|----------|----------|----------|
| 检索到的 contexts 完整文本 | `_collect_rag_samples()` 采集了但未持久化 | 在 result 字典中增加 `retrieved_contexts` 字段 |
| 检索分数 (scores) | pipeline 返回了但未采集 | 在 `_collect_rag_samples()` 中采集 `response.get("scores", [])` |
| chunk_ids | pipeline 返回了但未采集 | 在 `_collect_rag_samples()` 中采集 `response.get("chunk_ids", [])` |
| 生成 Prompt | Generator 硬编码了 prompt 但未记录 | 在 result 中增加 `generation_prompt` 字段 |
| 期望答案 (expected_answer) | 采集了但未写入 result | 在 result 字典中增加 `expected_answer` 字段 |
| 期望来源 (expected_sources) | 采集了但未写入 result | 在 result 字典中增加 `expected_sources` 字段 |

**B. 指标计算过程透明性（中优先）**

| 缺失信息 | 修复方案 |
|----------|----------|
| Faithfulness 中间产物 | 修改 `calculate_faithfulness()` 返回 `statements` + `verdicts` |
| Context Precision 中间产物 | 修改 `_judge_context_relevance()` 返回 `verdict` + `reason` |
| Context Recall 中间产物 | 修改 `_can_infer_from_context()` 返回 `verdict` + `reason` |
| Answer Relevancy 中间产物 | 修改返回 `dimension_scores` + `reasoning` |
| Dedup 去重过程 | 暴露 `keep_indices` 和去重映射 |
| Chunk 匹配过程 | 记录精确匹配 vs 邻近匹配的判定 |

**C. 深度透明性（低优先）**

| 缺失信息 | 修复方案 |
|----------|----------|
| Embedding 向量 | retriever 返回 `query_embedding` |
| Query Rewrite 结果 | pipeline 记录改写前后文本 |
| Rerank 过程 | 记录 rerank 前后排序和分数 |
| LLM 评估 Prompt | 随结果保存实际 prompt |
| LLM 评估原始响应 | 保存 LLM 返回的原始文本 |

#### 建议实施路径

1. **Phase 1**：修复数据流断点，确保 `_collect_rag_samples()` 采集所有可用数据并写入 result
2. **Phase 2**：修改指标计算函数，返回中间产物（statements、verdicts、维度分数）
3. **Phase 3**：新增 verbose 报告模板，逐问题展示完整信息链
4. **Phase 4**：深度透明性（embedding、rerank 等）

---

### 2. INV-007 — 评测系统可靠性全面审查

**对齐 v0.1.9 第二项任务**："确认目前的exp系统能生成合理的结果"

**规模**：中 | **依赖**：FEAT-014（透明报告是审查的前提） | **紧迫性**：极高

#### 已发现的致命级 Bug

**contexts/sources 混淆**（[run_experiment.py:861](file:///b:/project/w1-easy-rag/eval/run_experiment.py#L861)）：

```python
eval_result = evaluator.evaluate_single(
    contexts=sample.get("retrieved_sources", []),  # ← 传的是来源路径！不是文本内容
)
```

而 `sample` 中：
- `contexts` = chunk 文本内容列表（正确）
- `retrieved_sources` = 来源路径列表（如 `research_reports\2026年光伏行业分析.md`）

**影响**：

| 指标 | 影响 |
|------|------|
| hit_rate / mrr / ndcg | 无影响（检索指标恰好需要路径） |
| **faithfulness** | **完全失效**——LLM 被要求判断"答案陈述是否能从文件路径推导出来" |
| **context_precision** | **部分失效**——LLM 判断"文件路径是否与问题相关" |
| **context_recall** | **部分失效**——同上 |
| answer_relevancy | 无影响（不需要 contexts） |

#### 自评偏差问题

当前系统**用同一个 LLM 生成答案并评估答案**，存在系统性偏差：
- Faithfulness 自评偏差：LLM 倾向于认为自己的输出是忠实的
- Answer Relevancy 自评偏差：LLM 倾向于给自己的回答打高分
- 缺少缓解措施：未使用不同模型评估、未多次评估取平均、未与人工标注对比校准

#### 其他可靠性问题

| 问题 | 严重性 | 说明 |
|------|--------|------|
| expected_sources 标注错误 | 高 | 问题基于整篇文档生成，但 LLM 生成的问题可能涉及文档中提到的其他公司 |
| expected_chunks 定位粗糙 | 高 | `_locate_answer_chunks()` 使用关键词+子串重叠的启发式方法，可能遗漏或误匹配 |
| chunk_ids/expected_chunks 未传递 | 高 | `_evaluate_with_builtin()` 未传 `chunk_ids` 和 `expected_chunks`，导致 chunk 级指标实际不计算 |
| LLM 评估指标不稳定 | 中 | 评估结果不可复现 |
| chunk_id 解析脆弱 | 中 | `_parse_chunk_id()` 使用 `rfind("_")`，文件名含下划线时可能解析错误 |

#### 建议实施路径

1. **立即修复** contexts/sources 混淆 Bug
2. **立即修复** `_evaluate_with_builtin()` 未传递 chunk_ids/expected_chunks 的问题
3. 从一个 PDF + 一个问题开始精调，验证全链路数据正确性
4. 引入评估模型与生成模型分离的配置选项
5. 对 golden_qa 中的 expected_sources 进行人工校验

---

### 3. INV-006 — golden test 是否基于老策略

**对齐 v0.1.9 第三项任务**：跑基线测试前必须确认测试集本身是否有效

**规模**：小（纯调查） | **依赖**：无 | **紧迫性**：高

#### 调查结论

**golden_qa.json 基于旧策略（chunk-based），确认需要重做。**

证据：
1. `category` 字段使用 `factual`/`boundary`/`multi_hop`——这是旧策略的三种分类
2. 不包含新策略的 `question_type`、`source_files`、`source_chunks`、`answer` 等字段
3. golden_qa.json 不是 TestSetManager 管理的格式——它是独立的 fixture 文件（纯数组）
4. 新策略使用 6 种类型：`single_fact`/`multi_fact`/`reasoning`/`comparative`/`missing`/`irrelevant`

**两套系统完全独立**：
- `tests/fixtures/golden_qa.json` → 用于 `tests/test_regression.py` 的回归测试
- TestSetManager 管理的 JSON → 用于 `eval/run_experiment.py` 的实验评测

**当前状态**：`data/meals/*/test_sets/` 下无任何 JSON 文件，说明还没有通过 TestSetManager 生成并持久化的测试集。

#### 建议行动

1. 使用新策略（document-based）重新生成 golden_qa.json，覆盖 6 种问题类型
2. 将 golden_qa.json 迁移为 TestSetManager 管理的格式（带 metadata/quality_metrics/questions 三层结构）
3. 确保新 golden test 的 `source_files` 与当前 Meal 的 PDF 列表一致
4. 更新 `tests/test_regression.py` 以适配新格式

---

## 三、🟡 中优先级（提升系统质量）

### 4. INV-001 — 实验报告 sources 字段细化到标题头或 chunk

**规模**：小-中 | **依赖**：FEAT-006 已完成，可独立推进

#### 虚高根因

当前 `source_files` 始终是 `[source_path]`（文档级路径），导致：
- 76 个 PDF → 9647 个 chunk，平均每文档约 127 个 chunk
- Top-5 检索只需命中同一文档的**任意** chunk 即算成功
- 类比："开卷考试只要求翻到正确的书，不要求翻到正确的页"

#### 已有但未集成的修复

| 已实现 | 未完成 |
|--------|--------|
| chunk 级指标函数（`chunk.py`） | `_evaluate_with_builtin()` 未传 `chunk_ids`/`expected_chunks` |
| dedup 指标函数（`dedup.py`） | `_collect_rag_samples()` 未采集 `chunk_ids` |
| pipeline 返回 `chunk_ids` | sample 字典中无 `chunk_ids` 字段 |
| `_locate_answer_chunks()` 定位 | 定位使用启发式方法，可能不准 |

#### 建议行动

1. 修复 `_collect_rag_samples()` 和 `_evaluate_with_builtin()` 的参数传递（与 INV-007 重叠）
2. 改进 `_locate_answer_chunks()` 的定位精度
3. 在实验报告中展示 chunk 级指标，与文档级指标并列对比

---

### 5. RF-004 — 硬编码配置值提取到 config.yaml

**规模**：中 | **依赖**：无

#### 硬编码审计结果

**eval/metrics/ 目录**（最严重）：

| 文件 | 硬编码项 | 数量 |
|------|----------|------|
| generation.py | model_name、base_url、max_tokens、temperature | 12 处 |
| llm_retrieval.py | model_name、base_url、max_tokens、temperature | 8 处 |
| experiment_reporter.py | fallback model_name、max_tokens、temperature、base_url | 5 处 |
| test_generator.py | temperature、max_tokens、截断长度、TYPE_DISTRIBUTION | 11 处 |
| chunk.py / dedup.py / fpr.py / retrieval.py | k=5、adjacent_tolerance=1 | 10 处 |

**config.yaml 中已有但未被引用的配置**：

| 配置路径 | 被硬编码覆盖 |
|----------|-------------|
| `llm_presets.default.model_name` | eval/metrics 中的 `"LongCat-Flash-Lite"` |
| `llm_presets.default.base_url` | eval/metrics 中的 `"https://api.longcat.chat/anthropic"` |
| `llm_presets.default.temperature` | test_generator 中的 `0.7` |
| `retrieval.top_k` | eval/metrics 中多处 `k=5` |

**config.yaml 中完全缺失的配置项**：

1. 评测 LLM 配置（`evaluation.llm`）——评测指标使用的模型名、base_url、各步骤的 max_tokens/temperature
2. 报告生成 LLM 配置（`evaluation.report_llm`）——max_tokens=4096、temperature=0.3
3. 测试生成 LLM 参数（`test_generation.llm_params`）——temperature=0.7、max_tokens=512/1024、文档截断长度=8000
4. 评测指标算法参数（`evaluation.metrics`）——k=5、adjacent_tolerance=1、term_threshold=2、overlap_threshold=0.5
5. test_generator 的 TYPE_DISTRIBUTION 类变量与 config.yaml 重复但代码使用类变量

#### 建议实施路径

1. 在 config.yaml 新增 `evaluation.llm` 和 `evaluation.report_llm` 配置节
2. 修改 eval/metrics/ 中所有函数从配置读取 LLM 参数（保留默认值 fallback）
3. 修改 test_generator.py 使用配置中的 TYPE_DISTRIBUTION 而非类变量
4. 统一 `k` 值引用 `retrieval.top_k`

---

### 6. RF-012 — 旧格式 test_sets DeprecationWarning 清理

**规模**：小 | **依赖**：无 | **可顺手做**

当前测试中有大量旧格式警告，这是向后兼容的预期行为，但后续版本应逐步清理。建议在完成 INV-006（golden test 重做）后一并处理。

---

## 四、🟢 低优先级（可后续版本处理）

### 7. FEAT-011 — 补做 LLM 报告功能

**规模**：小 | **实用性**：高

实验跑完后补生成 LLM 总结报告。当前 `generate_markdown_report()` 支持 `mode="llm"` 但需要在实验运行时指定。建议增加独立的 `--llm-report` 命令行参数，可对已有实验结果补做。

### 8. OPT-003 — 问题生成 token 消耗优化

**规模**：中 | **建议**：等基线确认后再优化

每问题 5-6k token，主因是每次输入完整 MD 文档。可考虑：
- 缓存已输入的 MD 文档，仅发送增量部分
- 使用更短的 prompt 模板
- 分批发送，复用 context

### 9. INV-012 — 测试体系深度审查（883条是否过多）

**规模**：中 | **建议**：重要但不紧急

883 条测试项对于一个学习型 RAG 项目确实偏多。建议：
- 排查重复测试（同逻辑不同参数的参数化测试是否过度）
- 排查无意义测试（测试框架本身而非业务逻辑）
- 评估集成测试的必要性（当前 182s 偏长）

### 10. FEAT-019 — .trae 目录归档机制

**规模**：中 | **建议**：打扫卫生时顺手做

本次打扫卫生已手动归档了 7 个文档 + 1 个 spec。建议沉淀为 skill 或脚本，在每次发版后自动触发。

---

## 五、❌ 不推荐现在做的

| Issue ID | 描述 | 不推荐原因 |
|----------|------|-----------|
| FEAT-012 | 断点续传（实验中断恢复） | 规模大，依赖 v0.1.9 基线确认 |
| FEAT-013 | 部分评测支持 | 规模大，依赖 v0.1.9 基线确认 |
| FEAT-015 | 更细粒度实验记录 | 规模中，与 FEAT-014 透明报告有重叠，等 FEAT-014 完成后再评估 |
| INV-009 | 问题集扩大与指标收敛 | 明确依赖 v0.1.9 发版 |
| INV-002 | 问题生成策略可扩展性 | 依赖黄金测试集落地 |
| FEAT-017 | CI/CD 集成 | 开源准备，不急 |
| INV-011 | 开源许可证评估 | 开源准备，不急 |
| FEAT-008 | test-future-directions 剩余方向 | 依赖测试体系审查（INV-012） |

---

## 六、推荐实施顺序

```
Phase 0: 致命 Bug 修复（INV-007 的紧急部分）
  ├─ 修复 contexts/sources 混淆
  └─ 修复 _evaluate_with_builtin() 参数传递

Phase 1: 透明报告基础（FEAT-014 Phase 1-2）
  ├─ 修复数据流断点
  └─ 修改指标函数返回中间产物

Phase 2: 测试集重建（INV-006）
  ├─ 用新策略重做 golden_qa.json
  └─ 迁移为 TestSetManager 格式

Phase 3: 全链路精调（INV-007 完整审查 + INV-001）
  ├─ 一个 PDF + 一个问题走完全链路
  ├─ 校验 expected_sources 标注
  └─ 验证 chunk 级指标计算

Phase 4: 代码质量（RF-004 + RF-012）
  ├─ 硬编码配置提取
  └─ 旧格式警告清理

Phase 5: 跑基线测试
  └─ 生成 v0.1.9 的透明版基线实验报告
```

---

## 七、Issue 间依赖关系图

```
FEAT-014 (透明报告)
    ↓
INV-007 (评测可靠性) ←── INV-001 (sources 细化)
    ↓                       ↑
INV-006 (golden test) ──────┘
    ↓
RF-004 (硬编码提取) ←── RF-012 (警告清理)
    ↓
基线测试
```
