# 实验结果虚高排查计划

## 问题概述

基线 RAG（无任何优化）在 5kpage 数据集上的检索评测结果异常好：
- Hit Rate: 0.9355 (93.55%)
- MRR: 0.8251
- NDCG: 0.8591

用户认为这个结果不合常理，需要排查虚高原因。

---

## 排查发现：5 个核心问题

### 问题 1（致命）：评测粒度为文档级，而非 chunk 级 —— 这是最主要的虚高来源

**现象**：评测时 ground truth 是 `source_files`（文档级路径），匹配逻辑只检查"检索结果中是否包含来自同一文档的 chunk"，而非"是否检索到了包含答案的具体 chunk"。

**代码证据**：
- [eval/metrics.py:64-68](file:///b:/project/ash-easy-rag/eval/metrics.py#L64-L68) — `calculate_hit_rate` 用 `normalize_source()` 提取文件名 stem 后做集合交集
- [src/test_generator.py:846-853](file:///b:/project/ash-easy-rag/src/test_generator.py#L846-L853) — `source_files = [source_path]`，只记录文档路径

**具体影响**：
- 76 个 PDF 文档被分成 9647 个 chunk，平均每个文档约 127 个 chunk
- Top-5 检索结果中，只要**任何一个** chunk 来自目标文档就算命中
- 对于一个有 127 个 chunk 的文档，随机检索到该文档某个 chunk 的概率本身就很高
- 这相当于"开卷考试只要求翻到正确的书，不要求翻到正确的页"

**数据佐证**：从结果中可以看到，绝大多数命中案例的 5 个检索结果全部来自同一文档（如 q001-q005），说明同一文档的多个 chunk 在向量空间中高度聚集，进一步放大了文档级匹配的虚高效应。

### 问题 2（严重）：同一文档的多个 chunk 在 Top-K 中重复出现，稀释了评测的区分度

**现象**：Top-5 检索结果中，经常出现 5 个结果全部来自同一文档的情况。

**数据佐证**：
- q001: 5 个 sources 全部是 `2025中国宫颈癌诊疗现状白皮书.md`
- q003: 5 个 sources 全部是 `2025年民用纵列式无人直升机行业词条报告.md`
- q084: 5 个 sources 全部是 `中国建筑股份有限公司2023年年度报告.md`

**影响**：在文档级评测下，5 个来自同一文档的 chunk 只贡献 1 次有效命中，但占满了 Top-5 的位置，使得 Hit Rate 计算变得毫无区分度——无论检索质量好坏，只要"大致方向对"就能命中。

### 问题 3（中等）：irrelevant 类型问题被排除在检索指标之外

**现象**：5 个 `irrelevant`（无关问题）设置了 `expect_retrieval=False`，不参与检索指标计算。

**代码证据**：[eval/run_experiment.py:587-594](file:///b:/project/ash-easy-rag/eval/run_experiment.py#L587-L594) — `if expect_retrieval and expected_sources:` 才计算检索指标

**影响**：
- 98 个问题中，5 个 irrelevant + 10 个 missing = 15 个问题要么不参与计算，要么对 Hit Rate 贡献天然偏高
- 实际参与检索指标计算的只有 93 个问题
- irrelevant 问题本应是最能区分检索质量的——好的检索系统应该对无关问题返回低相关性结果

### 问题 4（中等）：missing 类型问题的评测逻辑不合理

**现象**：10 个 `missing`（缺失信息）类型问题设置了 `expect_no_answer=True` 但 `expect_retrieval=True`，且 `source_files = [source_path]`。

**影响**：
- missing 类型的问题期望系统"无法回答"，但评测时仍然检查检索是否命中了源文档
- 这意味着即使问题涉及的信息在文档中不存在，只要检索到了该文档就算成功
- 这进一步推高了 Hit Rate

### 问题 5（轻微）：同一公司存在"年报全文"和"年报摘要"两个版本，导致误判

**现象**：部分 hit_rate=0 的案例中，检索到了正确公司的"年报全文"，但期望的是"年报摘要"（或反之），因文件名 stem 不同而被判为未命中。

**数据佐证**：
- q084: 检索到 `中国建筑股份有限公司2023年年度报告.md`，期望 `中国建筑股份有限公司2023年年度报告摘要.md` → stem 分别为 `中国建筑股份有限公司2023年年度报告` 和 `中国建筑股份有限公司2023年年度报告摘要`，不匹配
- q086: 检索到 `2023年年度报告.md`，期望 `2023年年度报告_英文版_.md` → stem 不匹配

**影响**：这个问题反而**压低**了分数（约 2-3 个问题），但暴露了 ground truth 构建方式的问题——问题基于某个文档生成，但语义上同一公司的全文版/摘要版/英文版都能回答。

---

## 修复计划

### 步骤 1：引入 chunk 级评测（核心修复）

**目标**：将评测粒度从文档级提升到 chunk 级，使 Hit Rate 真正衡量"是否检索到了包含答案的具体段落"。

**具体改动**：
1. 修改 `src/test_generator.py` 中文档级问题生成逻辑，在生成问题时记录 `source_chunks`（答案所在的 chunk ID 列表），而非仅记录 `source_files`
2. 修改 `eval/metrics.py` 中的匹配逻辑，增加 chunk 级匹配模式
3. 修改 `eval/run_experiment.py` 中的评测逻辑，优先使用 chunk 级匹配

**关键设计决策**：
- 问题生成时，LLM 返回的 `answer_sources` 信息可用于定位 chunk
- 需要在 chunk 的 metadata 中记录 chunk_id，以便检索结果可以回溯到具体 chunk
- chunk 级匹配应支持"同一文档的相邻 chunk 也算命中"的容错机制（因为答案可能跨 chunk 边界）

### 步骤 2：添加文档级去重后的检索指标

**目标**：在 Top-K 检索结果去重后（每个文档只保留最相关的 1 个 chunk），重新计算 Hit Rate / MRR / NDCG，作为辅助参考指标。

**具体改动**：
1. 在 `eval/metrics.py` 中添加 `calculate_diversified_hit_rate` 等函数
2. 在评测报告中同时展示去重前后的指标

### 步骤 3：将 irrelevant 类型问题纳入检索评测

**目标**：对 irrelevant 问题，评测检索系统是否正确地返回了低相关性或不相关的结果。

**具体改动**：
1. 修改 `eval/run_experiment.py`，对 irrelevant 类型问题计算"误检率"（检索到了不相关文档的比例）
2. 在聚合指标中加入 irrelevant 问题的惩罚项

### 步骤 4：修复 missing 类型的评测逻辑

**目标**：missing 类型问题应评测"检索系统是否正确地没有返回高置信度结果"，而非检查是否命中了源文档。

**具体改动**：
1. 修改 missing 类型的 ground truth 设置，`expect_retrieval=False` 或使用特殊逻辑
2. 对 missing 问题，评测检索结果的最高相似度分数是否低于阈值

### 步骤 5：处理同一文档多版本问题

**目标**：对同一公司的"年报全文"和"年报摘要"等变体，在 ground truth 中建立等价关系。

**具体改动**：
1. 在 `normalize_source` 中增加公司名+年份的模糊匹配逻辑
2. 或在 meal 构建时，将同一公司的多版本文档标记为等价组

---

## 预期效果

修复后，基线 RAG 的 Hit Rate 预计会从 0.9355 下降到 0.5-0.7 的区间，更符合"无优化基线"的真实水平。这也将为后续优化实验（reranker、hybrid retrieval 等）提供更有区分度的评测基准。
