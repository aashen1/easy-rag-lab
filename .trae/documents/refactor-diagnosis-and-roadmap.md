# ash-easy-rag 重构计划：诊断、扫盲与路线

> 本文档基于对 v0.1.17 代码的深度阅读，给出项目现状诊断、需要补强的知识领域扫盲，以及重构路线建议。

---

## 一、项目现状：它是什么，做了什么

### 1.1 核心定位

ash-easy-rag 是一个**金融研报 RAG 问答系统**，核心价值链：

```
PDF 文件 → 解析 → 分块 → 向量化 → 检索 → 生成 → 评测 → 实验报告
```

它不是一个简单的 RAG demo，而是一个**实验驱动的 RAG 实验室**——你可以用一套实验配置（exp_config），跑多个超参数变体，自动生成对比报告。这是它最有价值的设计思想。

### 1.2 已有的能力

| 能力 | 实现状态 | 对应模块 |
|------|---------|---------|
| PDF 解析 | ✅ pymupdf4llm / fitz / pdfplumber 三种 | `src/parsers/` |
| 文本分块 | ✅ fixed / page-aware / semantic 三种 | `src/chunker.py`, `src/semantic_chunker.py` |
| 向量嵌入 | ✅ BGE-large-zh | `src/embedder.py` |
| 向量索引 | ✅ Qdrant 本地模式 | `src/indexer.py` |
| 多路检索 | ✅ 向量 / BM25 / 混合检索 | `src/retriever.py`, `src/bm25_retriever.py`, `src/hybrid_retriever.py` |
| 重排序 | ✅ Cross-Encoder Reranker | `src/reranker.py` |
| 查询改写 | ✅ HyDE / MultiQuery | `src/query_rewriter.py` |
| LLM 生成 | ✅ Anthropic API | `src/generator.py` |
| 评测系统 | ✅ builtin + RAGAS 双后端 | `eval/` |
| 实验框架 | ✅ 多变体对比 + 报告生成 | `src/experiment.py`, `eval/runner/` |
| 数据管理 | ✅ Meal 系统（不可变数据快照） | `src/meal/` |
| Web UI | ✅ Streamlit 多页面 | `src/app.py`, `src/app_pages/` |
| 维修工 Agent | ✅ LangGraph Agent | `src/agent/` |
| 测试集管理 | ✅ 生成/组合/审查/标注 | `src/test_generation/`, `src/testset_cli/` |

### 1.3 代码规模

| 指标 | 数值 |
|------|------|
| 源码文件 | ~60 个 Python 文件 |
| 核心代码行数 | ~15,000+ 行（src/ 目录） |
| 测试文件 | 70 个，~2296 个测试用例 |
| 配置文件 | config.yaml + Pydantic schema |
| 文档 | 100+ 个 .md 文件 |

---

## 二、核心问题诊断：为什么它"不够结实"

### 2.1 问题一：架构耦合——"零件焊死"

**症状**：想抽一个零件出来独立用，发现到处都是牵绊。

**根因**：

1. **RAGPipeline 是上帝对象**（1077 行）：它同时负责配置解析、组件初始化、Meal 加载、检索策略选择、懒加载、资源释放、配置热替换。任何改动都可能波及全系统。

2. **Pipeline ↔ Meal 双向渗透**：`build_index()` 内部计算 data_id/config_hashes，`MealManager._build_pipeline()` 又调用 Pipeline 的组件。基础 RAG 功能被 Meal 绑架。

3. **实验运行器暴力篡改 Pipeline 内部**：`eval/runner/core.py` 直接赋值 `pipeline.indexer = None`、调用 `pipeline._setup_retrievers()` 等私有方法。Pipeline 没有提供"重新配置"的公共 API。

4. **Agent Tools 每次重建重型资源**：每次工具调用都 `RAGPipeline(meal_name=...)` 重新加载 Embedder（~1.3GB），性能灾难。

5. **core/ops 抽象层只被部分采用**：Pipeline 仍走旧路径，新旧双路径共存。

**影响**：无法独立测试或替换任何子功能，无法做成服务。

### 2.2 问题二：测试不硬——"AI 自娱自乐"

**症状**：2000+ 测试全部绿灯，但端到端跑起来不出三个操作必现 bug。

**根因**：

1. **Mock 过度**：683 处 patch/monkeypatch，测试验证的是"Mock 被按 Mock 的方式调用了"而非"真实业务逻辑正确"。test_pipeline.py 单文件 232 处 patch。

2. **集成测试近零**：仅 1 处 `@pytest.mark.integration`，测试金字塔倒置。

3. **端到端测试缺失**：0 个真实 PDF→解析→检索→生成→评测的 E2E 测试。

4. **异常路径几乎未测试**：2296 个测试中仅 13 处 `pytest.raises`，与项目定义的多种自定义异常严重不匹配。

5. **无覆盖率度量**：没有 pytest-cov / coverage 工具，无法量化实际代码覆盖率。

6. **整块模块零测试**：`src/issue/`（6 个文件）和 `src/testset_cli/`（7 个文件）完全没有测试。

7. **Marker 覆盖极度不均**：约 82% 的测试函数没有任何 marker，`pixi run test-unit` 只能覆盖一小部分。

**影响**：重构时没有安全网，改一处不知道会不会炸另一处。

### 2.3 问题三：不够专业化——"差一口气"的生产就绪度

**症状**：功能都有，但就是不能上生产。

**根因**：

| 缺失维度 | 现状 | 生产要求 |
|----------|------|---------|
| 异步支持 | 零 `async/await` | LLM API 调用天然 I/O 密集，async 可提升 10x 吞吐 |
| API 层 | 所有业务逻辑绑定在 Streamlit | 需要 RESTful API 供程序化调用 |
| 容器化 | 无 Dockerfile | 容器化部署是生产化的基础 |
| 认证授权 | 无 | 至少需要 API Key 认证 |
| 健康检查 | 无 `/health` `/ready` | K8s 部署的前提 |
| 结构化日志 | 纯文本日志 | 需要 JSON 结构化日志 + 请求关联 |
| 资源监控 | 无 Prometheus 指标 | 需要接入监控告警系统 |
| 优雅关闭 | 无信号处理器 | 进程被 kill 可能丢数据 |
| BM25 持久化 | 纯内存索引 | 大数据集启动慢 |

**影响**：无法在服务器上真正部署，无法支撑真实用户。

### 2.4 问题四：类型与配置不结实

**症状**：配置写错一个字段名，系统不报错，静默用默认值。

**根因**：

1. **Pydantic 验证旁路**：`load_config()` 返回 `dict[str, Any]`，验证后立即 `model_dump()` 回 dict。所有下游消费者操作原始字典，丧失类型安全。

2. **`extra: "allow"`**：Pydantic 模型允许未知字段，拼写错误的配置键被静默忽略。

3. **ExperimentConfig / MealConfig 是 dataclass**：没有 Pydantic 的运行时类型验证。

4. **config_overrides 绕过验证**：`deep_merge` 后的 effective_config 没有经过 Pydantic 验证。

5. **LLM 配置通过环境变量间接引用**：Pydantic 验证时看到的是 `"LLM_MODEL_ID"` 字符串，不是实际模型 ID。

**影响**：配置错误在运行时才暴露，而且往往以难以调试的方式失败。

---

## 三、知识扫盲：你需要补强的领域

下面按照"从近到远"的顺序，把重构需要的知识领域梳理一遍。每个领域我会说明：它是什么、属于什么岗位、你现在缺什么、怎么学。

### 3.1 🏗️ 领域一：软件架构设计（后端架构师 / Tech Lead）

**这是什么**：决定代码怎么组织、模块怎么拆分、依赖怎么管理的学问。你现在的核心问题（Pipeline 上帝对象、双向耦合）本质上都是架构问题。

**你需要知道的关键概念**：

| 概念 | 一句话解释 | 对应你项目的问题 |
|------|-----------|----------------|
| **依赖注入 (DI)** | 不在类内部创建依赖，而是从外部传入 | Pipeline 内部 `self.embedder = Embedder(...)` 应改为外部传入 |
| **依赖倒置原则 (DIP)** | 高层模块不依赖低层模块，两者都依赖抽象 | Pipeline 不应依赖具体的 Embedder 类，而应依赖 Embedder 协议 |
| **Protocol / Interface** | Python 的结构化子类型，定义"能做什么"而不关心"是什么" | 检索器、解析器、生成器都应定义 Protocol |
| **注册表模式 (Registry)** | 用名字注册实现类，运行时按名查找 | `@registry.register("pymupdf4llm")` 替代 if-else 分支 |
| **服务层模式** | 把业务逻辑从基础设施（DB/API/UI）中分离出来 | QueryService / IngestionService / EvalService |
| **六边形架构** | 核心业务不依赖任何外部框架，外部通过端口适配 | RAG 核心逻辑不应知道 Streamlit / Qdrant 的存在 |
| **CQRS** | 读写分离——索引构建（写）和查询（读）是不同的模型 | build_index 和 query 应该是两个独立服务 |

**岗位**：后端架构师、Tech Lead、高级后端工程师

**怎么学**：
- 📖 《架构整洁之道》(Robert C. Martin)——核心是讲依赖规则和边界
- 📖 《实现领域驱动设计》(Vaughn Vernon)——讲限界上下文和服务拆分
- 🎥 "Hexagonal Architecture" by Alistair Cockburn（原文短文，Google 可搜到）
- 🔨 实践：先把你项目的 `RAGPipeline` 拆成 3 个 Protocol + 3 个 Service，体会解耦

### 3.2 🌐 领域二：API 设计与 Web 服务开发（后端工程师）

**这是什么**：把你的 RAG 能力暴露为 HTTP API，让任何客户端（Web/CLI/SDK）都能调用。这是"前后端分离"的核心。

**你需要知道的关键概念**：

| 概念 | 一句话解释 | 你项目需要做的 |
|------|-----------|--------------|
| **RESTful API** | 用 HTTP 方法（GET/POST/PUT/DELETE）操作资源的标准风格 | `/api/v1/query`, `/api/v1/datasets`, `/api/v1/experiments` |
| **FastAPI** | Python 最流行的异步 Web 框架，自带 Swagger 文档 | 替代 Streamlit 成为 API 层 |
| **Pydantic 请求/响应模型** | 用 Pydantic 定义 API 的输入输出类型 | `QueryRequest(BaseModel)` / `QueryResponse(BaseModel)` |
| **中间件** | 请求/响应的拦截器，用于认证、日志、限流等横切关注点 | 认证中间件、请求日志中间件、CORS 中间件 |
| **异步 (async/await)** | 非阻塞 I/O，一个进程可同时处理多个请求 | `async def query()` 替代 `def query()` |
| **WebSocket** | 双向持久连接，适合流式输出 | LLM 流式生成用 WebSocket 推送 |
| **OpenAPI / Swagger** | API 文档自动生成 | FastAPI 自带，零成本 |
| **CORS** | 跨域资源共享，前端和后端不同域时必须配置 | Streamlit/React 调 FastAPI 时需要 |
| **API 版本化** | `/api/v1/` vs `/api/v2/`，保证向后兼容 | 初期就加 `/v1/` 前缀 |

**岗位**：后端工程师、全栈工程师

**怎么学**：
- 📖 FastAPI 官方教程（https://fastapi.tiangolo.com/）——最好的入门，边读边写
- 📖 《RESTful Web APIs》(Richardson & Ruby)——REST 设计原则
- 🔨 实践：用 FastAPI 写一个 `/api/v1/query` 端点，能接收问题、返回答案

### 3.3 🧪 领域三：测试工程（测试工程师 / SDET）

**这是什么**：不只是"写测试"，而是设计一套测试策略，让测试真正能保护你。

**你需要知道的关键概念**：

| 概念 | 一句话解释 | 你项目的问题 |
|------|-----------|------------|
| **测试金字塔** | 单元测试多、集成测试中、E2E 测试少，形成金字塔 | 你现在是倒金字塔——大量 Mock 单元 + 几乎无集成/E2E |
| **测试替身 (Test Double)** | Mock / Stub / Fake / Spy 的统称 | 你只用了 Mock，应该多用 Fake（如内存 Qdrant） |
| **契约测试** | 验证两个模块之间的接口约定 | Pipeline 和实验运行器之间应有契约测试 |
| **测试分层** | unit / integration / e2e / smoke / regression | 你的 marker 体系形同虚设 |
| **覆盖率** | 代码行覆盖率 / 分支覆盖率 / 变异测试 | 你完全没有覆盖率工具 |
| **Fixture 设计** | 测试数据的组织方式 | 你的 fixture 太假（`np.ones(1024)` 全 1 向量） |
| **属性测试 (Property-based)** | 用规则自动生成大量测试输入 | 适合测试分块、指标计算等有数学属性的模块 |

**岗位**：SDET（软件开发测试工程师）、QA 工程师

**怎么学**：
- 📖 《测试驱动的面向对象软件开发》(Kent Beck)——TDD 的经典
- 📖 《Effective Software Testing》(Maurício Aniche)——现代测试工程实践
- 🎥 "Integrated Tests Are a Scam" by J.B. Rainsberger（YouTube）——讲为什么集成测试不是万能的
- 🔨 实践：给你项目写 5 个 E2E 测试（真实 PDF → 完整链路 → 断言结果）

### 3.4 🐳 领域四：DevOps 与容器化（DevOps 工程师 / SRE）

**这是什么**：让你的应用能自动化地构建、部署、运行、监控。

**你需要知道的关键概念**：

| 概念 | 一句话解释 | 你项目需要做的 |
|------|-----------|--------------|
| **Docker** | 把应用和它的依赖打包成一个可移植的容器 | 写 Dockerfile，`docker build` 出镜像 |
| **docker-compose** | 定义和运行多容器应用 | API + Qdrant + Redis + PostgreSQL 一键启动 |
| **健康检查** | `/health`（进程活着）和 `/ready`（可以服务了） | K8s/Compose 依赖这个判断服务状态 |
| **结构化日志** | JSON 格式日志，含 trace_id/request_id | loguru 输出 JSON，方便 ELK/Loki 聚合 |
| **可观测性三支柱** | 日志(Logs) + 指标(Metrics) + 追踪(Traces) | Prometheus 指标 + OpenTelemetry 追踪 |
| **CI/CD** | 代码提交后自动测试、构建、部署 | GitHub Actions: lint → test → build → push |
| **优雅关闭** | 收到 SIGTERM 后完成当前请求再退出 | FastAPI 的 lifespan 事件 |
| **环境分离** | dev / staging / prod 配置隔离 | 不同 config.yaml 或环境变量 |

**岗位**：DevOps 工程师、SRE（站点可靠性工程师）、平台工程师

**怎么学**：
- 📖 Docker 官方教程（https://docs.docker.com/get-started/）
- 📖 《SRE: Google 运维解密》——理解 SRE 思维
- 🔨 实践：写一个 Dockerfile 把你的 FastAPI 服务容器化，用 docker-compose 加上 Qdrant

### 3.5 🔒 领域五：安全与认证（安全工程师 / 后端工程师）

**这是什么**：保护你的 API 不被未授权访问。

**你需要知道的关键概念**：

| 概念 | 一句话解释 | 你项目需要做的 |
|------|-----------|--------------|
| **API Key 认证** | 最简单的认证：请求头带 `X-API-Key` | 内部服务/CLI 用这个就够了 |
| **JWT** | 无状态令牌，包含用户信息和过期时间 | 如果需要多用户，用 JWT |
| **OAuth2** | 第三方授权协议 | 暂时不需要，除非要接企业 SSO |
| **HTTPS** | 加密传输 | 生产环境必须 |
| **输入校验** | 防止注入攻击 | Pydantic 天然支持 |
| **速率限制** | 防止 API 被滥用 | slowapi 中间件 |

**岗位**：安全工程师、后端工程师

**怎么学**：
- 📖 FastAPI 官方 Security 章节（https://fastapi.tiangolo.com/tutorial/security/）
- 🔨 实践：给 FastAPI 加 API Key 认证中间件

### 3.6 ⚡ 领域六：异步编程（后端工程师）

**这是什么**：让你的服务在等待 I/O（LLM API、数据库、文件）时不阻塞，一个进程处理多个请求。

**你需要知道的关键概念**：

| 概念 | 一句话解释 | 你项目的问题 |
|------|-----------|------------|
| **async/await** | 协程语法，遇到 I/O 自动让出控制权 | 你的代码全是同步的 |
| **事件循环** | asyncio 的核心，调度协程执行 | FastAPI/uvicorn 自带事件循环 |
| **asyncio.gather** | 并发执行多个协程 | 多个 LLM 请求可以并发 |
| **aiohttp / httpx** | 异步 HTTP 客户端 | 替代同步的 requests |
| **线程 vs 协程** | 线程是 OS 调度，协程是用户态调度 | 协程更轻量，单进程可处理万级并发 |
| **GIL** | Python 全局解释器锁，限制真并行 | CPU 密集（embedding）仍需多进程，I/O 密集用协程 |

**岗位**：后端工程师

**怎么学**：
- 📖 Python 官方 asyncio 文档（https://docs.python.org/3/library/asyncio.html）
- 📖 《Python Concurrency with asyncio》(Matthew Fowler)
- 🔨 实践：把 `Generator.generate()` 改成 `async def generate()`

### 3.7 📊 领域七：可观测性（SRE / 平台工程师）

**这是什么**：让你知道系统在干什么、出了什么问题。

**你需要知道的关键概念**：

| 概念 | 一句话解释 | 你项目需要做的 |
|------|-----------|--------------|
| **Prometheus** | 指标收集系统，拉取式 | 暴露 `/metrics` 端点 |
| **Grafana** | 指标可视化仪表盘 | 查询延迟、Token 消耗、缓存命中率 |
| **OpenTelemetry** | 统一的追踪/指标/日志标准 | 自动追踪每个请求的完整链路 |
| **trace_id** | 贯穿一个请求所有日志的唯一 ID | 请求进来时生成，传给所有组件 |
| **结构化日志** | JSON 格式，机器可解析 | loguru + JSON sink |

**岗位**：SRE、平台工程师

**怎么学**：
- 📖 OpenTelemetry Python 官方文档
- 🔨 实践：给 FastAPI 加 Prometheus 中间件，在 Grafana 里看 QPS 和延迟

---

## 四、重构路线建议

### 4.1 总体策略：渐进式重构 vs 推倒重来

**推荐：推倒重来，但保留核心思想**

理由：
1. v1 的耦合太深，渐进式重构的成本可能比推倒重来更高（你需要同时维护两套体系）
2. 你要加的东西（async、API 层、容器化）从根本上改变了架构，不是在旧架构上能"加"的
3. 但 v1 的**核心思想**（实验配置→多变体运行→评测报告）和**领域知识**（PDF 解析、RAG 管线、评测指标）必须保留

### 4.2 分阶段路线

#### Phase 0：地基（1-2 周）

**目标**：新项目骨架 + 配置系统 + 组件协议

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| 新项目初始化 | pixi 项目 + 目录结构 + 依赖声明 | `pixi run test` 通过 |
| 配置系统 | `AppConfig` Pydantic 模型 + `load_config()` | `extra: "forbid"` 生效，拼写错误立即报错 |
| 组件协议 | Parser/Chunker/Embedder/Retriever/Generator Protocol | `isinstance(impl, Protocol)` 返回 True |
| 组件注册表 | Registry 类 + 装饰器注册 | `@registry.register("pymupdf4llm")` 可用 |
| 测试基础设施 | conftest + 真实 PDF fixture + 内存 Qdrant | E2E 测试骨架通过 |

**学习重点**：领域一（架构设计）+ 领域三（测试工程）

#### Phase 1：核心管线（2-3 周）

**目标**：IngestionService + QueryService 可运行

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| Parser 实现 | pymupdf4llm / fitz 解析器 | 解析真实 PDF，输出 ParseResult |
| Chunker 实现 | fixed / semantic / page-aware 分块器 | 分块结果可索引 |
| Embedder 实现 | BGE / Mock 嵌入器 | 输出正确维度向量 |
| VectorStore 抽象 | Qdrant / 内存存储 | 索引 + 检索可用 |
| Retriever 实现 | 向量 / BM25 / 混合检索器 | 检索结果格式统一 |
| Generator 实现 | Anthropic / Mock 生成器 | 流式 + 非流式输出 |
| IngestionService | 解析→分块→嵌入→索引 全链路 | 真实 PDF 可入库 |
| QueryService | 查询→检索→重排→生成 全链路 | 真实查询可返回答案 |
| E2E 测试 | PDF→入库→查询→返回答案 | `pixi run test-all` 通过 |

**学习重点**：领域六（异步编程）+ 领域一（架构设计）

#### Phase 2：API 层（1-2 周）

**目标**：FastAPI 层，前后端分离

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| FastAPI 应用 | 路由 + 中间件 + 异常处理 | Swagger 文档可用 |
| 认证中间件 | API Key 认证 | 未认证请求被拒绝 |
| Ingestion API | 上传/解析/索引 端点 | curl 可调用 |
| Query API | 查询/流式 端点 | WebSocket 流式输出 |
| 健康检查 | /health /ready 端点 | 探针可用 |
| Streamlit 前端 | 问答页面（调用 API 而非直接用 Pipeline） | 前端可正常使用 |

**学习重点**：领域二（API 设计）+ 领域五（安全与认证）

#### Phase 3：评测系统（2 周）

**目标**：EvalService 可运行，评测结果可信

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| 检索指标 | hit_rate / mrr / ndcg / recall@k | 与 v1 指标对齐 |
| 生成指标 | faithfulness / answer_relevancy | LLM-as-Judge + 缓存 |
| 评测缓存 | SQLite 缓存层 | 相同样本不重复计算 |
| GT 管理器 | 自动生成 + 可信度标记 | Gold/Silver/Bronze 分层 |
| 统计报告 | 均值/CI/效应量 | variant 对比有统计依据 |
| EvalService | 评测全链路 | 评测结果可复现 |

**学习重点**：统计学基础（置信区间、效应量、显著性检验）

#### Phase 4：实验框架 + Meal 2.0（1-2 周）

**目标**：实验配置→多变体运行→报告 的完整闭环

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| 实验系统 | 配置→多变体运行→报告 | 实验可复现 |
| Meal 2.0 | 数据版本管理 | Meal 可创建/复用/不可变 |
| 断点续传 | 实验级 + 问题级 checkpoint | 中断后可恢复 |

#### Phase 5：生产化（2 周）

**目标**：容器化 + 监控 + 部署

| 任务 | 产出 | 验收标准 |
|------|------|---------|
| Dockerfile | 多阶段构建 | `docker build` 成功 |
| docker-compose | 完整开发环境 | `docker compose up` 可用 |
| 结构化日志 | JSON 格式 + trace_id | 日志可聚合分析 |
| Prometheus 指标 | 查询延迟/Token 消耗/缓存命中率 | Grafana 可可视化 |
| 优雅关闭 | SIGTERM 处理器 | 无数据丢失 |
| CI/CD | GitHub Actions | PR 自动测试 + 镜像构建 |

**学习重点**：领域四（DevOps）+ 领域七（可观测性）

---

## 五、学习路径建议

### 5.1 优先级排序

| 优先级 | 领域 | 理由 |
|--------|------|------|
| 🔴 P0 | 架构设计 | 不懂架构，后面所有东西都建在沙子上 |
| 🔴 P0 | API 设计 (FastAPI) | 这是"前后端分离"的核心，也是你明确提出的需求 |
| 🟡 P1 | 测试工程 | 重构没有测试保护就是裸奔 |
| 🟡 P1 | 异步编程 | FastAPI 天然异步，不懂 async 写不好 API |
| 🟢 P2 | DevOps / 容器化 | Phase 5 才需要，但早点学不亏 |
| 🟢 P2 | 可观测性 | 生产化阶段需要 |
| 🔵 P3 | 安全与认证 | API Key 认证很简单，JWT 可以后学 |

### 5.2 最小学习路径（2 周内可上手）

1. **第 1-3 天**：读 FastAPI 官方教程的前半部分（路径操作、请求体、依赖注入），写一个 Hello World API
2. **第 4-5 天**：读《架构整洁之道》第 8-13 章（依赖管理、边界），理解为什么你的 Pipeline 需要拆
3. **第 6-7 天**：学习 Python Protocol 和依赖注入，把你项目的 Embedder/Retriever/Generator 定义为 Protocol
4. **第 8-10 天**：学习 async/await 基础，写一个异步的 LLM 调用函数
5. **第 11-14 天**：开始 Phase 0 的实际编码

### 5.3 推荐的学习资源汇总

| 资源 | 类型 | 覆盖领域 | 时间投入 |
|------|------|---------|---------|
| FastAPI 官方教程 | 文档+代码 | API 设计 | 2-3 天 |
| 《架构整洁之道》 | 书 | 架构设计 | 1 周 |
| Python asyncio 官方文档 | 文档 | 异步编程 | 1-2 天 |
| Docker 官方入门教程 | 文档+代码 | 容器化 | 1 天 |
| 《Effective Software Testing》 | 书 | 测试工程 | 1 周 |
| OpenTelemetry Python 入门 | 文档 | 可观测性 | 1 天 |

---

## 六、关键决策点（需要你决定）

### 6.1 新项目还是同仓库新目录？

- **选项 A**：新建一个独立仓库（如 `ash-rag-lab`），完全从零开始
- **选项 B**：在当前仓库的 `v2/` 目录下开发，可以方便地参考 v1 代码
- **选项 C**：在当前仓库的新分支上开发

### 6.2 异步优先还是同步优先？

- **选项 A**：从一开始就 async 原生（学习曲线陡，但架构正确）
- **选项 B**：先同步实现，验证逻辑正确后再改 async（稳妥但可能需要二次重构）

### 6.3 数据库选型？

- **选项 A**：SQLite（零依赖，开发友好，单机够用）
- **选项 B**：PostgreSQL（生产级，但开发环境需要额外部署）
- **选项 C**：开发用 SQLite，生产用 PostgreSQL（通过 SQLAlchemy 抽象层切换）

### 6.4 前端策略？

- **选项 A**：继续用 Streamlit（快速，但受限于 Streamlit 的架构）
- **选项 B**：用 React/Vue 独立前端（最灵活，但前端开发量大）
- **选项 C**：Streamlit 先行，后续按需换（务实）

---

## 七、总结

你的项目 v1 做了一件很有价值的事：**验证了 RAG 实验室的可行性**。从 PDF 到评测报告的完整闭环已经跑通，Meal 系统、实验框架、维修工 Agent 都是有意义的设计。

但 v1 的"不够结实"是结构性的——不是修修补补能解决的。核心问题是：

1. **架构耦合**：Pipeline 上帝对象 + 双向依赖 + 暴力篡改内部
2. **测试不硬**：Mock 自娱自乐 + 零 E2E + 零覆盖率
3. **生产不够**：无 API 层 + 无异步 + 无容器化 + 无认证
4. **类型不结实**：Pydantic 旁路 + dict 到处传 + 配置无验证

重构需要的知识横跨**后端架构、API 设计、测试工程、DevOps、安全、异步编程、可观测性**七个领域。但核心中的核心是**架构设计 + API 设计**——这两个搞定了，其他都是锦上添花。

建议的学习路径：先花 2 周学 FastAPI + 架构设计基础，然后开始 Phase 0 编码。边做边学，比纯看书有效得多。
