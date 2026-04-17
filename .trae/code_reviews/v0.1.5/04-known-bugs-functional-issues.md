# 已知 Bug 与功能问题审查

> **状态标注版本**（标注日期：2026-04-18）— 各问题标题前已添加状态标签：✅ 已修复 / 📋 已安排 / ⏳ 待定

审查日期：2026-04-18
审查来源：CHANGELOG.md Known Issues、代码分析、测试结果

---

## 严重程度定义

| 等级 | 定义 |
|------|------|
| 🔴 严重 | 功能完全不可用或产生错误结果 |
| 🟠 中等 | 功能受限或行为不符合预期 |
| 🟡 轻微 | 体验不佳或代码风格问题 |

---

## 🔴 严重问题

### 1. 📋 已安排 — 检索指标始终返回 0

**来源**：CHANGELOG.md Known Issues #1

**问题**：检索到的 sources 使用相对 Markdown 路径（如 `annual_report/xxx.md`），而 expected sources 使用 PDF 文件名（如 `xxx.pdf`），路径格式不匹配导致所有检索指标（Hit Rate、MRR、NDCG）始终返回 0。

**影响**：评测系统形同虚设，无法得到有效的 baseline 数据。这是整个评测系统的核心 bug。

**涉及文件**：
- `eval/metrics.py` — 指标计算中的 source 匹配逻辑
- `src/retriever.py` — 返回的 source 路径格式
- `eval/test_data.json` — expected_sources 的路径格式

**修复方向**：
- 统一 source 路径格式（建议统一为 PDF 文件名）
- 或在指标计算时添加路径格式转换逻辑

---

### 2. ✅ 已修复 — chunk_comparison.yaml 使用无效策略名

**来源**：CHANGELOG.md Known Issues #2

**问题**：`exp_configs/chunk_comparison.yaml` 中使用了 `"complex"` 策略名，但 `src/test_generator.py` 仅支持 `factual`、`boundary`、`multi_hop` 三种策略。

**影响**：运行 `pixi run exp chunk_comparison` 会抛出 `ValueError`，实验无法执行。

**修复方向**：将 `"complex"` 改为有效的策略名（如 `"multi_hop"`）。

---

## 🟠 中等问题

### 3. ✅ 已修复 — Generator 未使用 Anthropic API 的 system 参数

**来源**：CHANGELOG.md Known Issues #3

**问题**：`Generator.generate()` 将 system prompt 拼接到 user message 中，而非使用 Anthropic API 的专用 `system` 参数。

**影响**：
- 降低了指令遵循质量（system prompt 的权重低于 user message）
- 与 Anthropic API 最佳实践不一致
- 可能导致模型忽略系统指令

**涉及文件**：`src/generator.py`

**修复方向**：将 system prompt 传入 API 的 `system` 参数：

```python
response = client.messages.create(
    model=model_name,
    system=system_prompt,  # 使用专用参数
    messages=[{"role": "user", "content": query}],
    ...
)
```

---

### 4. ✅ 已修复 — Indexer 资源未自动释放

**来源**：CHANGELOG.md Known Issues #4

**问题**：`RAGPipeline` 未调用 `VectorIndexer.close()`，可能导致资源泄露和 Windows 上的文件锁定问题。

**影响**：
- Qdrant 客户端连接未正确关闭
- Windows 上可能出现文件锁，导致后续操作失败
- 长时间运行可能导致内存泄露

**涉及文件**：`src/pipeline.py`

**修复方向**：
- 为 `RAGPipeline` 添加上下文管理器协议（`__enter__`/`__exit__`）
- 或在 `query()` 方法结束后调用 `close()`
- 或使用 `atexit` 注册清理函数

---

### 5. ✅ 已修复 — Meal total_chunks 偏差一位

**来源**：CHANGELOG.md Known Issues #5

**问题**：`total_chunks` 初始化为文件数量而非 0，导致计数偏大（多了 JSONL 文件数量的值）。

**影响**：Meal 元数据中的 `total_chunks` 不准确，影响统计报告和状态判断。

**涉及文件**：`src/meal.py`

**修复方向**：将 `total_chunks` 初始化为 0，在遍历 chunks 时累加。

---

### 6. 📋 已安排 — 测试数据占位符未填充

**来源**：CHANGELOG.md Known Issues #6

**问题**：`eval/test_data.json` 中部分 `expected_answer` 字段包含占位符值（如 `"XXX亿元"`）。

**影响**：无法用于生成质量评测（Faithfulness、Answer Relevancy 等指标需要参考答案）。

**修复方向**：填充真实的 expected_answer 值。

---

### 7. 📋 已安排 — 生成质量指标未实现

**来源**：CHANGELOG.md Known Issues #7

**问题**：Faithfulness 和 Answer Relevancy 指标尚未实现。

**影响**：只能评估检索质量，无法评估生成质量，评测体系不完整。

**修复方向**：使用 `ragas` 库实现这两个指标（项目已添加 `ragas` 依赖）。

---

## 🟡 轻微问题

### 8. 📋 已安排 — NDCG 简化实现

**来源**：CHANGELOG.md Known Issues #9

**问题**：当前 NDCG 使用二元相关性（gain=1.0 for all hits），不支持分级相关性。

**影响**：NDCG 值可能不够精细，但对 baseline 评测影响有限。

---

### 9. 📋 已安排 — Hit Rate 定义非标准

**来源**：CHANGELOG.md Known Issues #10

**问题**：当前 Hit Rate 计算"期望文档被检索到的比例"（recall-oriented），而非标准的"至少命中一个的查询比例"（Hit Rate@K）。

**影响**：与学术界标准定义不一致，可能影响与其他系统的对比。

---

### 10. 📋 已安排 — 评测指标配置未动态应用

**来源**：CHANGELOG.md Known Issues #11

**问题**：`evaluation.metrics.retrieval` 列表在实验配置中声明但未动态应用，三个指标是硬编码的。

**影响**：无法通过配置灵活选择评测指标。

---

### 11. 📋 已安排 — 文档类别检测逻辑重复

**来源**：CHANGELOG.md Known Issues #12

**问题**：文档类别检测（annual_report/research_report）在 `parser.py` 和 `chunker.py` 中重复硬编码。

**影响**：维护成本高，修改时容易遗漏。

---

### 12. 📋 已安排 — Embedder show_progress 参数未实现

**来源**：CHANGELOG.md Known Issues #13

**问题**：`Embedder.embed_texts()` 接受 `show_progress` 参数但未实现进度显示。

**影响**：大批量 embedding 时无法看到进度。

---

## 测试覆盖问题

### 13. 📋 已安排 — 测试覆盖不完整

**来源**：CHANGELOG.md Known Issues #8

**缺失的测试模块**：

| 模块 | 测试状态 |
|------|----------|
| `src/indexer.py` | 无单元测试 |
| `src/retriever.py` | 无单元测试 |
| `src/generator.py` | 无单元测试 |
| `src/pipeline.py` | 无单元测试 |
| `eval/metrics.py` | 无单元测试 |
| `src/test_generator.py` | 未测试 `generate_test_set` 主入口 |
| `eval/run_eval.py` | 仅测试配置加载，未测试评测执行 |

---

## 问题优先级排序

| 优先级 | 问题编号 | 问题 | 修复难度 |
|--------|---------|------|----------|
| P0 | #1 | 检索指标始终返回 0 | 中等 |
| P0 | #2 | chunk_comparison.yaml 无效策略名 | 简单 |
| P1 | #3 | Generator 未使用 system 参数 | 简单 |
| P1 | #4 | Indexer 资源未释放 | 中等 |
| P1 | #5 | total_chunks 偏差 | 简单 |
| P2 | #6 | 测试数据占位符 | 简单 |
| P2 | #7 | 生成质量指标未实现 | 较难 |
| P3 | #8-12 | 轻微问题 | 简单 |
| P3 | #13 | 测试覆盖不完整 | 较难 |
