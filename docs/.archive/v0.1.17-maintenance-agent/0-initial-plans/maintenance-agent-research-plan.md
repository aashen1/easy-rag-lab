# 维修工 Agent 技术调研与初步框架设计

> 状态：Plan（v0.2 修订版）| 日期：2026-05-04
> 修订说明：根据用户反馈深度修订，核心变更——框架选型转向 LangGraph、架构策略改为共享单元抽象、Meal 体系扩展手动模式、Agent 权限提升

***

## 一、需求理解（已确认）

### 1.1 核心定位

"维修工"Agent 是一个**权限仅次于用户的系统管理员角色**，能够深度介入实验系统的每个环节，像拿扳手一样对 PDF 解析、分块、检索、生成等各阶段进行精细调整。它不是批量实验流程的替代品，而是"精修 case"阶段的手术刀——当用户需要对某个 PDF 甚至某页做深度诊断、对比、调优时，维修工出场。

### 1.2 核心能力需求（用户已确认）

| #   | 能力        | 用户确认的需求细节                                                |
| --- | --------- | -------------------------------------------------------- |
| C1  | 单文件/单页面处理 | 脱离 Meal 批量体系，手动指定单个 PDF、单页、甚至单表格                         |
| C2  | 全链路工具调用   | 可调用解析、分块、嵌入、检索、生成等所有链路工具                                 |
| C3  | 工具结果质量比较  | 对同一输入用不同工具/参数处理，比较结果差异                                   |
| C4  | 分块参数可配置   | chunk\_size、overlap、语义分块阈值等，预留父子块热插拔接口                   |
| C5  | 单步/多步执行   | 支持单步调用某个工具，也支持多步串联                                       |
| C6  | 轻量/全量双模式  | 轻量模式处理 1-2 个 PDF，全量模式同现有实验系统                             |
| C7  | LLM 自主决策  | Agent 通过系统提示词理解角色，根据用户指令自主判断工具选择；用户也可通过 Web UI 下拉菜单锁定工具链 |
| C8  | 结果反馈循环    | 用户发现问题时可回退到任意阶段重做，Agent 记住最优方案                           |
| C9  | 分析报告与维修日志 | 持久化维修日志和笔记，跨 session 积累经验，集成 Issue 系统                    |
| C10 | 用户交互      | Web UI 优先（下拉菜单指定工具链），CLI 辅助（调试用，指令代替按钮）                  |
| C11 | Meal 手动模式 | 扩展 Meal 体系支持手动指定 PDF（非随机抽样），向后兼容                         |
| C12 | 高权限操作     | 维修工权限高，可写回 Meal/Artifact，通过备份+白名单机制防误删                   |

### 1.3 已确认的设计决策

| 问题        | 用户决策                        | 设计影响                      |
| --------- | --------------------------- | ------------------------- |
| Q1 自主判断程度 | LLM 自主决策 + 用户可锁定            | 需要 LLM 推理能力 + 工具描述 schema |
| Q2 单页表格补强 | **必须支持单页级**，甚至单表格级          | PdfPlumberEnhancer 需改造    |
| Q3 交互界面   | Web UI 优先 + CLI 辅助          | 两套前端，共享后端                 |
| Q4 写回权限   | **高权限**，可写回 Meal            | 需要备份机制 + 白名单              |
| Q5 日志持久化  | **完整持久化** + 记忆系统 + Issue 集成 | 需要跨 session 存储方案          |

***

## 二、现有系统架构分析

### 2.1 全链路架构

```
PDF 文件
  │
  ▼ S1: 解析
ParserRegistry.get_composite() → parser.parse(pdf_path) → ParseResult
  │  产物: data/artifacts/{data_id}/parsed_{parser_hash}/*.md + *.pages.json
  ▼ S1.5: 表格增强
TableEnhancer.enhance(pdf_path, parse_result) → ParseResult
  │  当前: 全文档增强；需要: 单页/单表格增强
  ▼ S2: 分块
process_parsed_files_page_aware() → chunks JSONL
  │  产物: data/artifacts/{data_id}/chunks_{chunker_hash}/*.jsonl
  ▼ S3: 嵌入
Embedder.embed_documents(chunks) → vectors
  │
  ▼ S4: 索引
VectorIndexer.build_index(chunks_dir, embedder) → Qdrant collection
  │
  ▼ S5: 检索
Retriever.search(query) → ranked chunks
  │  (可选) BM25Retriever / HybridRetriever / Reranker
  ▼ S6: 生成
Generator.generate(query, contexts) → answer + sources
  │
  ▼ S7: 评测
BuiltinEvaluator / RagasEvaluator → metrics
```

### 2.2 现有模块单文件支持度

| 模块                               | 单文件支持            | 关键耦合点                      | 改造难度 |
| -------------------------------- | ---------------- | -------------------------- | ---- |
| `ParserRegistry.get_composite()` | ✅ 天然支持           | 无                          | 无需改造 |
| `BaseParser.parse(pdf_path)`     | ✅ 天然支持           | 无                          | 无需改造 |
| `TableEnhancer.enhance()`        | ✅ 单 PDF          | 全页遍历，不支持单页                 | 低    |
| `parse_all_pdfs_unified()`       | ❌ 全量             | 全量遍历 + 全局 manifest/pointer | 中    |
| `process_parsed_files*()`        | ✅ source\_filter | 无                          | 无需改造 |
| `chunk_text*()` 底层函数             | ✅ 纯函数            | 无                          | 无需改造 |
| `VectorIndexer.build_index()`    | ⚠️ 部分            | 缺少按 source 删除 points 的 API | 中    |
| `ArtifactCache.save_manifest()`  | ❌ 覆盖写入           | 不支持增量更新                    | 中    |
| `RAGPipeline.query()`            | ✅ 单问题            | 无                          | 无需改造 |
| `PipelineProfiler`               | ✅ 阶段级            | 无                          | 无需改造 |
| `case_diagnoser.diagnose()`      | ✅ 纯函数            | 无                          | 无需改造 |
| `ParserBenchmarkRunner`          | ✅ 单文件            | 仅覆盖 S1                     | 扩展即可 |
| `MealManager.create_meal()`      | ❌ 仅随机抽样          | 不支持手动指定 PDF 列表             | 中    |

### 2.3 最接近的参考模板

**`ParserBenchmarkRunner`**（[eval/parser\_benchmark/runner.py](file:///b:/project/w0-easy-rag/eval/parser_benchmark/runner.py)）是最接近维修工需求的现有架构：

- 单文件粒度处理
- 结果缓存（config hash）
- 可组合的 pipeline 配置
- 独立的指标计算和报告生成

但局限是：只覆盖 S1（解析），没有分块/检索/问答等后续阶段。

***

## 三、Agent 框架选型调研（修订版）

### 3.1 用户反馈后的重新评估

用户提出了关键质疑：**维修工需要"来回跳跃"的能力**——用户可能在分块阶段发现问题，要回退到解析阶段换一种解析器；甚至走到重排序阶段才发现是切块没切好，需要全部重来。这种**非线性、可回退、可跳转**的工作流，对编排框架的要求远超简单 DAG。

### 3.2 LangGraph 深度调研结果

通过查阅 LangGraph 官方文档（MCP 工具），以下能力与维修工需求高度匹配：

#### 3.2.1 StateGraph — 状态图编排

```python
from langgraph.graph import StateGraph, START, END

class MaintenanceState(TypedDict):
    pdf_path: str
    current_stage: str  # "parse" | "chunk" | "embed" | "index" | "retrieve" | "generate" | "evaluate"
    parse_results: dict  # parser_name → ParseResult
    chunk_results: dict  # strategy → chunks
    ...

workflow = StateGraph(MaintenanceState)
workflow.add_node("parse", parse_node)
workflow.add_node("chunk", chunk_node)
workflow.add_node("embed", embed_node)
workflow.add_node("index", index_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)
workflow.add_node("evaluate", evaluate_node)
workflow.add_node("decide_next", decide_next_node)  # LLM 决策节点

# 条件边：LLM 决定下一步去哪个阶段
workflow.add_conditional_edges("decide_next", route_decision, {
    "parse": "parse",
    "chunk": "chunk",
    "embed": "embed",
    "index": "index",
    "retrieve": "retrieve",
    "generate": "generate",
    "evaluate": "evaluate",
    "end": END,
})
```

**关键优势**：条件边 `add_conditional_edges()` 让 Agent 可以根据 LLM 决策或用户指令跳转到任意阶段，完美支持"来回跳跃"。

#### 3.2.2 Persistence — 持久化与断点续传

```python
from langgraph.checkpoint.memory import InMemorySaver
# 生产环境可用 SqliteSaver / PostgresSaver

checkpointer = InMemorySaver()
graph = workflow.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "maintenance-session-1"}}
result = graph.invoke(initial_state, config=config)
```

**关键优势**：

- 每个 super-step 自动保存 checkpoint
- 支持 `get_state_history()` 回溯任意历史状态
- 支持 `update_state()` 修改历史状态并从该点重新执行（time travel）
- 这就是"维修笔记"和"跨 session 记忆"的天然基础设施

#### 3.2.3 Interrupts — 人工干预

```python
from langgraph.types import interrupt, Command

def parse_node(state: MaintenanceState):
    result = parser.parse(state["pdf_path"])

    # 暂停，展示结果给用户，等待反馈
    user_feedback = interrupt({
        "message": "解析完成，请检查结果",
        "page_count": len(result.pages),
        "table_count": ...,
    })

    # 用户反馈后继续执行
    if user_feedback.get("action") == "retry_with_different_parser":
        return {"current_stage": "parse", "parser_name": user_feedback["parser_name"]}
    return {"parse_results": {...}, "current_stage": "chunk"}
```

**关键优势**：

- `interrupt()` 可在任意节点暂停，等待用户输入后继续
- 用户可以 approve / reject / edit 参数
- 完美支持"用户看到表格散了，告诉 Agent 换一种解析方式"的交互模式

#### 3.2.4 Memory Store — 跨 session 记忆

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
graph = workflow.compile(checkpointer=checkpointer, store=store)

# 在节点中存取记忆
def parse_node(state, *, store, config):
    user_id = config["configurable"]["user_id"]
    namespace = (user_id, "maintenance_notes")

    # 读取历史维修笔记
    memories = store.search(namespace)

    # 保存新的维修经验
    store.put(namespace, "case_001", {
        "pdf_type": "annual_report",
        "best_parser": "fitz_pdfplumber",
        "reason": "年报表格多，fitz+pdfplumber 组合效果最好",
    })
```

**关键优势**：跨 thread 的长期记忆，Agent 可以积累"哪种 PDF 适合哪种解析器"的经验。

#### 3.2.5 Tool Calling — LLM 工具调用

```python
from langchain.tools import tool

@tool
def parse_pdf(pdf_path: str, parser_name: str = "pymupdf4llm",
              enhancer_name: str | None = None) -> dict:
    """解析 PDF 文件。可选解析器: pymupdf4llm, fitz。可选增强器: pdfplumber。"""
    parser = ParserRegistry.get_composite(primary=parser_name, enhancer=enhancer_name)
    result = parser.parse(pdf_path)
    return {"page_count": len(result.pages), ...}

@tool
def chunk_pdf(parse_result: dict, strategy: str = "page_aware",
              chunk_size: int = 512, overlap: int = 0) -> dict:
    """对解析结果进行分块。可选策略: fixed, page_aware, semantic。"""
    ...

# LLM 绑定工具
llm_with_tools = llm.bind_tools([parse_pdf, chunk_pdf, ...])
```

**关键优势**：`@tool` 装饰器 + `bind_tools()` 让 LLM 自动选择工具和参数，Agent 的"自主判断"能力天然支持。

### 3.3 修订后的框架对比

| 维度               | LangGraph（修订后评估）                          | 自建框架（原方案）        |
| ---------------- | ----------------------------------------- | ---------------- |
| **非线性工作流**       | ✅ 条件边 + Command(goto=...)                 | ❌ 需自行实现回退/跳转     |
| **状态持久化**        | ✅ 内置 Checkpointer                         | ❌ 需自行实现          |
| **人工干预**         | ✅ interrupt() + Command(resume=...)       | ❌ 需自行实现          |
| **跨 session 记忆** | ✅ Memory Store                            | ❌ 需自行实现          |
| **LLM 工具调用**     | ✅ @tool + bind\_tools()                   | ❌ 需自行实现 ReAct 循环 |
| **Time Travel**  | ✅ get\_state\_history() + update\_state() | ❌ 无              |
| **与现有代码集成**      | ⚠️ 需适配 Anthropic 认证                       | ✅ 零摩擦            |
| **依赖引入**         | ⚠️ langgraph + langchain-core             | ✅ 零新增            |
| **学习曲线**         | ⚠️ 需要学习 LangGraph 概念                      | ✅ 纯 Python       |

### 3.4 修订后的推荐方案：LangGraph 为主 + 共享单元层

**推荐采用 LangGraph 作为 Agent 编排框架**，理由：

1. **非线性工作流是刚需**：用户明确要求"来回跳跃"能力——从分块回退到解析、从重排序回退到切块、全部重来。LangGraph 的条件边 + `Command(goto=...)` 天然支持这种跳转，自建框架需要大量工作才能实现同等能力。
2. **持久化和记忆是刚需**：用户要求维修日志、维修笔记、跨 session 积累经验。LangGraph 的 Checkpointer + Memory Store 开箱即用。
3. **人工干预是刚需**：用户要求"看到表格散了，告诉 Agent 换一种方式"。LangGraph 的 `interrupt()` 机制完美匹配。
4. **LLM 自主决策是刚需**：用户要求 Agent 能根据知识判断工具选择。LangGraph 的 `@tool` + `bind_tools()` 天然支持。
5. **沙盒环境，不怕依赖**：用户明确表示"这是一个 playground，随便发挥"，不需要担心生产环境的依赖约束。

**但有一个关键架构决策**：不使用 LangChain 的工具抽象层来包装现有代码，而是**先抽象共享单元层，再在共享单元上同时挂载 LangGraph @tool 和实验系统的调用**。这样避免两套并行代码，确保一致性。

### 3.5 Anthropic 认证适配方案

项目使用非标准 Anthropic 认证（`Authorization: Bearer` 而非 `x-api-key`）。适配方案：

```python
from langchain_anthropic import ChatAnthropic

# 方案 1: 通过环境变量适配
# LangChain 的 ChatAnthropic 支持 ANTHROPIC_API_KEY 环境变量
# 项目已有 create_anthropic_client()，可以提取 API key 传入

# 方案 2: 自定义 http_client
import httpx
from langchain_anthropic import ChatAnthropic

def create_langchain_anthropic_client(config: dict) -> ChatAnthropic:
    base_url = config.get("base_url", "https://api.anthropic.com")
    api_key = config.get("api_key")  # 从项目配置获取

    return ChatAnthropic(
        model=config.get("model", "claude-sonnet-4-20250514"),
        anthropic_api_key=api_key,
        anthropic_api_url=base_url,
        default_headers={"Authorization": f"Bearer {api_key}"},
    )
```

**适配难度**：低。LangChain 的 `ChatAnthropic` 支持自定义 `base_url` 和 `default_headers`，可以直接对接项目的 API 代理。

***

## 四、架构改造策略（修订版）

### 4.1 核心策略：共享单元抽象（取代"最小侵入胶水层"）

**原方案问题**：如果只在 Agent 侧写胶水代码包装现有模块，实验系统侧不变，那么：

- 实验系统优化时，胶水代码需要跟着改
- 两套并行链路，维护成本高
- 代码不一致风险

**新方案**：将现有模块中"恰好适合包装成工具"的部分**抽象为共享单元**，实验系统和 Agent 都调用这些共享单元。

```
                    ┌─────────────────┐
                    │   共享单元层     │
                    │ (src/core/ops/)  │
                    └───────┬─────────┘
                            │
                ┌───────────┼───────────┐
                │                       │
        ┌───────▼───────┐     ┌────────▼────────┐
        │  实验系统       │     │  维修工 Agent    │
        │  (eval/runner/) │     │  (src/agent/)   │
        │  调用共享单元    │     │  @tool 包装      │
        │  + Meal 编排    │     │  + LangGraph    │
        └────────────────┘     └─────────────────┘
```

**关键原则**：

- 共享单元是**纯函数或近纯函数**，无全局状态副作用
- 共享单元的粒度是"单个操作"（解析一个 PDF、分块一个解析结果、索引一组 chunks）
- 实验系统的批量编排逻辑（Meal、Variant、ExperimentConfig）留在实验系统侧
- Agent 的 LangGraph 编排逻辑留在 Agent 侧
- 两侧都通过共享单元访问核心算法，修改算法只需改一处

### 4.2 共享单元设计

#### 4.2.1 解析单元 `parse_pdf`

```python
# src/core/ops/parse.py

def parse_pdf(
    pdf_path: str,
    parser_name: str = "pymupdf4llm",
    enhancer_name: str | None = None,
    parser_options: dict | None = None,
    enhancer_options: dict | None = None,
) -> ParseResult:
    """解析单个 PDF 文件

    共享单元：实验系统和 Agent 都通过此函数调用解析功能。
    内部调用 ParserRegistry.get_composite() + parser.parse()。
    """
    parser = ParserRegistry.get_composite(
        primary=parser_name,
        enhancer=enhancer_name,
        primary_config=parser_options,
        enhancer_config=enhancer_options,
    )
    return parser.parse(pdf_path)


def enhance_page(
    pdf_path: str,
    page_number: int,
    existing_text: str,
    enhancer_name: str = "pdfplumber",
    enhancer_options: dict | None = None,
) -> str:
    """对单个页面执行表格增强

    新增能力：支持指定页码，只增强目标页的表格。
    """
    enhancer = ParserRegistry.get_enhancer(enhancer_name, enhancer_options)
    return enhancer.enhance_page(pdf_path, page_number, existing_text)
```

**实验系统侧调用**：`parse_all_pdfs_unified()` 内部改为调用 `parse_pdf()` 逐文件处理，而非自己管理 parser 实例。
**Agent 侧调用**：`@tool` 包装 `parse_pdf()` 和 `enhance_page()`。

#### 4.2.2 分块单元 `chunk_parsed`

```python
# src/core/ops/chunk.py

def chunk_parsed(
    parse_result: ParseResult,
    strategy: str = "page_aware",
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    model_name: str | None = None,
    cross_page_overlap: int = 0,
    similarity_threshold: float = 0.5,
    breakpoint_percentile: float | None = None,
    embedder: Any | None = None,
) -> list[dict[str, Any]]:
    """对单个 ParseResult 执行分块

    共享单元：统一入口，根据 strategy 分发到具体分块函数。
    """
    if strategy == "fixed":
        return _chunk_fixed(parse_result, chunk_size, overlap, encoding_name, model_name)
    elif strategy == "page_aware":
        return _chunk_page_aware(parse_result, chunk_size, overlap, encoding_name, model_name, cross_page_overlap)
    elif strategy == "semantic":
        return _chunk_semantic(parse_result, chunk_size, similarity_threshold, breakpoint_percentile, encoding_name, embedder)
    else:
        raise ValueError(f"Unknown chunking strategy: {strategy}")
```

#### 4.2.3 索引单元 `index_chunks` / `delete_and_reindex`

```python
# src/core/ops/index.py

def index_chunks(
    chunks: list[dict],
    embedder: Embedder,
    collection_name: str,
    batch_size: int = 32,
    source_filter: set | None = None,
) -> int:
    """将 chunks 索引到向量库

    共享单元：统一索引入口。
    """
    ...

def delete_source_and_reindex(
    source: str,
    new_chunks: list[dict],
    embedder: Embedder,
    collection_name: str,
) -> int:
    """删除指定 source 的旧向量并索引新 chunks

    新增能力：支持增量更新单个 source 的向量。
    """
    ...
```

#### 4.2.4 查询单元 `query_rag`

```python
# src/core/ops/query.py

def query_rag(
    question: str,
    pipeline: RAGPipeline,
) -> dict[str, Any]:
    """执行单次 RAG 查询

    共享单元：包装 RAGPipeline.query()，返回标准化结果。
    """
    return pipeline.query(question)
```

#### 4.2.5 评测单元 `evaluate_single`

```python
# src/core/ops/evaluate.py

def evaluate_single(
    question: str,
    answer: str,
    contexts: list[str],
    expected_answer: str | None = None,
    expected_sources: list[str] | None = None,
    metrics: list[str] | None = None,
    config: dict | None = None,
) -> dict[str, float]:
    """评测单个问答样本

    共享单元：包装 BuiltinEvaluator.evaluate_batch()。
    """
    ...
```

### 4.3 Meal 体系扩展：手动模式

当前 `MealManager.create_meal()` 只支持随机抽样（`sample_ratio` / `sample_count`）。需要新增手动指定模式：

```python
# src/meal/manager.py 扩展

def create_meal(
    self,
    name: str,
    pdf_files: list[str] | None = None,      # 新增：手动指定 PDF 列表
    sample_ratio: float | None = None,         # 原有：随机抽样比例
    sample_count: int | None = None,           # 原有：随机抽样数量
    sample_pages: int | None = None,           # 原有：按页数抽样
    source_dir: str | None = None,             # 新增：指定搜索目录
    file_pattern: str | None = None,           # 新增：文件名模式匹配（如 "*年报*"）
    tags: list[str] | None = None,             # 新增：标签（如 ["煤炭", "年报"]）
    description: str | None = None,            # 新增：描述
) -> MealConfig:
    """创建 Meal，支持手动指定和随机抽样两种模式

    向后兼容：如果只传 sample_ratio/sample_count，行为与原来完全一致。
    新增模式：传入 pdf_files 列表直接指定，或传入 source_dir + file_pattern 搜索。
    """
```

**Agent 侧使用**：

```python
@tool
def create_curated_meal(
    name: str,
    pdf_files: list[str],
    description: str | None = None,
) -> dict:
    """创建手动指定的 Meal（数据集）。

    适用于：用户说"给我挑三四份煤炭行业的企业年报"，
    Agent 根据知识找到对应 PDF，创建 Meal。
    """
    meal = MealManager.create_meal(name=name, pdf_files=pdf_files, description=description)
    return {"meal_name": meal.name, "file_count": len(meal.pdf_files)}
```

### 4.4 PdfPlumberEnhancer 单页增强改造

```python
# src/parsers/pdfplumber_enhancer.py 扩展

class PdfPlumberEnhancer(TableEnhancer):
    # ... 现有代码不变 ...

    def enhance_page(
        self,
        pdf_path: str,
        page_number: int,
        existing_text: str,
    ) -> str:
        """对单个页面执行表格增强

        Args:
            pdf_path: PDF 文件路径
            page_number: 1-indexed 页码
            existing_text: 该页已有的 Markdown 文本

        Returns:
            增强后的 Markdown 文本（表格部分被替换/补充）
        """
        page_count = self._get_page_count(pdf_path)
        tables_by_page = self._extract_all_tables(pdf_path, page_count)

        page_idx = page_number - 1  # 转为 0-indexed
        if page_idx not in tables_by_page or not tables_by_page[page_idx]:
            return existing_text

        enhanced_text = self._merge_tables_into_page(
            existing_text, tables_by_page[page_idx]
        )
        return enhanced_text
```

### 4.5 共享单元与现有模块的迁移路径

**迁移原则**：渐进式，不一次性重写

1. **Phase 1**：先创建共享单元函数（`src/core/ops/`），内部调用现有模块的底层函数
2. **Phase 2**：让 Agent 的 `@tool` 直接包装共享单元
3. **Phase 3**：逐步让实验系统也调用共享单元（替换直接调用底层函数的地方）
4. **Phase 4**：共享单元稳定后，底层函数可以重构为共享单元的内部实现

```
Phase 1:  共享单元 → 调用现有底层函数
Phase 2:  Agent @tool → 调用共享单元
Phase 3:  实验系统 → 调用共享单元（替换直接调用底层函数）
Phase 4:  底层函数 → 重构为共享单元的内部实现（可选）
```

***

## 五、代码变更范围（修订版）

### 5.1 新增文件

```
src/core/                            # 共享单元层（新增）
├── __init__.py
└── ops/                             # 操作单元
    ├── __init__.py
    ├── parse.py                     # parse_pdf(), enhance_page()
    ├── chunk.py                     # chunk_parsed()
    ├── embed.py                     # embed_chunks()
    ├── index.py                     # index_chunks(), delete_source_and_reindex()
    ├── query.py                     # query_rag()
    └── evaluate.py                  # evaluate_single()

src/agent/                           # 维修工 Agent 包（新增）
├── __init__.py                      # 公开 API 导出
├── graph.py                         # LangGraph StateGraph 定义
├── state.py                         # MaintenanceState TypedDict
├── nodes/                           # LangGraph 节点函数
│   ├── __init__.py
│   ├── parse_node.py                # 解析节点
│   ├── chunk_node.py                # 分块节点
│   ├── embed_node.py                # 嵌入节点
│   ├── index_node.py                # 索引节点
│   ├── retrieve_node.py             # 检索节点
│   ├── generate_node.py             # 生成节点
│   ├── evaluate_node.py             # 评测节点
│   ├── compare_node.py              # 对比节点
│   └── decide_node.py               # LLM 决策节点
├── tools/                           # LangChain @tool 定义
│   ├── __init__.py
│   ├── parse_tools.py               # parse_pdf, enhance_page
│   ├── chunk_tools.py               # chunk_parsed
│   ├── embed_tools.py               # embed_chunks
│   ├── index_tools.py               # index_chunks, delete_source_and_reindex
│   ├── query_tools.py               # query_rag
│   ├── evaluate_tools.py            # evaluate_single
│   ├── compare_tools.py             # compare_results
│   ├── meal_tools.py                # create_curated_meal, list_pdfs
│   └── issue_tools.py               # create_issue, list_issues
├── memory/                          # 记忆系统
│   ├── __init__.py
│   ├── maintenance_log.py           # 维修日志（基于 LangGraph Checkpointer）
│   └── experience_store.py          # 经验积累（基于 LangGraph Store）
├── prompts/                         # 提示词
│   ├── __init__.py
│   ├── system_prompt.py             # 维修工系统提示词
│   └── decision_prompt.py           # 工具选择决策提示词
├── reporters/                       # 报告生成
│   ├── __init__.py
│   ├── maintenance_report.py        # 维修报告
│   └── comparison_report.py         # 对比报告
├── ui/                              # 用户界面
│   ├── __init__.py
│   ├── streamlit_page.py            # Streamlit 页面
│   └── cli.py                       # CLI 入口
└── config.py                        # Agent 配置
```

### 5.2 修改文件

| 文件                                   | 变更内容                                                 | 影响范围      |      |
| ------------------------------------ | ---------------------------------------------------- | --------- | ---- |
| `src/parsers/pdfplumber_enhancer.py` | 新增 `enhance_page()` 方法                               | 仅新增方法     |      |
| `src/parsers/registry.py`            | 新增 `get_enhancer()` 方法                               | 仅新增方法     |      |
| `src/meal/manager.py`                | 扩展 `create_meal()` 支持手动模式                            | 向后兼容扩展    |      |
| `src/meal/models.py`                 | 新增 `creation_mode` 字段（"random"                       | "manual"） | 向后兼容 |
| `src/meal/cache.py`                  | 新增 `update_manifest_entry()` 方法                      | 仅新增方法     |      |
| `src/indexer.py`                     | 新增 `delete_by_source()` 和 `upsert_chunks()` 方法       | 仅新增方法     |      |
| `src/parser.py`                      | `parse_all_pdfs_unified()` 内部改为调用 `parse_pdf()` 共享单元 | 内部重构，接口不变 |      |
| `main.py`                            | 新增 `agent` 子命令入口                                     | 仅新增分支     |      |
| `config.yaml`                        | 新增 `agent` 配置段                                       | 仅新增段      |      |
| `src/app.py`                         | 新增维修工 Tab                                            | 仅新增       |      |

### 5.3 最小处理单位定义

| 阶段        | 最小处理单位             | 共享单元函数                                           | 说明     |
| --------- | ------------------ | ------------------------------------------------ | ------ |
| S1 解析     | 单个 PDF 文件          | `parse_pdf()`                                    | 天然支持   |
| S1.5 表格增强 | **单页**             | `enhance_page()`                                 | 新增能力   |
| S2 分块     | 单个解析结果             | `chunk_parsed()`                                 | 天然支持   |
| S3 嵌入     | 单个 chunk 列表        | `embed_chunks()`                                 | 天然支持   |
| S4 索引     | 单个 source 的 chunks | `index_chunks()` / `delete_source_and_reindex()` | 新增增量能力 |
| S5 检索     | 单个查询               | `query_rag()`                                    | 天然支持   |
| S6 生成     | 单个查询+上下文           | `query_rag()`                                    | 天然支持   |
| S7 评测     | 单个样本               | `evaluate_single()`                              | 天然支持   |

***

## 六、LangGraph 工作流设计

### 6.1 维修工 StateGraph

```python
# src/agent/graph.py

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

class MaintenanceState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    pdf_path: str | None
    page_number: int | None
    current_stage: str  # "init" | "parse" | "chunk" | "embed" | "index" | "retrieve" | "generate" | "evaluate" | "compare" | "done"
    parse_results: dict  # parser_config_key → {result, metrics}
    chunk_results: dict  # strategy_config_key → {chunks, metrics}
    embed_result: dict | None
    index_result: dict | None
    retrieve_result: dict | None
    generate_result: dict | None
    evaluate_result: dict | None
    comparison_reports: list[dict]
    user_locked_tools: dict | None  # 用户通过 UI 锁定的工具链
    maintenance_notes: list[str]  # 维修笔记

def build_maintenance_graph():
    workflow = StateGraph(MaintenanceState)

    # 添加节点
    workflow.add_node("agent", agent_node)           # LLM 决策：选择工具和参数
    workflow.add_node("parse", parse_node)           # 解析 PDF
    workflow.add_node("enhance_page", enhance_page_node)  # 单页增强
    workflow.add_node("chunk", chunk_node)           # 分块
    workflow.add_node("embed", embed_node)           # 嵌入
    workflow.add_node("index", index_node)           # 索引
    workflow.add_node("retrieve", retrieve_node)     # 检索
    workflow.add_node("generate", generate_node)     # 生成
    workflow.add_node("evaluate", evaluate_node)     # 评测
    workflow.add_node("compare", compare_node)       # 对比结果
    workflow.add_node("report", report_node)         # 生成报告

    # 边：从 START 到 agent
    workflow.add_edge(START, "agent")

    # 条件边：agent 决定下一步
    workflow.add_conditional_edges("agent", route_from_agent, {
        "parse": "parse",
        "enhance_page": "enhance_page",
        "chunk": "chunk",
        "embed": "embed",
        "index": "index",
        "retrieve": "retrieve",
        "generate": "generate",
        "evaluate": "evaluate",
        "compare": "compare",
        "report": "report",
        "end": END,
    })

    # 每个工具节点执行完后回到 agent（让 LLM 决定下一步）
    for node in ["parse", "enhance_page", "chunk", "embed", "index",
                 "retrieve", "generate", "evaluate", "compare", "report"]:
        workflow.add_edge(node, "agent")

    # 编译
    checkpointer = InMemorySaver()  # 开发用；生产用 SqliteSaver
    store = InMemoryStore()
    graph = workflow.compile(
        checkpointer=checkpointer,
        store=store,
    )
    return graph
```

### 6.2 Agent 节点：LLM 决策

```python
# src/agent/nodes/decide_node.py (即 agent_node)

def agent_node(state: MaintenanceState, *, store, config) -> dict:
    """LLM 决策节点：根据当前状态和用户消息，决定下一步调用什么工具"""

    # 1. 读取历史维修经验
    user_id = config.get("configurable", {}).get("user_id", "default")
    namespace = (user_id, "maintenance_experience")
    experiences = store.search(namespace)

    # 2. 构建决策 prompt
    system_prompt = MAINTENANCE_WORKER_SYSTEM_PROMPT.format(
        current_stage=state["current_stage"],
        available_parsers=ParserRegistry.list_primaries(),
        available_enhancers=ParserRegistry.list_enhancers(),
        available_chunk_strategies=["fixed", "page_aware", "semantic"],
        parse_results_summary=summarize_parse_results(state.get("parse_results", {})),
        chunk_results_summary=summarize_chunk_results(state.get("chunk_results", {})),
        past_experiences=[e.value for e in experiences],
        user_locked_tools=state.get("user_locked_tools"),
    )

    # 3. 调用 LLM（带工具绑定）
    llm = get_llm_with_tools()
    response = llm.invoke(
        [{"role": "system", "content": system_prompt}] + state["messages"],
    )

    # 4. 如果 LLM 返回工具调用，路由到对应节点
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        return {
            "messages": [response],
            "current_stage": tool_call["name"],  # 路由到对应工具节点
        }

    # 5. 如果 LLM 直接回复（无工具调用），可能是向用户提问
    return {"messages": [response]}


def route_from_agent(state: MaintenanceState) -> str:
    """根据 agent 节点的输出决定路由"""
    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        tool_name = last_message.tool_calls[0]["name"]
        # 映射工具名到节点名
        tool_to_node = {
            "parse_pdf": "parse",
            "enhance_page": "enhance_page",
            "chunk_parsed": "chunk",
            "embed_chunks": "embed",
            "index_chunks": "index",
            "query_rag": "retrieve",
            "generate_answer": "generate",
            "evaluate_single": "evaluate",
            "compare_results": "compare",
            "generate_report": "report",
        }
        return tool_to_node.get(tool_name, "end")

    return "end"
```

### 6.3 维修工系统提示词

```python
# src/agent/prompts/system_prompt.py

MAINTENANCE_WORKER_SYSTEM_PROMPT = """你是一个金融研报 RAG 系统的"维修工"Agent。你的角色是系统管理员，
权限仅次于用户，能够深入实验系统的每个环节进行精细调整。

## 当前状态
- 当前阶段: {current_stage}
- 已有解析结果: {parse_results_summary}
- 已有分块结果: {chunk_results_summary}

## 可用工具
### 解析器 (S1)
- pymupdf4llm: 通用解析器，速度快，适合纯文本文档
- fitz: PyMuPDF 原生解析，保留更多结构信息

### 表格增强器 (S1.5)
- pdfplumber: 专门提取表格，适合含大量表格的年报

### 分块策略 (S2)
- fixed: 固定长度分块，简单可靠
- page_aware: 页感知分块，保留页码和标题元数据（推荐用于研报）
- semantic: 语义分块，按语义断点分割（更智能但更慢）

### 其他阶段
- embed: 向量嵌入 (S3)
- index: 向量索引 (S4)
- retrieve: 检索 (S5)
- generate: 生成 (S6)
- evaluate: 评测 (S7)
- compare: 对比不同工具/参数的结果
- report: 生成维修报告

## 过去经验
{past_experiences}

## 用户锁定的工具链
{user_locked_tools}

## 工作原则
1. 先诊断后操作：先了解问题，再选择工具
2. 对比验证：对关键步骤用多种工具/参数对比
3. 记录经验：发现好的配置组合时记录下来
4. 用户至上：用户明确指定时，严格遵循用户的选择
5. 渐进探索：不确定时从简单方案开始，逐步尝试复杂方案
"""
```

### 6.4 工具节点示例

```python
# src/agent/nodes/parse_node.py

def parse_node(state: MaintenanceState) -> dict:
    """执行 PDF 解析"""
    last_message = state["messages"][-1]
    tool_call = last_message.tool_calls[0]
    args = tool_call["args"]

    # 调用共享单元
    result = parse_pdf(
        pdf_path=args["pdf_path"],
        parser_name=args.get("parser_name", "pymupdf4llm"),
        enhancer_name=args.get("enhancer_name"),
    )

    # 计算度量
    metrics = compute_document_metrics(result)

    # 构建工具响应
    tool_response = {
        "page_count": len(result.pages),
        "total_chars": metrics.total_chars,
        "table_count": metrics.total_tables,
        "parse_time_seconds": metrics.parse_time_seconds,
    }

    # 更新状态
    config_key = f"{args.get('parser_name', 'pymupdf4llm')}+{args.get('enhancer_name', 'none')}"
    updated_parse_results = {**state.get("parse_results", {}), config_key: {
        "result": serialize_parse_result(result),
        "metrics": tool_response,
    }}

    return {
        "messages": [ToolMessage(content=json.dumps(tool_response), tool_call_id=tool_call["id"])],
        "parse_results": updated_parse_results,
        "current_stage": "parse_done",
    }
```

### 6.5 人工干预流程

```python
# 在任意节点中插入 interrupt

def parse_node(state: MaintenanceState) -> dict:
    result = parse_pdf(...)
    metrics = compute_document_metrics(result)

    # 暂停，展示结果给用户
    user_feedback = interrupt({
        "type": "parse_result_review",
        "message": f"解析完成：{metrics.total_chars} 字符，{metrics.total_tables} 个表格",
        "metrics": metrics.__dict__,
        "available_actions": [
            "approve - 继续下一步",
            "retry - 换一种解析器重试",
            "enhance_page - 对特定页面做表格增强",
            "view_page - 查看特定页面的解析结果",
        ],
    })

    # 根据用户反馈决定下一步
    if user_feedback.get("action") == "retry":
        return {"current_stage": "parse", ...}  # 回到解析阶段
    elif user_feedback.get("action") == "enhance_page":
        return {"current_stage": "enhance_page", "page_number": user_feedback["page_number"], ...}
    else:
        return {"current_stage": "parse_done", ...}  # 继续前进
```

### 6.6 回退与跳转

LangGraph 的 `Command(goto=...)` 支持从任意节点跳转到任意其他节点：

```python
from langgraph.types import Command

def agent_node(state: MaintenanceState) -> Command:
    # 用户说"回到解析阶段，换表格补强"
    if user_requests_backtrack:
        return Command(
            goto="parse",  # 跳转到解析节点
            update={"parser_name": "fitz", "enhancer_name": "pdfplumber"},
        )

    # 用户说"全部重来"
    if user_requests_restart:
        return Command(
            goto="parse",
            update={"parse_results": {}, "chunk_results": {}, ...},  # 清空所有结果
        )
```

***

## 七、变更风险评估（修订版）

### 7.1 风险矩阵

| 风险                   | 概率 | 影响 | 应对策略                                                              |
| -------------------- | -- | -- | ----------------------------------------------------------------- |
| Agent 工具调用异常导致数据损坏   | 低  | 高  | 写操作前自动备份到 `.trashbin/`；白名单机制限制危险操作（如删库）；禁止 DROP/DELETE 全量操作       |
| 与 Meal 体系的状态不一致      | 中  | 中  | 维修工写回 Meal 时做一致性校验；Meal 新增 `creation_mode` 字段区分来源                 |
| LangGraph 版本 API 不稳定 | 中  | 中  | 锁定 langgraph 版本；封装 LangGraph 调用到 `src/agent/graph.py`，隔离变化        |
| 共享单元重构引入回归           | 低  | 高  | 共享单元先作为薄包装层，内部调用现有底层函数；渐进式迁移；每步加测试                                |
| LLM 自主决策的工具选择不可控     | 中  | 中  | 系统提示词约束 + 用户锁定机制 + interrupt 人工审核                                 |
| Anthropic 认证适配问题     | 低  | 中  | ChatAnthropic 支持自定义 headers，适配成本低                                 |
| LangGraph 依赖链过重      | 低  | 低  | 沙盒环境不担心；仅需 `langgraph` + `langchain-core` + `langchain-anthropic` |

### 7.2 回归保护

- 共享单元先作为**薄包装层**，内部调用现有底层函数，不改变现有行为
- 实验系统迁移到共享单元是**渐进式**的，每步迁移都有测试覆盖
- Agent 代码在 `src/agent/` 独立包中，与现有代码物理隔离
- 对现有模块的修改仅限**新增方法**和**向后兼容的参数扩展**
- CI 中 Agent 测试标记为 `@pytest.mark.agent`，可独立运行

***

## 八、技术难度评估（修订版）

### 8.1 难度分级

| 模块                      | 难度  | 说明                                   |
| ----------------------- | --- | ------------------------------------ |
| 共享单元层 (`src/core/ops/`) | ★★☆ | 薄包装现有函数，接口设计是关键                      |
| LangGraph StateGraph 定义 | ★★☆ | 学习曲线中等，但概念清晰                         |
| @tool 定义（包装共享单元）        | ★☆☆ | 直接 `@tool` 装饰器包装                     |
| Agent 节点函数              | ★★☆ | 需要处理 interrupt 和状态更新                 |
| LLM 决策节点 + 提示词          | ★★★ | 核心难点：提示词需要精心设计                       |
| 条件边路由                   | ★★☆ | 逻辑清晰，但需要处理多种跳转场景                     |
| Checkpointer 持久化        | ★☆☆ | 开箱即用，InMemorySaver 开发，SqliteSaver 生产 |
| Memory Store 经验积累       | ★★☆ | 需要设计 namespace 和记忆结构                 |
| Meal 手动模式扩展             | ★★☆ | 向后兼容扩展，需要测试覆盖                        |
| PdfPlumberEnhancer 单页增强 | ★★☆ | 内部已有页码索引，只需过滤                        |
| ArtifactCache 增量更新      | ★★★ | 需要处理并发安全和原子性                         |
| VectorIndexer 增量操作      | ★★★ | Qdrant filter-based delete + upsert  |
| Streamlit 交互页面          | ★★☆ | 参考现有 app\_pages                      |
| CLI 交互模式                | ★★☆ | 用指令代替按钮，参考 interactive\_qa.py        |
| Anthropic 认证适配          | ★☆☆ | ChatAnthropic 支持自定义 headers          |

### 8.2 总体评估

- **系统解耦**：★★☆（低难度）— 共享单元层是薄包装，不改变底层逻辑
- **工具抽象**：★☆☆（低难度）— LangGraph `@tool` 装饰器直接包装共享单元
- **Agent 编排**：★★★（中等难度）— LangGraph 大幅降低编排复杂度，但条件边和跳转需要仔细设计
- **LLM 决策**：★★★（中等难度）— 提示词工程是核心，需要多轮迭代
- **与现有系统集成**：★★☆（低-中难度）— 共享单元确保一致性，渐进式迁移降低风险

***

## 九、实施计划（修订版）

### Phase 0：基础设施（前置依赖）

**目标**：安装 LangGraph、创建共享单元层骨架、适配 Anthropic 认证

| 步骤  | 内容                                                             | 产出                     |
| --- | -------------------------------------------------------------- | ---------------------- |
| 0.1 | `pixi add --pypi langgraph langchain-core langchain-anthropic` | 依赖安装                   |
| 0.2 | 创建 `src/core/ops/` 包结构                                         | 目录骨架                   |
| 0.3 | 实现 `parse_pdf()` 共享单元                                          | 包装 ParserRegistry      |
| 0.4 | 实现 `chunk_parsed()` 共享单元                                       | 包装 chunk\_text\*()     |
| 0.5 | 实现 `query_rag()` 共享单元                                          | 包装 RAGPipeline.query() |
| 0.6 | 实现 `evaluate_single()` 共享单元                                    | 包装 BuiltinEvaluator    |
| 0.7 | 适配 Anthropic 认证到 ChatAnthropic                                 | LLM 客户端工厂              |
| 0.8 | 编写共享单元测试                                                       | pytest 覆盖              |

### Phase 1：Agent MVP（核心能力 C1-C3, C5, C7, C9）

**目标**：实现 LangGraph StateGraph + 解析对比 + 分块对比 + 维修日志

| 步骤   | 内容                                                         | 产出           |
| ---- | ---------------------------------------------------------- | ------------ |
| 1.1  | 创建 `src/agent/` 包结构                                        | 目录骨架         |
| 1.2  | 定义 `MaintenanceState` TypedDict                            | 状态模型         |
| 1.3  | 实现 `@tool` 定义（parse\_pdf, chunk\_parsed, compare\_results） | LangChain 工具 |
| 1.4  | 实现 agent\_node（LLM 决策节点）                                   | 核心决策逻辑       |
| 1.5  | 实现 parse\_node, chunk\_node, compare\_node                 | 工具节点         |
| 1.6  | 构建 StateGraph + 条件边                                        | 工作流图         |
| 1.7  | 实现 Checkpointer 持久化                                        | 维修日志         |
| 1.8  | 实现系统提示词                                                    | 维修工角色定义      |
| 1.9  | 实现 CLI 入口（基础版）                                             | 命令行交互        |
| 1.10 | 编写 Agent 测试                                                | pytest 覆盖    |

### Phase 2：扩展能力（C4, C6, C8, C10-C12）

**目标**：全链路工具 + 回退跳转 + Meal 手动模式 + 人工干预 + 单页增强

| 步骤   | 内容                                                      | 产出                           |
| ---- | ------------------------------------------------------- | ---------------------------- |
| 2.1  | 实现全链路 @tool（embed, index, retrieve, generate, evaluate） | 完整工具集                        |
| 2.2  | 实现全链路节点函数                                               | 完整节点集                        |
| 2.3  | 实现 `Command(goto=...)` 回退跳转                             | 非线性工作流                       |
| 2.4  | 实现 `interrupt()` 人工干预                                   | 用户反馈循环                       |
| 2.5  | 扩展 Meal 手动模式                                            | create\_meal(pdf\_files=...) |
| 2.6  | 实现 PdfPlumberEnhancer.enhance\_page()                   | 单页增强                         |
| 2.7  | 实现 enhance\_page @tool 和节点                              | 单页增强集成                       |
| 2.8  | 实现 Memory Store 经验积累                                    | 跨 session 记忆                 |
| 2.9  | 实现 Meal @tool（create\_curated\_meal, list\_pdfs）        | Meal 操作工具                    |
| 2.10 | 实现 Issue @tool（create\_issue, list\_issues）             | Issue 集成                     |
| 2.11 | ArtifactCache 增量更新                                      | 写回 Meal 支持                   |
| 2.12 | VectorIndexer 增量操作                                      | 增量索引更新                       |
| 2.13 | 编写测试                                                    | pytest 覆盖                    |

### Phase 3：用户界面与优化

**目标**：Streamlit 页面 + CLI 完善 + 提示词优化 + 实验系统迁移

| 步骤  | 内容                           | 产出          |
| --- | ---------------------------- | ----------- |
| 3.1 | 实现 Streamlit 维修工页面           | Web UI      |
| 3.2 | 实现 UI 下拉菜单锁定工具链              | 用户指定模式      |
| 3.3 | 完善 CLI 交互（指令代替按钮）            | CLI 调试支持    |
| 3.4 | 优化系统提示词（多轮迭代）                | 决策质量提升      |
| 3.5 | 实验系统迁移到共享单元                  | 一致性保障       |
| 3.6 | 实现维修报告生成                     | 对比报告 + 维修日志 |
| 3.7 | Checkpointer 迁移到 SqliteSaver | 生产级持久化      |
| 3.8 | 编写完整测试 + 文档                  | 质量保障        |

***

## 十、总结与建议

### 10.1 核心结论（修订版）

1. **框架选型**：**推荐 LangGraph**。用户对非线性工作流（回退/跳转）、持久化、人工干预、LLM 自主决策的需求，恰好是 LangGraph 的核心优势。自建框架实现同等能力的成本远高于引入 LangGraph。
2. **架构策略**：**共享单元抽象**取代"最小侵入胶水层"。先抽象共享单元（`src/core/ops/`），实验系统和 Agent 都通过共享单元访问核心算法，确保一致性，避免两套并行代码。
3. **Meal 体系扩展**：新增手动模式（`pdf_files` 参数），向后兼容。Agent 可以根据用户指令创建手动 Meal。
4. **Agent 权限**：高权限 + 备份 + 白名单。写操作前自动备份到 `.trashbin/`，危险操作（删库等）通过白名单禁止。
5. **技术难度**：整体中等。LangGraph 降低了编排和状态管理的难度，核心挑战在提示词工程和共享单元接口设计。

### 10.2 关键依赖

| 依赖                    | 版本     | 用途               |
| --------------------- | ------ | ---------------- |
| `langgraph`           | >= 0.2 | Agent 编排框架       |
| `langchain-core`      | >= 0.3 | @tool 装饰器、消息类型   |
| `langchain-anthropic` | >= 0.3 | Anthropic LLM 集成 |

### 10.3 开放问题（待后续会话细化）

1. **LLM 模型选择**：维修工的 LLM 用哪个 preset（default/opus/sonnet/haiku）？建议 sonnet 平衡性能和成本。
2. **Memory Store 的 namespace 设计**：按用户？按 PDF 类型？按问题类型？
3. **共享单元的粒度边界**：哪些操作应该抽象为共享单元，哪些留在调用侧？
4. **Streamlit 页面的交互细节**：下拉菜单的具体选项、interrupt 的 UI 表现形式。
5. **实验系统迁移到共享单元的优先级**：哪些模块先迁移？

### 10.4 可拆分给多会话的工作包

| 工作包                                | 对应 Phase        | 可独立程度            |
| ---------------------------------- | --------------- | ---------------- |
| WP1: 共享单元层 + 测试                    | Phase 0         | 完全独立             |
| WP2: LangGraph 骨架 + 解析对比           | Phase 1         | 依赖 WP1           |
| WP3: 全链路工具 + 回退跳转                  | Phase 2.1-2.4   | 依赖 WP2           |
| WP4: Meal 手动模式 + 单页增强              | Phase 2.5-2.7   | 依赖 WP1，可与 WP3 并行 |
| WP5: 记忆系统 + Issue 集成               | Phase 2.8-2.10  | 依赖 WP2           |
| WP6: 增量更新（ArtifactCache + Indexer） | Phase 2.11-2.12 | 依赖 WP1           |
| WP7: Streamlit UI + CLI 完善         | Phase 3.1-3.3   | 依赖 WP3           |
| WP8: 提示词优化 + 实验系统迁移                | Phase 3.4-3.5   | 依赖 WP3 + WP5     |
