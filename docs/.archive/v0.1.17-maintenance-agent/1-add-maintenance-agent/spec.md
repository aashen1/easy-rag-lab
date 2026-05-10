# 维修工 Agent Spec

## Why

当前 RAG 实验系统以 Meal 批量体系为核心，缺少对单个 PDF 甚至单页的精细诊断能力。用户需要一种"手术刀"式工具——当某个 PDF 解析质量差、分块不合理、检索不准时，能深入每个环节对比调优，并将经验积累下来。维修工 Agent 正是填补这一空缺的高权限系统管理员角色。

## What Changes

- 新增共享单元层 `src/core/ops/`，将现有底层函数抽象为实验系统与 Agent 共用的纯函数接口
- 新增维修工 Agent 包 `src/agent/`，基于 LangGraph StateGraph 实现非线性工作流编排
- 扩展 Meal 体系支持手动指定 PDF 列表（向后兼容）
- 扩展 PdfPlumberEnhancer 支持单页/单表格级增强
- 扩展 VectorIndexer 支持按 source 增量删除/更新
- 扩展 ArtifactCache 支持增量更新 manifest
- 适配 Anthropic 认证到 LangChain ChatAnthropic
- 新增 Streamlit 维修工页面和 CLI 入口
- 新增维修报告与对比报告生成
- 新增 Issue 系统集成工具
- 新增高权限操作安全机制（备份 + 白名单）
- 新增轻量/全量双模式
- **BREAKING**: 无破坏性变更，所有对现有模块的修改均为新增方法或向后兼容的参数扩展

## Impact

- Affected specs: 无既有 spec 受影响（全新功能）
- Affected code:
  - `src/parsers/pdfplumber_enhancer.py` — 新增 `enhance_page()` 和 `enhance_table()` 方法
  - `src/parsers/registry.py` — 新增 `get_enhancer()` 方法
  - `src/meal/manager.py` — 扩展 `create_meal()` 参数（pdf_files, source_dir, file_pattern, tags, description）
  - `src/meal/models.py` — 新增 `creation_mode` 字段
  - `src/meal/cache.py` — 新增 `update_manifest_entry()` 方法
  - `src/indexer.py` — 新增 `delete_by_source()` 和 `upsert_chunks()` 方法
  - `src/parser.py` — `parse_all_pdfs_unified()` 内部重构为调用共享单元
  - `src/llm_client.py` — 新增 LangChain Anthropic 客户端工厂
  - `src/agent/config.py` — 新增 Agent 配置加载模块
  - `config.yaml` — 新增 `agent` 配置段
  - `src/app.py` — 新增维修工 Tab
  - `main.py` — 新增 `agent` 子命令

---

## 最小处理单位定义

| 阶段 | 最小处理单位 | 共享单元函数 | 说明 |
|------|------------|------------|------|
| S1 解析 | 单个 PDF 文件 | `parse_pdf()` | 天然支持 |
| S1.5 表格增强 | **单页** / **单表格** | `enhance_page()` / `enhance_table()` | 新增能力 |
| S2 分块 | 单个解析结果 | `chunk_parsed()` | 天然支持 |
| S3 嵌入 | 单个 chunk 列表 | `embed_chunks()` | 天然支持 |
| S4 索引 | 单个 source 的 chunks | `index_chunks()` / `delete_source_and_reindex()` | 新增增量能力 |
| S5 检索 | 单个查询 | `query_rag()` | 天然支持 |
| S6 生成 | 单个查询+上下文 | `query_rag()` | 天然支持 |
| S7 评测 | 单个样本 | `evaluate_single()` | 天然支持 |

> **索引约定**：所有共享单元函数中，`page_number` 和 `table_index` 统一采用 **1-indexed**（从 1 开始计数），与用户直觉一致。例如 `page_number=5` 表示第 5 页，`table_index=3` 表示该页第 3 个表格。

---

## ADDED Requirements

### Requirement: 共享单元层 (Shared Ops Layer)

系统 SHALL 提供 `src/core/ops/` 包，包含以下纯函数接口，供实验系统和 Agent 共同调用：

- `parse_pdf(pdf_path, parser_name, enhancer_name, parser_options, enhancer_options)` → ParseResult
- `enhance_page(pdf_path, page_number, existing_text, enhancer_name, enhancer_options)` → str
- `enhance_table(pdf_path, page_number, table_index, existing_text, enhancer_name, enhancer_options)` → str
- `chunk_parsed(parse_result, strategy, chunk_size, overlap, encoding_name, model_name, cross_page_overlap, similarity_threshold, breakpoint_percentile, embedder, parent_chunk_config)` → list[dict]
- `embed_chunks(chunks, embedder, batch_size)` → list[vector]
- `index_chunks(chunks, embedder, collection_name, batch_size, source_filter)` → int
- `delete_source_and_reindex(source, new_chunks, embedder, collection_name)` → int
- `query_rag(question, pipeline)` → dict
- `evaluate_single(question, answer, contexts, expected_answer, expected_sources, metrics, config)` → dict[str, float]

共享单元 SHALL 遵循渐进式迁移路径：
1. **Phase A**: 共享单元作为薄包装层，内部调用现有底层函数，不改变现有行为
2. **Phase B**: Agent @tool 直接包装共享单元
3. **Phase C**: 实验系统逐步改为调用共享单元（替换直接调用底层函数）
4. **Phase D**: 共享单元稳定后，底层函数可重构为共享单元的内部实现（可选）

#### Scenario: 共享单元调用解析
- **WHEN** 任何调用方调用 `parse_pdf(pdf_path="test.pdf", parser_name="pymupdf4llm")`
- **THEN** 系统通过 ParserRegistry 获取对应解析器，执行解析，返回 ParseResult
- **AND** 结果与直接调用 `ParserRegistry.get_composite().parse()` 一致

#### Scenario: 共享单元调用分块
- **WHEN** 任何调用方调用 `chunk_parsed(parse_result, strategy="page_aware", chunk_size=512)`
- **THEN** 系统根据 strategy 分发到对应分块函数，返回 chunks 列表
- **AND** 结果与直接调用底层分块函数一致

#### Scenario: 父子块热插拔接口预留
- **WHEN** 调用 `chunk_parsed(parse_result, parent_chunk_config={"enabled": True, "parent_size": 2048, "parent_overlap": 200})`
- **THEN** 系统在分块时同时生成父块和子块，子块携带 `parent_id` 元数据
- **AND** 当 `parent_chunk_config` 为 None 时，行为与普通分块完全一致（向后兼容）

### Requirement: 维修工 Agent LangGraph 工作流

系统 SHALL 基于 LangGraph StateGraph 实现维修工 Agent，具备以下能力：

- 非线性工作流：支持通过条件边在解析/分块/嵌入/索引/检索/生成/评测阶段间跳转
- LLM 自主决策：Agent 节点通过 LLM + @tool 绑定自主选择工具和参数
- 用户锁定：用户可通过 UI 下拉菜单锁定工具链，覆盖 LLM 决策
- 人工干预：支持 `interrupt()` 在任意节点暂停等待用户反馈
- 回退跳转：支持 `Command(goto=...)` 回退到任意阶段重做
- 轻量/全量双模式：轻量模式处理 1-2 个 PDF（默认），全量模式同现有实验系统

#### Scenario: Agent 自主选择解析器
- **WHEN** 用户说"帮我解析这份年报"
- **THEN** Agent 根据 PDF 特征和经验记忆，选择合适的解析器组合
- **AND** 执行解析后返回结果摘要

#### Scenario: 用户回退到解析阶段
- **WHEN** 用户在分块阶段发现解析质量差，说"回到解析阶段换 pdfplumber 补强"
- **THEN** Agent 通过 Command(goto="parse") 跳转回解析节点
- **AND** 使用 pdfplumber 增强器重新解析

#### Scenario: 人工干预暂停
- **WHEN** 解析节点执行完毕
- **THEN** 系统通过 interrupt() 暂停，展示解析结果摘要给用户
- **AND** 等待用户 approve / reject / 指定新参数后继续

#### Scenario: 轻量模式
- **WHEN** 用户启动维修工时未指定全量模式
- **THEN** Agent 以轻量模式运行，仅处理用户指定的 1-2 个 PDF
- **AND** 不触发 Meal 批量体系，不依赖全局 manifest

#### Scenario: 全量模式
- **WHEN** 用户启动维修工时指定全量模式（`--full` 或 UI 切换）
- **THEN** Agent 可调用 Meal 批量体系，处理完整数据集
- **AND** 行为与现有实验系统一致，但保留 Agent 的精细控制能力

### Requirement: 维修日志与经验记忆

系统 SHALL 提供跨 session 的维修日志和经验积累能力：

- 基于 LangGraph Checkpointer 实现状态持久化（InMemorySaver 开发，SqliteSaver 生产）
- 基于 LangGraph Memory Store 实现跨 session 经验积累
- 维修日志记录每次操作的输入/输出/参数/时间戳
- 经验记忆按 namespace 组织，Agent 可检索历史经验辅助决策

#### Scenario: 经验积累
- **WHEN** Agent 发现某类 PDF 用 fitz+pdfplumber 组合效果最好
- **THEN** 将此经验存入 Memory Store
- **AND** 下次处理同类 PDF 时检索到该经验并优先推荐

### Requirement: 高权限操作安全机制

维修工权限仅次于用户，可写回 Meal/Artifact。系统 SHALL 通过以下机制防止误操作：

- **自动备份**：所有写操作（修改 Meal、更新 Artifact、删除向量）执行前，SHALL 自动将受影响数据备份到 `.trashbin/` 目录
- **白名单机制**：系统 SHALL 维护一个危险操作白名单，禁止以下操作：
  - 删除整个 Qdrant collection（DROP/DELETE 全量）
  - 删除整个 Meal（仅允许通过 Issue 系统标记为废弃）
  - 批量覆盖 Artifact manifest
- **操作确认**：所有写操作 SHALL 通过 interrupt() 等待用户确认后才执行
- **操作日志**：所有写操作 SHALL 记录到维修日志，包含操作类型、目标、时间戳、操作前快照路径

#### Scenario: 写操作自动备份
- **WHEN** 维修工执行 `delete_source_and_reindex()` 更新某个 PDF 的向量
- **THEN** 系统先将被删除的旧向量元数据备份到 `.trashbin/`
- **AND** 备份文件名包含时间戳和 source 标识
- **AND** 然后才执行删除和重新索引

#### Scenario: 危险操作拦截
- **WHEN** LLM 决策调用 `delete_collection()` 删除整个向量库
- **THEN** 白名单机制拦截该操作，返回错误信息
- **AND** 记录拦截事件到维修日志

### Requirement: Meal 手动模式

系统 SHALL 扩展 MealManager.create_meal() 支持手动指定 PDF 列表：

- 新增 `pdf_files` 参数，直接指定 PDF 文件列表
- 新增 `source_dir` 参数，指定搜索目录
- 新增 `file_pattern` 参数，文件名模式匹配（如 "*年报*"）
- 新增 `tags` 参数，标签（如 ["煤炭", "年报"]）
- 新增 `description` 参数，描述
- MealConfig 新增 `creation_mode` 字段（"random" | "manual"）
- 向后兼容：只传 sample_ratio/sample_count 时行为不变

#### Scenario: 手动创建 Meal
- **WHEN** 调用 `create_meal(name="test", pdf_files=["a.pdf", "b.pdf"])`
- **THEN** 创建包含指定 PDF 的 Meal，creation_mode 为 "manual"
- **AND** 不触发随机抽样逻辑

#### Scenario: 按目录和模式创建 Meal
- **WHEN** 调用 `create_meal(name="coal_reports", source_dir="data/raw/", file_pattern="*煤炭*")`
- **THEN** 搜索 source_dir 下匹配 file_pattern 的 PDF 文件
- **AND** 创建包含匹配文件的 Meal，creation_mode 为 "manual"

#### Scenario: 向后兼容
- **WHEN** 调用 `create_meal(name="test", sample_ratio=0.5)`
- **THEN** 行为与修改前完全一致，creation_mode 为 "random"

### Requirement: PdfPlumberEnhancer 单页/单表格增强

系统 SHALL 在 PdfPlumberEnhancer 中新增以下方法：

- `enhance_page(pdf_path, page_number, existing_text)` — 对指定页面执行表格增强
- `enhance_table(pdf_path, page_number, table_index, existing_text)` — 对指定页面的指定表格执行增强

两者均不影响现有 `enhance()` 全文档增强方法。

#### Scenario: 单页增强
- **WHEN** 调用 `enhance_page(pdf_path="test.pdf", page_number=5, existing_text="...")`
- **THEN** 仅对第 5 页执行表格提取和合并
- **AND** 返回增强后的 Markdown 文本

#### Scenario: 单表格增强
- **WHEN** 调用 `enhance_table(pdf_path="test.pdf", page_number=5, table_index=3, existing_text="...")`
- **THEN** 仅对第 5 页的第 3 个表格（1-indexed）执行提取和合并
- **AND** 返回增强后的 Markdown 文本，仅替换目标表格部分

### Requirement: VectorIndexer 增量操作

系统 SHALL 在 VectorIndexer 中新增以下方法：

- `delete_by_source(collection_name, source)` — 按 source 元数据过滤删除向量
- `upsert_chunks(collection_name, chunks, embedder)` — 增量插入/更新 chunks

#### Scenario: 增量更新
- **WHEN** 维修工重新分块某个 PDF 后需要更新索引
- **THEN** 先 delete_by_source 删除旧向量，再 upsert_chunks 插入新向量
- **AND** 其他 source 的向量不受影响

### Requirement: ArtifactCache 增量更新

系统 SHALL 在 ArtifactCache 中新增 `update_manifest_entry()` 方法：

- 支持更新 manifest 中单个条目，而非覆盖写入整个 manifest
- 维修工写回 Artifact 时使用此方法，避免影响其他条目
- 保证原子性：更新失败时 manifest 保持原状

#### Scenario: 增量更新 manifest
- **WHEN** 维修工重新解析某个 PDF 后需要更新对应的 Artifact 条目
- **THEN** 调用 `update_manifest_entry(key, new_value)` 仅更新目标条目
- **AND** manifest 中其他条目不受影响

#### Scenario: 更新失败回滚
- **WHEN** `update_manifest_entry()` 写入过程中发生异常
- **THEN** manifest 文件保持更新前的状态
- **AND** 异常被记录到日志

### Requirement: Issue 系统集成

系统 SHALL 在维修工 Agent 中提供 Issue 系统集成工具：

- `create_issue(title, description, severity, tags)` — 创建 Issue，记录发现的问题
- `list_issues(status, tags)` — 列出 Issue，查看已知问题
- `close_issue(issue_id, resolution)` — 关闭 Issue，记录解决方案

维修工在诊断过程中发现系统性问题时，SHALL 主动建议创建 Issue。

#### Scenario: 诊断发现系统性问题
- **WHEN** 维修工发现某类 PDF 的解析结果普遍存在表格散乱问题
- **THEN** Agent 建议用户创建 Issue 记录此问题
- **AND** 用户确认后调用 `create_issue()` 创建 Issue

#### Scenario: 查看已知问题
- **WHEN** 维修工开始处理一个 PDF
- **THEN** Agent 自动检索相关 Issue，提示用户已知问题
- **AND** 如果有已关闭的 Issue，展示其解决方案供参考

### Requirement: Anthropic 认证适配

系统 SHALL 提供 LangChain ChatAnthropic 客户端工厂，适配项目的非标准 Anthropic 认证：

- 复用项目已有的 API key 和 base_url 配置
- 支持 `Authorization: Bearer` header（非标准 x-api-key）
- 与现有 `create_anthropic_client()` 共享配置来源

#### Scenario: 创建 LangChain LLM 客户端
- **WHEN** 调用 `create_langchain_anthropic_client(config)`
- **THEN** 返回配置好 base_url 和 auth headers 的 ChatAnthropic 实例
- **AND** 可以正常调用 Anthropic API

### Requirement: 维修报告与对比报告生成

系统 SHALL 提供两种报告生成能力：

- **维修报告**：汇总一次维修会话的所有操作、结果、发现和结论，持久化为 Markdown 文件
- **对比报告**：对同一输入用不同工具/参数处理的结果进行结构化对比，包含差异摘要和推荐

#### Scenario: 生成维修报告
- **WHEN** 维修会话结束（用户说"生成报告"或 Agent 判断工作完成）
- **THEN** 系统汇总本次会话的所有操作记录、参数变更、结果对比
- **AND** 生成 Markdown 格式的维修报告，保存到 `data/maintenance_reports/` 目录

#### Scenario: 生成对比报告
- **WHEN** 用户对同一 PDF 使用了多种解析器或分块策略
- **THEN** 系统生成结构化对比报告，包含各方案的指标对比（字符数、表格数、分块数等）
- **AND** 标注推荐方案及理由

### Requirement: Streamlit 维修工页面

系统 SHALL 在 Streamlit 应用中新增维修工 Tab：

- 展示当前维修会话状态（阶段、已有结果）
- 提供下拉菜单锁定工具链
- 展示 interrupt 暂停时的结果和操作选项
- 展示维修日志和对比报告
- 支持轻量/全量模式切换

### Requirement: CLI 入口

系统 SHALL 提供维修工 CLI 入口（`main.py agent` 子命令）：

- 支持文本指令交互（调试用）
- 支持 `--pdf` 指定目标 PDF
- 支持 `--session-id` 恢复历史会话
- 支持 `--full` 启用全量模式
- 支持指令代替按钮（如 `:parse pymupdf4llm`、`:back chunk`、`:compare`）

---

## MODIFIED Requirements

### Requirement: ParserRegistry 增强

ParserRegistry SHALL 新增 `get_enhancer(enhancer_name, enhancer_options)` 方法，返回独立的 TableEnhancer 实例，供 `enhance_page()` 和 `enhance_table()` 共享单元使用。

### Requirement: parse_all_pdfs_unified 内部重构

`parse_all_pdfs_unified()` 内部 SHALL 改为调用 `parse_pdf()` 共享单元逐文件处理，而非直接管理 parser 实例。外部接口不变。此重构遵循共享单元迁移路径 Phase C。

---

## REMOVED Requirements

无移除的需求。

---

## 风险评估与回归保护

### 风险矩阵

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| Agent 工具调用异常导致数据损坏 | 低 | 高 | 写操作前自动备份到 `.trashbin/`；白名单机制限制危险操作；禁止 DROP/DELETE 全量操作 |
| 与 Meal 体系的状态不一致 | 中 | 中 | 维修工写回 Meal 时做一致性校验；Meal 新增 `creation_mode` 字段区分来源 |
| LangGraph 版本 API 不稳定 | 中 | 中 | 锁定 langgraph 版本；封装 LangGraph 调用到 `src/agent/graph.py`，隔离变化 |
| 共享单元重构引入回归 | 低 | 高 | 共享单元先作为薄包装层，内部调用现有底层函数；渐进式迁移；每步加测试 |
| LLM 自主决策的工具选择不可控 | 中 | 中 | 系统提示词约束 + 用户锁定机制 + interrupt 人工审核 |
| Anthropic 认证适配问题 | 低 | 中 | ChatAnthropic 支持自定义 headers，适配成本低 |
| LangGraph 依赖链过重 | 低 | 低 | 沙盒环境不担心；仅需 `langgraph` + `langchain-core` + `langchain-anthropic` |

### 回归保护措施

1. **薄包装层**：共享单元先作为薄包装层，内部调用现有底层函数，不改变现有行为
2. **渐进式迁移**：实验系统迁移到共享单元是渐进式的，每步迁移都有测试覆盖
3. **物理隔离**：Agent 代码在 `src/agent/` 独立包中，与现有代码物理隔离
4. **仅新增方法**：对现有模块的修改仅限新增方法和向后兼容的参数扩展
5. **独立测试标记**：CI 中 Agent 测试标记为 `@pytest.mark.agent`，可独立运行

---

## 技术难度评估

| 模块 | 难度 | 说明 |
|------|------|------|
| 共享单元层 (`src/core/ops/`) | ★★☆ | 薄包装现有函数，接口设计是关键 |
| LangGraph StateGraph 定义 | ★★☆ | 学习曲线中等，但概念清晰 |
| @tool 定义（包装共享单元） | ★☆☆ | 直接 `@tool` 装饰器包装 |
| Agent 节点函数 | ★★☆ | 需要处理 interrupt 和状态更新 |
| LLM 决策节点 + 提示词 | ★★★ | 核心难点：提示词需要精心设计 |
| 条件边路由 | ★★☆ | 逻辑清晰，但需要处理多种跳转场景 |
| Checkpointer 持久化 | ★☆☆ | 开箱即用，InMemorySaver 开发，SqliteSaver 生产 |
| Memory Store 经验积累 | ★★☆ | 需要设计 namespace 和记忆结构 |
| Meal 手动模式扩展 | ★★☆ | 向后兼容扩展，需要测试覆盖 |
| PdfPlumberEnhancer 单页/单表格增强 | ★★☆ | 内部已有页码索引，只需过滤 |
| ArtifactCache 增量更新 | ★★★ | 需要处理并发安全和原子性 |
| VectorIndexer 增量操作 | ★★★ | Qdrant filter-based delete + upsert |
| 高权限安全机制 | ★★☆ | 备份到 .trashbin + 白名单，逻辑清晰但需全面覆盖 |
| 轻量/全量双模式 | ★★☆ | 状态管理差异，需在 State 中区分 |
| Streamlit 交互页面 | ★★☆ | 参考现有 app_pages |
| CLI 交互模式 | ★★☆ | 用指令代替按钮，参考 interactive_qa.py |
| Anthropic 认证适配 | ★☆☆ | ChatAnthropic 支持自定义 headers |
| Issue 系统集成 | ★☆☆ | 包装现有 issue CLI |
| 报告生成 | ★★☆ | 模板化 Markdown 生成 |

---

## 开放问题

1. **LLM 模型选择**：维修工的 LLM 用哪个 preset（default/opus/sonnet/haiku）？建议 sonnet 平衡性能和成本
2. **Memory Store 的 namespace 设计**：按用户？按 PDF 类型？按问题类型？
3. **共享单元的粒度边界**：哪些操作应该抽象为共享单元，哪些留在调用侧？
4. **Streamlit 页面的交互细节**：下拉菜单的具体选项、interrupt 的 UI 表现形式
5. **实验系统迁移到共享单元的优先级**：哪些模块先迁移？
