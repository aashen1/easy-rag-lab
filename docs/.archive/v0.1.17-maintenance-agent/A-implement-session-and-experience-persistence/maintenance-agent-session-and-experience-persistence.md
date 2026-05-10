# 维修工 Agent — Session 管理与经验持久化 需求计划书

> 状态：Plan v3 | 日期：2026-05-09
> 依据：0 号设计总稿 C9 需求 + 9 号审查报告 P0-1 + 用户讨论确认 + LangGraph 官方文档
> 目标：为下一个冷启动对话提供完整、自包含的实施指南，无需再做先期调查

---

## 一、背景与动机

### 1.1 为什么要做 Session 管理？

当前维修工 Agent 的 Streamlit 页面存在以下问题：

1. **对话无法持久化**：`st.session_state.maintenance_messages` 是纯内存的，浏览器刷新/关闭后对话丢失
2. **无法切换对话**：每次打开都是"全新开始"，无法回到之前的对话继续工作
3. **无法复制/编辑对话**：用户不能对历史消息进行编辑重发，也不能复制一份对话走不同的分支
4. **thread_id 与 UI 脱节**：LangGraph 的 `thread_id` 已通过 SqliteSaver 持久化了 graph state，但 UI 层的聊天消息没有与之关联

**目标**：像网页版聊天工具一样，左侧有历史对话列表，支持新建、切换、复制、编辑，点击某个历史对话后完整恢复上下文并继续聊天。

### 1.2 为什么要做经验持久化？

当前 `ExperienceStore` 使用 `InMemoryStore` + JSON 文件落盘，存在以下问题：

1. **经验质量不可控**：当前是 Agent 自动保存经验（每次 parse_pdf/chunk_parsed 后自动写入），大量"垃圾经验"被持久化
2. **用户无法参与**：用户无法决定哪些经验值得保留
3. **检索能力弱**：`get_all_experiences` 返回某个 namespace 下的全部经验，无法按相关性筛选
4. **持久化方案粗糙**：JSON 文件全量读写，不支持增量更新，并发不安全

**目标**：让用户主导经验的沉淀——用户说"记住这个"就落盘；或者开启"经验扫描"模式让 Agent 提议、用户确认后落盘。经验存储迁移到 SQLite，与 checkpointer 共享数据库。

### 1.3 为什么先做 Session 再做经验？

Session 是基础设施——经验需要知道"来自哪个对话"，用户需要"在某个对话中说记住这个"。没有 Session 概念，经验的归属和上下文就无从谈起。因此实施顺序为：**先做 Session 管理 → 再做经验持久化**。

---

## 二、当前架构现状（冷启动必读）

### 2.1 关键文件清单

| 文件 | 作用 | 需要修改 |
|------|------|---------|
| `src/agent/state.py` | MaintenanceState TypedDict 定义 | ✅ 新增 session 相关字段 |
| `src/agent/graph.py` | LangGraph StateGraph 构建、agent_node/tool_node/approval_node | ✅ 经验写入逻辑改造 |
| `src/agent/checkpoint.py` | SqliteSaver 初始化（`get_checkpointer_direct`） | ✅ 新增 session 管理函数 |
| `src/agent/config.py` | Agent 配置读取 | ✅ 新增 session 配置 |
| `src/agent/memory/experience_store.py` | 经验存储（InMemoryStore + JSON） | ✅ 重构为 SQLite 后端 |
| `src/agent/cli.py` | CLI 交互入口 | ✅ 支持 session 列表/切换 |
| `src/app_pages/maintenance.py` | Streamlit 维修工页面（550 行） | ✅ 大幅重构 UI |
| `config.yaml` | Agent 配置段 | ✅ 新增 session/experience 配置 |

### 2.2 当前数据流

```
Streamlit UI (maintenance.py)
  │
  ├─ st.session_state.maintenance_messages  ← 聊天消息（纯内存，不持久化）
  ├─ st.session_state.maintenance_thread_id ← thread_id（随机生成，不持久化到 UI）
  ├─ st.session_state.maintenance_current_state ← Agent 状态快照
  │
  └─ _get_compiled_agent() [cached_resource]
       ├─ InMemoryStore → ExperienceStore → data/agent_experience.json
       └─ SqliteSaver → data/agent_checkpoints.db
              │
              └─ 按 thread_id 存储 checkpoint 链
```

### 2.3 当前 Session State 键（全部以 `maintenance_` 前缀）

| 键 | 类型 | 用途 |
|----|------|------|
| `maintenance_messages` | `list[dict]` | 对话历史（纯内存） |
| `maintenance_auto_review` | `bool` | 自动审查开关 |
| `maintenance_locked_tool` | `str \| None` | 工具链锁定 |
| `maintenance_current_state` | `dict` | 当前 Agent 状态 |
| `maintenance_mode` | `"light"/"full"` | 运行模式 |
| `maintenance_interrupted` | `bool` | 是否处于中断 |
| `maintenance_interrupt_payload` | `dict \| None` | 中断 payload |
| `maintenance_thread_id` | `str` | LangGraph thread_id |
| `maintenance_collapse_thinking` | `bool` | 折叠思考过程 |
| `maintenance_streaming` | `bool` | 是否正在流式输出 |
| `maintenance_pending_prompt` | `str \| None` | 待处理的用户输入 |
| `maintenance_latest_report` | `dict \| None` | 最新维修报告 |

### 2.4 当前 ExperienceStore 机制

- 底层：LangGraph `InMemoryStore`（进程内，不跨进程共享）
- 持久化：每次 `save_experience()` 后全量写 JSON 文件（原子写入：tempfile + os.replace）
- 加载：`ExperienceStore.__init__` 时从 JSON 文件加载到 InMemoryStore
- 写入时机：`tool_node` 中执行 `parse_pdf_tool`/`chunk_parsed_tool` 后自动保存
- 读取时机：`agent_node` 中根据 `current_source` 推断 PDF 类型，读取对应 namespace 的全部经验
- namespace 格式：`("default", "maintenance_experience", pdf_type)`
- 检索方式：`get_all_experiences()` 返回 namespace 下全部经验，无筛选

---

## 三、LangGraph 官方文档关键发现

> 以下内容来自 LangGraph 官方文档（通过 MCP 工具查阅），直接影响本计划的技术方案。

### 3.1 Checkpoint 与 Thread

- **Thread** = 一组 checkpoint 的容器，通过 `thread_id` 标识
- **Checkpoint** = 每个 super-step 的状态快照，包含 `values`、`next`、`config`、`metadata`、`created_at`、`parent_config`
- `get_state(config)` 返回最新的 `StateSnapshot`
- `get_state_history(config)` 返回按时间倒序排列的所有 checkpoint

### 3.2 Time Travel — Fork 模式（官方推荐）

LangGraph 官方文档明确支持 **Fork** 操作——从某个历史 checkpoint 创建分支：

```python
# 1. 找到要分叉的 checkpoint
history = list(graph.get_state_history(config))
before_joke = next(s for s in history if s.next == ("write_joke",))

# 2. Fork: 用 update_state 创建新分支
fork_config = graph.update_state(
    before_joke.config,
    values={"topic": "chickens"},  # 修改状态
)

# 3. 从 fork 点继续执行
fork_result = graph.invoke(None, fork_config)
```

**关键特性**：
- `update_state` **不会修改原始 checkpoint**，而是创建一个新的 checkpoint 分支
- 原始执行历史完整保留
- 可以指定 `as_node` 控制从哪个节点继续执行
- **在新鲜 thread 上设置状态**也是支持的（`as_node` 显式指定即可）

### 3.3 Memory Store — 跨 Thread 共享

LangGraph 官方文档区分两种记忆：

| 类型 | 作用域 | 实现 | 用途 |
|------|--------|------|------|
| **Short-term memory** | Thread 内 | Checkpointer | 对话历史 |
| **Long-term memory** | 跨 Thread | Store (BaseStore) | 用户偏好、经验知识 |

**Store 的生产后端**：官方提到 `PostgresStore`、`MongoDBStore`、`RedisStore`，以及 `SqliteStore`（来自 `langgraph.store.sqlite`，与 `SqliteSaver` 同包）。

**InMemoryStore 支持语义搜索**：

```python
store = InMemoryStore(index={"embed": embed_func, "dims": 128})
items = store.search(namespace, query="语言偏好", filter={"my-key": "my-value"})
```

这为未来升级经验检索提供了路径——实现 `SqliteStore` 时预留 `index` 参数接口。

### 3.4 Memory 写入策略

官方文档区分两种写入方式：

| 方式 | 说明 | 优缺点 |
|------|------|--------|
| **In the hot path** | Agent 在对话中实时写入 | 实时可见，但增加延迟和复杂度 |
| **In the background** | 后台任务异步写入 | 无延迟影响，但需要触发机制 |

我们的方案：
- **手动模式** = In the hot path（用户说"记住这个"时立即保存）
- **扫描模式** = In the background（用户点击按钮触发后台扫描）

---

## 四、Session 管理设计

### 4.1 数据模型

在 `data/agent_checkpoints.db` 中新增 `sessions` 表：

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,          -- 格式: "sess_{uuid4_hex[:12]}"
    thread_id   TEXT NOT NULL UNIQUE,      -- LangGraph thread_id，一对一映射
    title       TEXT NOT NULL DEFAULT '新对话',
    created_at  TEXT NOT NULL,             -- ISO 8601
    updated_at  TEXT NOT NULL,             -- ISO 8601，每次对话更新
    message_count INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0 -- 0=活跃, 1=归档
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_is_archived ON sessions(is_archived);
```

**设计决策**：
- `session_id` 与 `thread_id` 分离：`session_id` 是面向用户的标识，`thread_id` 是 LangGraph 内部标识
- 一对一映射：一个 session 恰好对应一个 LangGraph thread
- `title`：自动从第一条用户消息提取（取前 20 字符），用户可编辑
- `is_archived`：归档的 session 不在默认列表中显示，但不删除

### 4.2 Session 管理器

新建 `src/agent/session_manager.py`：

```python
class SessionManager:
    def __init__(self, db_path: str | None = None) -> None:
        """初始化 SessionManager，连接到 agent_checkpoints.db"""

    def create_session(self, title: str = "新对话") -> dict:
        """创建新 session，生成 session_id 和 thread_id，返回 session 元数据"""

    def list_sessions(self, include_archived: bool = False) -> list[dict]:
        """列出所有 session，按 updated_at 降序"""

    def get_session(self, session_id: str) -> dict | None:
        """获取单个 session 元数据"""

    def get_session_by_thread_id(self, thread_id: str) -> dict | None:
        """通过 thread_id 查找 session"""

    def update_session(self, session_id: str, **kwargs) -> None:
        """更新 session 元数据（title, is_archived, message_count 等）"""

    def delete_session(self, session_id: str) -> None:
        """删除 session 元数据（不删除 checkpoint，checkpoint 由 LangGraph 管理）"""

    def duplicate_session(self, session_id: str, new_title: str | None = None) -> dict:
        """复制 session：创建新 session，复制 checkpoint 状态到新 thread_id"""

    def archive_session(self, session_id: str) -> None:
        """归档 session"""

    def unarchive_session(self, session_id: str) -> None:
        """取消归档"""

    def touch_session(self, session_id: str) -> None:
        """更新 updated_at 为当前时间"""

    def auto_title(self, session_id: str, first_message: str) -> None:
        """从第一条用户消息自动提取标题（前 20 字符）"""
```

### 4.3 Session 与 Checkpoint 的关系

```
sessions 表                    LangGraph checkpoints
┌──────────────────┐          ┌─────────────────────────┐
│ session_id       │          │ thread_id               │
│ thread_id ───────┼─────────>│ checkpoint_id 链        │
│ title            │          │   ├─ ckpt_0 (初始)      │
│ created_at       │          │   ├─ ckpt_1 (第1轮)     │
│ updated_at       │          │   ├─ ckpt_2 (第2轮)     │
│ message_count    │          │   └─ ckpt_N (最新)      │
│ is_archived      │          │                         │
└──────────────────┘          └─────────────────────────┘
```

**关键**：切换 session 时，只需更换 `thread_id`，LangGraph 会自动从 checkpointer 恢复对应的 graph state。UI 层的聊天消息需要从 checkpoint 中重建（见 4.5 节）。

### 4.4 聊天消息持久化策略

**问题**：当前聊天消息存在 `st.session_state.maintenance_messages` 中，不持久化。切换 session 后需要恢复聊天消息。

**方案**：聊天消息从 LangGraph checkpoint 的 `messages` 字段重建。

**原理**：
- LangGraph 的 `MaintenanceState.messages` 已经包含了完整的对话历史（用户消息 + AI 消息 + ToolMessage）
- 切换 session 时，调用 `agent.get_state(config)` 获取当前 checkpoint 的 state
- 从 `state.values["messages"]` 中提取聊天消息，重建 UI 层的 `maintenance_messages`

**重建逻辑**：

```python
def _rebuild_messages_from_checkpoint(agent, thread_id: str) -> list[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    graph_state = agent.get_state(config)
    if not graph_state or not graph_state.values:
        return []

    messages = graph_state.values.get("messages", [])
    ui_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            ui_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            if msg.content:  # 跳过纯 tool_call 消息
                ui_messages.append({
                    "role": "assistant",
                    "content": _extract_text_from_content(msg.content),
                    "thinking_parts": [],  # thinking_parts 不持久化，切换后不显示
                })
    return ui_messages
```

**限制**：`thinking_parts`（思考过程和工具调用详情）不持久化到 checkpoint，切换 session 后无法恢复。这是可接受的——用户关心的是对话内容和结果，不是中间过程。

### 4.5 Streamlit UI 重构

#### 4.5.1 整体布局

```
┌──────────────────────────────────────────────────────────────┐
│  🔧 RAG 维修工                                                │
├──────────────┬───────────────────────────────────────────────┤
│              │                                               │
│  历史对话     │   主对话区域                                    │
│              │                                               │
│  [+ 新对话]   │   ┌─────────────────────────────────────┐    │
│              │   │ 👤 用户: 解析这个年报 PDF              │    │
│  📄 年报解析  │   │ 🤖 维修工: 已完成解析...              │    │
│     05-09    │   │ 👤 用户: 记住这个经验                  │    │
│              │   │ 🤖 维修工: 好的，已记录...              │    │
│  📄 分块测试  │   └─────────────────────────────────────┘    │
│     05-08    │                                               │
│              │   ┌─────────────────────────────────────┐    │
│  📄 索引重建  │   │ ⚠️ 等待审批: delete_source          │    │
│     05-07    │   │ [✅ 批准]  [❌ 拒绝]                  │    │
│              │   └─────────────────────────────────────┘    │
│  ──────────  │                                               │
│  📦 已归档    │   ┌─────────────────────────────────────┐    │
│   📄 旧测试   │   │ 输入问题进行诊断...          [发送]  │    │
│              │   └─────────────────────────────────────┘    │
│              │                                               │
│  ──────────  │   📋 执行日志  │  📊 阶段历史               │
│  🧠 经验库   │   📄 维修报告 (如有)                        │
│  🔍 扫描经验  │                                               │
│  💡 经验1    │                                               │
│  💡 经验2    │                                               │
│              │                                               │
├──────────────┴───────────────────────────────────────────────┤
│  🗺️ 维修工架构图                                              │
└──────────────────────────────────────────────────────────────┘
```

#### 4.5.2 左侧栏：历史对话列表

```python
with st.sidebar:
    st.markdown("### 💬 对话历史")

    if st.button("➕ 新对话", key="btn_new_session", use_container_width=True):
        session_mgr = _get_session_manager()
        new_session = session_mgr.create_session()
        _switch_to_session(new_session["session_id"])
        st.rerun()

    sessions = session_mgr.list_sessions()
    for sess in sessions:
        is_current = sess["session_id"] == st.session_state.maintenance_session_id
        with st.container():
            col_title, col_menu = st.columns([5, 1])
            with col_title:
                label = f"{'▶ ' if is_current else ''}{sess['title']}"
                if st.button(label, key=f"sess_{sess['session_id']}",
                             type="primary" if is_current else "secondary",
                             use_container_width=True):
                    if not is_current:
                        _switch_to_session(sess["session_id"])
                        st.rerun()
            with col_menu:
                # 弹出菜单：复制、归档、删除
                menu = st.popover("⋯", key=f"menu_{sess['session_id']}")
                if menu.button("📋 复制", key=f"dup_{sess['session_id']}"):
                    _duplicate_session(sess["session_id"])
                if menu.button("📦 归档" if not sess["is_archived"] else "📤 取消归档",
                               key=f"arch_{sess['session_id']}"):
                    ...
```

#### 4.5.3 消息编辑与重发（基于 LangGraph Fork 模式）

**核心原理**：利用 LangGraph 官方 Fork API，从某条消息对应的 checkpoint 创建分支，替换消息内容后继续执行。

```python
def _resend_from_message(editing_idx: int, new_content: str) -> None:
    """基于 LangGraph Fork 模式的消息编辑重发

    步骤：
    1. 通过 get_state_history 找到编辑消息对应的 checkpoint
    2. 用 update_state 在该 checkpoint 创建 Fork（替换消息内容）
    3. 用 invoke(None, fork_config) 从 Fork 点继续执行
    """
    agent = _get_compiled_agent()
    thread_id = st.session_state.maintenance_thread_id
    config = {"configurable": {"thread_id": thread_id}}

    # 1. 找到编辑消息对应的 checkpoint
    # UI 消息索引 → checkpoint 步骤的映射
    # 每条用户消息对应一个 checkpoint（source="input"）
    target_step = _ui_msg_idx_to_checkpoint_step(editing_idx)
    history = list(agent.get_state_history(config))
    target_ckpt = next(s for s in history if s.metadata["step"] == target_step)

    # 2. Fork: 修改该 checkpoint 的消息
    fork_config = agent.update_state(
        target_ckpt.config,
        values={"messages": [{"role": "user", "content": new_content}]},
        as_node="agent",  # 将更新视为 agent 节点产生，后续走 tools 路径
    )

    # 3. 从 Fork 点继续执行
    st.session_state.maintenance_messages = st.session_state.maintenance_messages[:editing_idx]
    st.session_state.maintenance_messages.append({"role": "user", "content": new_content})

    with st.chat_message("assistant"):
        _render_streaming_agent(agent, None, fork_config)
```

**关键细节**：
- `update_state` 创建新分支，**不修改原始 checkpoint**，原始对话历史完整保留
- `as_node` 参数控制 Fork 后从哪个节点继续执行
- 如果 Fork 失败或过于复杂，降级方案为：直接用新消息在当前 thread 末尾追加（不 Fork）

**UI 编辑按钮**：

```python
for i, msg in enumerate(st.session_state.maintenance_messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            col_content, col_edit = st.columns([6, 1])
            with col_content:
                st.markdown(msg["content"])
            with col_edit:
                if st.button("✏️", key=f"edit_msg_{i}"):
                    st.session_state.maintenance_editing_msg_idx = i
                    st.rerun()
        else:
            # assistant 消息渲染（含 thinking_parts）
            ...
```

**编辑模式**：

```python
editing_idx = st.session_state.get("maintenance_editing_msg_idx")
if editing_idx is not None:
    original_content = st.session_state.maintenance_messages[editing_idx]["content"]
    new_content = st.text_area("编辑消息", value=original_content,
                                key=f"edit_area_{editing_idx}")
    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("🔄 重发", key=f"resend_msg_{editing_idx}"):
            _resend_from_message(editing_idx, new_content)
    with col_cancel:
        if st.button("取消", key=f"cancel_edit_{editing_idx}"):
            st.session_state.maintenance_editing_msg_idx = None
            st.rerun()
```

#### 4.5.4 对话复制（基于 LangGraph update_state 种子化）

**核心原理**：利用 LangGraph 官方文档提到的"在新鲜 thread 上设置状态"能力。

```python
def _duplicate_session(source_session_id: str) -> None:
    """复制 session：在新 thread_id 上种子化源 session 的状态"""
    agent = _get_compiled_agent()
    session_mgr = _get_session_manager()

    # 1. 获取源 session 的当前状态
    source_session = session_mgr.get_session(source_session_id)
    source_config = {"configurable": {"thread_id": source_session["thread_id"]}}
    source_state = agent.get_state(source_config)

    # 2. 创建新 session（新 thread_id）
    new_session = session_mgr.create_session(
        title=f"{source_session['title']} (副本)"
    )

    # 3. 在新 thread 上种子化源状态
    # LangGraph 文档: "Specify as_node explicitly when: No execution history:
    # Setting up state on a fresh thread (common in testing)."
    new_config = {"configurable": {"thread_id": new_session["thread_id"]}}
    agent.update_state(
        new_config,
        values=source_state.values,
        as_node="__input__",
    )

    # 4. 切换到新 session
    _switch_to_session(new_session["session_id"])
    st.rerun()
```

### 4.6 Session 切换流程

```
用户点击历史对话列表中的某个 session
  │
  ├─ 1. 保存当前 session 的 UI 状态（如有修改）
  │
  ├─ 2. 更新 st.session_state.maintenance_session_id = target_session_id
  │     更新 st.session_state.maintenance_thread_id = target_thread_id
  │
  ├─ 3. 从 checkpoint 重建聊天消息：
  │     messages = _rebuild_messages_from_checkpoint(agent, target_thread_id)
  │     st.session_state.maintenance_messages = messages
  │
  ├─ 4. 从 checkpoint 恢复 Agent 状态：
  │     state = agent.get_state(config)
  │     st.session_state.maintenance_current_state = _extract_current_state(state.values)
  │
  ├─ 5. 检查 interrupt 状态：
  │     if state.values.get("__interrupt__"):
  │         st.session_state.maintenance_interrupted = True
  │         st.session_state.maintenance_interrupt_payload = ...
  │
  └─ 6. st.rerun()
```

### 4.7 Session State 键变更

新增/修改的 session_state 键：

| 键 | 类型 | 变更 | 用途 |
|----|------|------|------|
| `maintenance_session_id` | `str` | **新增** | 当前 session ID |
| `maintenance_thread_id` | `str` | **修改** | 从 session 元数据获取，不再随机生成 |
| `maintenance_messages` | `list[dict]` | **修改** | 切换 session 时从 checkpoint 重建 |
| `maintenance_editing_msg_idx` | `int \| None` | **新增** | 正在编辑的消息索引 |
| `maintenance_show_archived` | `bool` | **新增** | 是否显示已归档对话 |

### 4.8 CLI Session 支持

CLI 模式也需要支持 session 管理：

```bash
# 列出历史 session
pixi run agent --list-sessions

# 指定 session 继续
pixi run agent --session-id sess_abc123

# 新建 session
pixi run agent --new-session "年报解析测试"
```

CLI 内部快捷命令扩展：

| 命令 | 作用 |
|------|------|
| `:sessions` | 列出历史 session |
| `:switch <session_id>` | 切换到指定 session |
| `:new [title]` | 新建 session |
| `:copy [session_id]` | 复制当前/指定 session |

---

## 五、经验持久化设计

### 5.1 架构：两层分离

```
┌─────────────────────────────────────────────┐
│  ExperienceStore (领域层)                     │
│  - save_experience(summary, category, ...)  │
│  - get_relevant_experiences(pdf_type)       │
│  - search_experiences(query)                │
│  - list_experiences(category, pdf_type)     │
├─────────────────────────────────────────────┤
│  SqliteStore (官方内置，langgraph.store.sqlite)│
│  - put(namespace, key, value, index, ttl)   │
│  - get(namespace, key)                      │
│  - search(namespace_prefix, query, filter)  │
│  - delete(namespace, key)                   │
│  - list_namespaces(prefix)                  │
│                                             │
│  持久化: data/agent_checkpoints.db          │
│  与 SqliteSaver 共享同一数据库文件            │
│  支持语义搜索（配置 index 参数）              │
│  支持 TTL（数据过期）                         │
└─────────────────────────────────────────────┘
```

**为什么两层？**
- `SqliteStore`（官方内置）是通用 KV 存储，LangGraph 节点通过 `store` 参数自然访问
- `ExperienceStore` 是领域包装器，提供结构化的经验 API（category、pdf_type 筛选）
- 未来其他跨 thread 数据（用户偏好、配置等）也可以用 `SqliteStore`
- `ExperienceStore` 内部通过 `SqliteStore` 的 `put`/`search` 实现经验存取

### 5.2 SqliteStore 使用（官方内置，无需自己实现）

> **重要更正**：LangGraph 官方已提供 `SqliteStore`（来自 `langgraph.store.sqlite`），
> 与 `SqliteSaver` 在同一个包 `langgraph-checkpoint-sqlite` 中。
> **不需要自己实现 `BaseStore`**，直接使用官方类即可。

**来源**：`from langgraph.store.sqlite import SqliteStore`

**初始化方式**：

```python
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

conn = sqlite3.connect("data/agent_checkpoints.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")

checkpointer = SqliteSaver(conn)
store = SqliteStore(conn)
store.setup()

agent = compile_agent(checkpointer=checkpointer, store=store)
```

**官方 SqliteStore 的完整能力**：

| 能力 | 说明 | 状态 |
|------|------|------|
| `put(namespace, key, value, index, ttl)` | 写入，支持 index 和 ttl 参数 | ✅ 可用 |
| `get(namespace, key)` | 按 key 读取 | ✅ 可用 |
| `search(namespace_prefix, query, filter, limit, offset)` | 搜索，支持 query 语义搜索和 filter 过滤 | ✅ 可用 |
| `delete(namespace, key)` | 删除 | ✅ 可用 |
| `list_namespaces(prefix)` | 列出 namespace | ✅ 可用 |
| 语义搜索 | 配置 `index={"embed": embed_func, "dims": N, "fields": [...]}` | ✅ 可用（预留口子） |
| TTL 数据过期 | 配置 `ttl=TTLConfig(...)` | ✅ 可用 |

**语义搜索预留口子**：

当前不配置语义搜索（经验量小，关键词匹配够用），但预留升级路径：

```python
# 当前：不配置 index，使用基础搜索
store = SqliteStore(conn)

# 未来：配置 index，启用语义搜索（复用项目 RAG 链路的嵌入模型）
# 项目已有嵌入模型配置（config.yaml 中的 embeddings 段），可直接复用
from langchain.embeddings import init_embeddings
store = SqliteStore(
    conn,
    index={
        "embed": init_embeddings("openai:text-embedding-3-small"),
        "dims": 1536,
        "fields": ["summary", "details"],
    },
)
```

**与 InMemoryStore 的兼容性**：
- `SqliteStore` 实现了 `BaseStore` 的全部接口，可以直接替换 `InMemoryStore`
- 传入 `compile_agent(checkpointer=checkpointer, store=store)` 即可
- LangGraph 节点通过 `store` 参数接收，无需修改节点签名
- `search` 方法签名略有不同：`SqliteStore.search(namespace_prefix, /, *, query, filter, ...)`
  注意第一个参数是 `namespace_prefix`（前缀匹配），不是精确 namespace

### 5.3 ExperienceStore 重构

```python
class ExperienceStore:
    """经验存储领域层，底层使用官方 SqliteStore"""

    NAMESPACE_PREFIX = ("maintenance", "experience")

    def __init__(self, store: BaseStore) -> None:
        self._store = store

    def save_experience(
        self,
        summary: str,
        category: str,
        details: str,
        session_id: str | None = None,
        pdf_type: str | None = None,
        source_path: str | None = None,
    ) -> str:
        """保存一条经验到经验库，返回经验 key"""
        key = f"exp_{uuid.uuid4().hex[:12]}"
        namespace = self.NAMESPACE_PREFIX + ((pdf_type,) if pdf_type else ("generic",))
        value = {
            "summary": summary,
            "category": category,
            "details": details,
            "session_id": session_id,
            "pdf_type": pdf_type,
            "source_path": source_path,
            "timestamp": datetime.now().isoformat(),
        }
        self._store.put(namespace, key, value)
        return key

    def get_relevant_experiences(self, pdf_type: str | None = None) -> list[dict]:
        """获取与当前上下文相关的经验"""
        # SqliteStore.search 的第一个参数是 namespace_prefix（前缀匹配）
        # 搜索 ("maintenance", "experience", pdf_type) 下的所有条目
        namespace_prefix = self.NAMESPACE_PREFIX + ((pdf_type,) if pdf_type else ())
        items = self._store.search(namespace_prefix, limit=20)
        return [item.value for item in items]

    def search_experiences(self, query: str, limit: int = 10) -> list[dict]:
        """搜索经验（当前为关键词匹配，配置 index 后可升级为语义搜索）"""
        items = self._store.search(
            self.NAMESPACE_PREFIX,
            query=query,
            limit=limit,
        )
        return [item.value for item in items]

    def list_experiences(
        self, category: str | None = None, pdf_type: str | None = None, limit: int = 50,
    ) -> list[dict]:
        """列出经验，支持筛选"""
        namespace_prefix = self.NAMESPACE_PREFIX + ((pdf_type,) if pdf_type else ())
        filter_dict = {"category": category} if category else None
        items = self._store.search(namespace_prefix, filter=filter_dict, limit=limit)
        return [{"namespace": item.namespace, "key": item.key, **item.value} for item in items]

    def delete_experience(self, namespace: tuple[str, ...], key: str) -> None:
        """删除一条经验"""
        self._store.delete(namespace, key)
```

**关键变更**：
- 不再直接操作 SQLite 表，而是通过官方 `SqliteStore` 间接操作
- `ExperienceStore` 不再自己管理数据库连接和 JSON 文件
- 经验的 namespace 组织：`("maintenance", "experience", pdf_type)` — 与 LangGraph Store 的 namespace 体系一致
- `save_experience` 的参数从 `(namespace, experience_dict)` 改为结构化参数
- 新增 `category` 和 `pdf_type` 筛选（通过 `search` 的 `filter` 参数实现）
- `search` 使用 `namespace_prefix`（前缀匹配），可以一次搜索多个子 namespace

### 5.4 经验写入模式

| 模式 | 触发方式 | 用户参与度 | 适用场景 |
|------|---------|-----------|---------|
| **手动模式** | 用户说"记住这个经验" | 高 | 用户明确知道哪些经验有价值 |
| **扫描模式** | 用户点击"扫描经验"按钮 | 中 | Agent 提议，用户确认 |
| ~~自动模式~~ | ~~Agent 自动保存~~ | 无 | **废弃**——当前方案，产生大量垃圾经验 |

#### 5.4.1 手动模式

用户在对话中说"记住这个经验"或类似表述，Agent 调用 `save_experience_tool` 保存经验。

**新增工具** `save_experience_tool`：

```python
@tool
def save_experience_tool(
    summary: str,
    category: str,
    details: str,
) -> dict:
    """保存一条维修经验到经验库。

    当用户说"记住这个经验"、"记录下来"时调用此工具。

    Args:
        summary: 经验摘要（一句话，如"年报表格多时用 fitz+pdfplumber 组合"）
        category: 经验类别（parser_selection / chunk_strategy / workflow_tip / other）
        details: 经验详情（包含具体场景、推荐方案、原因等）
    """
```

**Prompt 指导**（添加到 `prompt.py`）：

```
## 经验记录

当用户说"记住这个经验"、"记录下来"等类似表述时，你应该：
1. 从当前对话上下文中提取关键经验
2. 用简洁的 summary 概括（一句话）
3. 选择合适的 category
4. 在 details 中详细描述场景、推荐方案、原因
5. 调用 save_experience_tool 保存

不要主动保存经验——只有用户明确要求时才保存。
```

#### 5.4.2 扫描模式

用户点击"扫描经验"按钮，Agent 扫描当前对话，提取可能有价值的经验，展示给用户确认。

**实现方式**：

1. 用户点击"🔍 扫描经验"按钮
2. 将当前对话历史（messages）发送给 Agent，附加特殊 prompt："请扫描以下对话，提取可能有价值的维修经验。每条经验包含 summary、category、details。只提取真正有价值的技巧性知识，不要提取临时性信息（如某个 bug 的修复过程）。"
3. Agent 返回候选经验列表
4. UI 展示候选经验，用户逐条确认或拒绝
5. 确认的经验调用 `save_experience_tool` 保存

### 5.5 经验读取集成

**当前**：`agent_node` 中根据 `current_source` 推断 PDF 类型，调用 `ExperienceStore.get_all_experiences(namespace)` 获取全部经验注入 prompt。

**改为**：

```python
def agent_node(state, *, store=None, config=None):
    # store 现在是 SqliteStore 实例（持久化的）
    experience_store = ExperienceStore(store)
    pdf_type = _infer_pdf_type(state.get("current_source"))
    relevant_experiences = experience_store.get_relevant_experiences(pdf_type=pdf_type)

    system_prompt = build_system_prompt(
        ...,
        past_experiences=relevant_experiences,
    )
```

**关键改进**：
- `store` 参数现在是官方 `SqliteStore` 实例，不再是 `InMemoryStore`
- `ExperienceStore` 直接用 `store` 参数构造，无需全局单例
- 经验数据持久化在 SQLite 中，进程重启后不丢失

### 5.6 经验管理 UI

在侧边栏添加经验管理区域：

```python
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🧠 经验库")

    if st.button("🔍 扫描经验", key="btn_scan_experience", disabled=is_streaming):
        ...

    store = _get_store()  # 官方 SqliteStore 实例
    experience_store = ExperienceStore(store)
    experiences = experience_store.list_experiences(limit=20)
    for exp in experiences:
        with st.expander(f"💡 {exp['summary']}", expanded=False):
            st.markdown(f"**类别**: {exp['category']}")
            st.markdown(exp['details'])
            if st.button("🗑️ 删除", key=f"del_exp_{exp['key']}"):
                experience_store.delete_experience(exp['namespace'], exp['key'])
                st.rerun()
```

### 5.7 经验与 Session 的关系

```
Session A (年报解析)
  │
  ├─ 用户: "用 fitz+pdfplumber 解析年报效果好"
  ├─ 用户: "记住这个经验"
  │     │
  │     └─ Agent 调用 save_experience_tool
  │            │
  │            └─ ExperienceStore.save_experience(
  │                   summary="年报用 fitz+pdfplumber",
  │                   category="parser_selection",
  │                   session_id="sess_abc123",  ← 记录来源
  │                   pdf_type="annual_report",
  │               )
  │               → SqliteStore.put(
  │                     ("maintenance", "experience", "annual_report"),
  │                     "exp_xxx",
  │                     {summary, category, details, session_id, ...}
  │                 )
  │
  └─ 经验持久化到 SQLite

Session B (新对话，处理另一个年报)
  │
  ├─ agent_node 自动读取相关经验:
  │     ExperienceStore(store).get_relevant_experiences(pdf_type="annual_report")
  │     → SqliteStore.search(("maintenance", "experience", "annual_report"))
  │     → 返回 Session A 中保存的经验
  │
  └─ Agent 在 prompt 中看到历史经验，推荐 fitz+pdfplumber
```

---

## 六、实施步骤

### Phase 1: Session 基础设施（预计 6-8 小时）

**目标**：实现 Session 数据模型和管理器，不涉及 UI 变更

| 步骤 | 内容 | 涉及文件 | 产出 |
|------|------|---------|------|
| 1.1 | 创建 `sessions` 表 schema | `src/agent/session_manager.py`（新建） | 表结构 + 迁移逻辑 |
| 1.2 | 实现 `SessionManager` 类 | `src/agent/session_manager.py` | 完整 CRUD |
| 1.3 | 实现 `duplicate_session`（基于 `update_state` 种子化） | `src/agent/session_manager.py` | 复制对话功能 |
| 1.4 | 修改 `checkpoint.py` 集成 SessionManager | `src/agent/checkpoint.py` | 统一 DB 连接 |
| 1.5 | 更新 `config.yaml` 添加 session 配置 | `config.yaml` | 配置项 |
| 1.6 | 编写 SessionManager 单元测试 | `tests/test_agent.py` | 测试覆盖 |

**验收标准**：
- SessionManager 的 CRUD 操作全部通过测试
- duplicate_session 能正确复制 checkpoint 到新 thread（使用 `update_state` 种子化）
- sessions 表与 checkpoints 表在同一个 SQLite 文件中

### Phase 2: Streamlit Session UI（预计 8-10 小时）

**目标**：重构 Streamlit 页面，实现历史对话列表、切换、新建

| 步骤 | 内容 | 涉及文件 | 产出 |
|------|------|---------|------|
| 2.1 | 重构 `_get_compiled_agent` 集成 SessionManager | `src/app_pages/maintenance.py` | 初始化逻辑 |
| 2.2 | 实现左侧历史对话列表 UI | `src/app_pages/maintenance.py` | 侧边栏对话列表 |
| 2.3 | 实现 session 切换逻辑 | `src/app_pages/maintenance.py` | `_switch_to_session()` |
| 2.4 | 实现从 checkpoint 重建聊天消息 | `src/app_pages/maintenance.py` | `_rebuild_messages_from_checkpoint()` |
| 2.5 | 实现新建对话 | `src/app_pages/maintenance.py` | 新建按钮逻辑 |
| 2.6 | 实现对话复制（基于 `update_state` 种子化） | `src/app_pages/maintenance.py` | 复制按钮逻辑 |
| 2.7 | 实现对话归档 | `src/app_pages/maintenance.py` | 归档按钮逻辑 |
| 2.8 | 实现消息编辑与重发（基于 LangGraph Fork） | `src/app_pages/maintenance.py` | 编辑按钮 + 重发逻辑 |
| 2.9 | 处理 interrupt 状态在 session 切换时的恢复 | `src/app_pages/maintenance.py` | interrupt 恢复 |
| 2.10 | 手动测试全流程 | - | 验证 |

**验收标准**：
- 左侧显示历史对话列表，按更新时间降序
- 点击历史对话可切换，聊天消息从 checkpoint 恢复
- 新建对话创建新 session，thread_id 正确
- 复制对话能通过 `update_state` 种子化新 thread
- 编辑消息后重发，通过 Fork 模式从编辑点重新执行
- interrupt 状态在切换后正确恢复

### Phase 3: CLI Session 支持（预计 2-3 小时）

**目标**：CLI 支持 session 列表和切换

| 步骤 | 内容 | 涉及文件 | 产出 |
|------|------|---------|------|
| 3.1 | CLI 添加 `--list-sessions` 参数 | `src/agent/cli.py` | 列表输出 |
| 3.2 | CLI 添加 `--new-session` 参数 | `src/agent/cli.py` | 新建 session |
| 3.3 | CLI 添加 `:sessions` / `:switch` / `:new` / `:copy` 快捷命令 | `src/agent/cli.py` | 交互式命令 |
| 3.4 | 手动测试 | - | 验证 |

**验收标准**：
- `pixi run agent --list-sessions` 列出历史 session
- `:switch sess_abc123` 切换到指定 session
- `:new 年报测试` 新建 session

### Phase 4: ExperienceStore 重构 + SqliteStore 接入（预计 3-4 小时）

**目标**：用官方 SqliteStore 替换 InMemoryStore，重构 ExperienceStore 为领域层包装器

| 步骤 | 内容 | 涉及文件 | 产出 |
|------|------|---------|------|
| 4.1 | 修改 `_get_compiled_agent` 使用官方 `SqliteStore` | `src/app_pages/maintenance.py` | 初始化 |
| 4.2 | 重构 `ExperienceStore` 为领域层包装器 | `src/agent/memory/experience_store.py` | 新 API |
| 4.3 | 实现数据迁移（JSON → SqliteStore） | `src/agent/memory/experience_store.py` | 迁移逻辑 |
| 4.4 | 修改 `graph.py` 中的经验读取逻辑 | `src/agent/graph.py` | 适配新 API |
| 4.5 | 移除 `tool_node` 中的自动经验保存 | `src/agent/graph.py` | 废弃自动模式 |
| 4.6 | 新增 `save_experience_tool` | `src/agent/tools.py` | 新工具 |
| 4.7 | 更新 prompt.py 添加经验记录指导 | `src/agent/prompts/prompt.py` | prompt 更新 |
| 4.8 | 编写 ExperienceStore 单元测试 | `tests/test_agent.py` | 测试覆盖 |
| 4.9 | 运行全量测试确认无回归 | - | `pixi run test` |

**验收标准**：
- 官方 `SqliteStore` 替换 `InMemoryStore`，与 `SqliteSaver` 共享同一数据库
- ExperienceStore 通过官方 SqliteStore 间接操作
- 旧 JSON 文件中的经验能自动迁移到 SqliteStore
- `save_experience_tool` 可被 Agent 调用
- 全量测试通过

### Phase 5: 经验扫描与管理 UI（预计 4-5 小时）

**目标**：实现经验扫描和管理 UI

| 步骤 | 内容 | 涉及文件 | 产出 |
|------|------|---------|------|
| 5.1 | 实现经验扫描逻辑（Agent 提取候选经验） | `src/app_pages/maintenance.py` | 扫描功能 |
| 5.2 | 实现候选经验确认 UI | `src/app_pages/maintenance.py` | 确认界面 |
| 5.3 | 实现经验列表展示 UI | `src/app_pages/maintenance.py` | 侧边栏经验库 |
| 5.4 | 实现经验删除 UI | `src/app_pages/maintenance.py` | 删除按钮 |
| 5.5 | 手动测试全流程 | - | 验证 |

**验收标准**：
- "扫描经验"按钮能触发 Agent 扫描当前对话
- 候选经验展示给用户，用户可逐条确认或拒绝
- 侧边栏显示经验库列表
- 用户可删除经验

### Phase 6: 集成测试与收尾（预计 3-4 小时）

**目标**：端到端测试、清理、文档

| 步骤 | 内容 | 涉及文件 | 产出 |
|------|------|---------|------|
| 6.1 | 端到端手动测试 | - | 测试报告 |
| 6.2 | 补充自动化测试 | `tests/test_agent.py` | 测试覆盖 |
| 6.3 | 清理旧代码（移除 InMemoryStore 依赖、JSON 持久化） | 多个文件 | 代码清理 |
| 6.4 | 更新 config.yaml 移除 `experience_persist_path` | `config.yaml` | 配置清理 |
| 6.5 | 运行 `pixi run test` + `pixi run lint` | - | 质量验收 |

**验收标准**：
- 全量测试通过
- Lint 检查通过
- 无残留的 InMemoryStore/JSON 持久化代码

---

## 七、技术风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| checkpoint 重建消息丢失 thinking_parts | 高 | 低 | 可接受——thinking_parts 是调试信息，非核心 |
| Fork 模式的 `as_node` 选择不当导致执行路径错误 | 中 | 中 | 充分测试 Fork 后的执行路径；降级方案为追加模式 |
| `update_state` 种子化新 thread 可能不完整 | 中 | 中 | 测试各种状态组合；对复杂状态（含 interrupt）做特殊处理 |
| SQLite 并发写入（Streamlit 多线程） | 低 | 中 | 已使用 WAL 模式 + `check_same_thread=False` |
| 经验扫描的 Agent 输出质量不稳定 | 中 | 低 | 用户确认环节兜底，不自动保存 |

### 关于 Fork 模式的降级方案

如果 LangGraph Fork 模式在维修工的复杂 graph（含 interrupt、approval 节点）中表现不稳定，降级方案为：

1. **消息编辑**：不 Fork，而是将编辑后的消息作为新输入追加到当前 thread 末尾
2. **对话复制**：不种子化完整状态，而是只复制 messages 到新 thread

降级方案的功能完整性略低，但实现简单、风险低。

---

## 八、数据迁移方案

### 8.1 旧经验数据迁移

当前 `data/agent_experience.json` 中的经验需要迁移到 SqliteStore。

**迁移逻辑**（在 `ExperienceStore.__init__` 中自动执行）：

```python
def _migrate_from_json(self, json_path: str | Path) -> None:
    json_path = Path(json_path)
    if not json_path.exists():
        return

    with open(json_path) as f:
        data = json.load(f)

    for ns_key, experiences in data.get("namespaces", {}).items():
        ns = tuple(ns_key.split("/"))
        for exp in experiences:
            key = exp.pop("_store_key", f"exp_{uuid.uuid4().hex[:8]}_migrated")
            self._store.put(ns, key, exp)

    # 迁移完成后重命名旧文件
    json_path.rename(json_path.with_suffix(".json.migrated"))
```

### 8.2 旧 thread_id 兼容

当前已有的 `maintenance-{uuid4_hex[:8]}` 格式的 thread_id 在 checkpointer 中有对应的 checkpoint。新增 SessionManager 后，需要为这些旧 thread 创建对应的 session 记录。

**兼容逻辑**：当 `SessionManager.list_sessions()` 返回空列表但 checkpointer 中有 checkpoint 时，自动扫描 checkpoint 并创建 session 记录。

---

## 九、配置变更

### config.yaml 新增项

```yaml
agent:
  checkpoint:
    db_path: "data/agent_checkpoints.db"
  session:
    auto_title_max_length: 20       # 自动标题最大长度
    default_title: "新对话"
    list_limit: 50                  # 历史对话列表最大显示数
  experience:
    scan_max_candidates: 5          # 扫描经验时最多提取的候选数
    categories:                     # 经验类别列表
      - parser_selection
      - chunk_strategy
      - workflow_tip
      - other
  # 移除: experience_persist_path（不再使用 JSON 文件）
```

---

## 十、验收标准总览

### Session 管理验收

| # | 验收项 | 优先级 |
|---|--------|--------|
| S1 | 左侧显示历史对话列表，按更新时间降序 | P0 |
| S2 | 点击历史对话可切换，聊天消息从 checkpoint 恢复 | P0 |
| S3 | 新建对话创建新 session，thread_id 正确 | P0 |
| S4 | 切换 session 后继续聊天，Agent 能正确接续上下文 | P0 |
| S5 | 切换 session 后 interrupt 状态正确恢复 | P0 |
| S6 | 对话复制：通过 `update_state` 种子化新 thread | P1 |
| S7 | 消息编辑与重发：通过 Fork 模式从编辑点重新执行 | P1 |
| S8 | 对话归档与取消归档 | P1 |
| S9 | 对话标题自动提取（首条消息前 20 字符） | P2 |
| S10 | 对话标题手动编辑 | P2 |
| S11 | CLI 支持 session 列表和切换 | P1 |

### 经验持久化验收

| # | 验收项 | 优先级 |
|---|--------|--------|
| E1 | 官方 SqliteStore 替换 InMemoryStore，与 SqliteSaver 共享数据库 | P0 |
| E2 | ExperienceStore 通过官方 SqliteStore 间接操作 | P0 |
| E3 | 旧 JSON 经验自动迁移到 SqliteStore | P0 |
| E4 | 用户说"记住这个经验"时 Agent 调用 save_experience_tool | P0 |
| E5 | Agent 在新对话中自动读取相关经验 | P0 |
| E6 | 经验扫描：Agent 提取候选经验，用户确认后保存 | P1 |
| E7 | 侧边栏经验库列表展示 | P1 |
| E8 | 经验删除 | P2 |
| E9 | 经验按 category/pdf_type 筛选 | P2 |

### 质量验收

| # | 验收项 |
|---|--------|
| Q1 | `pixi run test` 全量测试通过 |
| Q2 | `pixi run lint` 检查通过 |
| Q3 | 无残留的 InMemoryStore/JSON 持久化代码 |
| Q4 | 旧数据迁移后旧文件重命名为 `.migrated` |

---

## 十一、总工作量评估

| Phase | 内容 | 预计工作量 | 风险 |
|-------|------|-----------|------|
| Phase 1 | Session 基础设施 | 6-8 小时 | 低 |
| Phase 2 | Streamlit Session UI | 8-10 小时 | 中（UI 重构 + Fork 模式） |
| Phase 3 | CLI Session 支持 | 2-3 小时 | 低 |
| Phase 4 | ExperienceStore 重构 + SqliteStore 接入 | 3-4 小时 | 低（官方 Store，无需自己实现） |
| Phase 5 | 经验扫描与管理 UI | 4-5 小时 | 中（Agent 输出质量） |
| Phase 6 | 集成测试与收尾 | 3-4 小时 | 低 |
| **总计** | | **26-34 小时** | **中等** |

**建议分 2-3 个对话完成**：
- 对话 1：Phase 1 + Phase 2（Session 基础设施 + UI，核心功能）
- 对话 2：Phase 3 + Phase 4（CLI + ExperienceStore 重构 + 官方 SqliteStore 接入）
- 对话 3：Phase 5 + Phase 6（经验 UI + 测试收尾）

---

## 十二、附录

### A. 关键代码位置速查

| 需求 | 关键代码位置 | 说明 |
|------|-------------|------|
| Session 表创建 | `src/agent/session_manager.py`（新建） | SessionManager 类 |
| Session CRUD | `src/agent/session_manager.py` | create/list/get/update/delete/duplicate |
| Streamlit 对话列表 | `src/app_pages/maintenance.py` 侧边栏 | 左侧历史对话列表 |
| 消息重建 | `src/app_pages/maintenance.py` `_rebuild_messages_from_checkpoint()` | 从 checkpoint 恢复 UI 消息 |
| 消息编辑重发 | `src/app_pages/maintenance.py` `_resend_from_message()` | 基于 LangGraph Fork 模式 |
| Session 复制 | `src/agent/session_manager.py` `duplicate_session()` | 基于 `update_state` 种子化 |
| Session 切换 | `src/app_pages/maintenance.py` `_switch_to_session()` | 切换 thread_id + 重建状态 |
| SqliteStore | `langgraph.store.sqlite`（官方内置） | 官方 SQLite Store，无需自己实现 |
| ExperienceStore | `src/agent/memory/experience_store.py` | 重构为领域层包装器 |
| save_experience_tool | `src/agent/tools.py` | 新增工具 |
| 经验读取 | `src/agent/graph.py` `agent_node` | 修改为调用新 API |
| 经验扫描 | `src/app_pages/maintenance.py` | 扫描按钮 + 确认 UI |
| 数据迁移 | `src/agent/memory/experience_store.py` `_migrate_from_json()` | JSON → SqliteStore |
| 配置 | `config.yaml` `agent.session` + `agent.experience` | 新增配置段 |

### B. LangGraph 官方 API 参考

| API | 用途 | 文档链接 |
|-----|------|---------|
| `graph.get_state(config)` | 获取最新 checkpoint 状态 | /oss/python/langgraph/persistence |
| `graph.get_state_history(config)` | 获取全部 checkpoint 历史 | /oss/python/langgraph/persistence |
| `graph.update_state(config, values, as_node)` | Fork: 创建新分支 | /oss/python/langgraph/use-time-travel |
| `graph.invoke(None, fork_config)` | 从 Fork 点继续执行 | /oss/python/langgraph/use-time-travel |
| `BaseStore.put(namespace, key, value)` | 写入 Store | /oss/python/concepts/memory |
| `BaseStore.search(namespace_prefix, query, filter)` | 搜索 Store（前缀匹配） | /oss/python/concepts/memory |
| `SqliteStore(conn, index=..., ttl=...)` | 官方 SQLite Store（支持语义搜索和 TTL） | langgraph.store.sqlite |
| `InMemoryStore(index={"embed": ..., "dims": N})` | 带向量索引的内存 Store | /oss/python/concepts/memory |

### C. 经验类别定义

| category | 说明 | 示例 |
|----------|------|------|
| `parser_selection` | 解析器选择经验 | "年报表格多时用 fitz+pdfplumber 组合" |
| `chunk_strategy` | 分块策略经验 | "研报用 page_aware + chunk_size=768 效果好" |
| `workflow_tip` | 工作流技巧 | "回退时先诊断再修复，避免跳步" |
| `other` | 其他经验 | "Qdrant 索引重建后需要等待 5 秒" |
