# CLI 交互式问答增强：多轮对话 + Case 收集

## 目标

增强 `main.py` 中的 `_interactive_qa()` 函数，使其具备与 Web UI 一致的多轮对话体验和 badcase/goodcase 收集能力。由于当前 Pipeline 不支持多轮上下文传递，需要从底层开始改造。

## 现状分析

| 层级 | 当前状态 |
|------|---------|
| `Generator.generate()` | 无 `chat_history` 参数，LLM 调用只发单条 user message |
| `RAGPipeline.query()` | 无 `chat_history` 参数，每次查询独立无状态 |
| CLI `_interactive_qa()` | 已有 `/badcase` `/goodcase` 命令（仅保存最近一条），无对话历史维护 |
| Web UI `qa_demo.py` | 前端累积显示消息，但未传 chat_history 给 pipeline |
| `save_case()` | 保存单轮结果，不含对话历史 |

## 实施步骤

### Step 1: Generator 增加 `chat_history` 支持

**文件**: `src/generator.py`

- `generate()` 新增参数 `chat_history: list[dict[str, str]] | None = None`
- `chat_history` 格式: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- 当 `chat_history` 非空时，将其消息拼接到 LLM `messages` 列表中（在当前 user message 之前）
- Anthropic API 要求 messages 以 user 开头且交替，需做格式校验/自动修正
- 更新 docstring

### Step 2: RAGPipeline.query() 增加 `chat_history` 支持

**文件**: `src/pipeline.py`

- `query()` 新增参数 `chat_history: list[dict[str, str]] | None = None`
- 透传给 `self.generator.generate(question, contexts, ..., chat_history=chat_history)`
- 更新 docstring

### Step 3: save_case() 增加可选 `chat_history` 保存

**文件**: `src/case_collector.py`

- `save_case()` 新增可选参数 `chat_history: list[dict[str, Any]] | None = None`
- 当 `chat_history` 非空时，额外写入 `chat_history.json` 到 case 目录
- `manifest.json` 中增加 `has_chat_history: bool` 字段
- `load_case()` 增加读取 `chat_history.json` 的逻辑
- 完全向后兼容：不传 `chat_history` 时行为不变

### Step 4: CLI `_interactive_qa()` 多轮对话 + Case 收集增强

**文件**: `main.py`

#### 4a. 维护对话历史

- 新增 `messages: list[dict[str, Any]]` 列表，结构与 Web UI 一致：
  - 用户消息: `{"role": "user", "content": "问题"}`
  - 助手消息: `{"role": "assistant", "result": {...}, "config_overrides": {...}, "meal_name": "...", "saved_case_type": None}`
- 每次查询后将问答对追加到 `messages`
- 从 `messages` 中提取 `chat_history`（仅 role + content）传给 `pipeline.query()`

#### 4b. 显示对话历史

- 每次新回答后，显示当前对话轮次编号（如 `[Q3]`）
- 不重复打印全部历史（CLI 不像 Web 可以滚动），只在回答前标注轮次

#### 4c. 增强斜杠命令

| 命令 | 说明 |
|------|------|
| `/badcase` | 保存最近一条助手回答为 badcase |
| `/badcase N` | 保存第 N 条助手回答为 badcase（1-indexed） |
| `/goodcase` | 保存最近一条助手回答为 goodcase |
| `/goodcase N` | 保存第 N 条助手回答为 goodcase（1-indexed） |
| `/clear` | 清空对话历史，重新开始 |
| `/history` | 显示对话历史摘要（编号 + 问题预览 + 是否已标记 case） |
| `/help` | 显示所有可用命令 |
| `quit`/`exit`/`q` | 退出（已有） |

#### 4d. Case 收集逻辑

- 与 Web UI 完全一致：调用 `save_case()`，传入 `chat_history`
- 防重复：已标记同类型的消息不再重复保存
- 保存时将当前对话历史一并落盘，便于复现多轮上下文
- 保存成功后更新 `msg["saved_case_type"]`

#### 4e. 欢迎信息更新

- 显示可用命令列表
- 显示当前 meal 信息

### Step 5: Web UI `qa_demo.py` 传递 chat_history

**文件**: `src/app_pages/qa_demo.py`

- 从 `st.session_state.messages` 提取 `chat_history`（role + content/answer）
- 传给 `pipeline.query(question, chat_history=chat_history, config_overrides=...)`
- `_do_save_case()` 调用时传入 `chat_history`

### Step 6: 编写测试

**文件**: `tests/test_generator.py`（新增或追加）

- 测试 `Generator.generate()` 传入 `chat_history` 时 LLM messages 拼接正确
- 测试 `chat_history` 为空时行为不变（向后兼容）

**文件**: `tests/test_pipeline.py`（新增或追加）

- 测试 `RAGPipeline.query()` 传入 `chat_history` 时透传给 generator

**文件**: `tests/test_case_collector.py`（追加）

- 测试 `save_case()` 传入 `chat_history` 时写入 `chat_history.json`
- 测试 `save_case()` 不传 `chat_history` 时行为不变
- 测试 `load_case()` 读取 `chat_history`
- 测试 `manifest.json` 中 `has_chat_history` 字段

**文件**: `tests/test_interactive_qa.py`（新增）

- 测试 `_interactive_qa()` 的命令解析逻辑（提取为可测试的纯函数）
- 测试 `/badcase N`、`/goodcase N` 的消息索引解析
- 测试 `/clear`、`/history` 命令
- 测试防重复保存逻辑

### Step 7: Lint + 测试验证

- `pixi run lint` 确保代码质量
- `pixi run test` 确保所有测试通过

## 设计决策

1. **chat_history 格式**: 采用 `[{"role": "user"/"assistant", "content": "..."}]` 标准格式，与 Anthropic API messages 格式对齐
2. **CLI 命令用斜杠前缀**: `/badcase`、`/goodcase` 等，与现有 CLI 风格一致，避免与普通问题冲突
3. **Case 收集支持指定轮次**: `/badcase N` 可标记历史中任意一条，弥补 CLI 无按钮的不足
4. **对话历史落盘**: Case 中保存 chat_history，确保多轮 badcase 可完整复现
5. **向后兼容**: 所有新增参数均为可选，不传时行为与改造前完全一致
