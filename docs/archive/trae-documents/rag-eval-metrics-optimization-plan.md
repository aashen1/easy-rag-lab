# RAG 评测系统深度优化计划

## 背景

参考 RAGAS、DeepEval 等生产级评测框架，对当前 RAG 评测系统进行全面优化，使指标计算与业界标准对齐。

***

## 一、当前系统与业界标准对比

### 1.1 检索指标对比

| 指标                | 当前实现    | RAGAS | DeepEval | 状态      |
| ----------------- | ------- | ----- | -------- | ------- |
| Hit Rate          | ✅ 有     | ❌ 无   | ❌ 无      | 保留，但需优化 |
| MRR               | ✅ 有     | ❌ 无   | ❌ 无      | 保留，但需优化 |
| NDCG              | ⚠️ 有Bug | ❌ 无   | ❌ 无      | 需修复     |
| Context Precision | ❌ 无     | ✅ 有   | ✅ 有      | **需添加** |
| Context Recall    | ❌ 无     | ✅ 有   | ✅ 有      | **需添加** |

### 1.2 生成指标对比

| 指标                 | 当前实现 | RAGAS | DeepEval | 状态       |
| ------------------ | ---- | ----- | -------- | -------- |
| Faithfulness       | ✅ 有  | ✅ 有   | ✅ 有      | 实现类似，可优化 |
| Answer Relevancy   | ✅ 有  | ✅ 有   | ✅ 有      | 计算方式不同   |
| Answer Correctness | ❌ 无  | ✅ 有   | ✅ 有      | **需添加**  |

***

## 二、核心问题分析

### 问题 1: NDCG 计算存在严重 Bug

**现象**：NDCG 值超过 1.0（如 2.948...）

**原因**：检索结果包含重复文档时，DCG 被多次累加

**影响**：NDCG 指标完全失真

### 问题 2: 缺少 Context Precision 和 Context Recall

**业界标准做法**（DeepEval）：

```
Contextual Precision = (1/相关节点数) × Σ(前k个位置的相关节点数/k × r_k)
```

* 使用 LLM-as-a-judge 判断每个检索节点是否与问题相关

* 强调顶部结果的排序质量

* 比传统的 Hit Rate 更适合 RAG 场景

**RAGAS 的 Context Recall**：

* 将 Ground Truth 分割成句子

* 判断每个句子是否能从检索上下文中推断出来

* 计算：`可推断句子数 / 总句子数`

### 问题 3: Answer Relevancy 计算方式与业界不同

**RAGAS 做法**：

1. 基于答案生成 n 个伪问题
2. 计算原始问题与每个伪问题的余弦相似度
3. 计算平均相似度

**当前做法**：

* 使用 LLM 直接评分（直接相关性、信息充分性、简洁聚焦性）

**建议**：保留当前方式（更直观），但可考虑添加 RAGAS 方式作为备选

### 问题 4: 测试集设计问题

**现象**：部分问题的 `expected_sources` 指向不在检索库中的文档

**影响**：人为拉低检索指标，无法真实反映系统能力

### 问题 5: 缺少问题有效性分类

**业界做法**：

* 区分"可回答"和"不可回答"问题

* 对"无法回答"的情况单独统计

* 按问题难度分类报告

***

## 三、优化方案

### 3.1 修复 NDCG 计算 Bug

**修改文件**: `eval/metrics.py`

**修改内容**:

```python
def calculate_ndcg(
    retrieved_sources: List[str],
    expected_sources: List[str],
    k: int = 5,
    relevance_scores: Optional[Dict[str, int]] = None,
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain.
    
    Fixed version with deduplication to ensure NDCG ∈ [0, 1].
    """
    if not expected_sources:
        return 0.0

    expected_normalized = [normalize_source(s) for s in expected_sources]
    expected_set = set(expected_normalized)

    if relevance_scores is None:
        relevance_scores = {s: 1 for s in expected_normalized}

    # 关键修复：去重，只保留每个文档的首次出现
    retrieved_normalized = [normalize_source(s) for s in retrieved_sources[:k]]
    seen = set()
    unique_retrieved = []
    for source in retrieved_normalized:
        if source not in seen:
            seen.add(source)
            unique_retrieved.append(source)

    # 计算 DCG
    dcg = 0.0
    for i, source in enumerate(unique_retrieved):
        if source in expected_set and source in relevance_scores:
            rel = relevance_scores[source]
            dcg += (2**rel - 1) / math.log2(i + 2)

    # 计算 IDCG
    ideal_rels = sorted(
        [relevance_scores[s] for s in expected_normalized if s in relevance_scores],
        reverse=True
    )[:k]
    
    ideal_dcg = sum((2**rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal_rels))

    if ideal_dcg == 0:
        return 0.0

    ndcg = dcg / ideal_dcg
    
    # 边界检查（防御性编程）
    return min(1.0, max(0.0, ndcg))
```

### 3.2 添加 Context Precision 指标

**新增文件**: `eval/metrics.py` 中添加

**实现方式**（参考 DeepEval）:

```python
CONTEXT_PRECISION_PROMPT = """你是一个专业的信息检索评估专家。

请判断以下检索到的上下文是否与问题相关。

【问题】
{question}

【期望答案】
{expected_output}

【检索上下文】
{context}

请判断这个上下文是否包含回答问题所需的关键信息。
只回答"是"或"否"，并简要说明理由。

请以JSON格式输出：
{{"verdict": "是"或"否", "reason": "简要理由"}}
"""

def calculate_context_precision(
    question: str,
    expected_output: str,
    retrieval_context: List[str],
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
    model_name: str = "LongCat-Flash-Lite",
) -> float:
    """
    Calculate Context Precision using LLM-as-a-judge.
    
    Formula: CP = (1/N) × Σ(Precision@k × r_k)
    
    Where:
    - N = number of relevant nodes
    - Precision@k = (relevant nodes up to position k) / k
    - r_k = 1 if node k is relevant, 0 otherwise
    
    Args:
        question: The user's question.
        expected_output: The expected answer (ground truth).
        retrieval_context: List of retrieved context strings.
        api_key: API key for LLM.
        base_url: Base URL for LLM API.
        model_name: LLM model name.
    
    Returns:
        Context precision score in [0, 1].
    """
    if not retrieval_context:
        return 0.0
    
    # 使用 LLM 判断每个上下文的相关性
    relevance_verdicts = []
    for ctx in retrieval_context:
        verdict = _judge_context_relevance(
            question, expected_output, ctx, api_key, base_url, model_name
        )
        relevance_verdicts.append(verdict)
    
    # 计算加权累积精度
    relevant_count = sum(relevance_verdicts)
    if relevant_count == 0:
        return 0.0
    
    wcp_sum = 0.0
    relevant_up_to_k = 0
    
    for k, is_relevant in enumerate(relevance_verdicts, 1):
        if is_relevant:
            relevant_up_to_k += 1
            precision_at_k = relevant_up_to_k / k
            wcp_sum += precision_at_k
    
    return wcp_sum / relevant_count
```

### 3.3 添加 Context Recall 指标

**实现方式**（参考 RAGAS）:

```python
def calculate_context_recall(
    question: str,
    ground_truth: str,
    retrieval_context: List[str],
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
    model_name: str = "LongCat-Flash-Lite",
) -> float:
    """
    Calculate Context Recall.
    
    Measures how much of the ground truth can be inferred from
    the retrieved context.
    
    Formula: CR = (inferable sentences) / (total sentences in ground truth)
    
    Args:
        question: The user's question.
        ground_truth: The expected answer (ground truth).
        retrieval_context: List of retrieved context strings.
        api_key: API key for LLM.
        base_url: Base URL for LLM API.
        model_name: LLM model name.
    
    Returns:
        Context recall score in [0, 1].
    """
    if not ground_truth or not retrieval_context:
        return 0.0
    
    # 将 ground_truth 分割成句子
    sentences = _split_into_sentences(ground_truth)
    if not sentences:
        return 0.0
    
    # 判断每个句子是否能从上下文中推断
    context_text = "\n\n".join(retrieval_context)
    inferable_count = 0
    
    for sentence in sentences:
        if _can_infer_from_context(sentence, context_text, api_key, base_url, model_name):
            inferable_count += 1
    
    return inferable_count / len(sentences)
```

### 3.4 优化 Answer Relevancy 计算

**当前方式保留，添加 RAGAS 方式作为备选**:

```python
def calculate_answer_relevancy_ragas_style(
    question: str,
    answer: str,
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
    model_name: str = "LongCat-Flash-Lite",
    num_generated_questions: int = 3,
    embedding_model: str = "BAAI/bge-large-zh-v1.5",
) -> float:
    """
    Calculate Answer Relevancy using RAGAS-style approach.
    
    1. Generate n pseudo-questions from the answer
    2. Calculate cosine similarity between original question and each pseudo-question
    3. Return average similarity
    
    Args:
        question: The original question.
        answer: The generated answer.
        api_key: API key for LLM.
        base_url: Base URL for LLM API.
        model_name: LLM model name.
        num_generated_questions: Number of pseudo-questions to generate.
        embedding_model: Embedding model for similarity calculation.
    
    Returns:
        Answer relevancy score in [0, 1].
    """
    if not answer or not question:
        return 0.0
    
    # 生成伪问题
    pseudo_questions = _generate_pseudo_questions(
        answer, num_generated_questions, api_key, base_url, model_name
    )
    
    if not pseudo_questions:
        return 0.0
    
    # 计算余弦相似度
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer(embedding_model)
    
    original_embedding = embedder.encode([question])
    pseudo_embeddings = embedder.encode(pseudo_questions)
    
    similarities = cosine_similarity(original_embedding, pseudo_embeddings)[0]
    
    # RAGAS 使用 mean，但也可以用 max
    return float(np.mean(similarities))
```

### 3.5 添加问题有效性检查

**新增功能**:

```python
@dataclass
class QuestionValidity:
    """问题有效性评估结果"""
    is_valid: bool
    reason: str
    expected_sources_in_corpus: bool
    answerable: bool  # 是否可以基于检索库回答

def validate_question(
    question: Dict[str, Any],
    corpus_sources: Set[str],
) -> QuestionValidity:
    """
    验证测试问题的有效性。
    
    Args:
        question: 测试问题字典
        corpus_sources: 检索库中的文档集合
    
    Returns:
        QuestionValidity 对象
    """
    expected_sources = question.get("expected_sources", [])
    if not expected_sources:
        expected_sources = question.get("source_files", [])
    
    # 检查期望文档是否在检索库中
    normalized_expected = {normalize_source(s) for s in expected_sources}
    normalized_corpus = {normalize_source(s) for s in corpus_sources}
    
    sources_in_corpus = bool(normalized_expected & normalized_corpus)
    
    if not sources_in_corpus:
        return QuestionValidity(
            is_valid=False,
            reason="expected_sources not in corpus",
            expected_sources_in_corpus=False,
            answerable=False,
        )
    
    return QuestionValidity(
        is_valid=True,
        reason="valid",
        expected_sources_in_corpus=True,
        answerable=True,
    )
```

### 3.6 优化测试集生成

**修改文件**: `src/test_generator.py`

**修改内容**:

1. 生成问题时验证 `expected_sources` 在检索库中
2. 添加 `valid` 字段标记问题有效性
3. 支持 "unanswerable" 问题类型

### 3.7 增强实验报告

**修改文件**: `eval/experiment_reporter.py`

**新增内容**:

1. 有效问题统计
2. 按问题难度分类的指标
3. "无法回答"问题的统计
4. Context Precision 和 Context Recall 指标

***

## 四、实施步骤

### Phase 1: 修复核心 Bug（高优先级）

1. **修复 NDCG 计算**

   * 添加去重逻辑

   * 添加边界检查

   * 编写单元测试

2. **添加单元测试**

   * 测试 NDCG 计算正确性

   * 测试边界情况（重复文档、空列表等）

### Phase 2: 添加业界标准指标（高优先级）

1. **添加 Context Precision**

   * 实现 LLM-as-a-judge 判断

   * 实现加权累积精度计算

   * 添加单元测试

2. **添加 Context Recall**

   * 实现 ground truth 句子分割

   * 实现可推断性判断

   * 添加单元测试

### Phase 3: 优化现有指标（中优先级）

1. **优化 Answer Relevancy**

   * 保留当前 LLM 直接评分方式

   * 添加 RAGAS 风格的伪问题方式作为备选

2. **优化 Faithfulness**

   * 当前实现已与 RAGAS 类似

   * 考虑添加 HHEM-2.1-Open 作为备选

### Phase 4: 完善评测流程（中优先级）

1. **添加问题有效性检查**

   * 实现验证函数

   * 在评测时过滤无效问题

2. **优化测试集生成**

   * 验证 expected\_sources 存在性

   * 标记问题有效性

3. **增强实验报告**

   * 添加有效问题统计

   * 添加分类统计

   * 添加新指标展示

***

## 五、预期效果

### 5.1 指标对齐

| 指标类别 | 当前                             | 优化后                                                         |
| ---- | ------------------------------ | ----------------------------------------------------------- |
| 检索指标 | Hit Rate, MRR, NDCG (有Bug)     | Hit Rate, MRR, NDCG (修复), Context Precision, Context Recall |
| 生成指标 | Faithfulness, Answer Relevancy | Faithfulness, Answer Relevancy (两种方式), Answer Correctness   |

### 5.2 质量提升

1. **NDCG 指标正确**：值在 \[0, 1] 范围内
2. **Context Precision/Recall**：与 RAGAS/DeepEval 对齐
3. **问题有效性**：过滤无效问题，指标更真实
4. **报告更清晰**：分类统计，便于分析

### 5.3 测试覆盖

* 所有指标函数有单元测试

* 边界情况有测试覆盖

* 与 RAGAS 结果对比验证

***

## 六、参考资源

1. **RAGAS Documentation**: <https://docs.ragas.io/>
2. **DeepEval Documentation**: <https://www.deepeval.com/docs/>
3. **RAGAS Faithfulness**: <https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/>
4. **DeepEval Contextual Precision**: <https://www.deepeval.com/docs/metrics-contextual-precision>

