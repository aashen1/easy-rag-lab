# MVP RAG + Baseline 评测 - 规格说明

## 1. 项目概述

### 1.1 目标
构建最小可运行的 RAG（检索增强生成）系统，并建立 baseline 评测基准，为后续优化提供对照依据。

### 1.2 范围
- **包含**：基础 RAG 链路、评测系统、测试集构建
- **不包含**：任何优化手段（混合检索、重排、语义分块等）

### 1.3 技术栈
- **PDF 解析**：pymupdf4llm
- **分块策略**：固定长度分块（overlap=0）
- **Embedding**：BAAI/bge-large-zh-v1.5（本地）
- **向量存储**：Qdrant（本地持久化）
- **LLM**：Anthropic SDK 调用 LongCat API
- **评测框架**：RAGAS
- **测试框架**：pytest

---

## 2. 系统架构

### 2.1 Pipeline 架构

```
PDF 文件
    ↓
[PDF Parser] → Markdown 文本
    ↓
[Chunker] → 固定长度 chunks
    ↓
[Embedder] → 向量
    ↓
[Vector Store] → Qdrant 索引
    ↓
[Retriever] → Top-K chunks
    ↓
[LLM Generator] → 最终回答
```

### 2.2 目录结构

```
ash-easy-rag/
├── config.yaml              # 超参数配置
├── .env.example             # 环境变量模板
├── main.py                  # 主入口（CLI）
├── src/
│   ├── __init__.py
│   ├── parser.py            # PDF 解析模块
│   ├── chunker.py           # 分块模块
│   ├── embedder.py          # Embedding 模块
│   ├── indexer.py           # 向量索引模块
│   ├── retriever.py         # 检索模块
│   ├── generator.py         # LLM 生成模块
│   └── pipeline.py          # 完整流水线
├── eval/
│   ├── __init__.py
│   ├── test_data.json       # 测试集（Q&A pairs）
│   ├── run_eval.py          # 评测脚本
│   └── results/             # 评测结果
│       └── baseline_report.json
├── tests/
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_chunker.py
│   ├── test_embedder.py
│   ├── test_indexer.py
│   ├── test_retriever.py
│   ├── test_generator.py
│   └── test_pipeline.py
├── notes/
│   └── baseline_results.md  # Baseline 评测报告
└── data/
    ├── raw/                 # 原始 PDF（已存在）
    ├── parsed/              # 解析后的 Markdown
    ├── chunks/              # 分块后的 JSONL
    └── vector_store/        # Qdrant 持久化
```

---

## 3. 模块详细设计

### 3.1 配置管理（config.yaml）

```yaml
# PDF 解析
parser:
  input_dir: "data/raw"
  output_dir: "data/parsed"

# 分块
chunker:
  input_dir: "data/parsed"
  output_dir: "data/chunks"
  chunk_size: 512        # tokens
  chunk_overlap: 0       # tokens

# Embedding
embedding:
  model_name: "BAAI/bge-large-zh-v1.5"
  device: "cuda"         # or "cpu"
  batch_size: 32

# 向量存储
vector_store:
  type: "qdrant"
  collection_name: "financial_reports"
  persist_dir: "data/vector_store"
  distance: "Cosine"

# 检索
retrieval:
  top_k: 5

# LLM
llm:
  provider: "anthropic"  # 使用 Anthropic SDK
  model: "claude-3-5-sonnet-20241022"  # 或其他模型
  api_base: "https://api.longcat.ai/v1"  # LongCat API endpoint
  temperature: 0.0
  max_tokens: 1024

# 评测
evaluation:
  test_data_path: "eval/test_data.json"
  results_dir: "eval/results"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

### 3.2 环境变量（.env.example）

```env
# LongCat API Configuration
LONGCAT_API_KEY=your_api_key_here
LONGCAT_API_BASE=https://api.longcat.ai/v1

# Optional: Hugging Face
HF_HOME=./.cache/huggingface
```

### 3.3 PDF 解析模块（src/parser.py）

**功能**：将 PDF 转换为 Markdown 格式

**输入**：`data/raw/` 下的 PDF 文件

**输出**：`data/parsed/` 下的 `.md` 文件

**核心函数**：

```python
def parse_pdf(pdf_path: str) -> str:
    """
    使用 pymupdf4llm 解析 PDF 为 Markdown

    Args:
        pdf_path: PDF 文件路径

    Returns:
        Markdown 格式的文本

    Raises:
        FileNotFoundError: PDF 文件不存在
        Exception: 解析失败
    """
    pass

def parse_all_pdfs(input_dir: str, output_dir: str) -> None:
    """
    批量解析目录下所有 PDF

    Args:
        input_dir: 输入目录
        output_dir: 输出目录
    """
    pass
```

**异常处理**：
- 文件不存在：记录日志，跳过该文件
- 解析失败：记录错误日志，继续处理下一个文件

### 3.4 分块模块（src/chunker.py）

**功能**：将 Markdown 文本按固定长度分块

**输入**：`data/parsed/` 下的 `.md` 文件

**输出**：`data/chunks/` 下的 `.jsonl` 文件

**核心函数**：

```python
def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 0
) -> List[Dict[str, Any]]:
    """
    将文本按固定 token 数分块

    Args:
        text: 输入文本
        chunk_size: 每块最大 token 数
        overlap: 相邻块重叠 token 数

    Returns:
        chunk 列表，每个 chunk 包含 text 和 metadata
    """
    pass

def process_parsed_files(
    input_dir: str,
    output_dir: str,
    chunk_size: int,
    overlap: int
) -> None:
    """
    批量处理解析后的文件
    """
    pass
```

**实现要点**：
- 使用 `tiktoken` 进行 token 计数
- 每个 chunk 包含：`chunk_id`, `text`, `metadata`
- metadata 包含：`source`, `category`, `chunk_index`, `char_count`, `token_count`

### 3.5 Embedding 模块（src/embedder.py）

**功能**：将文本转换为向量

**核心函数**：

```python
class Embedder:
    def __init__(self, model_name: str, device: str = "cuda"):
        """
        初始化 Embedding 模型

        Args:
            model_name: 模型名称
            device: 运行设备
        """
        pass

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        批量生成文本向量

        Args:
            texts: 文本列表

        Returns:
            向量矩阵 (n_texts, embedding_dim)
        """
        pass

    def embed_query(self, query: str) -> np.ndarray:
        """
        生成查询向量
        """
        pass
```

### 3.6 向量索引模块（src/indexer.py）

**功能**：构建和管理 Qdrant 向量索引

**核心函数**：

```python
class VectorIndexer:
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Qdrant 客户端
        """
        pass

    def create_collection(self, collection_name: str, vector_size: int) -> None:
        """
        创建向量集合
        """
        pass

    def index_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: np.ndarray
    ) -> None:
        """
        将 chunks 和向量写入 Qdrant
        """
        pass

    def build_index(
        self,
        chunks_dir: str,
        embedder: Embedder,
        rebuild: bool = False
    ) -> None:
        """
        从 chunks 构建完整索引
        """
        pass
```

### 3.7 检索模块（src/retriever.py）

**功能**：从向量存储中检索相关 chunks

**核心函数**：

```python
class Retriever:
    def __init__(self, indexer: VectorIndexer, embedder: Embedder, top_k: int):
        """
        初始化检索器
        """
        pass

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """
        检索 top-k 相关 chunks

        Args:
            query: 查询文本

        Returns:
            检索结果列表，每个结果包含 chunk 和 score
        """
        pass
```

### 3.8 LLM 生成模块（src/generator.py）

**功能**：基于检索结果生成回答

**核心函数**：

```python
class Generator:
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 LLM 客户端（使用 Anthropic SDK）
        """
        pass

    def generate(
        self,
        query: str,
        contexts: List[str]
    ) -> str:
        """
        基于上下文生成回答

        Args:
            query: 用户问题
            contexts: 检索到的上下文列表

        Returns:
            生成的回答
        """
        pass
```

**Prompt 模板**：

```
你是一个金融研报分析助手。请基于以下参考资料回答用户问题。

参考资料：
{contexts}

用户问题：{query}

请提供准确、简洁的回答。如果参考资料中没有相关信息，请明确说明。
```

### 3.9 完整流水线（src/pipeline.py）

**功能**：串联所有模块，提供端到端 RAG 功能

**核心函数**：

```python
class RAGPipeline:
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化 RAG 流水线

        Args:
            config_path: 配置文件路径
        """
        pass

    def query(self, question: str) -> Dict[str, Any]:
        """
        执行完整 RAG 查询

        Args:
            question: 用户问题

        Returns:
            {
                "answer": "生成的回答",
                "contexts": ["检索到的上下文"],
                "scores": [相似度分数]
            }
        """
        pass

    def build_index(self, rebuild: bool = False) -> None:
        """
        构建/重建向量索引
        """
        pass
```

---

## 4. 评测系统设计

### 4.1 测试集构建（eval/test_data.json）

**格式**：

```json
[
  {
    "id": "q001",
    "question": "贵州茅台2023年的营业收入是多少？",
    "category": "fact_extraction",
    "source_docs": ["贵州茅台_2023_年度报告.pdf"],
    "expected_answer": "贵州茅台2023年营业收入为XXX亿元。"
  },
  {
    "id": "q002",
    "question": "白酒行业2024年的发展趋势是什么？",
    "category": "summary",
    "source_docs": ["中金公司_2024_白酒行业研报.pdf"],
    "expected_answer": "白酒行业2024年发展趋势包括..."
  }
]
```

**问题类型**：
- `fact_extraction`：事实提取（数字、日期、名称等）
- `summary`：信息总结
- `comparison`：信息对比
- `analysis`：简单分析

**数量**：至少 20 个问答对

### 4.2 评测脚本（eval/run_eval.py）

**功能**：运行完整评测并生成报告

**核心流程**：

```python
def run_evaluation(
    pipeline: RAGPipeline,
    test_data: List[Dict],
    output_dir: str
) -> Dict[str, Any]:
    """
    执行评测

    Args:
        pipeline: RAG 流水线
        test_data: 测试数据
        output_dir: 结果输出目录

    Returns:
        评测结果字典
    """
    results = []

    for item in test_data:
        # 执行查询
        response = pipeline.query(item["question"])

        # 计算检索指标
        retrieval_metrics = calculate_retrieval_metrics(
            retrieved_docs=response["contexts"],
            expected_docs=item["source_docs"]
        )

        # 计算生成指标
        generation_metrics = calculate_generation_metrics(
            question=item["question"],
            answer=response["answer"],
            contexts=response["contexts"]
        )

        results.append({
            "id": item["id"],
            "question": item["question"],
            "answer": response["answer"],
            "retrieval_metrics": retrieval_metrics,
            "generation_metrics": generation_metrics
        })

    # 汇总统计
    summary = aggregate_metrics(results)

    # 保存结果
    save_results(summary, output_dir)

    return summary
```

### 4.3 评测指标

#### 4.3.1 检索质量指标

**Hit Rate**：
```python
def calculate_hit_rate(
    retrieved_docs: List[str],
    expected_docs: List[str]
) -> float:
    """
    计算命中率

    Args:
        retrieved_docs: 检索到的文档列表
        expected_docs: 期望的文档列表

    Returns:
        命中率（0-1）
    """
    retrieved_set = set(retrieved_docs)
    expected_set = set(expected_docs)
    return len(retrieved_set & expected_set) / len(expected_set)
```

**MRR (Mean Reciprocal Rank)**：
```python
def calculate_mrr(
    retrieved_docs: List[str],
    expected_docs: List[str]
) -> float:
    """
    计算平均倒数排名
    """
    for i, doc in enumerate(retrieved_docs):
        if doc in expected_docs:
            return 1.0 / (i + 1)
    return 0.0
```

**NDCG (Normalized Discounted Cumulative Gain)**：
```python
def calculate_ndcg(
    retrieved_docs: List[str],
    expected_docs: List[str],
    k: int = 5
) -> float:
    """
    计算 NDCG@k
    """
    # 实现细节
    pass
```

#### 4.3.2 生成质量指标

使用 RAGAS 框架计算：

**Faithfulness**：回答是否忠实于上下文

**Answer Relevancy**：回答与问题的相关性

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

def calculate_generation_metrics(
    question: str,
    answer: str,
    contexts: List[str]
) -> Dict[str, float]:
    """
    使用 RAGAS 计算生成质量指标
    """
    data = {
        "question": [question],
        "answer": [answer],
        "contexts": [contexts]
    }

    result = evaluate(
        data,
        metrics=[faithfulness, answer_relevancy]
    )

    return {
        "faithfulness": result["faithfulness"],
        "answer_relevancy": result["answer_relevancy"]
    }
```

### 4.4 评测报告格式

**baseline_report.json**：

```json
{
  "timestamp": "2026-04-15T10:30:00",
  "config": {
    "chunk_size": 512,
    "chunk_overlap": 0,
    "embedding_model": "BAAI/bge-large-zh-v1.5",
    "top_k": 5,
    "llm_model": "claude-3-5-sonnet-20241022"
  },
  "summary": {
    "total_questions": 20,
    "retrieval_metrics": {
      "avg_hit_rate": 0.85,
      "avg_mrr": 0.72,
      "avg_ndcg": 0.78
    },
    "generation_metrics": {
      "avg_faithfulness": 0.88,
      "avg_answer_relevancy": 0.82
    }
  },
  "detailed_results": [
    {
      "id": "q001",
      "question": "...",
      "answer": "...",
      "retrieval_metrics": {
        "hit_rate": 1.0,
        "mrr": 1.0,
        "ndcg": 1.0
      },
      "generation_metrics": {
        "faithfulness": 0.95,
        "answer_relevancy": 0.90
      }
    }
  ]
}
```

---

## 5. 主入口设计（main.py）

**CLI 接口**：

```python
import argparse
from src.pipeline import RAGPipeline

def main():
    parser = argparse.ArgumentParser(description="RAG System CLI")
    parser.add_argument("--query", type=str, help="Query question")
    parser.add_argument("--build-index", action="store_true", help="Build vector index")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild index from scratch")
    parser.add_argument("--config", type=str, default="config.yaml", help="Config file path")

    args = parser.parse_args()

    pipeline = RAGPipeline(config_path=args.config)

    if args.build_index or args.rebuild:
        pipeline.build_index(rebuild=args.rebuild)
        print("Index built successfully")

    if args.query:
        result = pipeline.query(args.query)
        print(f"Answer: {result['answer']}")
        print(f"\nSources:")
        for i, ctx in enumerate(result['contexts'], 1):
            print(f"{i}. {ctx[:100]}...")

if __name__ == "__main__":
    main()
```

**使用示例**：

```bash
# 构建索引
pixi run python main.py --build-index

# 查询
pixi run python main.py --query "贵州茅台2023年的营业收入是多少？"

# 重建索引
pixi run python main.py --rebuild
```

---

## 6. 测试策略

### 6.1 单元测试

每个模块对应一个测试文件：

- `tests/test_parser.py`：测试 PDF 解析
- `tests/test_chunker.py`：测试分块逻辑
- `tests/test_embedder.py`：测试 Embedding 生成
- `tests/test_indexer.py`：测试向量索引
- `tests/test_retriever.py`：测试检索功能
- `tests/test_generator.py`：测试 LLM 生成
- `tests/test_pipeline.py`：测试完整流水线

### 6.2 测试数据

- 使用小型测试 PDF（1-2 页）
- Mock LLM API 调用（避免实际消耗）
- 使用 fixture 管理测试数据

### 6.3 测试覆盖

- 正常流程
- 边界情况（空输入、超大文件等）
- 异常处理（文件不存在、API 错误等）

---

## 7. 开发流程

### 7.1 开发顺序

1. **基础设施**：配置文件、环境变量、日志配置
2. **数据准备**：准备测试 PDF 文件
3. **Pipeline 开发**（按顺序）：
   - PDF 解析
   - 分块
   - Embedding
   - 向量索引
   - 检索
   - LLM 生成
   - 完整流水线
4. **评测系统**：
   - 构建测试集
   - 实现评测脚本
   - 运行评测
5. **文档**：编写 baseline 评测报告

### 7.2 提交策略

每个模块开发完成后独立提交：
- `feat: add PDF parser module`
- `feat: add chunker module`
- `feat: add embedder module`
- ...

---

## 8. 验收标准

### 8.1 功能验收

- [ ] `pixi run python main.py --query "..."` 能返回回答
- [ ] `pixi run python eval/run_eval.py` 能完成评测
- [ ] 所有测试通过：`pixi run pytest tests/ -v`

### 8.2 质量验收

- [ ] 所有公共函数有类型标注
- [ ] 所有公共函数有 docstring
- [ ] 所有 IO 操作有异常处理
- [ ] 使用 loguru 记录日志，无 print 语句
- [ ] 代码通过 autopep8 格式化

### 8.3 文档验收

- [ ] `notes/baseline_results.md` 包含完整评测报告
- [ ] 报告包含所有指标数值和分析

---

## 9. 风险与依赖

### 9.1 技术风险

- **LongCat API 可用性**：需要确认 API endpoint 和认证方式
- **GPU 资源**：本地 Embedding 模型需要 GPU
- **PDF 质量**：部分 PDF 可能解析效果不佳

### 9.2 外部依赖

- **LongCat API**：需要 API Key
- **Hugging Face**：下载 Embedding 模型
- **测试数据**：需要准备金融研报 PDF

---

## 10. 后续优化方向（Backlog）

本阶段完成后，可考虑以下优化：

1. **检索优化**：
   - 混合检索（BM25 + 向量）
   - Reranker 重排
   - 查询改写

2. **分块优化**：
   - 语义分块
   - 滑动窗口
   - 父子 chunk

3. **生成优化**：
   - Prompt 工程
   - HyDE
   - Multi-Query

4. **系统优化**：
   - 缓存机制
   - 并发处理
   - 监控告警

---

## 11. 参考资料

- [LongCat API 文档](plgd/ref-info/LongCat-API适配性分析.md)（待确认）
- [RAGAS 文档](https://docs.ragas.io/)
- [Qdrant 文档](https://qdrant.tech/documentation/)
- [LlamaIndex 文档](https://docs.llamaindex.ai/)
