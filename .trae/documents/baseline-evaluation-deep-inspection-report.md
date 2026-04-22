# RAG 基线链路深度勘察报告

> 基于实验：`exp_20260423_015208_baseline_evaluation`  
> 勘察日期：2026-04-23  
> 目标：从 PDF 到 LLM 答案的完整链路逐层解剖，识别关键节点、潜在问题与改进空间。

---

## 0. 实验概览

| 项目 | 值 |
|------|-----|
| 实验ID | `exp_20260423_015208_baseline_evaluation` |
| Meal | `m1_10p`（21份PDF的10%采样，seed=107） |
| 总页数 | 1,159 页 |
| 总Chunk数 | 2,790 个 |
| 测试问题数 | 20 |
| 检索指标 | Hit Rate=0.0000, MRR=0.0000, NDCG=0.0000 |
| 生成指标 | Faithfulness=0.8556, Answer Relevancy=0.8910 |

**核心矛盾**：生成质量看起来不错（Faithfulness 0.86, Relevancy 0.89），但检索指标全部为 0。这意味着 LLM 可能在“ hallucinate（幻觉）”或利用自身知识回答问题，而非真正依赖检索到的上下文。

---

## 1. 第一阶段：PDF 解析

### 1.1 配置参数

```yaml
parser:
  algorithm: pymupdf4llm
  pymupdf4llm:
    header: False
    footer: False
    page_separators: False
    write_images: False
    page_chunks: True        # 关键：按页输出
    force_text: True
    ignore_code: True
    use_ocr: True
    ocr_language: chi_sim+eng
```

### 1.2 解析流程

**入口**：`src/parser.py::parse_all_pdfs()` → `src/parsers/pymupdf4llm_parser.py::parse()`

```
PDF文件 → pymupdf4llm.to_markdown(page_chunks=True) → 每页一个dict → .pages.json
```

**输出格式**（`.pages.json`）：
```json
[
  {
    "metadata": {"page_number": 1},
    "text": "# 标题\n正文内容..."
  },
  {
    "metadata": {"page_number": 2},
    "text": "# 第二节\n更多内容..."
  }
]
```

### 1.3 关键发现与问题

#### 🔴 问题 1.1：解析器配置中的 `page_chunks` 与 `chunker` 的联动

配置中 `page_chunks: True` 表示解析器按页输出。但 `chunker` 配置为 `fixed` 策略，`chunk_size=512`。

在 `pipeline.py::build_index()` 中：
```python
if use_page_chunks and chunker_strategy != "semantic":
    chunk_results = process_parsed_files_page_aware(...)
```

这意味着系统走的是 **`page_aware_fixed`** 分块路径——**每页独立分块，跨页不连续**。

**影响**：
- 如果一页内容超过 512 tokens，会被切成多个 chunk，但这些 chunk 不会与下一页的内容重叠
- 表格、段落可能因分页而被强行切断
- **chunk_overlap=64 只在同一页内生效，不跨页**

#### 🟡 发现 1.2：OCR 开启但无后处理

`use_ocr: True` 表示 pymupdf4llm 会对扫描页使用 Tesseract OCR（chi_sim+eng）。但：
- OCR 后的文本质量无校验
- 金融报告中的表格数字、百分比可能在 OCR 中出错
- 无文本清洗流程（如去除页眉页脚虽然 `header/footer: False`，但这是解析器级别的）

#### 🟡 发现 1.3：文件名中的 `.pages.pages.json`

从实验结果的 `sources` 字段可以看到：
```
research_reports\\2026现代女性精力管理现状报告.pages.pages.json
```

文件名出现了 **`.pages.pages.json`** 的重复后缀。这说明在 `process_parsed_files_page_aware` 中，`source_name = relative_path.with_suffix("").stem` 的处理方式可能导致了后缀处理异常。

**代码位置**：`src/chunker.py::process_parsed_files_page_aware()` 第 379 行：
```python
source_name = relative_path.with_suffix("").stem
# relative_path = "xxx.pages.json"
# .with_suffix("") -> "xxx.pages"
# .stem -> "xxx"  (在Windows上Path.stem的行为)
```

但实际上输出文件名是：
```python
output_file = output_path / relative_path.with_suffix(".jsonl")
# "xxx.pages.json" -> "xxx.pages.jsonl"
```

而 `source_name` 用于生成 `chunk_id`：
```python
chunk_id = f"{source_name}_{chunk_index_str}"
# source_name = "xxx.pages"  (因为 with_suffix("") 去掉了 .json，剩下 .pages)
```

这导致 `chunk_id` 中包含了 `.pages`，但这不是致命问题。

---

## 2. 第二阶段：文档分块 (Chunking)

### 2.1 配置参数

```yaml
chunker:
  strategy: fixed
  chunk_size: 512
  chunk_overlap: 64
```

### 2.2 分块流程

**入口**：`src/chunker.py::chunk_text_page_aware()` → `chunk_text()`

```
.pages.json (每页一个text) → tiktoken编码(cl100k_base) → 按512 tokens切片 → 每页内前后重叠64 tokens → .jsonl
```

**核心代码**（`src/chunker.py::chunk_text()` 第 72-111 行）：

```python
tokens = encoding.encode(text)          # 整页文本编码为token序列
total_tokens = len(tokens)

while start < total_tokens:
    end = min(start + chunk_size, total_tokens)   # 取512个token
    chunk_tokens = tokens[start:end]
    chunk_text_decoded = encoding.decode(chunk_tokens)  # 解码回文本
    
    # ... 记录 metadata ...
    
    if end >= total_tokens:
        break
    start = end - overlap if overlap > 0 else end   # 下一chunk回退64个token
```

### 2.3 Chunk 元数据结构

```json
{
  "chunk_id": "source_name_p1_000",
  "text": "chunk文本内容...",
  "metadata": {
    "source": "relative/path.pages.json",
    "page_number": 1,
    "category": "research_reports",
    "strategy": "page_aware_fixed",
    "chunk_index": "p1_000",
    "char_count": 1200,
    "token_count": 512,
    "start_token": 0,
    "end_token": 512
  }
}
```

### 2.4 关键发现与问题

#### 🔴 问题 2.1：chunk_overlap 配置不一致

**实验报告中显示 `chunk_overlap: 64`**，但在 `meal_snapshot.json` 中：
```json
"chunker": {
  "chunk_size": 512,
  "chunk_overlap": 64,
  "encoding": "cl100k_base"
}
```

而实验报告的描述中同时出现了：
- "基线配置 (chunk_size: 512, chunk_overlap: 0)" —— 在 `variant_description` 中
- "Chunking: fixed (size=512, overlap=64)" —— 在 Technology Summary 中

**这是矛盾的！** 需要确认实际使用的是哪个值。从代码逻辑看，`config.yaml` 中配置的是 `chunk_overlap: 64`，但实验变体的描述写的是 `chunk_overlap: 0`。

#### 🔴 问题 2.2：跨页上下文断裂

由于 `page_aware_fixed` 策略**每页独立分块**，即使两页内容在语义上连续（如同一段文字跨页），它们之间也不会有任何 overlap。

**影响**：
- 一个问题如果涉及跨页的信息（如表格跨页、段落跨页），检索时只能拿到其中一页的片段
- 这可能导致信息不完整，影响答案质量

#### 🟡 发现 2.3：Chunk ID 生成方式

```python
chunk_id = f"{source_name}_{chunk_index_str}"
# 例如: "2026现代女性精力管理现状报告.pages_p1_000"
```

这个 ID 在 Qdrant 中作为 `payload.chunk_id` 存储，但 Qdrant 的 point ID 是简单的自增整数（`id=i`）。

**潜在问题**：如果重建索引，同一个 chunk 的 point ID 会变化，但 chunk_id 保持不变。

#### 🟡 发现 2.4：无去重机制

同一个 PDF 被解析后，如果内容有重复（如页眉页脚、免责声明），chunk 之间可能存在大量重复文本。目前无去重逻辑。

---

## 3. 第三阶段：Embedding 与向量索引

### 3.1 配置参数

```yaml
embedding:
  model_name: BAAI/bge-large-zh-v1.5
  device: cuda
  batch_size: 32
  query_instruction: null   # 但代码中会自动检测BGE模型并添加指令

vector_store:
  type: qdrant
  collection_name: financial_reports
  distance: Cosine
```

### 3.2 Embedding 流程

**入口**：`src/embedder.py::Embedder`

```python
# 文档文本编码
self._tokenizer(texts, padding=True, truncation=True, max_length=512)
outputs = self._model(input_ids=input_ids, attention_mask=attention_mask)
cls_embeddings = outputs.last_hidden_state[:, 0, :]  # 取CLS token
embeddings = torch.nn.functional.normalize(cls_embeddings, p=2, dim=1)  # L2归一化
```

**查询编码**（带指令前缀）：
```python
# 由于 query_instruction 为 null，代码自动检测：
if "bge" in model_name.lower():
    self.query_instruction = "为这个句子生成表示以用于检索相关文章："
    
prefixed_query = "为这个句子生成表示以用于检索相关文章：" + query
```

### 3.3 向量索引流程

**入口**：`src/indexer.py::VectorIndexer`

```
所有 .jsonl chunk 文件 → 读取 text → Embedder.embed_texts(batch_size=32) → Qdrant upsert
```

**Qdrant 存储结构**：
- Point ID: 自增整数 `0, 1, 2, ...`
- Vector: 1024 维（BGE-large 的 hidden_size）
- Payload:
  ```json
  {
    "chunk_id": "...",
    "text": "chunk文本",
    "metadata": {...}
  }
  ```

### 3.4 关键发现与问题

#### 🔴 问题 3.1：Embedding max_length 与 chunk_size 不匹配

- **Chunk size**: 512 tokens（基于 tiktoken/cl100k_base）
- **Embedding max_length**: 512 tokens（基于 BGE tokenizer）

**但这两个 tokenizer 不同！**
- tiktoken (cl100k_base) 是 OpenAI 的 tokenizer
- BGE tokenizer 是 Hugging Face 的 tokenizer

对于中文文本，两者的 token 切分方式可能不同。一个 512 tiktoken 的 chunk，在 BGE tokenizer 中可能超过 512，导致 **truncation（截断）**。

**影响**：
- Chunk 的尾部内容在 embedding 时被截断，导致向量表示不完整
- 检索时可能因此错过关键信息

#### 🟡 发现 3.2：查询指令前缀

BGE 模型推荐使用指令前缀，但当前配置 `query_instruction: null`。代码虽然会自动添加，但这是一个隐式行为，可能导致：
- 如果更换非 BGE 模型，指令前缀消失，检索质量可能下降
- 文档 embedding 时没有加指令，查询时加了指令，这是 BGE 的预期用法，但需要确认一致性

#### 🟡 发现 3.3：Qdrant 的 Distance 配置

配置为 `Cosine`，但 BGE 模型输出已经做了 L2 归一化：
```python
embeddings = torch.nn.functional.normalize(cls_embeddings, p=2, dim=1)
```

对于已归一化的向量，Cosine 相似度 = Dot Product。所以 `Cosine` 和 `Dot` 在此等价。

---

## 4. 第四阶段：检索 (Retrieval)

### 4.1 配置参数

```yaml
retrieval:
  method: vector
  top_k: 5
  score_threshold: 0
```

### 4.2 检索流程

**入口**：`src/retriever.py::Retriever.retrieve()`

```python
query_embedding = self.embedder.embed_query(query)  # 带指令前缀

search_results = self.indexer.client.query_points(
    collection_name=self.indexer.collection_name,
    query=query_embedding.tolist(),
    limit=self.top_k,        # 取 top 5
    with_payload=True,
).points
```

### 4.3 关键发现与问题

#### 🔴 问题 4.1：检索指标全部为 0 的根因分析

实验结果显示 `avg_hit_rate=0.0, avg_mrr=0.0, avg_ndcg=0.0`，但 LLM 仍然能回答问题。

**可能原因**：

1. **Source 路径格式不匹配**：
   - `expected_sources`: `research_reports/2026现代女性精力管理现状报告.pages.json`（正斜杠）
   - `actual_sources`: `research_reports\\2026现代女性精力管理现状报告.pages.pages.json`（反斜杠 + 双后缀）
   
   在 Windows 上，`relative_path` 使用反斜杠，而测试集中的 `source_files` 使用正斜杠。这导致 **source 匹配逻辑永远失败**。

2. **等价组 (Equivalence Group) 推断问题**：
   `meal_snapshot.json` 中定义了等价组，例如：
   ```json
   "2023年年度报告": [
     "annual_reports\\2023\\云南白药\\2023年年度报告_英文版_.pdf",
     "annual_reports\\2023\\格力电器\\2023年年度报告摘要.pdf",
     "annual_reports\\2023\\隆基绿能\\2023年年度报告摘要.pdf"
   ]
   ```
   
   这三份不同的报告被归为同一个等价组 "2023年年度报告"。但测试问题 q010 问的是"云南白药"，q011 问的是"隆基绿能"——它们共享同一个等价组名称，但内容完全不同。

3. **Hit Rate 计算方式**：
   从 `results/baseline.json` 看，每个问题的 `sources` 列表确实返回了正确的文档（如 q001 返回了现代女性精力管理报告），但 `hit_rate` 仍为 0。
   
   这说明 **hit rate 的计算逻辑有问题**，可能是路径格式不匹配导致匹配失败。

#### 🔴 问题 4.2：Top-K=5 可能不足以覆盖多文档问题

对于需要跨文档回答的问题（如 q008 钙钛矿电池对比），top-5 可能只返回了单文档的 chunks，导致信息不完整。

#### 🟡 发现 4.3：Score Threshold = 0

`score_threshold: 0` 意味着不过滤任何结果。即使相似度很低（如 0.1）的 chunk 也会被返回。这可能导致：
- 无关问题（如 q020 美联储加息）仍然返回了恒瑞医药的 chunks
- LLM 需要自行判断信息是否相关

---

## 5. 第五阶段：Prompt 构建与答案生成

### 5.1 配置参数

```yaml
generation:
  system_prompt: null
  max_context_tokens: null

llm_presets:
  default:
    model_name: LLM_MODEL_ID      # 实际使用 LongCat-Flash-Lite
    temperature: 0.0
    max_tokens: 1024
```

### 5.2 Prompt 构建流程

**入口**：`src/generator.py::Generator.generate()`

**System Prompt**（硬编码默认值）：
```
你是一个金融研报分析助手。请基于以下参考资料回答用户问题。

要求：
1. 回答要准确、简洁、专业
2. 如果参考资料中有相关信息，请基于资料回答
3. 如果参考资料中没有相关信息，请明确说明"根据提供的参考资料，我无法回答这个问题"
4. 回答时请引用具体的来源（如"根据贵州茅台2023年年度报告..."）
5. 直接以回答内容开头，禁止使用"好的"、"当然"、"我来"等对话性用语开头
```

**User Message 构建**（`src/generator.py` 第 195-211 行）：
```python
if sources:
    context_text = "\n\n".join(
        [
            f"参考资料 {i+1}（来源：{Path(sources[i]).stem if i < len(sources) else '未知'}）:\n{ctx}"
            for i, ctx in enumerate(contexts)
        ]
    )

user_message = f"""{context_text}

用户问题：{query}

请基于参考资料回答上述问题："""
```

**实际 Prompt 示例**（以 q001 为例）：
```
[System]
你是一个金融研报分析助手...

[User]
参考资料 1（来源：2026现代女性精力管理现状报告.pages）：
[chunk 1 文本]

参考资料 2（来源：2026现代女性精力管理现状报告.pages）：
[chunk 2 文本]

...（共5个参考资料）

用户问题：报告中提到中国女性就业人员占比是多少？

请基于参考资料回答上述问题：
```

### 5.3 LLM 调用

```python
message = self.client.messages.create(
    model=self.model_name,           # LongCat-Flash-Lite
    max_tokens=self.max_tokens,      # 1024
    temperature=self.temperature,    # 0.0
    system=system_prompt,
    messages=[{"role": "user", "content": user_message}],
)
```

### 5.4 关键发现与问题

#### 🔴 问题 5.1：System Prompt 与模型能力不匹配

System Prompt 要求：
- "回答时请引用具体的来源"
- "如果参考资料中没有相关信息，请明确说明"

但从实验结果看：
- q010（云南白药）的答案是：**"根据贵州茅台2023年年度报告摘要（参考资料1）..."** —— 模型引用了错误的来源！
- q014（工行2024）的答案是：**"根据工商银行2025年度报告摘要（参考资料1）..."** —— 模型引用了2025年报告来回答2024年的问题
- q004（NCM523价格）模型回答"无法回答"，但 Faithfulness 只有 0.83

这说明：
1. **模型无法可靠地识别 source 的正确性**
2. **模型可能在编造来源引用**
3. 即使 `temperature=0.0`，模型仍然会产生幻觉

#### 🔴 问题 5.2：Context 中的 Source 名称不准确

```python
f"来源：{Path(sources[i]).stem}"
```

对于 `research_reports\\2026现代女性精力管理现状报告.pages.pages.json`，`Path.stem` 会得到 `2026现代女性精力管理现状报告.pages`。

这导致 LLM 看到的来源名称是 **"2026现代女性精力管理现状报告.pages"**，而不是更清晰的名称。

#### 🔴 问题 5.3：无 Context 截断机制

`max_context_tokens: null` 表示不限制上下文长度。

从 token_summary 看：
- 平均 input_tokens: ~1650（含 system_prompt + 5个context + query）
- 最高 input_tokens: 2112（q013 五粮液）

虽然当前未超限，但如果 top_k 增大或 chunk_size 增大，可能超出模型上下文限制。

#### 🟡 发现 5.4：Token 使用统计

| 类别 | Input Tokens | Output Tokens | Total |
|------|-------------|---------------|-------|
| RAG QA (20 questions) | 32,987 | 3,310 | 36,297 |
| Test Generation | 91,123 | 4,943 | 96,066 |
| Report Generation | 6,656 | 1,473 | 8,129 |
| **总计** | **130,766** | **9,726** | **140,492** |

测试生成消耗了 68% 的 token，这是预期的（用 LLM 生成测试问题）。

RAG QA 中，context tokens 占绝大部分（29,568 / 32,987 = 90%）。

---

## 6. 关键问题汇总

### 🔴 严重问题（影响评测结果可靠性）

| 编号 | 问题 | 影响 | 位置 |
|------|------|------|------|
| P1 | **检索指标全部为0的根因**：Source 路径格式不匹配（Windows反斜杠 vs 正斜杠） | 无法正确计算 Hit Rate/MRR/NDCG，评测结果完全不可信 | `src/evaluator.py` 或评测逻辑 |
| P2 | **等价组推断错误**：不同公司的年报被归为同一等价组 | 测试问题的 expected_source 可能指向错误文档 | `meal_snapshot.json` 生成逻辑 |
| P3 | **LLM 来源引用幻觉**：模型编造来源名称或引用错误文档 | Faithfulness 指标可能虚高 | `src/generator.py` |
| P4 | **Embedding truncation**：tiktoken 512 tokens ≠ BGE tokenizer 512 tokens | Chunk 尾部信息在 embedding 时丢失 | `src/embedder.py` |

### 🟡 中等问题（影响回答质量）

| 编号 | 问题 | 影响 | 位置 |
|------|------|------|------|
| M1 | 跨页分块无 overlap | 跨页信息断裂，检索不完整 | `src/chunker.py` |
| M2 | chunk_overlap 配置矛盾 | 实际 overlap 值不确定 | `config.yaml` vs 实验描述 |
| M3 | Score threshold = 0 | 低质量 chunk 被返回，干扰 LLM | `config.yaml` |
| M4 | Source 名称包含 `.pages` 后缀 | 不美观，可能干扰 LLM | `src/generator.py` |
| M5 | 无上下文长度限制 | 可能超出模型上下文窗口 | `config.yaml` |

### 🟢 轻微问题（可优化）

| 编号 | 问题 | 影响 | 位置 |
|------|------|------|------|
| L1 | 文件名后缀重复 `.pages.pages.json` | 不美观 | `src/chunker.py` |
| L2 | OCR 后无文本质量校验 | 可能的 OCR 错误未被发现 | `src/parser.py` |
| L3 | 无 chunk 去重机制 | 重复内容占用索引空间 | `src/chunker.py` |

---

## 7. 链路数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RAG 基线链路数据流                                │
└─────────────────────────────────────────────────────────────────────────────┘

[Raw PDFs]
    │ 21份PDF, 1159页
    ▼
┌─────────────────┐
│  PDF Parser     │  pymupdf4llm.to_markdown(page_chunks=True)
│  src/parser.py  │  → .pages.json (每页一个dict)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   Chunker       │  tiktoken(cl100k_base) 编码
│ src/chunker.py  │  → 每页独立分块, 512 tokens, overlap 64
│                 │  → .jsonl (2790 chunks)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   Embedder      │  BAAI/bge-large-zh-v1.5
│ src/embedder.py │  → 1024维向量, L2归一化
│                 │  ⚠️ max_length=512 (BGE tokenizer)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Vector Store   │  Qdrant (Cosine距离)
│ src/indexer.py  │  → Collection: m_2f6d1d65436b
└─────────────────┘
    │
    │ Query: "中国女性就业人员占比是多少？"
    ▼
┌─────────────────┐
│   Retriever     │  embed_query() + query_points(limit=5)
│ src/retriever.py│  → 返回 top-5 chunks
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   Generator     │  System Prompt + 5个参考资料 + 用户问题
│ src/generator.py│  → LongCat-Flash-Lite (temp=0, max_tokens=1024)
└─────────────────┘
    │
    ▼
[Answer]
    "根据参考资料1，国家统计局数据显示，中国女性就业人员占比达43.5%。"
```

---

## 8. 下一步建议

1. **修复 Source 路径匹配问题**：统一使用 `Path.as_posix()` 进行路径比较，解决 Windows 反斜杠问题
2. **重新设计等价组推断逻辑**：避免将不同公司的年报归为同一组
3. **验证 chunk_overlap 实际值**：确认实验中实际使用的是 0 还是 64
4. **统一 Tokenizer**：Embedding 时使用与 chunker 相同的 tokenizer，避免 truncation
5. **增加跨页 overlap 选项**：在 `page_aware_fixed` 策略中支持跨页上下文保留
6. **改进 Source 引用格式**：清理 `.pages` 后缀，提供更清晰的来源名称
7. **增加 Score Threshold**：设置合理的阈值（如 0.3-0.5），过滤低质量检索结果
8. **增加 Context 截断保护**：设置 `max_context_tokens` 防止超限

---

## 9. 最高优先级的修复清单（立即执行）

> 目标：打通链路，产出第一份可信的评测结果。以下按阻塞优先级排序。

### 🔥 P0 — 阻塞级（必须先修，否则评测结果不可信）

#### P0-1：修复 Source 路径匹配问题（检索指标全部为0的根因）

**问题**：Windows 反斜杠路径与测试集正斜杠路径不匹配，导致 Hit Rate/MRR/NDCG 永远为 0。

**修复位置**：评测逻辑中的 source 匹配代码（可能在 `src/evaluator.py` 或实验运行器中）。

**修复方案**：
```python
# 在比较前统一归一化路径
from pathlib import Path

def normalize_source(path: str) -> str:
    """统一路径格式，消除 Windows/Linux 路径差异。"""
    return Path(path).as_posix().replace(".pages.pages.json", ".pages.json")

# 比较时
if normalize_source(actual_source) == normalize_source(expected_source):
    hit = True
```

**同时需要处理**：`sources` 列表中的 `.pages.pages.json` 双后缀问题（见 L1）。

**验证方式**：修复后重新跑 baseline 实验，确认 Hit Rate > 0。

---

#### P0-2：修复等价组（Equivalence Group）推断逻辑

**问题**：不同公司的年报被归为同一等价组（如 "2023年年度报告" 包含云南白药、格力电器、隆基绿能）。这导致 `expected_sources` 指向错误的文档，即使检索正确也会被判定为 miss。

**修复位置**：`src/meal.py` 或 `src/test_generator.py` 中的等价组推断逻辑。

**修复方案**：
- 等价组应基于 **文件路径的目录结构** 推断，而非仅基于文件名
- 或完全禁用等价组，使用精确的文件路径匹配
- 至少应将 `annual_reports/2023/云南白药/...` 和 `annual_reports/2023/隆基绿能/...` 视为不同组

**验证方式**：检查 `meal_snapshot.json` 中的 `equivalence_groups`，确保不同公司不在同一组。

---

#### P0-3：确认并统一 chunk_overlap 配置

**问题**：`config.yaml` 中 `chunk_overlap: 64`，但实验变体描述写 `chunk_overlap: 0`，存在矛盾。

**修复位置**：`config.yaml` 和实验配置生成逻辑。

**修复方案**：
- 检查 `src/chunker.py` 实际读取的是哪个值
- 统一配置，确保实验描述与实际行为一致
- 建议基线使用 `chunk_overlap: 64`（有 overlap 比无 overlap 更合理）

**验证方式**：在 `chunk_text()` 中加日志输出实际使用的 overlap 值。

---

### 🔥 P1 — 高优先级（严重影响回答质量）

#### P1-1：统一 Chunker 与 Embedder 的 Tokenizer

**问题**：Chunker 用 tiktoken (cl100k_base) 切 512 tokens，Embedder 用 BGE tokenizer 编码（max_length=512）。两者对中文切分不同，导致 chunk 尾部被静默截断。

**修复位置**：`src/chunker.py` 或 `src/embedder.py`。

**修复方案（二选一）**：
- **方案 A**：Chunker 改用 BGE 的 tokenizer 切分（推荐，更精确）
- **方案 B**：Embedder 的 `max_length` 设为大于 512（如 768），确保不截断

**验证方式**：对比同一个 chunk 的 tiktoken 长度和 BGE token 长度，确认差异。

---

#### P1-2：修复 Source 名称显示（清理 `.pages` 后缀）

**问题**：LLM 看到的来源名称是 `"2026现代女性精力管理现状报告.pages"`，不美观且可能干扰模型。

**修复位置**：`src/generator.py` 第 198 行。

**修复方案**：
```python
# 原代码
f"来源：{Path(sources[i]).stem if i < len(sources) else '未知'}"

# 修复后
clean_name = Path(sources[i]).stem.replace(".pages", "").replace(".json", "")
f"来源：{clean_name}"
```

---

#### P1-3：设置合理的 Score Threshold

**问题**：`score_threshold: 0` 导致即使相似度 0.1 的 chunk 也被返回，干扰 LLM。

**修复位置**：`config.yaml`。

**修复方案**：
- 先跑实验观察 score 分布
- 设置初始阈值如 `0.3` 或 `0.4`
- 对于 Cosine 相似度，0.3 意味着有一定相关性，0.5 意味着较强相关

---

### 🔥 P2 — 中优先级（优化体验与稳定性）

#### P2-1：增加跨页 Chunk Overlap

**问题**：`page_aware_fixed` 策略每页独立分块，跨页无 overlap，导致跨页信息断裂。

**修复位置**：`src/chunker.py::chunk_text_page_aware()`。

**修复方案**：
- 在页与页之间保留一定 overlap（如最后一页的最后 64 tokens 与下一页的前 64 tokens 重叠）
- 或提供 `cross_page_overlap` 配置选项

---

#### P2-2：增加 Context 截断保护

**问题**：`max_context_tokens: null` 表示不限制上下文长度，可能超出模型窗口。

**修复位置**：`config.yaml`。

**修复方案**：
- 设置 `max_context_tokens: 8192`（或根据模型上下文调整）
- `src/generator.py` 中已有 `_truncate_contexts()` 逻辑，只需开启配置

---

#### P2-3：修复文件名后缀重复问题

**问题**：`.pages.json` 被处理后变成 `.pages.pages.json`。

**修复位置**：`src/chunker.py::process_parsed_files_page_aware()` 第 391 行。

**修复方案**：
```python
# 原代码
output_file = output_path / relative_path.with_suffix(".jsonl")
# relative_path = "xxx.pages.json" -> "xxx.pages.jsonl"

# 修复后
output_file = output_path / relative_path.with_suffix("").with_suffix(".jsonl")
# "xxx.pages.json" -> "xxx.pages" -> "xxx.jsonl"
```

---

### 📋 修复执行顺序建议

| 顺序 | 修复项 | 预计影响 | 难度 |
|------|--------|----------|------|
| 1 | P0-1 路径匹配 | 检索指标从0变正常 | 低 |
| 2 | P0-2 等价组 | expected_source 更准确 | 中 |
| 3 | P0-3 chunk_overlap 确认 | 消除配置矛盾 | 低 |
| 4 | P1-1 统一 tokenizer | 减少信息截断 | 中 |
| 5 | P1-2 清理 source 名称 | LLM 引用更准确 | 低 |
| 6 | P1-3 score threshold | 减少低质量检索 | 低 |
| 7 | P2-1 跨页 overlap | 跨页信息更完整 | 中 |
| 8 | P2-2 context 截断 | 防止模型超限 | 低 |

**建议**：先完成 P0 三项，立即重跑 baseline 实验，验证检索指标是否正常。然后再逐步处理 P1/P2。

---

*本报告基于实验 `exp_20260423_015208_baseline_evaluation` 的完整数据与项目源码分析生成。*
