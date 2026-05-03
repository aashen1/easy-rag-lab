# CLI 交互式问答增强：多轮对话 + Case 收集 + 代码搬迁

## 目标

1. 将 `_interactive_qa()` 从根目录 `main.py` 搬迁到 `src/` 下作为独立模块
2. 增加多轮对话支持（对话历史传递给 LLM）
3. 增加 Case 收集斜杠命令，复用 Web UI 的去重逻辑
4. 不重复造轮子，尽可能复用已有后端代码

---

## 现状分析

| 组件 | 当前状态 | 问题 |
|------|---------|------|
| `_interactive_qa()` | 在 `main.py` 根目录，820-923 行 | 位置不合理，应归入 `src/` |
| Case 收集去重 | 仅在 Web UI `_do_save_case()` 中实现 | CLI 未复用，逻辑重复 |
| 多轮对话 | Web UI 仅前端展示，未传 `chat_history` 给 LLM | `Generator.generate()` 无 `chat_history` 参数 |
| `save_case()` | 保存单轮结果，不含对话历史 | 多轮场景下缺少上下文 |
| CLI `/badcase` `/goodcase` | 仅保存最近一条，无去重，无指定轮次 | 功能不完整 |

---

## 实施步骤

### Step 1: 提取 Case 收集去重逻辑为共享函数

**文件**: `src/case_collector.py`

当前 Web UI 的 `_do_save_case()` 包含去重逻辑：
- 已标记为同类型 → 跳过（防重复）
- 已标记为不同类型 → 允许覆盖（badcase → goodcase 转换）

**改造**：在 `case_collector.py` 中新增共享函数 `save_case_with_dedup()`：

```python
def save_case_with_dedup(
    case_type: str,
    question: str,
    result: dict[str, Any],
    config_overrides: dict[str, Any],
    base_config: dict[str, Any],
    meal_config: Any | None = None,
    meal_name: str | None = None,
    chat_history: list[dict[str, Any]] | None = None,
    saved_case_type: str | None = None,
) -> tuple[Path | None, str]:
    """Save case with deduplication logic shared by CLI and Web UI.

    Returns:
        Tuple of (case_dir_path or None, status_message).
        status_message is one of: "saved", "duplicate", "type_changed".
    """
```

- `saved_case_type` 参数：传入当前已保存的类型（`None` / `"bad"` / `"good"`）
- 返回值包含状态，让调用方自行决定如何提示用户
- 内部调用 `save_case()` 执行实际落盘
- 此函数 CLI 和 Web UI 都可调用，消除重复逻辑

### Step 2: `save_case()` 增加可选 `chat_history` 保存

**文件**: `src/case_collector.py`

- `save_case()` 新增可选参数 `chat_history: list[dict[str, Any]] | None = None`
- 当 `chat_history` 非空时，额外写入 `chat_history.json` 到 case 目录
- `manifest.json` 中增加 `has_chat_history: bool` 字段
- `load_case()` 增加读取 `chat_history.json` 的逻辑
- **完全向后兼容**：不传 `chat_history` 时行为不变

### Step 3: `Generator.generate()` 增加 `chat_history` 支持

**文件**: `src/generator.py`

- `generate()` 新增参数 `chat_history: list[dict[str, str]] | None = None`
- `chat_history` 格式: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- 当 `chat_history` 非空时，将其消息拼接到 LLM `messages` 列表中（在当前 user message 之前）
- Anthropic API 要求 messages 以 user 开头且交替，需做格式校验/自动修正
- 更新 docstring

### Step 4: `RAGPipeline.query()` 增加 `chat_history` 支持

**文件**: `src/pipeline.py`

- `query()` 新增参数 `chat_history: list[dict[str, str]] | None = None`
- 透传给 `self.generator.generate(question, contexts, ..., chat_history=chat_history)`
- 更新 docstring

### Step 5: 创建 `src/interactive_qa.py` — CLI 交互式问答模块

**文件**: `src/interactive_qa.py`（新建）

从 `main.py` 的 `_interactive_qa()` 搬迁并增强：

#### 5a. 搬迁核心逻辑

- 将 `_interactive_qa()` 函数移入 `src/interactive_qa.py`
- `main.py` 中改为 `from src.interactive_qa import interactive_qa`，在 `--interactive` 分支调用

#### 5b. 维护对话历史

- 新增 `messages: list[dict[str, Any]]` 列表，结构与 Web UI 一致：
  - 用户消息: `{"role": "user", "content": "问题"}`
  - 助手消息: `{"role": "assistant", "result": {...}, "config_overrides": {...}, "meal_name": "...", "saved_case_type": None}`
- 每次查询后将问答对追加到 `messages`
- 从 `messages` 中提取 `chat_history`（仅 role + content）传给 `pipeline.query()`

#### 5c. 增强斜杠命令

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

#### 5d. Case 收集逻辑

- 调用 `save_case_with_dedup()`，复用共享去重逻辑
- 保存时将当前对话历史一并落盘（`chat_history` 参数）
- 保存成功后更新 `msg["saved_case_type"]`
- 去重行为与 Web UI 完全一致：
  - 同类型重复标记 → 提示"已标记，无需重复"
  - 不同类型覆盖 → 允许（badcase → goodcase 或反之）

#### 5e. 欢迎信息更新

- 显示可用命令列表
- 显示当前 meal 信息

### Step 6: Web UI `qa_demo.py` 改用共享去重函数

**文件**: `src/app_pages/qa_demo.py`

- 将 `_do_save_case()` 改为调用 `save_case_with_dedup()`
- 传递 `chat_history` 给 `pipeline.query()` 和 `save_case_with_dedup()`
- 消除 Web UI 中的去重硬编码，统一使用共享函数

### Step 7: 编写测试

- `tests/test_generator.py`：测试 `chat_history` 传入时 LLM messages 拼接正确，空时向后兼容
- `tests/test_pipeline.py`：测试 `chat_history` 透传给 generator
- `tests/test_case_collector.py`：测试 `save_case_with_dedup()` 去重逻辑、`chat_history` 落盘、`load_case()` 读取
- `tests/test_interactive_qa.py`（新建）：测试命令解析、消息索引、防重复保存

### Step 8: Lint + 测试验证

- `pixi run lint`
- `pixi run test`

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/case_collector.py` | 修改 | 新增 `save_case_with_dedup()`；`save_case()` 增加 `chat_history` 参数；`load_case()` 增加 `chat_history` 读取 |
| `src/generator.py` | 修改 | `generate()` 增加 `chat_history` 参数 |
| `src/pipeline.py` | 修改 | `query()` 增加 `chat_history` 参数，透传给 generator |
| `src/interactive_qa.py` | **新建** | 从 `main.py` 搬迁 `_interactive_qa()` 并增强 |
| `main.py` | 修改 | 删除 `_interactive_qa()`，改为 import 调用 |
| `src/app_pages/qa_demo.py` | 修改 | `_do_save_case()` 改用 `save_case_with_dedup()`；传递 `chat_history` |
| `tests/test_case_collector.py` | 修改 | 追加去重逻辑和 chat_history 测试 |
| `tests/test_generator.py` | 修改 | 追加 chat_history 测试 |
| `tests/test_pipeline.py` | 修改 | 追加 chat_history 透传测试 |
| `tests/test_interactive_qa.py` | **新建** | 命令解析、去重、多轮对话测试 |

---

## 设计决策

1. **共享去重函数 `save_case_with_dedup()`**：从 Web UI 的 `_do_save_case()` 提取核心逻辑，CLI 和 Web UI 共用，避免写两遍
2. **CLI 模块搬迁到 `src/interactive_qa.py`**：与 `src/app_pages/qa_demo.py` 平级，一个管 CLI 交互，一个管 Web 交互
3. **`chat_history` 格式**：`[{"role": "user"/"assistant", "content": "..."}]`，与 Anthropic API messages 格式对齐
4. **斜杠命令支持指定轮次**：`/badcase N` 可标记历史中任意一条，弥补 CLI 无按钮的不足
5. **向后兼容**：所有新增参数均为可选，不传时行为与改造前完全一致
6. **Anthropic API 交替消息约束**：在 `Generator.generate()` 中做自动修正（确保 user/assistant 交替、以 user 开头）
