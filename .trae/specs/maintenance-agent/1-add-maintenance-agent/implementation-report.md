# 维修工 Agent 实施报告

> 日期：2026-05-04
> 分支：`agent-maintainer`
> 基于：`v0.1.16` (e2e5b61)
> 变更统计：28 files changed, +4031 / -683 lines

---

## 一、总体概述

本次实施完成了维修工 Agent 的 **Phase 0（共享单元层 + 基础设施）** 和 **Phase 1（Agent MVP）** 以及 **Phase 2 的核心高风险工具**，使项目具备了以下能力：

1. **共享操作层**：将 RAG 管线的解析、分块、嵌入、索引、查询、评估六大环节封装为独立可调用的函数，为 Agent 和未来重构提供统一接口
2. **LangGraph Agent**：基于 StateGraph 的 ReAct 循环 Agent，可自主诊断 RAG 管线问题并执行修复
3. **安全机制**：高风险操作通过 `interrupt()` 实现人工审批，防止误操作
4. **CLI 入口**：通过 `pixi run agent` 即可启动交互式维修工

---

## 二、Phase 0：共享单元层 + 基础设施 + 现有模块扩展

### 2.1 依赖管理

| 依赖 | 来源 | 用途 |
|------|------|------|
| `langgraph` | PyPI | Agent StateGraph 框架 |
| `langchain-core` | PyPI | LangChain 核心类型（BaseMessage, @tool 等） |
| `langchain-anthropic` | 已有 | ChatAnthropic LLM 客户端 |

提交：`7df016b feat: add langgraph and langchain-core dependencies for maintenance agent`

### 2.2 共享操作层 `src/core/ops/`

新建 `src/core/ops/` 包，包含 6 个子模块：

| 子模块 | 函数 | 说明 |
|--------|------|------|
| `parse.py` | `parse_pdf()` | 包装 ParserRegistry，支持 composite 和 legacy 解析器 |
| | `enhance_page()` | 单页表格增强（1-indexed page_number） |
| | `enhance_table()` | 单表格增强（1-indexed page_number + table_index） |
| `chunk.py` | `chunk_parsed()` | 按 strategy 分发到 fixed/page_aware/semantic，含 `parent_chunk_config` 预留 |
| `embed.py` | `embed_chunks()` | 包装 Embedder.embed_texts()，返回 list[list[float]] |
| `index.py` | `index_chunks()` | 创建 collection → 嵌入 → 索引 |
| | `delete_source_and_reindex()` | 按 source 删除旧向量 → 嵌入新块 → 增量 upsert |
| `query.py` | `query_rag()` | 包装 RAGPipeline.query() |
| `evaluate.py` | `evaluate_single()` | Phase A 基础指标（context_relevance, answer_relevancy, hit_rate） |

提交：`7df016b`（依赖）+ `0f5f88c`（包结构）+ Phase 0 合并提交

### 2.3 LangChain Anthropic 适配

在 `src/llm_client.py` 新增 `create_langchain_anthropic_client()`：

- 复用现有 `Authorization: Bearer` 认证模式
- 使用 `ChatAnthropic` 的 `anthropic_api_key`, `anthropic_api_url`, `model` 参数
- 懒加载 `langchain_anthropic` 避免重导入

### 2.4 现有模块扩展

| 模块 | 新增方法/字段 | 说明 |
|------|-------------|------|
| `PdfPlumberEnhancer` | `enhance_page(pdf_path, page_number, existing_text)` | 单页增强，1-indexed |
| | `enhance_table(pdf_path, page_number, table_index, existing_text)` | 单表格增强，1-indexed |
| `ParserRegistry` | `get_enhancer(enhancer_name, enhancer_options)` | 获取增强器实例 |
| `VectorIndexer` | `delete_by_source(source)` | Qdrant filter-based 删除，返回删除数量 |
| | `upsert_chunks(chunks, embeddings, batch_size)` | UUID-based 增量插入，避免 ID 冲突 |
| `MealConfig` | `creation_mode: str = "random"` | 新增字段，向后兼容 |
| `MealManager` | `create_meal_manual(name, pdf_files, source_dir, file_pattern, tags, description, ...)` | 手动创建 meal |
| `ArtifactCache` | `update_manifest_entry(data_id, key, value)` | 原子性增量更新 manifest |

提交：`05e57ce feat: extend existing modules for maintenance agent support`

### 2.5 Phase 0 测试

- `pixi run test`：**1991 passed, 0 failed**（全量无回归）
- `pixi run lint`：通过

---

## 三、Phase 1：Agent MVP

### 3.1 包结构

```
src/agent/
├── __init__.py     # 包标记
├── state.py        # MaintenanceState TypedDict
├── tools.py        # 11 个 @tool 定义
├── prompt.py       # 系统提示词
├── graph.py        # StateGraph 构建 + 编译
└── cli.py          # 交互式 CLI
```

### 3.2 状态模型 `MaintenanceState`

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | `Annotated[list, add_messages]` | LangGraph 消息列表，自动追加 |
| `current_meal` | `str \| None` | 当前操作的 meal |
| `current_source` | `str \| None` | 当前操作的数据源 |
| `diagnosis` | `list[dict]` | 诊断结果列表 |
| `pending_action` | `dict \| None` | 待执行的高风险操作 |
| `approved` | `bool \| None` | 用户审批结果 |
| `execution_log` | `list[str]` | 操作执行日志 |

### 3.3 工具定义

**8 个安全工具**（无需审批）：

| 工具名 | 功能 | 包装的共享单元 |
|--------|------|--------------|
| `list_meals` | 列出所有 meal | MealManager.list_meals() |
| `get_meal_detail` | 查看 meal 详情 | MealManager.load_meal() |
| `query_rag_tool` | 测试 RAG 查询 | query_rag() |
| `parse_pdf_tool` | 解析 PDF | parse_pdf() |
| `enhance_page_tool` | 单页表格增强 | enhance_page() |
| `chunk_parsed_tool` | 解析+分块 | parse_pdf() + chunk_parsed() |
| `evaluate_answer_tool` | 评估回答质量 | evaluate_single() |
| `get_index_info` | 查看索引状态 | VectorIndexer.get_collection_info() |

**3 个高风险工具**（需 interrupt 审批）：

| 工具名 | 功能 | 包装的共享单元 |
|--------|------|--------------|
| `rebuild_index` | 重建向量索引 | VectorIndexer.build_index() |
| `delete_source` | 删除数据源 | VectorIndexer.delete_by_source() |
| `update_meal` | 更新 meal 元数据 | ArtifactCache.update_manifest_entry() |

### 3.4 LangGraph 图结构

```
START → agent → (should_continue?) → approval → tools → agent → ...
                                ↓
                              __end__
```

- **agent_node**：调用 LLM（ChatAnthropic）with tools bound，返回 AI 消息
- **should_continue**：检查最后一条消息是否有 tool_calls，有则路由到 approval，否则结束
- **approval_node**：检查 tool_calls 中是否有 HIGH_RISK_TOOLS，有则 `interrupt()` 等待用户确认
  - 用户拒绝：替换为拒绝 ToolMessage，从 remaining_tool_calls 中移除
  - 用户批准：保留 tool_call，继续执行
- **tool_node**：执行所有 tool_calls，返回 ToolMessage 结果 + 执行日志

### 3.5 系统提示词

定义了维修工的三阶段工作流：
1. **诊断阶段**：查看 meal → 检查索引 → RAG 查询测试 → 解析/分块检查 → 评估
2. **分析阶段**：判断问题根源（解析/分块/检索/生成质量）
3. **修复阶段**：提出方案，高风险操作需用户确认

### 3.6 CLI 入口

`pixi run agent` 启动交互式 CLI：
- 输入问题进行诊断
- 遇到 interrupt 时提示用户确认（y/n）
- 显示执行日志
- 输入 `quit`/`exit` 退出

### 3.7 Phase 1 测试

`tests/test_agent.py`：**22 个测试**，覆盖：

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|---------|
| `TestMaintenanceState` | 2 | 状态创建、字段访问 |
| `TestHighRiskTools` | 2 | HIGH_RISK_TOOLS 集合成员检查 |
| `TestToolFunctions` | 10 | 8 个安全工具 + 2 个错误处理 |
| `TestGraphBuild` | 3 | build_graph, compile_agent, checkpointer |
| `TestShouldContinue` | 2 | 路由到 tools / END |
| `TestToolNode` | 1 | 未知工具处理 |
| `TestSystemPrompt` | 2 | 提示词内容检查 |

提交：`a07f359 feat: add maintenance agent MVP with LangGraph`

---

## 四、Phase 2（部分）：高风险工具 + pixi task

### 4.1 高风险工具实现

在 `src/agent/tools.py` 中新增：

- **`rebuild_index(meal_name, rebuild=True)`**：获取 meal 的 pipeline → 重建 collection → 从 chunks 目录构建索引
- **`delete_source(meal_name, source)`**：获取 meal 的 pipeline → 调用 `indexer.delete_by_source()`
- **`update_meal(meal_name, updates)`**：白名单字段（description, tags）→ 调用 `cache.update_manifest_entry()`

### 4.2 pixi task 注册

```toml
[tasks.agent]
cmd = "python -m src.agent.cli"
```

使用方式：`pixi run agent`

### 4.3 全量测试

- `pixi run test`：**2013 passed, 0 failed**
- `pixi run lint`：通过

---

## 五、Git 提交记录

| 提交 | 说明 |
|------|------|
| `7df016b` | feat: add langgraph and langchain-core dependencies |
| `0f5f88c` | fix: add trailing newline to src/core/__init__.py |
| `05e57ce` | feat: add shared ops layer and LangChain Anthropic adapter |
| `a07f359` | feat: add maintenance agent MVP with LangGraph |
| `1863062` | style: ruff-format tools.py (high-risk tools + pixi task) |
| `9f2358f` | style: ruff-fix and format test_agent.py |
| `4d8e18a` | docs: update checklist.md |
| `7995b70` | docs: update tasks.md |

---

## 六、架构决策与设计说明

### 6.1 扁平化包结构 vs 嵌套子包

Spec 原计划创建 `nodes/`, `tools/`, `prompts/`, `memory/`, `reporters/` 等子包。实际实施采用扁平结构（`tools.py`, `prompt.py`, `graph.py`），原因：

- 当前 11 个 @tool 数量不多，单文件可维护
- LangGraph 的 ReAct 模式下，节点函数和工具定义紧密耦合，拆分子包增加导入复杂度
- 后续如需扩展，可按需拆分

### 6.2 approval_node 设计

采用独立的 `approval_node` 而非在 `tool_node` 中嵌入审批逻辑，原因：

- 职责分离：审批与执行是不同关注点
- 可测试性：approval_node 可独立测试
- 可扩展性：未来可在 approval_node 中添加更多审批逻辑（如自动审批低风险操作）

### 6.3 共享单元层 Phase A 策略

`evaluate_single()` 当前使用 LLM-free 的基础指标（Jaccard 词重叠），而非调用 BuiltinEvaluator，原因：

- BuiltinEvaluator 依赖重导入（ragas/torch），会拖慢 Agent 启动
- Phase A 优先保证接口可用，Phase B/C 再迁移到完整评估器
- 基础指标足以支持 Agent 的初步诊断决策

### 6.4 MealManager.create_meal_manual() vs 扩展 create_meal()

新增 `create_meal_manual()` 而非修改 `create_meal()`，原因：

- `create_meal()` 的参数签名已稳定，修改会破坏向后兼容
- 手动模式的参数（pdf_files, source_dir, file_pattern）与采样模式完全不同
- 新方法更清晰，避免一个函数承担两种职责

---

## 七、待后续迭代

| Phase | 任务 | 优先级 |
|-------|------|--------|
| Phase 2 | Command(goto=...) 回退跳转 | 中 |
| Phase 2 | Memory Store 经验积累 | 中 |
| Phase 2 | Issue 系统集成（create_issue, list_issues, close_issue） | 中 |
| Phase 2 | 更多 interrupt 点（parse_node, chunk_node 结果审查） | 低 |
| Phase 3 | Streamlit 维修工页面 | 中 |
| Phase 3 | 维修报告 + 对比报告生成 | 中 |
| Phase 3 | SqliteSaver 持久化替换 InMemorySaver | 高 |
| Phase 3 | 系统提示词优化（多轮迭代） | 低 |
| Phase 3 | 实验系统迁移到共享单元（Phase C） | 低 |

---

## 八、文件清单

### 新增文件（18 个）

```
src/agent/__init__.py
src/agent/cli.py
src/agent/graph.py
src/agent/prompt.py
src/agent/state.py
src/agent/tools.py
src/core/__init__.py
src/core/ops/__init__.py
src/core/ops/chunk.py
src/core/ops/embed.py
src/core/ops/evaluate.py
src/core/ops/index.py
src/core/ops/parse.py
src/core/ops/query.py
tests/test_agent.py
.trae/specs/add-maintenance-agent/spec.md
.trae/specs/add-maintenance-agent/tasks.md
.trae/specs/add-maintenance-agent/checklist.md
```

### 修改文件（6 个）

```
pixi.toml                    # +langgraph, +langchain-core, +agent task
src/llm_client.py            # +create_langchain_anthropic_client()
src/indexer.py               # +delete_by_source(), +upsert_chunks()
src/meal/models.py           # +creation_mode field
src/meal/manager.py          # +create_meal_manual()
src/meal/cache.py            # +update_manifest_entry()
src/parsers/pdfplumber_enhancer.py  # +enhance_page(), +enhance_table()
src/parsers/registry.py      # +get_enhancer()
```
