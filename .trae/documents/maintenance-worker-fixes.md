# 维修工三 issue 修复计划

## 涉及 Issue

| ID                   | 标题                    | 类型     |
| -------------------- | --------------------- | ------ |
| FEAT-20260505-005-w0 | 对话框位置不对，应在最底部         | 布局修复   |
| FEAT-20260505-004-w0 | 异步思考内容显示为原始 JSON，需美化  | 显示优化   |
| FEAT-20260505-006-w0 | 高风险操作确认 UI 重复出现，按钮无响应 | Bug 修复 |

## 修改文件

仅修改 `src/app_pages/maintenance.py`

***

## Issue 1: FEAT-005 — 对话框位置修复

### 问题分析

当前代码流程：

```
L320: for msg in session_state.messages:  → 渲染历史消息（第1轮对话）
L356: if prompt := st.chat_input(...):    → 渲染输入框
L359-392: [if prompt 块内]               → 渲染当前轮对话（第2轮）
L394-433: 日志/报告/架构图
```

**实际视觉效果**（用户提交了两轮后）：

```
我的第一次输入          ← L320 渲染
维修工第一次输出        ← L320 渲染
[输入问题进行诊断...]   ← L356 chat_input 在这里
我的第二次输入          ← L359-361 if prompt 块内渲染
维修工第二次输出        ← L363-392 if prompt 块内渲染
---
执行日志  阶段历史      ← L394-409
维修工架构图            ← L425-433
```

**根因**：`st.chat_input` 返回值触发 `if prompt` 块，新消息在 chat\_input 之后渲染，导致输入框被夹在旧消息和新消息之间。

### 修复方案

使用 `on_submit` 回调模式，将 prompt 存入 session\_state，然后在消息渲染区统一处理：

1. 定义 `_on_chat_submit()` 回调，将 prompt 存入 `st.session_state.maintenance_pending_prompt`
2. 在消息渲染循环之前，检查是否有 pending prompt
3. 如有，先调用 agent 处理，将结果追加到 `maintenance_messages`
4. 统一从 `maintenance_messages` 渲染所有消息
5. 将 `st.chat_input` 移到函数末尾（架构图之后），使用 `on_submit` 回调

**修复后视觉效果**：

```
执行日志  阶段历史      ← 移到消息上方
维修报告
我的第一次输入          ← 统一从 session_state 渲染
维修工第一次输出
我的第二次输入
维修工第二次输出
维修工架构图
[输入问题进行诊断...]   ← chat_input 在最底部
```

### 具体步骤

1. 新增 `_on_chat_submit()` 回调函数
2. 新增 `maintenance_pending_prompt` session state 初始化
3. 在消息渲染循环之前，检测 pending prompt 并调用 agent
4. 将 `st.chat_input` 从 L356 移到函数末尾，改用 `on_submit` 回调
5. 删除原 `if prompt` 块中的内联渲染逻辑
6. 将日志/报告移到消息区上方

***

## Issue 2: FEAT-004 — 异步思考内容美化

### 问题分析

当前 `_render_streaming_agent()` 中 L92-96 处理 AIMessage 时：

```python
if msg.content:
    thinking_parts.append({"type": "thinking", "content": msg.content})
```

`msg.content` 在包含 tool\_calls 时是一个 list of dicts，例如：

```python
[{'text': '嗯，只返回了 1 页内容...', 'type': 'text'},
 {'id': 'call_98ccc6b00c974cde9e5640f9', 'input': {...}, 'name': 'parse_pdf_tool', 'type': 'tool_use'}]
```

直接 `str(msg.content)` 会输出原始 JSON，非常不美观。而 tool\_use 部分实际上已被 L97-105 的 `msg.tool_calls` 单独处理，不应在 thinking 中重复显示。

### 修复方案

1. 解析 `msg.content`：如果是 list，只提取 `type='text'` 的部分拼接显示；如果是 str，直接显示
2. 过滤掉 `type='tool_use'` 的部分（已由 `msg.tool_calls` 处理）
3. 同样修复 `_resume_interrupt_streaming()` 中的相同逻辑（L447-463）

### 具体步骤

* 提取一个 `_extract_text_from_content(content)` 辅助函数，处理 str / list 两种格式

* 在 `_render_streaming_agent()` 和 `_resume_interrupt_streaming()` 中使用该函数替代直接 `msg.content`

***

## Issue 3: FEAT-006 — 高风险操作确认 UI 重复

### 问题分析

确认 UI 出现在两处：

1. `_render_streaming_agent()` L182-197：流式过程中即时渲染，但按钮点击后没有 `st.rerun()`，导致点了没反应
2. `render_maintenance()` L324-354：持久化版本，按钮点击后调用 `_resume_interrupt_streaming()` 并 `st.rerun()`，正常工作

当流式过程中发生 interrupt 时，两处 UI 同时渲染，导致确认框出现两次。

### 修复方案

删除 `_render_streaming_agent()` 中的确认 UI（L182-197），只保留 `render_maintenance()` 中的持久化版本。

流式过程中检测到 interrupt 时，只设置 session state（`maintenance_interrupted` / `maintenance_interrupt_payload`），不渲染按钮。页面继续执行到持久化版本时，自动渲染确认 UI。

### 具体步骤

* 删除 `_render_streaming_agent()` 中 L182-197 的确认 UI 代码

* 保留 L182-184 的 session state 设置逻辑

***

## 执行顺序

1. 先修 FEAT-006（最简单，删代码）
2. 再修 FEAT-004（提取辅助函数，改两处逻辑）
3. 最后修 FEAT-005（回调模式重构 + 布局调整，改动最大）
4. 每步完成后运行 `pixi run lint` 检查
5. 运行 `pixi run test` 验证测试通过

