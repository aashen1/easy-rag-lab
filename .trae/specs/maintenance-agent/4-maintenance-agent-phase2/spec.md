# 维修工 Agent Phase 2 Spec

## Why

Phase 0 + Phase 1 已验收通过，维修工 Agent 具备了基本的 LangGraph ReAct 骨架（agent → approval → tools → agent 循环）和 11 个 @tool。但存在 4 项偏差需要修正，且 Phase 2 的全链路工具、回退跳转、人工干预增强、Memory Store 经验积累、Issue 系统集成尚未实现。本 Spec 覆盖偏差修正 + Phase 2 全部功能。

## What Changes

- **偏差 1（高优先级）**：`delete_source` 工具执行前缺少数据备份。新增 `VectorIndexer.scroll_by_source()` 方法，在删除前导出将被删除的 points 元数据到 `.trashbin/`
- **偏差 2（低优先级）**：多处硬编码配置值。新增 `config.yaml` 的 `agent` 配置段 + `src/agent/config.py` 配置加载模块
- **偏差 3（低优先级）**：`src/core/ops/parse.py` 三个 IO 函数缺少 try/except。补全异常处理
- **偏差 4（低优先级）**：每次 `agent_node` 调用重建 LLM 客户端。使用模块级缓存复用
- **Task 2.2**：新增 9 个 @tool（embed_chunks_tool, index_chunks_tool, delete_and_reindex_tool, create_curated_meal, list_pdfs, create_issue, list_issues, close_issue）
- **Task 2.3**：回退跳转——在 `MaintenanceState` 新增 `stage_history` 字段，tool_node 执行后更新，注入系统提示词让 LLM 感知历史
- **Task 2.4**：人工干预增强——`MaintenanceState` 新增 `auto_review` 字段，CLI 支持 `:review on/off` 切换
- **Task 2.5**：Memory Store 经验积累——新增 `src/agent/memory/experience_store.py`，agent_node 检索经验注入提示词，tool_node 自动保存经验
- **Task 2.6**：Issue 系统集成——3 个 @tool 包装 `pixi run issue` CLI，系统提示词增加 Issue 规则
- **Task 2.7**：StateGraph 更新——注册新工具到 `_get_tools()`，`HIGH_RISK_TOOLS` 新增 `delete_and_reindex_tool`，系统提示词更新
- **BREAKING**: `MaintenanceState` 新增 `stage_history` 和 `auto_review` 字段，现有测试需适配

## Impact

- Affected specs: `add-maintenance-agent` Phase 1 spec（Phase 2 是其增量）
- Affected code:
  - `src/indexer.py` — 新增 `scroll_by_source()` 方法
  - `src/agent/tools.py` — 新增 9 个 @tool，`delete_source` 增加备份逻辑，`HIGH_RISK_TOOLS` 更新
  - `src/agent/state.py` — 新增 `stage_history`, `auto_review` 字段
  - `src/agent/graph.py` — `_get_tools()` 注册新工具，`agent_node` 缓存 LLM + 注入经验，`tool_node` 更新 stage_history + 保存经验，`compile_agent()` 接受 `store` 参数
  - `src/agent/prompt.py` — 注入 stage_history + 新工具说明 + Issue 规则 + 经验提示
  - `src/agent/cli.py` — 支持 `:review on/off`，创建 InMemoryStore 并传入
  - `src/agent/config.py` — 新增配置加载模块
  - `src/core/ops/parse.py` — 三个函数加 try/except
  - `config.yaml` — 新增 `agent` 配置段
  - `src/agent/memory/experience_store.py` — 新增经验存储模块
  - `tests/test_agent.py` — 新增和更新测试

---

## ADDED Requirements

### Requirement: VectorIndexer.scroll_by_source() 方法

系统 SHALL 在 `VectorIndexer` 中新增 `scroll_by_source(source, with_vectors=False)` 方法：

- 使用 Qdrant `client.scroll()` 按 source filter 检索 points
- `with_vectors=False` 时仅返回 payload（不含向量数据），用于备份
- 返回 `list[dict]`，每个 dict 包含 point 的 `id` 和 `payload`
- 当无匹配 points 时返回空列表

#### Scenario: 按 source 检索 points 元数据
- **WHEN** 调用 `scroll_by_source(source="年报.pdf")`
- **THEN** 返回所有 `metadata.source` 匹配 `"年报.pdf"` 的 points 的 id 和 payload
- **AND** 不包含向量数据

#### Scenario: 无匹配 points
- **WHEN** 调用 `scroll_by_source(source="不存在.pdf")`
- **THEN** 返回空列表 `[]`

### Requirement: delete_source 工具备份机制

`delete_source` 工具 SHALL 在执行删除前自动备份将被删除的 points 元数据：

- 调用 `scroll_by_source(source)` 获取将被删除的 points 元数据
- 序列化为 JSON 保存到 `.trashbin/` 目录
- 备份文件名格式：`source_backup_{source_hash}_{timestamp}.json`
- 备份成功后才执行 `delete_by_source()`
- 备份失败时记录警告日志但仍继续执行删除（不阻塞操作）

#### Scenario: 删除前自动备份
- **WHEN** 执行 `delete_source(meal_name="test", source="年报.pdf")`
- **THEN** 系统先调用 `scroll_by_source` 获取元数据
- **AND** 将元数据保存到 `.trashbin/source_backup_{hash}_{timestamp}.json`
- **AND** 然后执行 `delete_by_source()`

#### Scenario: 备份失败不阻塞删除
- **WHEN** 备份过程因磁盘空间不足等原因失败
- **THEN** 记录 warning 日志
- **AND** 仍然执行删除操作

### Requirement: Agent 配置集中化

系统 SHALL 在 `config.yaml` 新增 `agent` 配置段，并在 `src/agent/config.py` 提供配置加载函数：

- `config.yaml` 新增 `agent.defaults` 子段，包含：
  - `parser_name`（默认 `"pymupdf4llm"`）
  - `enhancer_name`（默认 `"pdfplumber"`）
  - `chunk_size`（默认 `512`）
  - `chunk_overlap`（默认 `0`）
  - `collection_name`（默认 `"financial_reports"`）
  - `thread_id`（默认 `"maintenance-session"`）
- `src/agent/config.py` 提供 `get_agent_config()` 函数，读取 `agent` 配置段
- 各模块（tools.py, graph.py, cli.py）从配置读取默认值，替换硬编码

#### Scenario: 从配置读取默认值
- **WHEN** `parse_pdf_tool` 未指定 `parser_name` 参数
- **THEN** 使用 `config.yaml` 中 `agent.defaults.parser_name` 的值
- **AND** 如果配置中未设置，回退到硬编码默认值 `"pymupdf4llm"`

### Requirement: parse.py 共享单元异常处理

`src/core/ops/parse.py` 中的 `parse_pdf()`, `enhance_page()`, `enhance_table()` 三个函数 SHALL 添加 try/except：

- 捕获异常后使用 `loguru.logger` 记录错误日志
- 然后 re-raise 异常（不吞没异常）
- 日志包含函数名和原始异常信息

#### Scenario: parse_pdf 异常处理
- **WHEN** `parse_pdf()` 内部调用 `parser.parse()` 抛出异常
- **THEN** 记录 `logger.error(f"parse_pdf failed: {e}")`
- **AND** re-raise 原始异常

### Requirement: LLM 客户端缓存

`_get_llm()` 和 `_get_tools()` SHALL 使用模块级缓存，避免每次 `agent_node` 调用时重建：

- 使用 `functools.lru_cache` 或模块级变量缓存 LLM 客户端和工具列表
- 首次调用时创建，后续调用复用
- 保证线程安全（LangGraph 单线程执行，无需加锁）

#### Scenario: LLM 客户端复用
- **WHEN** `agent_node` 第二次被调用
- **THEN** `_get_llm()` 返回缓存的 LLM 客户端实例
- **AND** 不重新创建 ChatAnthropic 实例

### Requirement: 全链路 @tool

系统 SHALL 新增以下 @tool：

| 工具名 | 类型 | 包装的共享单元/功能 | 说明 |
|--------|------|-------------------|------|
| `embed_chunks_tool` | 安全 | `embed_chunks()` | 嵌入 chunks 列表，返回向量维度和数量 |
| `index_chunks_tool` | 安全 | `index_chunks()` | 索引 chunks 到向量库，返回索引数量 |
| `delete_and_reindex_tool` | 高风险 | `delete_source_and_reindex()` | 按 source 删除旧向量并重新索引 |
| `create_curated_meal` | 安全 | `MealManager.create_meal_manual()` | 手动创建 Meal |
| `list_pdfs` | 安全 | 直接 glob `data/raw/` | 列出可用 PDF 文件 |

所有新工具遵循现有模式：try/except + loguru + JSON 返回。

#### Scenario: embed_chunks_tool 嵌入 chunks
- **WHEN** 调用 `embed_chunks_tool(chunks=[...], collection_name="m_test")`
- **THEN** 返回 JSON 包含 `embedding_dim` 和 `chunk_count`

#### Scenario: index_chunks_tool 索引 chunks
- **WHEN** 调用 `index_chunks_tool(chunks=[...], collection_name="m_test")`
- **THEN** 返回 JSON 包含 `indexed_count`

#### Scenario: delete_and_reindex_tool 高风险操作
- **WHEN** 调用 `delete_and_reindex_tool(source="年报.pdf", new_chunks=[...], collection_name="m_test")`
- **THEN** 先删除旧向量，再索引新 chunks
- **AND** 该工具在 `HIGH_RISK_TOOLS` 集合中，需用户审批

#### Scenario: create_curated_meal 手动创建 Meal
- **WHEN** 调用 `create_curated_meal(name="test", pdf_files=["a.pdf", "b.pdf"])`
- **THEN** 创建包含指定 PDF 的 Meal，返回 Meal 详情

#### Scenario: list_pdfs 列出可用 PDF
- **WHEN** 调用 `list_pdfs()`
- **THEN** 返回 `data/raw/` 目录下所有 PDF 文件列表

### Requirement: Issue 系统 @tool

系统 SHALL 新增 3 个 Issue @tool，包装 `pixi run issue` CLI：

- `create_issue(title, issue_type, priority, labels)` → `pixi run issue create -t {type} -T "{title}" -p {priority} -l {labels}`
- `list_issues(status, issue_type)` → `pixi run issue list --status {status} --type {type} --all`
- `close_issue(issue_id, resolution)` → `pixi run issue done {issue_id}`

使用 `subprocess.run(["pixi", "run", "issue", ...])` 包装，捕获 stdout/stderr，返回 JSON 结果。

#### Scenario: create_issue 创建 Issue
- **WHEN** 调用 `create_issue(title="表格解析异常", issue_type="bug", priority="high")`
- **THEN** 执行 `pixi run issue create -t bug -T "表格解析异常" -p high`
- **AND** 返回创建结果（包含 issue_id）

#### Scenario: list_issues 列出 Issue
- **WHEN** 调用 `list_issues(status="todo")`
- **THEN** 执行 `pixi run issue list --status todo --all`
- **AND** 返回 Issue 列表

#### Scenario: close_issue 关闭 Issue
- **WHEN** 调用 `close_issue(issue_id="BUG-20260504-001-wt1")`
- **THEN** 执行 `pixi run issue done BUG-20260504-001-wt1`
- **AND** 返回关闭结果

### Requirement: stage_history 回退感知

系统 SHALL 在 `MaintenanceState` 新增 `stage_history: list[str]` 字段：

- `tool_node` 执行完每个工具后，将工具名追加到 `stage_history`
- `agent_node` 将 `stage_history` 注入系统提示词，让 LLM 知道已执行了哪些步骤
- 系统提示词增加"回退"指令说明，告知 LLM 可以重新选择之前的工具
- 不采用 `Command(goto=...)` 模式，因为 ReAct 模式下 agent 每次都重新决策

#### Scenario: stage_history 记录工具执行历史
- **WHEN** 用户先调用 `parse_pdf_tool`，再调用 `chunk_parsed_tool`
- **THEN** `stage_history` 为 `["parse_pdf_tool", "chunk_parsed_tool"]`
- **AND** 系统提示词中包含"已执行步骤：parse_pdf_tool, chunk_parsed_tool"

#### Scenario: LLM 感知历史后重新选择工具
- **WHEN** 用户说"回到解析阶段换 pdfplumber"
- **THEN** LLM 根据 `stage_history` 知道已做过解析，重新选择 `parse_pdf_tool` 并指定 `enhancer_name="pdfplumber"`

### Requirement: auto_review 人工干预增强

系统 SHALL 在 `MaintenanceState` 新增 `auto_review: bool` 字段（默认 False）：

- 当 `auto_review=True` 时，`tool_node` 执行完解析/分块工具后自动 `interrupt()` 展示结果摘要
- 用户可通过 CLI 指令 `:review on` / `:review off` 切换
- 不修改现有 `approval_node` 逻辑
- auto_review 默认关闭，避免频繁 interrupt 打断 ReAct 工作流

#### Scenario: auto_review 开启后自动暂停
- **WHEN** `auto_review=True` 且 `tool_node` 执行完 `parse_pdf_tool`
- **THEN** 自动 `interrupt()` 展示解析结果摘要
- **AND** 等待用户确认后继续

#### Scenario: CLI 切换 auto_review
- **WHEN** 用户输入 `:review on`
- **THEN** `auto_review` 设为 True
- **AND** 后续工具执行后自动暂停

### Requirement: Memory Store 经验积累

系统 SHALL 使用 LangGraph 的 `InMemoryStore` 实现跨会话经验积累：

- 新增 `src/agent/memory/experience_store.py`，封装 InMemoryStore 的存取逻辑：
  - `save_experience(namespace, experience)` — 保存经验
  - `search_experiences(namespace, query)` — 检索相关经验
  - `get_all_experiences(namespace)` — 获取全部经验
- namespace 设计：`(user_id, "maintenance_experience", pdf_type)`
- 经验结构包含：`pdf_type`, `best_parser`, `best_chunk_strategy`, `best_chunk_size`, `reason`, `timestamp`
- `compile_agent()` 接受 `store` 参数
- `agent_node` 从 store 检索经验注入系统提示词
- `tool_node` 当发现好的配置组合时，自动保存经验
- `cli.py` 创建 InMemoryStore 并传给 compile_agent

#### Scenario: 经验保存
- **WHEN** 维修工发现某类 PDF 用 `pymupdf4llm+pdfplumber` 组合效果最好
- **THEN** 将经验存入 Memory Store，namespace 为 `("default", "maintenance_experience", "annual_report")`
- **AND** 经验包含 `best_parser`, `best_chunk_strategy`, `reason` 等字段

#### Scenario: 经验检索
- **WHEN** 维修工开始处理一个年报类 PDF
- **THEN** 从 Memory Store 检索 namespace `("default", "maintenance_experience", "annual_report")` 下的经验
- **AND** 将经验注入系统提示词，推荐最佳配置

### Requirement: 系统提示词增强

系统提示词 SHALL 增加以下内容：

- 已执行步骤（stage_history）注入
- 新增工具说明（embed, index, delete_and_reindex, meal, pdf, issue）
- Issue 规则：诊断发现系统性问题时主动建议创建 Issue
- 经验提示：如果有历史经验，注入推荐配置
- 回退指令说明：告知 LLM 可以重新选择之前的工具

#### Scenario: 提示词包含 stage_history
- **WHEN** `stage_history` 为 `["parse_pdf_tool", "chunk_parsed_tool"]`
- **THEN** 系统提示词中包含"已执行步骤：1. parse_pdf_tool, 2. chunk_parsed_tool"

#### Scenario: 提示词包含经验推荐
- **WHEN** Memory Store 中有年报类 PDF 的经验
- **THEN** 系统提示词中包含"历史经验推荐：年报类 PDF 建议使用 pymupdf4llm+pdfplumber"

---

## MODIFIED Requirements

### Requirement: MaintenanceState 字段扩展

`MaintenanceState` SHALL 新增以下字段：

- `stage_history: list[str]` — 记录已执行的工具名，默认 `[]`
- `auto_review: bool` — 是否自动暂停审查，默认 `False`

现有字段不变。现有测试需适配新字段。

### Requirement: HIGH_RISK_TOOLS 集合更新

`HIGH_RISK_TOOLS` 集合 SHALL 新增 `delete_and_reindex_tool`：

- 原有：`{"rebuild_index", "delete_source", "update_meal"}`
- 新增后：`{"rebuild_index", "delete_source", "update_meal", "delete_and_reindex_tool"}`

### Requirement: _get_tools() 注册新工具

`_get_tools()` SHALL 返回包含所有新工具的列表：

- 原有 11 个工具 + 新增 9 个工具 = 共 20 个工具

### Requirement: compile_agent() 接受 store 参数

`compile_agent(checkpointer=None, store=None)` SHALL 接受可选的 `store` 参数：

- 当 `store` 不为 None 时，传递给 `graph.compile(store=store)`
- 向后兼容：不传 `store` 时行为不变

---

## REMOVED Requirements

无移除的需求。
