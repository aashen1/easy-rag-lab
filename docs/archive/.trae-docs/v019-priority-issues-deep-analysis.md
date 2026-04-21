# v0.1.9 积压 Issue 优先推荐与深度分析

> 生成日期：2026-04-21
> 更新日期：2026-04-21（rebase fix-many-baseline-bugs 后更新）
> 对齐版本目标：v0.1.9（透明报告 + 确认实验系统合理性 + 跑基线测试）

---

## 一、当前积压统计

| 类型 | 待处理 | 已延期 | 总计 |
|------|--------|--------|------|
| Bug | 4 | 2 | 6 |
| Feature | 15 | 0 | 15 |
| Refactor | 10 | 0 | 10 |
| Optimization | 7 | 0 | 7 |
| Investigation | 14 | 0 | 14 |

共 **50 条待处理** issue（rebase 后新增 19 条）。

---

## 二、✅ rebase 已修复的关键问题

`fix-many-baseline-bugs` 分支已修复以下致命/高优先级问题：

| 原 Issue | 问题描述 | 修复内容 |
|----------|----------|----------|
| **P6-3** | contexts/sources 混淆导致 faithfulness 完全失效 | 分离 contexts 和 retrieved_sources，正确传递给 evaluator |
| **P5-1** | System Prompt 硬编码，无法通过配置调整 | Generator 支持构造函数和 per-call 覆盖 system_prompt |
| **P4-1** | 查询未加 BGE 指令前缀，检索效果未达最优 | Embedder 支持 BGE query instruction prefix（可配置） |
| **P4-2** | 无分数过滤，低质量匹配也返回 | Retriever 支持 score threshold 过滤 |
| **P5-4** | 引用来源要求模糊，LLM 无法真正引用 | Generator 在 context 中包含 source document names |
| **数据流断点** | chunk_ids/question_type 未传递 | `_collect_rag_samples()` 现在采集并传递这些字段 |

**影响**：这些修复直接解决了 INV-007 分析中发现的**致命级 Bug**，faithfulness/context_precision/context_recall 现在可以正确评估了。

---

## 三、🔴 高优先级（v0.1.9 核心路径）

### 1. FEAT-014 — 透明版完整实验报告

**对齐 v0.1.9 第一项任务**："修改逻辑以生成完全透明的verbose版本实验报告"

**规模**：大 | **依赖**：无 | **紧迫性**：极高

#### 现状分析（rebase 后更新）

rebase 后，**数据流断点已部分修复**：
- `chunk_ids` 和 `question_type` 现在会被采集
- `contexts` 和 `retrieved_sources` 已分离

但仍需补齐的透明性信息：

| 缺失信息 | 当前状态 | 修复方案 |
|----------|----------|----------|
| 检索分数 (scores) | pipeline 返回了但未采集 | 在 `_collect_rag_samples()` 中采集 |
| 生成 Prompt | Generator 支持 system_prompt 但未记录到结果 | 在 result 中增加 `generation_prompt` 字段 |
| 期望答案 (expected_answer) | 采集了但未写入 result | 在 result 字典中增加 |
| Faithfulness 中间产物 | statements/verdicts 被丢弃 | 修改指标函数返回中间产物 |
| Context Precision 中间产物 | verdicts 被丢弃 | 修改指标函数返回中间产物 |
| Answer Relevancy 中间产物 | 维度分数被丢弃 | 修改指标函数返回中间产物 |

#### 建议实施路径

1. **Phase 1**：在 `_collect_rag_samples()` 中采集 scores，写入 result
2. **Phase 2**：修改指标计算函数，返回中间产物（statements、verdicts、维度分数）
3. **Phase 3**：新增 verbose 报告模板，逐问题展示完整信息链
4. **Phase 4**：深度透明性（embedding 向量、rerank 过程等）

---

### 2. INV-007 — 评测系统可靠性全面审查

**对齐 v0.1.9 第二项任务**："确认目前的exp系统能生成合理的结果"

**规模**：中 | **依赖**：FEAT-014 | **紧迫性**：高（但致命 Bug 已修复）

#### rebase 后状态更新

**已修复**：
- ✅ contexts/sources 混淆（P6-3）
- ✅ chunk_ids/question_type 传递
- ✅ System Prompt 可配置

**仍待解决**：

| 问题 | 严重性 | 说明 |
|------|--------|------|
| BUG-017 | 高 | expected_sources 标注错误（问题涉及文档中提到的其他实体，但 source_files 仅指向生成问题时的源文档） |
| P6-8 | 高 | expected_chunks 定位粗糙（关键词+子串重叠启发式，可能遗漏或误匹配） |
| P6-6 | 中 | Faithfulness 自评偏差（同一 LLM 生成并评估） |
| P6-7 | 中 | Answer Relevancy 分数不稳定 |

#### 建议行动

1. **立即**：用一个 PDF + 一个问题验证全链路数据正确性（致命 Bug 已修复，需确认）
2. **短期**：校验 golden_qa 中的 expected_sources 标注
3. **中期**：引入评估模型与生成模型分离的配置选项

---

### 3. INV-006 — golden test 是否基于老策略

**对齐 v0.1.9 第三项任务**：跑基线测试前必须确认测试集本身是否有效

**规模**：小（纯调查） | **依赖**：无 | **紧迫性**：高

#### 调查结论

**golden_qa.json 基于旧策略（chunk-based），确认需要重做。**

证据：
- `category` 字段使用 `factual`/`boundary`/`multi_hop`——旧策略分类
- 不包含新策略的 `question_type`、`source_files`、`source_chunks`、`answer` 等字段
- 新策略使用 6 种类型：`single_fact`/`multi_fact`/`reasoning`/`comparative`/`missing`/`irrelevant`

#### 建议行动

1. 使用新策略（document-based）重新生成 golden_qa.json
2. 将 golden_qa.json 迁移为 TestSetManager 管理的格式
3. 确保新 golden test 的 `source_files` 与当前 Meal 的 PDF 列表一致

---

## 四、🟡 中优先级（提升系统质量）

### 4. BUG-017 — expected_sources 标注错误

**规模**：中 | **来源**：[pipeline-deep-audit.md#P6-5](pipeline-deep-audit.md#P6-5)

#### 问题描述

LLM 生成的问题可能涉及文档中提到的其他实体，但 `source_files` 仅指向生成问题时的源文档。

**实例**：q010 问"中际旭创和新易盛哪家更值得投资"，expected_sources 指向中芯国际年报（完全无关）。

#### 建议行动

需要重新设计问题生成策略，使 `source_files` 反映问题实际涉及的文档。

---

### 5. FEAT-025 — 检索器层面文档级去重

**规模**：中 | **来源**：[pipeline-deep-audit.md#P6-4](pipeline-deep-audit.md#P6-4)

#### 问题描述

当前 top 5 检索结果经常全部来自同一文档，检索多样性为零。

**实际数据**：8/10 问题的 top 5 全部来自同一文档。

#### 建议行动

在 retriever 层面实现文档级去重，确保 top_k 结果按文档多样性分配。

---

### 6. RF-004 — 硬编码配置值提取到 config.yaml

**规模**：中 | **依赖**：无

#### 硬编码审计结果（仍有效）

| 文件 | 硬编码项 | 数量 |
|------|----------|------|
| eval/metrics/generation.py | model_name、base_url、max_tokens、temperature | 12 处 |
| eval/metrics/llm_retrieval.py | model_name、base_url、max_tokens、temperature | 8 处 |
| eval/experiment_reporter.py | fallback model_name、max_tokens、temperature | 5 处 |
| src/test_generator.py | temperature、max_tokens、TYPE_DISTRIBUTION | 11 处 |

---

## 五、🟢 低优先级（可后续版本处理）

### 7. FEAT-011 — 补做 LLM 报告功能

**规模**：小 | **实用性**：高

### 8. OPT-003 — 问题生成 token 消耗优化

**规模**：中 | **建议**：等基线确认后再优化

### 9. INV-012 — 测试体系深度审查（883条是否过多）

**规模**：中 | **建议**：重要但不紧急

### 10. FEAT-019 — .trae 目录归档机制

**规模**：中 | **建议**：打扫卫生时顺手做

---

## 六、新增 Issue（来自 RAGAS 集成和 pipeline-deep-audit）

### RAGAS 相关

| ID | 描述 | 优先级 |
|----|------|--------|
| BUG-018 | RAGAS 框架版本兼容性风险 | 中 |
| BUG-019 | context_precision/context_recall 聚合位置不一致 | 中 |
| BUG-020 | RAGAS evaluate() 的 raise_exceptions 行为差异 | 低 |
| FEAT-020 | RAGAS 版本升级与 API 适配 | 中 |
| FEAT-021 | Ground Truth 手动标注工具 | 低 |
| FEAT-022 | RAGAS 评测 Token 消耗追踪 | 中 |
| OPT-005 | RAGAS/builtin 指标结果统一归一化 | 低 |
| OPT-006 | RAGAS 评测缓存与增量计算 | 低 |
| INV-013 | 自动生成的 Ground Truth 质量有限 | 中 |
| INV-014 | RAGAS 指标与 Builtin 指标深度对比分析 | 低 |

### Pipeline 审计相关

| ID | 描述 | 优先级 |
|----|------|--------|
| FEAT-023 | Context 长度控制（防止超出模型 context window） | 中 |
| FEAT-024 | 页眉页脚清洗 | 低 |
| FEAT-025 | 检索器层面文档级去重 | 高 |
| RF-013 | chunk_id 命名规范化 | 低 |
| RF-014 | normalize_source 匹配精度提升 | 低 |
| OPT-007 | 基线 chunk_overlap 非零优化 | 低 |
| INV-015 | tiktoken 与 BGE tokenizer 的 token 数差异量化 | 中 |
| INV-016 | PDF 表格解析质量评估与替代方案调研 | 中 |

---

## 七、推荐实施顺序（更新）

```
Phase 0: 验证修复效果（INV-007 验证）
  ├─ 用一个 PDF + 一个问题走完全链路
  └─ 确认 faithfulness/context_precision 现在能正确计算

Phase 1: 透明报告基础（FEAT-014 Phase 1-2）
  ├─ 采集 scores 到 result
  └─ 修改指标函数返回中间产物

Phase 2: 测试集重建（INV-006）
  ├─ 用新策略重做 golden_qa.json
  └─ 迁移为 TestSetManager 格式

Phase 3: 标注修复（BUG-017）
  └─ 重新设计问题生成策略

Phase 4: 检索多样性（FEAT-025）
  └─ 实现文档级去重

Phase 5: 代码质量（RF-004 + RF-012）
  ├─ 硬编码配置提取
  └─ 旧格式警告清理

Phase 6: 跑基线测试
  └─ 生成 v0.1.9 的透明版基线实验报告
```

---

## 八、Issue 间依赖关系图（更新）

```
FEAT-014 (透明报告)
    ↓
INV-007 (评测可靠性验证) ←── BUG-017 (expected_sources 标注)
    ↓                           ↑
INV-006 (golden test) ──────────┘
    ↓
FEAT-025 (检索多样性)
    ↓
RF-004 (硬编码提取)
    ↓
基线测试
```

---

## 九、最推荐的下一步行动

**rebase 后，最推荐的 issue 变为：**

### 🥇 第一推荐：INV-007 验证

**原因**：致命 Bug 已修复，需要先验证修复效果再继续其他工作。

**具体行动**：
1. 运行一次冒烟测试
2. 检查 faithfulness/context_precision 数值是否合理
3. 确认 contexts 现在是文本内容而非文件路径

### 🥈 第二推荐：INV-006（golden test 重做）

**原因**：测试集是基线测试的基础，当前 golden_qa.json 基于旧策略，需要更新。

### 🥉 第三推荐：FEAT-014（透明报告）

**原因**：v0.1.9 核心交付物，但可以在验证和测试集更新后再推进。

---

## 十、状态变更总结

| 原推荐 | 状态 | 说明 |
|--------|------|------|
| INV-007 致命 Bug 修复 | ✅ 已修复 | contexts/sources 混淆已解决 |
| P4-1 BGE 指令前缀 | ✅ 已修复 | Embedder 支持 query instruction |
| P4-2 分数过滤 | ✅ 已修复 | Retriever 支持 score threshold |
| P5-1 System Prompt 硬编码 | ✅ 已修复 | Generator 支持配置 |
| P5-4 引用来源模糊 | ✅ 已修复 | Context 包含 source document names |
| INV-007 验证 | 🆕 新增 | 需验证修复效果 |
| BUG-017 | 🆕 新增 | expected_sources 标注错误 |
| FEAT-025 | 🆕 新增 | 检索多样性问题 |
