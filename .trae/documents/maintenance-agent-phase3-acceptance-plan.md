# 维修工 Agent Phase 3 深度验收计划

> 日期：2026-05-05
> 范围：Phase 3 新增功能验收 + 上次推迟问题的复查

---

## 一、验收范围

### A. Phase 3 新增功能（T1-T8）

| Task | 内容 | 完成度 |
|------|------|--------|
| T1 | SqliteSaver 持久化 | 95% — WAL 模式未启用 |
| T2 | 维修报告 + 对比报告 | 90% — 报告工具依赖 LLM 传参 |
| T3 | CLI 指令交互完善 | 95% — :review 逻辑分散 |
| T4 | 工具链锁定 | 100% |
| T5 | 轻量/全量双模式 | 0% — 暂缓 |
| T6 | Streamlit 维修工页面 | 80% — interrupt 处理有风险 |
| T7 | 系统提示词优化 | 100% |
| T8 | Phase C 迁移 | 0% — 未实现 |

### B. 上次推迟的问题（6 项）

| 编号 | 问题 | 当前状态 |
|------|------|---------|
| P0-2 | CLI 状态跨 turn 丢失 | 部分解决（SqliteSaver 已集成，但手动同步） |
| P0-3 | 空壳经验自动保存 | 未解决（graph.py L308-316 仍保存 None 值） |
| P1-1 | MaintenanceState 应改 TypedDict | 未解决 |
| P1-4 | collection_name 与 meal 系统冲突 | 部分解决 |
| P1-7 | CLI review 空壳测试 | 未解决（L984-989 仍 assert True） |
| P1-10 | config 缓存 | 已解决（lru_cache） |

---

## 二、发现的问题清单（按严重度排序）

### 🔴 P0 — 必须修复

#### P0-A: Streamlit interrupt 处理可能无法正确恢复

- **文件**: `src/app_pages/maintenance.py` L132-150
- **问题**: interrupt 后显示批准/拒绝按钮，点击后调用 `_resume_interrupt()` + `st.rerun()`。但 Streamlit rerun 后，之前的 `agent.invoke()` 结果已经丢失，interrupt 上下文可能无法恢复。LangGraph 的 interrupt 机制设计用于同步执行流，而 Streamlit 的 rerun 模式会丢失中间状态
- **影响**: 高风险操作的审批流程在 UI 中可能无法正常工作
- **验证方式**: 手动测试——在 Streamlit 中触发高风险操作 → 点击批准 → 检查是否正确恢复执行

#### P0-B: 空壳经验仍在自动保存（P0-3 未解决）

- **文件**: `src/agent/graph.py` L308-316
- **问题**: 保存的经验中 `best_parser`、`best_chunk_strategy`、`best_chunk_size` 仍全是 None
- **影响**: 经验库积累不完整记录，注入 prompt 后可能误导 LLM

### 🟡 P1 — 应该修复

#### P1-A: MaintenanceState 仍为 dict 子类（P1-1 未解决）

- **文件**: `src/agent/state.py`
- **问题**: 继承 dict 而非 TypedDict，类型注解无效。Phase 3 新增了 `locked_tool` 和 `locked_tool_args` 字段，问题加剧
- **影响**: IDE 无类型提示，mypy 无法检查，字段遗漏不会报错

#### P1-B: CLI review 空壳测试（P1-7 未解决）

- **文件**: `tests/test_agent.py` L984-989
- **问题**: `TestCLIReviewCommand` 两个方法只有 `assert True`

#### P1-C: 报告工具依赖 LLM 传参

- **文件**: `src/agent/tools.py` L878-928
- **问题**: `generate_maintenance_report_tool` 要求 LLM 传入 `execution_log`、`stage_history`、`diagnosis` 等参数，但 LLM 无法直接访问 state，只能从对话上下文推断，可能导致报告内容不完整
- **建议**: 让工具从 checkpointer 读取当前 state，而非依赖 LLM 传参

#### P1-D: `_get_tool_names()` 不必要地清除缓存

- **文件**: `src/app_pages/maintenance.py` L13
- **问题**: 每次渲染都调用 `_get_tools.cache_clear()`，抵消 LRU 缓存优势

#### P1-E: Streamlit 双重状态管理

- **文件**: `src/app_pages/maintenance.py` L49-56, L115-128
- **问题**: 同时使用 `st.session_state.maintenance_current_state` 和 SqliteSaver 管理状态，可能导致不一致

#### P1-F: `get_agent_default()` 仍无缓存

- **文件**: `src/agent/config.py` L13-16
- **问题**: 每次调用都重新 `load_config()`。P1-10 标记为"已解决"是因为 `_get_llm` 和 `_get_tools` 有 lru_cache，但 `get_agent_default()` 本身仍无缓存，在 `chunk_parsed_tool` 中被调用 3 次

#### P1-G: `locked_tool` 存在时仍传入 `build_system_prompt()`

- **文件**: `src/agent/graph.py` L146
- **问题**: 当 `locked_tool` 存在时，LLM 不会被调用，但 `build_system_prompt()` 仍被调用并传入 `locked_tool` 参数。这是逻辑冗余，不影响功能

### 🟢 P2 — 建议改进

#### P2-A: 操作时间线缺少时间列

- **文件**: `src/agent/reporters/maintenance_report.py` L36-43
- **问题**: 只有序号和记录，缺少时间戳和工具名列

#### P2-B: `ComparisonReporter.generate()` 推荐逻辑取 max

- **文件**: `src/agent/reporters/comparison_report.py` L105
- **问题**: `best = max(numeric_vals, key=lambda x: x[1])` 假设所有指标越大越好，但某些指标（如延迟、错误率）越小越好

#### P2-C: Streamlit 页面缺少报告展示区域和下载按钮

- **文件**: `src/app_pages/maintenance.py`
- **问题**: 计划要求"报告内容在主区域展示 + 下载按钮"，当前只是将"生成维修报告"作为对话消息发送

#### P2-D: `get_checkpointer_direct()` 未启用 WAL 模式

- **文件**: `src/agent/checkpoint.py` L76
- **问题**: SQLite 默认 journal 模式在高并发写入时性能差，WAL 模式更适合 Streamlit 场景

---

## 三、验收执行步骤

### Step 1: 基线确认
- `pixi run test` 全量通过
- `pixi run lint` 通过

### Step 2: 修复 P0-B（空壳经验）
- 修改 `graph.py` L308-316，在保存经验时从 state 中提取实际使用的 parser/chunk 参数
- 或者：如果无法获取实际参数，暂时关闭自动保存（只在 LLM 显式调用报告工具时保存）

### Step 3: 修复 P1-B（CLI review 空壳测试）
- 补充 `TestCLIReviewCommand` 的实际测试逻辑

### Step 4: 修复 P1-D（_get_tool_names 清缓存）
- 移除 `_get_tools.cache_clear()` 调用

### Step 5: 修复 P1-F（get_agent_default 缓存）
- 给 `get_agent_config()` 加 `@functools.lru_cache`

### Step 6: 修复 P1-G（locked_tool 冗余 prompt）
- 当 `locked_tool` 存在时，跳过 `build_system_prompt()` 调用

### Step 7: 修复 P2-B（ComparisonReporter 推荐逻辑）
- 添加 `higher_is_better` 参数或标注指标方向

### Step 8: 更新 Spec 勘误
- 记录 Phase 3 验收发现

### Step 9: 回归验证
- `pixi run test` + `pixi run lint`

---

## 四、本轮不修复的问题

| 编号 | 问题 | 原因 |
|------|------|------|
| P0-A | Streamlit interrupt 处理 | 需要手动测试验证，且修复涉及 Streamlit 架构重构，风险大 |
| P1-A | MaintenanceState 改 TypedDict | LangGraph 对 TypedDict 的支持需要验证，改错会破坏整个图 |
| P1-C | 报告工具从 checkpointer 读 state | 需要传入 thread_id 和 config，改动较大 |
| P1-E | Streamlit 双重状态管理 | 需要重构 maintenance.py 的状态管理架构 |
| P2-A | 操作时间线加时间列 | 需要在 execution_log 中记录时间戳，改动链路长 |
| P2-C | 报告展示区域和下载 | UI 功能增强，非 bug |
| P2-D | WAL 模式 | 性能优化，非 bug |
