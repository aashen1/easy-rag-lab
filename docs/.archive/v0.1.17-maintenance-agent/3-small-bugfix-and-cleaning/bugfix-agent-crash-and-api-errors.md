# Bugfix Report: Agent 维修工启动与审批流程修复

日期：2026-05-04

## 问题总览

本次验收发现 4 个 bug，其中 2 个阻塞性（崩溃级）、2 个功能级。

| # | 现象 | 严重度 | 根因文件 |
|---|------|--------|----------|
| 1 | `No module named 'src.config'` | 阻塞 | tools.py, graph.py |
| 2 | 输入 n 拒绝高危操作后崩溃 `'ToolMessage' has no attribute 'tool_calls'` | 阻塞 | graph.py |
| 3 | `MealManager` object has no attribute `get_pipeline` | 功能 | tools.py |
| 4 | LLM 提供的 PDF 路径缺少 `data/raw` 前缀导致前两次解析失败 | 功能 | tools.py |

---

## Bug 1：`No module named 'src.config'`

### 现象

```
pixi run agent → 输入任意问题 → ERROR: No module named 'src.config'
```

### 根因

`src/config.py` 从未被创建。agent 模块的 tools.py（7 处）和 graph.py（1 处）均使用 `from src.config import get_config`，这是一个悬空依赖。spec 中规划了 `src/agent/config.py`，但实施时遗漏。

### 修复

将所有 `from src.config import get_config` 替换为项目已有的 `from src.utils import load_config`，`get_config()` → `load_config()`。graph.py 的 `_get_llm()` 额外改用 `get_llm_config(config)` 正确解析 preset + 环境变量，而非直接读 `config.get("llm", {})`。

---

## Bug 2：拒绝高危操作后崩溃

### 现象

```
⚠️ 高风险操作需要确认：rebuild_index
确认执行？(y/n): n
错误: 'ToolMessage' object has no attribute 'tool_calls'
```

### 根因

图结构中 `approval → tools` 是**无条件边**。当用户拒绝操作后：

1. `approval_node` 返回 `[updated_ai, rejected_tool_msg]`，其中 `rejected_tool_msg` 是 ToolMessage
2. 无条件边仍然流向 `tool_node`
3. `tool_node` 取 `state["messages"][-1]`（即 ToolMessage）并调用 `.tool_calls` → 崩溃

即使全部拒绝，`approval_node` 返回空 dict `{}`，图仍流向 `tool_node`，同样崩溃。

### 修复

- 将 `approval → tools` 无条件边改为条件路由 `_route_after_approval`：有待执行的 tool_calls → tools，全部拒绝 → agent（让 LLM 重新决策）
- `tool_node` 增加防御性检查：若最后一条消息不是 AIMessage with tool_calls，返回空消息

---

## Bug 3：`MealManager` 没有 `get_pipeline` 方法

### 现象

```
query_rag_tool failed: 'MealManager' object has no attribute 'get_pipeline'
```

### 根因

`query_rag_tool`、`rebuild_index`、`delete_source` 三个工具均调用 `mgr.get_pipeline(meal_name)`，但 `MealManager` 类不存在此方法。这是实施时的 API 调用错误。

### 修复

改用项目标准的 `RAGPipeline(meal_name=meal_name)` 构建管道：

- `query_rag_tool`：`RAGPipeline(meal_name=...)` + `pipeline.query(question)`
- `rebuild_index`：`RAGPipeline(meal_name=...)` + `pipeline.build_index(rebuild=True)`
- `delete_source`：`RAGPipeline(meal_name=...)` + `pipeline.indexer.delete_by_source(source)`

---

## Bug 4：PDF 路径缺少 `data/raw` 前缀

### 现象

LLM 调用 `parse_pdf_tool("annual_reports/2024/格力电器/2024年年度报告.pdf")` → 文件不存在，前两次解析均失败，第三次 LLM 猜对完整路径后才成功。

### 根因

LLM 无法得知 PDF 文件的根目录前缀，经常省略 `data/raw/`。

### 修复

新增 `_resolve_pdf_path()` 辅助函数：当给定路径不存在时，自动尝试加上 config 中的 `parser.input_dir`（默认 `data/raw`）前缀。应用于 `parse_pdf_tool`、`enhance_page_tool`、`chunk_parsed_tool`。

---

## 修改文件清单

| 文件 | 改动要点 |
|------|---------|
| `src/agent/tools.py` | 替换悬空 import；改用 RAGPipeline；新增 `_resolve_pdf_path` |
| `src/agent/graph.py` | 条件路由替代无条件边；tool_node 防御性检查 |
| `src/agent/cli.py` | 改进响应格式化，倒序查找 AIMessage |
