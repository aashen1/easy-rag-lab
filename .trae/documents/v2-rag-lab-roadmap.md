# ash-easy-rag v2 路线图：从实验工具到 RAG 实验室

> **定位**：一份面向 v2 从零重建的总路线图，系统性地纳入 v0.1.0~v0.1.17 的踩坑经验，目标是一个能上升的、快速的、从轻量到大规模都可伸缩的 RAG 实验室。

---

## 一、v1 诊断：四大核心问题的根因分析

### 1.1 测试不硬——"AI 自娱自乐"的测试体系

**现象**：2000+ 测试全部绿灯，但端到端跑起来不出三个操作必现 bug。

**根因**：

| 问题 | 数据 | 根因 |
|------|------|------|
| Mock 过度 | 1123 处 Mock 调用，46 个文件 | AI 生成的测试倾向于 Mock 掉所有外部依赖，验证的是"Mock 被按 Mock 的方式调用了"而非"真实业务逻辑正确" |
| 集成测试近零 | 仅 1 处 `@pytest.mark.integration` | 测试金字塔倒置——大量 unit 测试 + 极少量 slow 测试，integration 层形同虚设 |
| 端到端测试缺失 | 0 个真实 PDF→解析→检索→生成→评测的 E2E 测试 | 从未验证过完整链路在真实数据上的正确性 |
| Pydantic 验证旁路 | 所有模型 `extra: "allow"`，`load_config()` 返回 dict 不走 Pydantic | 验证层与运行时路径脱节，拼写错误的配置键被静默忽略 |
| 测试数据虚假 | conftest 中 `np.ones(1024)` 全 1 向量、固定文本 "This is a test answer" | Mock 数据与真实数据分布完全脱节，无法发现维度不匹配、格式异常等真实 bug |

**v1 教训**：测试数量不等于测试质量。2000 个验证 Mock 行为的测试，不如 20 个验证真实链路的集成测试。AI 写测试时，人类必须审查每个测试的"断言是否验证了有意义的业务属性"。

---

### 1.2 架构不够干净——"尾大不掉"的耦合体系

**现象**：想抽一个零件出来独立用，发现到处都是牵绊。

**根因**：

| 耦合点 | 具体表现 | 后果 |
|--------|---------|------|
| RAGPipeline 上帝对象 | 1077 行，承担 9+ 种职责（配置/初始化/Meal/检索/索引/查询/懒加载/释放/克隆） | 任何改动都可能波及全系统，无法独立测试或替换任何子功能 |
| Pipeline ↔ Meal 双向渗透 | `build_index` 内部计算 data_id/config_hashes，无法脱离 Meal 独立运行 | 基础 RAG 功能被 Meal 绑架，想"冲滩序就冲滩序"做不到 |
| Agent Tools 每次重建重型资源 | 每次查询都 `RAGPipeline(meal_name=...)` 重新加载 Embedder（~1.3GB） | 性能灾难，Agent 实际不可用 |
| core/ops 抽象层只被部分采用 | Pipeline 仍走旧路径（`parse_all_pdfs_unified` + `process_parsed_files`） | 新旧双路径共存，维护成本翻倍 |
| MealManager._build_pipeline 重复逻辑 | 184 行方法与 Pipeline.build_index 大量重复 | 同一功能两份代码，bug 修一处漏一处 |
| LLM 客户端仅支持 Anthropic | `api_key="dummy"` hack、硬编码默认模型名 | 无法适配 OpenAI/DeepSeek 等后端 |
| Embedder 全局副作用 | `os.environ["HF_HUB_OFFLINE"] = "1"` 模块级导入即生效 | 影响同进程内所有 HuggingFace 使用者 |

**v1 教训**：快速迭代时"在 Pipeline 上打补丁"是最省力的方式，但每打一个补丁就增加一分耦合。解耦必须从架构设计之初就作为核心原则，而非事后补救。v1 的 `core/ops/` 抽象层方向正确，但执行不彻底——v2 必须让所有路径都走抽象层。

---

### 1.3 不够专业化——"差一口气"的生产就绪度

**现象**：功能都有，但就是不能上生产。

**根因**：

| 缺失维度 | 现状 | 生产要求 |
|----------|------|---------|
| 异步支持 | 零 `async/await` 代码，所有 I/O 同步阻塞 | LLM API 调用天然 I/O 密集，async 可提升 10x 吞吐 |
| API 层 | 所有业务逻辑绑定在 Streamlit UI 上 | 需要 RESTful API 供程序化调用 |
| 容器化 | 无 Dockerfile、无 docker-compose | 容器化部署是生产化的基础 |
| 认证授权 | 无任何用户认证机制 | 至少需要 API Key 认证 |
| 断路器 | 无，API 持续故障时重试持续消耗资源 | 需要快速失败机制保护系统 |
| 健康检查 | 无 `/health` `/ready` 端点 | K8s 部署的前提 |
| 结构化日志 | 纯文本日志，无 trace_id 关联 | 需要 JSON 结构化日志 + 请求关联 |
| 资源监控 | 无 Prometheus/OpenTelemetry 指标导出 | 需要接入监控告警系统 |
| 优雅关闭 | 无信号处理器，进程被 kill 可能丢数据 | 需要注册 SIGTERM 处理器 |
| BM25 持久化 | 纯内存索引，每次重启从 JSONL 重建 | 大数据集启动慢，违反"持久化中间产物"规范 |

**v1 教训**：v1 的定位是"实验工具 + Streamlit 前端"，这个定位本身限制了生产化。v2 必须从架构层面确立"服务优先"原则——核心逻辑是独立服务，UI 只是客户端之一。

---

### 1.4 评测差点意思——"修了又坏"的评测链路

**现象**：从 v0.1.7 到 v0.1.17，评测链路一直是最大的时间黑洞，修一个暴露另一个。

**根因**：

| 问题 | 具体表现 | 后果 |
|------|---------|------|
| Ground Truth 幻觉 | LLM 生成的 expected_answer 本身可能包含幻觉，"以错评错" | 评测结果的可信度从根本上受限 |
| source_chunks 始终为空 | 文档级问题生成策略无法精确到 chunk | chunk 级指标（hit_rate/mrr/ndcg）无法正确计算 |
| expected_sources 标注错误 | LLM 生成问题时涉猎文档判断不准 | 检索指标虚高或虚低 |
| RAGAS 版本兼容性 | 依赖 `_metrics` 等内部 API，0.5 发布即断裂 | 评测系统随时可能崩溃 |
| 评测缓存缺失 | 相同 question+answer+contexts 重复调用 LLM | Token 浪费严重，评测成本高 |
| 指标聚合无统计显著性 | 仅计算简单平均值，无置信区间/标准差 | 无法判断 variant 间差异是否具有实际意义 |
| Builtin/RAGAS 指标不可比 | 同名指标（faithfulness 等）使用不同 prompt 和评分逻辑 | 双后端评测结果无法直接对比 |

**v1 教训**：评测是 RAG 项目的命脉。虚高的评测指标比没有评测更危险——它会误导后续所有优化决策。v0.1.7~v0.1.14 整整 6 个版本的核心工作都在修评测链路，这是早期决策不审慎的最大代价。

---

## 二、v2 设计哲学

### 2.1 核心原则

| 原则 | v1 的教训 | v2 的做法 |
|------|----------|----------|
| **乐高原则** | Pipeline 上帝对象，所有零件焊死 | 每个组件可独立运行、独立测试、独立替换 |
| **服务优先** | Streamlit 绑定所有业务逻辑 | 核心逻辑是独立服务，UI 只是客户端 |
| **评测先行** | 评测链路修了 6 个版本 | MVP 阶段就建立可信评测基线 |
| **异步原生** | 零 async 代码，同步阻塞 | 所有 I/O 操作默认异步 |
| **配置即契约** | Pydantic 验证旁路，`extra: "allow"` | 配置加载必须经过严格校验，`extra: "forbid"` |
| **测试即防线** | 2000 个 Mock 测试发现不了真实 bug | 测试金字塔：少量 E2E + 适量集成 + 精选单元 |

### 2.2 目标画像

**v2 是一个 RAG 实验室**，不是另一个 RAG demo。它应该：

- **轻量可起**：5 分钟内从零启动一个最小 RAG 服务
- **乐高可拼**：每个组件（解析器/分块器/嵌入器/检索器/生成器/评测器）可独立插拔
- **规模可扩**：从单机开发到集群部署，架构无需重写
- **实验可比**：评测结果可信、可复现、可对比
- **服务可用**：RESTful API + 认证 + 监控 + 容器化

---

## 三、v2 架构设计

### 3.1 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        客户端层                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Streamlit │  │  CLI     │  │  SDK     │  │  第三方   │   │
│  │  Web UI   │  │ (typer)  │  │ (Python) │  │  前端     │   │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘   │
│        └──────────────┴───────────┴──────────────┘         │
│                          │ REST / WebSocket                  │
├──────────────────────────┼──────────────────────────────────┤
│                    API 网关层 (FastAPI)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 认证中间件│  │ 限流中间件│  │ 日志中间件│  │ CORS     │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
├─────────────────────────────────────────────────────────────┤
│                      服务层 (核心业务)                        │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ IngestionSvc│  │  QuerySvc   │  │  EvalSvc    │        │
│  │ (解析/分块/ │  │ (检索/重排/ │  │ (评测/报告/ │        │
│  │  嵌入/索引) │  │  生成)      │  │  对比)      │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                 │
│  ┌──────┴────────────────┴────────────────┴──────┐         │
│  │              组件注册表 (Registry)              │         │
│  │  ParserRegistry / ChunkerRegistry / ...       │         │
│  └──────────────────────┬───────────────────────┘         │
│                         │                                  │
│  ┌──────────┐  ┌───────┴───────┐  ┌──────────┐           │
│  │ LLM      │  │  向量存储      │  │  缓存     │           │
│  │ Provider │  │  (Qdrant)     │  │  (Redis)  │           │
│  │ Registry │  │  (Milvus)     │  │  (File)   │           │
│  └──────────┘  └───────────────┘  └──────────┘           │
├─────────────────────────────────────────────────────────────┤
│                     基础设施层                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ 配置中心  │  │ 日志系统  │  │ 指标系统  │  │ 追踪系统  │  │
│  │ (Pydantic│  │ (loguru +│  │ (Prometheus│ │ (OpenTelemetry│
│  │  严格校验)│  │  JSON)   │  │  /OTLP)  │  │  trace)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 核心设计决策

#### 决策 1：组件协议 (Protocol) 而非继承

v1 的检索器用继承，v2 用 Python Protocol（结构化子类型）：

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Parser(Protocol):
    async def parse(self, pdf_path: Path) -> ParseResult: ...
    def supported_formats(self) -> list[str]: ...

@runtime_checkable
class Chunker(Protocol):
    async def chunk(self, parsed: ParseResult) -> ChunkResult: ...
    def supported_strategies(self) -> list[str]: ...

@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def dimension(self) -> int: ...

@runtime_checkable
class Retriever(Protocol):
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]: ...

@runtime_checkable
class Generator(Protocol):
    async def generate(self, query: str, contexts: list[str]) -> GenerationResult: ...

@runtime_checkable
class Evaluator(Protocol):
    async def evaluate(self, samples: list[EvalSample]) -> EvalReport: ...
```

**v1 教训**：v1 的检索器继承体系导致 HybridRetriever 必须知道 VectorRetriever 和 BM25Retriever 的具体实现。Protocol 允许任何实现了接口的类注册，无需继承关系。

#### 决策 2：服务化拆分——三个核心服务

| 服务 | 职责 | 对应 v1 模块 |
|------|------|-------------|
| **IngestionService** | PDF 上传 → 解析 → 分块 → 嵌入 → 索引 | pipeline.build_index + MealManager._build_pipeline |
| **QueryService** | 查询 → 检索 → 重排 → 生成 → 追踪 | pipeline.query |
| **EvalService** | 评测 → 报告 → 对比 → Bad Case 分析 | experiment + evaluators |

**关键**：三个服务通过消息队列（Redis Streams 或 Kafka）解耦，Ingestion 完成后发事件通知 Query 和 Eval。

#### 决策 3：LLM Provider 抽象

```python
@runtime_checkable
class LLMProvider(Protocol):
    async def complete(self, messages: list[Message], **kwargs) -> LLMResponse: ...
    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[LLMChunk]: ...
    def model_id(self) -> str: ...
    def token_limit(self) -> int: ...
```

内置实现：
- `AnthropicProvider`：原生 Anthropic SDK（async）
- `OpenAIProvider`：OpenAI SDK（async）
- `ProxyProvider`：适配 LongCat 等代理 API
- `MockProvider`：测试用，返回预设响应

**v1 教训**：v1 的 `api_key="dummy"` hack 和硬编码默认模型名是不可接受的。v2 的认证策略必须配置化，每个 Provider 自己处理认证细节。

#### 决策 4：配置即契约

```python
class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 严格模式

    llm: dict[str, LLMPresetConfig]
    parser: ParserConfig
    chunker: ChunkerConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    ...

def load_config(path: Path) -> AppConfig:  # 返回 Pydantic 模型，不是 dict
    raw = yaml.safe_load(path.read_text())
    return AppConfig(**raw)  # 任何拼写错误或非法值立即报错
```

**v1 教训**：v1 的 `extra: "allow"` 让 Pydantic 校验形同虚设。v2 必须是 `extra: "forbid"`，配置加载的返回值必须是 Pydantic 模型而非 dict。

#### 决策 5：异步原生

所有 I/O 操作默认 async：
- LLM API 调用：`async def complete(...)`
- 向量存储操作：`async def search(...)` / `async def upsert(...)`
- 文件 I/O：`aiofiles`
- 数据库：`asyncpg` / `motor`

同步入口仅用于 CLI 工具，内部通过 `asyncio.run()` 桥接。

**v1 教训**：v1 的同步阻塞 + ThreadPoolExecutor 方案受 GIL 限制，并发 10 个查询就需要 10 个线程。async 方案单进程可轻松处理 100+ 并发。

---

### 3.3 数据管理：Meal 2.0

v1 的 Meal 系统方向正确但实现耦合。v2 重新设计：

```
Meal = Dataset + PipelineConfig + Artifacts

Dataset:    原始 PDF 文件集（不可变，内容寻址）
PipelineConfig: 解析/分块/嵌入配置（不可变，哈希标识）
Artifacts:  解析结果/分块结果/向量索引（可从 Dataset + PipelineConfig 重建）
```

**关键改进**：

1. **Meal 与 Pipeline 完全解耦**：`build_index()` 只接受 `chunks_dir` 和 `collection_name`，不关心 Meal
2. **Artifacts 可重建**：任何 Artifact 都可以从 Dataset + PipelineConfig 重新生成，缓存只是加速手段
3. **内容寻址**：`data_id = sha256(sorted(pdf_paths))`，`config_hash = sha256(pipeline_config.json())`
4. **不可变快照**：Meal 一旦创建不可修改，只能创建新版本

---

### 3.4 Agent 系统：独立服务

v1 的维修工 Agent 与 Streamlit 深度耦合，v2 将其独立为服务：

```
AgentService
├── LangGraph Agent Core
│   ├── Tool Registry（从组件注册表自动发现可用工具）
│   ├── Checkpoint Store（SQLite/PostgreSQL）
│   └── Experience Store（向量数据库）
├── WebSocket API（流式输出）
└── 事件总线（订阅 Ingestion/Query/Eval 事件）
```

**关键改进**：

1. **资源池化**：Agent 通过服务层访问 Pipeline，不再每次重建
2. **工具自动发现**：基于组件注册表，新增组件自动暴露为 Agent 工具
3. **独立于 UI**：Agent 通过 WebSocket API 与前端通信，不绑定 Streamlit
4. **审批机制服务化**：高风险操作的确认通过 API 而非 Streamlit interrupt

---

## 四、v2 测试策略

### 4.1 测试金字塔重塑

```
        ╱  E2E  ╲           5-10 个：真实 PDF → 完整链路 → 评测报告
       ╱─────────╲          运行：test-all，~60s
      ╱ Integration ╲       30-50 个：真实组件协作（内存 Qdrant + 小模型）
     ╱───────────────╲      运行：test，~30s
    ╱    Unit Tests    ╲    200-400 个：纯逻辑验证，零 Mock
   ╱───────────────────╲   运行：test-unit，~5s
```

### 4.2 核心原则

| 原则 | v1 的教训 | v2 的做法 |
|------|----------|----------|
| **不 Mock 自己的代码** | 1123 处 Mock 验证 Mock 行为 | 只 Mock 外部服务（LLM API），内部组件用真实实例 |
| **测试有意义的业务属性** | 验证 `mock.assert_called_once_with(...)` | 验证"检索结果包含期望文档"、"生成答案与 GT 语义相似" |
| **E2E 测试是金标准** | 0 个 E2E 测试 | 每个核心链路至少 1 个 E2E 测试 |
| **真实数据 fixture** | `np.ones(1024)` 全 1 向量 | 小型真实 PDF + 预计算的 embedding + 真实评测结果 |
| **集成测试用轻量替代** | Mock 掉 Qdrant 和 Embedder | 内存 Qdrant + 小型 embedding 模型（all-MiniLM-L6-v2） |

### 4.3 测试分层

| 层级 | 数量 | 内容 | 运行命令 | 耗时 |
|------|------|------|---------|------|
| unit | 200-400 | 纯逻辑：配置校验、指标计算、文本处理、协议验证 | `pixi run test-unit` | ~5s |
| integration | 30-50 | 组件协作：内存 Qdrant + 小模型 + 真实解析器 | `pixi run test` | ~30s |
| e2e | 5-10 | 完整链路：真实 PDF → 评测报告 | `pixi run test-all` | ~60s |
| slow | 3-5 | RAGAS 评测、大模型推理 | `pixi run test-slow` | ~5min |

### 4.4 Pydantic 验证的正确用法

v1 的问题不是 Pydantic 没用，而是用错了：

| v1 做法 | v2 做法 |
|---------|---------|
| `extra: "allow"` 静默接受未知字段 | `extra: "forbid"` 拒绝未知字段 |
| `load_config()` 返回 dict | `load_config()` 返回 `AppConfig` 实例 |
| Pydantic 仅用于 Streamlit UI 展示 | Pydantic 是配置加载的必经之路 |
| 校验规则分散在各处 | 校验规则集中在 Pydantic 模型中 |

---

## 五、v2 评测系统设计

### 5.1 评测架构

```
EvalService
├── MetricRegistry（指标注册表）
│   ├── RetrievalMetrics: hit_rate, mrr, ndcg, recall@k, diversity, fpr
│   ├── GenerationMetrics: faithfulness, answer_relevancy, correctness
│   └── LLMRetrievalMetrics: context_precision, context_recall
├── EvalBackendRegistry（后端注册表）
│   ├── BuiltinBackend: 自实现指标
│   ├── RagasBackend: RAGAS 框架适配
│   └── CustomBackend: 用户自定义
├── EvalCache（评测缓存）
│   ├── 基于 question+answer+contexts+metric+prompt_version 的 hash
│   ├── Redis / SQLite 存储
│   └── prompt_version 变更自动失效
├── GroundTruthManager（GT 管理）
│   ├── 自动生成（LLM）
│   ├── 人工标注（Web UI）
│   └── 质量评分（可信度标记）
└── ReportGenerator（报告生成）
    ├── 聚合统计（均值/中位数/CI/效应量）
    ├── 对比分析（variant 间统计显著性检验）
    └── Bad Case 自动归档
```

### 5.2 关键改进

#### 5.2.1 Ground Truth 可信度分层

v1 的核心问题是 GT 质量不可控。v2 引入可信度分层：

| 可信度 | 来源 | 标记 | 用途 |
|--------|------|------|------|
| Gold | 人工标注 + 交叉验证 | 🟢 | 基线标定、发布验证 |
| Silver | LLM 生成 + 自动验证通过 | 🟡 | 日常实验、参数扫描 |
| Bronze | LLM 生成 + 未验证 | 🔴 | 快速探索、方向判断 |

**关键**：只有 Gold 级别的 GT 才用于发布决策。Silver/Bronze 仅用于方向性判断。

#### 5.2.2 评测缓存

```python
class EvalCache:
    def cache_key(self, sample: EvalSample, metric: str, prompt_version: str) -> str:
        content = f"{sample.question}|{sample.answer}|{json.dumps(sample.contexts)}|{metric}|{prompt_version}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def get_or_compute(self, key: str, compute_fn: Callable) -> float:
        cached = await self.store.get(key)
        if cached is not None:
            return cached
        result = await compute_fn()
        await self.store.set(key, result, ttl=self.ttl)
        return result
```

**v1 教训**：v1 的评测 Token 消耗极高，相同样本在不同实验中重复计算。缓存可节省 60-80% 的评测 Token。

#### 5.2.3 RAGAS 适配层隔离

```python
class RagasAdapter:
    """隔离 RAGAS 版本差异的适配层"""

    def __init__(self):
        self._ragas_version = self._detect_version()
        self._metric_classes = self._load_metrics_for_version()

    def _detect_version(self) -> tuple[int, int, int]:
        import ragas
        return tuple(int(x) for x in ragas.__version__.split("."))

    def _load_metrics_for_version(self) -> dict[str, type]:
        if self._ragas_version >= (0, 5, 0):
            return self._load_v05_metrics()
        elif self._ragas_version >= (0, 4, 3):
            return self._load_v04_metrics()
        else:
            raise UnsupportedVersionError(f"RAGAS {self._ragas_version} not supported")
```

**v1 教训**：v1 直接 import RAGAS 内部 API（`_metrics`），版本升级即断裂。v2 通过适配层隔离版本差异。

#### 5.2.4 统计显著性

```python
@dataclass
class ComparisonResult:
    metric: str
    variant_a_mean: float
    variant_b_mean: float
    variant_a_std: float
    variant_b_std: float
    p_value: float
    effect_size: float  # Cohen's d
    is_significant: bool  # p < 0.05

    @property
    def interpretation(self) -> str:
        if not self.is_significant:
            return "差异不显著，可能是噪声"
        if abs(self.effect_size) < 0.2:
            return "统计显著但实际意义微小"
        elif abs(self.effect_size) < 0.8:
            return "中等效应量，值得注意"
        else:
            return "大效应量，明确改进/退化"
```

**v1 教训**：v1 的评测报告只显示平均分，0.72 vs 0.74 的差异无法判断是真实改进还是噪声。

---

## 六、v2 生产化路线

### 6.1 部署架构

```
┌─────────────────────────────────────────────────┐
│                 Kubernetes Cluster               │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐│
│  │ API Gateway │  │ Ingestion  │  │  Query     ││
│  │ (FastAPI)   │  │ Service    │  │  Service   ││
│  │ x2 (HA)    │  │ x1-x3     │  │  x2-x5    ││
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘│
│         │               │               │       │
│  ┌──────┴─────┐  ┌──────┴─────┐  ┌──────┴─────┐│
│  │   Redis    │  │   Qdrant   │  │ PostgreSQL ││
│  │  (缓存/队列)│  │  (向量存储) │  │ (元数据/GT) ││
│  └────────────┘  └────────────┘  └────────────┘│
│                                                  │
│  ┌────────────┐  ┌────────────┐                  │
│  │  Eval      │  │  Agent     │                  │
│  │  Service   │  │  Service   │                  │
│  │  x1       │  │  x1       │                  │
│  └────────────┘  └────────────┘                  │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  可观测性: Prometheus + Grafana + Jaeger   │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 6.2 单机开发模式

v2 同时支持单机开发模式（零依赖启动）：

```bash
# 最小启动（仅内存组件，无需 Redis/Qdrant/PostgreSQL）
pixi run serve --mode=dev

# 完整启动（所有外部依赖，Docker Compose）
pixi run serve --mode=full
```

开发模式使用内存替代品：
- Redis → `dict` + `threading.Lock`
- Qdrant → `QdrantClient(":memory:")`
- PostgreSQL → SQLite

### 6.3 容器化

```dockerfile
# 多阶段构建
FROM python:3.12-slim AS base
# ... 安装 pixi + 依赖

FROM base AS api
# ... 仅 API 服务

FROM base as worker
# ... 仅 Worker 进程

FROM base AS full
# ... 完整安装（含模型下载）
```

```yaml
# docker-compose.yml
services:
  api:
    build: { target: api }
    ports: ["8000:8000"]
    depends_on: [redis, qdrant, postgres]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]

  redis:
    image: redis:7-alpine

  qdrant:
    image: qdrant/qdrant:latest
    volumes: ["qdrant_data:/qdrant/storage"]

  postgres:
    image: postgres:16-alpine
    volumes: ["pg_data:/var/lib/postgresql/data"]
```

---

## 七、v2 实施路线图

### Phase 0：地基（2 周）

**目标**：项目骨架 + 配置系统 + 组件协议

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| 项目初始化 | pixi 项目 + 依赖声明 + 目录结构 | `pixi run test` 通过 |
| 配置系统 | `AppConfig` Pydantic 模型 + `load_config()` | `extra: "forbid"` 生效，拼写错误立即报错 |
| 组件协议 | Parser/Chunker/Embedder/Retriever/Generator/Evaluator Protocol | `isinstance(impl, Protocol)` 返回 True |
| 组件注册表 | Registry 类 + 装饰器注册 | `@registry.register("pymupdf4llm")` 可用 |
| 测试基础设施 | conftest + 真实 PDF fixture + 内存 Qdrant | E2E 测试骨架通过 |

### Phase 1：核心管线（3 周）

**目标**：IngestionService + QueryService 可运行

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| Parser 实现 | pymupdf4llm / fitz / pdfplumber 三种解析器 | 解析真实 PDF，输出 ParseResult |
| Chunker 实现 | fixed / semantic / page-aware 三种分块器 | 分块结果可索引 |
| Embedder 实现 | BGE / OpenAI / Mock 三种嵌入器 | 输出正确维度向量 |
| VectorStore 抽象 | Qdrant / Milvus / 内存 三种存储 | 索引 + 检索可用 |
| Retriever 实现 | 向量 / BM25 / 混合 三种检索器 | 检索结果格式统一 |
| Generator 实现 | Anthropic / OpenAI / Mock 三种生成器 | 流式 + 非流式输出 |
| IngestionService | 解析→分块→嵌入→索引 全链路 | 真实 PDF 可入库 |
| QueryService | 查询→检索→重排→生成 全链路 | 真实查询可返回答案 |
| E2E 测试 | PDF→入库→查询→返回答案 | `pixi run test-all` 通过 |

### Phase 2：评测系统（2 周）

**目标**：EvalService 可运行，评测结果可信

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| 检索指标 | hit_rate / mrr / ndcg / recall@k / diversity / fpr | 与 v1 指标对齐 |
| 生成指标 | faithfulness / answer_relevancy / correctness | LLM-as-Judge + 缓存 |
| RAGAS 适配层 | 版本检测 + 适配器 | RAGAS 0.4.x / 0.5.x 均可运行 |
| 评测缓存 | Redis / SQLite 缓存层 | 相同样本不重复计算 |
| GT 管理器 | 自动生成 + 可信度标记 | Gold/Silver/Bronze 分层 |
| 统计报告 | 均值/CI/效应量/显著性检验 | variant 对比有统计依据 |
| EvalService | 评测全链路 | 评测结果可复现 |

### Phase 3：API 与前端（2 周）

**目标**：FastAPI 层 + Streamlit 前端

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| FastAPI 应用 | 路由 + 中间件 + 异常处理 | Swagger 文档可用 |
| 认证中间件 | API Key + JWT | 未认证请求被拒绝 |
| Ingestion API | 上传/解析/索引 端点 | curl 可调用 |
| Query API | 查询/流式 端点 | WebSocket 流式输出 |
| Eval API | 评测/报告/对比 端点 | 评测任务可提交 |
| Streamlit 前端 | 问答/评测/管理 页面 | 前端可正常使用 |
| 健康检查 | /health /ready 端点 | K8s 探针可用 |

### Phase 4：Agent 与高级功能（2 周）

**目标**：Agent 服务 + 实验系统

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| Agent 服务 | LangGraph Agent + 工具注册 | Agent 可执行运维操作 |
| 工具自动发现 | 基于组件注册表 | 新组件自动暴露为工具 |
| 实验系统 | 配置→多变体运行→报告 | 实验可复现 |
| Meal 2.0 | 数据版本管理 | Meal 可创建/复用/不可变 |
| 断点续传 | 实验级 + 问题级 checkpoint | 中断后可恢复 |

### Phase 5：生产化（2 周）

**目标**：容器化 + 监控 + 部署

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| Dockerfile | 多阶段构建 | `docker build` 成功 |
| docker-compose | 完整开发环境 | `docker compose up` 可用 |
| 结构化日志 | JSON 格式 + trace_id | 日志可聚合分析 |
| Prometheus 指标 | 查询延迟/Token 消耗/缓存命中率 | Grafana 可可视化 |
| 优雅关闭 | SIGTERM 处理器 | 无数据丢失 |
| BM25 持久化 | 索引落盘 | 重启无需重建 |
| CI/CD | GitHub Actions | PR 自动测试 + 镜像构建 |

---

## 八、v1 踩坑经验 → v2 设计决策映射

| v1 踩坑 | v2 设计决策 |
|---------|-----------|
| 评测链路修了 6 个版本 | 评测先行：Phase 2 专门做评测，MVP 阶段就建立可信基线 |
| Mock 过度，测试不硬 | 不 Mock 自己的代码，E2E 测试是金标准 |
| Pipeline 上帝对象 | 三服务拆分 + 组件协议 + 注册表 |
| Pipeline ↔ Meal 双向渗透 | Meal 与 Pipeline 完全解耦，build_index 不关心 Meal |
| Agent 每次重建 Embedder | 资源池化，Agent 通过服务层访问 |
| core/ops 只被部分采用 | 所有路径必须走抽象层，旧路径不存在 |
| Pydantic 验证旁路 | `extra: "forbid"` + `load_config()` 返回 Pydantic 模型 |
| LLM 客户端仅 Anthropic | LLMProvider Protocol + 多后端实现 |
| 零 async 代码 | 异步原生，所有 I/O 默认 async |
| 无 API 层 | FastAPI 网关层，UI 只是客户端 |
| RAGAS 内部 API 依赖 | 适配层隔离版本差异 |
| 评测缓存缺失 | 基于 hash 的评测缓存 + prompt_version 自动失效 |
| GT 质量不可控 | 可信度分层（Gold/Silver/Bronze） |
| 统计显著性缺失 | 置信区间 + Cohen's d + 显著性检验 |
| 日志 handler 生命周期 | 日志初始化只在程序入口点执行一次 |
| Streamlit rerun 冲突 | Agent 独立于 UI，通过 WebSocket 通信 |
| 缓存 hash 遗漏参数 | 配置参数与 hash 映射表，新增参数强制检查 |
| 资源生命周期 | 所有重资源实现 `async with` 上下文管理 |
| 多 worktree issue 冲突 | 基于 hash 的 ID 方案 |
| 半吊子迁移 | 迁移一步到位，旧路径不存在 |
| AI 代码人审不足 | 每个 PR 必须有人类审查，plan/spec 必须细读 |
| 功能膨胀 | 每个新功能回答"不做会怎样" |

---

## 九、技术选型

| 领域 | v1 选型 | v2 选型 | 理由 |
|------|--------|--------|------|
| Web 框架 | Streamlit | FastAPI + Streamlit | API 层与 UI 分离 |
| 异步框架 | 无 | asyncio + uvicorn | I/O 密集场景必须异步 |
| LLM SDK | anthropic + langchain | 多 Provider Protocol | 支持多后端 |
| 向量存储 | Qdrant embedded | Qdrant（可 embedded/standalone） | 开发用 embedded，生产用 standalone |
| 缓存 | 文件系统 | Redis + 文件系统 | 评测缓存需要快速 KV 存储 |
| 元数据存储 | JSON 文件 | PostgreSQL + SQLite | 开发用 SQLite，生产用 PostgreSQL |
| 消息队列 | 无 | Redis Streams | 服务间解耦 |
| Agent 框架 | LangGraph | LangGraph | 方向正确，保持 |
| 配置校验 | Pydantic（旁路） | Pydantic（强制） | 配置即契约 |
| 日志 | loguru（文本） | loguru（JSON + 文本） | 结构化日志支持聚合 |
| 指标 | 无 | Prometheus + OTLP | 可观测性 |
| 追踪 | 自定义 trace_models | OpenTelemetry | 标准化分布式追踪 |
| 容器 | 无 | Docker + K8s | 生产部署 |
| CI/CD | pre-commit | GitHub Actions | 自动化测试 + 镜像构建 |
| 测试 | pytest + 大量 Mock | pytest + 真实组件 + 少量 Mock | 测试即防线 |
| 包管理 | pixi | pixi | 保持，项目级配置 |

---

## 十、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| RAGAS 0.5 破坏性变更 | 高 | 评测系统不可用 | 适配层隔离 + 版本检测 + 锁定版本 |
| 异步改造复杂度超预期 | 中 | Phase 1 延期 | 先做同步版本，异步作为增量改进 |
| Agent 与服务层集成困难 | 中 | Phase 4 延期 | Agent 独立部署，通过 API 交互 |
| 多 Provider 适配工作量大 | 中 | LLM 切换不灵活 | 先做 Anthropic + Mock，其他 Provider 按需添加 |
| 评测缓存一致性 | 低 | 评测结果不准确 | prompt_version 强制失效 + 缓存 TTL |
| Docker 镜像过大 | 中 | 部署慢 | 多阶段构建 + 模型按需下载 |

---

## 十一、成功指标

| 指标 | v1 现状 | v2 目标 |
|------|--------|--------|
| 端到端测试覆盖 | 0 个 | 5-10 个 |
| 集成测试覆盖 | 1 个 | 30-50 个 |
| Mock 使用量 | 1123 处 | < 100 处（仅外部服务） |
| 组件可独立运行 | 3/10 | 10/10 |
| API 可用性 | 无 | RESTful API + Swagger |
| 异步支持 | 0% | 100%（所有 I/O） |
| 评测结果可信度 | Silver 级 | Gold 级（人工标注 GT） |
| 评测缓存命中率 | 0% | > 60% |
| 统计显著性 | 无 | 每个对比报告含 p-value + Cohen's d |
| 容器化 | 无 | Docker + docker-compose |
| 部署时间 | 手动 | < 10 分钟（docker compose up） |
| 健康检查 | 无 | /health + /ready |
| 认证 | 无 | API Key + JWT |

---

## 十二、总结

v1 是一次成功的"快速验证"——它证明了 RAG 管线可以跑通，实验系统可以管理多变体对比，评测系统可以量化效果。但"能跑"和"能上"之间隔着四个根本性差距：

1. **测试不硬** → v2 用 E2E + 集成测试替代 Mock 自娱自乐
2. **架构不净** → v2 用 Protocol + Registry + 三服务拆分实现乐高式组合
3. **生产不够** → v2 用 FastAPI + async + Docker + 监控补齐基础设施
4. **评测不准** → v2 用 GT 可信度分层 + 评测缓存 + 统计显著性确保结果可信

v2 不是 v1 的修补，而是站在 v1 踩坑经验上的重新出发。每一个 v1 的教训都已映射为 v2 的设计决策。目标明确：一个能上升的、快速的、从轻量到大规模都可伸缩的 RAG 实验室。
