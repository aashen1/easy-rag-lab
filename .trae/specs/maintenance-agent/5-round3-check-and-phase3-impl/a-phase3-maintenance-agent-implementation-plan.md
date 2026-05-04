# Phase 3 实现计划：维修工 Agent UI + 报告 + 生产化

> 基于 `0-maintenance-agent-checklist.md` 中 16 项未完成项
> 日期：2026-05-05
> 目标：将 checklist 完成率从 87% 提升到 \~95%（T5 轻量/全量模式暂缓）

***

## 总览

Phase 3 共 7 个 Task（T5 轻量/全量模式暂缓），按依赖关系分为 4 个批次实施：

| 批次       | Task                               | 依赖    | 预计文件变更      |
| -------- | ---------------------------------- | ----- | ----------- |
| B1 基础设施  | T1 SqliteSaver, T2 报告生成, T3 CLI 增强 | 无     | 6 新建 + 3 修改 |
| B2 状态与逻辑 | T4 工具链锁定                           | T1    | 3 修改        |
| B3 UI    | T6 Streamlit 页面                    | T1-T4 | 2 新建 + 2 修改 |
| B4 迁移与优化 | T7 提示词优化, T8 Phase C 迁移            | 无     | 2 修改        |

> **暂缓项**：T5 轻量/全量双模式切换 — 需求待讨论，不影响其他 Task

***

## B1-T1：Checkpointer 迁移到 SqliteSaver

### 目标

替换 `InMemorySaver` 为 `SqliteSaver`，使维修会话可跨进程恢复。

### 具体步骤

1. **安装依赖**

   ```bash
   pixi add --pypi langgraph-checkpoint-sqlite
   ```

2. **创建** **`src/agent/checkpoint.py`**

   * 工厂函数 `get_checkpointer(db_path: str | None = None) -> SqliteSaver`

   * 默认路径从 `config.yaml` → `agent.checkpoint.db_path` 读取

   * 回退默认值：`data/agent_checkpoints.db`

   * 自动创建 `data/` 目录（如不存在）

   * 使用 `SqliteSaver.from_conn_string(db_path)` 初始化

3. **修改** **`src/agent/cli.py`**

   * 将 `MemorySaver()` 替换为 `get_checkpointer()`

   * 新增 `--session-id` CLI 参数（argparse），覆盖 config 中的 `thread_id`

   * 新增 `--pdf` CLI 参数，自动注入到初始 state 的 `current_source`

4. **修改** **`src/agent/graph.py`**

   * `compile_agent()` 签名不变，checkpointer 由调用方传入

5. **修改** **`config.yaml`**

   * 在 `agent` 段新增：

     ```yaml
     agent:
       checkpoint:
         db_path: "data/agent_checkpoints.db"
     ```

6. **修改** **`src/agent/config.py`**

   * 新增 `get_checkpoint_config()` 函数

7. **测试**

   * 新增 `tests/test_agent_checkpoint.py`

   * 测试 SqliteSaver 创建、会话持久化、跨进程恢复

   * 标记 `@pytest.mark.agent`

### 验收指标

* [ ] `langgraph-checkpoint-sqlite` 已安装

* [ ] `get_checkpointer()` 工厂函数已实现

* [ ] CLI 使用 SqliteSaver 替代 MemorySaver

* [ ] `--session-id` 参数支持会话恢复

* [ ] `--pdf` 参数支持指定目标 PDF

* [ ] config.yaml 新增 `agent.checkpoint.db_path`

* [ ] 测试通过

***

## B1-T2：维修报告与对比报告生成

### 目标

实现两种报告生成能力：维修报告（会话汇总）和对比报告（多方案对比）。

### 具体步骤

1. **创建** **`src/agent/reporters/__init__.py`**

   * 导出 `MaintenanceReporter` 和 `ComparisonReporter`

2. **创建** **`src/agent/reporters/maintenance_report.py`**

   * 类 `MaintenanceReporter`

   * `generate(state: MaintenanceState, session_id: str) -> str` — 生成 Markdown 报告

   * `save(report: str, session_id: str) -> Path` — 保存到 `data/maintenance_reports/`

   * 报告结构：

     ```markdown
     # 维修报告 — {session_id}
     ## 元数据
     - 时间：{timestamp}
     - 目标 PDF：{current_source}
     - 目标 Meal：{current_meal}

     ## 操作时间线
     | # | 时间 | 工具 | 参数 | 结果摘要 |
     |---|------|------|------|----------|

     ## 诊断记录
     {diagnosis 条目}

     ## 关键发现
     {从 messages 中提取的 AI 分析结论}

     ## 最终配置推荐
     {从经验记录中提取}

     ## 经验记录
     {已保存到 ExperienceStore 的经验}
     ```

3. **创建** **`src/agent/reporters/comparison_report.py`**

   * 类 `ComparisonReporter`

   * `add_result(label: str, metrics: dict)` — 添加一组结果

   * `generate() -> str` — 生成 Markdown 对比报告

   * `save(report: str, session_id: str) -> Path` — 保存到 `data/maintenance_reports/`

   * 报告结构：

     ```markdown
     # 对比报告 — {session_id}
     ## 对比维度
     {解析器/分块策略/参数组合}

     ## 指标对比
     | 指标 | 方案 A | 方案 B | 差异 |
     |------|--------|--------|------|
     | 字符数 | ... | ... | ... |
     | 表格数 | ... | ... | ... |
     | 分块数 | ... | ... | ... |

     ## 差异摘要
     {关键差异点高亮}

     ## 推荐方案
     {推荐及理由}
     ```

4. **新增 @tool：`generate_maintenance_report_tool`**

   * 在 `src/agent/tools.py` 新增

   * 调用 `MaintenanceReporter.generate()` + `save()`

   * 返回报告文件路径

5. **新增 @tool：`generate_comparison_report_tool`**

   * 在 `src/agent/tools.py` 新增

   * 接收多组结果数据，调用 `ComparisonReporter`

   * 返回对比报告文件路径

6. **修改** **`src/agent/graph.py`**

   * `_get_tools()` 中添加两个新工具

7. **修改** **`src/agent/prompt.py`**

   * 在"全链路工具"段落中添加报告工具说明

8. **测试**

   * 新增 `tests/test_agent_reporters.py`

   * 测试报告生成、保存、格式正确性

   * 标记 `@pytest.mark.agent`

### 验收指标

* [ ] `MaintenanceReporter` 类已实现

* [ ] `ComparisonReporter` 类已实现

* [ ] 报告保存到 `data/maintenance_reports/`

* [ ] `generate_maintenance_report_tool` @tool 已注册

* [ ] `generate_comparison_report_tool` @tool 已注册

* [ ] 报告格式包含元数据、时间线、发现、推荐

* [ ] 对比报告包含指标对比表、差异摘要、推荐方案

* [ ] 测试通过

***

## B1-T3：CLI 指令交互完善

### 目标

扩展 CLI 指令集，支持快捷操作和会话管理。

### 具体步骤

1. **修改** **`src/agent/cli.py`**

   * 重构为 argparse + 交互循环双层结构

   * 新增 CLI 参数：

     * `--session-id ID`：恢复历史会话（依赖 T1 SqliteSaver）

     * `--pdf PATH`：指定目标 PDF（注入 `current_source`）

   - 新增交互指令：

     * `:parse <parser>` → 构造 `parse_pdf_tool` 调用消息，跳过 LLM 决策

     * `:back <stage>` → 从 `stage_history` 中找到指定阶段，构造回退指令

     * `:compare` → 构造 `generate_comparison_report_tool` 调用消息

     * `:report` → 构造 `generate_maintenance_report_tool` 调用消息

     * `:history` → 显示 `stage_history` 和 `execution_log`

     * `:status` → 显示当前 state 摘要（current\_meal, current\_source, stage\_history）

2. **实现指令→工具调用映射**

   * `:parse pymupdf4llm` → 向 state 追加一条 HumanMessage "请用 pymupdf4llm 解析当前 PDF"

   * `:back chunk` → 向 state 追加一条 HumanMessage "回到分块阶段重新做"

   * `:compare` → 向 state 追加一条 HumanMessage "生成对比报告"

   * `:report` → 向 state 追加一条 HumanMessage "生成维修报告"

   * 这些指令本质上是快捷方式，将用户意图转化为自然语言消息让 LLM 处理

3. **更新启动提示**

   * 显示可用指令列表

4. **测试**

   * 新增 CLI 指令解析测试

   * 标记 `@pytest.mark.agent`

### 验收指标

* [ ] `:parse <parser>` 指令已实现

* [ ] `:back <stage>` 指令已实现

* [ ] `:compare` 指令已实现

* [ ] `:report` 指令已实现

* [ ] `:history` 指令已实现

* [ ] `:status` 指令已实现

* [ ] `--session-id` 参数已实现

* [ ] `--pdf` 参数已实现

* [ ] 启动提示显示可用指令

* [ ] 测试通过

***

## B2-T4：工具链锁定机制

### 目标

用户可通过 UI 或 CLI 锁定工具链，覆盖 LLM 自主决策。

### 具体步骤

1. **修改** **`src/agent/state.py`**

   * 新增字段：`locked_tool: str | None = None`（锁定单个工具名）

   * 新增字段：`locked_tool_args: dict[str, Any] | None = None`（锁定的参数）

2. **修改** **`src/agent/graph.py`**

   * 在 `agent_node` 中检测 `locked_tool`：

     * 如果 `locked_tool` 不为 None，构造一个 AIMessage 包含指定 tool\_call，跳过 LLM 调用

     * 执行后自动清除 `locked_tool` 和 `locked_tool_args`

   * 新增 `locked_agent_node()` 函数处理锁定逻辑

3. **修改** **`src/agent/prompt.py`**

   * 当 `locked_tool` 存在时，提示词中说明"当前用户已锁定工具 XXX，请等待执行结果后再决策"

4. **测试**

   * 新增锁定工具的 graph 集成测试

   * 标记 `@pytest.mark.agent`

### 验收指标

* [ ] `MaintenanceState` 新增 `locked_tool` 和 `locked_tool_args` 字段

* [ ] `agent_node` 检测锁定工具时跳过 LLM 决策

* [ ] 锁定工具执行后自动清除锁定状态

* [ ] 测试通过

***

## B3-T6：Streamlit 维修工页面

### 目标

在现有 Streamlit 应用中新增维修工 Tab，提供可视化交互界面。

### 设计原则

* 遵循现有 `app_pages/` 的 `render_*` 模式

* 使用 `st.tabs()` 在 `app.py` 中注册新 Tab

* 遵循 `.trae/rules/streamlit-api-migration.md` 规则（使用 `st.html()` 而非 `st.components.v1.html`）

### 具体步骤

1. **创建** **`src/app_pages/maintenance.py`**

   * 主函数 `render_maintenance()`

   * 组件结构：

   ```
   ┌─────────────────────────────────────────────┐
   │ 侧边栏                                      │
   │ ┌─────────────────────────────────────────┐ │
   │ │ 🔧 维修工控制面板                        │ │
   │ │                                         │ │
   │ │ 工具链锁定: [自动 ▾ / parse_pdf / ...]  │ │
   │ │  (下拉菜单，选择后锁定指定工具)          │ │
   │ │                                         │ │
   │ │ 自动审查: [开/关] toggle                 │ │
   │ │                                         │ │
   │ │ 快捷操作:                               │ │
   │ │ [生成维修报告] [生成对比报告]            │ │
   │ └─────────────────────────────────────────┘ │
   └─────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────┐
   │ 主区域                                       │
   │ ┌─────────────────────────────────────────┐ │
   │ │ 💬 对话区域                              │ │
   │ │ (st.chat_message + st.chat_input)        │ │
   │ │                                         │ │
   │ │ 用户: 帮我检查 meal_2024 的索引状态      │ │
   │ │ 维修工: [AI 回复]                        │ │
   │ │                                         │ │
   │ │ ⚠️ 高风险操作确认                        │ │
   │ │ [✅ 批准] [❌ 拒绝]                      │ │
   │ └─────────────────────────────────────────┘ │
   │                                             │
   │ ┌──────────────┐ ┌──────────────────────┐   │
   │ │ 📋 执行日志  │ │ 📊 阶段历史          │   │
   │ │ TOOL: xxx    │ │ 1. parse_pdf_tool    │   │
   │ │ TOOL: yyy    │ │ 2. chunk_parsed_tool │   │
   │ └──────────────┘ └──────────────────────┘   │
   └─────────────────────────────────────────────┘
   ```

2. **核心交互逻辑**

   a. **会话初始化**

   * 使用 `@st.cache_resource` 缓存编译后的 agent

   * 使用 SqliteSaver（依赖 T1）实现会话持久化

   * `st.session_state` 管理 thread\_id、auto\_review、locked\_tool 等

   b. **对话交互**

   * `st.chat_input` 接收用户输入

   * 调用 `agent.invoke()` 执行

   * `st.chat_message` 展示 AI 回复

   * 解析 `execution_log` 展示工具调用记录

   c. **Interrupt 处理**

   * 检测 `result.get("__interrupt__")`

   * 展示 interrupt payload（操作名、参数）

   * 提供 `st.button("✅ 批准")` / `st.button("❌ 拒绝")`

   * 用户点击后调用 `agent.invoke(Command(resume=decision))`

   d. **工具链锁定**

   * 侧边栏 `st.selectbox("工具链锁定", ["自动", "parse_pdf_tool", ...])`

   * 选择非"自动"时，设置 `state["locked_tool"]`

   * 依赖 T4 的锁定机制

   e. **报告展示**

   * 侧边栏按钮触发报告生成

   * 报告内容在主区域展示（`st.markdown`）

   * 提供下载按钮

3. **修改** **`src/app.py`**

   * 在 `tab_names` 中添加 `"🔧 维修工"`

   * 导入并调用 `render_maintenance()`

4. **修改** **`src/agent/graph.py`**

   * 确保 `compile_agent()` 可被 Streamlit 缓存调用

   * `_agent_store` 全局变量需改为线程安全

5. **测试**

   * 新增 `tests/test_app_maintenance.py`

   * 使用 `streamlit.testing.v1.AppTest` 框架

   * 测试页面渲染、对话交互、interrupt 处理

### 验收指标

* [ ] `src/app_pages/maintenance.py` 已创建

* [ ] `render_maintenance()` 函数已实现

* [ ] `app.py` 新增维修工 Tab

* [ ] 对话交互（chat\_input + chat\_message）已实现

* [ ] Interrupt 处理（approve/reject 按钮）已实现

- [ ] 工具链锁定下拉菜单已实现

- [ ] 执行日志和阶段历史面板已实现

* [ ] 报告生成和展示已实现

* [ ] 遵循 streamlit-api-migration 规则

* [ ] 测试通过

***

## B4-T7：系统提示词优化

### 目标

多轮迭代优化提示词，提升 Agent 决策质量。

### 具体步骤

1. **修改** **`src/agent/prompt.py`**

   * 添加更多具体示例（解析器选择、分块策略选择、回退场景）

   * 添加约束规则（如"不要连续调用同一工具超过 3 次"）

   * 添加错误处理指导（如"工具调用失败时，先分析错误原因再重试"）

   * 优化经验推荐格式（更结构化）

2. **测试**

   * 更新 `TestBuildSystemPrompt` 测试

### 验收指标

* [ ] 提示词包含具体工具选择示例

* [ ] 提示词包含错误处理指导

* [ ] 提示词包含约束规则

* [ ] 测试通过

***

## B4-T8：实验系统迁移到共享单元（Phase C）

### 目标

将 `parse_all_pdfs_unified()` 内部改为调用 `src/core/ops/parse.py` 的 `parse_pdf()` 共享单元。

### 当前调用链

```
parse_all_pdfs_unified()  [src/parser.py:77]
  └── ParserRegistry.get(algorithm, parser_options).parse(pdf_path)
```

### 目标调用链

```
parse_all_pdfs_unified()  [src/parser.py:77]
  └── parse_pdf(pdf_path, parser_name=algorithm, parser_options=parser_options)  [src/core/ops/parse.py]
       └── ParserRegistry.get_composite().parse(pdf_path)  # 内部实现不变
```

### 具体步骤

1. **修改** **`src/parser.py`**

   * 在 `parse_all_pdfs_unified()` 中，将 `ParserRegistry.get(algorithm, parser_options).parse(pdf_path)` 替换为 `parse_pdf(pdf_path, parser_name=algorithm, parser_options=parser_options)`

   * 注意：`parse_pdf()` 使用 `ParserRegistry.get_composite()`，而原代码使用 `ParserRegistry.get(algorithm)`，需要确认行为一致性

   * 如果 `get_composite()` 与 `get(algorithm)` 行为不同，需要在 `parse_pdf()` 中添加 `parser_name` 参数路由逻辑

2. **验证** **`parse_pdf()`** **兼容性**

   * 确认 `parse_pdf()` 返回的 `ParseResult` 与原代码期望的格式一致

   * 确认 `parse_pdf()` 的 try/except 不影响批量解析的错误处理

3. **类似地检查分块迁移**

   * `process_parsed_files()` / `process_parsed_files_page_aware()` 是否可替换为 `chunk_parsed()`

   * 评估迁移风险，如风险高则暂不迁移

4. **运行全量测试**

   * `pixi run test-all` 确保实验系统测试全部通过

### 验收指标

* [ ] `parse_all_pdfs_unified()` 内部调用 `parse_pdf()` 共享单元

* [ ] 实验系统测试全部通过

* [ ] 无行为回归

***

## 实施顺序与依赖图

```
B1-T1 SqliteSaver ─────────────┐
B1-T2 报告生成 ────────────────┤
B1-T3 CLI 增强 ────────────────┼──→ B3-T6 Streamlit 页面
                                │
B2-T4 工具链锁定 ──────────────┘

B4-T7 提示词优化 ────── (独立)
B4-T8 Phase C 迁移 ──── (独立)
```

**推荐实施顺序**：

1. B1-T1 → B1-T2 → B1-T3（基础设施，可并行）
2. B2-T4（状态逻辑，依赖 T1）
3. B3-T6（UI，依赖 T1-T4）
4. B4-T7 + B4-T8（独立，可在任何时间点实施）

***

## Checklist 完成度预期

实施完成后，以下未完成项将勾选（T5 轻量/全量模式除外）：

| Checklist 章节       | 当前 | 实施后    |
| ------------------ | -- | ------ |
| 0-1.6 C6 轻量/全量双模式  | ⚠️ | ⚠️（暂缓） |
| 0-1.7 C7 LLM 自主决策  | ⚠️ | ✅      |
| 0-1.9 C9 分析报告与维修日志 | ⚠️ | ✅      |
| 0-1.10 C10 用户交互    | ⚠️ | ✅      |
| 0-1.12 C12 高权限操作   | ⚠️ | ✅      |
| 0-2.1 Q1 自主判断程度    | ❌  | ✅      |
| 0-2.3 Q3 交互界面      | ❌  | ✅      |
| 0-3.7 Phase C 迁移   | ❌  | ✅      |
| 0-11.4 Phase 3     | ❌  | 大部分 ✅  |

**预期完成率：\~95%（T5 相关 3 项暂缓）**

***

## 风险与缓解

| 风险                                            | 缓解措施                                  |
| --------------------------------------------- | ------------------------------------- |
| Streamlit 与 LangGraph interrupt 机制集成复杂        | 先在 CLI 验证 interrupt 流程，再迁移到 Streamlit |
| SqliteSaver 在 Windows 上的并发问题                  | 使用 `from_conn_string` + WAL 模式        |
| Phase C 迁移导致实验系统回归                            | 先跑全量测试确认，如有回归则回退                      |
| 工具链锁定与 LLM 决策冲突                               | 锁定只影响单步，执行后自动清除                       |
| Streamlit session\_state 与 LangGraph state 同步 | 使用 thread\_id 作为唯一关联键                 |

