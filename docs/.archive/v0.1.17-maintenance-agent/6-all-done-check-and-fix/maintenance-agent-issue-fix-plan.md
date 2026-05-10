# 维修工 Agent 问题修复计划

> 日期：2026-05-05
> 基于：从 v0.1.16 至今全部规划文档（0号~Phase3）与代码实现的深度对比审查
> 目标：将 checklist 完成率从 ~90% 提升到 ~98%，修复所有已知设计缺陷和安全漏洞

---

## 问题总览

| 编号 | 问题 | 优先级 | 涉及文件 | 预估改动量 |
|------|------|--------|----------|-----------|
| P0-1 | 安全策略可绕过：连续 delete_source 无限制 | 🔴 高 | graph.py, state.py | 小 |
| P0-2 | 阶段守卫缺失：LLM 可跳过诊断直接修复 | 🔴 高 | graph.py | 小 |
| P0-3 | 报告工具依赖 LLM 传参，内容可能不完整 | 🔴 高 | tools.py, graph.py | 中 |
| P1-1 | C6 轻量/全量双模式完全缺失 | 🟡 中 | state.py, graph.py, prompt.py, cli.py | 中 |
| P1-2 | Phase C 迁移未做：实验系统不走共享单元 | 🟡 中 | parser.py | 小 |
| P1-3 | MaintenanceState 继承 dict 而非 TypedDict | 🟡 中 | state.py, graph.py, 全部测试 | 中 |
| P1-4 | Streamlit interrupt 处理可能无法恢复 | 🟡 中 | maintenance.py | 大 |
| P1-5 | 经验存储为内存级，进程重启后丢失 | 🟡 中 | experience_store.py, cli.py, maintenance.py | 中 |
| P1-6 | `_agent_store` 全局变量不支持多实例 | 🟡 低 | graph.py | 小 |
| P2-1 | 操作时间线缺时间列 | 🟢 低 | maintenance_report.py, graph.py | 小 |
| P2-2 | SqliteSaver 未启用 WAL 模式 | 🟢 低 | checkpoint.py | 极小 |
| P2-3 | Streamlit 缺报告展示/下载区域 | 🟢 低 | maintenance.py | 小 |

---

## 🔴 P0-1：安全策略可绕过——连续 delete_source 无限制

### 问题描述

0号规划 §7.1 和 spec 明确要求"禁止删除整个 Qdrant collection"的硬拦截。当前 `FORBIDDEN_OPERATIONS` 只拦截已知的危险操作名（如 `drop_collection`），但 LLM 可以通过连续调用 `delete_source` 逐个删除所有 source，效果等同于删除整个 collection，安全策略形同虚设。

同理，`update_meal` 可以被反复调用修改 Meal 的所有字段，也没有频率限制。

### 当前代码

```python
# src/agent/graph.py — approval_node
FORBIDDEN_OPERATIONS = {"drop_collection", "delete_all", "clear_index"}
HIGH_RISK_TOOLS = {"rebuild_index", "delete_source", "update_meal", "delete_and_reindex_tool"}
```

`delete_source` 每次调用都需要 interrupt 审批，但审批是逐次的，用户可能不意识到累计效果。

### 修复方案

在 `MaintenanceState` 新增 `delete_count: int` 字段，`tool_node` 执行 `delete_source` 后递增。当 `delete_count` 达到阈值（默认 3）时，强制 interrupt 并展示累计警告。

### 具体步骤

1. **修改 `src/agent/state.py`**
   - 新增字段 `delete_count: int`，默认 `0`

2. **修改 `src/agent/graph.py` 的 `tool_node`**
   - 在工具执行循环中，当 `tool_call["name"] == "delete_source"` 时，检查 `state.get("delete_count", 0)`
   - 如果 `delete_count >= 3`，在执行前插入 interrupt，payload 包含累计删除数量和警告信息
   - 执行成功后，返回 `"delete_count": state.get("delete_count", 0) + 1`

3. **修改 `src/agent/prompt.py`**
   - 在"高风险操作"段落中增加说明："连续删除多个数据源前，请向用户说明累计影响范围"

4. **修改 `src/agent/cli.py`**
   - `current_state` 初始化中增加 `"delete_count": 0`
   - 在 result 同步逻辑中增加 `"delete_count"` 的同步

5. **修改 `src/app_pages/maintenance.py`**
   - `maintenance_current_state` 初始化中增加 `"delete_count": 0`
   - 在 result 同步逻辑中增加 `"delete_count"` 的同步

6. **新增测试**
   - 测试 `delete_count` 字段存在性
   - 测试 `delete_source` 执行后 `delete_count` 递增
   - 测试 `delete_count >= 3` 时触发 interrupt

### 验收标准

- [ ] `MaintenanceState` 包含 `delete_count` 字段
- [ ] `delete_source` 执行后 `delete_count` 递增
- [ ] `delete_count >= 3` 时自动 interrupt，展示累计警告
- [ ] CLI 和 Streamlit 正确同步 `delete_count`
- [ ] 测试通过

---

## 🔴 P0-2：阶段守卫缺失——LLM 可跳过诊断直接修复

### 问题描述

0号规划 §6 画了多节点 StateGraph，每个阶段是独立节点，LLM 不可能跳过某个阶段。实际实现为 ReAct 单节点模式，虽然 prompt 中有"先诊断后操作"的约束，但 LLM 不一定遵守。在实测中，LLM 可能在没有查看 meal 详情、没有检查索引状态的情况下直接调用 `rebuild_index` 或 `delete_source`。

### 修复方案

在 `tool_node` 中加入轻量的"阶段守卫"：如果 LLM 试图在未调用任何诊断工具的情况下直接调用修复工具，自动拒绝并返回提示消息。

### 具体步骤

1. **修改 `src/agent/graph.py`**
   - 在 `tool_node` 函数顶部定义两个集合：
     ```python
     DIAGNOSIS_TOOLS = {"list_meals", "get_meal_detail", "query_rag_tool", "get_index_info", "evaluate_answer_tool"}
     REPAIR_TOOLS = {"rebuild_index", "delete_source", "delete_and_reindex_tool", "update_meal"}
     ```
   - 在工具执行循环中，对每个 `tool_call`：
     - 如果 `tool_call["name"] in REPAIR_TOOLS`：
       - 检查 `state.get("stage_history", [])` 中是否有任何 `DIAGNOSIS_TOOLS` 的记录
       - 如果没有，替换为拒绝 ToolMessage：`"请先进行诊断（查看 meal、检查索引、测试查询），再执行修复操作"`
       - 记录日志 `"GUARD: {tool_name} blocked - no diagnosis performed"`

2. **新增测试**
   - 测试：`stage_history` 为空时，`rebuild_index` 被拒绝
   - 测试：`stage_history` 包含 `list_meals` 后，`rebuild_index` 可执行
   - 测试：`stage_history` 包含 `query_rag_tool` 后，`delete_source` 可执行

### 验收标准

- [ ] 未调用任何诊断工具时，修复工具调用被拒绝
- [ ] 拒绝消息引导 LLM 先进行诊断
- [ ] 已调用诊断工具后，修复工具可正常执行
- [ ] 测试通过

---

## 🔴 P0-3：报告工具依赖 LLM 传参，内容可能不完整

### 问题描述

`generate_maintenance_report_tool` 要求 LLM 传入 `execution_log`、`stage_history`、`diagnosis` 等参数。但 LLM 无法直接访问 state，只能从对话上下文推断，导致：
- 报告内容可能不完整（LLM 可能忘记某些执行日志）
- 报告内容可能不准确（LLM 可能编造或混淆参数）
- 这与 spec 中"汇总本次会话的所有操作记录"的要求矛盾

### 当前代码

```python
# src/agent/tools.py — generate_maintenance_report_tool
@tool
def generate_maintenance_report_tool(
    execution_log: list[str] | None = None,
    stage_history: list[str] | None = None,
    diagnosis: list[dict] | None = None,
    ...
) -> str:
```

### 修复方案

改为从 checkpointer 读取当前 state，而非依赖 LLM 传参。工具接收 `thread_id` 参数，内部通过 checkpointer 获取完整 state。

### 具体步骤

1. **修改 `src/agent/tools.py`**
   - `generate_maintenance_report_tool` 签名改为：
     ```python
     @tool
     def generate_maintenance_report_tool(
         thread_id: str | None = None,
         session_id: str | None = None,
     ) -> str:
     ```
   - 内部逻辑：
     - 从 `src/agent/checkpoint.py` 获取 checkpointer
     - 使用 `checkpointer.get(config)` 读取当前 state
     - 从 state 中提取 `execution_log`、`stage_history`、`diagnosis`、`current_meal`、`current_source`
     - 调用 `MaintenanceReporter.generate(state, session_id)`
   - 类似地修改 `generate_comparison_report_tool`

2. **修改 `src/agent/reporters/maintenance_report.py`**
   - `generate()` 方法改为接收 `MaintenanceState`（或等价 dict），而非分散参数
   - 从 state 中自动提取所有需要的信息

3. **修改 `src/agent/graph.py`**
   - 在 `tool_node` 中，当执行报告工具时，将当前 `thread_id` 注入 tool_call 的 args（如果 LLM 没有传入的话）
   - 或者：在 `agent_node` 的 system prompt 中明确告知 thread_id，让 LLM 传入

4. **修改 `src/agent/prompt.py`**
   - 在"报告生成"工具说明中，明确告知 LLM："调用报告工具时传入当前会话 ID 即可，系统会自动从历史记录中提取完整信息"

5. **更新测试**
   - 测试报告工具不传 `execution_log` 等参数时仍能生成完整报告
   - 测试从 checkpointer 读取 state 的逻辑

### 验收标准

- [ ] 报告工具不再要求 LLM 传入 `execution_log`、`stage_history`、`diagnosis`
- [ ] 报告内容从 checkpointer 读取的 state 中提取
- [ ] 报告内容完整，不依赖 LLM 记忆
- [ ] 测试通过

---

## 🟡 P1-1：C6 轻量/全量双模式完全缺失

### 问题描述

0号规划 §1.2 C6 明确要求"轻量模式处理 1-2 个 PDF，全量模式同现有实验系统"，spec 中有完整 scenario 定义。但至今无任何模式切换逻辑，`--full` 参数不存在。

### 修复方案

在 state 中新增 `mode: Literal["light", "full"]` 字段，prompt 中根据模式注入不同的工作指导，CLI 和 Streamlit 提供切换入口。

### 具体步骤

1. **修改 `src/agent/state.py`**
   - 新增字段 `mode: str`，默认 `"light"`

2. **修改 `src/agent/graph.py`**
   - `agent_node` 将 `mode` 传入 `build_system_prompt(mode=...)`

3. **修改 `src/agent/prompt.py`**
   - `build_system_prompt` 新增 `mode` 参数
   - 当 `mode == "light"` 时，追加：
     ```
     ## 当前模式：轻量模式
     - 仅处理用户指定的 1-2 个 PDF
     - 不触发 Meal 批量体系
     - 专注于单文件精细诊断和修复
     ```
   - 当 `mode == "full"` 时，追加：
     ```
     ## 当前模式：全量模式
     - 可调用 Meal 批量体系处理完整数据集
     - 可使用 create_curated_meal 创建新的 Meal
     - 注意：全量操作影响范围大，执行前务必确认
     ```

4. **修改 `src/agent/cli.py`**
   - 新增 `--full` CLI 参数，设置 `mode="full"`
   - 新增 `:mode light` / `:mode full` 交互指令

5. **修改 `src/app_pages/maintenance.py`**
   - 侧边栏新增模式切换 toggle 或 selectbox
   - 切换时更新 `st.session_state.maintenance_mode`

6. **修改 `config.yaml`**
   - `agent.defaults` 新增 `mode: "light"` 默认值

7. **新增测试**
   - 测试 `mode` 字段存在性
   - 测试 `build_system_prompt(mode="light")` 包含轻量模式说明
   - 测试 `build_system_prompt(mode="full")` 包含全量模式说明
   - 测试 CLI `--full` 参数

### 验收标准

- [ ] `MaintenanceState` 包含 `mode` 字段
- [ ] `build_system_prompt` 根据 `mode` 注入不同指导
- [ ] CLI 支持 `--full` 参数
- [ ] Streamlit 支持模式切换
- [ ] 测试通过

---

## 🟡 P1-2：Phase C 迁移未做——实验系统不走共享单元

### 问题描述

0号规划 §4.5 定义了四步迁移路径（A→B→C→D），目前只完成了 A 和 B。`parse_all_pdfs_unified()` 仍然直接调用 `ParserRegistry.get()`，不走 `parse_pdf()` 共享单元，存在两条并行调用路径。

### 当前代码

```python
# src/parser.py — parse_all_pdfs_unified()
parser = ParserRegistry.get(algorithm, parser_options)
result = parser.parse(pdf_path)
```

### 目标代码

```python
# src/parser.py — parse_all_pdfs_unified()
from src.core.ops.parse import parse_pdf
result = parse_pdf(pdf_path, parser_name=algorithm, parser_options=parser_options)
```

### 具体步骤

1. **验证 `parse_pdf()` 与 `ParserRegistry.get()` 的行为一致性**
   - `parse_pdf()` 内部使用 `ParserRegistry.get_composite(primary=parser_name)`
   - `parse_all_pdfs_unified()` 使用 `ParserRegistry.get(algorithm, parser_options)`
   - 需要确认：对于同一个 `algorithm` 值，`get_composite(primary=algorithm)` 和 `get(algorithm)` 返回的 parser 行为是否一致
   - 如果不一致，需要在 `parse_pdf()` 中添加路由逻辑

2. **修改 `src/parser.py`**
   - 在 `parse_all_pdfs_unified()` 中，将 `ParserRegistry.get(algorithm, parser_options).parse(pdf_path)` 替换为 `parse_pdf(pdf_path, parser_name=algorithm, parser_options=parser_options)`
   - 注意处理 `enhancer_name` 参数：原代码没有增强器，`parse_pdf()` 的 `enhancer_name` 默认为 None，行为一致

3. **运行全量测试**
   - `pixi run test-all` 确保实验系统测试全部通过
   - 特别关注解析相关的集成测试

4. **如果步骤1发现不一致**
   - 在 `parse_pdf()` 中添加 `legacy_mode: bool = False` 参数
   - 当 `legacy_mode=True` 时使用 `ParserRegistry.get()` 而非 `get_composite()`
   - `parse_all_pdfs_unified()` 传入 `legacy_mode=True` 保持向后兼容

### 验收标准

- [ ] `parse_all_pdfs_unified()` 内部调用 `parse_pdf()` 共享单元
- [ ] 实验系统测试全部通过
- [ ] 无行为回归

---

## 🟡 P1-3：MaintenanceState 继承 dict 而非 TypedDict

### 问题描述

0号规划 §6.1 明确定义 `MaintenanceState` 为 `TypedDict`，但实际实现为 `class MaintenanceState(dict)`。所有类型注解都是摆设——IDE 无提示、mypy 无法检查、字段遗漏不会报错。随着字段增多（现已 10+ 个），问题加剧。

### 当前代码

```python
# src/agent/state.py
class MaintenanceState(dict):
    messages: Annotated[list, add_messages]
    current_meal: str | None
    ...
```

### 修复方案

先写 spike 验证 LangGraph 对 TypedDict + `Annotated[list, add_messages]` 的支持，确认后迁移。

### 具体步骤

1. **Spike：验证 LangGraph TypedDict 兼容性**
   - 创建临时测试文件，验证以下场景：
     - `StateGraph(TypedDict子类)` 能否正常编译
     - `Annotated[list, add_messages]` reducer 是否正常工作
     - `state["key"]` 和 `state.get("key")` 访问是否正常
     - 新增字段是否有默认值问题（TypedDict 无默认值机制）
   - 如果验证失败，考虑使用 `dataclass` 或保留 `dict` 子类但添加 `__init__` 方法

2. **如果 spike 通过，修改 `src/agent/state.py`**
   ```python
   from typing import Annotated, Any, TypedDict
   from langgraph.graph.message import add_messages

   class MaintenanceState(TypedDict, total=False):
       messages: Annotated[list, add_messages]
       current_meal: str
       current_source: str
       diagnosis: list[dict[str, Any]]
       pending_action: dict[str, Any]
       approved: bool
       execution_log: list[str]
       stage_history: list[str]
       auto_review: bool
       locked_tool: str
       locked_tool_args: dict[str, Any]
       delete_count: int
       mode: str
   ```
   - 使用 `total=False` 使所有字段可选（与 dict 行为一致）

3. **更新所有测试**
   - 搜索所有 `MaintenanceState(` 构造调用，确保传入的参数名与字段名一致
   - 搜索所有 `state["key"]` 和 `state.get("key")` 访问，确保字段名正确

4. **运行全量测试**
   - `pixi run test-all` 确保无回归

### 验收标准

- [ ] `MaintenanceState` 改为 `TypedDict` 子类
- [ ] IDE 类型提示正常工作
- [ ] LangGraph 图编译和执行正常
- [ ] 全量测试通过

---

## 🟡 P1-4：Streamlit interrupt 处理可能无法恢复

### 问题描述

`maintenance.py` 中 interrupt 后的批准/拒绝按钮在 `st.rerun()` 后可能丢失 interrupt 上下文。LangGraph 的 interrupt 机制设计用于同步执行流，而 Streamlit 的 rerun 模式会丢失中间状态。

### 当前代码

```python
# src/app_pages/maintenance.py L131-149
if result.get("__interrupt__"):
    ...
    if st.button("✅ 批准"):
        _resume_interrupt(agent, config, True, result)
        st.rerun()  # ← rerun 后 interrupt 上下文可能丢失
```

### 修复方案

利用 LangGraph 的 checkpointer 持久化 interrupt 状态。interrupt 后不依赖内存中的 result，而是从 checkpointer 恢复。

### 具体步骤

1. **修改 `src/app_pages/maintenance.py` 的 interrupt 处理逻辑**
   - 不再在 rerun 后依赖 `result` 变量
   - 改为：在 `st.session_state` 中记录 interrupt 状态（`maintenance_interrupted = True`）
   - rerun 后，检测 `maintenance_interrupted`，从 checkpointer 读取当前 state 判断是否仍有 pending interrupt
   - 如果有，重新显示批准/拒绝按钮

2. **具体实现**
   ```python
   # 在 session_state 初始化中增加：
   if "maintenance_interrupted" not in st.session_state:
       st.session_state.maintenance_interrupted = False

   # 在主渲染逻辑中：
   if st.session_state.maintenance_interrupted:
       # 从 checkpointer 检查是否仍有 pending interrupt
       agent = _get_compiled_agent()
       config = {"configurable": {"thread_id": st.session_state.maintenance_thread_id}}
       state_snapshot = agent.get_state(config)
       if state_snapshot.next:  # 仍有待执行节点
           # 显示 interrupt UI
           ...
       else:
           st.session_state.maintenance_interrupted = False

   # 在 interrupt 发生时：
   st.session_state.maintenance_interrupted = True

   # 在批准/拒绝后：
   agent.invoke(Command(resume=decision), config=config)
   st.session_state.maintenance_interrupted = False
   st.rerun()
   ```

3. **手动测试**
   - 在 Streamlit 中触发高风险操作
   - 点击批准，检查是否正确恢复执行
   - 点击拒绝，检查是否正确回退
   - 刷新页面后，检查是否正确恢复 interrupt 状态

### 验收标准

- [ ] Streamlit interrupt 后批准/拒绝正常工作
- [ ] 页面刷新后 interrupt 状态可恢复
- [ ] 手动测试通过

---

## 🟡 P1-5：经验存储为内存级，进程重启后丢失

### 问题描述

0号规划 §1.2 C9 要求"跨 session 积累经验"，§3.2.4 Memory Store 部分也强调跨 session 的长期记忆。但当前使用 `InMemoryStore`，进程重启后所有经验丢失，与需求矛盾。

### 修复方案

将 `InMemoryStore` 替换为基于 SQLite 的持久化存储，或至少在进程退出时序列化到磁盘。

### 具体步骤

1. **方案 A：使用 LangGraph 的持久化 Store（推荐）**
   - 检查 `langgraph-store-sqlite` 或类似包是否可用
   - 如果可用，替换 `InMemoryStore` 为 SQLite-backed Store
   - 配置持久化路径：`data/agent_experience.db`

2. **方案 B：自建 JSON 文件持久化**
   - 在 `ExperienceStore` 中增加 `save_to_file()` 和 `load_from_file()` 方法
   - 持久化路径：`data/agent_experience.json`
   - CLI 启动时加载，每次保存经验时写盘
   - 使用 `tempfile` + `os.replace()` 保证原子性

3. **修改 `src/agent/cli.py`**
   - 替换 `InMemoryStore()` 为持久化 Store
   - 或在启动时从文件加载经验

4. **修改 `src/app_pages/maintenance.py`**
   - 同上

5. **新增测试**
   - 测试经验持久化：保存→重启→读取
   - 测试并发安全（如果使用 SQLite）

### 验收标准

- [ ] 经验在进程重启后可恢复
- [ ] CLI 和 Streamlit 使用相同的持久化存储
- [ ] 测试通过

---

## 🟡 P1-6：`_agent_store` 全局变量不支持多实例

### 问题描述

`src/agent/graph.py` 使用模块级全局变量 `_agent_store` 存储 store 引用，在 `compile_agent()` 中赋值。如果多个 agent 实例并发运行（如 Streamlit 多用户场景），会互相覆盖。

### 当前代码

```python
# src/agent/graph.py L15
_agent_store = None

# compile_agent() 中：
global _agent_store
_agent_store = store
```

### 修复方案

通过 LangGraph 的 `config` 机制注入 store，而非全局变量。

### 具体步骤

1. **修改 `src/agent/graph.py`**
   - 移除 `_agent_store` 全局变量
   - `agent_node` 和 `tool_node` 通过 `config` 参数获取 store：
     ```python
     def agent_node(state: MaintenanceState, *, config: dict) -> dict:
         store = config.get("configurable", {}).get("__store__")
         # 或使用 LangGraph 的 store 注入机制
     ```
   - 检查 LangGraph 是否支持通过 `config` 传递自定义对象
   - 如果不支持，使用 `functools.partial` 或闭包在 `compile_agent()` 中绑定 store

2. **更新测试**
   - 测试多个 agent 实例使用不同 store 时互不干扰

### 验收标准

- [ ] 移除 `_agent_store` 全局变量
- [ ] store 通过 config 或闭包注入
- [ ] 多实例并发不冲突
- [ ] 测试通过

---

## 🟢 P2-1：操作时间线缺时间列

### 问题描述

`MaintenanceReporter.generate()` 生成的操作时间线只有序号和记录文本，缺少时间戳和工具名列，不利于事后分析。

### 修复方案

在 `execution_log` 中记录时间戳和工具名，报告生成时提取展示。

### 具体步骤

1. **修改 `src/agent/graph.py` 的 `tool_node`**
   - 将 `log_entry` 从 `"TOOL: {tool_name}"` 改为包含时间戳的 JSON 字符串：
     ```python
     import json
     from datetime import datetime
     log_entry = json.dumps({
         "tool": tool_call["name"],
         "time": datetime.now().isoformat(),
         "status": "ok" if observation != f"Error: {e}" else "error",
     }, ensure_ascii=False)
     ```

2. **修改 `src/agent/reporters/maintenance_report.py`**
   - 解析 `execution_log` 中的 JSON 条目
   - 时间线表格增加"时间"和"工具"列

3. **更新测试**

### 验收标准

- [ ] `execution_log` 条目包含时间戳和工具名
- [ ] 维修报告的操作时间线包含时间列
- [ ] 测试通过

---

## 🟢 P2-2：SqliteSaver 未启用 WAL 模式

### 问题描述

`src/agent/checkpoint.py` 的 `get_checkpointer_direct()` 创建 SqliteSaver 时未启用 WAL 模式。SQLite 默认 journal 模式在高并发写入时性能差，WAL 模式更适合 Streamlit 场景。

### 具体步骤

1. **修改 `src/agent/checkpoint.py`**
   - 在创建连接后执行 `PRAGMA journal_mode=WAL`：
     ```python
     import sqlite3
     conn = sqlite3.connect(db_path)
     conn.execute("PRAGMA journal_mode=WAL")
     ```
   - 注意：`SqliteSaver.from_conn_string()` 可能不接受自定义连接，需要检查 API
   - 如果 `from_conn_string` 不支持，改用 `SqliteSaver(conn)` 直接传入连接

2. **新增测试**
   - 验证 WAL 模式已启用

### 验收标准

- [ ] SqliteSaver 使用 WAL 模式
- [ ] 测试通过

---

## 🟢 P2-3：Streamlit 缺报告展示/下载区域

### 问题描述

Phase 3 计划要求"报告内容在主区域展示 + 下载按钮"，当前只是将"生成维修报告"作为对话消息发送，没有专门的报告展示区域。

### 具体步骤

1. **修改 `src/app_pages/maintenance.py`**
   - 在主区域底部增加报告展示区域
   - 检测 AI 回复中是否包含报告内容（通过特殊标记或工具返回值）
   - 如果是报告，使用 `st.markdown()` 渲染 + `st.download_button()` 提供下载

2. **修改 `src/agent/tools.py`**
   - 报告工具返回值增加 `__report__` 标记，便于 Streamlit 识别

3. **新增测试**

### 验收标准

- [ ] 报告在主区域以 Markdown 渲染展示
- [ ] 提供下载按钮
- [ ] 测试通过

---

## 实施顺序建议

按依赖关系和优先级，建议分 4 个批次实施：

### 批次 1：安全加固（P0-1 + P0-2）

这两个改动都只涉及 `graph.py` 和 `state.py`，互相独立，可以一起做。改动量小，风险低。

### 批次 2：报告工具修复（P0-3）

涉及 `tools.py`、`reporters/`、`graph.py`，改动量中等。需要先完成 P0-1（因为 state 新增了 `delete_count` 字段）。

### 批次 3：功能补全（P1-1 + P1-2）

轻量/全量模式和 Phase C 迁移互相独立，可以并行。P1-1 涉及多个文件但改动量可控，P1-2 改动量极小但需要验证行为一致性。

### 批次 4：技术债清理（P1-3 + P1-4 + P1-5 + P1-6 + P2-x）

这些改动风险较高或优先级较低，建议放在最后。P1-3（TypedDict 迁移）需要先做 spike 验证。P1-4（Streamlit interrupt）需要手动测试。P1-5（经验持久化）需要调研 LangGraph 生态的持久化方案。

```
批次1: P0-1 + P0-2 ──→ 批次2: P0-3 ──→ 批次3: P1-1 + P1-2 ──→ 批次4: P1-3~P1-6 + P2-x
```

---

## 预期完成率

| 修复后 | Checklist 完成率 |
|--------|-----------------|
| 批次 1 完成后 | ~92% |
| 批次 2 完成后 | ~94% |
| 批次 3 完成后 | ~96% |
| 批次 4 完成后 | ~98% |

剩余 2% 为 C6 全量模式的完整 Meal 批量体系集成（需要更多设计讨论）。
