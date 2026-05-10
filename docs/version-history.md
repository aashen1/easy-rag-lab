# 版本演进年轮

<!-- status: active -->

> 最后更新：2026-05-10

本文档记录项目的版本迭代历程，每个版本的关键决策、交付成果和经验教训。

> 说明：因为一直在修LLM合成评测集的质量问题，一直拖着没有发版，东做做西做做积压了几百个commit，于是让LLM帮忙想了个"故事感"，一下子拆了五个版本出来，这个调子，只能说~~很装~~

---

## v0.1.17 (2026-05-10)

### 版本主题

修得好

### 叙事

> v0.1.16 让系统学会了"看病"——Bad Case 从发现到诊断全链路闭环。
>
> 这一版让系统拥有了"自主维修"的能力：LangGraph Agent 编排全链路工具调用，Session 持久化让对话不再丢失，经验积累让维修越做越聪明。共享单元层为 Agent 和实验系统架起统一桥梁，Pydantic 配置校验让系统更健壮，Streamlit 维修工页面让 AI 维修触手可及。
>
> 不是只会诊断，而是能动手修好。

### 关键决策

- 采用 LangGraph StateGraph 构建 Agent 维修工系统，agent → approval → tools 三节点循环图，支持 interrupt 审批和条件边路由
- 建立 20+ 个 @tool 覆盖 RAG 全链路操作，安全工具与高风险工具分级管理，FORBIDDEN_OPERATIONS 硬拦截
- 新建共享单元层（src/core/ops/），将解析、分块、嵌入、索引、评测逻辑从 Pipeline/Meal 中提取为独立函数，为 Agent 和实验系统提供统一接口
- Session 持久化采用 SQLite（SqliteSaver + SessionManager），支持跨会话状态恢复和孤儿 checkpoint 迁移
- 经验存储从 InMemoryStore+JSON 迁移到 SqliteStore，旧数据自动迁移（单向不可回退），改为用户手动触发保存
- 引入 Pydantic 配置校验系统，config.yaml 的 schema 验证、必填项校验、范围校验集成到 load_config()
- 轻量/全量双模式设计：轻量模式限制 1-2 个 PDF、删除阈值 3 次；全量模式开放 Meal 批量体系、删除阈值 10 次
- 诊断前置守卫：必须先诊断再修复，防止 Agent 盲目操作

### 交付成果

- **维修工 Agent 系统**：LangGraph StateGraph 编排、20+ 个 @tool（安全/高风险/报告三类）、approval_node 审批机制、FORBIDDEN_OPERATIONS 硬拦截、诊断前置守卫、删除计数阈值、.trashbin 自动备份
- **维修工 CLI**：`pixi run agent` 交互式入口，支持 :parse/:back/:compare/:report/:history/:status/:review/:mode/:sessions 等指令
- **Streamlit 维修工页面**：对话历史列表、工具链锁定、模式切换、自动审查、思考过程折叠、经验库管理、Mermaid 架构图
- **Session 管理系统**：SQLite 持久化 SessionManager、session_id/thread_id 自动生成、auto_title、孤儿 checkpoint 迁移
- **经验持久化系统**：SqliteStore 领域层包装器、namespace 结构、旧 JSON 自动迁移、手动触发保存
- **共享单元层**：src/core/ops/ 6 个模块（parse/chunk/embed/index/evaluate/query），parser/chunker/embedder/indexer 全部迁移到 core/ops 调用
- **Pydantic 配置校验**：config.yaml schema 验证、必填项校验、范围校验、集成到 load_config()
- **维修/对比报告**：maintenance_report.py（Markdown 维修报告）、comparison_report.py（多方案指标对比）
- **资源管理增强**：RAGPipeline.close()、Embedder/Reranker/BM25Retriever unload/clear、实验 variant 间共享 Embedder
- **Web UI 改进**：streamlit-searchbox 集成、公司名标签、思考过程折叠/展开、对话框位置修正、Mermaid 架构图渲染
- **代码健康**：MaintenanceState dict→TypedDict、Agent 配置集中化、LLM 客户端 lru_cache、废弃 eval/run_eval.py 移除

### 版本验收

- Git tag: `v0.1.17`
- L1: lint + test-all 全绿（2377 passed, 10 skipped）
- L2: CHANGELOG + version-history 完整

---

## v0.1.16 (2026-05-04)

### 版本主题

诊得明

### 叙事

> v0.1.15 让系统跑得快，但跑得快不等于跑得对。
>
> 这一版让系统学会"看病"——Bad Case 从发现到追踪到诊断到根因定位，全链路闭环；解析链路从"能用"升级为"精调"，混合架构让表格不再是盲区；实验系统学会"省着花"，报告复用和缓存校验让算力不再浪费；测试集管线从碎片化走向统一入口。
>
> 不是跑得更快，而是跑得更明白。

### 关键决策

- 建立 Bad Case 闭环分析体系：收集→追踪→诊断→根因定位，Pipeline trace 捕获 + Case Analyzer 可视化 + Root Cause Diagnoser 自动归因
- 采用两步法解析架构（CompositeParser = 主力解析器 + 表格增强器），6 种候选管线抽样实验确定默认链路为 pymupdf4llm + pdfplumber(text)，OCR 关闭
- 实验报告引入复用机制（InPlaceReuseHandler + CopyMigrateHandler），配置指纹识别判断是否实质相同
- 测试集管线整合：TestSetComposer + testset_review + testset_cli 统一入口，消除碎片化
- 统一 --query/--interactive/--build-index 到 Meal/Artifact 系统，消除独立链路
- 引入 call_with_retry 指数退避处理 429 限流，压力测试确定安全并发上限（safe_max=21，默认 10）
- 建立三层测试体系（unit / standard / all）+ pytest-xdist 并行加速

### 交付成果

- **Bad Case 闭环分析**：case_collector（5 文件完整可复现）、trace_models（管线各阶段中间结果）、case_diagnoser（6 类根因自动诊断 RC-0~RC-5）、retrieval_analyzer（检索质量分析）、ground_truth_finder（标准答案定位）、query_history（CLI 环形历史缓冲区）、interactive_qa（多轮对话 + /badcase 命令）、case_analyzer 页面（Streamlit 可视化分析）
- **混合解析链路**：CompositeParser 两步法架构、FitzParser（纯 fitz 主力）、PdfPlumberEnhancer（表格补强）、better_wins 多维度质量比较（行数/空单元格率/合并单元格率）、parser_benchmark 独立评测模块、PdfPlumberEnhancer 性能优化（PDF 只开一次）
- **实验系统增强**：experiment_reuse（InPlaceReuseHandler + CopyMigrateHandler + 配置指纹）、llm_retry（call_with_retry 指数退避）、ResumeConfig YAML 支持、S9 evaluation profiling stage
- **测试集管线整合**：TestSetComposer（合并/过滤/增量组合）、testset_review（AI 审核）、testset_cli（统一 CLI：enrich/review/approve/compose/generate/migrate）、distribution 模块提取
- **Meal 系统统一**：get_or_create_full_meal()、meals.default_name 配置、--query/--interactive/--build-index 自动接入 Meal
- **多轮对话贯通**：chat_history 从 CLI → Pipeline → Generator 全链路、save_case_with_dedup 去重、build_chat_history 重构
- **缓存与配置修复**：prepare_meal 配置匹配检查（防旧缓存）、find_full_dataset_meal config_hashes 校验、page_chunks 模式缓存复用、load_config 结果缓存
- **日志系统修复**：setup_logger handler 生命周期管理、RAGPipeline 移除 setup_logger 调用、实验日志 handler 保护
- **测试基础设施**：三层测试 + pytest-xdist 并行、unit marker 标注、Streamlit AppTest 冒烟测试、BM25Retriever class-scoped fixture 复用
- **代码健康**：docstring 补全、类型标注修正、控制字符 JSON 修复、profiling stage 追踪修正、Qdrant 并发访问冲突修复

### 版本验收

- Git tag: `v0.1.16`
- L1: lint + test-all 全绿
- L2: 归档文档完整性验证（32 documents + 12 specs = 44 文件，逐文件 diff 全 OK）

---

## v0.1.15 (2026-05-01)

### 版本主题

实验加速

### 叙事

> v0.1.14 治好了骨架，这一版让骨架跑起来。
>
> 并发查询、断点续跑、线程安全——实验不再是单线程的漫长等待，而是可控的并行加速。Streamlit UI 也从"能看"升级为"能聊"，多轮对话和动态调参让探索更直觉。

### 关键决策

- 实验运行器引入并发查询/评测机制，通过 `clone_for_concurrency()` 共享只读组件、重建有状态组件
- 问题级 checkpoint + 原子写入实现断点续跑，`--resume` CLI 支持中断恢复
- Pipeline 引入 `config_overrides` + lazy loading，Streamlit 侧边栏可动态调参无需重启
- 评测体系统一 error_handler 模块，MetricResolver 优雅过滤不可用后端
- Streamlit UI 迁移至 `st.html`，废弃 `st.components.v1.html`

### 交付成果

- **实验运行器增强**：并发查询（`concurrent_queries`）、并发评测（`builtin_concurrent_workers`）、问题级 checkpoint 断点续跑、`--resume` CLI、原子写入、线程安全 TokenTracker、`RAGPipeline.clone_for_concurrency()`、indexer 缓存复用 + `VectorIndexer.reopen()`
- **Streamlit UI 交互升级**：多轮对话历史、动态 config_overrides 侧边栏、lazy loading（BM25/Reranker/QueryRewriter）、浮动导航按钮、`st.html` 迁移
- **评测体系增强**：recall@3/5/10 指标、MetricResolver 优雅过滤不可用后端、error_handler 统一模块、BuiltinEvaluator 配置修复
- **Pipeline 重构**：`deep_merge` 提取到 utils.py、`top_k` 动态参数、BM25Retriever 签名统一、QueryRewriter auth 修复、dead code 清理
- **代码健康**：docstring 补全、类型标注修正（`str | None`）、`sanitize_name()` 去重（6x→1x）、CLAUDE.md 精简（116→76 行）、trashbin-rule 强化

### 版本验收

- Git tag: `v0.1.15`
- L1: lint + 1642 单元测试全绿
- L2: 补充 `clone_for_concurrency()` 和 `VectorIndexer.reopen()`/`is_closed()` 单元测试
- L3: smoke_quick.yaml 端到端冒烟通过

---

## v0.1.14 (2026-04-29)

### 版本主题

代码健康治理

### 叙事

> 看得见的产品有了，看不见的骨架也得撑得住。

v0.1.13 让 RAG 有了可展示的界面，但底层四个巨型文件已经成了"轻度屎山"的典型症状。这一版把上帝文件拆包为独立模块，补齐了 pipeline 策略模式和 Pydantic 配置校验，同时完成了文档目录的叙事化重组。

### 关键决策

- 将 4 个巨型文件（5000/3000/1800/1500 行）拆分为独立包，每个子模块职责单一
- Pipeline.query() 应用策略模式，解耦查询改写和检索策略
- ExperimentConfig 从手动 validate() 迁移到 Pydantic 模型校验
- 文档目录从 docs/guides/ 拆分为 docs/user-guides/ 和 docs/dev-guides/

### 交付成果

- **test_generator.py 拆包**：~5000 行 → `src/test_generation/` 包（9 子模块：generator, llm_caller, document_loader, segment_builder, models, validators, supplement, prompts, chunk_locator）
- **meal.py 拆包**：~1500 行 → `src/meal/` 包（6 子模块：manager, builders, cache, hashes, models, utils）
- **run_experiment.py 拆包**：~3000 行 → `eval/runner/` 包（8 子模块：core, evaluation, metrics, preparation, comparison, reporting, reproduction, asset_verifier）
- **experiment_reporter.py 拆包**：~1800 行 → `eval/reporter/` 包（5 子模块：models, formatters, llm_reporter, template_single, template_variant）
- **Pipeline 策略模式**：query_rewrite_strategies.py + retrieval_strategies.py
- **Pydantic 配置校验**：experiment_schemas.py 替代手动 validate()
- **Golden testset 生成质量提升**：自适应 CJK 引文长度、对抗性过滤、证据自动补充、per-type max_tokens、missing-type 专用 prompt
- **硬编码清除**：API URL 和模型名移入配置
- **文档重组**：user-guides / dev-guides 分离 + 归档按版本叙事重构
- **验收报告**：[acceptance-report.md](.archive/v0.1.14-code-health-era/release/v0.1.14/acceptance-report.md)

### 版本验收

- Git tag: `v0.1.14`

---

## v0.1.13 (2026-04-28)

### 版本主题

RAG 可视化

### 叙事

> 看不见的系统只能靠信仰，看得见的系统才能靠判断。

RAG 一直是命令行里的黑盒。现在你能看见它、摸到它、和它对话了。

### 关键决策

- 采用 Streamlit 构建 Web UI，提供交互式 RAG Q&A Demo
- PDF 预览通过 HTTP server + st.iframe 实现，绕过浏览器沙箱限制
- Issue 系统 ID 从序列文件改为从已有文件推导，消除序列维护开销

### 交付成果

- **Streamlit Web UI**：交互式 RAG Q&A Demo，chat_input Enter-to-send 交互
- **PDF 预览**：HTTP server + iframe 方案，tab-based 预览 + 页码跳转
- **Mermaid 架构图**：Diagram/Code 切换视图
- **Meal 文件列表**：Web UI 中查看 meal 包含的文件
- **Issue ID 优化**：消除序列文件，从已有 issue 文件推导 ID；修复 ID 碰撞检测
- **问题生成质量**：largest remainder 方法分配问题类型、irrelevant 专用 prompt、LLM 输出类型覆盖校验
- **RAGAS 修复**：有/无 reference 样本分开评测、Markdown 表格 context_recall 句分割

### 版本验收

- Git tag: `v0.1.13`

---

## v0.1.12 (2026-04-28)

### 版本主题

项目治理

### 叙事

> 个人项目靠记忆，团队项目靠系统。我们选择了系统。

项目从"能跑"长成了"要维护"。Issue 系统、代码规范、跨 session 记忆——我们在为长期作战打地基。

### 关键决策

- 引入分布式 Issue 管理系统替代 backlog.md，支持 CLI 操作和多 worktree
- 建立自定义异常体系，替代内置 Exception
- 引入 ruff + pre-commit 统一代码风格
- 建立 project-memory skill 实现跨 session 记忆传递

### 交付成果

- **Issue 管理系统**：CLI（create/list/show/start/done/context），状态流 todo→in_progress→review→done
- **Issue 迁移**：从 backlog.md 迁移 169 个 issue（47 active + 114 completed + 8 deferred）
- **Worktree 管理**：issue CLI 支持 worktree 命令
- **自定义异常体系**：src/exceptions.py，9 个业务异常类（RF-017）
- **类型规范化**：Optional[X] → X | None（Python 3.10+）（RF-016）
- **异常链修复**：B904，19 个文件添加 `from e`
- **project-memory skill**：跨 session 记忆系统
- **todo-archiver skill**：TODO → backlog 归档
- **archive-conventions skill**：一致的归档规范
- **TODO-backlog 双向同步机制**
- **CONTRIBUTING.md**
- **License 变更**：MIT → AGPL-3.0（PyMuPDF 依赖）
- **force_overwrite config**：pipeline 阶段缓存控制
- **MetricResolver**：多后端指标分配
- **自适应段落压缩**：adaptive segment compaction，节省 token
- **问题去重**：test set generation 中的问题去重
- **Review 工具增强**：AI reviewer + PDF viewer + tiered review + progress bar

### 版本验收

- Git tag: `v0.1.12`

---

## v0.1.11 (2026-04-26)

### 版本主题

链路统一

### 叙事

> 分裂是技术债的温床。统一不是妥协，是让好的东西惠及所有人。

我们有两套并行的测试集生成链路，各做各的，质量不均。现在合二为一，两种策略都受益了。

### 关键决策

- 将 Golden 独有功能分为 A/B/X 三类：A 类（所有策略受益）并入内部链路，B 类（仅 golden 需要）条件分支，X 类（抛掉不保留）
- Golden 不再直接读 data/parsed/，改为通过 MealManager.find_full_dataset_meal() 查找全量 PDF meal
- Golden 脚本退化为薄 CLI 壳，仅做参数解析

### 交付成果

- **链路统一**：Golden 生成逻辑收编入 TestSetGenerator，Golden 脚本 1242→62 行
- **adversarial 问题类型**：7 种问题类型，默认分布 0%（A1）
- **数值精度校验**：10 倍换算错误自动检测修正，所有策略受益（A2）
- **excerpt 验证**：ground_truth_excerpt 原文真实性验证，所有策略受益（A4）
- **文档去重**：内容重叠检测与补充文档排除，golden 策略专用（B1）
- **全量 meal 查找**：MealManager.find_full_dataset_meal()
- **Golden 自动生成**：resolve_test_set 中 golden 不存在时自动生成
- **Golden 150 题测试集**：LLM 辅助 + 人工审核，7 种问题类型
- **evidence-aware prompt**：quote-based 追踪 + 验证机制
- **ground_truth_excerpt**：hybrid 问题生成支持严格指标计算
- **Artifact 路径迁移**：pipeline.py 改用 ArtifactCache 动态计算（BUG-026）
- **Token 统计**：get_summary_by_variant() 按 variant 区分（BUG-027）
- **irrelevant 指标修复**：context_precision/recall 守卫、RAGAS reference fallback、expected_answer 条件回退（BUG-029/030/031）
- **LLM 报告**：全部 variant 失败时跳过生成（FEAT-042）
- **Artifact 体系完善**：Pointer 文件机制、artifact CLI、友好路径日志
- **路径清理**：删除 config.yaml 中废弃的 parser.output_dir / chunker.input_dir / chunker.output_dir

### 版本验收

- Git tag: `v0.1.11`
- [完成报告](.archive/v0.1.11-unification-era/release/v0.1.11/completion-report.md)

---

## v0.1.10 (2026-04-22)

### 版本主题

解析新纪元

### 叙事

> PDF 解析是 RAG 的源头。源头不自由，下游处处受限。

我们被锁死在一种 PDF 解析器里，现在有了抽象层、多种解析器、页面感知分块，中间产物也有了干净的家。

### 关键决策

- 引入 Parser 抽象层（BaseParser + ParserRegistry），支持多种解析器热插拔
- 采用 page-aware 分块策略，保留页码和标题元数据
- 从 data/parsed + data/chunks 迁移到 Artifact 体系，统一中间产物管理
- 统一 chunker 和 embedder 的 tokenizer（BGETokenizerEncoder）

### 交付成果

- **Multi-parser 框架**：BaseParser + ParseResult + ParsedPage + ParserRegistry
- **三个解析器**：pymupdf4llm（page_chunks）、fitz+pdfplumber（表格/标题/栏式布局）、pdfplumber（原有）
- **Page-aware 分块**：页码标记、标题元数据、跨页 overlap、context length control
- **Artifact 体系**：ArtifactCache + Pointer 文件 + artifact CLI（list/pointer/info）
- **路径迁移**：data/parsed → artifacts，pipeline 改用 ArtifactCache 动态计算
- **Tokenizer 统一**：BGETokenizerEncoder（chunker + embedder 共享）
- **Parser hash 隔离**：parser options 纳入 config hash 和 snapshot
- **Pipeline Profiling**：性能剖析系统 + OCR 对比实验
- **LazyDocumentLoader**：mtime 缓存失效 + LRU 淘汰
- **缓存安全**：修复 ArtifactCache 和 parser 的缓存污染风险
- **normalize_source**：include_parent 参数支持目录感知匹配

### 版本验收

- Git tag: `v0.1.10`

---

## v0.1.9 (2026-04-21)

### 版本主题

评测双引擎

### 叙事

> 你没法改进你量不准的东西。这一版的核心是让评测从"够用"变成"可信"。

我们只能用一种方式评测，现在有了两种，而且两种都更强了。

### 关键决策

- 集成 RAGAS 评测框架作为第二评测引擎，与 BuiltinEvaluator 并行
- 引入 Evaluator 抽象层和 MetricResolver，支持多后端指标分配
- 统一 context_precision / context_recall 的双后端聚合逻辑
- 引入 create_llm_client factory 统一 LLM 客户端创建

### 交付成果

- **RAGAS 五大指标**：answer_correctness、faithfulness、context_precision、context_recall、answer_relevancy
- **Evaluator 抽象层**：MetricResolver 多后端指标分配
- **BuiltinEvaluator 增强**：chunk/dedup/FPR/Recall@k/hallucination_rate/diversity/anomaly detection
- **双后端统一聚合**：context_precision / context_recall 从两个后端统一聚合
- **create_llm_client factory**：统一 LLM 客户端创建
- **metric namespace prefixes**：多后端评测的指标命名空间
- **基线评测链路修复**：expect_retrieval 守卫、reference fallback、source 分离
- **检索增强**：score threshold 过滤、BGE query instruction prefix
- **Generator 增强**：system prompt 可配置、source document names in prompt
- **配置提取**：硬编码 LLM 配置值提取到 config.yaml（RF-004）
- **代码质量**：ruff linter/formatter + pre-commit hooks

### 版本验收

- Git tag: `v0.1.9`

---

## v0.1.8 (2026-04-20)

### 版本主题

TestSet 独立管理系统

### 关键决策

- 将 TestSet 提升为与 Meal 对等的独立可管理实体
- 引入 metadata 元数据结构，支持审计追踪
- 设计 on_missing 三种模式（auto / clean_only / strict）
- 用户定义集支持三种 invalid_policy（immutable / trim / regenerate）
- Archive 备份机制防止数据丢失

### 交付成果

- **TestSetManager 类**：CRUD 操作、有效性判定、自动清洗、Archive 备份
- **metadata 元数据结构**：name、meal_id、generation、user_defined、invalid_policy、audit_log
- **on_missing 路由逻辑**：三种模式控制查找失败时的兜底行为
- **自动清洗流程**：机器生成集和用户定义集分别处理
- **向后兼容**：旧格式测试集 JSON 自动迁移，旧配置触发 deprecation warning
- **CLI 增强**：--generate-test-set 支持 --name 参数
- **831 个测试全部通过**：无回归

### 版本验收

- Git tag: `v0.1.8`
- [实现指南](user-guides/test-set-management.md)

---

## v0.1.7 (2026-04-19)

### 版本主题

评测系统增强

### 关键决策

- 采用文档级问题生成策略，与 chunk 参数解耦
- 引入生成质量指标（Faithfulness, Answer Relevancy）
- 改进检索指标实现，采用业界标准定义

### 交付成果

- **文档级问题生成**：基于完整 MD 文档生成真实场景问题，支持 6 种问题类型
- **生成质量指标**：Faithfulness（忠实度）、Answer Relevancy（回答相关性）
- **检索指标改进**：Hit Rate 采用业界标准定义，NDCG 支持多级相关性
- **真实性检查**：过滤学术化表述，确保问题贴近用户场景
- **向后兼容**：旧策略保留并显示 deprecation 警告

### 版本验收

- Git tag: `v0.1.7`
- [交付对照](.archive/v0.1.7-evaluation-era/release/v0.1.7/outcome.md)

---

## v0.1.6 (2026-04-18)

### 版本主题

项目卫生 + 文档系统重构

### 关键决策

- 建立四级文档目录结构（guides, reviews, archive, troubleshooting）
- 引入版本历史系统和 Backlog 系统
- 统一文档命名规范（英文文件名）

### 交付成果

- **文档系统重构**：新目录结构、版本历史、Backlog 系统、Review 系统
- **代码质量改进**：类型标注、Docstrings、代码重构
- **测试改进**：新增测试、测试修复、测试清理
- **功能增强**：动态 metric 配置、进度显示参数

### 版本验收

- Git tag: `v0.1.6`
- [交付对照](.archive/v0.1.6-hygiene-era/release/v0.1.6/outcome.md)

---

## v0.1.1~v0.1.5 (2026-04-16)

### 版本主题

MVP RAG + Baseline 评测 + 自动化实验系统

### 关键决策

- 采用固定长度分块策略（512 tokens, overlap=0）作为 baseline
- 使用 BAAI/bge-large-zh-v1.5 作为 Embedding 模型
- 使用 Qdrant 作为向量存储
- 通过 Anthropic SDK 调用 LongCat API

### 交付成果

- **Meal 数据管理系统**：数据集版本管理、采样策略、完整性验证
- **自动化评测系统**：多 Variant 对比实验、自动数据准备、实验复现
- **Token 追踪系统**：Token 消耗统计、成本估算
- **测试集生成器**：LLM 辅助问题生成、多种策略支持
- **356 个测试用例**：覆盖所有核心模块

### 版本验收

- Git tag: `v0.1.5`
- [代码审查报告](.archive/v0.1.0-v0.1.5-mvp-era/release/v0.1.5/code-review.md)
- [交付对照](.archive/v0.1.0-v0.1.5-mvp-era/release/v0.1.5/outcome.md)

---

## v0.1.0 (2026-04-15)

### 版本主题

MVP RAG 基础链路

### 关键决策

- 采用经典的 RAG 架构：PDF 解析 → 分块 → Embedding → 向量索引 → 检索 → LLM 生成
- 使用 pymupdf4llm 进行 PDF 解析
- 使用 tiktoken 进行 token 计数

### 交付成果

- **核心 RAG 链路**：6 个核心模块（parser, chunker, embedder, indexer, retriever, generator）
- **评测指标**：Hit Rate, MRR, NDCG
- **多 LLM preset 支持**：default, opus, sonnet, haiku
- **基础 CLI**：单次问答、交互式问答、索引构建

### 经验教训

- 评测指标需要统一 source 路径格式
- 测试覆盖需要尽早建立

---

## 版本规划

### v0.1.17（已发布 2026-05-10）

- ✅ LangGraph Agent 维修工系统
- ✅ Session 持久化与经验积累
- ✅ 共享单元层（Phase C 迁移完成）
- ✅ Pydantic 配置校验
- 透明版完整实验报告（FEAT-010）→ 推迟到 v0.1.18
- Baseline 标定与"花头"效果验证 → 推迟到 v0.1.18

### v0.1.18（计划中）

- 透明版完整实验报告（FEAT-010）
- Baseline 标定与"花头"效果验证
- dev → main 合并准备

### v0.2.0（计划中）

- RAGAS 深度核实，五大指标全部验收
- 完善自动化评测系统
- 标定稳定 baseline
- dev 分支并入 main
- 开源版本库发布
