# 独立 Issue 批量处理记录

> 会话日期：2026-04-23
> 工作模式：Spec → Implementation → Verification
> Spec 文档：`.trae/specs/independent-issues-batch/`

---

## 1. 接到的任务

用户要求批量处理 5 个独立的 backlog issue：

| Issue ID | 类型 | 描述 | 产出类型 |
|----------|------|------|----------|
| INV-019 | Investigation | 测试并行化可行性评估（pytest-xdist） | 分析报告 |
| INV-021 | Investigation | 文件路径安全检查（防路径遍历攻击） | 分析报告 |
| RF-017 | Refactor | 自定义异常类型定义，纯代码风格，无逻辑变更 | 代码变更 |
| RF-002 | Refactor | 项目结构整理，需先评估影响范围 | 评估报告 |
| FEAT-011 | Feature | 补做 LLM 报告功能，功能独立 | 代码变更 |

用户明确指出：INV-019 和 INV-021 可并行产出分析报告；RF-017 是纯代码风格无逻辑变更；RF-002 需先评估影响范围；FEAT-011 功能独立。

---

## 2. 完成的修复

### 2.1 INV-019：测试并行化可行性评估

**产出**：`docs/reviews/inv-019-test-parallelization.md`

**修复思路**：
1. 运行 `pixi run pytest tests/ -m "not integration" --durations=0` 获取 1089 个单元测试的执行时间基线
2. 逐个审查 `tests/conftest.py` 中的 fixture 作用域和隔离性
3. 识别文件系统竞争、Qdrant 实例共享等并行化风险
4. 评估 pytest-xdist 配置方案（worker 数量、分发策略）
5. 给出分阶段启用建议

**核心结论**：
- 所有 fixture 均为 function-scoped，并行安全
- 主要瓶颈是 Windows 上 teardown 阶段清理临时文件耗时（占 60%+）
- 建议启用 pytest-xdist，预期加速 2-4x
- 阻塞项：需安装 pytest-xdist、验证单 worker 兼容性

**判定依据**：报告包含完整的 5 项要求内容（时间基线、fixture 隔离性分析、风险清单、配置建议、推荐方案），且数据来自实际测试运行结果。

---

### 2.2 INV-021：文件路径安全检查

**产出**：`docs/reviews/inv-021-file-path-security.md`

**修复思路**：
1. 全量搜索 `src/` 和 `eval/` 中的 `Path()`、`open()`、`.resolve()`、`relative_to()` 模式
2. 按来源分类路径构造入口：配置驱动（12 个配置键）、用户输入（CLI 参数）、硬编码默认路径（14 处）
3. 审计已有保护措施（仅 `meal.py` 的 `relative_to()` 检查）
4. 评估缺失保护的风险等级（高/中/低）
5. 提出统一路径验证函数等修复方案

**核心结论**：
- 高风险 3 项：`--config` 可读任意文件、`--output` 可写任意位置、`raw_dir` 配置篡改
- 中风险 7 项，低风险 11 项
- 项目中唯一显式路径遍历防护仅在 `meal.py:1530-1542`，且未使用 `.resolve()` 规范化路径
- 建议：创建 `validate_path_in_project()` 工具函数，逐步覆盖所有文件操作入口

**判定依据**：报告包含完整的 5 项要求内容（路径入口清单、已有保护、缺失保护及风险等级、推荐修复），且每项风险均标注了具体文件和行号。

---

### 2.3 RF-017：自定义异常类型定义

**产出**：新增 `src/exceptions.py`，修改 26 个源文件 + 24 个测试文件

**修复思路**：
1. 在 `src/exceptions.py` 中定义异常层次结构：`RAGPipelineError`（基类）+ 8 个子类（ConfigurationError、ParsingError、RetrievalError、IndexingError、GenerationError、MealError、TestSetError、EvaluationError）
2. 按语义映射规则逐文件替换 `raise ValueError/Exception/RuntimeError/TypeError/FileNotFoundError/ImportError` 为对应自定义异常
3. 保持所有错误消息文本和 `from e` 链式异常不变
4. 更新 `src/__init__.py` 导出所有异常类
5. 同步更新 24 个测试文件中的 `pytest.raises()` 调用
6. 运行 lint 和测试验证

**映射规则示例**：
- 配置校验失败 → `ConfigurationError`
- PDF/文档解析失败 → `ParsingError`
- 检索执行失败 → `RetrievalError`
- LLM 生成/API 调用失败 → `GenerationError`
- Meal 管理操作失败 → `MealError`
- 测试集管理操作失败 → `TestSetError`
- 评估计算失败 → `EvaluationError`

**判定依据**：
- `src/` 和 `eval/` 中不再有 `raise ValueError`、`raise Exception` 等通用异常（docstring 中的引用除外）
- 所有替换保持错误消息文本不变（抽查验证）
- 所有替换保持 `from e` 链式异常不变（抽查验证）
- `pixi run lint` 通过
- `pixi run pytest tests/ -m "not integration"` 1089 passed, 0 failed

**修复过程中发现的问题**：
- 初次替换后 97 个测试失败，原因是测试文件中 `pytest.raises(ValueError)` 等仍捕获旧异常类型
- 逐一更新 24 个测试文件后，仍有 1 个测试失败（`test_bm25_retriever.py::test_retrieve_before_index_raises`），原因是子代理将 BM25 索引未构建的错误映射为 `RetrievalError`，但源代码实际使用 `IndexingError`（更准确），修正测试后全部通过

---

### 2.4 RF-002：项目结构整理评估

**产出**：`docs/reviews/rf-002-project-structure.md`

**修复思路**：
1. 分析 `main.py`（704 行）和 `interactive.py`（79 行）的完整依赖关系
2. 逐行对比两个文件的交互式 Q&A 功能，识别 80% 逻辑重叠
3. 评估 4 种迁移方案：移入 `src/cli/`、保持根目录、合并 `interactive.py` 到 `main.py`、保持根目录+内部重构
4. 检查 pixi.toml 入口脚本、文档引用（约 65 处）等影响范围

**核心结论**：
- `interactive.py` 是 `main.py` 的功能子集，重叠率约 80%
- 推荐方案：合并 `interactive.py` 到 `main.py`（新增 `--interactive` 参数），后续按需提取 `src/cli/` 模块
- 注意：ruff lint 当前不检查根目录 `.py` 文件，存在盲区

**判定依据**：报告包含完整的 5 项要求内容（依赖分析、功能重叠分析、迁移方案及推荐、影响范围评估），且每项分析均有具体数据支撑。

---

### 2.5 FEAT-011：补做 LLM 报告功能

**产出**：修改 `eval/run_experiment.py` 和 `main.py`，新增 3 个测试

**修复思路**：
1. 在 `eval/run_experiment.py` 中新增 `generate_llm_report_only(exp_dir, system_config_path)` 函数
   - 验证实验目录和 manifest.json 是否存在
   - 加载系统配置和实验结果
   - 从 `results/` 子目录读取所有变体结果 JSON
   - 加载 config_snapshot.yaml 获取 LLM preset 配置
   - 创建 `ExperimentReporter` 并调用 `generate_variant_comparison_report(use_llm=True)` 生成 LLM 报告
   - 完善的异常处理：目录不存在、manifest 缺失、无变体结果均抛出 `ConfigurationError`；报告生成失败抛出 `EvaluationError`
2. 在 `main.py` 中新增 `--llm-report-only <EXP_DIR>` CLI 参数
3. 编写 3 个测试覆盖错误路径

**判定依据**：
- `generate_llm_report_only()` 函数已实现，包含完整的错误处理
- `--llm-report-only` CLI 参数已添加，目录不存在/文件缺失/API 不可用时均不崩溃
- 报告保存到 `{exp_dir}/experiment_report_llm.md`
- Token 消耗被 token_tracker 记录
- 3 个新测试全部通过
- `pixi run lint` 通过

---

## 3. 执行策略

本次采用 **Spec 模式**，流程为：

1. **Spec 阶段**：撰写 spec.md、tasks.md、checklist.md 三份文档，经用户审批后开始实施
2. **并行实施**：INV-019、INV-021、RF-002、RF-017 四个独立任务通过 Sub-Agent 并行推进
3. **串行修正**：RF-017 的测试更新因依赖源代码替换完成，在主线程串行执行；FEAT-011 在 RF-017 完成后实施（避免文件冲突）
4. **验证阶段**：系统性验证 38 项 checklist，全部通过

---

## 4. 文件变更清单

### 新增文件
| 文件 | 用途 |
|------|------|
| `src/exceptions.py` | 自定义异常层次结构 |
| `docs/reviews/inv-019-test-parallelization.md` | 测试并行化分析报告 |
| `docs/reviews/inv-021-file-path-security.md` | 文件路径安全审计报告 |
| `docs/reviews/rf-002-project-structure.md` | 项目结构评估报告 |

### 修改文件（源代码）
| 文件 | 变更内容 |
|------|----------|
| `src/__init__.py` | 导出 9 个异常类 |
| `src/pipeline.py` | ValueError/Exception → RetrievalError |
| `src/retriever.py` | ValueError/Exception → RetrievalError |
| `src/hybrid_retriever.py` | ValueError/Exception → RetrievalError |
| `src/bm25_retriever.py` | ValueError/RuntimeError/FileNotFoundError/Exception → RetrievalError/IndexingError |
| `src/parser.py` | FileNotFoundError/ValueError/Exception → ParsingError |
| `src/parsers/registry.py` | TypeError/ValueError/ImportError → ParsingError |
| `src/parsers/pymupdf4llm_parser.py` | FileNotFoundError/ValueError/Exception → ParsingError |
| `src/parsers/fitz_pdfplumber_parser.py` | FileNotFoundError/ValueError/Exception → ParsingError |
| `src/generator.py` | ValueError/Exception → GenerationError |
| `src/llm_client.py` | ValueError → GenerationError |
| `src/experiment.py` | ValueError/FileNotFoundError → ConfigurationError |
| `src/meal.py` | ValueError/FileNotFoundError → MealError |
| `src/test_set_manager.py` | ValueError/FileNotFoundError → TestSetError |
| `src/test_generator.py` | ValueError → TestSetError |
| `src/embedder.py` | ValueError/Exception → ConfigurationError/IndexingError |
| `src/indexer.py` | Exception/ValueError/FileNotFoundError → IndexingError |
| `src/chunker.py` | ValueError/Exception/FileNotFoundError → ParsingError |
| `src/semantic_chunker.py` | ValueError/Exception/FileNotFoundError → ParsingError |
| `src/sampler.py` | ValueError/Exception → ConfigurationError/ParsingError |
| `src/query_rewriter.py` | ValueError/Exception → ConfigurationError/GenerationError |
| `src/reranker.py` | ValueError/Exception → ConfigurationError/GenerationError |
| `src/utils.py` | ValueError → ConfigurationError |
| `eval/metrics/generation.py` | Exception/ValueError → EvaluationError |
| `eval/metrics/retrieval.py` | ValueError → EvaluationError |
| `eval/experiment_reporter.py` | ValueError/ImportError/Exception → EvaluationError |
| `eval/evaluators/ragas_evaluator.py` | ImportError/ValueError → EvaluationError |
| `eval/visualize.py` | FileNotFoundError/ImportError → EvaluationError |
| `eval/run_experiment.py` | 新增 generate_llm_report_only()；FileNotFoundError/ValueError → ConfigurationError/TestSetError/EvaluationError |
| `main.py` | 新增 --llm-report-only CLI 参数；新增 ConfigurationError 导入 |

### 修改文件（测试）
24 个测试文件更新了 `pytest.raises()` 中的异常类型，具体包括：test_bm25_retriever.py、test_chunker.py、test_embedder.py、test_experiment.py、test_generator.py、test_hybrid_retriever.py、test_indexer.py、test_meal.py、test_metrics.py、test_parser.py、test_parsers_base.py、test_parsers_fitz_pdfplumber.py、test_parsers_pymupdf4llm.py、test_pipeline.py、test_query_rewriter.py、test_reranker.py、test_retriever.py、test_run_eval.py、test_run_experiment.py、test_sampler.py、test_semantic_chunker.py、test_test_generator.py、test_test_set_manager.py、test_utils.py
