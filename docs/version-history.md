# 版本演进年轮

<!-- status: active -->

> 最后更新：2026-04-28

本文档记录项目的版本迭代历程，每个版本的关键决策、交付成果和经验教训。

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
- [完成报告](reviews/v0.1.11/completion-report.md)

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
- [Spec 文档](../.trae/specs/test-set-independent-management/spec.md)
- [实现指南](guides/test-set-management.md)

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
- [交付对照](reviews/v0.1.7/outcome.md)

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
- [交付对照](reviews/v0.1.6/outcome.md)

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
- [代码审查报告](reviews/v0.1.5/code-review.md)
- [交付对照](reviews/v0.1.5/outcome.md)

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

### v0.1.14（计划中）

- 透明版完整实验报告（FEAT-010）
- "花头"效果验证与对比报告
- 指标得分上下限确认

### v0.2.0（计划中）

- RAGAS 深度核实，五大指标全部验收
- 完善自动化评测系统
- 标定稳定 baseline
- dev 分支并入 main
- 开源版本库发布
