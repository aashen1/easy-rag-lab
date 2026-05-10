# 维修工 Agent 遗留问题修复 Spec

## Why

维修工 Agent 经逐条验收，发现 13 项与 0 号需求计划书不一致的条目（4 项 P0、5 项 P1、4 项 P2），涉及经验持久化缺失、安全策略可绕过、报告工具依赖 LLM 传参、实验系统与 Agent 双路径并行等核心问题。本 Spec 忠实依据 `maintenance-agent-remaining-issues-fix-plan.md` 撰写，旨在系统性修复所有遗留问题。

## What Changes

### P0（核心功能正确性）

- **P0-1**：经验存储从 `InMemoryStore` 替换为 JSON 文件持久化，跨 session 积累经验
- **P0-2**：`delete_source` 累计删除达到阈值时改为硬拦截（直接拒绝，非 interrupt），prompt 增加累计操作影响说明
- **P0-3**：报告工具改为从 state 自动注入参数，不再依赖 LLM 传入 `execution_log`、`stage_history`、`diagnosis`（当前已有部分实现，需完善并确保 LLM 不传入这些参数时仍能正常工作）
- **P0-4**：`parse_all_pdfs_unified()` 内部改为调用 `parse_pdf()` 共享单元（当前已部分实现，需验证行为一致性）

### P1（功能增强）

- **P1-1**：全量模式增加实际行为差异（批量操作指导、更高删除阈值、自动列出 Meal 状态）
- **P1-2**：CLI 快捷指令完善（`:parse`、`:back`、`:compare`、`:report`、`:history`、`:status`、`:mode` 已有基础实现，需验证完整性）
- **P1-3**：Streamlit interrupt 处理利用 checkpointer 持久化 interrupt 状态，页面刷新后可恢复
- **P1-4**：`MaintenanceState` 从 `dict` 子类改为 `TypedDict` 子类
- **P1-5**：移除 `_agent_store` 全局变量，改用 LangGraph 内置 store 注入机制

### P2（代码质量）

- **P2-1**：`execution_log` 条目改为 JSON 格式（含时间戳和工具名），维修报告时间线增加时间列
- **P2-2**：Streamlit 增加报告展示/下载区域
- **P2-3**：`search_experiences` 方法启用或明确标注为待启用
- **P2-4**：`evaluate_single` 标注为 Phase A 基础指标，中文场景区分度有限

## Impact

- Affected specs: C9（经验持久化）、C12（白名单安全）、C6（全量模式）、C10（CLI 指令）
- Affected code:
  - `src/agent/memory/experience_store.py` — 持久化存储
  - `src/agent/graph.py` — 硬拦截、store 注入、log 格式
  - `src/agent/tools.py` — 报告工具签名
  - `src/agent/state.py` — TypedDict 迁移
  - `src/agent/prompt.py` — 累计操作说明、全量模式指导
  - `src/agent/cli.py` — 持久化 store、指令完善
  - `src/app_pages/maintenance.py` — 持久化 store、interrupt 恢复、报告展示
  - `src/agent/reporters/maintenance_report.py` — JSON log 解析、时间列
  - `src/core/ops/evaluate.py` — Phase A 标注
  - `src/parser.py` — Phase C 迁移验证
  - `tests/test_agent.py` — 适配新定义

---

## ADDED Requirements

### Requirement: P0-1 经验存储持久化

系统 SHALL 将经验数据持久化到磁盘文件，确保进程重启后经验可恢复。

#### Scenario: 经验在进程重启后可恢复
- **WHEN** Agent 保存一条经验到 ExperienceStore
- **AND** 进程重启后创建新的 ExperienceStore 实例（使用相同持久化路径）
- **THEN** 之前保存的经验可通过 `get_all_experiences` 检索到

#### Scenario: CLI 和 Streamlit 使用相同的持久化存储
- **WHEN** CLI 模式保存经验到 `data/agent_experience.json`
- **AND** Streamlit 模式使用相同路径创建 ExperienceStore
- **THEN** 两个入口共享同一份经验数据

#### Scenario: 持久化写入原子性
- **WHEN** 保存经验时进程崩溃或断电
- **THEN** 持久化文件要么是完整的旧版本，要么是完整的新版本，不会出现半写状态

#### Scenario: 现有经验检索/保存功能不受影响
- **WHEN** 使用持久化 ExperienceStore 的 `save_experience`、`search_experiences`、`get_all_experiences` 方法
- **THEN** 行为与 InMemoryStore 版本一致

### Requirement: P0-2 delete_source 累计删除硬拦截

系统 SHALL 在 `delete_count` 达到阈值时硬拦截 `delete_source` 操作，直接返回错误消息而非 interrupt。

#### Scenario: delete_count 达到阈值时硬拦截
- **WHEN** `delete_count >= delete_count_threshold`（默认 3）
- **AND** LLM 尝试调用 `delete_source`
- **THEN** 操作被直接拒绝，返回 ToolMessage 错误："本次会话已删除 {delete_count} 个数据源，为防止误操作，请开启新会话继续"
- **AND** 不触发 interrupt

#### Scenario: delete_count 未达阈值时正常 interrupt
- **WHEN** `delete_count < delete_count_threshold`
- **AND** LLM 尝试调用 `delete_source`
- **THEN** 行为与当前一致（触发 interrupt 警告）

#### Scenario: prompt 包含累计操作影响说明
- **WHEN** 查看 system prompt
- **THEN** 高风险操作段落包含"连续删除多个数据源前，请向用户说明累计影响范围"

### Requirement: P0-3 报告工具不依赖 LLM 传参

系统 SHALL 确保报告工具从 state 自动注入所有必要参数，LLM 只需传入 `session_id`。

#### Scenario: LLM 只传 session_id 生成完整报告
- **WHEN** LLM 调用 `generate_maintenance_report_tool` 只传入 `session_id`
- **THEN** 报告内容完整，包含 execution_log、stage_history、diagnosis、current_meal、current_source 等信息
- **AND** 这些信息从 state 自动注入，不依赖 LLM 记忆

#### Scenario: 报告工具签名不要求 LLM 传入 state 字段
- **WHEN** 查看 `generate_maintenance_report_tool` 的参数定义
- **THEN** `execution_log`、`stage_history`、`diagnosis` 等参数标注为"自动填充，无需提供"

### Requirement: P0-4 Phase C 迁移——实验系统调用共享单元

系统 SHALL 确保实验系统和 Agent 对同一 PDF 得到一致的解析结果。

#### Scenario: parse_all_pdfs_unified 内部调用 parse_pdf 共享单元
- **WHEN** 查看 `parse_all_pdfs_unified()` 的实现
- **THEN** 内部调用 `parse_pdf()` 共享单元而非直接调用 `ParserRegistry.get()`

#### Scenario: 行为一致性验证
- **WHEN** 对同一 PDF 分别通过实验系统和 Agent 调用解析
- **THEN** 得到一致的解析结果

### Requirement: P1-1 全量模式行为差异化

系统 SHALL 在全量模式下提供与轻量模式不同的实际行为。

#### Scenario: 全量模式 prompt 包含批量操作指导
- **WHEN** 以 `mode="full"` 调用 `build_system_prompt`
- **THEN** prompt 包含批量操作指导（如 create_curated_meal + rebuild_index 组合）

#### Scenario: 全量模式删除阈值更高
- **WHEN** 以全量模式运行 Agent
- **THEN** `delete_count_threshold` 高于轻量模式（如 10 vs 3）

#### Scenario: 全量模式自动列出 Meal 状态
- **WHEN** 以全量模式启动会话
- **THEN** Agent 自动列出所有 Meal 和索引状态

### Requirement: P1-2 CLI 快捷指令完整

系统 SHALL 提供完整的 CLI 快捷指令集。

#### Scenario: 所有指令可用
- **WHEN** 在 CLI 中输入 `:parse <parser>`、`:back <stage>`、`:compare`、`:report`、`:history`、`:status`、`:mode light/full`
- **THEN** 每个指令产生预期行为

#### Scenario: 启动提示显示可用指令
- **WHEN** 启动 CLI
- **THEN** 显示所有可用指令列表

### Requirement: P1-3 Streamlit interrupt 状态持久化

系统 SHALL 在 Streamlit 页面刷新后恢复 interrupt 上下文。

#### Scenario: interrupt 后页面刷新可恢复
- **WHEN** Agent 触发 interrupt
- **AND** 用户刷新 Streamlit 页面
- **THEN** 批准/拒绝按钮仍然显示

#### Scenario: 批准/拒绝后正常继续
- **WHEN** 用户在 interrupt 恢复后点击批准或拒绝
- **THEN** Agent 正常继续执行

### Requirement: P1-4 MaintenanceState 改为 TypedDict

系统 SHALL 将 `MaintenanceState` 从 `dict` 子类改为 `TypedDict` 子类，提供类型安全。

#### Scenario: TypedDict 类型提示正常工作
- **WHEN** IDE 打开使用 `MaintenanceState` 的代码
- **THEN** 字段有类型提示和自动补全

#### Scenario: LangGraph 图编译和执行正常
- **WHEN** 使用 TypedDict 版本的 `MaintenanceState` 编译和执行 Agent 图
- **THEN** 行为与 dict 版本一致

### Requirement: P1-5 移除 _agent_store 全局变量

系统 SHALL 通过 LangGraph 内置 store 注入机制获取 store，而非全局变量。

#### Scenario: 多实例并发不冲突
- **WHEN** 两个 Agent 实例并发运行
- **THEN** 各自使用独立的 store，互不干扰

#### Scenario: store 通过 LangGraph 内置机制注入
- **WHEN** 查看 `agent_node` 和 `tool_node` 的实现
- **THEN** store 通过 `config` 参数获取，而非全局变量

### Requirement: P2-1 execution_log 条目结构化

系统 SHALL 将 `execution_log` 条目改为 JSON 格式，包含时间戳和工具名。

#### Scenario: log 条目包含时间戳和工具名
- **WHEN** 工具执行后写入 execution_log
- **THEN** 条目为 JSON 格式，包含 `tool`、`time`、`status` 字段

#### Scenario: 维修报告时间线包含时间列
- **WHEN** 生成维修报告
- **THEN** 操作时间线表格包含"时间"和"工具"列

### Requirement: P2-2 Streamlit 报告展示/下载

系统 SHALL 在 Streamlit 主区域展示报告并提供下载按钮。

#### Scenario: 报告以 Markdown 渲染展示
- **WHEN** Agent 生成维修报告
- **THEN** 报告在主区域以 Markdown 格式渲染展示

#### Scenario: 提供下载按钮
- **WHEN** 报告展示区域可见
- **THEN** 提供下载按钮，点击可下载 .md 文件

### Requirement: P2-3 search_experiences 启用或标注

系统 SHALL 启用 `search_experiences` 方法或明确标注为待启用。

#### Scenario: 持久化存储支持搜索时启用
- **WHEN** P0-1 持久化存储实现后支持搜索
- **THEN** `agent_node` 改用 `search_experiences` 替代 `get_all_experiences`

#### Scenario: 持久化存储不支持搜索时标注
- **WHEN** 持久化存储不支持语义搜索
- **THEN** `search_experiences` 方法 docstring 标注为待启用

### Requirement: P2-4 evaluate_single Phase A 标注

系统 SHALL 在 `evaluate_single` 中明确标注当前为 Phase A 基础指标。

#### Scenario: docstring 标注 Phase A 限制
- **WHEN** 查看 `evaluate_single` 的 docstring
- **THEN** 明确标注"Phase A 基础指标，中文场景区分度有限，待后续迁移到 BuiltinEvaluator"

---

## MODIFIED Requirements

### Requirement: ExperienceStore 持久化后端

原 `ExperienceStore` 使用 `InMemoryStore`，现改为 JSON 文件持久化。接口不变（`save_experience`、`search_experiences`、`get_all_experiences`），但构造函数增加 `persist_path` 参数。

### Requirement: tool_node delete_source 安全策略

原 `tool_node` 在 `delete_count >= threshold` 时触发 interrupt 警告，现改为硬拦截（直接返回错误 ToolMessage）。

### Requirement: generate_maintenance_report_tool 参数

原工具要求 LLM 传入 `execution_log`、`stage_history`、`diagnosis` 等参数，现改为从 state 自动注入（当前已有部分实现，需确保 LLM 不传这些参数时仍正常工作）。

### Requirement: MaintenanceState 类型

原 `MaintenanceState` 继承 `dict`，现改为继承 `TypedDict`。**BREAKING**：所有使用 `MaintenanceState(key=value)` 构造的代码需适配 TypedDict 语法。

### Requirement: execution_log 条目格式

原条目为纯文本（如 `"TOOL: parse_pdf_tool"`），现改为 JSON 格式（如 `{"tool": "parse_pdf_tool", "time": "2026-05-05T10:00:00", "status": "ok"}`）。**BREAKING**：所有解析 execution_log 的代码需适配新格式。

---

## REMOVED Requirements

### Requirement: _agent_store 全局变量

**Reason**：全局变量不支持多实例并发，改用 LangGraph 内置 store 注入机制。
**Migration**：`agent_node` 和 `tool_node` 通过 `config["store"]` 获取 store 实例。
