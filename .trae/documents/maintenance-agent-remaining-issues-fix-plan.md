# 维修工 Agent 遗留问题修复计划书

> 基准文档：`0-initial-plans/maintenance-agent-research-plan.md`
> 生成日期：2026-05-05
> 目的：汇总所有与0号需求计划书不一致的条目，供后续修复使用

---

## 总览

0号需求计划书定义了 12 项核心能力（C1-C12）、5 项设计决策（Q1-Q5）、共享单元层、Meal 体系扩展、LangGraph 工作流等。经逐条验收，以下条目未完全满足需求，按优先级分为三级：

| 优先级 | 数量 | 说明 |
|--------|------|------|
| 🔴 P0 | 4 项 | 需求明确要求但未实现或做错，影响核心功能正确性 |
| 🟡 P1 | 5 项 | 功能增强，影响用户体验或系统一致性 |
| 🟢 P2 | 4 项 | 代码质量或低优先级改进 |

---

## 🔴 P0-1：经验存储不持久化——跨 session 积累能力缺失

### 需求来源

- §1.2 C9："持久化维修日志和笔记，**跨 session 积累经验**"
- §3.2.4 Memory Store："跨 thread 的**长期记忆**，Agent 可以积累经验"
- §1.3 Q5 用户决策："**完整持久化** + 记忆系统 + Issue 集成"

### 当前状态

`ExperienceStore` 使用 LangGraph 的 `InMemoryStore`，进程重启后所有经验丢失。代码结构完整（save/search/get_all 方法都有），但存储后端是内存级的。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/memory/experience_store.py` | 替换 InMemoryStore 为持久化存储 |
| `src/agent/cli.py` | 替换 InMemoryStore 创建逻辑 |
| `src/app_pages/maintenance.py` | 替换 InMemoryStore 创建逻辑 |

### 修复方案

**方案 A（推荐）：使用 SQLite 持久化 Store**

1. 调研 `langgraph-store-sqlite` 或类似包是否可用
2. 如果可用，替换 `InMemoryStore` 为 SQLite-backed Store
3. 配置持久化路径：`data/agent_experience.db`
4. CLI 和 Streamlit 共用同一存储路径

**方案 B：自建 JSON 文件持久化**

1. 在 `ExperienceStore` 中增加 `save_to_file()` 和 `load_from_file()` 方法
2. 持久化路径：`data/agent_experience.json`
3. CLI 启动时加载，每次保存经验时写盘
4. 使用 `tempfile` + `os.replace()` 保证原子性

### 验收标准

- [ ] 经验在进程重启后可恢复
- [ ] CLI 和 Streamlit 使用相同的持久化存储
- [ ] 现有经验检索/保存功能不受影响
- [ ] 测试通过

---

## 🔴 P0-2：白名单硬拦截缺失——安全策略可绕过

### 需求来源

- §1.2 C12："通过备份+**白名单机制**防误删"
- §7.1 风险矩阵："**白名单机制限制危险操作**（如删库）；**禁止 DROP/DELETE 全量操作**"
- §1.3 Q4 用户决策："需要**备份机制 + 白名单**"

### 当前状态

- `FORBIDDEN_OPERATIONS` 只拦截已知危险操作名（`drop_collection`, `delete_all` 等），但 LLM 可以通过连续调用 `delete_source` 逐个删除所有 source，效果等同于删除整个 collection
- `delete_count` 守卫已实现（阈值 3 时强制 interrupt），但仍然是 interrupt 警告而非硬拦截
- `update_meal` 可被反复调用修改 Meal 的所有字段，无频率限制

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/graph.py` | `tool_node` 中增加硬拦截逻辑 |
| `src/agent/state.py` | 已有 `delete_count` 字段 |
| `src/agent/prompt.py` | 增加累计操作影响说明 |

### 修复方案

1. **`delete_source` 累计删除硬拦截**：
   - 当 `delete_count >= 阈值`（默认 3）时，不再只是 interrupt，而是**直接拒绝**并返回错误消息
   - 错误消息："本次会话已删除 {delete_count} 个数据源，为防止误操作，请开启新会话继续"
   - 将 `delete_count` 阈值从 config.yaml 读取（已有 `agent.defaults.delete_count_threshold: 3`）

2. **`update_meal` 字段白名单**：
   - 当前只允许修改 `description` 和 `tags`（代码中已有白名单）
   - 确认白名单完整，不允许修改 `name`、`pdf_files` 等关键字段

3. **prompt 增强**：
   - 在"高风险操作"段落中增加："连续删除多个数据源前，请向用户说明累计影响范围"

### 验收标准

- [ ] `delete_count >= 阈值` 时 `delete_source` 被硬拦截（返回错误，非 interrupt）
- [ ] `update_meal` 字段白名单完整，不允许修改关键字段
- [ ] prompt 包含累计操作影响说明
- [ ] 测试通过

---

## 🔴 P0-3：报告工具依赖 LLM 传参——报告内容可能不完整

### 需求来源

- §1.2 C9："分析报告与维修日志——**持久化维修日志和笔记**"
- §4.2.5 评测单元 / §4.2.4 查询单元：共享单元返回标准化结果
- §6.6 回退与跳转：Agent 记住最优方案

### 当前状态

`generate_maintenance_report_tool` 要求 LLM 传入 `execution_log`、`stage_history`、`diagnosis` 等参数。但 LLM 无法直接访问 state，只能从对话上下文推断，导致：
- 报告内容可能不完整（LLM 可能忘记某些执行日志）
- 报告内容可能不准确（LLM 可能编造或混淆参数）

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/tools.py` | 修改报告工具签名，改为从 checkpointer 读取 state |
| `src/agent/reporters/maintenance_report.py` | `generate()` 改为接收 state dict |
| `src/agent/graph.py` | `tool_node` 中注入 thread_id |
| `src/agent/prompt.py` | 更新报告工具说明 |

### 修复方案

1. **修改 `generate_maintenance_report_tool` 签名**：
   ```python
   @tool
   def generate_maintenance_report_tool(
       thread_id: str | None = None,
       session_id: str | None = None,
   ) -> str:
   ```
   - 内部从 checkpointer 获取当前 state
   - 从 state 中提取 `execution_log`、`stage_history`、`diagnosis`、`current_meal`、`current_source`

2. **修改 `generate_comparison_report_tool` 签名**：类似处理

3. **修改 `MaintenanceReporter.generate()`**：改为接收 `MaintenanceState`（或等价 dict），而非分散参数

4. **修改 `tool_node`**：当执行报告工具时，将当前 `thread_id` 注入 tool_call 的 args

5. **修改 prompt**：在报告工具说明中告知 LLM "调用报告工具时传入当前会话 ID 即可，系统会自动从历史记录中提取完整信息"

### 验收标准

- [ ] 报告工具不再要求 LLM 传入 `execution_log`、`stage_history`、`diagnosis`
- [ ] 报告内容从 checkpointer 读取的 state 中提取
- [ ] 报告内容完整，不依赖 LLM 记忆
- [ ] 测试通过

---

## 🔴 P0-4：Phase C 迁移未做——实验系统与 Agent 走两条并行路径

### 需求来源

- §4.1 核心策略："将现有模块中'恰好适合包装成工具'的部分**抽象为共享单元**，实验系统和 Agent **都调用这些共享单元**"
- §4.5 迁移路径 Phase C："实验系统逐步改为调用共享单元（替换直接调用底层函数）"
- §5.2 修改文件表："`parse_all_pdfs_unified()` 内部改为调用 `parse_pdf()` 共享单元"

### 当前状态

`parse_all_pdfs_unified()` 仍然直接调用 `ParserRegistry.get(algorithm, parser_options).parse(pdf_path)`，不走 `parse_pdf()` 共享单元。存在两条并行调用路径：
- 实验系统：`ParserRegistry.get()` → `parser.parse()`
- Agent：`parse_pdf()` → `ParserRegistry.get_composite()` → `parser.parse()`

如果 `get()` 和 `get_composite()` 行为不一致，可能导致实验系统和 Agent 对同一 PDF 得到不同结果。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/parser.py` | `parse_all_pdfs_unified()` 内部改为调用 `parse_pdf()` |

### 修复方案

1. **验证行为一致性**：
   - 确认 `ParserRegistry.get_composite(primary=algorithm)` 与 `ParserRegistry.get(algorithm)` 对同一 PDF 返回一致结果
   - 如果不一致，在 `parse_pdf()` 中添加路由逻辑

2. **修改 `parse_all_pdfs_unified()`**：
   ```python
   # 原：parser = ParserRegistry.get(algorithm, parser_options)
   #     result = parser.parse(pdf_path)
   # 改：
   from src.core.ops.parse import parse_pdf
   result = parse_pdf(pdf_path, parser_name=algorithm, parser_options=parser_options)
   ```

3. **运行全量测试**：`pixi run test-all` 确保无回归

4. **如果行为不一致**：在 `parse_pdf()` 中添加 `legacy_mode: bool = False` 参数，`parse_all_pdfs_unified()` 传入 `legacy_mode=True` 保持向后兼容

### 验收标准

- [ ] `parse_all_pdfs_unified()` 内部调用 `parse_pdf()` 共享单元
- [ ] 实验系统测试全部通过
- [ ] 无行为回归

---

## 🟡 P1-1：C6 轻量/全量双模式——全量模式逻辑未实现

### 需求来源

- §1.2 C6："轻量模式处理 1-2 个 PDF，**全量模式同现有实验系统**"
- §1.2 C6 用户确认："轻量/全量双模式"
- §9 Phase 2 Task 2.5-2.9：Meal 手动模式 + 全量模式

### 当前状态

- `mode` 字段已加入 `MaintenanceState`（`mode: str`，默认 `"light"`）
- `build_system_prompt(mode=...)` 已根据模式注入不同文字指导
- CLI `--full` 参数已实现
- Streamlit 模式切换已实现
- **但**：全量模式与轻量模式行为完全一样，只是 prompt 多了几句话。没有实际的全量模式行为差异，如：
  - 全量模式下 Agent 应能调用 Meal 批量体系处理完整数据集
  - 全量模式下应有批量解析、批量评测的能力
  - 全量模式下操作影响范围更大，应有更严格的安全守卫

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/graph.py` | `tool_node` 根据 mode 差异化行为 |
| `src/agent/prompt.py` | 全量模式 prompt 增加批量操作指导 |
| `src/agent/state.py` | 可能需要新增字段 |

### 修复方案

**注意**：此需求需要更多设计讨论。全量模式与 Meal 批量体系的深度集成涉及架构决策。

**最小可行方案**：

1. 全量模式下，prompt 中明确告知 LLM 可以使用 `create_curated_meal` + `rebuild_index` 等工具组合实现批量操作
2. 全量模式下，`delete_count` 阈值提高（如 10），允许更多删除操作
3. 全量模式下，自动在开始时列出所有 Meal 和索引状态

**完整方案**（需设计讨论）：

1. 新增批量操作工具（如 `batch_parse_meal`、`batch_evaluate_meal`）
2. 全量模式下 Agent 可调用实验系统的 `ExperimentRunner`
3. 操作影响范围提示增强

### 验收标准

- [ ] 全量模式与轻量模式有实际行为差异
- [ ] 全量模式可处理完整数据集
- [ ] 全量模式有更严格的安全守卫
- [ ] 测试通过

---

## 🟡 P1-2：CLI 快捷指令缺失

### 需求来源

- §1.2 C10："CLI 辅助（调试用，**指令代替按钮**）"
- §5.1 新增文件表：`src/agent/ui/cli.py`——"用指令代替按钮，参考 interactive_qa.py"
- Phase 3 计划 T3：CLI 指令交互完善

### 当前状态

已实现的 CLI 指令：
- `:review on/off` ✅
- `quit/exit` ✅

**未实现的 CLI 指令**：
- `:parse <parser>` — 构造 parse_pdf_tool 调用，跳过 LLM 决策
- `:back <stage>` — 从 stage_history 中找到指定阶段，构造回退指令
- `:compare` — 构造对比报告调用
- `:report` — 构造维修报告调用
- `:history` — 显示 stage_history 和 execution_log
- `:status` — 显示当前 state 摘要
- `:mode light/full` — 切换轻量/全量模式

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/cli.py` | 新增指令解析和执行逻辑 |

### 修复方案

1. **指令→自然语言消息映射**（推荐，简单可靠）：
   - `:parse pymupdf4llm` → 向 state 追加 HumanMessage "请用 pymupdf4llm 解析当前 PDF"
   - `:back chunk` → 向 state 追加 HumanMessage "回到分块阶段重新做"
   - `:compare` → 向 state 追加 HumanMessage "生成对比报告"
   - `:report` → 向 state 追加 HumanMessage "生成维修报告"
   - `:history` → 直接打印 `stage_history` 和 `execution_log`（不调用 LLM）
   - `:status` → 直接打印当前 state 摘要（不调用 LLM）
   - `:mode light/full` → 更新 state 的 `mode` 字段

2. **更新启动提示**：显示可用指令列表

### 验收标准

- [ ] `:parse <parser>` 指令已实现
- [ ] `:back <stage>` 指令已实现
- [ ] `:compare` 指令已实现
- [ ] `:report` 指令已实现
- [ ] `:history` 指令已实现
- [ ] `:status` 指令已实现
- [ ] `:mode light/full` 指令已实现
- [ ] 启动提示显示可用指令
- [ ] 测试通过

---

## 🟡 P1-3：Streamlit interrupt 处理可能无法恢复

### 需求来源

- §3.2.3 Interrupts："`interrupt()` 可在任意节点暂停，等待用户输入后继续"
- §6.5 人工干预流程："用户可以 approve / reject / edit 参数"

### 当前状态

`maintenance.py` 中 interrupt 后的批准/拒绝按钮在 `st.rerun()` 后可能丢失 interrupt 上下文。LangGraph 的 interrupt 机制设计用于同步执行流，而 Streamlit 的 rerun 模式会丢失中间状态。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/app_pages/maintenance.py` | 重构 interrupt 处理逻辑 |

### 修复方案

利用 LangGraph 的 checkpointer 持久化 interrupt 状态：

1. 在 `st.session_state` 中记录 interrupt 状态（`maintenance_interrupted = True`）
2. rerun 后，检测 `maintenance_interrupted`，从 checkpointer 读取当前 state 判断是否仍有 pending interrupt
3. 如果有，重新显示批准/拒绝按钮
4. 批准/拒绝后调用 `agent.invoke(Command(resume=decision), config=config)`

### 验收标准

- [ ] Streamlit interrupt 后批准/拒绝正常工作
- [ ] 页面刷新后 interrupt 状态可恢复
- [ ] 手动测试通过

---

## 🟡 P1-4：MaintenanceState 继承 dict 而非 TypedDict

### 需求来源

- §6.1 维修工 StateGraph：`class MaintenanceState(TypedDict):`
- §5.1 新增文件表：`src/agent/state.py` — `MaintenanceState TypedDict`

### 当前状态

`MaintenanceState` 继承自 `dict` 而非 `TypedDict`。所有类型注解都是摆设——IDE 无提示、mypy 无法检查、字段遗漏不会报错。随着字段增多（现已 13 个），问题加剧。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/state.py` | 改为 TypedDict |
| `tests/test_agent.py` | 适配新定义 |

### 修复方案

1. **先做 spike 验证**：LangGraph 对 TypedDict + `Annotated[list, add_messages]` 的支持
2. 如果通过，修改为：
   ```python
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
3. 使用 `total=False` 使所有字段可选（与 dict 行为一致）
4. 更新所有测试

### 验收标准

- [ ] `MaintenanceState` 改为 TypedDict 子类
- [ ] IDE 类型提示正常工作
- [ ] LangGraph 图编译和执行正常
- [ ] 全量测试通过

---

## 🟡 P1-5：`_agent_store` 全局变量不支持多实例

### 需求来源

- §4.1 核心策略："共享单元是纯函数或近纯函数，**无全局状态副作用**"
- §7.2 回归保护："Agent 代码在 `src/agent/` 独立包中，与现有代码物理隔离"

### 当前状态

`src/agent/graph.py` 使用模块级全局变量 `_agent_store` 存储 store 引用，在 `compile_agent()` 中赋值。如果多个 agent 实例并发运行（如 Streamlit 多用户场景），会互相覆盖。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/graph.py` | 移除全局变量，改用 config 或闭包注入 |

### 修复方案

1. 移除 `_agent_store` 全局变量
2. `agent_node` 和 `tool_node` 通过 LangGraph 的 store 注入机制获取 store（LangGraph 编译时传入 `store` 参数，节点函数通过 `config` 可访问）
3. 更新测试

### 验收标准

- [ ] 移除 `_agent_store` 全局变量
- [ ] store 通过 LangGraph 内置机制注入
- [ ] 多实例并发不冲突
- [ ] 测试通过

---

## 🟢 P2-1：操作时间线缺时间列

### 需求来源

- §1.2 C9："分析报告与维修日志"
- §6.4 工具节点示例：`"parse_time_seconds": metrics.parse_time_seconds`

### 当前状态

`execution_log` 条目是纯文本（如 `"TOOL: parse_pdf_tool"`），不含时间戳和工具名结构化信息。维修报告的操作时间线只有序号和记录文本，缺少时间列。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/graph.py` | `tool_node` 中 `log_entry` 改为 JSON |
| `src/agent/reporters/maintenance_report.py` | 解析 JSON 条目，时间线增加时间列 |

### 修复方案

1. `tool_node` 中 `log_entry` 改为：
   ```python
   log_entry = json.dumps({
       "tool": tool_call["name"],
       "time": datetime.now().isoformat(),
       "status": "ok" if not error else "error",
   }, ensure_ascii=False)
   ```
2. `MaintenanceReporter` 解析 JSON 条目，时间线表格增加"时间"和"工具"列

### 验收标准

- [ ] `execution_log` 条目包含时间戳和工具名
- [ ] 维修报告的操作时间线包含时间列
- [ ] 测试通过

---

## 🟢 P2-2：Streamlit 缺报告展示/下载区域

### 需求来源

- §1.2 C10："Web UI 优先（下拉菜单指定工具链）"
- Phase 3 计划 T6 Streamlit 页面："报告内容在主区域展示 + 下载按钮"

### 当前状态

报告只作为对话消息展示，没有专门的报告展示区域和下载按钮。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/app_pages/maintenance.py` | 新增报告展示区域 |
| `src/agent/tools.py` | 报告工具返回值增加标记 |

### 修复方案

1. 在主区域底部增加报告展示区域
2. 检测 AI 回复中是否包含报告内容（通过工具返回值中的特殊标记）
3. 如果是报告，使用 `st.markdown()` 渲染 + `st.download_button()` 提供下载

### 验收标准

- [ ] 报告在主区域以 Markdown 渲染展示
- [ ] 提供下载按钮
- [ ] 测试通过

---

## 🟢 P2-3：`search_experiences` 方法从未被调用

### 需求来源

- §3.2.4 Memory Store："`store.search(namespace)` 检索相关经验"
- §4.2 ExperienceStore 设计：`search_experiences(namespace, query)` 方法

### 当前状态

`ExperienceStore.search_experiences()` 方法已实现但从未被调用。`agent_node` 使用 `get_all_experiences` 而非 `search_experiences`，因为 `InMemoryStore` 不支持语义搜索。方法保留为未来使用。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/agent/memory/experience_store.py` | 当持久化存储支持搜索时启用 |
| `src/agent/graph.py` | `agent_node` 改用 `search_experiences` |

### 修复方案

1. 当 P0-1（经验持久化）修复后，如果新存储后端支持搜索，将 `agent_node` 中的 `get_all_experiences` 替换为 `search_experiences`
2. 如果新存储后端仍不支持搜索，保持现状，在 docstring 中标注

### 验收标准

- [ ] `search_experiences` 被实际调用，或明确标注为待启用
- [ ] 测试通过

---

## 🟢 P2-4：`evaluate_single` 对中文评测不友好

### 需求来源

- §4.2.5 评测单元：`evaluate_single()` 提供基础指标
- 项目定位：金融研报 RAG 问答系统（中文为主）

### 当前状态

`_word_overlap` 已修复为使用字符 bigram（勘误7），但 `evaluate_single` 整体仍使用简单的词重叠指标（Jaccard + bigram），对中文评测的区分度有限。Phase A 设计为"基础指标"，Phase B/C 计划迁移到完整评测器（BuiltinEvaluator / RagasEvaluator），但至今未迁移。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/core/ops/evaluate.py` | 迁移到 BuiltinEvaluator 或增加更多中文友好指标 |

### 修复方案

1. **最小方案**：在 docstring 中明确标注当前为 Phase A 基础指标，中文场景区分度有限
2. **推荐方案**：迁移到 `BuiltinEvaluator`，但需解决重导入问题（ragas/torch 拖慢启动）
3. **折中方案**：增加更多中文友好指标（如字符级 BLEU、ROUGE-L）

### 验收标准

- [ ] 评测指标对中文有合理区分度
- [ ] 或明确标注为 Phase A 基础指标，待后续迁移
- [ ] 测试通过

---

## 实施顺序建议

按依赖关系和优先级，建议分 4 个批次实施：

```
批次1: P0-2(安全硬拦截) + P0-4(Phase C 迁移)
  ↓
批次2: P0-1(经验持久化) + P0-3(报告工具修复)
  ↓
批次3: P1-1(全量模式) + P1-2(CLI 指令) + P1-3(Streamlit interrupt)
  ↓
批次4: P1-4(TypedDict) + P1-5(全局变量) + P2-x(低优先级)
```

**批次1 理由**：安全硬拦截和 Phase C 迁移互相独立，改动量小，风险低，应最先做。

**批次2 理由**：经验持久化和报告工具修复都涉及存储层变更，P0-1 的持久化存储选型会影响 P0-3 的 checkpointer 读取逻辑。

**批次3 理由**：功能增强，依赖批次1/2 的基础设施。

**批次4 理由**：技术债清理，风险较高（TypedDict 迁移需 spike 验证），优先级最低。

---

## 预期完成率

| 批次 | 完成后 Checklist 覆盖率 |
|------|----------------------|
| 批次1 完成后 | ~93% |
| 批次2 完成后 | ~96% |
| 批次3 完成后 | ~98% |
| 批次4 完成后 | ~99% |

剩余 1% 为 C6 全量模式的完整 Meal 批量体系集成（P1-1 的完整方案，需更多设计讨论）。
