# Tasks

## Phase 1: Session 基础设施

- [ ] Task 1.1: 创建 SessionManager 模块
  - [ ] 新建 `src/agent/session_manager.py`
  - [ ] 实现 `sessions` 表 schema（CREATE TABLE + 索引）
  - [ ] 实现 `SessionManager.__init__` 连接到 agent_checkpoints.db
  - [ ] 实现 `create_session()` — 生成 session_id + thread_id，写入 sessions 表
  - [ ] 实现 `list_sessions(include_archived)` — 按 updated_at 降序
  - [ ] 实现 `get_session(session_id)` / `get_session_by_thread_id(thread_id)`
  - [ ] 实现 `update_session(session_id, **kwargs)` — 更新 title/is_archived/message_count
  - [ ] 实现 `delete_session(session_id)` — 删除 session 元数据
  - [ ] 实现 `archive_session()` / `unarchive_session()`
  - [ ] 实现 `touch_session(session_id)` — 更新 updated_at
  - [ ] 实现 `auto_title(session_id, first_message)` — 从首条消息提取标题
  - [ ] 实现 `duplicate_session(session_id, new_title)` — 基于 LangGraph update_state 种子化
  - [ ] 实现 `_migrate_orphan_checkpoints(checkpointer)` — 当 sessions 表为空但 checkpointer 中有 checkpoint 时，自动扫描并为旧 thread_id 创建 session 记录

- [ ] Task 1.2: 修改 checkpoint.py 集成 SessionManager
  - [ ] 新增 `get_session_manager()` 函数，返回与 checkpointer 共享同一 DB 连接的 SessionManager 实例
  - [ ] 确保 sessions 表在首次访问时自动创建

- [ ] Task 1.3: 更新 config.py 添加 session/experience 配置读取
  - [ ] 新增 `get_session_config()` 函数
  - [ ] 新增 `get_experience_config()` 函数
  - [ ] 更新 `config.yaml` 新增 `agent.session` 和 `agent.experience` 配置段

- [ ] Task 1.4: 编写 SessionManager 单元测试
  - [ ] 新建 `tests/test_session_manager.py`
  - [ ] 测试 CRUD 操作
  - [ ] 测试 duplicate_session（需 mock LangGraph agent）
  - [ ] 测试 archive/unarchive
  - [ ] 测试 auto_title

## Phase 2: Streamlit Session UI

- [ ] Task 2.1: 重构 `_get_compiled_agent` 集成 SessionManager 和 SqliteStore
  - [ ] 将 InMemoryStore 替换为官方 SqliteStore（与 SqliteSaver 共享 sqlite3 连接）
  - [ ] 初始化 SessionManager
  - [ ] 初始化时创建或恢复当前 session

- [ ] Task 2.2: 实现左侧历史对话列表 UI
  - [ ] 在侧边栏添加"新对话"按钮
  - [ ] 渲染历史对话列表（标题 + 日期），当前对话高亮
  - [ ] 添加弹出菜单（复制、归档、删除）

- [ ] Task 2.3: 实现 session 切换逻辑
  - [ ] 实现 `_switch_to_session(session_id)` 函数
  - [ ] 更新 `maintenance_session_id` 和 `maintenance_thread_id`
  - [ ] 从 checkpoint 重建聊天消息（`_rebuild_messages_from_checkpoint`）
  - [ ] 恢复 Agent 状态（含 interrupt 状态）

- [ ] Task 2.4: 实现新建对话
  - [ ] 点击"新对话"按钮创建新 session
  - [ ] 切换到新 session，清空消息列表

- [ ] Task 2.5: 实现对话复制
  - [ ] 基于 `update_state` 种子化新 thread
  - [ ] 创建新 session 并切换

- [ ] Task 2.6: 实现对话归档
  - [ ] 归档/取消归档按钮
  - [ ] 归档的 session 在折叠区域显示

- [ ] Task 2.7: 实现消息编辑与重发（LangGraph Fork 模式）
  - [ ] 用户消息旁添加编辑按钮
  - [ ] 编辑模式 UI（text_area + 重发/取消按钮）
  - [ ] 实现 `_resend_from_message(editing_idx, new_content)` 基于 Fork 模式
  - [ ] 实现 `_ui_msg_idx_to_checkpoint_step` 映射
  - [ ] Fork 降级方案：追加模式

- [ ] Task 2.8: 处理 interrupt 状态在 session 切换时的恢复
  - [ ] 切换 session 时检查 checkpoint 的 interrupt 状态
  - [ ] 正确恢复 `maintenance_interrupted` 和 `maintenance_interrupt_payload`

- [ ] Task 2.9: 初始化 session_state 新增键
  - [ ] `maintenance_session_id`
  - [ ] `maintenance_editing_msg_idx`
  - [ ] `maintenance_show_archived`

- [ ] Task 2.10: 实现对话标题手动编辑
  - [ ] 在对话列表项旁添加编辑按钮（popover 菜单中）
  - [ ] 编辑模式 UI（text_input + 保存/取消按钮）
  - [ ] 调用 `SessionManager.update_session()` 更新标题

## Phase 3: CLI Session 支持

- [ ] Task 3.1: CLI 添加 `--list-sessions` 和 `--session-id` 参数
  - [ ] 在 `_parse_cli_args` 中添加 `--list-sessions` 参数
  - [ ] 在 `_parse_cli_args` 中添加 `--session-id` 参数（指定 session_id 继续）
  - [ ] 实现列表输出格式

- [ ] Task 3.2: CLI 添加 `--new-session` 参数
  - [ ] 在 `_parse_cli_args` 中添加参数
  - [ ] 实现新建 session 逻辑

- [ ] Task 3.3: CLI 添加交互式快捷命令
  - [ ] `:sessions` — 列出历史 session
  - [ ] `:switch <session_id>` — 切换到指定 session
  - [ ] `:new [title]` — 新建 session
  - [ ] `:copy [session_id]` — 复制 session

- [ ] Task 3.4: CLI 集成 SessionManager 和 SqliteStore
  - [ ] 替换 InMemoryStore 为 SqliteStore
  - [ ] 初始化 SessionManager
  - [ ] thread_id 从 session 元数据获取

## Phase 4: ExperienceStore 重构 + SqliteStore 接入

- [ ] Task 4.1: 重构 ExperienceStore 为领域层包装器
  - [ ] 修改 `__init__` 接收 `BaseStore` 实例，移除 `persist_path` 参数和 JSON 持久化逻辑
  - [ ] 重写 `save_experience(summary, category, details, session_id, pdf_type, source_path)` — 使用 SqliteStore.put()
  - [ ] 重写 `get_relevant_experiences(pdf_type)` — 使用 SqliteStore.search() 前缀匹配
  - [ ] 重写 `search_experiences(query)` — 使用 SqliteStore.search() query 参数
  - [ ] 新增 `list_experiences(category, pdf_type, limit)` — 支持筛选
  - [ ] 新增 `delete_experience(namespace, key)`
  - [ ] 实现 `_migrate_from_json(json_path)` — 自动迁移旧数据

- [ ] Task 4.2: 修改 graph.py 经验读取逻辑
  - [ ] `agent_node` 中使用 `ExperienceStore(store).get_relevant_experiences(pdf_type)` 替换 `get_all_experiences(namespace)`
  - [ ] namespace 从 `("default", "maintenance_experience", pdf_type)` 改为 `("maintenance", "experience", pdf_type)`

- [ ] Task 4.3: 移除 tool_node 中的自动经验保存
  - [ ] 删除 `tool_node` 中 `experience_tools` 相关的自动保存逻辑

- [ ] Task 4.4: 新增 save_experience_tool
  - [ ] 在 `src/agent/tools.py` 中添加 `save_experience_tool`
  - [ ] 在 `src/agent/graph.py` 的 `_get_tools()` 中注册
  - [ ] 在 `src/agent/prompts/prompt.py` 中添加经验记录指导

- [ ] Task 4.5: 编写 ExperienceStore 单元测试
  - [ ] 新建 `tests/test_experience_store.py`
  - [ ] 测试 save/get/search/list/delete
  - [ ] 测试 JSON 迁移逻辑

- [ ] Task 4.6: 运行全量测试确认无回归
  - [ ] `pixi run test` 通过

## Phase 5: 经验扫描与管理 UI

- [ ] Task 5.1: 实现经验扫描逻辑
  - [ ] 将当前对话历史发送给 Agent，附加特殊 prompt 提取候选经验
  - [ ] 限制最大候选数（从 config 读取 `scan_max_candidates`）

- [ ] Task 5.2: 实现候选经验确认 UI
  - [ ] 展示候选经验列表，每条有确认/拒绝按钮
  - [ ] 确认的调用 `save_experience_tool` 保存

- [ ] Task 5.3: 实现经验列表展示 UI
  - [ ] 侧边栏经验库区域，expander 形式展示
  - [ ] 显示摘要、类别、详情

- [ ] Task 5.4: 实现经验删除 UI
  - [ ] 每条经验旁的删除按钮
  - [ ] 调用 `ExperienceStore.delete_experience()`

## Phase 6: 集成测试与收尾

- [ ] Task 6.1: 补充自动化测试
  - [ ] Session + Experience 集成测试
  - [ ] Streamlit UI 相关逻辑测试

- [ ] Task 6.2: 清理旧代码
  - [ ] 移除 InMemoryStore 依赖
  - [ ] 移除 JSON 持久化相关代码
  - [ ] 更新 `config.yaml` 移除 `experience_persist_path`

- [ ] Task 6.3: 质量验收
  - [ ] `pixi run test` 全量测试通过
  - [ ] `pixi run lint` 检查通过
  - [ ] 无残留的 InMemoryStore/JSON 持久化代码

# Task Dependencies

- Task 1.x → Task 2.x (Session UI 依赖 SessionManager)
- Task 1.x → Task 3.x (CLI 依赖 SessionManager)
- Task 1.1 → Task 1.4 (测试依赖实现)
- Task 2.1 → Task 2.2~2.9 (UI 各功能依赖初始化重构)
- Task 4.1 → Task 4.2~4.5 (ExperienceStore 重构是其他改动的基础)
- Task 4.1 → Task 5.x (经验 UI 依赖新 ExperienceStore API)
- Phase 1 → Phase 2 (Session 基础设施先于 UI)
- Phase 4 → Phase 5 (ExperienceStore 重构先于经验 UI)
- Phase 1+2 与 Phase 4 可部分并行（Session 和 Experience 相对独立）
