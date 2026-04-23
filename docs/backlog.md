# 待做事项总表

<!-- status: active -->

> 最后更新：2026-04-24（RF-016 标记为已完成，TEST-008/TEST-002 标记为已完成）

本文档是项目"卫生情况"的总入口，追踪所有非阻塞性质的待做事项。

---

## 统计概览

| 类型 | 待处理 | 进行中 | 已完成 | 已延期 |
|------|--------|--------|--------|--------|
| Bug | 4 | 0 | 16 | 2 |
| Feature | 14 | 0 | 19 | 0 |
| Refactor | 6 | 0 | 14 | 1 |
| Optimization | 7 | 0 | 1 | 0 |
| Investigation | 15 | 0 | 5 | 1 |
| Test | 6 | 0 | 2 | 0 |

---

## Bug

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| BUG-021 | expected_sources 标注错误（LLM 生成问题涉及文档中提到的其他实体，但 source_files 仅指向生成问题时的源文档） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P6-5) | 📋 待处理 | 需重新设计问题生成策略，使 source_files 反映问题实际涉及的文档 |

### 🟡 已延期

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| BUG-001 | 测试数据占位符未填充 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | ⏳ 已延期 | 需人工从 PDF 查阅填入 |
| BUG-003 | NDCG 分级相关性 | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | ⏳ 已延期 | 当前阶段无明确收益 |
| BUG-017 | pytest tmp 目录配置导致 FileExistsError | [TODO.md](../TODO.md) | ✅ 已完成 | 添加 tmp_path_retention_count=0 + pytest_configure 预清理；详见 [troubleshooting](troubleshooting/pytest-basetemp-fileexistserror.md) |
| BUG-018 | RAGAS 框架版本兼容性风险 | [RAGAS 指南](guides/ragas-evaluation.md#4-已知未修复问题) | 📋 待处理 | 导入路径可能随 RAGAS 0.5.x break；当前锁定 >=0.4.3,<0.5 |
| BUG-019 | context_precision/context_recall 在 generation 下时聚合位置不一致 | [RAGAS 指南](guides/ragas-evaluation.md#4-已知未修复问题) | 📋 待处理 | 旧写法放 generation 下时逐题结果在 generation 字典而非 llm_retrieval；建议统一用 retrieval |
| BUG-020 | RAGAS evaluate() 的 raise_exceptions 行为差异 | [RAGAS 指南](guides/ragas-evaluation.md#4-已知未修复问题) | 📋 待处理 | evaluate_single 用 True 会抛异常中断，evaluate_batch 用 False 静默返回 NaN |

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
| FEAT-011 | 补做 LLM 报告功能 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 新增 `--llm-report-only` CLI 参数，追溯生成 LLM 报告 |
| FEAT-012 | 断点续传（实验中断恢复） | [TODO.md](../TODO.md) | 📋 待处理 | 大 | 支持实验中断后继续，需记录时间戳和基模变化 warning |
| FEAT-013 | 部分评测支持 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 如仅评测 PDF→MD 环节，不停换提取策略对比 |
| FEAT-014 | 透明版完整实验报告 | [TODO.md](../TODO.md) | 📋 待处理 | 大 | 含问题/答案/emb/recall/提示词/回复/指标计算过程 |
| FEAT-015 | 更细粒度实验记录 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | token per chunk、文档分布、meal 分布、统计量 |
| FEAT-016 | DATA_DIR 配置项支持 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 替代 mklink，系统级 RAG 数据源指定 |
| FEAT-017 | CI/CD 集成 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 学习并实施 CI/CD |
| FEAT-018 | pre-commit 钩子 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 添加 pre-commit 配置 |
| FEAT-019 | .trae 目录 plan/spec 文档定期归档机制 | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | .trae/documents 和 .trae/specs 下文档需定期归档；IDE 可能对 .trae 目录有保护；与 inbox/TODO 归档机制高度类似 |
| FEAT-020 | RAGAS 版本升级与 API 适配 | [RAGAS 指南](guides/ragas-evaluation.md#5-后续优化方向) | 📋 待处理 | 中 | 兼容性矩阵 + 版本检测自动选择导入路径 + CI 集成测试 |
| FEAT-021 | Ground Truth 手动标注工具 | [RAGAS 指南](guides/ragas-evaluation.md#5-后续优化方向) | 📋 待处理 | 大 | 交互式 CLI/Web 标注界面 + 审核/修正自动生成 expected_answer + TestSetManager 集成 |
| FEAT-022 | RAGAS 评测 Token 消耗追踪 | [RAGAS 指南](guides/ragas-evaluation.md#5-后续优化方向) | 📋 待处理 | 中 | 记录 RAGAS 评测 Token 使用量 + 与 token-tracking 系统集成 + 成本预估 |
| FEAT-023 | Context 长度控制（防止超出模型 context window） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P5-3) | 📋 待处理 | 中 | 5个512-token chunk约2560 token，需截断保护 |
| FEAT-024 | 页眉页脚清洗（PDF 解析后去除页码、logo、水印等噪声） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P1-3) | 📋 待处理 | 中 | 噪声进入检索影响质量 |
| FEAT-025 | 检索器层面文档级去重（top_k 结果按文档多样性分配） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P6-4) | 📋 待处理 | 中 | 当前 top 5 全部来自同一文档，检索多样性为零 |
| FEAT-026 | meal 系统升级支持扩充已有 meal | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 支持 merge_meals/extend_meal，composition 元数据追踪 |
| FEAT-027 | 问题集组合功能 | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 支持 merge_test_sets，问题去重与有效性验证 |
| FEAT-028 | 配置验证系统（Pydantic 模型验证 + 必填项校验 + 范围校验） | 深度审查 | 📋 待处理 | 中 | 当前 yaml.safe_load 直接加载无验证，可能导致意外行为 |
| FEAT-029 | 项目记忆系统 Skill（project-memory） | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 跨 session 项目记忆读写方法论，替代原"Project Context Skill"概念 |

---

## Refactor

| ID | 描述 | 来源 | 状态 | 规模 | 备注 |
|----|------|------|------|------|------|
| RF-001 | CLI 输出规范化（172 处 print） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 📋 待处理 | 中 | 替换为 loguru 会改变输出格式 |
| RF-002 | 项目结构整理（根目录 .py 文件） | [原 TODO.md](../TODO.md) | 📋 待处理 | 小 | 需评估影响范围 |
| RF-004 | 硬编码配置值提取到 config.yaml | v0.1.7 合并验收 | ✅ 已完成 | 中 | metrics.py/experiment_reporter.py/test_generator.py 中模型名、API URL、max_tokens、temperature 硬编码 |
| RF-005 | Anthropic 客户端创建统一抽象 | v0.1.7 合并验收 | ✅ 已完成 | 小 | 提取 create_anthropic_client 到 src/llm_client.py，4处→1处 |
| RF-007 | exp_configs 版本维护机制沉淀 | [TODO.md](../TODO.md) | 📋 待处理 | 小 | 随版本演进清洗模板，考虑沉淀为 skill 或系统提示词 |
| RF-008 | backlog issue 详细信息记录 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 参考 GitHub 做法，支持超链接引用详情 |
| RF-009 | commit-rule 与 CLAUDE.md 渐进式披露 | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 三层渐进式披露：commit-rule 23行+CLAUDE.md 3行+SKILL.md+docs/guides/commit-conventions.md |
| RF-010 | lint/ruff 配置 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 添加代码检查工具 |
| RF-011 | docs 目录组织度维护 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 打扫卫生时考量 docs 目录组织度，恢复整洁度 |
| RF-012 | 旧格式 test_sets DeprecationWarning 清理 | [TODO.md](../TODO.md) | ⏳ 已延期 | ⬇️ 低优先级暂缓；chunk-based 策略有不可替代优势，待升级为 chunk-aware 策略后再清理；详见 [分析报告](reviews/investigations/rf-012-chunk-vs-document-strategy-analysis.md) |
| RF-013 | chunk_id 命名规范化（当前依赖文件名含下划线时解析脆弱） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P2-3) | 📋 待处理 | 小 | 需设计新格式并考虑迁移兼容 |
| RF-014 | normalize_source 匹配精度提升（当前仅比较文件名 stem，过于宽松） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P6-1) | 📋 待处理 | 小 | 可能误判不同版本的同名文档 |
| RF-015 | 更新 hyperparameter-guide.md 增加新解析链路讲解 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 新增 PDF 解析策略章节，介绍 pymupdf4llm 和 fitz_pdfplumber 两种解析器 |
| RF-006 | TestSet 独立管理系统重构 | 设计文档 | ✅ 已完成 | 大 | 新增 TestSetManager，重构 prepare_test_sets，支持 on_missing 三种模式 |
| RF-017 | 自定义异常类型定义（RAGPipelineError、RetrievalError 等） | 深度审查 | ✅ 已完成 | 小 | 新增 src/exceptions.py，9个业务异常类，全项目替换 |
| RF-018 | Pipeline 类职责拆分（当前 560 行承担全流程） | 深度审查 | 📋 待处理 | 大 | 可拆分为 PipelineOrchestrator + 各阶段 Stage 类 |

---

## Optimization

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| OPT-001 | 优化"新用户"链路性能（PDF→parse→chunk→embed） | [原 TODO.md](../TODO.md) | 📋 待处理 | 需性能基准测试，部分可上 GPU |
| OPT-002 | 集成测试时间优化（当前 182s） | [原 TODO.md](../TODO.md) | 📋 待处理 | 需分析瓶颈；旧数据，需重新测试更新 |
| OPT-003 | 问题生成 token 消耗优化 | [TODO.md](../TODO.md) | ✅ 已完成 | 每问题 5-6k token，添加文档截断缓存机制 |
| OPT-004 | Hit Rate 扩充到 Recall@3/5/10 | [TODO.md](../TODO.md) | 📋 待处理 | 需先澄清现有指标体系（RAGAS 线 vs builtin 线） |
| OPT-005 | RAGAS/builtin 指标结果统一归一化 | [RAGAS 指南](guides/ragas-evaluation.md#5-后续优化方向) | 📋 待处理 | 后端间分数相关性分析 + 归一化映射 + prompt 版本追踪 |
| OPT-006 | RAGAS 评测缓存与增量计算 | [RAGAS 指南](guides/ragas-evaluation.md#5-后续优化方向) | 📋 待处理 | 基于 question+answer+contexts hash 缓存 + 增量评测 + 失效策略 |
| OPT-007 | 基线 chunk_overlap 非零优化 | [pipeline-deep-audit.md](pipeline-deep-audit.md#P2-1) | 📋 待处理 | 评测链路修复后，通过对比实验确定合适的非零 overlap 值 |
| OPT-008 | GPU 内存管理优化（Embedder/Reranker 加载后正确释放） | 深度审查 | 📋 待处理 | 需评估 GPU 内存释放机制，避免资源泄漏 |

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
| INV-012 | 测试体系深度审查（883条是否过多） | [TODO.md](../TODO.md) | ✅ 已完成 | 26个测试文件，913个测试函数；未发现重复或无意义测试 |
| INV-013 | 自动生成的 Ground Truth 质量有限 | [RAGAS 指南](guides/ragas-evaluation.md#4-已知未修复问题) | 📋 待处理 | LLM 生成 expected_answer 可能幻觉，影响 context_precision/context_recall/answer_correctness 可信度 |
| INV-014 | RAGAS 指标与 Builtin 指标深度对比分析 | [RAGAS 指南](guides/ragas-evaluation.md#5-后续优化方向) | 📋 待处理 | 差异报告 + 根因分析（prompt 差异 vs 评分逻辑差异）+ 置信区间估计 |
| INV-015 | tiktoken 与 BGE tokenizer 的 token 数差异量化 | [pipeline-deep-audit.md](pipeline-deep-audit.md#P3-1) | 📋 待处理 | chunk_size=512 tiktoken token 可能超过 BGE 512 token 限制，需实际数据验证截断影响 |
| INV-016 | PDF 表格解析质量评估与替代方案调研 | [pipeline-deep-audit.md](pipeline-deep-audit.md#P1-1) | 📋 待处理 | pymupdf4llm 对复杂表格转换错乱，金融研报财务数据可能丢失 |
| INV-017 | 边界条件测试覆盖评估（空输入、极端值等） | 深度审查 | ✅ 已完成 | 详见 [评估报告](reviews/inv-017-boundary-condition-test-coverage.md) |
| INV-018 | 异常路径测试覆盖评估 | 深度审查 | ✅ 已完成 | 详见 [评估报告](reviews/inv-018-exception-path-test-coverage.md) |
| INV-019 | 测试并行化可行性评估（pytest-xdist） | 深度审查 | 📋 待处理 | 评估是否可用 pytest-xdist 加速测试 |
| INV-020 | 大规模数据索引构建性能评估 | 深度审查 | 📋 待处理 | 评估大规模数据时索引构建时间和优化空间 |
| INV-021 | 文件路径安全检查（防止路径遍历攻击） | 深度审查 | 📋 待处理 | 文件路径处理是否防止 `../` 攻击 |

---

## Test

| ID | 描述 | 来源 | 状态 | 优先级 | 备注 |
|----|------|------|------|--------|------|
| TEST-001 | 补充 generator 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | 📋 待处理 | 高 | 空输入、None值、极端值测试 |
| TEST-002 | 补充 test_set_manager 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | ✅ 已完成 | 高 | 文件不存在、无效数据、空列表测试 |
| TEST-003 | 补充 experiment 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | 📋 待处理 | 高 | 配置缺失、无效配置、空测试集测试 |
| TEST-004 | 补充 run_experiment 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | 📋 待处理 | 高 | 权限错误、文件不存在、无效配置测试 |
| TEST-005 | 补充 generator 模块异常路径测试 | [INV-018](reviews/inv-018-exception-path-test-coverage.md) | 📋 待处理 | 高 | API调用失败、超时、速率限制测试 |
| TEST-006 | 补充 experiment 模块异常路径测试 | [INV-018](reviews/inv-018-exception-path-test-coverage.md) | 📋 待处理 | 高 | 无效配置、权限错误等异常测试 |
| TEST-007 | 补充 run_experiment 模块异常路径测试 | [INV-018](reviews/inv-018-exception-path-test-coverage.md) | 📋 待处理 | 高 | 文件操作异常测试 |
| TEST-008 | 补充 indexer 模块异常路径测试 | [INV-018](reviews/inv-018-exception-path-test-coverage.md) | ✅ 已完成 | 高 | 向量索引异常测试 |

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
| BUG-017 | pytest tmp 目录配置导致 FileExistsError | [TODO.md](../TODO.md) | 2026-04-22 |

### Feature

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| FEAT-001 | 实现生成质量指标（Faithfulness, Answer Relevancy） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-18 |
| FEAT-006 | 重写问题生成策略，与 chunk 解耦，基于整个 MD | [原 TODO.md](../TODO.md) | 2026-04-18 |
| FEAT-007 | TestSet 独立管理系统 | 设计文档 | 2026-04-20 |
| FEAT-009 | TODO 归档机制（TODO↔backlog 双向异步） | [TODO.md](../TODO.md) | 2026-04-21 |
| FEAT-018 | pre-commit 钩子 → 已配置 ruff + trailing-whitespace + yaml + merge-conflict | [TODO.md](../TODO.md) | 2026-04-21 |
| FEAT-016 | DATA_DIR 配置项支持 → load_config 自动解析 data/ 前缀路径 | [TODO.md](../TODO.md) | 2026-04-21 |
| FEAT-019 | .trae 目录 plan/spec 文档定期归档机制 | [TODO.md](../TODO.md) | 2026-04-21 |
| FEAT-029 | 项目记忆系统 Skill（project-memory） | [TODO.md](../TODO.md) | 2026-04-24 |
| FEAT-011 | 补做 LLM 报告功能 | [TODO.md](../TODO.md) | 2026-04-24 |
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
| RF-004 | 硬编码配置值提取到 config.yaml | v0.1.7 合并验收 | 2026-04-21 |
| RF-009 | commit-rule 与 CLAUDE.md 渐进式披露 → 三层架构：commit-rule 23行+CLAUDE.md 3行+SKILL.md+docs/guides/commit-conventions.md | [TODO.md](../TODO.md) | 2026-04-22 |
| RF-016 | Optional 类型使用规范化 → 统一为 Python 3.10+ 的 `| None` 语法 | 深度审查 | 2026-04-24 |
| RF-017 | 自定义异常类型定义 → 新增 src/exceptions.py，9个业务异常类，全项目替换 | 深度审查 | 2026-04-24 |

### Investigation

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| INV-004 | 实验资产包 token summary 记录 → 已实现保存 token_summary.json/txt | [原 TODO.md](../TODO.md) | 2026-04-19 |
| INV-008 | LLM 报告假设性问题类型提示词更新 → 已更新为 document 策略六类 | [TODO.md](../TODO.md) | 2026-04-21 |
| INV-012 | 测试体系深度审查（883条是否过多） | [TODO.md](../TODO.md) | 2026-04-21 |

### Optimization

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| OPT-003 | 问题生成 token 消耗优化 → 添加文档截断缓存机制 | [TODO.md](../TODO.md) | 2026-04-21 |

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
