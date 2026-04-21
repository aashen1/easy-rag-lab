# 评估积压 Issue 及修复计划（2026-04-22 更新版）

> **Workspace:** b:\project\w1-easy-rag
> **基准版本**：v0.1.8
> **上次更新**：2026-04-22

---

## 变更摘要（相比原版）

自原版文档编写以来，以下 issue 已完成修复：

| Issue ID | 描述 | 完成方式 | 完成时间 |
|----------|------|----------|----------|
| BUG-017(pytest) | pytest tmp 目录 FileExistsError | commit a99cc2f | 2026-04-22 |
| FEAT-023 | Context 长度控制 | commit 1670346 | 2026-04-22 |
| RF-014 | normalize_source 匹配精度提升 | commit e4e3f14 | 2026-04-22 |
| RF-013 | chunk_id 命名规范化 | Stream 2 完成 | 2026-04-22 |
| INV-015 | tiktoken/BGE tokenizer 差异量化 | Stream 2 完成 | 2026-04-22 |
| RF-009 | commit-rule 与 CLAUDE.md 渐进式披露 | commit ad546a5 | 2026-04-22 |

Stream 2 剩余 issue（INV-010、OPT-007）在其他对话中推进中。

---

## 🔴 第一梯队：直接影响评测结果可信度

### BUG-017 — expected_sources 标注错误 ⚠️ 仍活跃
- **问题**：LLM 基于整篇文档生成问题时，`source_files` 直接设为该文档路径，但问题可能涉及文档中提到的其他实体（如 q010 问光模块公司但 expected 指向中芯国际年报），导致 hit_rate=0.0 是假阴性
- **修复思路**：在问题生成后，增加一步"source 校验"——让 LLM 判断问题实际涉及哪些文档/实体，然后与 meal 中可用文档做匹配，修正 `expected_sources`。或者更根本地，在生成策略中区分"问题来源文档"和"问题目标文档"
- **规模**：中，需改动 test_generator.py 的生成逻辑
- **风险**：引入额外 LLM 调用，增加 token 消耗
- **状态**：📋 待处理

### FEAT-025 — 检索器层面文档级去重 ⚠️ 仍活跃
- **问题**：top 5 结果全部来自同一文档，检索多样性为零，hit_rate 虚高
- **修复思路**：在 retriever.py 的检索结果后处理中添加文档多样性分配逻辑。比如：先按 score 排序，然后按文档分组，每组最多取 N 个 chunk，保证 top_k 结果覆盖多个文档
- **规模**：中，改动 retriever.py
- **风险**：低，纯后处理逻辑，不影响索引构建
- **状态**：📋 待处理

### ~~RF-014 — normalize_source 匹配精度提升~~ ✅ 已完成
- **完成方式**：commit e4e3f14，增加 `include_parent` 参数，返回 `{parent_name}/{stem}` 格式
- **备注**：Stream 2 Task 3 已完成，config.yaml 新增 `evaluation.normalize_source_include_parent: true`

### ~~FEAT-023 — Context 长度控制~~ ✅ 已完成
- **完成方式**：commit 1670346，在 Generator 中新增 `_truncate_contexts()` 方法，config.yaml 新增 `generation.max_context_tokens`
- **备注**：从尾部截断 contexts，保留相似度最高的前排 chunk

---

## 🟡 第二梯队：影响评测体系完整性

### FEAT-014 — 透明版完整实验报告 ⚠️ 仍活跃 · v0.1.9 核心
- **问题**：当前报告不透明，无法验证基线性能是否虚高
- **修复思路**：在实验结果 JSON 中增加 verbose 模式，记录：原始问题、expected_answer、检索到的 chunk 文本、给 LLM 的完整 prompt、LLM 原始回复、各指标中间计算过程
- **规模**：大，涉及 experiment_reporter.py、evaluator.py 等多处
- **风险**：输出文件会变大，需控制粒度
- **状态**：📋 待处理，v0.1.9 版本主要任务
- **优先级说明**：这是 v0.1.9 的**核心交付物**，是确认基线性能是否虚高的关键手段

### ~~INV-015 — tiktoken 与 BGE tokenizer 的 token 数差异量化~~ ✅ 已完成
- **完成方式**：Stream 2 Task 1，创建 `scripts/analyze_tokenizer_diff.py`
- **备注**：纯调研脚本，结论将影响 chunk_size 配置决策

### ~~RF-013 — chunk_id 命名规范化~~ ✅ 已完成
- **完成方式**：Stream 2 Task 2，chunk_id 格式改为 `{source_name}::chunk::{index:03d}`，`_parse_chunk_id` 同时支持新旧格式
- **备注**：向后兼容旧格式，含下划线的文件名不再产生解析歧义

### FEAT-011 — 补做 LLM 报告功能 ⚠️ 仍活跃
- **问题**：实验跑完后才发现没开 LLM 总结，想补看报告
- **修复思路**：在 experiment_reporter.py 中增加一个独立的 `generate_llm_report(results_path)` 函数，读取已有实验结果 JSON，调用 LLM 生成总结报告
- **规模**：小，新增一个入口函数
- **风险**：低
- **状态**：📋 待处理

### RF-012 — 旧格式 test_sets DeprecationWarning 清理 ⚠️ 仍活跃
- **问题**：测试中大量旧格式警告
- **修复思路**：找到产生 DeprecationWarning 的代码路径，要么更新旧格式测试数据文件，要么在代码中统一处理格式转换并移除 warning
- **规模**：小
- **风险**：低
- **状态**：📋 待处理

### ~~BUG-017(pytest) — pytest tmp 目录 FileExistsError~~ ✅ 已完成
- **完成方式**：commit a99cc2f，添加 `tmp_path_retention_count=0` + `pytest_configure` 预清理
- **备注**：详见 troubleshooting 文档

---

## 🟢 第三梯队：改善体验和工程规范

### RF-001 — CLI 输出规范化（172 处 print） ⚠️ 仍活跃
- **修复思路**：批量替换 `print()` 为 `loguru` 的 `logger.info()`/`logger.debug()`
- **规模**：中，纯机械替换但量大
- **风险**：输出格式变化
- **状态**：📋 待处理，**必须最后做**（横切性质，触碰几乎所有源文件）

### ~~RF-009 — commit-rule 与 CLAUDE.md 渐进式披露~~ ✅ 已完成
- **完成方式**：commit ad546a5，三层渐进式披露架构：commit-rule 23行 + CLAUDE.md 3行 + SKILL.md + docs/guides/commit-conventions.md

### FEAT-012 — 断点续传 ⚠️ 仍活跃
- **修复思路**：在实验运行过程中，每完成一个问题就落盘中间结果。下次启动时检测到中间结果文件，从断点继续
- **规模**：大
- **风险**：需处理基模变化、时间戳标记等边界情况
- **状态**：📋 待处理
- **依赖**：FEAT-014（透明版报告定义了 verbose JSON 格式，断点续传的中间落盘依赖该格式）

### FEAT-015 — 更细粒度实验记录 ⚠️ 仍活跃
- **修复思路**：在实验结果中增加 token per chunk 的统计、文档分布、meal 分布等统计量
- **规模**：中
- **风险**：低
- **状态**：📋 待处理

### OPT-004 — Hit Rate 扩充到 Recall@3/5/10 ⚠️ 仍活跃
- **修复思路**：在 metrics.py 中增加 Recall@K 指标，K 取 3/5/10
- **规模**：小
- **风险**：低
- **状态**：📋 待处理

### INV-010 — 元数据增强改善 chunk 命中 🔄 进行中（Stream 2）
- **修复思路**：在 chunk 元数据中增加 PDF 页码和 MD 标题层级信息，改善 chunk 命中逻辑
- **规模**：中
- **风险**：需改动 chunker.py 和 parser.py
- **状态**：🔄 Stream 2 Task 4 进行中（parser.py 页码标记 + chunker.py 元数据增强）

### FEAT-024 — 页眉页脚清洗 ⚠️ 仍活跃
- **修复思路**：在 parser.py 的 PDF 解析后处理中，用正则或规则去除页码、logo 文字、水印等
- **规模**：中
- **风险**：规则可能误删正文
- **状态**：📋 待处理

### OPT-007 — 基线 chunk_overlap 非零优化 🔄 待启动（Stream 2）
- **修复思路**：通过对比实验确定合适的非零 chunk_overlap 值
- **规模**：小
- **风险**：低
- **状态**：📋 Stream 2 Task 5 待启动，依赖 INV-010 和 INV-015 结论

### 其余 RAGAS 相关（FEAT-020/021/022, OPT-005/006, BUG-018/019/020）
- 这些都是 RAGAS 集成的后续优化，当前 RAGAS 基本链路已通，建议等 v0.1.9 baseline 稳定后再推进
- **状态**：📋 待处理，建议延后至 v0.1.11

### 其余 Investigation（INV-001/002/003/005/006/007/009/011/013/014/016）
- 多数为调研性质，不涉及直接代码改动，可按需推进
- **INV-007**（评测系统可靠性全面审查）与 v0.1.9 核心任务高度相关，建议优先

---

## 📊 更新后汇总

### 活跃 issue 汇总（按优先级）

| 优先级 | Issue ID | 简述 | 预估规模 | 当前状态 |
|--------|----------|------|----------|----------|
| 🔴 P0 | BUG-017 | expected_sources 标注错误 | 中 | 📋 待处理 |
| 🔴 P0 | FEAT-025 | 检索结果文档级去重 | 中 | 📋 待处理 |
| 🟡 P1 | FEAT-014 | 透明版实验报告 | 大 | 📋 待处理 · v0.1.9 核心 |
| 🟡 P1 | FEAT-011 | 补做 LLM 报告 | 小 | 📋 待处理 |
| 🟡 P1 | RF-012 | DeprecationWarning 清理 | 小 | 📋 待处理 |
| 🟡 P1 | INV-007 | 评测系统可靠性审查 | 中 | 📋 待处理 · v0.1.9 相关 |
| 🟢 P2 | RF-001 | print→loguru | 中 | 📋 待处理 · 最后做 |
| 🟢 P2 | FEAT-012 | 断点续传 | 大 | 📋 待处理 |
| 🟢 P2 | FEAT-015 | 细粒度实验记录 | 中 | 📋 待处理 |
| 🟢 P2 | OPT-004 | Recall@K | 小 | 📋 待处理 |
| 🟢 P2 | INV-010 | 元数据增强 | 中 | 🔄 Stream 2 进行中 |
| 🟢 P2 | FEAT-024 | 页眉页脚清洗 | 中 | 📋 待处理 |
| 🟢 P2 | OPT-007 | chunk_overlap 非零优化 | 小 | 📋 Stream 2 待启动 |

### 已完成 issue 汇总（自原版以来）

| Issue ID | 简述 | 完成方式 |
|----------|------|----------|
| RF-014 | normalize_source 精度提升 | commit e4e3f14 |
| FEAT-023 | Context 长度控制 | commit 1670346 |
| RF-013 | chunk_id 命名规范化 | Stream 2 Task 2 |
| INV-015 | tiktoken/BGE token 差异量化 | Stream 2 Task 1 |
| BUG-017(pytest) | pytest tmp 目录冲突 | commit a99cc2f |
| RF-009 | 渐进式披露 | commit ad546a5 |

---

## 并行开发路线（更新版）

基于当前项目状态，8 路并行方案中各 Stream 的进展如下：

### Stream 1：解析层 🏭 — 📋 待处理
**独占文件**：`src/parser.py`

| Issue | 状态 |
|-------|------|
| FEAT-024（页眉页脚清洗） | 📋 待处理 |
| INV-016（PDF 表格解析质量评估） | 📋 待处理 |

### Stream 2：分块层 + 指标工具层 🔧 — 🔄 进行中
**独占文件**：`src/chunker.py`、`eval/metrics/utils.py`

| Issue | 状态 |
|-------|------|
| INV-015（tiktoken/BGE 差异量化） | ✅ 已完成 |
| RF-013（chunk_id 命名规范化） | ✅ 已完成 |
| RF-014（normalize_source 精度提升） | ✅ 已完成 |
| INV-010（元数据增强） | 🔄 进行中 |
| OPT-007（chunk_overlap 非零优化） | 📋 待启动 |

### Stream 3：检索层 🔍 — 📋 待处理
**独占文件**：`src/retriever.py`、`src/pipeline.py`

| Issue | 状态 |
|-------|------|
| FEAT-025（检索器文档级去重） | 📋 待处理 |

### Stream 4：生成层 🤖 — ✅ 已完成
**独占文件**：`src/generator.py`

| Issue | 状态 |
|-------|------|
| FEAT-023（Context 长度控制） | ✅ 已完成 |

### Stream 5：问题生成与测试集 📝 — 📋 待处理
**独占文件**：`src/test_generator.py`、`src/test_set_manager.py`

| Issue | 状态 |
|-------|------|
| BUG-017（expected_sources 标注错误） | 📋 待处理 |
| RF-012（DeprecationWarning 清理） | 📋 待处理 |
| INV-013（Ground Truth 质量有限） | 📋 待处理 |
| INV-002（问题生成策略可扩展性） | ⏳ 待定 |

### Stream 6：实验报告系统 📊 — 📋 待处理 · v0.1.9 核心
**独占文件**：`eval/run_experiment.py`、`eval/experiment_reporter.py`

| Issue | 状态 |
|-------|------|
| FEAT-014（透明版实验报告） | 📋 待处理 · v0.1.9 核心 |
| FEAT-011（补做 LLM 报告） | 📋 待处理 |
| FEAT-015（细粒度实验记录） | 📋 待处理 |
| FEAT-012（断点续传） | 📋 待处理 |
| FEAT-013（部分评测支持） | 📋 待处理 |
| INV-001（sources 字段细化） | 📋 待处理 |

### Stream 7：RAGAS 评测 🧪 — 📋 待处理 · 建议延后至 v0.1.11
**独占文件**：`eval/evaluators/ragas_evaluator.py`

| Issue | 状态 |
|-------|------|
| BUG-018（RAGAS 版本兼容性） | 📋 待处理 |
| BUG-019（context_precision 聚合位置） | 📋 待处理 |
| BUG-020（raise_exceptions 行为差异） | 📋 待处理 |
| FEAT-020（RAGAS 版本升级适配） | 📋 待处理 |
| FEAT-022（RAGAS Token 追踪） | 📋 待处理 |
| OPT-006（RAGAS 缓存与增量） | 📋 待处理 |

### Stream 8：Builtin 评测器 + 指标扩展 📏 — 📋 待处理
**独占文件**：`eval/evaluators/builtin_evaluator.py`、`eval/metrics/*.py`

| Issue | 状态 |
|-------|------|
| OPT-004（Recall@K） | 📋 待处理 |
| OPT-005（RAGAS/builtin 归一化） | 📋 待处理 |
| INV-007（评测系统可靠性审查） | 📋 待处理 · v0.1.9 相关 |
| INV-014（RAGAS vs Builtin 对比） | 📋 待处理 |

### 无法并入 8 路的独立 issue

| Issue | 类型 | 状态 | 建议处理 |
|-------|------|------|----------|
| RF-001 | print→loguru | 📋 待处理 | **最后做**，等所有流合并后统一替换 |
| RF-002 | 根目录 .py 文件整理 | 📋 待处理 | 等 Stream 6 完成后做 |
| OPT-001 | 新用户链路性能优化 | 📋 待处理 | 拆为子任务分别并入 Stream 1 和 Stream 2 |
| OPT-002 | 集成测试时间优化 | 📋 待处理 | 独立小任务 |
| FEAT-008 | test-future-directions 落实 | 📋 待处理 | 独立小任务 |
| FEAT-010 | golden_qa 数据源适配指引 | 📋 待处理 | 独立小任务 |
| FEAT-017 | CI/CD 集成 | 📋 待处理 | 独立小任务 |
| RF-007 | exp_configs 版本维护 | 📋 待处理 | 独立小任务 |
| RF-008 | backlog 详细信息记录 | 📋 待处理 | 独立小任务 |
| RF-011 | docs 目录组织度 | 📋 待处理 | 独立小任务 |
| INV-003 | 日志最佳实践 | 📋 待处理 | 纯调研 |
| INV-005 | 开源准备度核实 | 📋 待处理 | 纯调研 |
| INV-006 | golden test 是否基于老策略 | 📋 待处理 | 纯调研 |
| INV-009 | 指标收敛趋势 | 📋 待处理 | 依赖 v0.1.9 |
| INV-011 | 开源许可证评估 | 📋 待处理 | 纯调研 |
| FEAT-021 | Ground Truth 手动标注工具 | 📋 待处理 | 大，延后 |

---

## v0.1.9 发版路径建议

基于当前 issue 状态，v0.1.9 的核心目标是**确认基线性能是否虚高**，建议按以下顺序推进：

```
Phase 1: 基础设施修复（可并行）
├── Stream 5: BUG-017（expected_sources 标注错误）→ 修复后 hit_rate 才可信
├── Stream 3: FEAT-025（检索器文档级去重）→ 修复后检索多样性才合理
└── Stream 8: INV-007（评测系统可靠性审查）→ 确认评测逻辑本身无问题

Phase 2: 透明报告（核心交付）
└── Stream 6: FEAT-014（透明版实验报告）→ 确认基线性能是否虚高的关键手段

Phase 3: 基线标定
├── 跑基线测试，用透明报告验证
├── 精调 golden_test（50-150 问）
└── 产出有说服力的基线实验报告
```

Phase 1 的三个 issue 互不冲突，可完全并行。Phase 2 依赖 Phase 1 的修复结果（否则报告中的数据仍不可信）。Phase 3 是验证和产出阶段。
