# Phase 3 验收问题修复计划

> 日期：2026-05-05
> 来源：Phase 3 并行开发计划验收发现的 5 个问题

***

## 问题清单

| # | 严重度   | 问题                                                            | 文件                                                                |
| - | ----- | ------------------------------------------------------------- | ----------------------------------------------------------------- |
| 1 | 🔴 高  | `_get_compiled_agent()` 上下文管理器泄漏，SqliteSaver 连接在 `with` 退出后关闭 | `src/app_pages/maintenance.py`                                    |
| 2 | 🟡 中  | 维修报告缺少"最终配置推荐"和"经验记录"两个 section                               | `src/agent/reporters/maintenance_report.py`, `src/agent/tools.py` |
| 3 | 🟡 中  | 对比报告"推荐方案"过于笼统，未根据指标数据自动推荐                                    | `src/agent/reporters/comparison_report.py`                        |
| 4 | 🟡 低  | `agent_node` 中 `build_system_prompt(locked_tool=None)` 硬编码    | `src/agent/graph.py`                                              |
| 5 | 🟢 信息 | `_get_tool_names()` 双重 `cache_clear()`                        | `src/app_pages/maintenance.py`                                    |

***

## 修复步骤

### Fix-1：SqliteSaver 上下文管理器泄漏（🔴 高）

**根因**：`_get_compiled_agent()` 在 `with get_checkpointer() as checkpointer:` 内 `return`，`with` 退出后 SQLite 连接关闭，后续 `agent.invoke()` 使用已关闭的连接会报错。

**调研结论**：`SqliteSaver.__init__(conn: sqlite3.Connection)` 直接接受连接对象，无需上下文管理器。官方文档示例也是直接创建连接传入。

**修复方案**：

修改 `src/app_pages/maintenance.py` 的 `_get_compiled_agent()`：

```python
@st.cache_resource
def _get_compiled_agent():
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.store.memory import InMemoryStore

    from src.agent.config import get_checkpoint_config
    from src.agent.graph import compile_agent

    ckpt_config = get_checkpoint_config()
    db_path = ckpt_config.get("db_path", "data/agent_checkpoints.db")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    store = InMemoryStore()
    return compile_agent(checkpointer=checkpointer, store=store)
```

同时更新 `src/agent/checkpoint.py` 的 `get_checkpointer()`，新增 `get_checkpointer_direct()` 函数返回非上下文管理器的 SqliteSaver（供 Streamlit 等长生命周期场景使用）：

```python
def get_checkpointer_direct(db_path: str | None = None) -> "SqliteSaver":
    """Create a SqliteSaver with a persistent connection (no context manager).

    Suitable for long-lived applications like Streamlit where the
    checkpointer needs to stay alive across multiple invocations.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A SqliteSaver instance with an open connection.
    """
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    if db_path is None:
        from src.agent.config import get_checkpoint_config
        ckpt_config = get_checkpoint_config()
        db_path = ckpt_config.get("db_path", "data/agent_checkpoints.db")

    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing SqliteSaver (direct) at {db_path}")
    conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
    return SqliteSaver(conn)
```

然后 `maintenance.py` 使用 `get_checkpointer_direct()`：

```python
@st.cache_resource
def _get_compiled_agent():
    from langgraph.store.memory import InMemoryStore

    from src.agent.checkpoint import get_checkpointer_direct
    from src.agent.graph import compile_agent

    checkpointer = get_checkpointer_direct()
    store = InMemoryStore()
    return compile_agent(checkpointer=checkpointer, store=store)
```

**测试**：新增 `test_get_checkpointer_direct` 测试。

***

### Fix-2：维修报告缺少"最终配置推荐"和"经验记录"（🟡 中）

**修复方案**：

1. 修改 `src/agent/reporters/maintenance_report.py` 的 `generate()` 方法，在"阶段历史"之后添加两个 section：

   * `## 最终配置推荐`：从 `state.get("config_recommendations", [])` 提取

   * `## 经验记录`：从 `state.get("experiences", [])` 提取

2. 修改 `src/agent/tools.py` 的 `generate_maintenance_report_tool`，新增 `experiences` 和 `config_recommendations` 参数，传入 reporter。

***

### Fix-3：对比报告"推荐方案"过于笼统（🟡 中）

**修复方案**：

修改 `src/agent/reporters/comparison_report.py` 的 `generate()` 方法中的"推荐方案"section，实现基于数值指标的自动推荐逻辑：

* 遍历所有数值型指标，统计每个方案在各项指标上"更优"的次数

* 选择"更优"次数最多的方案作为推荐

* 列出推荐理由（哪些指标更优）

***

### Fix-4：`locked_tool=None` 硬编码（🟡 低）

**修复方案**：

修改 `src/agent/graph.py` 第 143-147 行，将 `locked_tool=None` 改为 `locked_tool=locked_tool`（使用局部变量）。虽然当前逻辑下 `locked_tool` 在此处必为 falsy，但使用变量更清晰且面向未来。

***

### Fix-5：双重 `cache_clear()` （🟢 信息）

**修复方案**：

修改 `src/app_pages/maintenance.py` 的 `_get_tool_names()`，移除第二次 `cache_clear()`。保留第一次 clear 确保获取最新工具列表即可。

***

## 实施顺序

1. Fix-1（🔴 高优先级）→ 修改 checkpoint.py + maintenance.py + 测试
2. Fix-2 + Fix-3（🟡 中优先级，同一模块）→ 修改 reporters + tools.py + 测试
3. Fix-4 + Fix-5（低优先级，快速修复）→ 修改 graph.py + maintenance.py + 测试
4. 运行全量测试 + lint 验证

## 预期提交

| 提交                                                                        | 内容            |
| ------------------------------------------------------------------------- | ------------- |
| `fix: resolve SqliteSaver context manager leak in Streamlit`              | Fix-1         |
| `fix: complete maintenance report sections and comparison recommendation` | Fix-2 + Fix-3 |
| `fix: minor code quality issues in graph.py and maintenance.py`           | Fix-4 + Fix-5 |

