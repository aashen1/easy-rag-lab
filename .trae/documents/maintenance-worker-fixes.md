# 维修工三 issue 修复计划（修订版）

## 涉及 Issue

| ID                   | 标题                    | 类型     |
| -------------------- | --------------------- | ------ |
| FEAT-20260505-005-w0 | 对话框位置不对，应在最底部         | 布局修复   |
| FEAT-20260505-004-w0 | 异步思考内容显示为原始 JSON，需美化  | 显示优化   |
| FEAT-20260505-006-w0 | 高风险操作确认 UI 重复出现，按钮无响应 | Bug 修复 |

## 修改文件

仅修改 `src/app_pages/maintenance.py`

***

## Issue 1: FEAT-006 — 高风险操作确认 UI 重复（最简单，先修）

### 问题分析

确认 UI 出现在两处：

1. `_render_streaming_agent()` L182-197：流式过程中即时渲染确认按钮
2. `render_maintenance()` L324-354：持久化版本，正常工作

当流式过程中发生 interrupt 时，两处 UI 同时渲染，导致确认框出现两次。用户点掉一个后，另一个留在页面上无法交互。

**根因**：`_render_streaming_agent()` 中的确认按钮在 `if prompt` 块内渲染。当用户点击按钮触发 rerun 时，没有新的 prompt 输入，`if prompt` 块不执行，按钮不存在于新页面上——所以"点了没反应"。而持久化版本在 `if prompt` 块之外，始终存在，能正常工作。

### 修复方案

删除 `_render_streaming_agent()` 中的确认 UI（L185-197），只保留 session state 设置（L183-184）。检测到 interrupt 后立即 `st.rerun()`，让持久化版本接管显示。

### 具体步骤

1. 删除 L185-197 的确认 UI 代码（warning、info、columns、buttons）
2. 保留 L183-184 的 session state 设置
3. 在 L184 之后添加 `st.rerun()`，确保 interrupt 后页面刷新显示持久化确认 UI

***

## Issue 2: FEAT-004 — 异步思考内容美化

### 问题分析

当前 `_render_streaming_agent()` L93-96 和 `_resume_interrupt_streaming()` L451-453：

```python
if msg.content:
    thinking_parts.append({"type": "thinking", "content": msg.content})
```

`msg.content` 在包含 tool\_calls 时是 list of dicts：

```python
[{'text': '嗯，只返回了 1 页内容...', 'type': 'text'},
 {'id': 'call_98ccc6b00c974cde9e5640f9', 'input': {...}, 'name': 'parse_pdf_tool', 'type': 'tool_use'}]
```

直接存入 thinking\_parts 后，`_render_thinking_parts()` 用 `str()` 拼接显示，输出原始 JSON。

### ⚠️ 前次修复的教训

前次修复提取了 `_extract_text_from_content()` 辅助函数，但导致**思考内容与最终回复一模一样**——重复显示。原因：最终 AIMessage 的 content 也被提取为纯文本放入 thinking\_parts，和 `_extract_response_text()` 提取的回复文本完全相同。

### 修复方案（修订）

1. 提取 `_extract_text_from_content(content)` 辅助函数：str 直接返回；list 只提取 `type='text'` 部分，过滤 `type='tool_use'`
2. **关键防重复**：只在 AIMessage **同时包含 tool\_calls** 时，才将其 content 加入 thinking\_parts。不含 tool\_calls 的 AIMessage 是最终回复，不应出现在思考区（它会被 `_extract_response_text()` 单独提取显示）
3. 同样修复 `_resume_interrupt_streaming()` 中的相同逻辑
4. 修复 `_extract_response_text()`：当 `msg.content` 为 list 时，也用辅助函数提取文本
5. 修复 `_render_thinking_parts()`：确保 content 始终为 str（辅助函数已保证）

### 具体步骤

1. 新增 `_extract_text_from_content(content: str | list) -> str` 辅助函数
2. `_render_streaming_agent()` L92-96：改为 `if msg.content and msg.tool_calls:` 条件 + 使用辅助函数
3. `_resume_interrupt_streaming()` L451-453：同上
4. `_extract_response_text()` L525-526：使用辅助函数处理 list 格式的 content

***

## Issue 3: FEAT-005 — 对话框位置修复（改动最大，最后修）

### 问题分析

当前代码流程：

```
L320-322: for msg in maintenance_messages → 渲染历史消息
L324-354: if interrupted → 渲染确认 UI
L356:     if prompt := st.chat_input(...) → 渲染输入框
L359-392: [if prompt 块内] → 渲染当前轮对话
L394-433: 日志/报告/架构图
```

**当前视觉效果**（用户提交了两轮后，无新输入时）：

```
我的第一次输入
维修工第一次输出
我的第二次输入
维修工第二次输出
[输入问题进行诊断...]   ← chat_input
执行日志  阶段历史
维修工架构图
```

**期望视觉效果**：

```
执行日志  阶段历史      ← 移到消息上方
维修报告
我的第一次输入
维修工第一次输出
我的第二次输入
维修工第二次输出
[输入问题进行诊断...]   ← chat_input 在最底部
====
维修工架构图            ← 架构图在输入框下方
```

### ⚠️ 前次修复的教训

前次使用 `on_submit` 回调模式时，**消息历史丢失**——每次只显示最近一条对话。原因：在处理 pending prompt 时，可能**替换**了 `maintenance_messages` 而非**追加**，或在回调中错误地重置了消息列表。

### 修复方案（修订）

使用 `on_submit` 回调模式，但**严格保证消息追加语义**：

1. 新增 `_on_chat_submit()` 回调，仅将 prompt 存入 `st.session_state.maintenance_pending_prompt`
2. 新增 `maintenance_pending_prompt` session state 初始化
3. 页面渲染顺序调整为：
   - 日志/报告（顶部）
   - 所有消息（从 `maintenance_messages` 渲染）
   - 中断确认 UI（持久化版本）
   - pending prompt 处理（追加用户消息 → 调用 agent → agent 追加回复）
   - `st.chat_input`（底部，使用 `on_submit`）
   - 分隔线 + 架构图
4. **防消息丢失关键约束**：
   - 用户消息：`maintenance_messages.append(...)`，绝不用 `= [...]` 替换
   - Agent 回复：`_render_streaming_agent()` 内部已有 `maintenance_messages.append(...)`，保持不变
   - 清空对话按钮：只有此处可以重置 `maintenance_messages`

### 具体步骤

1. 新增 `_on_chat_submit()` 回调函数
2. 新增 `maintenance_pending_prompt` session state 初始化（默认 None）
3. 将日志/报告区块从 L394-423 移到消息渲染之前
4. 将消息渲染循环（L320-322）保持不变
5. 将中断确认 UI（L324-354）保持不变
6. 将 `if prompt` 块替换为 pending prompt 检测：
   - `pending = st.session_state.pop("maintenance_pending_prompt", None)`
   - 如有 pending：追加用户消息到 `maintenance_messages`，渲染用户消息，调用 agent
7. 将 `st.chat_input` 移到 pending prompt 处理之后，改用 `on_submit=_on_chat_submit`
8. 将架构图移到 chat\_input 之后

***

## 执行顺序

1. 先修 FEAT-006（删代码 + 加 rerun）
2. 再修 FEAT-004（辅助函数 + 防重复逻辑）
3. 最后修 FEAT-005（回调模式 + 布局调整 + 防消息丢失）
4. 每步完成后运行 `pixi run lint` 检查
5. 运行 `pixi run test` 验证测试通过

