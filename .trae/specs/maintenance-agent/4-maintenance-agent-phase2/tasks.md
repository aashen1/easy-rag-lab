# Tasks

> 维修工 Agent Phase 2：偏差修正 + 全链路工具 + 回退跳转 + 人工干预 + Memory Store + Issue 集成
> 按 4 个提交批次组织，批次内按依赖顺序排列

---

## 批次 A：偏差修正（不依赖 Phase 2 新功能）

- [x] A1: `src/indexer.py` 新增 `scroll_by_source()` 方法
  - [x] A1.1: 在 `VectorIndexer` 类中新增 `scroll_by_source(source: str, with_vectors: bool = False) -> list[dict]` 方法
  - [x] A1.2: 使用 `self.client.scroll()` 按 source filter 检索 points，`with_vectors=False` 时仅返回 payload
  - [x] A1.3: 返回 `list[dict]`，每个 dict 包含 `id` 和 `payload`；无匹配时返回空列表
  - [x] A1.4: 包含 try/except + loguru 日志，异常时 re-raise IndexingError
  - [ ] A1.5: 编写单元测试 `tests/test_indexer.py`（或追加到已有测试文件）

- [x] A2: `src/agent/tools.py` 的 `delete_source` 增加备份逻辑
  - [x] A2.1: 在 `delete_source` 工具中，调用 `indexer.scroll_by_source(source, with_vectors=False)` 获取将被删除的 points 元数据
  - [x] A2.2: 将元数据序列化为 JSON，保存到 `.trashbin/source_backup_{source_hash}_{timestamp}.json`
  - [x] A2.3: 备份失败时记录 warning 日志但不阻塞删除操作
  - [x] A2.4: 返回结果中包含 `backup_path` 字段
  - [ ] A2.5: 编写单元测试验证备份流程

- [x] A3: `src/core/ops/parse.py` 三个函数加 try/except
  - [x] A3.1: `parse_pdf()` 函数体包裹 try/except，捕获异常后 `logger.error()` 并 re-raise
  - [x] A3.2: `enhance_page()` 函数体包裹 try/except，同上
  - [x] A3.3: `enhance_table()` 函数体包裹 try/except，同上
  - [x] A3.4: 确保异常类型和消息不变（re-raise 原始异常）

- [x] A4: `config.yaml` 新增 `agent` 配置段
  - [x] A4.1: 在 `config.yaml` 末尾新增 `agent:` 顶级配置段
  - [x] A4.2: 新增 `agent.defaults:` 子段，包含 `parser_name`, `enhancer_name`, `chunk_size`, `chunk_overlap`, `collection_name`, `thread_id` 六个默认值
  - [x] A4.3: 默认值与当前硬编码一致（parser_name="pymupdf4llm", enhancer_name="pdfplumber", chunk_size=512, chunk_overlap=0, collection_name="financial_reports", thread_id="maintenance-session"）

- [x] A5: `src/agent/config.py` 新增配置加载模块
  - [x] A5.1: 创建 `src/agent/config.py` 文件
  - [x] A5.2: 实现 `get_agent_config() -> dict` 函数，调用 `load_config()` 读取 `agent` 配置段
  - [x] A5.3: 实现 `get_agent_default(key: str, fallback=None) -> Any` 函数，读取 `agent.defaults.{key}` 的值
  - [x] A5.4: 配置缺失时回退到 fallback 值

- [x] A6: 替换硬编码配置值
  - [ ] A6.1: `tools.py` 中 `parse_pdf_tool` 的 `parser_name="pymupdf4llm"` 默认值改为从 `get_agent_default("parser_name", "pymupdf4llm")` 读取
  - [ ] A6.2: `tools.py` 中 `enhance_page_tool` 的 `enhancer_name="pdfplumber"` 默认值改为从配置读取
  - [ ] A6.3: `tools.py` 中 `chunk_parsed_tool` 的 `chunk_size=512, overlap=0` 默认值改为从配置读取
  - [ ] A6.4: `src/core/ops/index.py` 中 `collection_name="financial_reports"` 默认值改为从配置读取
  - [ ] A6.5: `cli.py` 中 `thread_id="maintenance-session"` 默认值改为从配置读取

- [x] A7: `src/agent/graph.py` LLM 客户端缓存
  - [ ] A7.1: 使用 `functools.lru_cache(maxsize=1)` 装饰 `_get_llm()` 函数
  - [ ] A7.2: 使用 `functools.lru_cache(maxsize=1)` 装饰 `_get_tools()` 函数
  - [ ] A7.3: 验证 `agent_node` 多次调用时 LLM 和 tools 不重复创建

- [x] A8: 补充偏差修正的单元测试
  - [ ] A8.1: `scroll_by_source()` 单元测试（mock Qdrant client.scroll）
  - [ ] A8.2: `delete_source` 备份流程测试（mock scroll_by_source + 验证 JSON 写入）
  - [ ] A8.3: `parse.py` 异常处理测试（mock parser 抛异常，验证 logger.error + re-raise）
  - [ ] A8.4: `get_agent_config()` 和 `get_agent_default()` 测试
  - [ ] A8.5: LLM 客户端缓存测试（验证多次调用返回同一实例）

- [x] A9: 回归验证
  - [ ] A9.1: `pixi run test` 全部通过
  - [ ] A9.2: `pixi run lint` 通过

---

## 批次 B：全链路工具 + Issue 集成

- [x] B1: `src/agent/tools.py` 新增 embed/index/meal/pdf 工具
  - [ ] B1.1: 新增 `embed_chunks_tool` @tool，包装 `embed_chunks()` 共享单元，参数：`chunks: list[dict]`, `collection_name: str`，返回 JSON 含 `embedding_dim` 和 `chunk_count`
  - [ ] B1.2: 新增 `index_chunks_tool` @tool，包装 `index_chunks()` 共享单元，参数：`chunks: list[dict]`, `collection_name: str`，返回 JSON 含 `indexed_count`
  - [ ] B1.3: 新增 `delete_and_reindex_tool` @tool，包装 `delete_source_and_reindex()` 共享单元，参数：`source: str`, `new_chunks: list[dict]`, `collection_name: str`，返回 JSON 含 `reindexed_count`
  - [ ] B1.4: 新增 `create_curated_meal` @tool，包装 `MealManager.create_meal_manual()`，参数：`name: str`, `pdf_files: list[str] | None`, `source_dir: str | None`, `file_pattern: str | None`, `tags: list[str] | None`, `description: str | None`，返回 JSON 含 Meal 详情
  - [ ] B1.5: 新增 `list_pdfs` @tool，直接 glob `data/raw/` 目录，参数：`pattern: str = "*.pdf"`，返回 JSON 含 PDF 文件列表（文件名、大小、修改时间）
  - [ ] B1.6: 所有新工具遵循现有模式：try/except + loguru + JSON 返回

- [x] B2: `src/agent/tools.py` 新增 Issue 工具
  - [ ] B2.1: 新增 `create_issue` @tool，使用 `subprocess.run(["pixi", "run", "issue", "create", "-t", issue_type, "-T", title, "-p", priority, "-l", labels])`，参数：`title: str`, `issue_type: str`, `priority: str = "medium"`, `labels: str | None = None`，返回 JSON 含创建结果
  - [ ] B2.2: 新增 `list_issues` @tool，使用 `subprocess.run(["pixi", "run", "issue", "list", "--status", status, "--type", issue_type, "--all"])`，参数：`status: str | None = None`, `issue_type: str | None = None`，返回 JSON 含 Issue 列表
  - [ ] B2.3: 新增 `close_issue` @tool，使用 `subprocess.run(["pixi", "run", "issue", "done", issue_id])`，参数：`issue_id: str`，返回 JSON 含关闭结果
  - [ ] B2.4: Issue 工具使用 `subprocess.run(capture_output=True, text=True, timeout=30)` 捕获输出
  - [ ] B2.5: Issue 工具处理 subprocess 异常（TimeoutExpired, CalledProcessError）

- [x] B3: `src/agent/tools.py` 更新 `HIGH_RISK_TOOLS`
  - [ ] B3.1: `HIGH_RISK_TOOLS` 集合新增 `"delete_and_reindex_tool"`
  - [ ] B3.2: 验证 `HIGH_RISK_TOOLS` 现为 `{"rebuild_index", "delete_source", "update_meal", "delete_and_reindex_tool"}`

- [x] B4: `src/agent/graph.py` 的 `_get_tools()` 注册新工具
  - [ ] B4.1: `_get_tools()` 返回列表新增 `embed_chunks_tool`, `index_chunks_tool`, `delete_and_reindex_tool`, `create_curated_meal`, `list_pdfs`, `create_issue`, `list_issues`, `close_issue`
  - [ ] B4.2: 验证 `_get_tools()` 返回 19 个工具（原 11 + 新 8，注意 delete_and_reindex_tool 是新增而非替换 delete_source）

- [x] B5: 补充新工具的单元测试
  - [ ] B5.1: `embed_chunks_tool` 存在性和参数测试
  - [ ] B5.2: `index_chunks_tool` 存在性和参数测试
  - [ ] B5.3: `delete_and_reindex_tool` 存在性测试 + HIGH_RISK_TOOLS 包含测试
  - [ ] B5.4: `create_curated_meal` 存在性和参数测试
  - [ ] B5.5: `list_pdfs` 存在性测试
  - [ ] B5.6: `create_issue` 存在性和参数测试（mock subprocess）
  - [ ] B5.7: `list_issues` 存在性和参数测试（mock subprocess）
  - [ ] B5.8: `close_issue` 存在性和参数测试（mock subprocess）

- [x] B6: 回归验证
  - [ ] B6.1: `pixi run test` 全部通过
  - [ ] B6.2: `pixi run lint` 通过

---

## 批次 C：回退跳转 + 人工干预 + 系统提示词

- [x] C1: `src/agent/state.py` 新增 `stage_history`, `auto_review` 字段
  - [ ] C1.1: `MaintenanceState` 新增 `stage_history: list[str]` 字段，默认 `[]`
  - [ ] C1.2: `MaintenanceState` 新增 `auto_review: bool` 字段，默认 `False`
  - [ ] C1.3: 更新现有测试中 `MaintenanceState` 的构造，补全新字段

- [x] C2: `src/agent/graph.py` 的 `tool_node` 更新 `stage_history`
  - [ ] C2.1: `tool_node` 执行完每个工具后，将工具名追加到 `state["stage_history"]`
  - [ ] C2.2: 返回 dict 中包含 `"stage_history": state.get("stage_history", []) + [tool_name]`
  - [ ] C2.3: 当 `auto_review=True` 且工具名为 `parse_pdf_tool` 或 `chunk_parsed_tool` 时，执行 `interrupt()` 展示结果摘要

- [x] C3: `src/agent/prompt.py` 注入 stage_history + 新工具说明 + Issue 规则
  - [ ] C3.1: 将 `SYSTEM_PROMPT` 从常量改为函数 `build_system_prompt(stage_history=None, experiences=None) -> str`
  - [ ] C3.2: 当 `stage_history` 非空时，追加"已执行步骤"段落
  - [ ] C3.3: 新增"全链路工具"说明段落（embed, index, delete_and_reindex, meal, pdf, issue 工具说明）
  - [ ] C3.4: 新增"Issue 规则"段落：诊断发现系统性问题时主动建议创建 Issue
  - [ ] C3.5: 新增"回退指令"段落：告知 LLM 可以重新选择之前的工具
  - [ ] C3.6: 当 `experiences` 非空时，追加"历史经验推荐"段落

- [x] C4: `src/agent/graph.py` 的 `agent_node` 使用动态提示词
  - [ ] C4.1: `agent_node` 调用 `build_system_prompt(stage_history=state.get("stage_history", []), experiences=...)` 构建提示词
  - [ ] C4.2: 替换原来硬编码的 `SYSTEM_PROMPT` 常量引用

- [x] C5: `src/agent/cli.py` 支持 `:review on/off` 指令
  - [ ] C5.1: 在用户输入处理循环中，检测 `:review on` 和 `:review off` 指令
  - [ ] C5.2: `:review on` 设置 `state["auto_review"] = True`
  - [ ] C5.3: `:review off` 设置 `state["auto_review"] = False`
  - [ ] C5.4: 打印当前 auto_review 状态反馈

- [x] C6: 补充单元测试
  - [ ] C6.1: `MaintenanceState` 新字段测试
  - [ ] C6.2: `tool_node` 更新 `stage_history` 测试
  - [ ] C6.3: `build_system_prompt()` 函数测试（含 stage_history、experiences 注入）
  - [ ] C6.4: `auto_review` interrupt 测试
  - [ ] C6.5: CLI `:review on/off` 指令测试

- [x] C7: 回归验证
  - [ ] C7.1: `pixi run test` 全部通过
  - [ ] C7.2: `pixi run lint` 通过

---

## 批次 D：Memory Store 经验积累

- [x] D1: `src/agent/memory/experience_store.py` 封装存取逻辑
  - [ ] D1.1: 创建 `src/agent/memory/` 包（`__init__.py`）
  - [ ] D1.2: 创建 `src/agent/memory/experience_store.py`
  - [ ] D1.3: 实现 `ExperienceStore` 类，接受 `store` (BaseStore) 参数
  - [ ] D1.4: 实现 `save_experience(namespace: tuple, experience: dict) -> str` 方法，使用 `store.put(namespace, key=uuid, value=experience)` 保存
  - [ ] D1.5: 实现 `search_experiences(namespace: tuple, query: str = None) -> list[dict]` 方法，使用 `store.search(namespace, query=query)` 检索
  - [ ] D1.6: 实现 `get_all_experiences(namespace: tuple) -> list[dict]` 方法，使用 `store.list_items(namespace)` 获取全部
  - [ ] D1.7: namespace 格式：`(user_id, "maintenance_experience", pdf_type)`

- [x] D2: `src/agent/graph.py` 的 `compile_agent()` 接受 `store` 参数
  - [ ] D2.1: `compile_agent(checkpointer=None, store=None)` 新增 `store` 参数
  - [ ] D2.2: `graph.compile(checkpointer=checkpointer, store=store)` 传递 store

- [x] D3: `src/agent/graph.py` 的 `agent_node` 检索经验注入提示词
  - [ ] D3.1: `agent_node` 从 `config` 中获取 store（通过闭包或全局变量）
  - [ ] D3.2: 根据 `current_source` 推断 `pdf_type`（从文件名提取关键词如"年报"/"研报"）
  - [ ] D3.3: 调用 `ExperienceStore.search_experiences()` 检索相关经验
  - [ ] D3.4: 将经验传入 `build_system_prompt(experiences=...)`

- [x] D4: `src/agent/graph.py` 的 `tool_node` 自动保存经验
  - [ ] D4.1: 当 `tool_node` 执行完 `parse_pdf_tool` 或 `chunk_parsed_tool` 后，检查结果是否包含有效配置信息
  - [ ] D4.2: 如果是有效的配置组合（parser + chunk strategy + chunk size），自动保存到 ExperienceStore
  - [ ] D4.3: 经验结构包含 `pdf_type`, `best_parser`, `best_chunk_strategy`, `best_chunk_size`, `reason`, `timestamp`

- [x] D5: `src/agent/cli.py` 创建 InMemoryStore 并传入
  - [ ] D5.1: `run_agent()` 中创建 `InMemoryStore()` 实例
  - [ ] D5.2: 传入 `compile_agent(checkpointer=checkpointer, store=store)`

- [x] D6: 补充单元测试
  - [ ] D6.1: `ExperienceStore.save_experience()` 测试
  - [ ] D6.2: `ExperienceStore.search_experiences()` 测试
  - [ ] D6.3: `ExperienceStore.get_all_experiences()` 测试
  - [ ] D6.4: `compile_agent(store=store)` 编译测试
  - [ ] D6.5: `agent_node` 经验检索集成测试

- [x] D7: 回归验证
  - [ ] D7.1: `pixi run test` 全部通过
  - [ ] D7.2: `pixi run lint` 通过

---

# Task Dependencies

**批次内依赖**：
- A1 → A2（scroll_by_source 是 delete_source 备份的前置）
- A4 → A5 → A6（配置文件 → 配置模块 → 替换硬编码）
- A7 独立于 A1-A6
- A8 依赖 A1-A7 全部完成
- A9 依赖 A8

- B1, B2 可并行
- B3 依赖 B1（需要知道新工具名）
- B4 依赖 B1, B2（需要导入新工具）
- B5 依赖 B1-B4
- B6 依赖 B5

- C1 → C2, C3（state 字段是 graph 和 prompt 的前置）
- C3 → C4（prompt 函数是 agent_node 的前置）
- C2, C4 可并行
- C5 独立于 C1-C4
- C6 依赖 C1-C5
- C7 依赖 C6

- D1 → D2, D3, D4（ExperienceStore 是集成的前置）
- D2, D3, D4 顺序执行
- D5 依赖 D2
- D6 依赖 D1-D5
- D7 依赖 D6

**批次间依赖**：
- 批次 B 依赖批次 A（配置集中化完成后新工具才能使用配置默认值）
- 批次 C 依赖批次 B（提示词需要包含新工具说明）
- 批次 D 依赖批次 C（agent_node 需要动态提示词函数）
