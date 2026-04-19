# RAG 对比实验系统指标计算优化计划

## 问题分析

通过分析实验报告 `exp_20260420_004941_smoke_quick` 和相关代码，发现以下问题：

### 问题 1: NDCG 计算存在严重 Bug（值超过 1.0）

**现象**：
- 实验报告中 NDCG = 0.9828，而 Hit Rate 和 MRR 都是 0.3333
- 单个问题的 NDCG 值为 `2.9484591188793923`，明显超过 1.0

**原因分析**：
查看 [metrics.py](file:///b:/project/ash-easy-rag/eval/metrics.py) 中的 `calculate_ndcg` 函数：

```python
dcg = 0.0
for i, source in enumerate(retrieved_normalized):
    if source in expected_set and source in relevance_scores:
        rel = relevance_scores[source]
        dcg += (2**rel - 1) / math.log2(i + 2)
```

问题在于：当检索结果中包含**重复的文档**时（如 baseline.json 中 sources 数组有 5 个相同的文件），DCG 会被多次累加：

- 检索结果：`[doc1, doc1, doc1, doc1, doc1]`（同一文档出现 5 次）
- expected_sources：`[doc1]`
- DCG 被累加 5 次，而 IDCG 只计算 1 次
- 导致 NDCG = DCG / IDCG > 1.0

**影响**：NDCG 指标完全失真，无法正确反映检索质量。

---

### 问题 2: 测试集设计不合理 - "不可能命中"的问题

**现象**：
从 baseline.json 可以看到：
- q003-q006 的 `expected_sources` 指向的文档不在检索库中
- 例如 q003 期望 `煤炭行业周报：中东局势持续扰动...`，但检索到的全是 `2026年光伏行业分析.md`

**原因分析**：
这是 `document` 策略生成测试集的问题：
- 测试集生成时随机选择文档生成问题
- 但某些文档可能不在当前的检索库中
- 导致这些问题注定无法命中正确答案

**影响**：
- 人为拉低 Hit Rate 和 MRR
- 无法真实反映检索系统的能力
- 干扰实验结论

---

### 问题 3: Hit Rate 计算逻辑与业界标准有差异

**现状**：
当前代码支持两种模式：
- `standard`: 标准 Hit Rate@k（top-k 中有相关文档则为 1）
- `recall`: 召回率模式（命中的相关文档数 / 总相关文档数）

**问题**：
- 默认使用 `standard` 模式是正确的
- 但当 `expected_sources` 为空时返回 0.0，可能掩盖了测试集设计问题

---

### 问题 4: 缺少对"无法回答"问题的特殊处理

**现象**：
当检索失败时，LLM 会返回类似"根据提供的参考资料，我无法回答..."的响应。

**问题**：
- 这些"无法回答"的情况应该被单独统计
- 目前 Faithfulness 和 Answer Relevancy 仍然会被计算
- 可能导致生成质量指标失真

---

### 问题 5: 指标汇总时缺少问题分类统计

**现状**：
- 只计算整体平均指标
- 没有区分"可命中"和"不可命中"的问题
- 没有按问题类型（easy/medium/hard）分类统计

---

## 优化方案

### 方案 1: 修复 NDCG 计算 Bug

**修改文件**: `eval/metrics.py`

**修改内容**:
1. 在计算 DCG 前，对 `retrieved_sources` 进行去重
2. 保持文档的首次出现位置作为其排名
3. 确保 NDCG 值在 [0, 1] 范围内

```python
def calculate_ndcg(...):
    # 去重：只保留每个文档的首次出现
    seen = set()
    unique_retrieved = []
    for source in retrieved_normalized:
        if source not in seen:
            seen.add(source)
            unique_retrieved.append(source)
    
    # 使用去重后的列表计算 DCG
    ...
```

---

### 方案 2: 优化测试集生成逻辑

**修改文件**: `src/test_generator.py`

**修改内容**:
1. 在生成问题时，验证 `expected_sources` 中的文档确实在检索库中
2. 添加 `unanswerable` 问题类型，明确标注无法回答的问题
3. 在测试集中添加 `valid` 字段，标记问题是否可被正确评估

---

### 方案 3: 增强指标计算和报告

**修改文件**: `eval/metrics.py`, `eval/run_experiment.py`, `eval/experiment_reporter.py`

**修改内容**:
1. 添加问题有效性检查函数
2. 区分"有效问题"和"无效问题"的指标统计
3. 在报告中添加：
   - 有效问题数量和比例
   - 按问题难度分类的指标
   - "无法回答"问题的统计

---

### 方案 4: 添加指标边界检查和日志

**修改文件**: `eval/metrics.py`

**修改内容**:
1. 在 `calculate_ndcg` 返回前添加边界检查
2. 如果 NDCG > 1.0，记录警告日志
3. 添加单元测试验证指标计算正确性

---

## 实施步骤

### Step 1: 修复 NDCG 计算 Bug（高优先级）
- 修改 `eval/metrics.py` 中的 `calculate_ndcg` 函数
- 添加去重逻辑
- 添加边界检查
- 编写单元测试

### Step 2: 增强测试集生成（中优先级）
- 修改 `src/test_generator.py`
- 添加文档存在性验证
- 添加问题有效性标记

### Step 3: 优化指标统计和报告（中优先级）
- 修改 `eval/run_experiment.py`
- 添加有效问题过滤
- 添加分类统计
- 更新报告模板

### Step 4: 添加单元测试（高优先级）
- 为 `calculate_ndcg` 添加测试用例
- 测试边界情况（重复文档、空列表等）
- 测试去重逻辑

---

## 预期效果

1. **NDCG 指标正确**：值在 [0, 1] 范围内，能正确反映检索质量
2. **测试集更合理**：所有问题的 `expected_sources` 都在检索库中
3. **报告更清晰**：区分有效/无效问题，按难度分类统计
4. **指标更可靠**：通过单元测试验证计算正确性
