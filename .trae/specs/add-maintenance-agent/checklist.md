# Checklist

## Phase 0：共享单元层 + 基础设施 + 现有模块扩展

- [x] langgraph、langchain-core、langchain-anthropic 已显式添加到 pixi.toml 依赖
- [x] `src/core/ops/` 包结构已创建，包含 `__init__.py`
- [x] `parse_pdf()` 共享单元已实现，测试通过
- [x] `chunk_parsed()` 共享单元已实现，含 `parent_chunk_config` 父子块接口预留，测试通过
- [x] `query_rag()` 共享单元已实现，测试通过
- [x] `evaluate_single()` 共享单元已实现，测试通过
- [x] `embed_chunks()` 共享单元已实现，测试通过
- [x] `index_chunks()` 和 `delete_source_and_reindex()` 共享单元已实现，测试通过
- [x] `create_langchain_anthropic_client()` 已实现，可创建 ChatAnthropic 实例
- [x] `PdfPlumberEnhancer.enhance_page()` 已实现，支持单页增强（page_number 为 1-indexed）
- [x] `PdfPlumberEnhancer.enhance_table()` 已实现，支持单表格增强（page_number 和 table_index 均为 1-indexed）
- [x] `ParserRegistry.get_enhancer()` 已实现
- [x] `enhance_page()` 和 `enhance_table()` 共享单元已实现
- [x] `VectorIndexer.delete_by_source()` 已实现，可按 source 过滤删除
- [x] `VectorIndexer.upsert_chunks()` 已实现，可增量插入
- [x] `MealConfig.creation_mode` 字段已添加
- [x] `MealManager.create_meal()` 支持 `pdf_files` 参数（通过 create_meal_manual()）
- [x] `MealManager.create_meal()` 支持 `source_dir` + `file_pattern` 参数（通过 create_meal_manual()）
- [x] `MealManager.create_meal()` 支持 `tags` 和 `description` 参数（通过 create_meal_manual()）
- [x] Meal 手动模式向后兼容：只传 sample_ratio 时行为不变
- [x] `ArtifactCache.update_manifest_entry()` 已实现，支持增量更新
- [x] ArtifactCache 增量更新保证原子性：更新失败时 manifest 保持原状
- [x] `pixi run test` 全部通过，无回归
- [x] `pixi run lint` 通过

## Phase 1：Agent MVP

- [x] `src/agent/` 包结构已创建
- [x] `MaintenanceState` TypedDict 已定义，字段完整
- [x] 核心 @tool 已实现：list_meals, get_meal_detail, query_rag_tool, parse_pdf_tool, enhance_page_tool, chunk_parsed_tool, evaluate_answer_tool, get_index_info
- [x] 高风险 @tool 已实现：rebuild_index, delete_source, update_meal
- [x] 维修工系统提示词已实现，包含角色定义、工具说明、工作原则
- [x] `agent_node` 已实现，可调用 LLM 并路由到工具节点
- [x] `should_continue()` 条件边路由已实现
- [x] `tool_node` 已实现，执行工具调用并返回结果
- [x] `approval_node` 已实现，使用 interrupt() 等待用户确认高风险操作
- [x] `build_graph()` 和 `compile_agent()` 已实现，StateGraph 可编译
- [x] InMemorySaver checkpointer 已配置
- [x] 高权限操作安全机制已实现：
  - [x] HIGH_RISK_TOOLS 集合定义
  - [x] 写操作通过 interrupt() 等待用户确认
  - [x] 操作日志记录（execution_log）
- [x] CLI 入口已实现（src/agent/cli.py），pixi task `agent` 已注册
- [x] Agent 测试已编写（22 个测试全部通过）
- [x] 安全机制测试通过（HIGH_RISK_TOOLS 集合、approval_node）

## Phase 2：全链路工具 + 回退跳转 + Issue 集成

- [ ] 全链路 @tool 已实现：embed, index, query, evaluate, meal, issue
- [ ] 全链路节点已实现：embed_node, index_node, retrieve_node, generate_node, evaluate_node
- [ ] `Command(goto=...)` 回退跳转已实现
- [ ] `interrupt()` 人工干预已在关键节点插入
- [ ] Memory Store 经验积累已实现
- [ ] Issue 系统集成已实现：
  - [ ] create_issue, list_issues, close_issue @tool 已实现
  - [ ] Agent 诊断发现系统性问题时主动建议创建 Issue
  - [ ] 开始处理 PDF 时自动检索相关 Issue
- [ ] StateGraph 已更新集成全链路节点
- [ ] 回退跳转测试通过
- [ ] interrupt 流程测试通过
- [ ] Issue 工具测试通过

## Phase 3：UI + 报告 + 生产化

- [ ] Streamlit 维修工页面已实现
- [ ] UI 下拉菜单锁定工具链已实现
- [ ] UI 支持轻量/全量模式切换
- [ ] CLI 指令交互已完善（:parse, :back, :compare 等指令）
- [ ] 维修报告生成已实现，保存到 `data/maintenance_reports/`
- [ ] 对比报告生成已实现，包含差异摘要和推荐
- [ ] Checkpointer 已迁移到 SqliteSaver
- [ ] 系统提示词已优化
- [ ] `parse_all_pdfs_unified()` 已迁移到调用 `parse_pdf()` 共享单元
- [ ] `pixi run test-all` 全部通过
- [ ] `pixi run lint` 通过
