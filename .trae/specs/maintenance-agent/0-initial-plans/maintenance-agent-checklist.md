# 维修工 Agent 实现验证清单

> 基于 `maintenance-agent-research-plan.md` v0.2 修订版
> 目的：当以下所有检查项完成打钩，即可认定"维修工"feature 已实现完善
> 规则：每条检查项涉及的代码范围不超过 500 行

---

## Phase 0：基础设施（前置依赖）

### 0.1 依赖安装

- [ ] 安装 `langgraph` 包（pixi add --pypi）
- [ ] 安装 `langchain-core` 包（pixi add --pypi）
- [ ] 安装 `langchain-anthropic` 包（pixi add --pypi）
- [ ] 验证依赖版本兼容性（langgraph >= 0.2, langchain-core >= 0.3, langchain-anthropic >= 0.3）

### 0.2 共享单元层目录结构

- [ ] 创建 `src/core/` 目录
- [ ] 创建 `src/core/__init__.py`
- [ ] 创建 `src/core/ops/` 目录
- [ ] 创建 `src/core/ops/__init__.py`

### 0.3 解析共享单元 (`src/core/ops/parse.py`)

- [ ] 实现 `parse_pdf()` 函数签名和参数定义
- [ ] 实现 `parse_pdf()` 调用 ParserRegistry.get_composite()
- [ ] 实现 `parse_pdf()` 调用 parser.parse() 并返回 ParseResult
- [ ] 实现 `enhance_page()` 函数签名和参数定义
- [ ] 实现 `enhance_page()` 调用 enhancer.enhance_page()
- [ ] 为 `parse_pdf()` 编写单元测试
- [ ] 为 `enhance_page()` 编写单元测试

### 0.4 分块共享单元 (`src/core/ops/chunk.py`)

- [ ] 实现 `chunk_parsed()` 函数签名和参数定义
- [ ] 实现 `chunk_parsed()` 的 strategy 分发逻辑（fixed/page_aware/semantic）
- [ ] 实现 `_chunk_fixed()` 内部函数
- [ ] 实现 `_chunk_page_aware()` 内部函数
- [ ] 实现 `_chunk_semantic()` 内部函数
- [ ] 为 `chunk_parsed()` 编写单元测试（覆盖三种策略）

### 0.5 嵌入共享单元 (`src/core/ops/embed.py`)

- [ ] 实现 `embed_chunks()` 函数签名和参数定义
- [ ] 实现 `embed_chunks()` 调用 Embedder.embed_documents()
- [ ] 为 `embed_chunks()` 编写单元测试

### 0.6 索引共享单元 (`src/core/ops/index.py`)

- [ ] 实现 `index_chunks()` 函数签名和参数定义
- [ ] 实现 `index_chunks()` 调用 VectorIndexer.build_index()
- [ ] 实现 `delete_source_and_reindex()` 函数签名和参数定义
- [ ] 实现 `delete_source_and_reindex()` 删除旧向量逻辑
- [ ] 实现 `delete_source_and_reindex()` 索引新 chunks 逻辑
- [ ] 为 `index_chunks()` 编写单元测试
- [ ] 为 `delete_source_and_reindex()` 编写单元测试

### 0.7 查询共享单元 (`src/core/ops/query.py`)

- [ ] 实现 `query_rag()` 函数签名和参数定义
- [ ] 实现 `query_rag()` 调用 RAGPipeline.query()
- [ ] 实现 `query_rag()` 返回标准化结果字典
- [ ] 为 `query_rag()` 编写单元测试

### 0.8 评测共享单元 (`src/core/ops/evaluate.py`)

- [ ] 实现 `evaluate_single()` 函数签名和参数定义
- [ ] 实现 `evaluate_single()` 调用 BuiltinEvaluator.evaluate_batch()
- [ ] 实现 `evaluate_single()` 返回指标字典
- [ ] 为 `evaluate_single()` 编写单元测试

### 0.9 Anthropic 认证适配

- [ ] 实现 `create_langchain_anthropic_client()` 函数
- [ ] 支持自定义 base_url 参数
- [ ] 支持自定义 default_headers（Bearer token）
- [ ] 从项目配置读取 API key
- [ ] 为认证适配编写单元测试

---

## Phase 1：Agent MVP（核心能力）

### 1.1 Agent 包目录结构

- [ ] 创建 `src/agent/` 目录
- [ ] 创建 `src/agent/__init__.py`
- [ ] 创建 `src/agent/nodes/` 目录
- [ ] 创建 `src/agent/nodes/__init__.py`
- [ ] 创建 `src/agent/tools/` 目录
- [ ] 创建 `src/agent/tools/__init__.py`
- [ ] 创建 `src/agent/memory/` 目录
- [ ] 创建 `src/agent/memory/__init__.py`
- [ ] 创建 `src/agent/prompts/` 目录
- [ ] 创建 `src/agent/prompts/__init__.py`
- [ ] 创建 `src/agent/reporters/` 目录
- [ ] 创建 `src/agent/reporters/__init__.py`
- [ ] 创建 `src/agent/ui/` 目录
- [ ] 创建 `src/agent/ui/__init__.py`

### 1.2 状态模型定义 (`src/agent/state.py`)

- [ ] 定义 `MaintenanceState` TypedDict
- [ ] 定义 `messages` 字段（Annotated[list[AnyMessage], add_messages]）
- [ ] 定义 `pdf_path` 字段
- [ ] 定义 `page_number` 字段
- [ ] 定义 `current_stage` 字段
- [ ] 定义 `parse_results` 字段（字典结构）
- [ ] 定义 `chunk_results` 字段（字典结构）
- [ ] 定义 `embed_result` 字段
- [ ] 定义 `index_result` 字段
- [ ] 定义 `retrieve_result` 字段
- [ ] 定义 `generate_result` 字段
- [ ] 定义 `evaluate_result` 字段
- [ ] 定义 `comparison_reports` 字段
- [ ] 定义 `user_locked_tools` 字段
- [ ] 定义 `maintenance_notes` 字段

### 1.3 解析工具定义 (`src/agent/tools/parse_tools.py`)

- [ ] 实现 `parse_pdf` @tool 装饰器包装
- [ ] 定义工具描述文档字符串
- [ ] 定义参数类型和默认值
- [ ] 调用共享单元 `parse_pdf()`
- [ ] 实现 `enhance_page` @tool 装饰器包装
- [ ] 定义工具描述文档字符串
- [ ] 调用共享单元 `enhance_page()`

### 1.4 分块工具定义 (`src/agent/tools/chunk_tools.py`)

- [ ] 实现 `chunk_parsed` @tool 装饰器包装
- [ ] 定义工具描述文档字符串
- [ ] 定义参数类型和默认值（strategy, chunk_size, overlap 等）
- [ ] 调用共享单元 `chunk_parsed()`

### 1.5 嵌入工具定义 (`src/agent/tools/embed_tools.py`)

- [ ] 实现 `embed_chunks` @tool 装饰器包装
- [ ] 定义工具描述文档字符串
- [ ] 调用共享单元 `embed_chunks()`

### 1.6 索引工具定义 (`src/agent/tools/index_tools.py`)

- [ ] 实现 `index_chunks` @tool 装饰器包装
- [ ] 实现 `delete_source_and_reindex` @tool 装饰器包装
- [ ] 定义工具描述文档字符串
- [ ] 调用共享单元函数

### 1.7 查询工具定义 (`src/agent/tools/query_tools.py`)

- [ ] 实现 `query_rag` @tool 装饰器包装
- [ ] 定义工具描述文档字符串
- [ ] 调用共享单元 `query_rag()`

### 1.8 评测工具定义 (`src/agent/tools/evaluate_tools.py`)

- [ ] 实现 `evaluate_single` @tool 装饰器包装
- [ ] 定义工具描述文档字符串
- [ ] 调用共享单元 `evaluate_single()`

### 1.9 对比工具定义 (`src/agent/tools/compare_tools.py`)

- [ ] 实现 `compare_results` @tool 函数
- [ ] 实现结果差异计算逻辑
- [ ] 实现对比报告生成逻辑
- [ ] 定义工具描述文档字符串

### 1.10 Meal 工具定义 (`src/agent/tools/meal_tools.py`)

- [ ] 实现 `create_curated_meal` @tool 函数
- [ ] 实现 `list_pdfs` @tool 函数
- [ ] 定义工具描述文档字符串

### 1.11 Issue 工具定义 (`src/agent/tools/issue_tools.py`)

- [ ] 实现 `create_issue` @tool 函数
- [ ] 实现 `list_issues` @tool 函数
- [ ] 定义工具描述文档字符串

### 1.12 Agent 决策节点 (`src/agent/nodes/decide_node.py`)

- [ ] 实现 `agent_node()` 函数签名
- [ ] 实现读取历史维修经验逻辑
- [ ] 实现构建决策 prompt 逻辑
- [ ] 实现调用 LLM（带工具绑定）
- [ ] 实现工具调用提取和路由逻辑
- [ ] 实现 `route_from_agent()` 条件路由函数
- [ ] 实现工具名到节点名的映射字典

### 1.13 解析节点 (`src/agent/nodes/parse_node.py`)

- [ ] 实现 `parse_node()` 函数签名
- [ ] 实现提取工具调用参数逻辑
- [ ] 实现调用共享单元 `parse_pdf()`
- [ ] 实现计算度量指标逻辑
- [ ] 实现构建工具响应消息
- [ ] 实现更新 parse_results 状态
- [ ] 实现 `enhance_page_node()` 函数

### 1.14 分块节点 (`src/agent/nodes/chunk_node.py`)

- [ ] 实现 `chunk_node()` 函数签名
- [ ] 实现提取工具调用参数逻辑
- [ ] 实现调用共享单元 `chunk_parsed()`
- [ ] 实现计算分块度量指标
- [ ] 实现构建工具响应消息
- [ ] 实现更新 chunk_results 状态

### 1.15 嵌入节点 (`src/agent/nodes/embed_node.py`)

- [ ] 实现 `embed_node()` 函数签名
- [ ] 实现调用共享单元 `embed_chunks()`
- [ ] 实现更新 embed_result 状态

### 1.16 索引节点 (`src/agent/nodes/index_node.py`)

- [ ] 实现 `index_node()` 函数签名
- [ ] 实现调用共享单元 `index_chunks()`
- [ ] 实现更新 index_result 状态

### 1.17 检索节点 (`src/agent/nodes/retrieve_node.py`)

- [ ] 实现 `retrieve_node()` 函数签名
- [ ] 实现调用共享单元 `query_rag()`
- [ ] 实现更新 retrieve_result 状态

### 1.18 生成节点 (`src/agent/nodes/generate_node.py`)

- [ ] 实现 `generate_node()` 函数签名
- [ ] 实现调用共享单元 `query_rag()`
- [ ] 实现更新 generate_result 状态

### 1.19 评测节点 (`src/agent/nodes/evaluate_node.py`)

- [ ] 实现 `evaluate_node()` 函数签名
- [ ] 实现调用共享单元 `evaluate_single()`
- [ ] 实现更新 evaluate_result 状态

### 1.20 对比节点 (`src/agent/nodes/compare_node.py`)

- [ ] 实现 `compare_node()` 函数签名
- [ ] 实现调用 `compare_results` 工具
- [ ] 实现更新 comparison_reports 状态

### 1.21 报告节点 (`src/agent/nodes/report_node.py`)

- [ ] 实现 `report_node()` 函数签名
- [ ] 实现生成维修报告逻辑
- [ ] 实现生成对比报告逻辑

### 1.22 StateGraph 构建 (`src/agent/graph.py`)

- [ ] 实现 `build_maintenance_graph()` 函数
- [ ] 创建 StateGraph 实例
- [ ] 添加所有节点到 graph
- [ ] 添加 START 到 agent 的边
- [ ] 添加 agent 的条件边
- [ ] 添加各工具节点到 agent 的边
- [ ] 创建 InMemorySaver checkpointer
- [ ] 创建 InMemoryStore store
- [ ] 编译 graph 并返回

### 1.23 系统提示词 (`src/agent/prompts/system_prompt.py`)

- [ ] 定义 `MAINTENANCE_WORKER_SYSTEM_PROMPT` 常量
- [ ] 包含角色定位描述
- [ ] 包含当前状态占位符
- [ ] 包含可用工具列表
- [ ] 包含过去经验占位符
- [ ] 包含用户锁定工具占位符
- [ ] 包含工作原则（5 条）

### 1.24 决策提示词 (`src/agent/prompts/decision_prompt.py`)

- [ ] 定义决策提示词模板
- [ ] 包含工具选择指导
- [ ] 包含参数推荐逻辑

### 1.25 维修日志 (`src/agent/memory/maintenance_log.py`)

- [ ] 实现 `MaintenanceLog` 类
- [ ] 实现基于 LangGraph Checkpointer 的日志存储
- [ ] 实现 `save_checkpoint()` 方法
- [ ] 实现 `load_checkpoint()` 方法
- [ ] 实现 `list_checkpoints()` 方法

### 1.26 经验存储 (`src/agent/memory/experience_store.py`)

- [ ] 实现 `ExperienceStore` 类
- [ ] 实现基于 LangGraph Store 的经验存储
- [ ] 实现 `save_experience()` 方法
- [ ] 实现 `search_experiences()` 方法
- [ ] 实现 `get_experience()` 方法

### 1.27 维修报告生成器 (`src/agent/reporters/maintenance_report.py`)

- [ ] 实现 `MaintenanceReporter` 类
- [ ] 实现 `generate_report()` 方法
- [ ] 实现报告模板（Markdown 格式）
- [ ] 实现报告持久化逻辑

### 1.28 对比报告生成器 (`src/agent/reporters/comparison_report.py`)

- [ ] 实现 `ComparisonReporter` 类
- [ ] 实现 `generate_comparison_report()` 方法
- [ ] 实现差异表格生成
- [ ] 实现对比分析文本生成

### 1.29 CLI 入口 (`src/agent/ui/cli.py`)

- [ ] 实现 CLI 主函数入口
- [ ] 实现用户输入解析
- [ ] 实现指令到工具调用的映射
- [ ] 实现结果展示逻辑
- [ ] 实现交互循环

### 1.30 Agent 配置 (`src/agent/config.py`)

- [ ] 定义 Agent 配置数据类
- [ ] 定义 LLM preset 选择
- [ ] 定义默认参数配置
- [ ] 实现配置加载逻辑

### 1.31 Agent 测试（Phase 1）

- [ ] 编写 `test_state.py` 测试状态模型
- [ ] 编写 `test_tools.py` 测试工具定义
- [ ] 编写 `test_nodes.py` 测试节点函数
- [ ] 编写 `test_graph.py` 测试工作流图
- [ ] 编写 `test_cli.py` 测试 CLI 入口
- [ ] 添加 `@pytest.mark.agent` 标记

---

## Phase 2：扩展能力

### 2.1 回退跳转实现

- [ ] 实现 `Command(goto=...)` 导入
- [ ] 在 agent_node 中实现回退逻辑
- [ ] 实现跳转到 parse 阶段
- [ ] 实现跳转到 chunk 阶段
- [ ] 实现全部重来逻辑（清空状态）
- [ ] 编写回退跳转测试

### 2.2 人工干预实现（interrupt）

- [ ] 在 parse_node 中实现 interrupt 调用
- [ ] 定义 interrupt 消息结构
- [ ] 定义可用操作列表
- [ ] 实现用户反馈处理逻辑
- [ ] 在其他节点中实现 interrupt（按需）
- [ ] 编写 interrupt 测试

### 2.3 Meal 手动模式扩展

- [ ] 在 `src/meal/models.py` 中新增 `creation_mode` 字段
- [ ] 在 `MealConfig` 中新增 `pdf_files` 字段
- [ ] 在 `MealConfig` 中新增 `source_dir` 字段
- [ ] 在 `MealConfig` 中新增 `file_pattern` 字段
- [ ] 在 `MealConfig` 中新增 `tags` 字段
- [ ] 在 `MealConfig` 中新增 `description` 字段
- [ ] 在 `src/meal/manager.py` 中扩展 `create_meal()` 方法
- [ ] 实现手动指定 PDF 列表逻辑
- [ ] 实现文件模式匹配逻辑
- [ ] 保持向后兼容性
- [ ] 编写 Meal 手动模式测试

### 2.4 PdfPlumberEnhancer 单页增强改造

- [ ] 在 `src/parsers/pdfplumber_enhancer.py` 中新增 `enhance_page()` 方法
- [ ] 实现单页表格提取逻辑
- [ ] 实现表格合并到页面文本逻辑
- [ ] 实现 1-indexed 到 0-indexed 转换
- [ ] 编写单页增强测试

### 2.5 ParserRegistry 扩展

- [ ] 在 `src/parsers/registry.py` 中新增 `get_enhancer()` 方法
- [ ] 实现 enhancer 实例创建逻辑
- [ ] 编写 get_enhancer 测试

### 2.6 ArtifactCache 增量更新

- [ ] 在 `src/meal/cache.py` 中新增 `update_manifest_entry()` 方法
- [ ] 实现单个条目更新逻辑
- [ ] 实现原子写入逻辑
- [ ] 编写增量更新测试

### 2.7 VectorIndexer 增量操作

- [ ] 在 `src/indexer.py` 中新增 `delete_by_source()` 方法
- [ ] 实现 Qdrant filter-based delete 逻辑
- [ ] 在 `src/indexer.py` 中新增 `upsert_chunks()` 方法
- [ ] 实现批量 upsert 逻辑
- [ ] 编写增量操作测试

### 2.8 记忆系统完善

- [ ] 实现 namespace 设计（按用户/PDF 类型）
- [ ] 实现经验结构定义
- [ ] 实现经验自动积累逻辑
- [ ] 实现经验检索和排序
- [ ] 编写记忆系统测试

### 2.9 Issue 系统集成

- [ ] 实现创建 issue 的工具逻辑
- [ ] 实现列出 issues 的工具逻辑
- [ ] 实现维修笔记自动关联 issue
- [ ] 编写 Issue 集成测试

### 2.10 Agent 测试（Phase 2）

- [ ] 编写回退跳转集成测试
- [ ] 编写人工干预集成测试
- [ ] 编写 Meal 手动模式集成测试
- [ ] 编写单页增强集成测试
- [ ] 编写增量更新集成测试
- [ ] 编写记忆系统集成测试
- [ ] 编写 Issue 集成测试

---

## Phase 3：用户界面与优化

### 3.1 Streamlit 页面基础结构 (`src/agent/ui/streamlit_page.py`)

- [ ] 实现 Streamlit 页面主函数
- [ ] 实现页面标题和描述
- [ ] 实现侧边栏配置区
- [ ] 实现主内容区布局
- [ ] 实现状态展示区

### 3.2 Streamlit 工具链锁定 UI

- [ ] 实现解析器下拉选择框
- [ ] 实现增强器下拉选择框
- [ ] 实现分块策略下拉选择框
- [ ] 实现分块参数输入框（chunk_size, overlap）
- [ ] 实现嵌入模型选择框
- [ ] 实现检索参数输入框
- [ ] 实现工具链锁定状态管理

### 3.3 Streamlit 文件选择 UI

- [ ] 实现文件浏览器组件
- [ ] 实现单文件选择逻辑
- [ ] 实现多文件选择逻辑
- [ ] 实现页码选择逻辑
- [ ] 实现文件预览功能

### 3.4 Streamlit 结果展示 UI

- [ ] 实现解析结果展示（Markdown 渲染）
- [ ] 实现分块结果展示（表格）
- [ ] 实现检索结果展示（卡片）
- [ ] 实现生成结果展示（问答对）
- [ ] 实现评测结果展示（指标图表）
- [ ] 实现对比结果展示（差异表格）

### 3.5 Streamlit 交互流程 UI

- [ ] 实现执行按钮
- [ ] 实现进度展示
- [ ] 实现中断/暂停按钮
- [ ] 实现回退按钮
- [ ] 实现重置按钮
- [ ] 实现反馈输入框

### 3.6 Streamlit 维修日志 UI

- [ ] 实现维修日志列表展示
- [ ] 实现日志详情查看
- [ ] 实现日志搜索功能
- [ ] 实现日志导出功能

### 3.7 CLI 完善

- [ ] 实现指令解析器（解析用户指令）
- [ ] 实现指令到工具调用的映射字典
- [ ] 实现批量指令执行
- [ ] 实现指令历史记录
- [ ] 实现指令自动补全（可选）

### 3.8 系统提示词优化

- [ ] 优化角色定位描述
- [ ] 优化工具选择指导
- [ ] 优化参数推荐逻辑
- [ ] 添加错误处理指导
- [ ] 添加边界情况处理
- [ ] 进行多轮迭代测试

### 3.9 实验系统迁移到共享单元

- [ ] 修改 `src/parser.py` 的 `parse_all_pdfs_unified()` 调用共享单元
- [ ] 修改 `src/chunker.py` 的相关函数调用共享单元
- [ ] 修改 `src/indexer.py` 的相关函数调用共享单元
- [ ] 修改 `src/evaluator.py` 的相关函数调用共享单元
- [ ] 验证实验系统功能不受影响
- [ ] 编写回归测试

### 3.10 维修报告生成完善

- [ ] 实现报告模板定制
- [ ] 实现报告导出（Markdown/HTML）
- [ ] 实现报告归档逻辑
- [ ] 实现报告与 Meal 关联

### 3.11 Checkpointer 迁移到 SqliteSaver

- [ ] 实现 SqliteSaver 配置
- [ ] 实现数据库初始化逻辑
- [ ] 实现 checkpoint 迁移脚本
- [ ] 实现生产环境配置
- [ ] 编写 SqliteSaver 测试

### 3.12 main.py 集成

- [ ] 在 `main.py` 中新增 `agent` 子命令
- [ ] 实现 agent 子命令入口函数
- [ ] 实现 CLI 模式启动逻辑
- [ ] 实现 Web UI 模式启动逻辑

### 3.13 config.yaml 集成

- [ ] 在 `config.yaml` 中新增 `agent` 配置段
- [ ] 定义 LLM preset 配置
- [ ] 定义默认参数配置
- [ ] 定义存储路径配置
- [ ] 定义权限配置

### 3.14 app.py 集成

- [ ] 在 `src/app.py` 中新增维修工 Tab
- [ ] 实现页面路由逻辑
- [ ] 实现状态共享逻辑

### 3.15 Agent 测试（Phase 3）

- [ ] 编写 Streamlit 页面测试
- [ ] 编写 CLI 完善测试
- [ ] 编写系统提示词优化测试
- [ ] 编写实验系统迁移回归测试
- [ ] 编写 Checkpointer 迁移测试
- [ ] 编写集成测试（端到端）

### 3.16 文档编写

- [ ] 编写 `docs/user-guides/maintenance-agent.md`（用户指南）
- [ ] 编写 `docs/dev-guides/maintenance-agent.md`（开发者指南）
- [ ] 更新 `docs/README.md` 添加维修工文档索引
- [ ] 更新 `CLAUDE.md` 添加维修工状态说明

---

## 核心能力验证清单

### C1：单文件/单页面处理

- [ ] 验证可以指定单个 PDF 文件处理
- [ ] 验证可以指定单个页面处理
- [ ] 验证可以指定单个表格处理

### C2：全链路工具调用

- [ ] 验证可以调用解析工具
- [ ] 验证可以调用分块工具
- [ ] 验证可以调用嵌入工具
- [ ] 验证可以调用索引工具
- [ ] 验证可以调用检索工具
- [ ] 验证可以调用生成工具
- [ ] 验证可以调用评测工具

### C3：工具结果质量比较

- [ ] 验证可以对同一输入用不同解析器处理
- [ ] 验证可以对同一输入用不同分块策略处理
- [ ] 验证可以比较结果差异
- [ ] 验证可以生成对比报告

### C4：分块参数可配置

- [ ] 验证可以配置 chunk_size
- [ ] 验证可以配置 overlap
- [ ] 验证可以配置语义分块阈值
- [ ] 验证预留了父子块热插拔接口

### C5：单步/多步执行

- [ ] 验证支持单步调用某个工具
- [ ] 验证支持多步串联执行
- [ ] 验证可以在任意步骤暂停

### C6：轻量/全量双模式

- [ ] 验证轻量模式可以处理 1-2 个 PDF
- [ ] 验证全量模式可以处理大量 PDF
- [ ] 验证模式切换正常

### C7：LLM 自主决策

- [ ] 验证 Agent 可以根据用户指令自主选择工具
- [ ] 验证 Agent 可以根据用户指令自主选择参数
- [ ] 验证用户可以通过 Web UI 锁定工具链

### C8：结果反馈循环

- [ ] 验证用户可以回退到任意阶段
- [ ] 验证用户可以重做任意步骤
- [ ] 验证 Agent 记住最优方案

### C9：分析报告与维修日志

- [ ] 验证维修日志持久化
- [ ] 验证维修笔记持久化
- [ ] 验证跨 session 积累经验
- [ ] 验证集成 Issue 系统

### C10：用户交互

- [ ] 验证 Web UI 可用
- [ ] 验证 CLI 可用
- [ ] 验证下拉菜单指定工具链正常
- [ ] 验证 CLI 指令代替按钮正常

### C11：Meal 手动模式

- [ ] 验证可以手动指定 PDF 列表创建 Meal
- [ ] 验证向后兼容随机抽样模式
- [ ] 验证 Agent 可以创建手动 Meal

### C12：高权限操作

- [ ] 验证维修工可以写回 Meal
- [ ] 验证维修工可以写回 Artifact
- [ ] 验证备份机制正常
- [ ] 验证白名单机制正常

---

## 风险控制验证清单

### R1：数据损坏防护

- [ ] 验证写操作前自动备份到 `.trashbin/`
- [ ] 验证白名单机制限制危险操作
- [ ] 验证禁止全量删除操作

### R2：状态一致性

- [ ] 验证维修工写回 Meal 时做一致性校验
- [ ] 验证 Meal 的 creation_mode 字段正确区分来源

### R3：LangGraph 版本稳定性

- [ ] 验证 langgraph 版本锁定
- [ ] 验证 LangGraph 调用封装在 `src/agent/graph.py`

### R4：共享单元回归保护

- [ ] 验证共享单元作为薄包装层
- [ ] 验证渐进式迁移不影响现有功能
- [ ] 验证每步迁移都有测试覆盖

### R5：LLM 决策可控性

- [ ] 验证系统提示词约束有效
- [ ] 验证用户锁定机制有效
- [ ] 验证 interrupt 人工审核有效

### R6：Anthropic 认证适配

- [ ] 验证 ChatAnthropic 自定义 headers 正常
- [ ] 验证 API 代理对接正常

### R7：依赖管理

- [ ] 验证仅引入 `langgraph` + `langchain-core` + `langchain-anthropic`
- [ ] 验证依赖链不过重

---

## 最终验收清单

### 功能完整性

- [ ] 所有核心能力（C1-C12）验证通过
- [ ] 所有风险控制（R1-R7）验证通过
- [ ] 所有 Phase 0-3 的检查项完成

### 测试覆盖率

- [ ] 共享单元测试覆盖率 >= 90%
- [ ] Agent 工具测试覆盖率 >= 90%
- [ ] Agent 节点测试覆盖率 >= 90%
- [ ] 集成测试覆盖主要流程

### 文档完整性

- [ ] 用户指南编写完成
- [ ] 开发者指南编写完成
- [ ] API 文档编写完成
- [ ] 示例代码编写完成

### 性能验证

- [ ] 单文件处理响应时间 < 5s
- [ ] 单页增强响应时间 < 2s
- [ ] 对比报告生成时间 < 3s

### 用户体验

- [ ] Web UI 交互流畅
- [ ] CLI 指令清晰易懂
- [ ] 错误提示友好
- [ ] 帮助文档完善

---

**总计检查项：** 378 项

**说明：**
- 每个检查项涉及的代码范围不超过 500 行
- 检查项按照 Phase 0-3 的实施顺序组织
- 核心能力验证清单对应需求文档中的 C1-C12
- 风险控制验证清单对应需求文档中的风险评估
- 最终验收清单用于整体质量把控

# 检查结果（5月9日13:07 周六）

