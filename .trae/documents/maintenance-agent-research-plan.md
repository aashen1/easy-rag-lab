# 维修工 Agent 技术调研与初步框架设计

> 状态：Plan | 版本：v0.1 | 日期：2026-05-04

---

## 一、需求理解

### 1.1 核心定位

"维修工"Agent 是一个**脱离系统批量操作流程、以单文件/单页面为粒度手动处理 PDF 的智能工具编排器**。它不是替代现有实验系统的批量流程，而是在批量流程之外提供"精细手术刀"——当用户需要对某个 PDF 甚至某页做深度诊断、对比、调优时，维修工出场。

### 1.2 核心能力需求

| # | 能力 | 说明 |
|---|------|------|
| C1 | 单文件/单页面处理 | 脱离 Meal 批量体系，手动指定单个 PDF 甚至单页 |
| C2 | 全链路工具调用 | 可调用解析、分块、嵌入、检索、生成等所有链路工具 |
| C3 | 工具结果质量比较 | 对同一输入用不同工具/参数处理，比较结果差异 |
| C4 | 分块参数可配置 | chunk_size、overlap、语义分块阈值等，预留父子块热插拔接口 |
| C5 | 单步/多步执行 | 支持单步调用某个工具，也支持多步串联 |
| C6 | 轻量/全量双模式 | 轻量模式处理 1-2 个 PDF，全量模式同现有实验系统 |
| C7 | 工具自主选择 | 根据用户指令选择工具，或自主判断工具选择 |
| C8 | 结果反馈循环 | 根据结果反馈切换工具/参数，直至完成评测 |
| C9 | 分析报告与维修日志 | 输出详细分析报告和操作日志 |
| C10 | 用户交互与反馈 | 支持查看执行细节并提供反馈 |

### 1.3 待澄清问题

在深入设计之前，以下问题需要用户确认：

| # | 问题 | 选项 | 影响 |
|---|------|------|------|
| Q1 | Agent 的"自主判断"程度？ | A) 纯规则驱动（用户指定工具链）<br>B) LLM 辅助决策（Agent 可建议工具选择）<br>C) LLM 自主决策（Agent 自行决定工具链） | 决定是否需要 LLM 推理能力，影响框架复杂度 |
| Q2 | 单页表格补强的粒度需求？ | A) 单 PDF 级（当前已支持）<br>B) 单页级（需改造 PdfPlumberEnhancer）<br>C) 单表格级（需新增表格定位能力） | 决定 PdfPlumberEnhancer 的改造深度 |
| Q3 | 交互界面偏好？ | A) CLI 交互（类似 interactive_qa.py）<br>B) Streamlit 页面（集成到现有 Web UI）<br>C) 两者都要 | 决定前端开发量 |
| Q4 | 维修工是否需要写回 Meal 体系？ | A) 只读不写（维修工的结果独立存储）<br>B) 可选写回（用户确认后可更新 Meal 缓存）<br>C) 自动写回 | 决定与 ArtifactCache 的耦合深度 |
| Q5 | "维修日志"的持久化需求？ | A) 仅本次会话（内存中）<br>B) 文件持久化（JSON/MD）<br>C) 集成到 Issue 系统 | 决定日志系统设计 |

---

## 二、现有系统架构分析

### 2.1 全链路架构

```
PDF 文件
  │
  ▼ S1: 解析
ParserRegistry.get_composite() → parser.parse(pdf_path) → ParseResult
  │  产物: data/artifacts/{data_id}/parsed_{parser_hash}/*.md + *.pages.json
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

| 模块 | 单文件支持 | 关键耦合点 | 改造难度 |
|------|-----------|-----------|---------|
| `ParserRegistry.get_composite()` | ✅ 天然支持 | 无 | 无需改造 |
| `BaseParser.parse(pdf_path)` | ✅ 天然支持 | 无 | 无需改造 |
| `TableEnhancer.enhance()` | ✅ 单 PDF | 全页遍历，不支持单页 | 低 |
| `parse_all_pdfs_unified()` | ❌ 全量 | 全量遍历 + 全局 manifest/pointer | 中 |
| `process_parsed_files*()` | ✅ source_filter | 无 | 无需改造 |
| `chunk_text*()` 底层函数 | ✅ 纯函数 | 无 | 无需改造 |
| `VectorIndexer.build_index()` | ⚠️ 部分 | 缺少按 source 删除 points 的 API | 中 |
| `ArtifactCache.save_manifest()` | ❌ 覆盖写入 | 不支持增量更新 | 中 |
| `RAGPipeline.query()` | ✅ 单问题 | 无 | 无需改造 |
| `PipelineProfiler` | ✅ 阶段级 | 无 | 无需改造 |
| `case_diagnoser.diagnose()` | ✅ 纯函数 | 无 | 无需改造 |
| `ParserBenchmarkRunner` | ✅ 单文件 | 仅覆盖 S1 | 扩展即可 |

### 2.3 最接近的参考模板

**`ParserBenchmarkRunner`**（[eval/parser_benchmark/runner.py](file:///b:/project/w0-easy-rag/eval/parser_benchmark/runner.py)）是最接近维修工需求的现有架构：
- 单文件粒度处理
- 结果缓存（config hash）
- 可组合的 pipeline 配置
- 独立的指标计算和报告生成

但局限是：只覆盖 S1（解析），没有分块/检索/问答等后续阶段。

---

## 三、Agent 框架选型调研

### 3.1 框架对比

| 维度 | LangGraph | LlamaIndex | 自建框架 | CrewAI | AutoGen | Smolagents |
|------|-----------|------------|----------|--------|---------|------------|
| 工具抽象 | ★★★★ | ★★★★ | ★★★★★ | ★★★ | ★★★ | ★★★ |
| 编排能力 | ★★★★★ | ★★★ | ★★★ | ★★★ | ★★★★ | ★★ |
| 状态管理 | ★★★★★ | ★★★ | ★★★ | ★★ | ★★★ | ★ |
| HITL | ★★★★★ | ★★★ | ★★★ | ★★★★ | ★★★★ | ★ |
| 集成难度 | ★★★ | ★★★★ | ★★★★★ | ★★ | ★ | ★★★★ |
| 成熟度 | ★★★★★ | ★★★★ | ★★ | ★★★ | ★★★ | ★★ |
| **本场景适配** | **7/10** | **6/10** | **8/10** | **4/10** | **3/10** | **5/10** |

### 3.2 关键决策因素

1. **项目已有完善的工具体系**：`ParserRegistry`、`BaseParser`/`TableEnhancer` ABC、`RAGPipeline` 等成熟抽象。引入外部框架的工具层意味着两套注册机制并存，增加认知负担。

2. **Anthropic 自定义认证**：项目使用非标准 Anthropic 认证（`Authorization: Bearer` 而非 `x-api-key`），LangChain/LlamaIndex 的 Anthropic 集成需要额外适配。

3. **场景复杂度适中**：维修工的核心工作流是"选 PDF → 并行调用多种工具 → 收集结果 → 对比差异 → 生成报告"，这是一个相对简单的 DAG，不需要复杂的多 Agent 协作。

4. **依赖管理**：项目使用 pixi + pypi，引入 LangChain 意味着需要安装多个包，依赖链较重。自建框架零新增依赖。

### 3.3 推荐方案：自建轻量 Agent 框架

**首选自建框架**，理由：
- 零摩擦集成：直接复用 `ParserRegistry`、`BaseParser`、`process_parsed_files()` 等现有抽象
- 依赖最小化：不引入新框架，pixi.toml 零变更
- Anthropic 认证零问题：直接使用项目已有的 `create_anthropic_client()`
- 场景匹配：工作流是简单 DAG，不需要 LangGraph 的全功能图引擎

**备选升级路径**：如果未来需求扩展到动态工具选择、多轮交互、断点续传，可迁移到 LangGraph。迁移路径：先自建 MVP → 验证价值 → 逐步引入 LangGraph 的 StateGraph。

---

## 四、架构改造需求分析

### 4.1 改造原则

1. **最小侵入**：不修改现有模块的核心逻辑，通过新增胶水层实现 Agent 功能
2. **复用优先**：优先复用现有组件（ParserRegistry、PipelineProfiler、case_diagnoser 等）
3. **渐进式**：先实现核心能力（C1-C3），再扩展高级能力（C7-C8）
4. **向后兼容**：Agent 的存在不影响现有批量实验流程

### 4.2 需要改造的模块

#### 4.2.1 新增：单文件解析入口（绕过 parse_all_pdfs_unified）

当前 `parse_all_pdfs_unified()` 强制全量遍历，维修工需要一个轻量入口：

```python
# 新增函数，位于 src/agent/tools/ 或 src/parser.py 中
def parse_single_pdf(
    pdf_path: str,
    parser_name: str = "pymupdf4llm",
    enhancer_name: str | None = None,
    parser_options: dict | None = None,
    enhancer_options: dict | None = None,
) -> ParseResult:
    """解析单个 PDF，返回 ParseResult，不涉及 Meal/Artifact 体系"""
    parser = ParserRegistry.get_composite(
        primary=parser_name,
        enhancer=enhancer_name,
        primary_config=parser_options,
        enhancer_config=enhancer_options,
    )
    return parser.parse(pdf_path)
```

**改造难度**：低。直接调用已有 `ParserRegistry.get_composite()` + `parser.parse()`。

#### 4.2.2 新增：单文件分块入口

现有 `process_parsed_files*()` 已支持 `source_filter`，但需要更轻量的单文件接口：

```python
def chunk_single_pdf(
    parse_result: ParseResult,
    strategy: str = "page_aware",  # "fixed" | "page_aware" | "semantic"
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    **kwargs,
) -> list[dict[str, Any]]:
    """对单个 ParseResult 执行分块，返回 chunks 列表"""
```

**改造难度**：低。底层 `chunk_text*()` 函数已是纯函数，只需薄包装。

#### 4.2.3 新增：单页表格补强（可选，依赖 Q2 答案）

如果需要单页级表格补强，需改造 `PdfPlumberEnhancer`：

```python
# 在 PdfPlumberEnhancer 中新增方法
def enhance_page(
    self, pdf_path: str, page_number: int, existing_text: str
) -> str:
    """对单个页面执行表格增强"""
```

**改造难度**：低-中。`_extract_all_tables()` 已按页码索引，只需过滤目标页。

#### 4.2.4 新增：ArtifactCache 增量更新

当前 `save_manifest()` 是覆盖写入，维修工需要增量更新：

```python
# 在 ArtifactCache 中新增方法
def update_manifest_entry(
    self, data_id: str, rel_path: str, sha256: str, file_size: int
) -> None:
    """增量更新 manifest 中的单个文件条目"""
```

**改造难度**：中。需要读取旧 manifest → 合并 → 写回，需要加锁保证原子性。

#### 4.2.5 新增：VectorIndexer 按 source 删除

当前 `VectorIndexer` 缺少按 source 删除 points 的 API：

```python
# 在 VectorIndexer 中新增方法
def delete_by_source(self, source: str) -> int:
    """删除指定 source 的所有向量点，返回删除数量"""

def upsert_chunks(
    self, chunks: list[dict], embedder: Embedder, batch_size: int = 32
) -> int:
    """增量插入/更新 chunks 的向量，返回插入数量"""
```

**改造难度**：中。Qdrant 支持 filter-based delete，但需要构造 payload filter。

### 4.3 不需要改造的模块

| 模块 | 原因 |
|------|------|
| `ParserRegistry` | 已足够灵活，直接复用 |
| `BaseParser.parse()` | 天然支持单文件 |
| `chunk_text*()` 底层函数 | 纯函数，直接调用 |
| `PipelineProfiler` | 阶段级可组合，直接复用 |
| `RAGPipeline.query()` | 天然支持单问题 |
| `case_diagnoser` | 纯函数，直接复用 |
| `BuiltinEvaluator` | 支持 batch，传入长度为 1 的 list 即可 |
| `compute_page_metrics()` | 已有单页度量能力 |

---

## 五、代码变更范围

### 5.1 新增文件

```
src/agent/                          # 维修工 Agent 包
├── __init__.py                     # 公开 API 导出
├── core.py                         # MaintenanceAgent 核心类
├── state.py                        # AgentState 数据模型
├── tools/                          # 工具注册与实现
│   ├── __init__.py
│   ├── base.py                     # AgentTool ABC + ToolRegistry
│   ├── parse_tool.py               # PDF 解析工具
│   ├── chunk_tool.py               # 分块工具
│   ├── embed_tool.py               # 嵌入工具
│   ├── index_tool.py               # 索引工具
│   ├── retrieve_tool.py            # 检索工具
│   ├── generate_tool.py            # 生成工具
│   ├── evaluate_tool.py            # 评测工具
│   ├── compare_tool.py             # 结果对比工具
│   └── profile_tool.py             # 性能分析工具
├── workflows/                      # 预定义工作流
│   ├── __init__.py
│   ├── parse_compare.py            # 解析对比工作流
│   ├── chunk_compare.py            # 分块对比工作流
│   ├── full_pipeline.py            # 全链路工作流
│   └── diagnose_fix.py             # 诊断修复工作流
├── reporters/                      # 报告生成
│   ├── __init__.py
│   ├── maintenance_log.py          # 维修日志
│   └── comparison_report.py        # 对比报告
└── cli.py                          # CLI 入口
```

### 5.2 修改文件

| 文件 | 变更内容 | 影响范围 |
|------|---------|---------|
| `src/parsers/pdfplumber_enhancer.py` | 新增 `enhance_page()` 方法（可选） | 仅新增方法，不影响现有逻辑 |
| `src/meal/cache.py` | 新增 `update_manifest_entry()` 方法 | 仅新增方法，不影响现有逻辑 |
| `src/indexer.py` | 新增 `delete_by_source()` 和 `upsert_chunks()` 方法 | 仅新增方法，不影响现有逻辑 |
| `main.py` | 新增 `agent` 子命令入口 | 仅新增分支，不影响现有命令 |
| `config.yaml` | 新增 `agent` 配置段 | 仅新增段，不影响现有配置 |

### 5.3 最小处理单位定义

| 阶段 | 最小处理单位 | 说明 |
|------|-------------|------|
| S1 解析 | 单个 PDF 文件 | `parser.parse(pdf_path)` 天然支持 |
| S1.5 表格增强 | 单个 PDF / 单页（可选） | `enhance()` 文档级；`enhance_page()` 页级（需新增） |
| S2 分块 | 单个解析结果 | `chunk_text*()` 纯函数，天然支持 |
| S3 嵌入 | 单个 chunk 列表 | `embedder.embed_documents()` 天然支持 |
| S4 索引 | 单个 source 的 chunks | 需新增 `delete_by_source()` + `upsert_chunks()` |
| S5 检索 | 单个查询 | `retriever.search(query)` 天然支持 |
| S6 生成 | 单个查询+上下文 | `generator.generate()` 天然支持 |
| S7 评测 | 单个样本 | `evaluator.evaluate_batch([sample])` 天然支持 |

---

## 六、变更风险评估

### 6.1 风险矩阵

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| Agent 工具调用异常导致数据损坏 | 低 | 高 | 维修工默认只读不写，写操作需用户显式确认；所有写操作前自动备份 |
| 与 Meal 体系的状态不一致 | 中 | 中 | 维修工结果独立存储，不自动写回 Meal；可选写回时做一致性校验 |
| 新增代码引入 bug 影响现有功能 | 低 | 高 | Agent 代码完全在 `src/agent/` 新包中，不修改现有模块核心逻辑 |
| LLM 自主决策的工具选择不可控 | 中 | 中 | 初期采用规则驱动 + LLM 建议模式，用户确认后执行 |
| 性能开销（加载模型等） | 低 | 低 | 懒加载，按需初始化 embedder/indexer 等重量级组件 |
| 单页表格补强改造引入回归 | 低 | 中 | 新增方法而非修改现有方法，加测试覆盖 |

### 6.2 回归保护

- Agent 代码完全在 `src/agent/` 新包中，与现有代码物理隔离
- 对现有模块的修改仅限新增方法，不修改现有方法签名和逻辑
- 新增方法的测试独立于现有测试，不影响现有测试覆盖率
- CI 中 Agent 测试标记为 `@pytest.mark.agent`，可独立运行

---

## 七、技术难度评估

### 7.1 难度分级

| 模块 | 难度 | 工作量估计 | 说明 |
|------|------|-----------|------|
| AgentTool ABC + ToolRegistry | ★☆☆ | 小 | 复用 ParserRegistry 模式，约 100 行 |
| 单文件解析工具 | ★☆☆ | 小 | 薄包装 ParserRegistry，约 50 行 |
| 单文件分块工具 | ★☆☆ | 小 | 薄包装 chunk_text*()，约 80 行 |
| 结果对比工具 | ★★☆ | 中 | 需设计对比维度和输出格式，约 200 行 |
| 维修日志与报告 | ★★☆ | 中 | 参考 ParserBenchmarkRunner 的报告生成，约 200 行 |
| 工作流编排 | ★★☆ | 中 | DAG 编排 + 条件分支，约 300 行 |
| 单页表格增强（可选） | ★★☆ | 中 | 修改 PdfPlumberEnhancer，约 50 行 |
| ArtifactCache 增量更新 | ★★★ | 中-大 | 需处理并发安全和原子性，约 100 行 |
| VectorIndexer 增量操作 | ★★★ | 中-大 | Qdrant filter-based delete + upsert，约 150 行 |
| LLM 辅助决策（可选） | ★★★ | 大 | 需设计 prompt + 工具描述 + 输出解析，约 400 行 |
| Streamlit 交互页面（可选） | ★★☆ | 中 | 参考现有 app_pages，约 300 行 |

### 7.2 总体评估

- **系统解耦**：★★☆（低难度）— 现有模块已有良好的抽象（ABC + Registry），Agent 只需薄包装
- **工具抽象**：★★☆（低难度）— 复用 ParserRegistry 模式，Pydantic Model 定义 I/O schema
- **Agent 交互**：★★★（中等难度）— 取决于 Q1 的答案，规则驱动简单，LLM 自主决策复杂
- **状态管理**：★★☆（低难度）— 维修工的状态简单（当前 PDF、处理结果、日志），用 dataclass 即可
- **与现有系统集成**：★★☆（低难度）— 大部分组件可直接复用，只有 ArtifactCache 和 VectorIndexer 需要少量扩展

---

## 八、初步框架设计

### 8.1 核心抽象

```python
# === src/agent/tools/base.py ===

class AgentTool(ABC):
    """工具基类，与现有 BaseParser 模式一致"""
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    @abstractmethod
    def run(self, params: BaseModel) -> BaseModel: ...

    def to_schema(self) -> dict:
        """生成 JSON Schema 供 LLM 工具调用"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


class ToolRegistry:
    """复用 ParserRegistry 的注册模式"""
    _tools: dict[str, AgentTool] = {}

    @classmethod
    def register(cls, tool: AgentTool): ...
    @classmethod
    def get(cls, name: str) -> AgentTool: ...
    @classmethod
    def list_tools(cls) -> list[dict]: ...
```

### 8.2 Agent 状态

```python
# === src/agent/state.py ===

@dataclass
class StepResult:
    tool_name: str
    params: dict
    output: dict
    metrics: dict  # 耗时、token 等
    timestamp: str

@dataclass
class AgentState:
    pdf_path: str | None = None
    page_number: int | None = None
    parse_results: dict[str, ParseResult] = field(default_factory=dict)
    chunk_results: dict[str, list[dict]] = field(default_factory=dict)
    comparison_reports: list[dict] = field(default_factory=list)
    step_history: list[StepResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    current_step: str = "init"
```

### 8.3 MaintenanceAgent 核心

```python
# === src/agent/core.py ===

class MaintenanceAgent:
    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.state = AgentState()
        self.registry = ToolRegistry()
        self.profiler = PipelineProfiler("maintenance_worker", 1, 1)
        self._register_tools()

    def _register_tools(self):
        """注册所有可用工具"""
        self.registry.register(ParseTool(self.config))
        self.registry.register(ChunkTool(self.config))
        self.registry.register(EmbedTool(self.config))
        self.registry.register(IndexTool(self.config))
        self.registry.register(RetrieveTool(self.config))
        self.registry.register(GenerateTool(self.config))
        self.registry.register(CompareTool())
        self.registry.register(ProfileTool(self.profiler))

    def run_workflow(
        self,
        workflow_name: str,
        pdf_path: str,
        **kwargs,
    ) -> AgentState:
        """执行预定义工作流"""
        workflow = self._get_workflow(workflow_name)
        return workflow.execute(self, pdf_path, **kwargs)

    def run_step(
        self,
        tool_name: str,
        params: dict,
    ) -> StepResult:
        """执行单步工具调用"""
        tool = self.registry.get(tool_name)
        with self.profiler.profile_stage(tool_name):
            output = tool.run(tool.input_model(**params))
        result = StepResult(...)
        self.state.step_history.append(result)
        return result

    def compare_results(
        self,
        results: dict[str, Any],
        dimensions: list[str] | None = None,
    ) -> dict:
        """对比多个工具的处理结果"""
        ...

    def generate_report(self) -> str:
        """生成维修日志和分析报告"""
        ...
```

### 8.4 工具示例

```python
# === src/agent/tools/parse_tool.py ===

class ParseToolInput(BaseModel):
    pdf_path: str
    parser_name: str = "pymupdf4llm"
    enhancer_name: str | None = None
    parser_options: dict | None = None
    enhancer_options: dict | None = None

class ParseToolOutput(BaseModel):
    parse_result: dict  # ParseResult 的序列化形式
    page_count: int
    total_chars: int
    table_count: int
    parse_time_seconds: float

class ParseTool(AgentTool):
    name = "pdf_parse"
    description = "解析单个 PDF 文件，支持多种解析器和表格增强器"
    input_model = ParseToolInput
    output_model = ParseToolOutput

    def run(self, params: ParseToolInput) -> ParseToolOutput:
        parser = ParserRegistry.get_composite(
            primary=params.parser_name,
            enhancer=params.enhancer_name,
            primary_config=params.parser_options,
            enhancer_config=params.enhancer_options,
        )
        start = time.time()
        result = parser.parse(params.pdf_path)
        elapsed = time.time() - start

        metrics = compute_document_metrics(result, elapsed)
        return ParseToolOutput(
            parse_result=serialize_parse_result(result),
            page_count=len(result.pages),
            total_chars=metrics.total_chars,
            table_count=metrics.total_tables,
            parse_time_seconds=elapsed,
        )
```

### 8.5 工作流示例

```python
# === src/agent/workflows/parse_compare.py ===

class ParseCompareWorkflow:
    """解析对比工作流：用多种解析器处理同一 PDF，对比结果"""

    def execute(
        self,
        agent: MaintenanceAgent,
        pdf_path: str,
        parsers: list[str] | None = None,
    ) -> AgentState:
        parsers = parsers or ParserRegistry.list_primaries()

        # Step 1: 并行解析
        for parser_name in parsers:
            result = agent.run_step("pdf_parse", {
                "pdf_path": pdf_path,
                "parser_name": parser_name,
            })
            agent.state.parse_results[parser_name] = result

        # Step 2: 对比结果
        comparison = agent.compare_results(
            agent.state.parse_results,
            dimensions=["total_chars", "table_count", "heading_count", "markdown_valid_ratio"],
        )
        agent.state.comparison_reports.append(comparison)

        # Step 3: 生成报告
        report = agent.generate_report()
        return agent.state
```

### 8.6 热插拔接口设计

```python
# === src/agent/tools/chunk_tool.py ===

class ChunkStrategy(ABC):
    """分块策略热插拔接口"""
    name: str

    @abstractmethod
    def chunk(self, parse_result: ParseResult, **kwargs) -> list[dict]: ...

class FixedChunkStrategy(ChunkStrategy):
    name = "fixed"
    def chunk(self, parse_result, **kwargs):
        return chunk_text(parse_result.text, **kwargs)

class PageAwareChunkStrategy(ChunkStrategy):
    name = "page_aware"
    def chunk(self, parse_result, **kwargs):
        return chunk_text_page_aware(parse_result.pages, **kwargs)

class SemanticChunkStrategy(ChunkStrategy):
    name = "semantic"
    def chunk(self, parse_result, **kwargs):
        return chunk_text_semantic(parse_result.text, embedder=kwargs["embedder"], **kwargs)

# 未来扩展：父子块策略
# class ParentChildChunkStrategy(ChunkStrategy):
#     name = "parent_child"
#     def chunk(self, parse_result, **kwargs): ...

class ChunkStrategyRegistry:
    """分块策略注册表，支持热插拔"""
    _strategies: dict[str, type[ChunkStrategy]] = {}

    @classmethod
    def register(cls, strategy: type[ChunkStrategy]): ...
    @classmethod
    def get(cls, name: str) -> ChunkStrategy: ...
```

---

## 九、实施计划

### Phase 1：MVP（核心能力 C1-C3, C5, C9）

**目标**：实现单文件解析对比 + 分块对比 + 维修日志

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1.1 | 创建 `src/agent/` 包结构 | 无 |
| 1.2 | 实现 `AgentTool` ABC + `ToolRegistry` | 无 |
| 1.3 | 实现 `ParseTool`（包装 ParserRegistry） | 1.2 |
| 1.4 | 实现 `ChunkTool`（包装 chunk_text*()） | 1.2 |
| 1.5 | 实现 `CompareTool`（结果对比） | 1.2 |
| 1.6 | 实现 `AgentState` + `MaintenanceAgent` 核心 | 1.2 |
| 1.7 | 实现 `ParseCompareWorkflow` | 1.3, 1.5, 1.6 |
| 1.8 | 实现 `ChunkCompareWorkflow` | 1.4, 1.5, 1.6 |
| 1.9 | 实现维修日志生成 | 1.6 |
| 1.10 | 实现 CLI 入口 | 1.6 |
| 1.11 | 编写测试 | 全部 |

### Phase 2：扩展能力（C4, C6, C10）

**目标**：分块参数可配置 + 轻量/全量双模式 + 用户交互

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 2.1 | 实现 `ChunkStrategyRegistry` + 热插拔接口 | Phase 1 |
| 2.2 | 实现 `EmbedTool` + `IndexTool` | Phase 1 |
| 2.3 | 实现 `RetrieveTool` + `GenerateTool` | 2.2 |
| 2.4 | 实现 `FullPipelineWorkflow` | 2.3 |
| 2.5 | 实现全量模式（对接 Meal 体系） | 2.4 |
| 2.6 | 实现用户交互（CLI 确认/反馈） | Phase 1 |
| 2.7 | ArtifactCache 增量更新 | Phase 1 |
| 2.8 | VectorIndexer 增量操作 | 2.2 |

### Phase 3：智能能力（C7, C8）

**目标**：LLM 辅助工具选择 + 结果反馈循环

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 3.1 | 设计 LLM 工具选择 prompt | Phase 2 |
| 3.2 | 实现 LLM 辅助决策模块 | 3.1 |
| 3.3 | 实现结果反馈循环 | 3.2 |
| 3.4 | 实现 `DiagnoseFixWorkflow` | 3.2 |
| 3.5 | Streamlit 交互页面（可选） | Phase 2 |

---

## 十、总结与建议

### 10.1 核心结论

1. **框架选型**：推荐自建轻量 Agent 框架，与项目架构最契合，集成成本最低。LangGraph 作为未来升级路径。

2. **架构改造**：改造量小。大部分现有组件可直接复用，只需新增胶水层和少量扩展方法。

3. **技术难度**：整体偏低。核心挑战在于工具结果对比的质量维度设计和 LLM 辅助决策的 prompt 工程。

4. **风险可控**：Agent 代码物理隔离在 `src/agent/` 新包中，对现有功能零影响。

### 10.2 建议的实施路径

1. **先回答 Q1-Q5**，明确需求边界
2. **Phase 1 MVP** 先行，验证"单文件解析对比"的核心价值
3. 根据用户反馈决定 Phase 2/3 的优先级和范围
4. 考虑将维修工 Agent 作为 v0.2.0 的一个子特性纳入版本规划

### 10.3 开放问题

- 维修工的"自主判断"程度（Q1）直接决定 Phase 3 的复杂度
- 单页表格补强（Q2）的需求优先级影响 Phase 2 的排期
- 交互界面（Q3）的选择影响用户体验和开发量
- 与 Meal 体系的写回关系（Q4）影响数据一致性设计
- 维修日志的持久化（Q5）影响跨 session 复用能力
