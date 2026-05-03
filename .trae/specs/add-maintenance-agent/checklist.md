# Checklist

## Phase 0：共享单元层 + 基础设施 + 现有模块扩展

- [ ] langgraph、langchain-core、langchain-anthropic 已显式添加到 pixi.toml 依赖
- [ ] `src/core/ops/` 包结构已创建，包含 `__init__.py`
- [ ] `parse_pdf()` 共享单元已实现，测试通过
- [ ] `chunk_parsed()` 共享单元已实现，含 `parent_chunk_config` 父子块接口预留，测试通过
- [ ] `query_rag()` 共享单元已实现，测试通过
- [ ] `evaluate_single()` 共享单元已实现，测试通过
- [ ] `embed_chunks()` 共享单元已实现，测试通过
- [ ] `index_chunks()` 和 `delete_source_and_reindex()` 共享单元已实现，测试通过
- [ ] `create_langchain_anthropic_client()` 已实现，可创建 ChatAnthropic 实例
- [ ] `PdfPlumberEnhancer.enhance_page()` 已实现，支持单页增强（page_number 为 1-indexed）
- [ ] `PdfPlumberEnhancer.enhance_table()` 已实现，支持单表格增强（page_number 和 table_index 均为 1-indexed）
- [ ] `ParserRegistry.get_enhancer()` 已实现
- [ ] `enhance_page()` 和 `enhance_table()` 共享单元已实现
- [ ] `VectorIndexer.delete_by_source()` 已实现，可按 source 过滤删除
- [ ] `VectorIndexer.upsert_chunks()` 已实现，可增量插入
- [ ] `MealConfig.creation_mode` 字段已添加
- [ ] `MealManager.create_meal()` 支持 `pdf_files` 参数
- [ ] `MealManager.create_meal()` 支持 `source_dir` + `file_pattern` 参数
- [ ] `MealManager.create_meal()` 支持 `tags` 和 `description` 参数
- [ ] Meal 手动模式向后兼容：只传 sample_ratio 时行为不变
- [ ] `ArtifactCache.update_manifest_entry()` 已实现，支持增量更新
- [ ] ArtifactCache 增量更新保证原子性：更新失败时 manifest 保持原状
- [ ] `pixi run test` 全部通过，无回归
- [ ] `pixi run lint` 通过

## Phase 1：Agent MVP

- [ ] `src/agent/` 包结构已创建（含 nodes, tools, prompts, memory, reporters 子包）
- [ ] `src/agent/config.py` Agent 配置加载模块已创建
- [ ] `MaintenanceState` TypedDict 已定义，字段完整（含 mode 字段区分轻量/全量）
- [ ] 核心 @tool 已实现：parse_pdf, enhance_page, enhance_table, chunk_parsed（含 parent_chunk_config）, compare_results
- [ ] 维修工系统提示词已实现，包含角色定义、工具说明、工作原则
- [ ] `agent_node` 已实现，可调用 LLM 并路由到工具节点
- [ ] `route_from_agent()` 条件边路由已实现
- [ ] parse_node、chunk_node、compare_node 已实现
- [ ] `build_maintenance_graph()` 已实现，StateGraph 可编译
- [ ] InMemorySaver checkpointer 已配置
- [ ] State 中 mode 字段可区分轻量/全量模式
- [ ] 高权限操作安全机制已实现：
  - [ ] 白名单定义（禁止删除整个 collection、删除整个 Meal、批量覆盖 manifest）
  - [ ] 写操作前自动备份到 `.trashbin/`
  - [ ] 写操作通过 interrupt() 等待用户确认
  - [ ] 操作日志记录
- [ ] CLI 入口 `main.py agent` 子命令已实现，支持 `--pdf`、`--session-id`、`--full` 参数
- [ ] Agent 测试已编写，标记为 `@pytest.mark.agent`
- [ ] 安全机制测试通过（白名单拦截、备份机制）

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
