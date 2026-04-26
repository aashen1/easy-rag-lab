# 待做事项总表

<!-- status: active -->

> 最后更新：2026-04-26（RF-008：新增 issue 详情文件机制，4 个高优先级 issue 已补充详情链接）

本文档是项目"卫生情况"的总入口，追踪所有非阻塞性质的待做事项。

---

## 统计概览

| 类型 | 待处理 | 进行中 | 已完成 | 已延期 |
|------|--------|--------|--------|--------|
| Bug | 8 | 0 | 18 | 2 |
| Feature | 26 | 0 | 21 | 0 |
| Refactor | 5 | 0 | 17 | 1 |
| Optimization | 7 | 0 | 2 | 0 |
| Investigation | 4 | 0 | 17 | 1 |
| Test | 0 | 0 | 8 | 0 |

---

## Bug

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| BUG-021 | expected_sources 标注错误（LLM 生成问题涉及文档中提到的其他实体，但 source_files 仅指向生成问题时的源文档） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P6-5) | 📋 待处理 | 需重新设计问题生成策略，使 source_files 反映问题实际涉及的文档 |
| BUG-022 | `_locate_answer_chunks()` 定位精度不足 | [INV-007 调查](reviews/investigations/inv-007-eval-system-reliability.md) | 📋 待处理 | 使用关键词+子串启发式方法，expected_chunks 可能遗漏或误匹配 |
| BUG-023 | `missing` 类型 `expect_retrieval` 标记错误导致 FPR 计算异常 | [inbox](inbox/一个关于FPR的bug，及两种修复方案.md) | ✅ 已完成 | commit `5e9fa65`：采用方案 A 将 `expect_retrieval` 改为 `True`，同时新增 `expect_no_answer` 跳过 faithfulness |
| BUG-024 | Chunk JSONL 文本编码损坏导致 chunk-level 指标无法计算 | [hybrid-metrics-fix.md](guides/development/hybrid-metrics-fix.md#6-未修复问题chunk-jsonl-文本编码损坏) | 📋 待处理 | chunk text 字段中文字符为乱码，source_chunks 始终为空；[详情](reviews/issues/bug-024-chunk-encoding-and-page-info.md) |
| BUG-025 | `source_chunks` 字段始终为空，文档级策略无法精确到页或 chunk | [TODO.md](../TODO.md) | 📋 待处理 | 需调研文档级策略能否精确到页/chunk；[详情](reviews/issues/bug-025-source-chunks-empty.md) |
| BUG-026 | 全量缓存 hash 计算问题导致缓存无法命中 | [TODO.md](../TODO.md) | ✅ 已完成 | pipeline.py 传了错误的 artifacts_dir，改为使用 ArtifactCache 动态计算路径 |
| BUG-027 | Token 统计功能可能无法正确识别多变体各变体消耗 | [TODO.md](../TODO.md) | ✅ 已完成 | 新增 get_summary_by_variant() 方法，run_experiment 中为 variant_tracker 添加 variant_name metadata |
| BUG-028 | 审查脚本缺少页码信息，无法定位 ground truth 出自哪一页 | [TODO.md](../TODO.md) | 📋 待处理 | source_chunks 字段未实装，审查时无法精确定位 |

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
| FEAT-014 | 透明版完整实验报告 | [TODO.md](../TODO.md) | 📋 待处理 | 大 | 含问题/答案/emb/recall/提示词/回复/指标计算过程；[详情](reviews/issues/feat-014-transparent-report.md) |
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
| FEAT-028 | 配置验证系统（Pydantic 模型验证 + 必填项校验 + 范围校验） | 深度审查 | 📋 待处理 | 中 | 当前 yaml.safe_load 直接加载无验证；需新增 pydantic 依赖；[详情](reviews/issues/feat-028-config-validation.md) |
| FEAT-029 | 项目记忆系统 Skill（project-memory） | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 跨 session 项目记忆读写方法论，替代原"Project Context Skill"概念 |
| FEAT-030 | 实验报告 sources 字段细化 | [INV-001 调查](reviews/investigations/inv-001-sources-field.md) | 📋 待处理 | 中 | 增加 retrieved_chunks 字段、标题层级信息，改善命中率虚高问题 |
| FEAT-031 | golden_qa.json 重做与回归测试更新 | [INV-006 调查](reviews/investigations/inv-006-golden-test.md) | ✅ 已完成 | 中 | Golden 生成逻辑收编入 TestSetGenerator，统一链路 |
| FEAT-032 | 评估模型与生成模型分离配置 | [INV-007 调查](reviews/investigations/inv-007-eval-system-reliability.md) | 📋 待处理 | 中 | 解决 faithfulness/answer_relevancy 自评偏差问题 |
| FEAT-033 | 增强日志系统覆盖率与 pytest 集成 | [INV-003 调查](reviews/investigations/inv-003-logging.md) | 📋 待处理 | 中 | pytest-loguru 集成、配置加载日志、文件写入结构化日志 |
| FEAT-034 | 开源准备度完善 | [INV-005 调查](reviews/investigations/inv-005-open-source.md) | ✅ 已完成 | 中 | CONTRIBUTING.md 已创建，README 已更新至 v0.1.8 |
| FEAT-035 | 元数据增强（页码+标题层级） | [INV-010 调查](reviews/investigations/inv-010-metadata.md) | 📋 待处理 | 中 | chunk metadata 增加 page_number 和 headings 字段 |
| FEAT-036 | PDF 表格解析质量提升 | [INV-016 调查](reviews/investigations/inv-016-table-parsing.md) | 📋 待处理 | 中 | fitz_pdfplumber 为推荐解析器、补充 OCR 支持、表格参数调优 |
| FEAT-037 | benchmark_use_ocr 对比维度参数化 | benchmark_use_ocr 扩展规划 | 📋 待处理 | 中 | 将 OCR 开/关硬编码改为 YAML 配置驱动，支持任意 pymupdf4llm 选项的 A/B 对比 |
| FEAT-038 | benchmark_use_ocr 与 exp 系统集成 | benchmark_use_ocr 扩展规划 | 📋 待处理 | 大 | 让实验系统支持单步对比（如 Parser 配置差异），需 Meal 与 Variant 解耦、S1 阶段 variant 级别记录 |
| FEAT-039 | 交互式审查脚本（Papers Please 风格） | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 指定问题集逐题审查：展示问题/预期答案/实际答案/信息源/分数，用户打回或放过，自动生成审查报告 |
| FEAT-040 | 审查脚本 PDF 高亮唤起功能 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 审查时唤起 PDF 并高亮相关段落关键词，审核完自动关闭 |
| FEAT-041 | 多变体实验增量补做 | [TODO.md](../TODO.md) | 📋 待处理 | 大 | 支持在已跑完基线上追加 variant，只算新增部分，最终综合报告 |
| FEAT-043 | 手动中断后部分生成报告 | [TODO.md](../TODO.md) | 📋 待处理 | 中 | 中断后根据已完成 variant 生成部分报告，需确认中断时是否保存已完成结果 |

---

## Refactor

| ID | 描述 | 来源 | 状态 | 规模 | 备注 |
|----|------|------|------|------|------|
| RF-001 | CLI 输出规范化（172 处 print） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | ✅ 已完成 | 中 | src/ 中仅剩 artifact_cli.py 的 20 处 print（CLI 工具合理用法）；pipeline.py 4 处已替换为 logger.info |
| RF-002 | 项目结构整理（根目录 .py 文件） | [原 TODO.md](../TODO.md) | ✅ 已完成 | 小 | 方案 C：合并 interactive.py 到 main.py，新增 --interactive 参数；详见 [评估报告](reviews/investigations/rf-002-project-structure.md) |
| RF-004 | 硬编码配置值提取到 config.yaml | v0.1.7 合并验收 | ✅ 已完成 | 中 | metrics.py/experiment_reporter.py/test_generator.py 中模型名、API URL、max_tokens、temperature 硬编码 |
| RF-005 | Anthropic 客户端创建统一抽象 | v0.1.7 合并验收 | ✅ 已完成 | 小 | 提取 create_anthropic_client 到 src/llm_client.py，4处→1处 |
| RF-007 | exp_configs 版本维护机制沉淀 | [TODO.md](../TODO.md) | 📋 待处理 | 小 | 随版本演进清洗模板，考虑沉淀为 skill 或系统提示词 |
| RF-008 | backlog issue 详细信息记录 | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 新增 docs/reviews/issues/ 详情文件机制，backlog 备注列添加超链接；todo-archiver skill 已更新 |
| RF-009 | commit-rule 与 CLAUDE.md 渐进式披露 | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 三层渐进式披露：commit-rule 23行+CLAUDE.md 3行+SKILL.md+docs/guides/commit-conventions.md |
| RF-010 | lint/ruff 配置 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 添加代码检查工具 |
| RF-011 | docs 目录组织度维护 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 打扫卫生时考量 docs 目录组织度，恢复整洁度 |
| RF-012 | 旧格式 test_sets DeprecationWarning 清理 | [TODO.md](../TODO.md) | ⏳ 已延期 | ⬇️ 低优先级暂缓；chunk-based 策略有不可替代优势，待升级为 chunk-aware 策略后再清理；详见 [分析报告](reviews/investigations/rf-012-chunk-vs-document-strategy-analysis.md) |
| RF-013 | chunk_id 命名规范化（当前依赖文件名含下划线时解析脆弱） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P2-3) | 📋 待处理 | 小 | 需设计新格式并考虑迁移兼容 |
| RF-014 | normalize_source 匹配精度提升（当前仅比较文件名 stem，过于宽松） | [pipeline-deep-audit.md](pipeline-deep-audit.md#P6-1) | ✅ 已完成 | 小 | 已在 retrieval.py/dedup.py/builtin_evaluator.py 中统一使用 include_parent=True |
| RF-015 | 更新 hyperparameter-guide.md 增加新解析链路讲解 | [TODO.md](../TODO.md) | ✅ 已完成 | 小 | 新增 PDF 解析策略章节，介绍 pymupdf4llm 和 fitz_pdfplumber 两种解析器 |
| RF-006 | TestSet 独立管理系统重构 | 设计文档 | ✅ 已完成 | 大 | 新增 TestSetManager，重构 prepare_test_sets，支持 on_missing 三种模式 |
| RF-017 | 自定义异常类型定义（RAGPipelineError、RetrievalError 等） | 深度审查 | ✅ 已完成 | 小 | 新增 src/exceptions.py，9个业务异常类，全项目替换 |
| RF-018 | Pipeline 类职责拆分（当前 560 行承担全流程） | 深度审查 | 📋 待处理 | 大 | 可拆分为 PipelineOrchestrator + 各阶段 Stage 类 |
| RF-019 | answer_relevancy 评分稳定性改进 | [INV-007 调查](reviews/investigations/inv-007-eval-system-reliability.md) | 📋 待处理 | 小 | overall_score 由 LLM 自主决定，考虑引入 RAGAS 式伪问题生成作为交叉验证 |
| RF-020 | 全量测试路径重构（data/parsed→artifacts） | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 旧路径全面迁移至 Artifact 体系，新增 Pointer 机制和 artifact_cli 工具 |

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
| OPT-009 | chunker 日志降噪（逐 chunk 日志打包输出） | [TODO.md](../TODO.md) | ✅ 已完成 | 逐文件 INFO→DEBUG，保留汇总 INFO 日志 |
| OPT-010 | 大规模数据 Qdrant 本地模式性能优化 | [TODO.md](../TODO.md) | 📋 待处理 | 全量 45077 chunks 触发 20000+ points 警告，需评估 Docker/Cloud 方案或分片策略 |

---

## Investigation

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| INV-002 | 验证问题生成策略可扩展性 | [原 TODO.md](../TODO.md) | ⏳ 待定 | 依赖黄金测试集落地 |
| INV-007 | 评测系统可靠性全面审查 | [TODO.md](../TODO.md) | 📋 待处理 | 致命 bug 已修复，系统从"不可信"提升到"部分可信"；产出 FEAT-032/BUG-022/RF-019 三个子条目 |
| INV-009 | 问题集扩大与指标收敛趋势 | [TODO.md](../TODO.md) | 📋 待处理 | 等 v0.1.9 发版确认数据有效性后推进 |
| INV-020 | 大规模数据索引构建性能评估 | 深度审查 | 📋 待处理 | ⬇️ 降级优先级；当前规模性能可接受，10万+ chunks 时需流式 embedding |
| INV-022 | 多 worktree 并行开发时 issue 编号撞车问题 | [TODO.md](../TODO.md) | 📋 待处理 | 纯文本 issue 系统在 merge 时同步，递增编号易撞车；需调研 hash 指纹方案或借鉴 GitHub 集中式 issue 系统 |

---

## Test

| ID | 描述 | 来源 | 状态 | 优先级 | 备注 |
|----|------|------|------|--------|------|
| TEST-001 | 补充 generator 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | ✅ 已完成 | 高 | 空输入、None值、极端值测试 |
| TEST-002 | 补充 test_set_manager 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | ✅ 已完成 | 高 | 文件不存在、无效数据、空列表测试 |
| TEST-003 | 补充 experiment 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | ✅ 已完成 | 高 | 配置缺失、无效配置、空测试集测试 |
| TEST-004 | 补充 run_experiment 模块边界条件测试 | [INV-017](reviews/inv-017-boundary-condition-test-coverage.md) | ✅ 已完成 | 高 | 权限错误、文件不存在、无效配置测试 |
| TEST-005 | 补充 generator 模块异常路径测试 | [INV-018](reviews/inv-018-exception-path-test-coverage.md) | ✅ 已完成 | 高 | API调用失败、超时、速率限制测试 |
| TEST-006 | 补充 experiment 模块异常路径测试 | [INV-018](reviews/inv-018-exception-path-test-coverage.md) | ✅ 已完成 | 高 | 无效配置、权限错误等异常测试 |
| TEST-007 | 补充 run_experiment 模块异常路径测试 | [INV-018](reviews/inv-018-exception-path-test-coverage.md) | ✅ 已完成 | 高 | 文件操作异常测试 |
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
| BUG-023 | missing 类型 expect_retrieval 标记错误导致 FPR 计算异常 | inbox | 2026-04-24 |

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
| FEAT-042 | 实验成功后才生成 LLM 报告 | [TODO.md](../TODO.md) | 2026-04-26 |
| FEAT-034 | 开源准备度完善 | [INV-005 调查](reviews/investigations/inv-005-open-source.md) | 2026-04-26 |
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
| RF-014 | normalize_source 匹配精度提升 → 已统一使用 include_parent=True | [pipeline-deep-audit.md](pipeline-deep-audit.md#P6-1) | 2026-04-26 |
| BUG-026 | 全量缓存 hash 路径不一致 → pipeline.py 改用 ArtifactCache 动态计算 | [TODO.md](../TODO.md) | 2026-04-26 |
| BUG-027 | Token 统计按 variant 区分 → 新增 get_summary_by_variant() | [TODO.md](../TODO.md) | 2026-04-26 |
| OPT-009 | chunker 日志降噪 → 逐文件 INFO→DEBUG | [TODO.md](../TODO.md) | 2026-04-26 |
| RF-001 | CLI 输出规范化 → src/ 中仅剩 artifact_cli.py 的 20 处 print（合理用法） | [v0.1.5 code-review](reviews/v0.1.5/code-review.md) | 2026-04-26 |
| RF-002 | 项目结构整理 → 方案 C：合并 interactive.py 到 main.py | [原 TODO.md](../TODO.md) | 2026-04-26 |
| RF-008 | backlog issue 详细信息记录 → 新增 docs/reviews/issues/ 详情文件机制 | [TODO.md](../TODO.md) | 2026-04-26 |

### Investigation

| ID | 描述 | 来源 | 完成日期 |
|----|------|------|---------|
| INV-004 | 实验资产包 token summary 记录 → 已实现保存 token_summary.json/txt | [原 TODO.md](../TODO.md) | 2026-04-19 |
| INV-008 | LLM 报告假设性问题类型提示词更新 → 已更新为 document 策略六类 | [TODO.md](../TODO.md) | 2026-04-21 |
| INV-012 | 测试体系深度审查（883条是否过多） | [TODO.md](../TODO.md) | 2026-04-21 |
| INV-017 | 边界条件测试覆盖评估（空输入、极端值等） | 深度审查 | 2026-04-24 |
| INV-018 | 异常路径测试覆盖评估 | 深度审查 | 2026-04-24 |
| INV-001 | 实验报告 sources 字段细化 → 转为 FEAT-030 | [原 TODO.md](../TODO.md) | 2026-04-24 |
| INV-003 | 日志系统最佳实践 → 转为 FEAT-033 | [原 TODO.md](../TODO.md) | 2026-04-24 |
| INV-005 | 开源准备度核实 → 转为 FEAT-034 | [TODO.md](../TODO.md) | 2026-04-24 |
| INV-006 | golden test 策略调查 → 转为 FEAT-031 | [TODO.md](../TODO.md) | 2026-04-24 |
| INV-010 | 元数据增强调查 → 转为 FEAT-035 | [TODO.md](../TODO.md) | 2026-04-24 |
| INV-011 | 开源许可证评估 → 结论：保持 MIT 不更换 | [TODO.md](../TODO.md) | 2026-04-24 |
| INV-013 | Ground Truth 质量调查 → 与 FEAT-021 合并 | [RAGAS 指南](guides/ragas-evaluation.md) | 2026-04-24 |
| INV-014 | RAGAS vs Builtin 指标对比 → 与 OPT-005 合并 | [RAGAS 指南](guides/ragas-evaluation.md) | 2026-04-24 |
| INV-015 | tiktoken/BGE tokenizer 差异 → 已通过 encoding: "bge" 解决 | [pipeline-deep-audit.md](pipeline-deep-audit.md) | 2026-04-24 |
| INV-016 | PDF 表格解析质量调研 → 转为 FEAT-036 | [pipeline-deep-audit.md](pipeline-deep-audit.md) | 2026-04-24 |
| INV-019 | pytest-xdist 可行性评估 → 结论：当前测试规模小，收益有限 | 深度审查 | 2026-04-24 |
| INV-021 | 路径安全检查 → 结论：CLI 工具无远程攻击面，可关闭 | 深度审查 | 2026-04-24 |

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
