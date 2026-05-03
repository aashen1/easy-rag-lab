# Bad Case 深度分析模式 — 实施计划

## 一、背景与目标

### 1.1 现状

项目已具备 Bad Case **收集**能力（`case_collector.py`），可将查询结果、配置快照、Meal 快照、环境信息落盘到 `data/cases/<case_id>/`。但**分析**层面完全空白：

- ❌ 无管线中间步骤的捕获（改写后的查询、重排序前后的结果、发给 LLM 的完整 Prompt）
- ❌ 无 Ground Truth 标注机制（用户无法指明正确答案来自哪个 PDF 哪一页）
- ❌ 无根因分类逻辑（是检索丢了？重排序排低了？还是 LLM 没用好？）
- ❌ 无交互式分析 UI（用户无法逐步追溯管线链路）

### 1.2 目标

构建 **Bad Case 深度分析模式**，让用户在标记 Bad Case 后，能够：

1. **逐步追溯** RAG 管线的每个阶段，看到完整的中间数据
2. **标注 Ground Truth**，指明正确答案来自哪个 PDF 的哪一页
3. **自动诊断根因**：系统自动判断问题出在检索、重排序还是生成阶段
4. **交互式对比**：查看分数变化、Prompt 内容、LLM 回复等

### 1.3 业界参考

| 工具 | 核心理念 | 我们借鉴什么 |
|------|---------|------------|
| **rag-debugger** (GitHub) | Trace Capture → 分析 trace.json | 管线 trace 数据模型设计 |
| **rag-doctor** (GitHub) | 6 类根因分类 + config_patch 建议 | 根因分类体系 + 修复建议 |
| **Maxim AI** | 分布式追踪 + 自动评估 + 质量告警 | 阶段化追踪思路 |
| **sourcemapr** | Evidence Observability：答案 → chunk → 原始文档的完整 lineage | Ground Truth 回溯设计 |

---

## 二、核心设计

### 2.1 Pipeline Trace 数据模型

新增 `PipelineTrace` 数据类，捕获 `query()` 执行的每一步中间结果：

```python
@dataclass
class TraceStep:
    stage: str              # "query_rewrite" | "retrieval" | "rerank" | "context_assembly" | "generation"
    input_data: dict        # 该阶段的输入
    output_data: dict       # 该阶段的输出
    duration_ms: float      # 耗时
    metadata: dict          # 额外信息（模型名、参数等）

@dataclass
class PipelineTrace:
    trace_id: str
    question: str
    steps: list[TraceStep]
    final_result: dict
    config_snapshot: dict
    created_at: str
```

**各阶段捕获内容**：

| 阶段 | 输入 | 输出 | 关键元数据 |
|------|------|------|-----------|
| query_rewrite | 原始问题 | 改写后的查询列表 + is_multi | 策略名、LLM 模型 |
| retrieval | 查询文本 + top_k | 检索结果列表（chunk_id, text, score, metadata） | 检索方法、top_k |
| rerank | 查询 + 检索结果 | 重排序结果列表（含 rerank_score） | reranker 模型、top_n |
| context_assembly | 截断后的 contexts + sources | 拼接后的完整 user_message | max_context_tokens、截断信息 |
| generation | system_prompt + user_message | LLM 回答 + token_usage | LLM 模型、temperature |

### 2.2 Ground Truth 标注模型

```python
@dataclass
class GroundTruth:
    answer_text: str                    # 正确答案文本
    source_pdf: str                     # 来源 PDF 文件名
    source_page: int | None            # 来源页码（可选）
    chunk_ids: list[str] | None        # 对应的 chunk ID（系统自动查找后填充）
    annotated_at: str                  # 标注时间
    annotator: str = "user"            # 标注者
```

### 2.3 根因分类体系

借鉴 rag-doctor 的 6 类根因，适配本项目：

| 根因 ID | 名称 | 含义 | 诊断逻辑 |
|---------|------|------|---------|
| RC-0 | healthy | 管线正常，可能是用户误标 | Ground Truth 在 top-1 且答案匹配 |
| RC-1 | retrieval_miss | 正确 chunk 未被召回 | Ground Truth chunk 不在检索结果中 |
| RC-2 | rank_too_low | 正确 chunk 被召回但排名靠后 | Ground Truth chunk 在结果中但不在 top-3 |
| RC-3 | context_dropped | 正确 chunk 被截断丢弃 | Ground Truth chunk 在检索结果中但被 context_assembly 截断 |
| RC-4 | generation_failure | 上下文包含正确信息但 LLM 未正确使用 | Ground Truth chunk 在最终 context 中但答案不匹配 |
| RC-5 | query_mismatch | 查询与文档词汇不匹配导致检索失败 | 查询改写后仍无法命中正确 chunk |

### 2.4 交互式分析流程

用户标记 Bad Case 后的分析流程：

```
用户点击 "Badcase" 按钮
    │
    ├─ 保存 case（现有逻辑）
    │
    └─ 弹出提示："是否启用深度分析？"
         │
         ├─ 选 "是" → 进入深度分析模式
         │    │
         │    ├─ Step 1: 管线链路总览
         │    │   展示 5 个阶段的流水线图，每个阶段显示关键指标
         │    │   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
         │    │   │ 查询改写  │ → │ 检索     │ → │ 重排序   │ → │ 上下文组装│ → │ 答案生成  │
         │    │   │ 1→1/3查询 │   │ top-5    │   │ top-5    │   │ 5 chunks │   │ 1 answer │
         │    │   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
         │    │
         │    ├─ Step 2: 逐阶段展开
         │    │   用户点击任一阶段 → 展示该阶段的完整输入/输出
         │    │
         │    ├─ Step 3: Ground Truth 标注
         │    │   用户指定：正确答案来自哪个 PDF 的哪一页
         │    │   系统自动：在向量库中查找该页对应的 chunk
         │    │
         │    ├─ Step 4: 自动根因诊断
         │    │   系统根据 Ground Truth 自动判断根因分类
         │    │   展示诊断报告 + 修复建议
         │    │
         │    └─ Step 5: 保存分析结果
         │       将 trace + ground_truth + diagnosis 写入 case 目录
         │
         └─ 选 "否" → 保持现有行为，仅保存 case
```

---

## 三、实施步骤

### Phase 1：管线 Trace 捕获（后端基础）

**目标**：让 `pipeline.query()` 能够捕获并返回完整的中间步骤数据。

#### 1.1 创建 Trace 数据模型

- 新建 `src/trace_models.py`
- 定义 `TraceStep`、`PipelineTrace` 数据类
- 定义 `TraceCapture` 上下文管理器，用于在管线各阶段自动记录

#### 1.2 改造 `RAGPipeline.query()`

- 新增 `capture_trace: bool = False` 参数
- 当 `capture_trace=True` 时，在管线各阶段记录 `TraceStep`
- 返回值中增加 `trace` 字段（包含完整 `PipelineTrace`）
- **关键**：不改默认行为，`capture_trace=False` 时完全兼容现有逻辑

#### 1.3 改造各子模块

- `query_rewriter.py`：记录改写前后的查询
- `retriever.py` / `bm25_retriever.py` / `hybrid_retriever.py`：记录检索结果（含分数）
- `reranker.py`：记录重排序前后的顺序和分数变化
- `generator.py`：记录完整的 system_prompt + user_message + LLM 回复

#### 1.4 测试

- 为 `trace_models.py` 编写单元测试
- 为 `pipeline.query(capture_trace=True)` 编写集成测试
- 验证 trace 数据的完整性

### Phase 2：Case 存储扩展

**目标**：扩展 case 的存储结构，支持 trace 数据和 ground truth 标注。

#### 2.1 扩展 `case_collector.py`

- `save_case()` 新增可选参数 `trace: PipelineTrace | None`
- 当 trace 存在时，写入 `pipeline_trace.json` 到 case 目录
- 新增 `save_ground_truth()` 函数，写入 `ground_truth.json`
- 新增 `save_diagnosis()` 函数，写入 `diagnosis.json`
- `load_case()` 相应扩展，读取新增文件

#### 2.2 Case 目录结构扩展

```
data/cases/<case_id>/
├── manifest.json          # 已有：case 元数据
├── config_snapshot.yaml   # 已有：配置快照
├── meal_snapshot.json     # 已有：Meal 快照
├── query_result.json      # 已有：查询结果
├── environment.json       # 已有：环境信息
├── pipeline_trace.json    # 新增：管线追踪数据
├── ground_truth.json      # 新增：Ground Truth 标注
└── diagnosis.json         # 新增：根因诊断结果
```

#### 2.3 测试

- 扩展 `test_case_collector.py`，覆盖 trace/ground_truth/diagnosis 的存储和读取

### Phase 3：Ground Truth 查找引擎

**目标**：用户标注 PDF + 页码后，系统能自动找到对应的 chunk 并计算其检索分数。

#### 3.1 创建 `ground_truth_finder.py`

- `find_chunks_by_source_page(source_pdf, page_number)` → 返回匹配的 chunk 列表
- 从 Qdrant 的 payload 中按 `metadata.source` + `metadata.page_numbers` 过滤
- 或从 chunks JSONL 文件中按元数据查找

#### 3.2 创建 `retrieval_analyzer.py`

- `compute_ground_truth_metrics(trace, ground_truth_chunks)` → 计算：
  - 是否被召回（recall@k）
  - 召回排名（rank）
  - 检索分数（score）
  - 重排序分数（rerank_score，如有）
  - 是否被截断（context_dropped）

#### 3.3 测试

- 为 `ground_truth_finder.py` 和 `retrieval_analyzer.py` 编写单元测试

### Phase 4：根因诊断引擎

**目标**：根据 trace 数据和 ground truth，自动诊断 bad case 的根因。

#### 4.1 创建 `case_diagnoser.py`

- `diagnose(trace, ground_truth)` → 返回 `DiagnosisResult`
- 实现根因分类逻辑（RC-0 ~ RC-5）
- 每个根因附带：
  - 严重程度（low / medium / high / critical）
  - 人类可读的发现描述
  - 修复建议
  - 配置补丁建议（如 `{"retrieval.reranker.enabled": true}`）

#### 4.2 诊断逻辑伪代码

```
1. 查找 ground truth chunk 在 trace 中的位置
2. 如果 ground truth chunk 不在检索结果中 → RC-1 retrieval_miss
3. 如果 ground truth chunk 在检索结果中但排名 > 3 → RC-2 rank_too_low
4. 如果 ground truth chunk 被截断丢弃 → RC-3 context_dropped
5. 如果 ground truth chunk 在最终 context 中但答案不匹配 → RC-4 generation_failure
6. 如果查询改写后仍无法命中 → RC-5 query_mismatch
7. 如果一切正常 → RC-0 healthy
```

#### 4.3 测试

- 为每种根因分类编写测试用例
- 边界情况测试

### Phase 5：交互式分析 UI

**目标**：在 Streamlit 中构建 Bad Case 深度分析界面。

#### 5.1 新增 Streamlit 页面

- 新建 `src/app_pages/case_analyzer.py`
- 在 `app.py` 中新增 Tab："🔍 Bad Case 分析"

#### 5.2 Case 列表视图

- 展示所有 bad case 列表（时间倒序）
- 每条显示：问题预览、创建时间、诊断状态（已诊断/未诊断）、根因标签
- 支持点击进入单个 case 的分析视图

#### 5.3 管线链路总览

- 用 Mermaid 或自定义 HTML 渲染管线流水线图
- 每个阶段显示关键指标（耗时、输入/输出数量）
- 颜色编码：正常阶段绿色，问题阶段红色

#### 5.4 逐阶段展开视图

- 用户点击某阶段 → 展示完整输入/输出
- 检索阶段：展示每个 chunk 的文本、分数、来源、页码
- 重排序阶段：展示排序变化（前→后），分数对比
- 生成阶段：展示完整 system_prompt + user_message + LLM 回复

#### 5.5 Ground Truth 标注界面

- 下拉选择 PDF 文件
- 输入页码
- 可选输入正确答案文本
- 点击"查找"→ 系统展示匹配的 chunk 列表
- 用户确认 → 保存 ground truth

#### 5.6 诊断报告视图

- 展示根因分类（大号标签 + 颜色）
- 展示诊断详情（发现描述、严重程度）
- 展示修复建议（可操作的配置调整建议）

#### 5.7 Streamlit API 规范

- 使用 `st.html()` 替代 `st.components.v1.html()`（遵循 streamlit-api-migration 规则）
- 使用 `st.session_state` 管理分析状态
- 使用 `@st.cache_data` 缓存 case 列表

### Phase 6：集成与优化

**目标**：将深度分析模式与现有 Bad Case 收集流程无缝集成。

#### 6.1 修改 `_do_save_case()`

- 保存 bad case 时，自动以 `capture_trace=True` 重新执行查询（或从 session_state 中获取已捕获的 trace）
- 保存后弹出 "是否启用深度分析？" 提示

#### 6.2 修改 `pipeline.query()` 调用链

- 在 `qa_demo.py` 中，每次查询都设置 `capture_trace=True`
- 将 trace 数据存入 `st.session_state.messages` 中

#### 6.3 性能优化

- trace 捕获对查询延迟的影响应 < 5%
- 大型 trace 数据的序列化优化

#### 6.4 端到端测试

- 完整流程测试：标记 Bad Case → 进入分析 → 标注 Ground Truth → 查看诊断

---

## 四、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `src/trace_models.py` | Trace 数据模型 |
| 新建 | `src/ground_truth_finder.py` | Ground Truth chunk 查找 |
| 新建 | `src/retrieval_analyzer.py` | 检索质量分析 |
| 新建 | `src/case_diagnoser.py` | 根因诊断引擎 |
| 新建 | `src/app_pages/case_analyzer.py` | 分析 UI 页面 |
| 新建 | `tests/test_trace_models.py` | Trace 模型测试 |
| 新建 | `tests/test_ground_truth_finder.py` | Ground Truth 查找测试 |
| 新建 | `tests/test_retrieval_analyzer.py` | 检索分析测试 |
| 新建 | `tests/test_case_diagnoser.py` | 诊断引擎测试 |
| 修改 | `src/pipeline.py` | 新增 `capture_trace` 参数 |
| 修改 | `src/generator.py` | 暴露完整 prompt 构建过程 |
| 修改 | `src/case_collector.py` | 扩展存储结构 |
| 修改 | `src/app_pages/qa_demo.py` | 集成深度分析入口 |
| 修改 | `src/app.py` | 新增分析 Tab |
| 修改 | `tests/test_case_collector.py` | 扩展测试覆盖 |

---

## 五、优先级与里程碑

| 里程碑 | 包含 Phase | 核心交付物 |
|--------|-----------|-----------|
| M1: 可追溯 | Phase 1 + 2 | 管线 trace 捕获 + case 存储扩展 |
| M2: 可诊断 | Phase 3 + 4 | Ground Truth 查找 + 根因诊断引擎 |
| M3: 可交互 | Phase 5 | Streamlit 分析 UI |
| M4: 可集成 | Phase 6 | 与现有流程无缝集成 |

建议按 M1 → M2 → M3 → M4 顺序交付，每个里程碑完成后提交并验证。

---

## 六、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| trace 捕获影响查询性能 | 默认关闭，仅在需要时开启；使用轻量级记录 |
| 大型 trace 数据占用存储 | JSON 压缩；定期清理旧 trace |
| Ground Truth 页码与 chunk 边界不对齐 | 支持模糊匹配（页码范围）；展示匹配的多个 chunk 供用户选择 |
| 根因分类边界模糊 | 允许多标签；提供置信度分数 |
| Streamlit UI 复杂度 | 分阶段实现，先核心后优化 |
