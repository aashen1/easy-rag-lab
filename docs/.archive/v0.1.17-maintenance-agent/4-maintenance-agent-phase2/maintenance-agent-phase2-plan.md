# 维修工 Agent：偏差修正 + Phase 2 完整实现计划

> 日期：2026-05-04
> 分支：`agent-maintainer`
> 前置：Phase 0 + Phase 1 + Phase 2.1 已验收通过

***

## 一、已观察偏差及修正计划

### 偏差 1：`delete_source` 缺少备份（高优先级）

**现状**：`delete_source` 工具执行前仅记录日志，无任何数据备份。Spec 明确要求"写操作前自动备份到 `.trashbin/`"。

**数据量分析**：

* `data/vector_store/` 总计 2.2 GB，单个 collection 最大 528 MB（一个 `storage.sqlite` 文件）

* `delete_source` 删除的是 Qdrant 中某个 source 对应的向量点（payload + vector），不是文件

* 一个 PDF 对应几十到几百个 chunks，每个 chunk 的 payload ≈ 几百 bytes，1024 维 float32 向量 ≈ 4 KB

* 删除 1 个 source 的 points 元数据导出 ≈ 几十 KB \~ 几百 KB

**修复方案**：在 `VectorIndexer` 中新增 `scroll_by_source()` 方法，用 Qdrant `client.scroll()` 按 source filter 检索将被删除的 points（仅 payload，不含 vector），序列化为 JSON 保存到 `.trashbin/`。然后在 `delete_source` 工具中调用此方法，在 `delete_by_source()` 之前先备份。

**具体步骤**：

1. `src/indexer.py`：新增 `scroll_by_source(source, with_vectors=False)` 方法
2. `src/agent/tools.py`：`delete_source` 中调用 `scroll_by_source` → 导出 JSON 到 `.trashbin/` → 再执行 `delete_by_source`
3. 补充单元测试

### 偏差 2：硬编码配置值（低优先级，本次一并修正）

**现状**：tools.py、graph.py、index.py、cli.py 中多处硬编码默认值。

**修复方案**：在 `config.yaml` 新增 `agent` 配置段，在 `src/agent/config.py` 中提供配置加载函数，各模块从配置读取默认值。

**具体位置**：

| 文件                | 硬编码项                                  | 配置键                                 |
| ----------------- | ------------------------------------- | ----------------------------------- |
| tools.py L159     | `parser_name="pymupdf4llm"`           | `agent.defaults.parser_name`        |
| tools.py L199     | `enhancer_name="pdfplumber"`          | `agent.defaults.enhancer_name`      |
| tools.py L228-229 | `chunk_size=512, overlap=0`           | `agent.defaults.chunk_size/overlap` |
| graph.py L54      | `model_name` 通过 `get_llm_config` 已解决  | —                                   |
| index.py L13      | `collection_name="financial_reports"` | `agent.defaults.collection_name`    |
| cli.py L41        | `thread_id="maintenance-session"`     | `agent.defaults.thread_id`          |

### 偏差 3：`parse.py` 共享单元缺少 try/except（低优先级）

**现状**：`src/core/ops/parse.py` 中 `parse_pdf()`、`enhance_page()`、`enhance_table()` 三个 IO 函数无 try/except，违反项目规范"所有 IO 操作必须有 try/except"。

**修复方案**：为三个函数添加 try/except，捕获异常后记录 loguru 日志并 re-raise。

### 偏差 4：每次 agent\_node 重建 LLM 客户端（性能，低优先级）

**现状**：`_get_llm()` 和 `_get_tools()` 每次 `agent_node` 调用时都重新创建。

**修复方案**：使用模块级缓存（`functools.lru_cache` 或简单变量），在首次调用时创建并复用。

***

## 二、Phase 2 完整实现计划

### Task 2.2：全链路 @tool（embed/index/meal/issue）

**新增 6 个 @tool**：

| 工具名                       | 类型  | 包装的共享单元                                 | 说明                  |
| ------------------------- | --- | --------------------------------------- | ------------------- |
| `embed_chunks_tool`       | 安全  | `embed_chunks()`                        | 嵌入 chunks 列表        |
| `index_chunks_tool`       | 安全  | `index_chunks()`                        | 索引 chunks 到向量库      |
| `delete_and_reindex_tool` | 高风险 | `delete_source_and_reindex()`           | 按 source 删除旧向量并重新索引 |
| `create_curated_meal`     | 安全  | `MealManager.create_meal_manual()`      | 手动创建 Meal           |
| `list_pdfs`               | 安全  | 直接 glob data/raw/                       | 列出可用 PDF 文件         |
| `create_issue`            | 安全  | `subprocess` 调用 `pixi run issue create` | 创建 Issue            |
| `list_issues`             | 安全  | `subprocess` 调用 `pixi run issue list`   | 列出 Issue            |
| `close_issue`             | 安全  | `subprocess` 调用 `pixi run issue done`   | 关闭 Issue            |

**实现要点**：

* Issue 工具使用 `subprocess.run(["pixi", "run", "issue", ...])` 包装现有 CLI，避免重写逻辑

* `delete_and_reindex_tool` 加入 `HIGH_RISK_TOOLS` 集合

* `create_curated_meal` 需要先 `list_pdfs` 让 LLM 知道有哪些 PDF 可用

* 所有新工具遵循现有模式：try/except + loguru + JSON 返回

### Task 2.3：Command(goto=...) 回退跳转

**现状**：当前 StateGraph 是线性循环 `agent → approval → tools → agent`，无跳转能力。

**设计**：在 `agent_node` 中检测用户回退指令（如"回到解析阶段"），返回 `Command(goto=..., update={...})` 跳转到指定阶段。

**但当前架构是 ReAct 模式**（agent 决策 → 单个 tool 调用 → 回到 agent），不是 Spec 原始设计的多节点跳转（parse\_node → chunk\_node → embed\_node...）。ReAct 模式下，"回退"本质上是 LLM 重新选择工具——不需要 `Command(goto=...)`，因为 agent 每次都会重新决策。

**决策**：Phase 2 的回退跳转**不采用 Command(goto=...) 模式**，而是：

1. 在 `MaintenanceState` 中新增 `stage_history: list[str]` 字段，记录已执行的工具名
2. 在系统提示词中增加"回退"指令说明，告知 LLM 可以重新选择之前的工具
3. 在 `agent_node` 中将 `stage_history` 注入系统提示词，让 LLM 知道已经做了什么
4. 如果未来需要真正的非线性工作流（如自动 pipeline），再引入 Command(goto=...)

**具体步骤**：

1. `state.py`：新增 `stage_history` 字段
2. `graph.py`：`tool_node` 执行后更新 `stage_history`
3. `prompt.py`：注入 `stage_history` 到系统提示词
4. 更新测试

### Task 2.4：interrupt() 人工干预增强

**现状**：interrupt 仅在 `approval_node` 中使用（高风险操作审批）。

**增强方案**：在关键工具执行后，如果结果可能需要用户审查，提供可选的 interrupt 点。但**不强制 interrupt**——因为 ReAct 模式下 LLM 会自动决定下一步，频繁 interrupt 会打断工作流。

**具体实现**：

1. 在 `MaintenanceState` 中新增 `auto_review: bool` 字段（默认 False）
2. 当 `auto_review=True` 时，`tool_node` 执行完解析/分块工具后自动 interrupt 展示结果摘要
3. 用户可通过 CLI 指令 `:review on/off` 切换
4. 不修改现有 approval\_node 逻辑

### Task 2.5：Memory Store 经验积累

**设计**：使用 LangGraph 的 `InMemoryStore`（开发）/ 持久化 Store（生产），按 namespace 组织经验。

**namespace 设计**：`(user_id, "maintenance_experience", pdf_type)`，其中 `pdf_type` 从 PDF 文件名推断（如"年报"/"研报"）。

**经验结构**：

```python
{
    "pdf_type": "annual_report",
    "best_parser": "pymupdf4llm+pdfplumber",
    "best_chunk_strategy": "page_aware",
    "best_chunk_size": 512,
    "reason": "年报表格多，fitz+pdfplumber 组合效果最好",
    "timestamp": "2026-05-04T10:30:00",
}
```

**具体步骤**：

1. `src/agent/memory/experience_store.py`：封装 InMemoryStore 的存取逻辑

   * `save_experience(namespace, experience)` — 保存经验

   * `search_experiences(namespace, query)` — 检索相关经验

   * `get_all_experiences(namespace)` — 获取全部经验
2. `graph.py`：`compile_agent()` 接受 `store` 参数
3. `agent_node`：从 store 检索经验注入系统提示词
4. `tool_node`：当发现好的配置组合时，自动保存经验
5. `cli.py`：创建 InMemoryStore 并传给 compile\_agent
6. 更新测试

### Task 2.6：Issue 系统集成

**设计**：包装现有 `pixi run issue` CLI，不重写逻辑。

**三个 @tool**：

* `create_issue(title, issue_type, priority, labels)` → `pixi run issue create -t {type} -T "{title}" -p {priority} -l {labels}`

* `list_issues(status, issue_type)` → `pixi run issue list --status {status} --type {type} --all`

* `close_issue(issue_id, resolution)` → `pixi run issue done {issue_id}`

**Agent 主动建议**：在系统提示词中增加规则——"诊断发现系统性问题时，主动建议用户创建 Issue"。

**具体步骤**：

1. `src/agent/tools.py`：新增 3 个 @tool
2. `prompt.py`：增加 Issue 相关提示词
3. 更新测试

### Task 2.7：StateGraph 更新集成全链路节点

**现状**：StateGraph 只有 3 个节点（agent, approval, tools），所有工具在 tool\_node 中统一执行。

**不需要新增独立节点**。当前 ReAct 模式下，tool\_node 已经能执行所有 @tool，新增工具只需注册到 `_get_tools()` 和 `HIGH_RISK_TOOLS` 即可。Spec 原始设计的多节点架构（parse\_node, chunk\_node 等）在 ReAct 模式下不适用。

**需要做的**：

1. `_get_tools()` 中注册所有新工具
2. `HIGH_RISK_TOOLS` 集合新增 `delete_and_reindex_tool`
3. 系统提示词更新，说明新增工具
4. `MaintenanceState` 新增字段（stage\_history, auto\_review）

### Task 2.8：Phase 2 测试

* 新增工具的存在性和参数测试

* `scroll_by_source()` 单元测试

* `delete_source` 备份流程测试

* Issue 工具 mock 测试（mock subprocess）

* Memory Store 存取测试

* stage\_history 更新测试

* 全量回归测试

***

## 三、实施顺序

按依赖关系排序，分 4 个提交批次：

### 批次 A：偏差修正（不依赖 Phase 2 新功能）

| 步骤 | 内容                                                 | 产出                 |
| -- | -------------------------------------------------- | ------------------ |
| A1 | `src/indexer.py`：新增 `scroll_by_source()`           | 按 source 检索 points |
| A2 | `src/agent/tools.py`：`delete_source` 增加备份逻辑        | 安全机制补全             |
| A3 | `src/core/ops/parse.py`：三个函数加 try/except           | 规范合规               |
| A4 | `config.yaml`：新增 `agent` 配置段                       | 配置集中化              |
| A5 | `src/agent/config.py`：新增配置加载模块                     | 配置读取               |
| A6 | `src/agent/tools.py` + `graph.py` + `cli.py`：替换硬编码 | 配置驱动               |
| A7 | `src/agent/graph.py`：LLM 客户端缓存                     | 性能优化               |
| A8 | 补充单元测试                                             | 质量保障               |
| A9 | `pixi run test` + `pixi run lint`                  | 回归确认               |

### 批次 B：全链路工具 + Issue 集成

| 步骤 | 内容                                              | 产出         |
| -- | ----------------------------------------------- | ---------- |
| B1 | `src/agent/tools.py`：新增 embed/index/meal/pdf 工具 | 6 个新 @tool |
| B2 | `src/agent/tools.py`：新增 Issue 工具                | 3 个新 @tool |
| B3 | `src/agent/tools.py`：更新 HIGH\_RISK\_TOOLS       | 安全集合       |
| B4 | `src/agent/graph.py`：`_get_tools()` 注册新工具       | 图更新        |
| B5 | 补充单元测试                                          | 质量保障       |
| B6 | `pixi run test` + `pixi run lint`               | 回归确认       |

### 批次 C：回退跳转 + 人工干预 + 系统提示词

| 步骤 | 内容                                                         | 产出     |
| -- | ---------------------------------------------------------- | ------ |
| C1 | `src/agent/state.py`：新增 stage\_history, auto\_review 字段    | 状态扩展   |
| C2 | `src/agent/graph.py`：tool\_node 更新 stage\_history          | 历史追踪   |
| C3 | `src/agent/prompt.py`：注入 stage\_history + 新工具说明 + Issue 规则 | 提示词增强  |
| C4 | `src/agent/cli.py`：支持 `:review on/off` 指令                  | CLI 增强 |
| C5 | 补充单元测试                                                     | 质量保障   |
| C6 | `pixi run test` + `pixi run lint`                          | 回归确认   |

### 批次 D：Memory Store 经验积累

| 步骤 | 内容                                              | 产出     |
| -- | ----------------------------------------------- | ------ |
| D1 | `src/agent/memory/experience_store.py`：封装存取逻辑   | 经验存储   |
| D2 | `src/agent/graph.py`：compile\_agent 接受 store 参数 | 图集成    |
| D3 | `src/agent/graph.py`：agent\_node 检索经验注入提示词      | 经验检索   |
| D4 | `src/agent/graph.py`：tool\_node 自动保存经验          | 经验积累   |
| D5 | `src/agent/cli.py`：创建 InMemoryStore 并传入         | CLI 集成 |
| D6 | 补充单元测试                                          | 质量保障   |
| D7 | `pixi run test` + `pixi run lint`               | 回归确认   |

***

## 四、不在本次范围内的项（Phase 3）

以下留待 Phase 3，不在本次实现：

* Streamlit 维修工页面（Task 3.1）

* UI 下拉菜单锁定工具链（Task 3.2）

* CLI 指令交互完善（:parse, :back, :compare）（Task 3.3）

* 维修报告 + 对比报告生成（Task 3.4）

* Checkpointer 迁移到 SqliteSaver（Task 3.5）

* 系统提示词多轮迭代优化（Task 3.6）

* 实验系统迁移到共享单元 Phase C（Task 3.7）

* 完整测试 + 文档（Task 3.8）

***

## 五、关键设计决策记录

1. **回退跳转不采用 Command(goto=...)**：当前 ReAct 模式下 agent 每次都重新决策，"回退"本质是 LLM 重新选择工具，不需要图级跳转。用 stage\_history 让 LLM 感知历史即可。
2. **Issue 工具用 subprocess 包装 CLI**：避免重写逻辑，复用现有 `pixi run issue` 的全部能力。
3. **delete\_source 备份用 scroll\_by\_source + JSON 导出**：不复制整个 SQLite 文件（528 MB），仅导出将被删除的 points 元数据（几十 KB \~ 几百 KB）。
4. **Memory Store 用 InMemoryStore**：开发阶段用内存 Store，Phase 3 再迁移到持久化 Store。
5. **auto\_review 默认关闭**：避免频繁 interrupt 打断 ReAct 工作流，用户按需开启。
