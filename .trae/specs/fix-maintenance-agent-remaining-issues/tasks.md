# Tasks

## 批次 1：P0-2（安全硬拦截）+ P0-4（Phase C 迁移）

互相独立，改动量小，风险低，应最先做。

- [x] Task 1: P0-2 delete_source 累计删除硬拦截
  - [x] Task 1.1: 修改 `src/agent/graph.py` 的 `tool_node`，当 `delete_count >= get_delete_count_threshold()` 时，将 `delete_source` 的 interrupt 改为硬拦截——直接返回 ToolMessage 错误（"本次会话已删除 {delete_count} 个数据源，为防止误操作，请开启新会话继续"），不触发 interrupt
  - [x] Task 1.2: 确认 `src/agent/prompt.py` 中高风险操作段落已包含"连续删除多个数据源前，请向用户说明累计影响范围"（当前已有，验证即可）
  - [x] Task 1.3: 确认 `update_meal` 字段白名单完整（当前 `allowed_fields = {"description", "tags"}`，不允许修改 `name`、`pdf_files` 等关键字段）
  - [x] Task 1.4: 在 `tests/test_agent.py` 中新增测试：验证 `delete_count >= threshold` 时 `delete_source` 被硬拦截（返回错误 ToolMessage，非 interrupt）
  - [x] Task 1.5: 运行 `pixi run test` 确保无回归

- [x] Task 2: P0-4 Phase C 迁移——验证 parse_all_pdfs_unified 已调用 parse_pdf 共享单元
  - [x] Task 2.1: 验证 `src/parser.py` 中 `parse_all_pdfs_unified()` 内部已调用 `parse_pdf()` 共享单元（当前代码已使用 `from src.core.ops.parse import parse_pdf` 并调用 `parse_pdf(pdf_path, parser_name=algorithm, parser_options=parser_options or {})`）
  - [x] Task 2.2: 验证 `ParserRegistry.get_composite(primary=algorithm)` 与 `ParserRegistry.get(algorithm)` 对同一 PDF 返回一致结果（当不传 enhancer_name 时，`parse_pdf` 走 `ParserRegistry.get()` 路径，行为与直接调用一致）
  - [x] Task 2.3: 运行 `pixi run test` 确保无回归

## 批次 2：P0-1（经验持久化）+ P0-3（报告工具修复）

都涉及存储层变更，P0-1 的持久化存储选型会影响 P0-3 的 checkpointer 读取逻辑。

- [x] Task 3: P0-1 经验存储持久化
  - [x] Task 3.1: 在 `src/agent/memory/experience_store.py` 中实现 JSON 文件持久化方案：增加 `persist_path` 参数，新增 `_save_to_file()` 和 `_load_from_file()` 方法，使用 `tempfile` + `os.replace()` 保证原子性写入
  - [x] Task 3.2: 修改 `ExperienceStore.__init__` 接受可选的 `persist_path` 参数；当提供时，初始化时从文件加载已有经验，每次保存时写盘
  - [x] Task 3.3: 修改 `src/agent/cli.py`，将 `InMemoryStore()` 替换为持久化 ExperienceStore（路径 `data/agent_experience.json`）
  - [x] Task 3.4: 修改 `src/app_pages/maintenance.py`，将 `InMemoryStore()` 替换为持久化 ExperienceStore（路径 `data/agent_experience.json`）
  - [x] Task 3.5: 在 `tests/test_agent.py` 中新增测试：验证经验在"保存→重新加载→检索"后可恢复
  - [x] Task 3.6: 在 `tests/test_agent.py` 中新增测试：验证持久化写入原子性（文件不会出现半写状态）
  - [x] Task 3.7: 运行 `pixi run test` 确保无回归

- [x] Task 4: P0-3 报告工具修复——确保不依赖 LLM 传参
  - [x] Task 4.1: 验证 `src/agent/graph.py` 的 `tool_node` 中 `generate_maintenance_report_tool` 的 state 注入逻辑（当前已有 `tool_args.setdefault` 实现，验证完整性）
  - [x] Task 4.2: 验证 `src/agent/tools.py` 中 `generate_maintenance_report_tool` 的参数 docstring 明确标注"自动填充，无需提供"（当前已有，验证即可）
  - [x] Task 4.3: 验证 `src/agent/prompt.py` 中报告工具说明告知 LLM "调用报告工具时传入当前会话 ID 即可，系统会自动从历史记录中提取完整信息"（当前已有，验证即可）
  - [x] Task 4.4: 确认 `generate_comparison_report_tool` 是否也需要类似处理（当前该工具需要 LLM 传入 `results` 列表，这是合理的设计——对比报告需要 LLM 提供对比数据）
  - [x] Task 4.5: 在 `tests/test_agent.py` 中验证现有 `TestReportToolStateInjection` 测试通过
  - [x] Task 4.6: 运行 `pixi run test` 确保无回归

## 批次 3：P1-1（全量模式）+ P1-2（CLI 指令）+ P1-3（Streamlit interrupt）

功能增强，依赖批次 1/2 的基础设施。

- [x] Task 5: P1-1 全量模式行为差异化
  - [x] Task 5.1: 修改 `src/agent/config.py`，新增 `get_full_mode_delete_threshold()` 函数，返回全量模式的删除阈值（默认 10）
  - [x] Task 5.2: 修改 `src/agent/graph.py` 的 `tool_node`，根据 `state.get("mode")` 使用不同的删除阈值
  - [x] Task 5.3: 修改 `src/agent/prompt.py`，全量模式 prompt 增加批量操作指导（如 create_curated_meal + rebuild_index 组合、批量解析和评测能力说明）
  - [x] Task 5.4: 修改 `src/agent/graph.py` 的 `agent_node`，全量模式下自动在 system prompt 中注入当前所有 Meal 和索引状态摘要
  - [x] Task 5.5: 在 `tests/test_agent.py` 中新增测试：验证全量模式使用更高的删除阈值
  - [x] Task 5.6: 在 `tests/test_agent.py` 中新增测试：验证全量模式 prompt 包含批量操作指导
  - [x] Task 5.7: 运行 `pixi run test` 确保无回归

- [x] Task 6: P1-2 CLI 快捷指令完善
  - [x] Task 6.1: 验证 `src/agent/cli.py` 中 `_handle_cli_command` 已实现 `:parse`、`:back`、`:compare`、`:report`、`:history`、`:status`、`:mode` 指令（当前已有基础实现，验证完整性）
  - [x] Task 6.2: 验证 CLI 启动提示显示所有可用指令（当前已有，验证完整性）
  - [x] Task 6.3: 验证 `:mode light/full` 在主循环中正确处理（当前已有 `if user_input.startswith(":mode")` 分支，验证完整性）
  - [x] Task 6.4: 验证 `:history` 和 `:status` 直接打印 state 信息（不调用 LLM）
  - [x] Task 6.5: 在 `tests/test_agent.py` 中验证现有 `TestCLICommands` 测试覆盖所有指令
  - [x] Task 6.6: 运行 `pixi run test` 确保无回归

- [x] Task 7: P1-3 Streamlit interrupt 状态持久化
  - [x] Task 7.1: 修改 `src/app_pages/maintenance.py`，在 `st.session_state` 中记录 interrupt 状态（`maintenance_interrupted = True`）
  - [x] Task 7.2: 修改 `src/app_pages/maintenance.py`，rerun 后检测 `maintenance_interrupted`，从 checkpointer 读取当前 state 判断是否有 pending interrupt
  - [x] Task 7.3: 修改 `src/app_pages/maintenance.py`，如果有 pending interrupt，重新显示批准/拒绝按钮
  - [x] Task 7.4: 修改 `src/app_pages/maintenance.py`，批准/拒绝后调用 `agent.invoke(Command(resume=decision), config=config)` 并清除 interrupt 状态
  - [x] Task 7.5: 手动测试 Streamlit interrupt 恢复流程
  - [x] Task 7.6: 运行 `pixi run test` 确保无回归

## 批次 4：P1-4（TypedDict）+ P1-5（全局变量）+ P2-x（低优先级）

技术债清理，风险较高（TypedDict 迁移需 spike 验证），优先级最低。

- [x] Task 8: P1-4 MaintenanceState 改为 TypedDict
  - [x] Task 8.1: Spike 验证——创建临时测试文件，验证 LangGraph 对 `TypedDict + Annotated[list, add_messages]` 的支持（图编译、节点执行、state 更新）
  - [x] Task 8.2: 如果 spike 通过，修改 `src/agent/state.py`，将 `MaintenanceState` 从 `dict` 子类改为 `TypedDict(total=False)` 子类
  - [x] Task 8.3: 更新 `tests/test_agent.py` 中所有 `MaintenanceState(...)` 构造调用，适配 TypedDict 语法
  - [x] Task 8.4: 运行 `pixi run test` 确保无回归
  - [x] Task 8.5: 如果 spike 不通过，记录原因并在 state.py 中添加注释说明限制

- [x] Task 9: P1-5 移除 _agent_store 全局变量
  - [x] Task 9.1: 修改 `src/agent/graph.py`，移除 `_agent_store` 全局变量
  - [x] Task 9.2: 修改 `agent_node`，通过 LangGraph 的 store 注入机制（`config.get("store")` 或函数签名中的 `store` 参数）获取 store
  - [x] Task 9.3: 修改 `tool_node`，同样通过注入机制获取 store
  - [x] Task 9.4: 修改 `compile_agent`，移除 `global _agent_store` 赋值
  - [x] Task 9.5: 更新 `tests/test_agent.py` 中涉及 `_agent_store` 的测试
  - [x] Task 9.6: 运行 `pixi run test` 确保无回归

- [x] Task 10: P2-1 execution_log 条目结构化
  - [x] Task 10.1: 修改 `src/agent/graph.py` 的 `tool_node`，将 `log_entry` 从纯文本改为 JSON 格式：`json.dumps({"tool": tool_call["name"], "time": datetime.now().isoformat(), "status": "ok" or "error"}, ensure_ascii=False)`
  - [x] Task 10.2: 修改 `src/agent/reporters/maintenance_report.py`，解析 JSON 条目，时间线表格增加"时间"和"工具"列
  - [x] Task 10.3: 更新 `tests/test_agent.py` 中涉及 `execution_log` 格式的测试
  - [x] Task 10.4: 运行 `pixi run test` 确保无回归

- [x] Task 11: P2-2 Streamlit 报告展示/下载
  - [x] Task 11.1: 修改 `src/agent/tools.py`，报告工具返回值增加特殊标记（如 `[REPORT_START]` / `[REPORT_END]`）
  - [x] Task 11.2: 修改 `src/app_pages/maintenance.py`，在主区域底部增加报告展示区域，检测 AI 回复中的报告标记
  - [x] Task 11.3: 如果是报告，使用 `st.markdown()` 渲染 + `st.download_button()` 提供下载
  - [x] Task 11.4: 运行 `pixi run test` 确保无回归

- [x] Task 12: P2-3 search_experiences 启用或标注
  - [x] Task 12.1: 评估 P0-1 持久化存储是否支持搜索；如果支持，修改 `agent_node` 将 `get_all_experiences` 替换为 `search_experiences`
  - [x] Task 12.2: 如果不支持搜索，确认 `search_experiences` 方法 docstring 已标注为待启用（当前已有标注，验证即可）
  - [x] Task 12.3: 运行 `pixi run test` 确保无回归

- [x] Task 13: P2-4 evaluate_single Phase A 标注
  - [x] Task 13.1: 修改 `src/core/ops/evaluate.py` 的 `evaluate_single` docstring，明确标注"Phase A 基础指标，中文场景区分度有限，待后续迁移到 BuiltinEvaluator"
  - [x] Task 13.2: 运行 `pixi run test` 确保无回归

# Task Dependencies

- Task 3 (P0-1 经验持久化) → Task 12 (P2-3 search_experiences)：P0-1 的持久化存储选型决定 search_experiences 是否可启用
- Task 8 (P1-4 TypedDict) → Task 9 (P1-5 全局变量)：建议先完成 TypedDict 迁移再改 store 注入，减少合并冲突
- Task 5 (P1-1 全量模式) 依赖 Task 1 (P0-2 硬拦截)：全量模式的差异化删除阈值基于硬拦截机制
- Task 7 (P1-3 Streamlit interrupt) 独立，但建议在 Task 3 (P0-1) 之后做，因为 interrupt 恢复需要 checkpointer 支持
- Task 10 (P2-1 log 结构化) 独立，但与 Task 4 (P0-3 报告工具) 相关——报告工具读取 execution_log，格式变更需同步
- Task 2 (P0-4 Phase C) 和 Task 4 (P0-3 报告工具) 互相独立
- Task 6 (P1-2 CLI 指令) 独立，当前已有基础实现，主要是验证
