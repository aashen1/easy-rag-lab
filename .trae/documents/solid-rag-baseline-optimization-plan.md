# RAG 基线实验优化计划书

> 目标：产出一份数据扎实、方法论严谨、经得起面试官深挖的 RAG 基线实验报告

---

## 一、现状诊断

### 1.1 当前基线结果（exp_20260423_065942）

| 指标 | 值 | 状态 |
|------|-----|------|
| Hit Rate (doc) | 0.8421 | ✅ 正常 |
| MRR (doc) | 0.7211 | ✅ 正常 |
| NDCG (doc) | 0.7539 | ✅ 正常 |
| Faithfulness | 0.8260 | ✅ 正常 |
| Answer Relevancy | 0.8710 | ✅ 正常 |
| Hit Rate (chunk) | null | ❌ 缺失 |
| MRR (chunk) | null | ❌ 缺失 |
| NDCG (chunk) | null | ❌ 缺失 |
| Dedup 指标 | null | ❌ 缺失 |
| FPR | null | ❌ 缺失 |
| Context Precision | 未启用 | ❌ 缺失 |
| Context Recall | 未启用 | ❌ 缺失 |

### 1.2 关键缺陷清单

| # | 缺陷 | 严重度 | 影响 |
|---|------|--------|------|
| D1 | `source_chunks` 全部为空 → chunk 级指标全部 null | 🔴 高 | 无法评估 chunk 级检索精度 |
| D2 | FPR 未计算（irrelevant 问题未被正确识别） | 🔴 高 | 无法评估误检率 |
| D3 | missing 类型问题的检索指标盲区 | 🟡 中 | 10% 的题目无任何检索评估 |
| D4 | 测试集仅 20 题，统计效力不足 | 🔴 高 | 无法得出可靠结论 |
| D5 | 无按问题类型的指标分解 | 🟡 中 | 无法定位短板 |
| D6 | 变体描述 bug：写 `chunk_overlap: 0` 实际是 64 | 🟡 中 | 误导读者 |
| D7 | 检索结果缺乏文档级多样性 | 🟡 中 | 5 个结果常来自同一文档 |
| D8 | 无置信区间 / 统计显著性 | 🔴 高 | 面试官一问就倒 |
| D9 | Context Precision/Recall 未启用 | 🟡 中 | 缺少 LLM 判定的检索质量维度 |
| D10 | 生成环节无反幻觉约束 | 🟡 中 | q001 出现 0.0 faithfulness |

### 1.3 面试官可能的质疑点

1. **"你的 Hit Rate 84% 是文档级的，chunk 级呢？"** → 当前无法回答
2. **"20 个问题够吗？置信区间多少？"** → 当前无法回答
3. **"无关问题误检率多少？"** → 当前无法回答
4. **"missing 类型问题检索到了相关文档但回答不了，怎么评估？"** → 当前是盲区
5. **"5 个检索结果全来自同一文档，这合理吗？"** → 当前无多样性控制
6. **"faithfulness 0.83 是怎么算的？LLM 评判的可靠性如何？"** → 需要说明
7. **"你的 baseline 配置到底 overlap 是 0 还是 64？"** → 描述有 bug

---

## 二、优化方案

### Phase 1：修复断裂的指标链路（让所有指标都能产出）

#### 1.1 修复 source_chunks 为空的问题

**根因**：`_locate_answer_chunks()` 方法存在三个问题：
- `chunks_dir` 路径与 ArtifactCache 实际存储结构不匹配
- `source_path` 格式（`.md`）与 chunk metadata.source 格式（`.pages.json`）不一致
- 启发式匹配阈值过严（`term_threshold=3`, `overlap_threshold=0.7`）

**修复方案**：
1. 修改 `_locate_answer_chunks()` 使用 ArtifactCache 解析 chunks_dir
2. 统一 source_path 的格式匹配：使用 `normalize_source()` 做模糊匹配，而非精确字符串比较
3. 降低匹配阈值：`term_threshold=2`, `overlap_threshold=0.5`
4. 启用 `adjacent_tolerance=1`，允许匹配相邻 chunk

**涉及文件**：
- `src/test_generator.py` — `_locate_answer_chunks()`, `_chunk_matches_answer()`

**验证**：重新生成测试集，确认 source_chunks 非空率 > 80%

#### 1.2 修复 FPR 未计算的问题

**根因**：`BuiltinEvaluator.evaluate_single()` 中 FPR 的计算条件是 `not expect_retrieval and not expected_sources`，但 irrelevant 类型问题虽然 `expect_retrieval=False`，如果 `source_files` 不为空则不满足条件。当前 irrelevant 类型的 `source_files=[]`，理论上应该能计算 FPR，但需要确认 `expected_sources` 在评估时是否也为空。

**修复方案**：
1. 在 `eval/run_experiment.py` 的 `_collect_rag_samples()` 中，确保 irrelevant 问题的 `expected_sources` 传递为空列表
2. 在 `BuiltinEvaluator.evaluate_single()` 中，增加日志确认 FPR 计算路径被触发
3. 在实验配置的 metrics.retrieval 中显式添加 `"false_positive_rate"`

**涉及文件**：
- `eval/evaluators/builtin_evaluator.py`
- `eval/run_experiment.py`

#### 1.3 修复 missing 类型的检索指标盲区

**当前行为**：missing 问题有 `source_files=[source_path]` 但 `expect_retrieval=False`，导致既不计算常规检索指标也不计算 FPR。

**修复方案**：missing 类型问题应该评估"检索是否找到了相关文档"——期望检索成功但答案应说明"文档未提及"。新增一个 `retrieval_success_for_missing` 指标：
- 如果检索到了 source_files 中的文档 → 1.0（检索成功）
- 如果没检索到 → 0.0（检索失败）
- 同时检查答案是否正确声明了"无法回答"

**涉及文件**：
- `eval/metrics/retrieval.py` — 新增 `calculate_missing_retrieval_success()`
- `eval/evaluators/builtin_evaluator.py` — 集成新指标

#### 1.4 修复变体描述 bug

**修复方案**：在 `exp_configs/baseline/baseline_10percent.yaml` 和实验报告生成逻辑中，确保 description 反映实际配置（`chunk_overlap: 64`）。

**涉及文件**：
- `exp_configs/baseline/baseline_10percent.yaml`

---

### Phase 2：提升测试集质量（从 20 题到 50 题，增加统计效力）

#### 2.1 扩大测试集规模

**当前**：20 题 / 21 个 PDF（10% 采样）
**目标**：50 题 / 更大采样

**理由**：
- 20 题的 95% 置信区间约为 ±19%（p=0.84 时），太宽
- 50 题的 95% 置信区间约为 ±10%，勉强可接受
- 100 题的 95% 置信区间约为 ±7%，比较 solid

**方案**：
- 采样比例从 10% 提升到 20%（约 42 个 PDF）
- 问题数量设为 50
- 类型分布保持不变

#### 2.2 优化问题类型分布

**当前分布**：
```
single_fact: 30%, multi_fact: 25%, reasoning: 15%, comparative: 15%, missing: 10%, irrelevant: 5%
```

**问题**：irrelevant 只有 5%（50 题中仅 2-3 题），FPR 估计极不稳定。

**调整方案**：
```
single_fact: 25%, multi_fact: 20%, reasoning: 15%, comparative: 15%, missing: 10%, irrelevant: 15%
```

将 irrelevant 提升到 15%（约 7-8 题），使 FPR 估计更可靠。同时减少 single_fact 和 multi_fact 各 5%，因为这两种类型已经足够代表。

#### 2.3 增加测试集种子固定和可复现性

**方案**：
- 在实验配置中显式指定 `seed: 42`
- 确保相同 seed + 相同 meal → 相同测试集（当前已支持）
- 在实验报告中记录 seed 值

---

### Phase 3：丰富评估维度（让指标体系无死角）

#### 3.1 启用 Context Precision 和 Context Recall

**当前**：这两个 LLM 判定的检索指标已实现但未启用。

**方案**：在实验配置的 metrics.retrieval 中添加：
```yaml
metrics:
  retrieval:
    - hit_rate
    - mrr
    - ndcg
    - context_precision
    - context_recall
  generation:
    - faithfulness
    - answer_relevancy
```

**注意**：这两个指标需要额外 LLM 调用，会增加成本和耗时。50 题约需额外 100 次 LLM 调用。

#### 3.2 启用 Dedup 指标

**当前**：dedup 指标已实现但未产出结果。

**方案**：确认 dedup 指标的计算条件（需要 `expected_sources` 非空且 `expect_retrieval=True`），在 metrics.retrieval 中添加：
```yaml
metrics:
  retrieval:
    - hit_rate
    - mrr
    - ndcg
    - dedup_hit_rate
    - dedup_mrr
    - dedup_ndcg
```

#### 3.3 新增按问题类型的指标分解

**当前**：聚合指标只有全局平均值，无法看出不同类型问题的表现差异。

**方案**：在 `compute_aggregate_metrics()` 中增加按 `question_type` / `difficulty` 分组的指标计算，输出到结果 JSON 和实验报告中。

**涉及文件**：
- `eval/run_experiment.py` — `compute_aggregate_metrics()`
- `eval/reporter.py` — 报告模板

#### 3.4 新增置信区间计算

**方案**：对每个指标计算 Wilson 置信区间（适用于二值/比例指标）或 Bootstrap 置信区间（适用于连续指标）。

**实现**：
```python
def compute_confidence_interval(values: list[float], confidence: float = 0.95) -> tuple[float, float]:
    """Bootstrap 置信区间"""
    n_bootstrap = 1000
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = random.choices(values, k=len(values))
        bootstrap_means.append(statistics.mean(sample))
    lower = np.percentile(bootstrap_means, (1 - confidence) / 2 * 100)
    upper = np.percentile(bootstrap_means, (1 + confidence) / 2 * 100)
    return lower, upper
```

**涉及文件**：
- `eval/run_experiment.py` — `compute_aggregate_metrics()`

---

### Phase 4：增强生成环节的反幻觉能力

#### 4.1 优化 System Prompt

**当前**：使用硬编码的默认 system prompt，无明确的反幻觉指令。

**方案**：在 `generation.system_prompt` 中添加反幻觉约束：
```
你是一个金融研报问答助手。请严格基于提供的参考资料回答问题。

规则：
1. 只使用参考资料中明确提及的信息
2. 如果参考资料中没有足够信息回答问题，请明确说明"根据提供的资料，无法回答该问题"
3. 不要编造、推测或使用外部知识补充答案
4. 引用数据时，必须与参考资料中的数字完全一致
5. 回答时注明信息来源（如"根据参考资料2"）
```

**涉及文件**：
- `config.yaml` — `generation.system_prompt`
- 或 `src/generator.py` — 默认 system prompt

#### 4.2 添加生成答案与参考答案的对比指标

**方案**：对于测试集中有参考答案的问题，计算 ROUGE-L 或 BERTScore 作为辅助参考指标。这不是主要指标，但可以作为 faithfulness 的交叉验证。

**优先级**：低，如果时间允许再实现。

---

### Phase 5：运行 Solid 基线实验

#### 5.1 实验配置

```yaml
name: "solid_baseline_v1"
description: "Solid基线实验 - 50题全指标评估，chunk_size=512, chunk_overlap=64"

data:
  meal: "m_solid_baseline"
  create_if_missing:
    sample_ratio: 0.2
    seed: 42

test_sets:
  - name: "solid_baseline_q50"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 50
      seed: 42
      type_distribution:
        single_fact: 0.25
        multi_fact: 0.20
        reasoning: 0.15
        comparative: 0.15
        missing: 0.10
        irrelevant: 0.15

variants:
  - name: "baseline"
    description: "基线配置 (chunk_size: 512, chunk_overlap: 64, top_k: 5)"
    config_overrides: {}

evaluation:
  llm_preset: "default"
  llm_report: true
  metrics:
    retrieval:
      - hit_rate
      - mrr
      - ndcg
      - dedup_hit_rate
      - dedup_mrr
      - dedup_ndcg
      - false_positive_rate
      - context_precision
      - context_recall
    generation:
      - faithfulness
      - answer_relevancy

llm:
  question_generation: "default"
  answering: "default"
```

#### 5.2 预期产出指标

| 维度 | 指标 | 预期状态 |
|------|------|---------|
| 文档级检索 | Hit Rate, MRR, NDCG | ✅ 有值 |
| Chunk 级检索 | chunk_hit_rate, chunk_mrr, chunk_ndcg | ✅ 有值（Phase 1 修复后） |
| 去重检索 | dedup_hit_rate, dedup_mrr, dedup_ndcg | ✅ 有值 |
| 误检率 | FPR | ✅ 有值（irrelevant 15% 保证） |
| LLM 检索质量 | Context Precision, Context Recall | ✅ 有值 |
| 生成忠实度 | Faithfulness | ✅ 有值 |
| 生成相关性 | Answer Relevancy | ✅ 有值 |
| 缺失知识检索 | missing_retrieval_success | ✅ 有值（Phase 1 新增） |
| 统计 | 95% 置信区间 | ✅ 有值（Phase 3 新增） |
| 分解 | 按问题类型的指标分解 | ✅ 有值（Phase 3 新增） |

---

### Phase 6：撰写面试级分析报告

#### 6.1 报告结构

```
1. 实验设计
   1.1 评估框架选型理由（为什么自建不用 RAGAS）
   1.2 指标体系设计（每个指标的含义、计算方式、选型理由）
   1.3 测试集构建方法论（问题类型分布、采样策略、质量管控）
   1.4 基线配置说明（每个参数的选择理由）

2. 实验结果
   2.1 全局指标汇总（含置信区间）
   2.2 按问题类型分解
   2.3 按难度分解
   2.4 检索 vs 生成质量关联分析
   2.5 逐题 Bad Case 分析

3. 深度分析
   3.1 检索失败根因分类（语义漂移 / 术语不匹配 / 文档缺失）
   3.2 幻觉类型分析（数据捏造 / 过度推断 / 来源混淆）
   3.3 Chunk 级 vs 文档级检索精度对比
   3.4 上下文利用效率分析（Context Precision/Recall 解读）

4. 方法论反思
   4.1 LLM-as-Judge 的局限性
   4.2 测试集覆盖度评估
   4.3 指标间相关性分析
   4.4 与业界基准的对比

5. 下一步优化方向
   5.1 基于数据的优化优先级排序
   5.2 预期收益估算
```

#### 6.2 面试 Battle Card

准备以下高频质疑的标准回答：

**Q1: "你的评估指标够全面吗？"**
→ 展示 5 维度 13 指标体系，每个指标都有明确的计算公式和选型理由

**Q2: "LLM 评判可靠吗？"**
→ 展示 faithfulness 的两阶段设计（提取+验证），说明 temperature=0 的确定性控制，承认局限性并展示交叉验证思路

**Q3: "50 题够吗？"**
→ 展示置信区间计算，说明 50 题在 p=0.8 时 95% CI 约为 ±11%，承认这是成本与精度的权衡

**Q4: "你的 baseline 配置怎么选的？"**
→ chunk_size=512 对齐 BGE 模型的 512 token 窗口，overlap=64 约 12.5% 是经验值，top_k=5 是常见默认值

**Q5: "Hit Rate 84% 算好还是坏？"**
→ 分解分析：single_fact 可能 >90%，但 reasoning/comparative 可能 <70%，整体 84% 在纯向量检索基线中属于中等偏上

**Q6: "你怎么知道不是评估系统本身的 bug？"**
→ 展示 7 次实验的演进历史（从全零到正常），说明路径归一化修复过程；展示逐题结果的人工抽检

---

## 三、实施步骤与优先级

| 步骤 | Phase | 任务 | 优先级 | 预估工作量 |
|------|-------|------|--------|-----------|
| 1 | P1 | 修复 source_chunks 为空 | 🔴 P0 | 中 |
| 2 | P1 | 修复 FPR 未计算 | 🔴 P0 | 小 |
| 3 | P1 | 修复 missing 类型指标盲区 | 🟡 P1 | 中 |
| 4 | P1 | 修复变体描述 bug | 🟢 P2 | 小 |
| 5 | P2 | 扩大测试集到 50 题 | 🔴 P0 | 配置变更 |
| 6 | P2 | 调整问题类型分布 | 🟡 P1 | 配置变更 |
| 7 | P3 | 启用 Context Precision/Recall | 🟡 P1 | 配置变更 |
| 8 | P3 | 启用 Dedup 指标 | 🟡 P1 | 配置变更 |
| 9 | P3 | 新增按类型指标分解 | 🟡 P1 | 中 |
| 10 | P3 | 新增置信区间计算 | 🔴 P0 | 中 |
| 11 | P4 | 优化 System Prompt | 🟡 P1 | 小 |
| 12 | P5 | 运行 Solid 基线实验 | 🔴 P0 | 运行时间 |
| 13 | P6 | 撰写面试级分析报告 | 🔴 P0 | 大 |

**建议执行顺序**：1→2→4→5→6→7→8→10→11→12→3→9→13

先修复阻塞性问题（P1.1, P1.2），然后调整配置（P2, P3 的配置变更部分），再实现需要写代码的功能（P3.3, P3.4, P1.3），最后运行实验和写报告。

---

## 四、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| source_chunks 修复后匹配率仍低 | 中 | chunk 级指标仍不可靠 | 降级为文档级评估为主，chunk 级作为参考 |
| 50 题 LLM 评估成本过高 | 低 | 预算超支 | 估算：50题 × 5次LLM调用 ≈ $0.5，可接受 |
| Context Precision/Recall 结果不稳定 | 中 | 指标可信度受质疑 | 多次运行取平均，与 faithfulness 交叉验证 |
| 测试集生成质量问题 | 中 | 评估基础不牢 | 人工抽检 10% 题目，验证答案准确性 |
| 50 题运行时间过长 | 低 | 效率问题 | 预估 20-30 分钟，可接受 |

---

## 五、成功标准

一份 "solid" 的基线实验应满足：

1. **指标完整性**：13 个指标全部有值，无 null
2. **统计可靠性**：50 题 + 95% 置信区间
3. **可复现性**：相同 seed + 相同 meal → 相同结果
4. **透明性**：每个指标的计算方式、每个参数的选择理由都有文档
5. **深度分析**：不仅有全局数字，还有按类型分解、Bad Case 分析、根因分类
6. **方法论自觉**：明确承认 LLM-as-Judge 的局限性、测试集覆盖度不足等问题
