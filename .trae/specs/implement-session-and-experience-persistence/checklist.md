# Checklist

## Phase 1: Session 基础设施

- [x] SessionManager 类实现完整 CRUD（create/list/get/update/delete）(P0)
- [x] sessions 表在 agent_checkpoints.db 中正确创建，含索引 (P0)
- [x] duplicate_session 能通过 LangGraph update_state 种子化新 thread (P1)
- [x] archive/unarchive 功能正常 (P1)
- [x] auto_title 从首条消息提取标题（前 20 字符）(P2)
- [x] 旧 thread_id 兼容：sessions 表为空但 checkpointer 有 checkpoint 时，自动扫描并创建 session 记录 (P1)
- [x] checkpoint.py 正确集成 SessionManager，共享 DB 连接 (P0)
- [x] config.yaml 新增 agent.session 和 agent.experience 配置段 (P0)
- [x] config.py 新增 get_session_config() 和 get_experience_config() (P0)
- [x] SessionManager 单元测试全部通过 (P0)

## Phase 2: Streamlit Session UI

- [x] 左侧栏显示历史对话列表，按更新时间降序 (P0)
- [x] 当前对话在列表中高亮显示 (P0)
- [x] 点击历史对话可切换，聊天消息从 checkpoint 恢复 (P0)
- [x] 新建对话创建新 session，thread_id 正确 (P0)
- [x] 切换 session 后继续聊天，Agent 能正确接续上下文 (P0)
- [x] 切换 session 后 interrupt 状态正确恢复 (P0)
- [x] 对话复制通过 update_state 种子化新 thread (P1)
- [x] 对话归档与取消归档功能正常 (P1)
- [x] 消息编辑与重发通过 Fork 模式从编辑点重新执行 (P1)
- [x] Fork 降级方案（追加模式）可用 (P1)
- [x] 用户可手动编辑对话标题 (P2)
- [x] maintenance_session_id / maintenance_editing_msg_idx / maintenance_show_archived 新增键正确初始化 (P0)

## Phase 3: CLI Session 支持

- [x] `pixi run agent --list-sessions` 列出历史 session (P1)
- [x] `pixi run agent --session-id sess_abc123` 指定 session 继续 (P1)
- [x] `:switch <session_id>` 切换到指定 session (P1)
- [x] `:new [title]` 新建 session (P1)
- [x] `:copy [session_id]` 复制 session (P1)
- [x] CLI 使用 SqliteStore 替换 InMemoryStore (P0)

## Phase 4: ExperienceStore 重构 + SqliteStore 接入

- [x] 官方 SqliteStore 替换 InMemoryStore，与 SqliteSaver 共享数据库 (P0)
- [x] ExperienceStore 通过官方 SqliteStore 间接操作 (P0)
- [x] 旧 JSON 经验自动迁移到 SqliteStore，旧文件重命名为 .migrated (P0)
- [x] save_experience_tool 可被 Agent 调用 (P0)
- [x] Agent 在新对话中自动读取相关经验 (P0)
- [x] tool_node 中不再自动保存经验 (P0)
- [x] ExperienceStore 单元测试全部通过 (P0)
- [x] `pixi run test` 全量测试通过 (P0)

## Phase 5: 经验扫描与管理 UI

- [x] "扫描经验"按钮能触发 Agent 扫描当前对话 (P1)
- [x] 候选经验展示给用户，用户可逐条确认或拒绝 (P1)
- [x] 侧边栏显示经验库列表 (P1)
- [x] 用户可删除经验 (P2)

## Phase 6: 集成测试与收尾

- [x] `pixi run test` 全量测试通过 (P0)
- [x] `pixi run lint` 检查通过 (P0)
- [x] 无残留的 InMemoryStore/JSON 持久化代码 (P0)
- [x] 旧数据迁移后旧文件重命名为 .migrated (P0)
