# 修复 Streamlit 思考过程折叠功能缺陷

## Bug 根因分析

### 问题现象

用户切换"折叠思考过程"开关后，所有已显示的思考过程内容完全消失，即使后端回答完成后也不会重新显示。

### 根因定位

核心问题在 [maintenance.py](file:///b:/project/ash-easy-rag/src/app_pages/maintenance.py) 的数据流设计：

1. **思考内容未持久化**：`thinking_parts` 是 `_render_streaming_agent` 中的局部变量（第 96 行），仅在流式渲染期间存在于内存中。流式渲染结束后，该变量随函数返回而销毁。

2. **消息存储不含思考内容**：流式渲染完成后，只有 `response_text` 被存入 `maintenance_messages`（第 180-182 行），`thinking_parts` 被完全丢弃。

3. **重渲染丢失内容**：当用户切换 toggle 触发 Streamlit rerun 时，页面重新执行，只从 `maintenance_messages` 渲染历史消息（第 363-365 行）。由于消息中不含思考内容，所有思考过程消失。

4. **toggle 行为不当**：当前 toggle 在流式渲染开始时读取一次 `collapse` 值（第 94 行），切换 toggle 会触发 rerun，导致正在进行的流式渲染被中断，且已积累的思考内容因未持久化而丢失。

### 数据流图

```
当前（有 bug）:
  流式渲染 → thinking_parts (局部变量) → 渲染到 thinking_container → 函数结束 → 丢失
  流式完成 → response_text → maintenance_messages → 持久化 ✓
  rerun → 只从 maintenance_messages 渲染 → 思考内容丢失 ✗

修复后:
  流式渲染 → thinking_parts → session_state + thinking_container 实时渲染
  流式完成 → response_text + thinking_parts + thinking_expanded → maintenance_messages → 持久化 ✓
  rerun → 从 maintenance_messages 渲染消息 + 思考内容 → 内容不丢失 ✓
```

## 实施计划

### Step 1: 修改消息数据结构

**文件**: `src/app_pages/maintenance.py`

将 assistant 消息从：

```python
{"role": "assistant", "content": "..."}
```

改为：

```python
{"role": "assistant", "content": "...", "thinking_parts": [...], "thinking_expanded": True/False}
```

* `thinking_parts`: 该消息关联的思考过程列表（复用现有格式）

* `thinking_expanded`: 该消息思考区域的展开/折叠状态

### Step 2: 添加 session state 初始化

在 `render_maintenance()` 的 session state 初始化区域（约第 262 行附近）添加：

```python
if "maintenance_thinking_parts" not in st.session_state:
    st.session_state.maintenance_thinking_parts = []
if "maintenance_streaming" not in st.session_state:
    st.session_state.maintenance_streaming = False
```

* `maintenance_thinking_parts`：流式渲染期间持久化思考内容，防止 rerun 中断导致数据丢失

* `maintenance_streaming`：流式渲染状态标志，用于禁用 sidebar 控件防止误触发 rerun

### Step 3: 修改 `_render_streaming_agent` 函数

**关键改动**：

1. **流式开始时**：设置 `maintenance_streaming = True`，清空 `maintenance_thinking_parts`
2. **收集思考内容时**：同时写入 `st.session_state.maintenance_thinking_parts`（而非仅局部变量）
3. **流式完成后**：将 thinking\_parts 和 thinking\_expanded 一起存入消息字典，设置 `maintenance_streaming = False`

```python
def _render_streaming_agent(agent, state, config):
    collapse = st.session_state.get("maintenance_collapse_thinking", True)
    st.session_state.maintenance_streaming = True
    st.session_state.maintenance_thinking_parts = []
    thinking_parts = st.session_state.maintenance_thinking_parts  # 引用

    # ... 流式循环中，thinking_parts.append() 同时更新 session_state ...

    # 流式完成后
    st.session_state.maintenance_streaming = False
    if response_text:
        st.session_state.maintenance_messages.append({
            "role": "assistant",
            "content": response_text,
            "thinking_parts": list(st.session_state.maintenance_thinking_parts),
            "thinking_expanded": not collapse,  # 新消息的默认状态由 toggle 决定
        })
```

**异常处理**：在 `except` 块中也需设置 `maintenance_streaming = False`，确保状态不卡死。

### Step 4: 修改 `_resume_interrupt_streaming` 函数

同样将 thinking\_parts 持久化到消息字典中，与 Step 3 保持一致。同时管理 `maintenance_streaming` 状态标志。

### Step 5: 修改历史消息渲染逻辑

**当前代码**（第 363-365 行）：

```python
for msg in st.session_state.maintenance_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
```

**修改为**：

```python
for i, msg in enumerate(st.session_state.maintenance_messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("thinking_parts"):
            expanded = msg.get("thinking_expanded", True)
            with st.expander(
                f"💭 思考与工具调用过程 ({len(msg['thinking_parts'])} 步)",
                expanded=expanded,
                key=f"thinking_expander_{i}",
            ):
                _render_thinking_parts(msg["thinking_parts"])
        st.markdown(msg["content"])
```

### Step 6: 修改 toggle 行为及 sidebar 控件禁用

**核心原则**：toggle 仅控制后续新增思考过程的默认显示状态，不影响已有内容。

**流式渲染期间禁用控件**：为 sidebar 中的 toggle、selectbox 等控件添加 `disabled` 参数：

```python
is_streaming = st.session_state.get("maintenance_streaming", False)

collapse_thinking = st.toggle(
    "折叠思考过程",
    value=st.session_state.maintenance_collapse_thinking,
    key="maintenance_collapse_toggle",
    disabled=is_streaming,
)
```

同样为模式选择、工具链锁定、自动审查等控件添加 `disabled=is_streaming`。

**流式期间提示**：在 sidebar 顶部添加状态提示：

```python
if is_streaming:
    st.caption("⏳ Agent 正在思考中，控件暂时禁用...")
```

这样用户在流式渲染期间无法切换 toggle，从根本上避免了 rerun 中断流式渲染的问题。

### Step 7: 添加 Expand All / Collapse All 按钮

在 toggle 下方（约第 301 行之后）添加两个按钮。按钮在流式渲染期间也应禁用：

```python
is_streaming = st.session_state.get("maintenance_streaming", False)

col_expand, col_collapse = st.columns(2)
with col_expand:
    if st.button("📂 展开所有", key="btn_expand_all_thinking", disabled=is_streaming):
        for msg in st.session_state.maintenance_messages:
            if msg["role"] == "assistant" and msg.get("thinking_parts"):
                msg["thinking_expanded"] = True
        keys_to_clear = [k for k in st.session_state if k.startswith("thinking_expander_")]
        for k in keys_to_clear:
            del st.session_state[k]
        st.rerun()

with col_collapse:
    if st.button("📁 折叠所有", key="btn_collapse_all_thinking", disabled=is_streaming):
        for msg in st.session_state.maintenance_messages:
            if msg["role"] == "assistant" and msg.get("thinking_parts"):
                msg["thinking_expanded"] = False
        keys_to_clear = [k for k in st.session_state if k.startswith("thinking_expander_")]
        for k in keys_to_clear:
            del st.session_state[k]
        st.rerun()
```

**关键点**：必须清除 `thinking_expander_*` 的 session state keys，否则 Streamlit 的 widget 状态会覆盖 `expanded` 参数的值。

### Step 8: 更新单元测试

**文件**: `tests/test_app_maintenance.py`

添加以下测试：

1. **test\_thinking\_parts\_persisted\_in\_message**：验证流式渲染完成后，thinking\_parts 被正确存入消息字典
2. **test\_toggle\_does\_not\_affect\_existing\_messages**：验证切换 toggle 不改变已有消息的 thinking\_expanded 状态
3. **test\_expand\_all\_updates\_thinking\_expanded**：验证"展开所有"按钮正确更新所有消息的 thinking\_expanded 为 True
4. **test\_collapse\_all\_updates\_thinking\_expanded**：验证"折叠所有"按钮正确更新所有消息的 thinking\_expanded 为 False

### Step 9: 手动验收测试

通过终端启动 Streamlit 应用，验证以下场景：

1. 发送问题 → 思考过程正常显示 → 切换 toggle → 思考内容不消失
2. 思考过程默认折叠 → 切换 toggle 为展开 → 新消息的思考过程默认展开
3. 点击"展开所有" → 所有思考区域展开
4. 点击"折叠所有" → 所有思考区域折叠
5. 多轮对话中，各消息的思考区域独立控制
6. 流式渲染期间，sidebar 控件显示为禁用状态，无法点击
7. 流式渲染完成后，sidebar 控件恢复可用

## 涉及文件

| 文件                              | 修改类型          |
| ------------------------------- | ------------- |
| `src/app_pages/maintenance.py`  | Bug 修复 + 功能增强 |
| `tests/test_app_maintenance.py` | 新增测试用例        |

## 流式渲染中断问题及应对

### 问题表现

当用户在 Agent 流式输出期间切换 toggle（或点击其他 sidebar 控件）时：

1. **Streamlit 触发 rerun**：toggle 是 Streamlit widget，任何交互都会触发整个脚本重新执行
2. **流式循环被中断**：`agent.stream()` 的 for 循环在下一个 `st.*` 调用时被 Streamlit 检测到 rerun 信号并终止
3. **双重丢失**：

   * `thinking_parts` 是局部变量，随函数中断而丢失

   * `response_text` 尚未存入 `maintenance_messages`，也丢失
4. **无法恢复**：`maintenance_pending_prompt` 已被 `pop()` 消费，rerun 时不会重新启动流式渲染
5. **用户看到**：所有内容突然消失，Agent 似乎"卡住"了

### 应对方案：流式渲染期间禁用控件

最简单有效的方案是：**在流式渲染期间禁用 toggle 和其他非必要 sidebar 控件**，防止用户误触发 rerun。

实现方式：

1. 添加 `maintenance_streaming` session state 标志
2. 流式渲染开始前设为 `True`，完成后设为 `False`
3. 所有 sidebar 控件添加 `disabled=st.session_state.maintenance_streaming`
4. 流式期间显示提示信息"⏳ Agent 正在思考中..."

此方案已纳入 Step 2（session state 初始化）和 Step 3（流式渲染函数修改）中。

## 风险与注意事项

1. **Streamlit expander widget 状态覆盖**：`st.expander` 的 widget state 优先级高于 `expanded` 参数。批量操作时必须清除 widget keys。
2. **向后兼容**：旧格式的消息（不含 `thinking_parts` 字段）需兼容处理，使用 `msg.get("thinking_parts")` 而非 `msg["thinking_parts"]`。
3. **流式中断兜底**：即使禁用了控件，极端情况下（如网络断开）流式仍可能中断。通过持久化 `thinking_parts` 到 session state，中断后已积累的内容不会丢失，但最终回复可能缺失。

