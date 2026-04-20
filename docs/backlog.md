# 待做事项总表

<!-- status: active -->

> 最后更新：2026-04-21

本文档是项目"卫生情况"的总入口，追踪所有非阻塞性质的待做事项。

---

## 统计概览

| 类型 | 待处理 | 进行中 | 已完成 | 已延期 |
|------|--------|--------|--------|--------|
| Bug | 0 | 0 | 15 | 2 |
| Feature | 10 | 0 | 18 | 0 |
| Refactor | 7 | 0 | 10 | 0 |
| Optimization | 4 | 0 | 0 | 0 |
| Investigation | 8 | 0 | 3 | 0 |

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
| FEAT-002 | 混合检索（BM25 + 向量） | [CLAUDE.md](../CLAUDE.md) | ✅ 已完成 | 中 | v0.1.8 已实现 |
| FEAT-003 | Reranker 重排 | [CLAUDE.md](../CLAUDE.md) | ✅ 已完成 | 中 | v0.1.8 已实现 |
| FEAT-004 | 查询改写 | [CLAUDE.md](../CLAUDE.md) | ✅ 已完成 | 中 | v0.1.8 已实现 |
| FEAT-005 | 语义分块 | [CLAUDE.md](../CLAUDE.md) | ✅ 已完成 | 中 | v0.1.8 已实现 |
| FEAT-008 | test-future-directions 剩余方向落实 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 完成测试未来方向文档中的待办项 |
| FEAT-010 | golden_qa 数据源适配指引 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 新用户部署指引：如何载入手头数据、做 meal、精调 golden_qa、跑保活测试 |
| FEAT-011 | 补做 LLM 报告功能 | [TODO.md](../TODO.md) | 📋 待处理 | 小 | 实验跑完后补生成 LLM 总结报告 |
| FEAT-012 | 断点续传（实验中断恢复） | [TODO.md](../TODO.md) | 📋 待处理 | 大 | 支持实验中断后继续，需记录时间戳和基模变化 warning |
| FEAT-013 | 部分评测支持 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 如仅评测 PDF→MD 环节，不停换提取策略对比 |
| FEAT-014 | 透明版完整实验报告 | [TODO.md](../TODO.md) | 📋 待处理 | 大 | 含问题/答案/emb/recall/提示词/回复/指标计算过程 |
| FEAT-015 | 更细粒度实验记录 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | token per chunk、文档分布、meal 分布、统计量 |
| FEAT-016 | DATA_DIR 配置项支持 | [TODO.md](../TODO.md) | 📋 待处理 | 小 | 替代 mklink，系统级 RAG 数据源指定 |
| FEAT-017 | CI/CD 集成 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 学习并实施 CI/CD |
| FEAT-018 | pre-commit 钩子 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 添加 pre-commit 配置 |
| FEAT-019 | .trae 目录 plan/spec 文档定期归档机制 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | .trae/documents 和 .trae/specs 下文档需定期归档；IDE 可能对 .trae 目录有保护；与 inbox/TODO 归档机制高度类似 |

---

## Refactor

| ID | 描述 | 来源 | 状态 | 规模 | 备注 |
|----|------|------|------|------|------|
| RF-001 | CLI 输出规范化（172 处 print） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 📋 待处理 | 中 | 替换为 loguru 会改变输出格式 |
| RF-002 | 项目结构整理（根目录 .py 文件） | [原 TODO.md](../TODO.md) | 📋 待处理 | 小 | 需评估影响范围 |
| RF-004 | 硬编码配置值提取到 config.yaml | v0.1.7 合并验收 | 📋 待处理 | 中 | metrics.py/experiment_reporter.py/test_generator.py 中模型名、API URL、max_tokens、temperature 硬编码 |
| RF-005 | Anthropic 客户端创建统一抽象 | v0.1.7 合并验收 | ✅ 已完成 | 小 | 提取 create_anthropic_client 到 src/llm_client.py，4处→1处 |
| RF-007 | exp_configs 版本维护机制沉淀 | [TODO.md](../TODO.md) | 📋 待处理 | 小 | 随版本演进清洗模板，考虑沉淀为 skill 或系统提示词 |
| RF-008 | backlog issue 详细信息记录 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 参考 GitHub 做法，支持超链接引用详情 |
| RF-009 | commit-rule 与 CLAUDE.md 渐进式披露 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 分离为 skill/rule，减少提示词长度 |
| RF-010 | lint/ruff 配置 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 添加代码检查工具 |
| RF-011 | docs 目录组织度维护 | [TODO.md](../TODO.md) | 📋 待处理 | 小 | 打扫卫生时考量 docs 目录组织度，恢复整洁度 |
| RF-006 | TestSet 独立管理系统重构 | 设计文档 | ✅ 已完成 | 大 | 新增 TestSetManager，重构 prepare_test_sets，支持 on_missing 三种模式 |

---

## Optimization

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| OPT-001 | 优化"新用户"链路性能（PDF→parse→chunk→embed） | [原 TODO.md](../TODO.md) | 📋 待处理 | 需性能基准测试，部分可上 GPU |
| OPT-002 | 集成测试时间优化（当前 182s） | [原 TODO.md](../TODO.md) | 📋 待处理 | 需分析瓶颈；旧数据，需重新测试更新 |
| OPT-003 | 问题生成 token 消耗优化 | [TODO.md](../TODO.md) | 📋 待处理 | 每问题 5-6k token，考虑 cache 输入 MD |
| OPT-004 | Hit Rate 扩充到 Recall@3/5/10 | [TODO.md](../TODO.md) | 📋 待处理 | 需先澄清现有指标体系（RAGAS 线 vs builtin 线） |

---

## Investigation

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| INV-001 | 实验报告 sources 字段细化到标题头或 chunk | [原 TODO.md](../TODO.md) | 📋 待处理 | FEAT-006 已完成，可独立推进；当前标记一连串 doc 导致命中率虚高 |
| INV-002 | 验证问题生成策略可扩展性 | [原 TODO.md](../TODO.md) | ⏳ 待定 | 依赖黄金测试集落地 |
| INV-003 | 日志系统"应记尽记"最佳实践 | [原 TODO.md](../TODO.md) | 📋 待处理 | pytest 日志不完整 |
| INV-005 | 05-open-source-readiness 核实 | [TODO.md](../TODO.md) | 📋 待处理 | 核实开源准备度检查清单 |
| INV-006 | golden test 是否基于老策略 | [TODO.md](../TODO.md) | 📋 待处理 | 需确认是否需要重做 |
| INV-007 | 评测系统可靠性全面审查 | [TODO.md](../TODO.md) | 📋 待处理 | 从一个 PDF 和一个问题开始精调 |
| INV-008 | LLM 报告假设性问题类型提示词更新 | [TODO.md](../TODO.md) | ✅ 已完成 | 3.1 节提示词仍为旧策略分析方法 |
| INV-009 | 问题集扩大与指标收敛趋势 | [TODO.md](../TODO.md) | 📋 待处理 | 等 v0.1.9 发版确认数据有效性后推进 |
| INV-010 | 元数据增强改善 chunk 命中 | [TODO.md](../TODO.md) | 📋 待处理 | PDF 页码 + MD 标题层级，需入库对话记录并实装 |
| INV-011 | 开源许可证评估（Apache 2.0） | [TODO.md](../TODO.md) | 📋 待处理 | 了解 Apache 2.0 及自动化标记源文件 |

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
| BUG-014 | NDCG 值超出 [0,1] 范围 | v0.1.8 合并发现 | 2026-04-20 |
| BUG-015 | irrelevant/missing 问题类型 source_files 错误 | v0.1.8 合并发现 | 2026-04-20 |
| BUG-016 | chunker config hash 缺少 strategy/semantic 参数 | v0.1.8 合并发现 | 2026-04-20 |

### Feature

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| FEAT-001 | 实现生成质量指标（Faithfulness, Answer Relevancy） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| FEAT-006 | 重写问题生成策略，与 chunk 解耦，基于整个 MD | [原 TODO.md](../TODO.md) | 2026-04-18 |
| FEAT-007 | TestSet 独立管理系统 | 设计文档 | 2026-04-20 |
| FEAT-009 | TODO 归档机制（TODO↔backlog 双向异步） | [TODO.md](../TODO.md) | 2026-04-21 |
| FEAT-018 | pre-commit 钩子 → 已配置 ruff + trailing-whitespace + yaml + merge-conflict | [TODO.md](../TODO.md) | 2026-04-21 |
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
| RF-010 | lint/ruff 配置 → 已配置 ruff + pyproject.toml + pixi tasks | [TODO.md](../TODO.md) | 2026-04-21 |
| RF-005 | Anthropic 客户端统一抽象 → 提取 create_anthropic_client 到 src/llm_client.py | v0.1.7 合并验收 | 2026-04-21 |

### Investigation

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| INV-004 | 实验资产包 token summary 记录 → 已实现保存 token_summary.json/txt | [原 TODO.md](../TODO.md) | 2026-04-19 |
| INV-008 | LLM 报告假设性问题类型提示词更新 → 已更新为 document 策略六类 | [TODO.md](../TODO.md) | 2026-04-21 |

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
