# 深度验收计划：`better-badcase-tracker` 分支 vs `dev`

> GLM-5.1

## 分支概览

| 项目 | 值 |
|------|-----|
| 当前分支 | `better-badcase-tracker` |
| 对比基准 | `dev` |
| Commit 数 | 17 |
| 变更文件 | 31 |
| 代码行数 | +5600 / -137 |
| 测试 | 1984 passed, ruff all clean |

---

## 一、功能模块梳理（按逻辑分层）

### 第 1 层：多轮对话基础能力

| Commit | 模块 | 变更 |
|--------|------|------|
| `82959eb` | [generator.py](file:///b/project/w0-easy-rag/src/generator.py) | `Generator.generate()` 新增 `chat_history` 参数，支持多轮上下文传入 LLM |
| `6287147` | [pipeline.py](file:///b/project/w0-easy-rag/src/pipeline.py) | `RAGPipeline.query()` 新增 `chat_history` 参数，透传给 Generator |
| `3bd5004` | [case_collector.py](file:///b/project/w0-easy-rag/src/case_collector.py) | `save_case` / `load_case` 支持 `chat_history` 字段落盘/读取；新增 `save_case_with_dedup` 共享去重函数 |

**验收要点**：
- [ ] `chat_history` 格式为 `[{"role": "user"/"assistant", "content": "..."}]`，与 Anthropic API 兼容
- [ ] `save_case_with_dedup` 去重逻辑：同 question 同 type → DUPLICATE；同 question 不同 type → TYPE_CHANGED（删除旧 case 创建新 case）
- [ ] `load_case` 能正确读取 `chat_history.json`

### 第 2 层：CLI 交互式问答增强

| Commit | 模块 | 变更 |
|--------|------|------|
| `b215b64` | [query_history.py](file:///b/project/w0-easy-rag/src/query_history.py) | **新模块**：QueryHistory 环形缓冲区，CLI 单次查询模式历史管理 |
| `4d3d7cf` | [case_collector.py](file:///b/project/w0-easy-rag/src/case_collector.py) | 新增 `delete_case`、`convert_case`、`find_case_by_question` |
| `bc81ab3` | [main.py](file:///b/project/w0-easy-rag/main.py) | CLI 集成 `--history-*` 命令，支持去重/转换 |
| `3c2664e` | [interactive_qa.py](file:///b/project/w0-easy-rag/src/interactive_qa.py) | **新模块**：从 main.py 提取 `_interactive_qa`，增强为多轮对话 + case 收集 |
| `c22c704` | [main.py](file:///b/project/w0-easy-rag/main.py) | CLI 交互式问答增强，支持 `/badcase`、`/goodcase`、`/history`、`/clear`、`/help` 斜杠命令 |

**验收要点**：
- [ ] `QueryHistory` 环形缓冲区：超 `max_entries` 自动淘汰最旧记录
- [ ] `delete_case` 遵守 trashbin 规则（移入 `.trashbin/` 而非永久删除）
- [ ] `convert_case` 流程：load → save new → delete old
- [ ] `interactive_qa` 的 `/badcase N` / `/goodcase N` 正确解析 1-based 索引
- [ ] 斜杠命令大小写不敏感（`/Help` 也能工作？→ 当前仅小写匹配，需确认）

### 第 3 层：管线追踪（Pipeline Trace）

| Commit | 模块 | 变更 |
|--------|------|------|
| `10a23c9` | [trace_models.py](file:///b/project/w0-easy-rag/src/trace_models.py) | **新模块**：`PipelineTrace`、`TraceStep`、`GroundTruth`、`DiagnosisResult` 数据模型 + 常量 |
| `10a23c9` | [pipeline.py](file:///b/project/w0-easy-rag/src/pipeline.py) | `query()` 新增 `capture_trace=True` 参数，5 阶段追踪（query_rewrite → retrieval → rerank → context_assembly → generation） |
| `7edd546` | [case_collector.py](file:///b/project/w0-easy-rag/src/case_collector.py) | `save_case` 支持 `trace` 参数落盘为 `pipeline_trace.json`；`load_case` 读取 trace；新增 `save_ground_truth`、`save_diagnosis` |

**验收要点**：
- [ ] `capture_trace=False`（默认）时行为与 dev 分支完全一致，零侵入
- [ ] `capture_trace=True` 时，5 个阶段均正确记录 timing + input/output
- [ ] `TraceStep` / `PipelineTrace` 的 `to_dict()` / `from_dict()` 可正确序列化/反序列化
- [ ] `DiagnosisResult` 包含 `root_cause_id`（RC-0~RC-5）、`severity`、`finding`、`fix_suggestion`、`config_patch`、`confidence`
- [ ] `GroundTruth` 包含 `answer_text`、`source_pdf`、`source_page`、`chunk_ids`

### 第 4 层：Bad Case 深度分析

| Commit | 模块 | 变更 |
|--------|------|------|
| `925c121` | [retrieval_analyzer.py](file:///b/project/w0-easy-rag/src/retrieval_analyzer.py) | **新模块**：`compute_ground_truth_metrics` — 对比 GT chunk_ids 与 trace 各阶段结果 |
| `925c121` | [case_diagnoser.py](file:///b/project/w0-easy-rag/src/case_diagnoser.py) | **新模块**：`diagnose()` — 基于指标自动归因（RC-0~RC-5） |
| `7edd546` | [ground_truth_finder.py](file:///b/project/w0-easy-rag/src/ground_truth_finder.py) | **新模块**：`find_chunks_by_source_page` — 按 PDF + 页码查找 chunk |

**根因分类体系**：

| ID | 名称 | 严重度 | 含义 |
|----|------|--------|------|
| RC-0 | healthy | low | GT 在 top-1 且答案匹配，可能是误标 |
| RC-1 | retrieval_miss | critical | GT chunk 完全未被检索到 |
| RC-2 | rank_too_low | medium | GT 在检索结果中但排名靠后 |
| RC-3 | context_dropped | high | GT 在检索结果中但被上下文截断丢弃 |
| RC-4 | generation_failure | medium | GT 在上下文中但 LLM 未正确利用 |
| RC-5 | query_mismatch | medium | 查询改写导致语义偏移 |

**验收要点**：
- [ ] `compute_ground_truth_metrics` 正确计算 7 个指标：found_in_retrieval, retrieval_rank, retrieval_score, found_in_rerank, rerank_rank, rerank_score, found_in_context, context_dropped
- [ ] `diagnose()` 的决策树覆盖所有 RC-0~RC-5 路径
- [ ] `find_chunks_by_source_page` 支持精确匹配 + 模糊匹配（页码范围）
- [ ] `save_ground_truth` / `save_diagnosis` 正确更新 manifest.json 的 `has_ground_truth` / `has_diagnosis` / `root_cause` 字段

### 第 5 层：Web UI 集成

| Commit | 模块 | 变更 |
|--------|------|------|
| `119f27c` | [qa_demo.py](file:///b/project/w0-easy-rag/src/app_pages/qa_demo.py) | 重构为 `save_case_with_dedup`；传递 `chat_history` + `capture_trace=True`；trace 数据存入 session_state |
| `7d8d92b` | [case_analyzer.py](file:///b/project/w0-easy-rag/src/app_pages/case_analyzer.py) | **新页面**：Bad Case 深度分析标签页（管线追踪可视化 + GT 标注 + 自动诊断） |
| `7d8d92b` | [app.py](file:///b/project/w0-easy-rag/src/app.py) | 新增「🔍 Bad Case 分析」标签页 |
| `c668b9a` | [test_app_smoke.py](file:///b/project/w0-easy-rag/tests/test_app_smoke.py) | Smoke test 更新 tab 数量 |

**验收要点**：
- [ ] Web UI 问答时自动 `capture_trace=True`，trace 不进入 `result`（用 `pop` 分离）
- [ ] Badcase 保存时 toast 提示"可到分析标签页深度分析"
- [ ] case_analyzer 页面：选择 case → 查看管线追踪 → 标注 GT → 自动诊断
- [ ] 诊断报告展示：root_cause_id 标签 + severity 颜色 + finding + fix_suggestion + config_patch

---

## 二、测试覆盖审查

| 测试文件 | 行数 | 覆盖模块 |
|----------|------|----------|
| [test_trace_models.py](file:///b/project/w0-easy-rag/tests/test_trace_models.py) | 260 | TraceStep, PipelineTrace, GroundTruth, DiagnosisResult 序列化/反序列化 |
| [test_query_history.py](file:///b/project/w0-easy-rag/tests/test_query_history.py) | 215 | QueryHistory CRUD、环形淘汰、去重、answer_preview 截断 |
| [test_case_collector.py](file:///b/project/w0-easy-rag/tests/test_case_collector.py) | 340 | save_case_with_dedup、chat_history、delete_case、convert_case、find_case_by_question |
| [test_interactive_qa.py](file:///b/project/w0-easy-rag/tests/test_interactive_qa.py) | 166 | 命令解析、消息解析、chat_history 构建 |
| [test_generator.py](file:///b/project/w0-easy-rag/tests/test_generator.py) | 121 | chat_history 传入、return_prompt_details |
| [test_retrieval_analyzer.py](file:///b/project/w0-easy-rag/tests/test_retrieval_analyzer.py) | 238 | compute_ground_truth_metrics 各场景 |
| [test_case_diagnoser.py](file:///b/project/w0-easy-rag/tests/test_case_diagnoser.py) | 245 | diagnose() RC-0~RC-5 全路径覆盖 |
| [test_ground_truth_finder.py](file:///b/project/w0-easy-rag/tests/test_ground_truth_finder.py) | 130 | find_chunks_by_source_page 精确/模糊/空匹配 |
| [test_pipeline.py](file:///b/project/w0-easy-rag/tests/test_pipeline.py) | +1 | chat_history=None 参数断言更新 |

**测试总量**：1984 passed ✅

---

## 三、潜在问题与风险点

### 🔴 高风险

1. **`capture_trace=True` 时 Generator 返回值类型变化**
   - `capture_trace=False`：`generate()` 返回 `str`
   - `capture_trace=True`：`generate(return_prompt_details=True)` 返回 `dict`
   - pipeline.py 中用 `if capture_trace` 分支处理，但需确认 Generator 内部逻辑无遗漏

2. **`convert_case` 数据丢失风险**
   - `convert_case` 只复制 `query_result`、`config_snapshot`、`meal_snapshot`
   - **丢失字段**：`chat_history`、`pipeline_trace`、`ground_truth`、`diagnosis` 均未迁移
   - 这意味着 bad→good 转换后，已标注的 GT 和诊断会丢失

### 🟡 中风险

3. **`interactive_qa` 中 `print` 代替 `logger`**
   - 用户交互输出用 `print` 合理，但错误信息也用 `print` 而非 `logger.error`
   - 当前已有 `logger.error` + `print` 双写，可接受

4. **`_build_chat_history` 函数重复**
   - `interactive_qa.py` 和 `qa_demo.py` 各有一份 `_build_chat_history`
   - 逻辑完全相同，应提取为共享工具函数

5. **`find_chunks_by_source_page` 性能**
   - 每次调用都扫描全部 JSONL 文件，无缓存
   - 对于大量 chunk 文件可能较慢，但当前规模可接受

### 🟢 低风险

6. **斜杠命令大小写敏感**
   - `/help`、`/clear`、`/history` 用 `lower()` 匹配 ✅
   - `/badcase`、`/goodcase` 也用 `lower()` 匹配 ✅
   - 但 `quit`/`exit`/`q` 也用 `lower()` ✅

7. **`trace_id` 哈希碰撞**
   - `hash(question) % 10000` 可能碰撞，但 trace_id 仅用于标识，不影响功能

8. **config.yaml 新增 `query_history` 段**
   - `max_entries: 10`、`dir: "data/query_history"` — 合理默认值

---

## 四、验收执行步骤

### Step 1：代码审查（只读）
- [ ] 确认 Generator.generate() 的 `return_prompt_details` 分支无副作用
- [ ] 确认 `convert_case` 数据丢失是否为预期行为
- [ ] 确认 `_build_chat_history` 重复代码是否需要提取

### Step 2：运行全量测试
- [ ] `pixi run test` — 已通过 ✅
- [ ] `pixi run ruff-check` — 已通过 ✅

### Step 3：功能验证（需手动/集成测试）
- [ ] CLI `pixi run python main.py --query "test"` 单次查询模式历史记录
- [ ] CLI `pixi run python main.py --interactive` 多轮对话 + `/badcase` 命令
- [ ] Web UI 问答 → 标记 Badcase → 切到分析标签页 → 标注 GT → 查看诊断
- [ ] 验证 case 目录结构：manifest.json + query_result.json + chat_history.json + pipeline_trace.json + ground_truth.json + diagnosis.json

### Step 4：边界场景验证
- [ ] 空 chat_history 传入 pipeline.query()
- [ ] 同一问题重复标记 badcase（去重）
- [ ] badcase → goodcase 转换（type changed）
- [ ] 无 reranker 时的 trace（无 rerank step）
- [ ] GT chunk 不在检索结果中（RC-1）

### Step 5：合并前检查
- [ ] 确认无未提交变更
- [ ] 确认分支可干净合并到 dev
- [ ] 确认文档同步（CLAUDE.md 版本号、docs/ 相关文档）

---

## 五、结论与建议

### 可合并项（无阻塞问题）
- 多轮对话基础能力 ✅
- 管线追踪 ✅
- CLI 交互式问答增强 ✅
- Bad Case 深度分析核心逻辑 ✅
- Web UI 集成 ✅

### 建议合并前修复
1. **`convert_case` 应迁移 `chat_history` 和 `pipeline_trace`**（数据完整性）
2. **`_build_chat_history` 提取为共享函数**（DRY 原则）

### 建议合并后跟进
1. `find_chunks_by_source_page` 添加缓存机制
2. 考虑 `interactive_qa` 的 `print` 输出统一为 rich 库格式化
3. 诊断决策树可考虑增加更多细分（如 RC-2 细分为"有 reranker 但排名仍低" vs "无 reranker"）
