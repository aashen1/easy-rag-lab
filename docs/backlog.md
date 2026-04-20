# 待做事项总表

<!-- status: active -->

> 最后更新：2026-04-20

本文档是项目"卫生情况"的总入口，追踪所有非阻塞性质的待做事项。

---

## 统计概览

| 类型 | 待处理 | 进行中 | 已完成 | 已延期 |
|------|--------|--------|--------|--------|
| Bug | 0 | 0 | 11 | 2 |
| Feature | 4 | 0 | 11 | 0 |
| Refactor | 4 | 0 | 5 | 0 |
| Optimization | 2 | 0 | 0 | 0 |
| Investigation | 3 | 0 | 1 | 0 |

---

## Bug

### 🟡 已延期

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| BUG-001 | 测试数据占位符未填充 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | ⏳ 已延期 | 需人工从 PDF 查阅填入 |
| BUG-003 | NDCG 分级相关性 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | ⏳ 已延期 | 当前阶段无明确收益 |

---

## Feature

| ID | 描述 | 来源 | 状态 | 规模 | 备注 |
|----|------|------|------|------|------|
| FEAT-002 | 混合检索（BM25 + 向量） | [CLAUDE.md](../CLAUDE.md) | 📋 待处理 | 中 | RAG 优化 |
| FEAT-003 | Reranker 重排 | [CLAUDE.md](../CLAUDE.md) | 📋 待处理 | 中 | RAG 优化 |
| FEAT-004 | 查询改写 | [CLAUDE.md](../CLAUDE.md) | 📋 待处理 | 中 | RAG 优化 |
| FEAT-005 | 语义分块 | [CLAUDE.md](../CLAUDE.md) | 📋 待处理 | 中 | RAG 优化 |

---

## Refactor

| ID | 描述 | 来源 | 状态 | 规模 | 备注 |
|----|------|------|------|------|------|
| RF-001 | CLI 输出规范化（172 处 print） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 📋 待处理 | 中 | 替换为 loguru 会改变输出格式 |
| RF-002 | 项目结构整理（根目录 .py 文件） | [原 TODO.md](../TODO.md) | 📋 待处理 | 小 | 需评估影响范围 |
| RF-004 | 硬编码配置值提取到 config.yaml | v0.1.7 合并验收 | 📋 待处理 | 中 | metrics.py/experiment_reporter.py/test_generator.py 中模型名、API URL、max_tokens、temperature 硬编码 |
| RF-005 | Anthropic 客户端创建统一抽象 | v0.1.7 合并验收 | 📋 待处理 | 小 | metrics.py calculate_answer_relevancy 重复创建客户端，api_key="dummy" 模式散布多处 |
| RF-006 | TestSet 独立管理系统重构 | 设计文档 | ✅ 已完成 | 大 | 新增 TestSetManager，重构 prepare_test_sets，支持 on_missing 三种模式 |

---

## Optimization

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| OPT-001 | 优化"新用户"链路性能（PDF→parse→chunk→embed） | [原 TODO.md](../TODO.md) | 📋 待处理 | 需性能基准测试，部分可上 GPU |
| OPT-002 | 集成测试时间优化（当前 182s） | [原 TODO.md](../TODO.md) | 📋 待处理 | 需分析瓶颈 |

---

## Investigation

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| INV-001 | 实验报告 sources 字段细化到标题头或 chunk | [原 TODO.md](../TODO.md) | 📋 待处理 | FEAT-006 已完成，可独立推进 |
| INV-002 | 验证问题生成策略可扩展性 | [原 TODO.md](../TODO.md) | ⏳ 待定 | 依赖黄金测试集落地 |
| INV-003 | 日志系统"应记尽记"最佳实践 | [原 TODO.md](../TODO.md) | 📋 待处理 | pytest 日志不完整 |

---

## 已完成

### Bug

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| BUG-002 | 生成质量指标未实现 → 已由 FEAT-001 解决 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-19 |
| BUG-004 | 检索指标始终返回 0 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| BUG-005 | chunk_comparison.yaml 无效策略名 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| BUG-006 | Generator 未使用 system 参数 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| BUG-007 | Indexer 资源未释放 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| BUG-008 | total_chunks 偏差 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| BUG-009 | main.py 缺失 typing 导入（Optional/Dict/Any） | 代码审查发现 | 2026-04-19 |
| BUG-010 | test_generator.py _save_test_set IO 写入无 try/except | v0.1.7 合并验收 | 2026-04-19 |
| BUG-011 | experiment_reporter.py generate_markdown_report 公共方法缺 docstring | v0.1.7 合并验收 | 2026-04-19 |
| BUG-012 | TestSetManager 类被 pytest 误识别为测试类 | 测试警告 | 2026-04-20 |
| BUG-013 | TestSetGenerator 旧格式兼容性未测试 | v0.1.8 实现发现 | 2026-04-20 |

### Feature

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| FEAT-001 | 实现生成质量指标（Faithfulness, Answer Relevancy） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| FEAT-006 | 重写问题生成策略，与 chunk 解耦，基于整个 MD | [原 TODO.md](../TODO.md) | 2026-04-18 |
| FEAT-007 | TestSet 独立管理系统 | 设计文档 | 2026-04-20 |
| FEAT-DONE-001 | 文档系统重构 | [原 TODO.md](../TODO.md) | 2026-04-18 |
| FEAT-DONE-002 | LLM 报告功能修复 | [原 TODO.md](../TODO.md) | 2026-04-17 |
| FEAT-DONE-003 | Token 统计功能 | [原 TODO.md](../TODO.md) | 2026-04-17 |
| FEAT-DONE-004 | 测试系统重构 | [原 TODO.md](../TODO.md) | 2026-04-17 |

### Refactor

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| RF-003 | 实验配置模板更新（multi-hop→multi_hop、补充 generation 指标、补 seed） | [原 TODO.md](../TODO.md) | 2026-04-19 |
| RF-DONE-001 | CHANGELOG 清洗 | [原 TODO.md](../TODO.md) | 2026-04-18 |
| RF-DONE-002 | README 和 CLAUDE 更新 | [原 TODO.md](../TODO.md) | 2026-04-18 |
| RF-DONE-003 | PytestCollectionWarning 修复 | [原 TODO.md](../TODO.md) | 2026-04-18 |

### Investigation

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| INV-004 | 实验资产包 token summary 记录 → 已实现保存 token_summary.json/txt | [原 TODO.md](../TODO.md) | 2026-04-19 |

---

## 状态标签说明

- `📋 待处理`：尚未开始
- `🔄 进行中`：正在处理
- `✅ 已完成`：已完成
- `⏳ 已延期`：延后处理，需注明原因

---

## ID 命名规范

- Bug: `BUG-NNN`
- Feature: `FEAT-NNN`
- Refactor: `RF-NNN`
- Optimization: `OPT-NNN`
- Investigation: `INV-NNN`
