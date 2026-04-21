# 独立推荐 Issue 分析

> 当前两个 worktree 任务：
> 1. 验证 RAGAS 五大指标是否能正常生成到实验报告中
> 2. 以冒烟测试为例，打开 baseline 链路的黑盒子
>
> 本文档分析：哪些推荐 issue 与这两个任务独立、不容易发生冲突

---

## 任务范围分析

| 任务 | 涉及模块 |
|------|----------|
| 任务1: RAGAS 五大指标 | `eval/evaluators/ragas_evaluator.py`, `ragas` 库, 报告生成 |
| 任务2: Baseline 链路黑盒 | `pipeline.py`, `retriever.py`, `embedder.py`, `generator.py`, `evaluator.py`, 测试集 |

---

## 独立 Issue 筛选

### ❌ 与任务冲突的 Issue（应避开）

| Issue | 冲突原因 |
|-------|----------|
| FEAT-014（透明报告） | 涉及报告生成，与任务1冲突 |
| INV-007（评测可靠性） | 涉及 evaluator，与任务2冲突 |
| FEAT-025（检索多样性） | 涉及 retriever，与任务2冲突 |
| BUG-017（expected_sources 标注） | 涉及问题生成，与测试集相关 |
| FEAT-011（补做 LLM 报告） | 涉及报告，与任务1冲突 |

### ✅ 独立的推荐 Issue

| Issue | 涉及模块 | 独立性 | 推荐理由 |
|-------|----------|--------|----------|
| **RF-004** | `eval/metrics/`, `experiment_reporter.py`, `test_generator.py` | ✅ 独立于 RAGAS 和 baseline 链路 | 硬编码配置提取，改进代码质量，不影响评测逻辑 |
| **OPT-003** | `test_generator.py` | ✅ 独立 | 问题生成 token 优化，不涉及评测链路 |
| **INV-012** | `tests/` 目录 | ✅ 独立 | 测试体系审查，不涉及 RAGAS 或 baseline 管线 |
| **FEAT-019** | `.trae/documents/` | ✅ 独立 | 文档归档机制，完全独立于代码逻辑 |

---

## 推荐优先级（独立 Issue）

### 🥇 RF-004 — 硬编码配置值提取到 config.yaml

**涉及模块**：`eval/metrics/generation.py`, `eval/metrics/llm_retrieval.py`, `experiment_reporter.py`, `test_generator.py`

**为什么独立**：
- 不涉及 RAGAS 评测（ragas_evaluator.py）
- 不涉及 baseline 管线（pipeline, retriever, embedder, generator, evaluator）
- 只涉及 metrics 计算函数的默认参数、测试生成器的参数

**具体内容**：
- 将 metrics 函数中的 `model_name="LongCat-Flash-Lite"`, `base_url`, `temperature`, `max_tokens` 提取到 config.yaml
- 将 test_generator 中的 `temperature=0.7`, `max_tokens=512/1024` 提取到配置

**风险**：低。只改默认参数，不改核心逻辑。

---

### 🥈 OPT-003 — 问题生成 token 消耗优化

**涉及模块**：`test_generator.py`

**为什么独立**：
- 完全不涉及评测系统
- 不涉及 RAGAS
- 只涉及问题生成模块

**具体内容**：
- 每问题 5-6k token，主要因为每次输入完整 MD 文档
- 可考虑：缓存已输入的 MD、缩短 prompt、分批发送

**风险**：低。优化生成效率，不影响评测。

---

### 🥉 INV-012 — 测试体系深度审查（883条是否过多）

**涉及模块**：`tests/` 目录

**为什么独立**：
- 测试代码独立于业务逻辑
- 不涉及 RAGAS 评测
- 不涉及 baseline 管线

**具体内容**：
- 排查重复测试
- 排查无意义测试
- 评估集成测试必要性

**风险**：低。只读分析，不改功能。

---

### 🏅 FEAT-019 — .trae 目录归档机制

**涉及模块**：`.trae/documents/`, `.trae/specs/`

**为什么独立**：
- 完全是文档管理
- 不涉及任何代码逻辑

**具体内容**：
- 定期将完成的 plan/spec 归档到 docs/archive/
- 沉淀为 skill 或脚本

**风险**：无。纯文档操作。

---

## 总结

**最推荐的独立 Issue**：

| 优先级 | Issue | 模块 | 工作量 | 理由 |
|--------|-------|------|--------|------|
| 🥇 | RF-004 | metrics/generator/reporter | 中 | 改进代码质量，为后续工作打基础 |
| 🥈 | OPT-003 | test_generator | 中 | 优化生成效率，降低成本 |
| 🥉 | INV-012 | tests/ | 中 | 评估测试体系必要性 |
| 🏅 | FEAT-019 | 文档 | 小 | 顺手可做 |

**建议**：可以开始做 **RF-004**（硬编码配置提取），这是一个中等工作量、风险低、价值高的改进，与当前两个任务完全独立。
