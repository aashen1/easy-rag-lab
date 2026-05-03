# Tasks

> **重要说明**：本任务量极大，建议分 4 次对话完成。每次对话专注一个 Phase。Phase 0 是所有后续 Phase 的前置依赖，建议优先完成。部分 Task 之间可并行执行，详见 Task Dependencies 部分。

---

## Phase 0：共享单元层 + 基础设施 + 现有模块扩展（建议第 1 次对话）

> 对应调研计划 WP1 + WP4 + WP6

- [x] Task 0.1: 显式添加 langgraph 依赖到 pixi.toml
  - [x] 运行 `pixi add --pypi langgraph langchain-core langchain-anthropic` 显式声明依赖
  - [x] 验证 `pixi run python -c "import langgraph; print(langgraph.__version__)"` 成功

- [x] Task 0.2: 创建 `src/core/ops/` 包结构
  - [x] 创建 `src/core/__init__.py`
  - [x] 创建 `src/core/ops/__init__.py`

- [x] Task 0.3: 实现 `parse_pdf()` 共享单元
  - [x] 在 `src/core/ops/parse.py` 中实现 `parse_pdf()` 函数，包装 ParserRegistry.get_composite().parse()
  - [ ] 编写单元测试 `tests/test_core_ops/test_parse.py`

- [x] Task 0.4: 实现 `chunk_parsed()` 共享单元（含父子块接口预留）
  - [x] 在 `src/core/ops/chunk.py` 中实现 `chunk_parsed()` 函数，根据 strategy 分发到底层分块函数
  - [x] 参数包含 `parent_chunk_config`，预留父子块热插拔接口（当为 None 时行为与普通分块一致）
  - [ ] 编写单元测试 `tests/test_core_ops/test_chunk.py`

- [x] Task 0.5: 实现 `query_rag()` 共享单元
  - [x] 在 `src/core/ops/query.py` 中实现 `query_rag()` 函数，包装 RAGPipeline.query()
  - [ ] 编写单元测试 `tests/test_core_ops/test_query.py`

- [x] Task 0.6: 实现 `evaluate_single()` 共享单元
  - [x] 在 `src/core/ops/evaluate.py` 中实现 `evaluate_single()` 函数，包装 BuiltinEvaluator
  - [ ] 编写单元测试 `tests/test_core_ops/test_evaluate.py`

- [x] Task 0.7: 实现 `embed_chunks()` 和 `index_chunks()` 共享单元
  - [x] 在 `src/core/ops/embed.py` 中实现 `embed_chunks()`
  - [x] 在 `src/core/ops/index.py` 中实现 `index_chunks()` 和 `delete_source_and_reindex()`
  - [ ] 编写单元测试

- [x] Task 0.8: 适配 Anthropic 认证到 LangChain ChatAnthropic
  - [x] 在 `src/llm_client.py` 中新增 `create_langchain_anthropic_client()` 工厂函数
  - [x] 复用现有 API key / base_url 配置，适配 `Authorization: Bearer` header
  - [ ] 编写单元测试验证客户端可创建

- [x] Task 0.9: 扩展 PdfPlumberEnhancer 支持单页/单表格增强
  - [x] 在 `src/parsers/pdfplumber_enhancer.py` 中新增 `enhance_page()` 方法（page_number 为 1-indexed）
  - [x] 在 `src/parsers/pdfplumber_enhancer.py` 中新增 `enhance_table()` 方法（page_number 和 table_index 均为 1-indexed）
  - [x] 在 `src/parsers/registry.py` 中新增 `get_enhancer()` 方法
  - [x] 在 `src/core/ops/parse.py` 中新增 `enhance_page()` 和 `enhance_table()` 共享单元
  - [ ] 编写单元测试

- [x] Task 0.10: 扩展 VectorIndexer 增量操作
  - [x] 在 `src/indexer.py` 中新增 `delete_by_source()` 方法（Qdrant filter-based delete）
  - [x] 在 `src/indexer.py` 中新增 `upsert_chunks()` 方法
  - [ ] 编写单元测试

- [x] Task 0.11: 扩展 Meal 手动模式
  - [x] 在 `src/meal/models.py` 中新增 `creation_mode` 字段（"random" | "manual"）
  - [x] 在 `src/meal/manager.py` 中扩展 `create_meal()` 支持以下参数：
    - [x] `pdf_files` — 直接指定 PDF 文件列表
    - [x] `source_dir` — 指定搜索目录
    - [x] `file_pattern` — 文件名模式匹配（如 "*年报*"）
    - [x] `tags` — 标签
    - [x] `description` — 描述
  - [x] 确保向后兼容：只传 sample_ratio/sample_count 时行为不变
  - [ ] 编写单元测试

- [x] Task 0.12: 扩展 ArtifactCache 增量更新
  - [x] 在 `src/meal/cache.py` 中新增 `update_manifest_entry()` 方法
  - [x] 保证原子性：更新失败时 manifest 保持原状
  - [ ] 编写单元测试

- [x] Task 0.13: 运行全量测试确认无回归
  - [x] `pixi run test` 确保所有现有测试通过
  - [x] `pixi run lint` 确保代码质量

---

## Phase 1：Agent MVP — LangGraph 骨架 + 解析对比 + 安全机制（建议第 2 次对话）

> 对应调研计划 WP2

- [x] Task 1.1: 创建 `src/agent/` 包结构
  - [x] 创建 `src/agent/__init__.py`
  - [x] 创建 `src/agent/state.py` — MaintenanceState TypedDict
  - [x] 创建 `src/agent/tools.py` — 所有 @tool 定义
  - [x] 创建 `src/agent/prompt.py` — 系统提示词
  - [x] 创建 `src/agent/graph.py` — StateGraph 构建
  - [x] 创建 `src/agent/cli.py` — CLI 入口

- [x] Task 1.2: 定义 `MaintenanceState` TypedDict
  - [x] 在 `src/agent/state.py` 中定义状态模型
  - [x] 包含 messages, current_meal, current_source, diagnosis, pending_action, approved, execution_log 字段

- [x] Task 1.3: 实现核心 @tool 定义
  - [x] 8 个安全工具: list_meals, get_meal_detail, query_rag_tool, parse_pdf_tool, enhance_page_tool, chunk_parsed_tool, evaluate_answer_tool, get_index_info
  - [x] 3 个高风险工具: rebuild_index, delete_source, update_meal
  - [x] 每个 @tool 包装对应的共享单元函数

- [x] Task 1.4: 实现系统提示词
  - [x] `src/agent/prompt.py` — 维修工角色定义、可用工具说明、工作原则

- [x] Task 1.5: 实现 agent_node（LLM 决策节点）
  - [x] `src/agent/graph.py` — agent_node 调用 LLM with tools bound
  - [x] 实现 `should_continue()` 条件边路由函数

- [x] Task 1.6: 实现工具节点函数
  - [x] `src/agent/graph.py` — tool_node 执行工具调用并返回结果
  - [x] 包含执行日志记录

- [x] Task 1.7: 构建 StateGraph + 条件边
  - [x] `src/agent/graph.py` — build_graph() 和 compile_agent() 函数
  - [x] 添加节点、条件边、编译图
  - [x] 支持 InMemorySaver checkpointer

- [x] Task 1.8: 实现高权限操作安全机制
  - [x] HIGH_RISK_TOOLS 白名单集合
  - [x] approval_node 使用 interrupt() 等待用户确认
  - [x] 被拒绝的工具调用替换为拒绝消息

- [x] Task 1.9: 实现 CLI 入口（基础版）
  - [x] `src/agent/cli.py` — 基础文本交互
  - [x] 支持 interrupt 处理和执行日志展示
  - [x] 注册 pixi task `agent`

- [x] Task 1.10: 编写 Agent 测试
  - [x] 测试 StateGraph 构建和编译
  - [x] 测试各 @tool 函数存在性
  - [x] 测试条件边路由逻辑
  - [x] 测试安全机制（HIGH_RISK_TOOLS 集合）
  - [x] 22 个测试全部通过

---

## Phase 2：全链路工具 + 回退跳转 + 人工干预 + Issue 集成（建议第 3 次对话）

> 对应调研计划 WP3 + WP5

- [x] Task 2.1: 实现高风险 @tool
  - [x] rebuild_index — 重建向量索引
  - [x] delete_source — 删除数据源
  - [x] update_meal — 更新 meal 元数据

- [ ] Task 2.2: 实现全链路 @tool（后续迭代）
  - [ ] embed_chunks, index_chunks, delete_source_and_reindex 工具
  - [ ] create_curated_meal, list_pdfs 工具
  - [ ] create_issue, list_issues, close_issue 工具

- [ ] Task 2.3: 实现 Command(goto=...) 回退跳转
  - [ ] 在 agent_node 中支持用户回退指令
  - [ ] 更新 StateGraph 条件边支持跳转

- [ ] Task 2.4: 实现 interrupt() 人工干预增强
  - [ ] 在关键节点中插入更多 interrupt 点
  - [ ] 设计 interrupt payload 格式（结果摘要 + 可选操作）

- [ ] Task 2.5: 实现 Memory Store 经验积累
  - [ ] `src/agent/memory/experience_store.py` — namespace 设计、存取接口
  - [ ] 在 agent_node 中集成经验检索和存储

- [ ] Task 2.6: 实现 Issue 系统集成
  - [ ] `src/agent/tools/issue_tools.py` — 包装现有 issue CLI
  - [ ] Agent 诊断发现系统性问题时主动建议创建 Issue
  - [ ] 开始处理 PDF 时自动检索相关 Issue

- [ ] Task 2.7: 更新 StateGraph 集成全链路节点
  - [ ] 将新节点添加到 graph.py
  - [ ] 更新条件边路由映射
  - [ ] 更新系统提示词

- [ ] Task 2.8: 编写测试
  - [ ] 测试全链路节点
  - [ ] 测试回退跳转
  - [ ] 测试 interrupt 流程
  - [ ] 测试 Issue 工具

---

## Phase 3：UI + 报告 + 生产化（建议第 4 次对话）

> 对应调研计划 WP7 + WP8

- [ ] Task 3.1: 实现 Streamlit 维修工页面
  - [ ] `src/agent/ui/streamlit_page.py` — 参考 app_pages 现有风格
  - [ ] 展示会话状态、工具下拉菜单、interrupt 操作面板
  - [ ] 支持轻量/全量模式切换
  - [ ] 在 `src/app.py` 中注册新 Tab

- [ ] Task 3.2: 实现 UI 下拉菜单锁定工具链
  - [ ] 用户可选择锁定某个工具/参数组合
  - [ ] 锁定后 Agent 跳过 LLM 决策，直接使用指定工具

- [ ] Task 3.3: 完善 CLI 交互
  - [ ] 支持指令代替按钮（如 `:parse pymupdf4llm`、`:back chunk`、`:compare`）
  - [ ] 支持会话恢复 `--session-id`

- [ ] Task 3.4: 实现维修报告与对比报告生成
  - [ ] `src/agent/reporters/maintenance_report.py` — 维修日志汇总，持久化为 Markdown
  - [ ] `src/agent/reporters/comparison_report.py` — 结构化对比，包含差异摘要和推荐
  - [ ] 报告保存到 `data/maintenance_reports/` 目录

- [ ] Task 3.5: Checkpointer 迁移到 SqliteSaver
  - [ ] 替换 InMemorySaver 为 SqliteSaver
  - [ ] 配置持久化路径

- [ ] Task 3.6: 优化系统提示词
  - [ ] 多轮迭代优化决策质量
  - [ ] 添加更多示例和约束

- [ ] Task 3.7: 实验系统迁移到共享单元（遵循迁移路径 Phase C）
  - [ ] `parse_all_pdfs_unified()` 内部改为调用 `parse_pdf()` 共享单元
  - [ ] 确保实验系统测试全部通过

- [ ] Task 3.8: 完整测试 + 文档
  - [ ] 全量测试 `pixi run test-all`
  - [ ] lint 检查 `pixi run lint`
  - [ ] 更新相关文档

---

# Task Dependencies

- [Phase 1] 依赖 [Phase 0]（共享单元层是 Agent @tool 的基础）
- [Phase 2] 依赖 [Phase 1]（全链路工具在 MVP 骨架上扩展）
- [Phase 3] 依赖 [Phase 2]（UI 需要完整工具链支持）

**Phase 0 内部并行关系**：
- Task 0.1 是所有其他 0.x 的前置
- Task 0.3, 0.4, 0.5, 0.6, 0.7 可并行（独立共享单元）
- Task 0.8 可与 0.3-0.7 并行（独立模块）
- Task 0.9, 0.10, 0.11, 0.12 可并行（独立模块扩展）
- Task 0.13 必须在所有其他 0.x 之后

**Phase 0 与 Phase 1 的并行机会**：
- 无。Phase 1 严格依赖 Phase 0 完成的共享单元层

**跨 Phase 并行机会**（如果分多次对话则不适用）：
- WP4（Meal 手动模式 + 单页增强 = Task 0.9 + 0.11）可与 WP3（全链路工具 = Phase 2）并行
- WP6（增量更新 = Task 0.10 + 0.12）可与 WP3 并行

---

# 建议的分次对话策略

| 对话 | 工作范围 | 预估 Task 数 | 依赖 | 对应 WP |
|------|---------|-------------|------|---------|
| 第 1 次 | Phase 0 全部 | 13 个 Task | 无 | WP1 + WP4 + WP6 |
| 第 2 次 | Phase 1 全部 | 10 个 Task | Phase 0 | WP2 |
| 第 3 次 | Phase 2 全部 | 8 个 Task | Phase 1 | WP3 + WP5 |
| 第 4 次 | Phase 3 全部 | 8 个 Task | Phase 2 | WP7 + WP8 |

每次对话结束后，通过 git commit 保存进度，下次对话从上次结束处继续。
