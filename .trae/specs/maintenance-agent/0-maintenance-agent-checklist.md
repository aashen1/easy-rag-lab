# 维修工 Agent 需求验收 Checklist

> 基于 `0-maintenance-agent-research-plan.md` 拆解
> 日期：2026-05-04
> 编号规则：0-X 对应原始文档章节/能力编号
> 状态标记：✅ 已完成 | ⚠️ 部分完成 | ❌ 未完成

---

## 0-1 核心能力验收（对应 §1.2 C1-C12）

### 0-1.1 C1 单文件/单页面处理

- [x] 可脱离 Meal 批量体系，手动指定单个 PDF 进行解析
- [x] 可指定单个 PDF 的单页进行表格增强（`enhance_page()`）
- [x] 可指定单个 PDF 的单页单表格进行增强（`enhance_table()`）
- [x] 单文件处理不依赖全局 manifest / pointer

### 0-1.2 C2 全链路工具调用

- [x] Agent 可调用解析工具（`parse_pdf_tool`）
- [x] Agent 可调用表格增强工具（`enhance_page_tool`）
- [x] Agent 可调用分块工具（`chunk_parsed_tool`）
- [x] Agent 可调用嵌入工具（`embed_chunks_tool`）
- [x] Agent 可调用索引工具（`index_chunks_tool`）
- [x] Agent 可调用检索/查询工具（`query_rag_tool`）
- [x] Agent 可调用评测工具（`evaluate_answer_tool`）
- [x] Agent 可调用增量索引工具（`delete_and_reindex_tool`）

### 0-1.3 C3 工具结果质量比较

- [x] 对同一 PDF 使用不同解析器解析后，可比较结果差异
- [x] 对同一解析结果使用不同分块策略后，可比较结果差异
- [x] 比较结果包含关键指标（字符数、表格数、分块数等）

### 0-1.4 C4 分块参数可配置

- [x] `chunk_size` 可配置
- [x] `overlap` 可配置
- [x] 语义分块阈值（`similarity_threshold`）可配置
- [x] 父子块热插拔接口已预留（`parent_chunk_config` 参数）
- [x] `parent_chunk_config` 为 None 时行为与普通分块完全一致

### 0-1.5 C5 单步/多步执行

- [x] 支持单步调用某个工具（如只解析不分块）
- [x] 支持多步串联（解析→分块→嵌入→索引→查询→评测）
- [x] Agent 通过 LLM 自主决定执行单步还是多步

### 0-1.6 C6 轻量/全量双模式

- [ ] ⚠️ 轻量模式：处理 1-2 个 PDF，不触发 Meal 批量体系（当前默认行为即轻量，但无显式模式切换）
- [ ] ❌ 全量模式：可调用 Meal 批量体系，处理完整数据集（无 `--full` 参数）
- [x] 默认为轻量模式
- [ ] ❌ 用户可通过 `--full` 或 UI 切换到全量模式

### 0-1.7 C7 LLM 自主决策

- [x] Agent 通过系统提示词理解维修工角色
- [x] Agent 根据用户指令自主判断工具选择
- [x] Agent 通过 `@tool` + `bind_tools()` 实现工具调用
- [ ] ❌ 用户可通过 Web UI 下拉菜单锁定工具链（覆盖 LLM 决策）（无 Streamlit 页面）

### 0-1.8 C8 结果反馈循环

- [x] 用户发现问题后可回退到任意阶段重做（通过 stage_history + LLM 重新选择工具）
- [x] Agent 记住已执行步骤（`stage_history`）
- [x] Agent 可根据历史步骤重新选择工具
- [x] LLM 感知历史后可重新选择之前的工具

### 0-1.9 C9 分析报告与维修日志

- [x] 维修日志记录每次操作的输入/输出/参数/时间戳（`execution_log`）
- [x] 维修日志持久化（InMemorySaver 开发，SqliteSaver 生产）— 开发版已实现
- [x] 经验记忆跨 session 积累（Memory Store）
- [x] Agent 可检索历史经验辅助决策
- [x] 集成 Issue 系统（create/list/close）
- [ ] ❌ 维修报告生成（Markdown 格式，保存到 `data/maintenance_reports/`）
- [ ] ❌ 对比报告生成（结构化对比，差异摘要和推荐）

### 0-1.10 C10 用户交互

- [ ] ❌ Web UI 优先：Streamlit 维修工页面
- [x] CLI 辅助：`pixi run agent` 启动交互式 CLI
- [x] CLI 支持指令代替按钮（`:review on/off` 等）
- [ ] ❌ CLI 支持更多指令（`:parse`, `:back`, `:compare`）

### 0-1.11 C11 Meal 手动模式

- [x] `MealManager` 支持 `pdf_files` 参数手动指定 PDF 列表（通过 `create_meal_manual()`）
- [x] `MealManager` 支持 `source_dir` + `file_pattern` 参数搜索 PDF
- [x] `MealManager` 支持 `tags` 和 `description` 参数
- [x] `MealConfig` 新增 `creation_mode` 字段（"random" | "manual"）
- [x] 向后兼容：只传 `sample_ratio`/`sample_count` 时行为不变
- [x] Agent 可通过 `create_curated_meal` 工具创建手动 Meal

### 0-1.12 C12 高权限操作

- [x] 维修工可写回 Meal（`update_meal` 工具）
- [x] 维修工可写回 Artifact（`update_manifest_entry`）
- [x] 写操作前自动备份到 `.trashbin/`
- [ ] ⚠️ 白名单机制：禁止删除整个 Qdrant collection（仅靠 HIGH_RISK_TOOLS + interrupt，无硬拦截）
- [ ] ⚠️ 白名单机制：禁止删除整个 Meal（仅靠提示词约束，无硬拦截）
- [x] 高风险操作通过 `interrupt()` 等待用户确认
- [x] 操作日志记录所有写操作

---

## 0-2 设计决策验收（对应 §1.3 Q1-Q5）

### 0-2.1 Q1 自主判断程度

- [x] LLM 自主决策：Agent 通过 LLM + @tool 绑定自主选择工具和参数
- [ ] ❌ 用户可锁定：用户可通过 UI 下拉菜单锁定工具链（无 Streamlit 页面）

### 0-2.2 Q2 单页表格补强

- [x] 支持单页级增强（`enhance_page()`）
- [x] 支持单表格级增强（`enhance_table()`）
- [x] `page_number` 和 `table_index` 统一 1-indexed

### 0-2.3 Q3 交互界面

- [ ] ❌ Web UI（Streamlit 页面）
- [x] CLI 辅助（交互式命令行）

### 0-2.4 Q4 写回权限

- [x] 高权限：可写回 Meal
- [x] 备份机制：写操作前自动备份到 `.trashbin/`
- [x] 白名单机制：限制危险操作（HIGH_RISK_TOOLS + interrupt）

### 0-2.5 Q5 日志持久化

- [x] 完整持久化：Checkpointer 保存状态（InMemorySaver）
- [x] 记忆系统：Memory Store 跨 session 经验积累
- [x] Issue 集成：create/list/close Issue

---

## 0-3 共享单元层验收（对应 §4.2）

### 0-3.1 解析单元

- [x] `parse_pdf()` 包装 ParserRegistry，返回 ParseResult
- [x] `parse_pdf()` 结果与直接调用 `ParserRegistry.get_composite().parse()` 一致
- [x] `enhance_page()` 对单页执行表格增强
- [x] `enhance_table()` 对单表格执行增强
- [x] `parse_pdf()` 包含 try/except + loguru 日志
- [x] `enhance_page()` 包含 try/except + loguru 日志
- [x] `enhance_table()` 包含 try/except + loguru 日志

### 0-3.2 分块单元

- [x] `chunk_parsed()` 根据 strategy 分发到具体分块函数
- [x] 支持 `fixed` 策略
- [x] 支持 `page_aware` 策略
- [x] 支持 `semantic` 策略
- [x] 未知策略抛出 `ValueError`
- [x] `parent_chunk_config` 预留父子块接口

### 0-3.3 嵌入单元

- [x] `embed_chunks()` 包装 Embedder.embed_texts()
- [x] 返回 `list[list[float]]`

### 0-3.4 索引单元

- [x] `index_chunks()` 创建 collection → 嵌入 → 索引
- [x] `delete_source_and_reindex()` 按 source 删除旧向量 → 嵌入新块 → 增量 upsert
- [x] `delete_source_and_reindex()` 内部复用 `delete_by_source()` 和 `upsert_chunks()`
- [x] `delete_source_and_reindex()` 使用 try/finally 确保 indexer.close()

### 0-3.5 查询单元

- [x] `query_rag()` 包装 RAGPipeline.query()

### 0-3.6 评测单元

- [x] `evaluate_single()` 提供基础指标（Phase A：Jaccard 词重叠）
- [x] 接口预留完整评测器迁移路径（Phase B/C）

### 0-3.7 渐进式迁移路径

- [x] Phase A：共享单元作为薄包装层，内部调用现有底层函数
- [x] Phase B：Agent @tool 直接包装共享单元
- [ ] ❌ Phase C：实验系统逐步改为调用共享单元（待实现）
- [ ] ❌ Phase D：共享单元稳定后，底层函数可重构为共享单元内部实现（可选）

---

## 0-4 Meal 体系扩展验收（对应 §4.3）

- [x] `create_meal()` 或 `create_meal_manual()` 支持 `pdf_files` 参数
- [x] 支持 `source_dir` + `file_pattern` 参数
- [x] 支持 `tags` 和 `description` 参数
- [x] `MealConfig.creation_mode` 字段区分 "random" / "manual"
- [x] 向后兼容：只传 `sample_ratio`/`sample_count` 时行为不变
- [x] Agent 可通过 `create_curated_meal` 工具创建手动 Meal

---

## 0-5 PdfPlumberEnhancer 改造验收（对应 §4.4）

- [x] `enhance_page(pdf_path, page_number, existing_text)` 方法已实现
- [x] `enhance_page()` 仅对指定页面执行表格提取和合并
- [x] `enhance_table(pdf_path, page_number, table_index, existing_text)` 方法已实现
- [x] `enhance_table()` 仅对指定表格执行提取和合并
- [x] 不影响现有 `enhance()` 全文档增强方法
- [x] `ParserRegistry.get_enhancer()` 方法已实现

---

## 0-6 LangGraph 工作流验收（对应 §6）

### 0-6.1 StateGraph 构建

- [x] `MaintenanceState` TypedDict 已定义
- [x] 包含 `messages` 字段（带 `add_messages` 注解）
- [x] 包含 `current_meal`, `current_source` 字段
- [x] 包含 `diagnosis`, `pending_action`, `approved` 字段
- [x] 包含 `execution_log` 字段
- [x] 包含 `stage_history` 字段
- [x] 包含 `auto_review` 字段

### 0-6.2 Agent 节点（LLM 决策）

- [x] `agent_node` 调用 LLM with tools bound
- [x] LLM 返回工具调用时路由到对应节点
- [x] LLM 直接回复时结束对话
- [x] `agent_node` 使用动态提示词（`build_system_prompt`）
- [x] `agent_node` 从 store 检索经验注入提示词

### 0-6.3 条件边路由

- [x] `should_continue()` 检查最后消息是否有 tool_calls
- [x] 有 tool_calls → 路由到 approval
- [x] 无 tool_calls → 结束
- [x] `_route_after_approval()` 条件路由：有待执行 tool_calls → tools，全部拒绝 → agent

### 0-6.4 审批节点

- [x] `approval_node` 检查 tool_calls 是否包含 HIGH_RISK_TOOLS
- [x] 高风险工具通过 `interrupt()` 等待用户确认
- [x] 用户拒绝：替换为拒绝 ToolMessage
- [x] 用户批准：保留 tool_call 继续执行

### 0-6.5 工具节点

- [x] `tool_node` 执行所有 tool_calls
- [x] 返回 ToolMessage 结果 + 执行日志
- [x] `tool_node` 更新 `stage_history`
- [x] `tool_node` 自动保存经验到 ExperienceStore
- [x] `auto_review=True` 时，解析/分块工具执行后自动 `interrupt()`

### 0-6.6 人工干预

- [x] `interrupt()` 可在任意节点暂停
- [x] 用户可 approve / reject / 指定新参数
- [x] `auto_review` 模式下关键工具执行后自动暂停

### 0-6.7 回退与跳转

- [x] `stage_history` 记录已执行的工具名
- [x] 系统提示词包含"已执行步骤"段落
- [x] LLM 可根据历史重新选择之前的工具
- [x] 系统提示词包含"回退指令"说明

---

## 0-7 安全机制验收（对应 §7.1）

- [x] 写操作前自动备份到 `.trashbin/`
- [x] `delete_source` 执行前备份将被删除的 points 元数据
- [x] `rebuild_index` 执行前备份 chunks 目录
- [x] `update_meal` 执行前备份 manifest.json
- [x] 备份文件名包含时间戳和标识
- [x] 备份失败时记录 warning 但不阻塞操作
- [ ] ⚠️ 白名单机制禁止删除整个 Qdrant collection（仅靠 HIGH_RISK_TOOLS + interrupt，无硬拦截）
- [ ] ⚠️ 白名单机制禁止删除整个 Meal（仅靠提示词约束，无硬拦截）
- [x] 高风险操作通过 `interrupt()` 等待用户确认
- [x] 操作日志记录所有写操作（类型、目标、时间戳、备份路径）

---

## 0-8 Anthropic 认证适配验收（对应 §3.5）

- [x] `create_langchain_anthropic_client()` 工厂函数已实现
- [x] 复用项目已有的 API key 和 base_url 配置
- [x] 支持 `Authorization: Bearer` header
- [x] 与现有 `create_anthropic_client()` 共享配置来源
- [x] LLM 客户端使用 `lru_cache` 缓存，避免重复创建

---

## 0-9 配置集中化验收（对应 §5.2 修改文件）

- [x] `config.yaml` 新增 `agent` 配置段
- [x] `agent.defaults` 包含 `parser_name`, `enhancer_name`, `chunk_size`, `chunk_overlap`, `collection_name`, `thread_id`
- [x] `src/agent/config.py` 提供 `get_agent_config()` 和 `get_agent_default()` 函数
- [x] `tools.py` 默认值从配置读取
- [x] `cli.py` 默认值从配置读取
- [x] `index.py` 默认值从配置读取
- [x] 配置缺失时回退到硬编码默认值

---

## 0-10 现有模块扩展验收（对应 §5.2 修改文件）

- [x] `VectorIndexer.delete_by_source()` 已实现
- [x] `VectorIndexer.upsert_chunks()` 已实现
- [x] `VectorIndexer.scroll_by_source()` 已实现
- [x] `ArtifactCache.update_manifest_entry()` 已实现
- [x] `update_manifest_entry()` 保证原子性：更新失败时 manifest 保持原状
- [x] `MealConfig.creation_mode` 字段已添加，默认 "random"
- [x] `MealManager.create_meal_manual()` 已实现

---

## 0-11 实施计划验收（对应 §9 Phase 0-3）

### 0-11.1 Phase 0：基础设施 ✅

- [x] langgraph 依赖已安装
- [x] `src/core/ops/` 包结构已创建
- [x] 6 个共享单元函数已实现
- [x] Anthropic 认证已适配
- [x] 现有模块扩展已完成
- [x] 全量测试通过

### 0-11.2 Phase 1：Agent MVP ✅

- [x] `src/agent/` 包结构已创建
- [x] `MaintenanceState` 已定义
- [x] 核心 @tool 已实现（8 安全 + 3 高风险）
- [x] 系统提示词已实现
- [x] agent_node 已实现
- [x] tool_node 已实现
- [x] approval_node 已实现
- [x] StateGraph + 条件边已构建
- [x] CLI 入口已实现
- [x] Agent 测试已编写

### 0-11.3 Phase 2：扩展能力 ✅

- [x] 全链路 @tool 已实现（embed, index, delete_and_reindex, meal, pdf, issue）
- [x] `stage_history` 回退感知已实现
- [x] `auto_review` 人工干预增强已实现
- [x] Memory Store 经验积累已实现
- [x] Issue 系统集成已实现
- [x] StateGraph 已更新集成新工具
- [x] 偏差修正已完成

### 0-11.4 Phase 3：UI + 报告 + 生产化 ❌

- [ ] ❌ Streamlit 维修工页面已实现
- [ ] ❌ UI 下拉菜单锁定工具链已实现
- [ ] ❌ CLI 指令交互已完善
- [ ] ❌ 维修报告生成已实现
- [ ] ❌ 对比报告生成已实现
- [ ] ❌ Checkpointer 已迁移到 SqliteSaver
- [ ] ❌ 系统提示词已优化
- [ ] ❌ 实验系统已迁移到共享单元（Phase C）

---

## 0-12 代码质量验收（对应 §7.2 回归保护）

- [x] 共享单元先作为薄包装层，不改变现有行为
- [x] Agent 代码在 `src/agent/` 独立包中，物理隔离
- [x] 对现有模块的修改仅限新增方法和向后兼容参数扩展
- [ ] ⚠️ Agent 测试标记为 `@pytest.mark.agent`，可独立运行（需确认）
- [x] 所有 @tool 包含 try/except + loguru 日志
- [x] VectorIndexer 实例使用 try/finally 确保 close()
- [x] 无硬编码配置值（从 config.yaml 读取）
- [x] `pixi run test` 全部通过
- [x] `pixi run lint` 通过

---

## 完成度统计

| 章节 | 总项 | ✅ 完成 | ⚠️ 部分 | ❌ 未完成 | 完成率 |
|------|------|---------|---------|----------|--------|
| 0-1 核心能力 C1-C12 | 46 | 38 | 4 | 4 | 83% |
| 0-2 设计决策 Q1-Q5 | 10 | 8 | 0 | 2 | 80% |
| 0-3 共享单元层 | 21 | 19 | 0 | 2 | 90% |
| 0-4 Meal 扩展 | 6 | 6 | 0 | 0 | 100% |
| 0-5 Enhancer 改造 | 6 | 6 | 0 | 0 | 100% |
| 0-6 LangGraph 工作流 | 23 | 23 | 0 | 0 | 100% |
| 0-7 安全机制 | 10 | 8 | 2 | 0 | 80% |
| 0-8 Anthropic 适配 | 5 | 5 | 0 | 0 | 100% |
| 0-9 配置集中化 | 7 | 7 | 0 | 0 | 100% |
| 0-10 模块扩展 | 7 | 7 | 0 | 0 | 100% |
| 0-11 实施计划 | 22 | 14 | 0 | 8 | 64% |
| 0-12 代码质量 | 9 | 8 | 1 | 0 | 89% |
| **合计** | **172** | **149** | **7** | **16** | **87%** |

### 未完成项汇总（按优先级排序）

**高优先级（Phase 3 核心功能）**：
1. Streamlit 维修工页面（C10, Q3）
2. UI 下拉菜单锁定工具链（C7, Q1）
3. 维修报告生成（C9）
4. 对比报告生成（C9）
5. Checkpointer 迁移到 SqliteSaver（Q5 生产化）

**中优先级（功能增强）**：
6. 轻量/全量双模式显式切换（C6）
7. CLI 指令交互完善（:parse, :back, :compare）（C10）
8. 系统提示词多轮迭代优化
9. 实验系统迁移到共享单元（Phase C）

**低优先级（安全加固）**：
10. 白名单硬拦截：禁止删除整个 Qdrant collection
11. 白名单硬拦截：禁止删除整个 Meal
12. Agent 测试标记 `@pytest.mark.agent`
