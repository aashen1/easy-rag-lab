# Checklist

## 批次 A：偏差修正

- [x] `VectorIndexer.scroll_by_source()` 方法已实现，支持 `with_vectors=False` 仅返回 payload
- [x] `scroll_by_source()` 无匹配 points 时返回空列表
- [x] `scroll_by_source()` 异常时记录日志并 re-raise IndexingError
- [x] `delete_source` 工具在执行删除前调用 `scroll_by_source()` 备份元数据
- [x] 备份文件保存到 `.trashbin/source_backup_{hash}_{timestamp}.json`
- [x] 备份失败时记录 warning 日志但不阻塞删除操作
- [x] `delete_source` 返回结果包含 `backup_path` 字段
- [x] `parse_pdf()` 函数包含 try/except，异常时 logger.error + re-raise
- [x] `enhance_page()` 函数包含 try/except，异常时 logger.error + re-raise
- [x] `enhance_table()` 函数包含 try/except，异常时 logger.error + re-raise
- [x] `config.yaml` 新增 `agent` 配置段，包含 `defaults` 子段和 6 个默认值
- [x] `src/agent/config.py` 已创建，提供 `get_agent_config()` 和 `get_agent_default()` 函数
- [x] `tools.py` 中 `parse_pdf_tool` 的 `parser_name` 默认值从配置读取
- [x] `tools.py` 中 `enhance_page_tool` 的 `enhancer_name` 默认值从配置读取
- [x] `tools.py` 中 `chunk_parsed_tool` 的 `chunk_size`/`overlap` 默认值从配置读取
- [x] `src/core/ops/index.py` 中 `collection_name` 默认值从配置读取
- [x] `cli.py` 中 `thread_id` 默认值从配置读取
- [x] `_get_llm()` 使用 `lru_cache` 缓存，多次调用返回同一实例
- [x] `_get_tools()` 使用 `lru_cache` 缓存，多次调用返回同一列表
- [x] `scroll_by_source()` 单元测试通过
- [x] `delete_source` 备份流程单元测试通过
- [x] `parse.py` 异常处理单元测试通过
- [x] `get_agent_config()` / `get_agent_default()` 单元测试通过
- [x] LLM 客户端缓存单元测试通过
- [x] `pixi run test` 全部通过
- [x] `pixi run lint` 通过

## 批次 B：全链路工具 + Issue 集成

- [x] `embed_chunks_tool` @tool 已实现，包装 `embed_chunks()` 共享单元
- [x] `index_chunks_tool` @tool 已实现，包装 `index_chunks()` 共享单元
- [x] `delete_and_reindex_tool` @tool 已实现，包装 `delete_source_and_reindex()` 共享单元
- [x] `create_curated_meal` @tool 已实现，包装 `MealManager.create_meal_manual()`
- [x] `list_pdfs` @tool 已实现，glob `data/raw/` 目录
- [x] `create_issue` @tool 已实现，使用 subprocess 包装 `pixi run issue create`
- [x] `list_issues` @tool 已实现，使用 subprocess 包装 `pixi run issue list`
- [x] `close_issue` @tool 已实现，使用 subprocess 包装 `pixi run issue done`
- [x] Issue 工具处理 subprocess 异常（TimeoutExpired, CalledProcessError）
- [x] 所有新工具遵循 try/except + loguru + JSON 返回模式
- [x] `HIGH_RISK_TOOLS` 集合包含 `"delete_and_reindex_tool"`
- [x] `_get_tools()` 返回包含所有 19 个工具的列表
- [x] `embed_chunks_tool` 存在性和参数测试通过
- [x] `index_chunks_tool` 存在性和参数测试通过
- [x] `delete_and_reindex_tool` 存在性测试 + HIGH_RISK_TOOLS 包含测试通过
- [x] `create_curated_meal` 存在性和参数测试通过
- [x] `list_pdfs` 存在性测试通过
- [x] `create_issue` 存在性和参数测试通过（mock subprocess）
- [x] `list_issues` 存在性和参数测试通过（mock subprocess）
- [x] `close_issue` 存在性和参数测试通过（mock subprocess）
- [x] `pixi run test` 全部通过
- [x] `pixi run lint` 通过

## 批次 C：回退跳转 + 人工干预 + 系统提示词

- [x] `MaintenanceState` 新增 `stage_history: list[str]` 字段
- [x] `MaintenanceState` 新增 `auto_review: bool` 字段
- [x] 现有测试中 `MaintenanceState` 构造已补全新字段 ⚠️ TestMaintenanceState/TestShouldContinue/TestToolNode 未补全 stage_history/auto_review
- [x] `tool_node` 执行完工具后更新 `stage_history`
- [x] `auto_review=True` 时，`tool_node` 执行完解析/分块工具后自动 `interrupt()` 展示结果摘要
- [x] `SYSTEM_PROMPT` 从常量改为 `build_system_prompt(stage_history, experiences)` 函数
- [x] `build_system_prompt()` 当 `stage_history` 非空时追加"已执行步骤"段落
- [x] `build_system_prompt()` 包含"全链路工具"说明段落
- [x] `build_system_prompt()` 包含"Issue 规则"段落
- [x] `build_system_prompt()` 包含"回退指令"段落
- [x] `build_system_prompt()` 当 `experiences` 非空时追加"历史经验推荐"段落
- [x] `agent_node` 使用 `build_system_prompt()` 构建动态提示词
- [x] CLI 支持 `:review on` 指令设置 `auto_review=True`
- [x] CLI 支持 `:review off` 指令设置 `auto_review=False`
- [x] `MaintenanceState` 新字段测试通过
- [x] `tool_node` 更新 `stage_history` 测试通过
- [x] `build_system_prompt()` 函数测试通过
- [x] `auto_review` interrupt 测试通过
- [x] CLI `:review on/off` 指令测试通过
- [x] `pixi run test` 全部通过
- [x] `pixi run lint` 通过

## 批次 D：Memory Store 经验积累

- [x] `src/agent/memory/` 包已创建（含 `__init__.py`）
- [x] `src/agent/memory/experience_store.py` 已创建
- [x] `ExperienceStore` 类已实现，接受 `store` (BaseStore) 参数
- [x] `save_experience(namespace, experience)` 方法已实现
- [x] `search_experiences(namespace, query)` 方法已实现
- [x] `get_all_experiences(namespace)` 方法已实现
- [x] namespace 格式为 `(user_id, "maintenance_experience", pdf_type)`
- [x] `compile_agent()` 接受 `store` 参数并传递给 `graph.compile()`
- [x] `agent_node` 从 store 检索经验并注入提示词
- [x] `agent_node` 根据 `current_source` 推断 `pdf_type`
- [x] `tool_node` 执行完解析/分块工具后自动保存经验到 ExperienceStore
- [x] 经验结构包含 `pdf_type`, `best_parser`, `best_chunk_strategy`, `best_chunk_size`, `reason`, `timestamp`
- [x] `cli.py` 创建 `InMemoryStore` 并传入 `compile_agent()`
- [x] `ExperienceStore.save_experience()` 测试通过
- [x] `ExperienceStore.search_experiences()` 测试通过
- [x] `ExperienceStore.get_all_experiences()` 测试通过
- [x] `compile_agent(store=store)` 编译测试通过
- [x] `agent_node` 经验检索集成测试通过
- [x] `pixi run test` 全部通过
- [x] `pixi run lint` 通过
