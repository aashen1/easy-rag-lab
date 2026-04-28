# 计划：对比讨论文档与当前代码实现，识别有道理但未落地的改进点

> 核实了一个旧对话是否已经实装。看来应该是已经实现为hybrid提问策略了。不过还是挖出一些有意思的点，放着之后有空可以优化。目前来看这些建议好像不算特别要紧。

## 背景

用户要求将 `plgd/RAG问答：文档来源定义.md` 中的讨论建议与当前代码实现进行对比，找出"有道理但我们没做"的改进点。

## 对比分析结果

### 已实现的讨论建议（不需要再做）

| 讨论建议 | 当前实现 | 状态 |
|---------|---------|------|
| **分段随机抽样替代固定截断** | `_segment_document()` + `segment_sampling_strategy: "random"` 已实现 | ✅ 已做 |
| **LLM 输出原文引用（verbatim quote）** | `EVIDENCE_AWARE_PROMPT` 要求输出 `evidence[].quote`，必须逐字一致 | ✅ 已做 |
| **引用验证机制** | `_validate_evidence()` + `_verify_quote_in_segment()` + `_fuzzy_match_quote()` | ✅ 已做 |
| **幻觉检测** | 引用不存在时标记 "Potential hallucination detected"，验证失败则重试 | ✅ 已做 |
| **通过 quote 定位 chunk** | `_locate_chunks_by_quote()` 替代了旧的关键词匹配 `_locate_answer_chunks()` | ✅ 已做 |
| **多跳问题 chunk 定位** | `_locate_multi_hop_chunks()` 对多条 evidence 分别定位后取并集 | ✅ 已做 |
| **6 种问题类型** | single_fact/multi_fact/reasoning/comparative/missing/irrelevant + adversarial | ✅ 已做，且多了 adversarial |
| **问题类型与选段策略映射** | `_select_segments_for_question_type()` 按类型选 0-3 段 | ✅ 已做 |
| **segment → chunk 映射** | `segment_chunk_map` 在生成时构建，用于精确定位 | ✅ 已做 |
| **数值精度校验** | `_validate_numerical_accuracy()` 检测 10 倍换算错误 | ✅ 已做 |
| **ground_truth_excerpt 原文验证** | `_verify_excerpt_in_document()` 验证 excerpt 是否存在于原文 | ✅ 已做 |
| **多跳问题选段多样性** | `_select_diverse_segments()` 等间距选取确保分布均匀 | ✅ 已做 |
| **融合策略架构** | `strategy="hybrid"` 已是默认策略，先选 segment 再生成问题 | ✅ 已做 |

---

### 有道理但未实现的改进点

#### 1. Page 级别标注（讨论中标记为 ⭐ 金融/法律文档常用）

**讨论建议**：采用混合策略，同时标注 page 级别和 chunk 级别。FinanceBench 的做法是 `gold document + page numbers + evidence text`。

**当前状态**：
- `_segment_document()` 按字符数均匀切分，**不感知文档结构**（章节/页面）
- segment 字典中只有 `start_char`/`end_char`/`segment_index`，**没有 page 信息**
- `_load_pages_json_documents()` 加载了 `.pages.json` 文件（含 page_number），但 page 信息在后续 segment 切分时丢失
- BUG-028：审查脚本缺少页码信息，无法定位 ground truth 出自哪一页
- FEAT-035（元数据增强：页码+标题层级）在 backlog 中待处理

**为什么有道理**：
- 金融研报 PDF 的页码是最自然的定位维度
- 人工标注时最自然的粒度就是"第几页"
- 页码信息对审查和调试至关重要
- 实现难度不高：`_segment_document()` 切分时可以继承 page 信息

---

#### 2. 按文档结构（章节/标题层级）分段（讨论中"多层级标注"建议）

**讨论建议**：HiChunk 的做法——按文档结构（L1 章节、L2 子章节、L3 段落）分段，而非按字符数均匀切分。

**当前状态**：
- `_segment_document()` 纯粹按字符数切分（`segment_size=8000`），仅在句号/换行处断句
- **完全不感知 Markdown 标题层级**（H1/H2/H3）
- 没有利用解析结果中的结构信息

**为什么有道理**：
- 研报有清晰的章节结构（公司概况、业务分析、财务数据等），按章节分段更语义化
- 同一章节内的信息关联性强，跨章节的信息关联性弱
- 按字符数切分可能把一个完整的分析段落切成两半
- 当前 chunker 已经按 fixed size 切分了，segment 如果也按 fixed size 切，只是"更大的 chunk"，没有带来结构化优势

**实现思路**：解析 Markdown 标题（`#`/`##`/`###`），按 H1 或 H2 边界分段，过长的章节再按字符数细分

---

#### 3. 多跳问题的语义相关性预筛选（讨论中的方案 A/B/C/D）

**讨论建议**：4 种方案确保多跳问题的两个选段有语义关联，推荐方案 D（让 LLM 自主决定）。

**当前状态**：
- `_select_candidate_segments()` 用 `_select_diverse_segments()` 等间距选取，**只保证空间分布均匀，不保证语义关联**
- 没有关键词共现检查（方案 B）
- 没有文档结构约束（方案 A，如同章节优先）
- LLM 拿到选段后自主生成问题，但**选段本身可能毫无关联**，LLM 可能被迫强行关联或忽略部分选段
- `selected_segments` 字段让 LLM 自主选择使用了哪些片段，但这是生成后的选择，不是生成前的筛选

**为什么有道理**：
- 当前等间距选取可能选到完全无关的段落（如公司概况 + 风险提示），LLM 强行生成多跳问题导致不自然
- 讨论中明确指出这是 chunk-based 策略的核心缺陷之一，hybrid 策略应该解决它
- 方案 D（给 LLM 更多候选段，让其自主选择）实现成本最低，效果可能最好

**实现思路**：给 multi_hop 类型提供 3-4 个候选 segment（当前已有 `multi_hop_candidate_count: 3`），但需要确保候选中有语义关联的组合

---

#### 4. Ground Truth 可靠性置信度评分

**讨论建议**：对 ground truth 标注一个置信度分数，而非简单的"通过/不通过"。

**当前状态**：
- evidence 验证只有 `verified: True/False` 二值判断
- 没有置信度分数
- `match_type` 有 exact/fuzzy 区分，但没有转化为量化分数
- 数值校验只有"是否 10 倍错误"，没有"数值是否一致"的置信度

**为什么有道理**：
- fuzzy match 的 0.85 阈值是硬截断，0.84 和 0.86 的 quote 质量差异不大，但一个被接受一个被拒绝
- 置信度分数可以让下游消费者（评估指标计算）自行决定阈值
- 对于评估指标计算，可以加权使用不同置信度的 ground truth

**实现思路**：基于 `match_type`（exact=1.0, fuzzy=match_score）和 evidence 数量计算综合置信度

---

#### 5. LLM 辅助验证（讨论中的"后验验证"方案 B）

**讨论建议**：生成问题后，用另一个 LLM 验证答案是否真的来自标注的 chunk/segment。

**当前状态**：
- `enable_llm_evaluation: false`（config.yaml 中默认关闭）
- 当前验证全部基于规则（字符串匹配、数值比较），没有 LLM 语义验证
- 只有 `_check_authenticity_rules()` 做表面规则检查（禁止学术化表述）

**为什么有道理**：
- 规则验证无法检测语义层面的幻觉（如 LLM 对原文数据的错误解读）
- 一个简单的 LLM 验证 prompt（"以下答案是否完全来自给定文本？"）成本很低
- 可以作为质量门控，过滤掉语义不一致的问题

**注意**：config 中已有 `enable_llm_evaluation` 开关，说明设计时考虑过，只是默认关闭。可以作为一个可选的质量增强步骤。

---

#### 6. Segment 与 Chunk 的对齐优化

**讨论建议**：抽样时记录段落对应的 chunk ID 列表，用原文引用反向定位到具体 chunk，由于引用来自抽样段落，定位必然准确。

**当前状态**：
- `segment_chunk_map` 已经实现了 segment → chunk_ids 的映射
- `_locate_chunks_by_quote()` 先在 segment 中定位，再在映射的 chunks 中精确匹配
- **但存在一个已知问题**：当 quote 跨越 chunk 边界时，可能无法定位到任何 chunk（L3738-3741 的 debug 日志表明这确实会发生）

**为什么有道理**：
- 跨 chunk 边界的 quote 定位失败是一个真实问题
- 可以在 segment 切分时考虑 chunk 边界对齐，或者在定位时对跨边界 quote 做拼接匹配

---

#### 7. 文档截断的 legacy 路径仍存在

**讨论建议**：彻底废弃固定截断方式。

**当前状态**：
- `DOCUMENT_TRUNCATE_MAX = 8000` 仍然存在（L418）
- `use_hybrid=False` 时仍走 `_generate_single_document_question()` 的截断路径
- `_locate_answer_chunks()` 仍被 legacy 路径调用（L2937, L2998, L3157）

**为什么有道理**：
- legacy 路径是技术债，新用户可能误用
- 讨论中明确指出固定截断是设计缺陷

---

## 优先级排序

| 优先级 | 改进点 | 理由 |
|--------|--------|------|
| **高** | Page 级别标注 | 金融文档最自然的定位维度，backlog 中已有相关 issue（BUG-028, FEAT-035） |
| **高** | 按文档结构分段 | 语义化分段比字符数分段更合理，是 hybrid 策略的核心优势所在 |
| **中** | 多跳语义相关性预筛选 | 直接影响多跳问题质量，当前等间距选取可能产生无意义组合 |
| **中** | 清理 legacy 截断路径 | 技术债，避免误用 |
| **低** | 置信度评分 | 锦上添花，当前二值判断已基本够用 |
| **低** | LLM 辅助验证 | 已有开关，成本较高，可作为可选增强 |
| **低** | Segment-Chunk 边界对齐 | 边界情况，影响范围有限 |

## 结论

讨论文档中提出的核心建议（分段随机抽样、原文引用追踪、引用验证、chunk 定位、融合策略架构）**已经全部实现**。这是 v0.1.9 统一测试集生成链路的重要成果。

尚未实现但有道理的改进点主要集中在**结构化感知**层面：Page 信息保留、按章节分段、多跳语义筛选。这些是下一阶段可以推进的方向。
