# 维修工 Agent Session 管理与经验持久化 Spec

## Why

当前维修工 Agent 存在两个核心缺陷：(1) 对话无法持久化，浏览器刷新后丢失，无法切换/复制/编辑历史对话；(2) 经验存储使用 InMemoryStore + JSON 落盘，产生大量垃圾经验，用户无法参与经验沉淀，且检索能力弱。需要实现 Session 管理让对话可持久、可切换、可编辑，并将经验存储迁移到官方 SqliteStore，让用户主导经验沉淀。

## What Changes

* 新建 `src/agent/session_manager.py`：Session 数据模型（sessions 表）+ SessionManager CRUD

* 修改 `src/agent/checkpoint.py`：集成 SessionManager，统一 DB 连接

* 修改 `src/agent/config.py`：新增 session/experience 配置读取函数

* 修改 `src/app_pages/maintenance.py`：大幅重构 UI，左侧历史对话列表、session 切换、消息编辑重发、经验管理

* 重构 `src/agent/memory/experience_store.py`：从 InMemoryStore+JSON 迁移到官方 SqliteStore 领域层包装器

* 修改 `src/agent/graph.py`：经验读取逻辑适配新 API，移除自动经验保存，新增 save\_experience\_tool

* 修改 `src/agent/tools.py`：新增 `save_experience_tool`

* 修改 `src/agent/prompts/prompt.py`：添加经验记录 prompt 指导

* 修改 `src/agent/cli.py`：支持 session 列表/切换/新建/复制

* 修改 `config.yaml`：新增 session/experience 配置段，移除 experience\_persist\_path

* 新建 `tests/test_session_manager.py`：SessionManager 单元测试

* 新建 `tests/test_experience_store.py`：ExperienceStore 单元测试

## Impact

* Affected specs: 维修工 Agent 全部交互流程

* Affected code: `src/agent/` 目录下多个核心文件 + `src/app_pages/maintenance.py` + `config.yaml`

## ADDED Requirements

### Requirement: Session 数据模型与管理器

系统 SHALL 在 `data/agent_checkpoints.db` 中新增 `sessions` 表，包含 `session_id`、`thread_id`、`title`、`created_at`、`updated_at`、`message_count`、`is_archived` 字段。`session_id` 与 `thread_id` 一对一映射。

#### Scenario: 创建新 session

* **WHEN** 调用 `SessionManager.create_session()`

* **THEN** 生成 `sess_{uuid4_hex[:12]}` 格式的 session\_id 和对应 thread\_id，写入 sessions 表，返回 session 元数据

#### Scenario: 列出 session

* **WHEN** 调用 `SessionManager.list_sessions(include_archived=False)`

* **THEN** 返回非归档 session 列表，按 `updated_at` 降序排列

#### Scenario: 复制 session

* **WHEN** 调用 `SessionManager.duplicate_session(source_session_id)`

* **THEN** 创建新 session，通过 LangGraph `update_state` 在新 thread\_id 上种子化源 session 的状态

#### Scenario: 归档 session

* **WHEN** 调用 `SessionManager.archive_session(session_id)`

* **THEN** 将 `is_archived` 设为 1，归档的 session 不在默认列表中显示

#### Scenario: 对话标题手动编辑

* **WHEN** 用户在对话列表中点击标题编辑按钮并修改标题

* **THEN** 调用 `SessionManager.update_session(session_id, title=new_title)` 更新标题，UI 即时刷新显示新标题

#### Scenario: 旧 thread\_id 兼容

* **WHEN** `SessionManager.list_sessions()` 返回空列表但 checkpointer 中存在 checkpoint

* **THEN** 自动扫描 checkpoint 并为旧 thread\_id 创建对应的 session 记录

### Requirement: Streamlit 历史对话列表与切换

系统 SHALL 在 Streamlit 侧边栏显示历史对话列表，支持新建、切换、复制、归档操作。

#### Scenario: 显示历史对话列表

* **WHEN** 用户打开维修工页面

* **THEN** 左侧栏显示历史对话列表，按更新时间降序，当前对话高亮

#### Scenario: 切换对话

* **WHEN** 用户点击历史对话列表中的某个 session

* **THEN** 系统更新 `maintenance_session_id` 和 `maintenance_thread_id`，从 checkpoint 重建聊天消息，恢复 Agent 状态（含 interrupt 状态），页面 rerun

#### Scenario: 从 checkpoint 重建消息

* **WHEN** 切换到某个 session

* **THEN** 调用 `agent.get_state(config)` 获取 checkpoint，从 `state.values["messages"]` 中提取 HumanMessage 和 AIMessage 重建 UI 层 `maintenance_messages`。thinking\_parts 不持久化（可接受）

### Requirement: 消息编辑与重发（LangGraph Fork 模式）

系统 SHALL 支持用户编辑已发送的消息并从编辑点重新执行。

#### Scenario: 编辑消息并重发

* **WHEN** 用户点击用户消息旁的编辑按钮，修改内容后点击重发

* **THEN** 系统通过 LangGraph `get_state_history` 找到编辑消息对应的 checkpoint，用 `update_state` 创建 Fork（替换消息内容），从 Fork 点继续执行。原始 checkpoint 不被修改

#### Scenario: Fork 降级

* **WHEN** LangGraph Fork 模式在复杂 graph 中表现不稳定

* **THEN** 降级为将编辑后的消息作为新输入追加到当前 thread 末尾

### Requirement: CLI Session 支持

系统 SHALL 在 CLI 模式下支持 session 管理。

#### Scenario: 列出 session

* **WHEN** 用户执行 `pixi run agent --list-sessions`

* **THEN** 列出历史 session 的 ID、标题、更新时间

#### Scenario: 指定 session 继续

* **WHEN** 用户执行 `pixi run agent --session-id sess_abc123`

* **THEN** 使用指定 session\_id 对应的 thread\_id 继续对话

#### Scenario: 切换 session

* **WHEN** 用户在 CLI 中输入 `:switch <session_id>`

* **THEN** 切换到指定 session 继续对话

#### Scenario: 新建 session

* **WHEN** 用户在 CLI 中输入 `:new [title]`

* **THEN** 创建新 session 并切换

### Requirement: ExperienceStore 迁移到官方 SqliteStore

系统 SHALL 使用 LangGraph 官方 `SqliteStore`（来自 `langgraph.store.sqlite`）替换 `InMemoryStore`，与 `SqliteSaver` 共享同一数据库文件。

#### Scenario: 初始化 SqliteStore

* **WHEN** `_get_compiled_agent()` 初始化时

* **THEN** 创建 `SqliteStore(conn)` 实例（与 SqliteSaver 共享同一 sqlite3 连接），调用 `store.setup()`，传入 `compile_agent(checkpointer=checkpointer, store=store)`

#### Scenario: 旧 JSON 数据迁移

* **WHEN** `ExperienceStore` 初始化时检测到 `data/agent_experience.json` 存在

* **THEN** 自动将 JSON 中的经验数据迁移到 SqliteStore，完成后将旧文件重命名为 `.json.migrated`

### Requirement: ExperienceStore 领域层包装器

系统 SHALL 将 `ExperienceStore` 重构为基于官方 SqliteStore 的领域层包装器，提供结构化的经验 API。

#### Scenario: 保存经验

* **WHEN** 调用 `ExperienceStore.save_experience(summary, category, details, session_id, pdf_type, source_path)`

* **THEN** 生成 `exp_{uuid4_hex[:12]}` 格式的 key，namespace 为 `("maintenance", "experience", pdf_type)`，通过 `SqliteStore.put()` 写入

#### Scenario: 获取相关经验

* **WHEN** 调用 `ExperienceStore.get_relevant_experiences(pdf_type="annual_report")`

* **THEN** 通过 `SqliteStore.search(("maintenance", "experience", "annual_report"))` 搜索，返回经验列表

#### Scenario: 搜索经验

* **WHEN** 调用 `ExperienceStore.search_experiences(query="解析器")`

* **THEN** 通过 `SqliteStore.search()` 的 query 参数搜索（当前为关键词匹配，预留语义搜索升级路径）

### Requirement: 手动经验保存（save\_experience\_tool）

系统 SHALL 提供 `save_experience_tool`，当用户说"记住这个经验"时由 Agent 调用。

#### Scenario: 用户要求保存经验

* **WHEN** 用户在对话中说"记住这个经验"或类似表述

* **THEN** Agent 调用 `save_experience_tool(summary, category, details)` 保存经验到经验库，经验关联当前 session\_id

#### Scenario: Agent 不主动保存

* **WHEN** Agent 执行 parse\_pdf\_tool/chunk\_parsed\_tool 后

* **THEN** 不再自动保存经验（废弃自动模式）

### Requirement: 经验扫描模式

系统 SHALL 支持用户触发经验扫描，Agent 提取候选经验，用户确认后保存。

#### Scenario: 扫描经验

* **WHEN** 用户点击"扫描经验"按钮

* **THEN** 将当前对话历史发送给 Agent，附加特殊 prompt 提取候选经验，展示给用户逐条确认或拒绝，确认的调用 `save_experience_tool` 保存

### Requirement: 经验管理 UI

系统 SHALL 在侧边栏提供经验库展示和管理界面。

#### Scenario: 查看经验列表

* **WHEN** 用户查看侧边栏经验库区域

* **THEN** 显示经验列表（expander 形式），包含摘要、类别、详情

#### Scenario: 删除经验

* **WHEN** 用户点击经验旁的删除按钮

* **THEN** 调用 `ExperienceStore.delete_experience()` 删除该经验

## MODIFIED Requirements

### Requirement: 维修工 Agent 初始化

原：`_get_compiled_agent()` 使用 `InMemoryStore` + JSON 持久化初始化 ExperienceStore
改：`_get_compiled_agent()` 使用官方 `SqliteStore` 初始化，与 `SqliteSaver` 共享 sqlite3 连接，SessionManager 通过同一连接管理 sessions 表

### Requirement: 维修工 Agent 经验读取

原：`agent_node` 中根据 `current_source` 推断 PDF 类型，调用 `ExperienceStore.get_all_experiences(namespace)` 获取全部经验
改：`agent_node` 中使用 `ExperienceStore(store).get_relevant_experiences(pdf_type=pdf_type)` 获取相关经验，store 为 SqliteStore 实例

### Requirement: 维修工 Agent 经验写入

原：`tool_node` 中执行 `parse_pdf_tool`/`chunk_parsed_tool` 后自动保存经验
改：移除 `tool_node` 中的自动经验保存逻辑，改为用户通过 `save_experience_tool` 手动保存或扫描模式确认保存

### Requirement: 维修工 Streamlit session\_state

新增以下 session\_state 键：

* `maintenance_session_id` (str)：当前 session ID

* `maintenance_editing_msg_idx` (int | None)：正在编辑的消息索引

* `maintenance_show_archived` (bool)：是否显示已归档对话

修改以下 session\_state 键：

* `maintenance_thread_id`：从 session 元数据获取，不再随机生成

* `maintenance_messages`：切换 session 时从 checkpoint 重建

## REMOVED Requirements

### Requirement: InMemoryStore + JSON 持久化

**Reason**: 迁移到官方 SqliteStore，不再需要 InMemoryStore 和 JSON 文件落盘
**Migration**: 旧 JSON 文件自动迁移到 SqliteStore 后重命名为 `.migrated`

### Requirement: 自动经验保存

**Reason**: 产生大量垃圾经验，用户无法参与。改为手动保存 + 扫描确认模式
**Migration**: 移除 `tool_node` 中的自动保存逻辑，新增 `save_experience_tool` 供用户手动触发
