# 代码质量修复进度报告

> 基于审计报告：`code-quality-audit-report-260509.md` | 创建日期：2026-05-10 | 目标：系统性修复所有已识别问题

---

## 目录

1. [Phase 1: 止血（P0 严重问题）](#phase-1-止血p0-严重问题)
2. [Phase 2: 瘦身（P1 臃肿与重复）](#phase-2-瘦身p1-臃肿与重复)
3. [Phase 3: 治本（P2-P3 架构问题）](#phase-3-治本p2-p3-架构问题)
4. [Phase 4: 测试质量（P5 测试问题）](#phase-4-测试质量p5-测试问题)
5. [Phase 5: 清理（P4-P6 其他问题）](#phase-5-清理p4-p6-其他问题)

---

## Phase 1: 止血（P0 严重问题）

### 1.1 删除假测试

**文件**: `tests/test_run_experiment.py:1130-1132`

- [x] **删除假测试函数**
  - 位置: `test_dual_backend_results_have_namespace_prefix()`
  - 当前状态: 方法体只有 `pass`
  - 验收标准: 函数已删除或替换为真实测试逻辑
  - 优先级: P0
  - 预计耗时: 10分钟

---

### 1.2 删除死代码

#### 1.2.1 删除未使用的装饰器

**文件**: `eval/evaluators/error_handler.py:28-49`

- [x] **确认 `safe_metric_calculation()` 无调用**
  - 搜索范围: 全项目
  - 验收标准: 确认无调用点或找到遗漏的调用
  - 优先级: P0
  - 预计耗时: 5分钟

- [x] **删除 `safe_metric_calculation()` 装饰器**
  - 前置条件: 确认无调用
  - 验收标准: 代码已删除，所有测试通过
  - 优先级: P0
  - 预计耗时: 5分钟

#### 1.2.2 删除未使用的静态方法

**文件**: `eval/parser_benchmark/runner.py`

- [x] **确认 `_compute_config_hash()` 无调用**
  - 搜索范围: 全项目
  - 验收标准: 确认无调用点
  - 优先级: P0
  - 预计耗时: 5分钟

- [x] **删除 `_compute_config_hash()` 方法**
  - 前置条件: 确认无调用
  - 验收标准: 代码已删除，所有测试通过
  - 优先级: P0
  - 预计耗时: 5分钟

#### 1.2.3 删除无价值的转发模块

**文件**: `src/testset_review/pdf_viewer.py`

- [x] **确认 `PDFViewer` 仅重新导出**
  - 检查文件内容
  - 验收标准: 确认只有 `from scripts.pdf_viewer import PDFViewer`
  - 优先级: P0
  - 预计耗时: 5分钟
  - **决策**: 该文件被 `src/testset_cli/review.py` 和 `src/testset_review/__init__.py` 引用，作为包的公共API桥接层有实际用途。删除需要修改引用方import路径，收益不大。决定保留。

- [x] **决策：保留文件**
  - 理由：作为包的公共API桥接层，被其他模块引用
  - 验收标准: 文件保留，决策已记录
  - 优先级: P0
  - 预计耗时: 已完成

---

### 1.3 修复拼写错误

**文件**: `eval/runner/asset_verifier.py`

- [x] **修复 `pymupdf4llllm` 拼写错误**
  - 位置: `key_packages` 列表
  - 正确拼写: `pymupdf4llm`
  - 验收标准: 拼写已修正，功能验证通过
  - 优先级: P0
  - 预计耗时: 5分钟

---

### 1.4 修复违反项目规范的代码

#### 1.4.1 替换 `print()` 为 `logger`

**文件**: `eval/runner/core.py`

- [ ] **替换 `list_experiments()` 中的 `print()`**
  - 使用 `loguru` logger
  - 验收标准: 无 `print()` 调用，日志输出正常
  - 优先级: P0
  - 预计耗时: 10分钟

- [ ] **替换 `show_experiment_info()` 中的 `print()`**
  - 使用 `loguru` logger
  - 验收标准: 无 `print()` 调用，日志输出正常
  - 优先级: P0
  - 预计耗时: 10分钟


---

## Phase 2: 瘦身（P1 臃肿与重复）

### 2.1 拆分 God 文件与 God 函数

#### 2.1.1 拆分 `src/test_generation/generator.py` (1563行)

**文件**: `src/test_generation/generator.py`

- [ ] **分析 `TestSetGenerator` 职责边界**
  - 识别 10+ 种职责
  - 绘制职责矩阵
  - 验收标准: 完成职责分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `QuestionGenerator` 类**
  - 职责: 核心问题生成逻辑
  - 包含方法: `generate_hybrid_question`, `generate_document_based_questions`, `_post_process_question`
  - 验收标准: 新类创建完成，测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **提取 `TestSetOrchestrator` 类**
  - 职责: 编排逻辑
  - 包含方法: `generate_test_set`, `generate_golden_testset`, `supplement_document_based_questions`
  - 验收标准: 新类创建完成，测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **消除 `generate_hybrid_questions` 和 `generate_golden_testset` 重复代码**
  - 估计重复行数: 200+ 行
  - 提取公共方法
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 3小时

- [ ] **更新所有调用点**
  - 搜索 `TestSetGenerator` 的所有使用
  - 更新为新的类结构
  - 验收标准: 所有调用点已更新，测试通过
  - 优先级: P1
  - 预计耗时: 2小时

---

#### 2.1.2 拆分 `eval/runner/core.py` 的 `run_experiment()` (690行)

**文件**: `eval/runner/core.py`

- [ ] **分析 `run_experiment()` 职责**
  - 识别 8 种职责
  - 绘制流程图
  - 验收标准: 完成职责分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_load_and_validate_config()` 函数**
  - 职责: 加载配置、解析 resume/reuse 参数
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_create_experiment_directory()` 函数**
  - 职责: 创建实验目录（含 3 种分支）
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_initialize_profiler()` 函数**
  - 职责: 初始化 profiler
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **提取 `_prepare_evaluation_assets()` 函数**
  - 职责: 准备 meal/chunks/test set
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_run_variant_evaluation()` 函数**
  - 职责: 遍历 variant 执行评估
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **提取 `_generate_and_save_report()` 函数**
  - 职责: 生成报告
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_save_token_and_profiling_data()` 函数**
  - 职责: 保存 token 摘要和 profiling 数据
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **重构 `run_experiment()` 为编排函数**
  - 调用上述提取的子函数
  - 验收标准: 主函数 < 50 行，功能验证通过
  - 优先级: P1
  - 预计耗时: 2小时

---

#### 2.1.3 拆分 `src/app_pages/maintenance.py` (1160行)

**文件**: `src/app_pages/maintenance.py`

- [ ] **分析 `render_maintenance()` 职责**
  - 识别 15+ 个 session state 变量
  - 绘制渲染流程图
  - 验收标准: 完成职责分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_initialize_session_state()` 函数**
  - 职责: 初始化 15+ 个 session state 变量
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_render_sidebar()` 函数**
  - 职责: 侧边栏渲染
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_render_chat_messages()` 函数**
  - 职责: 聊天消息渲染
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_handle_interruption()` 函数**
  - 职责: 中断处理
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_scan_experiences()` 函数**
  - 职责: 经验扫描
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_download_report()` 函数**
  - 职责: 报告下载
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_render_agent_graph()` 函数**
  - 职责: Agent 架构图渲染
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **重构 `render_maintenance()` 为编排函数**
  - 调用上述提取的子函数
  - 验收标准: 主函数 < 100 行，功能验证通过
  - 优先级: P1
  - 预计耗时: 2小时

---

#### 2.1.4 拆分 `src/agent/tools.py` (1033行)

**文件**: `src/agent/tools.py`

- [ ] **分析重复模式**
  - 识别 20+ 个 `@tool` 函数的共同模式
  - 统计 `load_config()`、`json.dumps`、`try/except` 重复次数
  - 验收标准: 完成模式分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **创建 `tool_with_error_handling` 装饰器**
  - 封装 `try/except` 和 `logger.error` 模式
  - 验收标准: 装饰器创建完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **创建 `json_response` 辅助函数**
  - 封装 `json.dumps(result, ensure_ascii=False, indent=2)` 模式
  - 验收标准: 函数创建完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **创建 `get_config()` 辅助函数**
  - 封装 `from src.utils import load_config; config = load_config()` 模式
  - 验收标准: 函数创建完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **重构所有 tool 函数使用新辅助工具**
  - 应用装饰器和辅助函数
  - 验收标准: 所有 tool 函数已重构，代码行数减少 30%+
  - 优先级: P1
  - 预计耗时: 3小时

---

#### 2.1.5 拆分 `src/agent/cli.py` 的 `run_agent()` (330+行)

**文件**: `src/agent/cli.py`

- [ ] **分析 `run_agent()` 职责**
  - 识别 CLI 参数解析、数据库连接、会话管理、交互循环等职责
  - 验收标准: 完成职责分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_parse_cli_args()` 函数**
  - 职责: CLI 参数解析
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_initialize_database()` 函数**
  - 职责: 数据库连接初始化
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_manage_session()` 函数**
  - 职责: 会话管理
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_interactive_loop()` 函数**
  - 职责: 交互式输入循环
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_dispatch_cli_command()` 函数**
  - 职责: CLI 命令分发
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **重构 `run_agent()` 为编排函数**
  - 调用上述提取的子函数
  - 验收标准: 主函数 < 50 行，功能验证通过
  - 优先级: P1
  - 预计耗时: 2小时

---

#### 2.1.6 拆分 `eval/runner/metrics.py` 的 `compute_aggregate_metrics()` (226行)

**文件**: `eval/runner/metrics.py`

- [ ] **分析 `compute_aggregate_metrics()` 职责**
  - 识别 9 种聚合逻辑
  - 验收标准: 完成职责分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_document_metrics()` 函数**
  - 职责: 文档级检索指标
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_generation_metrics()` 函数**
  - 职责: 生成指标
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_chunk_metrics()` 函数**
  - 职责: chunk 级指标
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_dedup_metrics()` 函数**
  - 职责: dedup 指标
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_diversity_metrics()` 函数**
  - 职责: 多样性指标
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_hallucination_metrics()` 函数**
  - 职责: 幻觉率
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_question_type_metrics()` 函数**
  - 职责: 按问题类型分组
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_compute_llm_retrieval_metrics()` 函数**
  - 职责: LLM 检索指标
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **重构 `compute_aggregate_metrics()` 为编排函数**
  - 调用上述提取的子函数
  - 验收标准: 主函数 < 30 行，功能验证通过
  - 优先级: P1
  - 预计耗时: 2小时

---

#### 2.1.7 拆分 `eval/evaluators/builtin_evaluator.py` 的 `evaluate_single()` (200行)

**文件**: `eval/evaluators/builtin_evaluator.py`

- [ ] **分析 `evaluate_single()` if-chain 结构**
  - 识别所有 metric 判断分支
  - 验收标准: 完成分支分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **创建 metric 注册表**
  - 使用 `dict[str, Callable]` 存储指标计算函数
  - 验收标准: 注册表创建完成
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **将每个 metric 分支提取为独立函数**
  - 提取所有 metric 计算逻辑
  - 验收标准: 所有 metric 函数提取完成
  - 优先级: P1
  - 预计耗时: 3小时

- [ ] **重构 `evaluate_single()` 使用注册表**
  - 替换 if-chain 为字典查找
  - 验收标准: 函数 < 20 行，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

### 2.2 消除重复代码

#### 2.2.1 消除 token tracker 重建逻辑重复

**文件**: `eval/runner/core.py:829-852, 909-926`

- [x] **提取 `_rebuild_token_tracker()` 函数**
  - 封装从 `variant_result["token_usage"]["records"]` 反序列化逻辑
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [x] **替换两处重复代码为函数调用**
  - 更新第 829-852 行
  - 更新第 909-926 行
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 30分钟

---

#### 2.2.2 消除 serial/concurrent 采样逻辑重复

**文件**: `eval/runner/evaluation.py`

- [ ] **分析 `_collect_rag_samples_serial()` 和 `_query_single_question()` 重复**
  - 识别 ~120 行重复代码
  - 验收标准: 完成重复分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_build_sample()` 函数**
  - 封装 sample 构建逻辑
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **重构两个函数使用 `_build_sample()`**
  - 更新 `_collect_rag_samples_serial()`
  - 更新 `_query_single_question()`
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 2.2.3 消除 RAGAS evaluator ref/no-ref 分支重复

**文件**: `eval/evaluators/ragas_evaluator.py:551-599, 601-649`

- [ ] **分析两个分支的重复逻辑**
  - 识别 RAGAS evaluate + 结果解析逻辑
  - 验收标准: 完成重复分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_run_ragas_evaluation()` 函数**
  - 封装 RAGAS evaluate 调用和结果解析
  - 参数: `samples`, `has_ref`
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **重构两个分支使用新函数**
  - 更新 `samples_with_ref` 分支
  - 更新 `samples_without_ref` 分支
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 2.2.4 消除 LLM 调用 + JSON 解析重复模式

**文件**: `eval/metrics/llm_retrieval.py`, `eval/metrics/generation.py`

- [ ] **分析 4+ 处重复模式**
  - 识别: 创建 client → 构建 prompt → call_with_retry → 正则提取 JSON → 判断 verdict
  - 验收标准: 完成重复分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_llm_judge()` 辅助函数**
  - 参数: `prompt`, `client`, `json_pattern`
  - 返回: `dict` (解析后的 JSON)
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **重构所有调用点使用 `_llm_judge()`**
  - 更新 `llm_retrieval.py`
  - 更新 `generation.py`
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 2小时

---

#### 2.2.5 消除 chunk 匹配逻辑重复

**文件**: `eval/metrics/chunk.py`

- [ ] **分析三个函数的匹配逻辑重复**
  - `calculate_chunk_hit_rate()`
  - `calculate_chunk_mrr()`
  - `calculate_chunk_ndcg()`
  - 验收标准: 完成重复分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_match_chunks()` 函数**
  - 封装 exact match + adjacent tolerance 逻辑
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **重构三个函数使用 `_match_chunks()`**
  - 更新 `calculate_chunk_hit_rate()`
  - 更新 `calculate_chunk_mrr()`
  - 更新 `calculate_chunk_ndcg()`
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 2.2.6 消除推荐逻辑重复

**文件**: `eval/reporter/template_single.py`, `eval/reporter/template_variant.py`

- [ ] **分析两个文件的推荐逻辑重复**
  - 阈值判断 + 建议文本
  - 验收标准: 完成重复分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_generate_recommendation()` 函数**
  - 封装阈值判断和建议生成逻辑
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **重构两个文件使用新函数**
  - 更新 `template_single.py`
  - 更新 `template_variant.py`
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 2.2.7 消除 `_resolve_db_path` 函数重复

**文件**: `src/agent/checkpoint.py:15-28`, `src/agent/session_manager.py:11-24`

- [ ] **创建 `src/agent/db_utils.py` 模块**
  - 新建文件
  - 验收标准: 文件创建完成
  - 优先级: P2
  - 预计耗时: 10分钟

- [ ] **移动 `_resolve_db_path` 到 `db_utils.py`**
  - 提取函数到新模块
  - 导出函数
  - 验收标准: 函数移动完成
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **更新 `checkpoint.py` 导入**
  - 从 `db_utils` 导入 `_resolve_db_path`
  - 删除本地实现
  - 验收标准: 导入正确，测试通过
  - 优先级: P2
  - 预计耗时: 15分钟

- [ ] **更新 `session_manager.py` 导入**
  - 从 `db_utils` 导入 `_resolve_db_path`
  - 删除本地实现
  - 验收标准: 导入正确，测试通过
  - 优先级: P2
  - 预计耗时: 15分钟

---

#### 2.2.8 消除 Reporter save 方法重复

**文件**: `src/agent/reporters/comparison_report.py:142-178`, `src/agent/reporters/maintenance_report.py:120-157`

- [ ] **创建 `BaseReporter` 基类**
  - 提取公共 `save()` 方法
  - 验收标准: 基类创建完成
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **重构 `ComparisonReporter` 继承 `BaseReporter`**
  - 删除重复的 `save()` 方法
  - 验收标准: 继承正确，测试通过
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **重构 `MaintenanceReporter` 继承 `BaseReporter`**
  - 删除重复的 `save()` 方法
  - 验收标准: 继承正确，测试通过
  - 优先级: P2
  - 预计耗时: 30分钟

---

#### 2.2.9 消除 Agent state 字典构造重复

**文件**: `src/agent/cli.py` (3处), `src/app_pages/maintenance.py` (3处)

- [ ] **创建 `build_agent_state()` 辅助函数**
  - 封装 12+ 个字段的 state 字典构造
  - 验收标准: 函数创建完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **重构 `cli.py` 中的 3 处调用**
  - 替换手动构造为函数调用
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **重构 `maintenance.py` 中的 3 处调用**
  - 替换手动构造为函数调用
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 30分钟

---

#### 2.2.10 消除流式处理逻辑重复

**文件**: `src/app_pages/maintenance.py`

- [ ] **分析 `_render_streaming_agent` 和 `_resume_interrupt_streaming` 重复**
  - 识别事件处理代码重复
  - 验收标准: 完成重复分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [ ] **提取 `_handle_streaming_event()` 函数**
  - 封装事件处理逻辑
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [ ] **重构两个函数使用 `_handle_streaming_event()`**
  - 更新 `_render_streaming_agent`
  - 更新 `_resume_interrupt_streaming`
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

## Phase 3: 治本（P2-P3 架构问题）

### 3.1 修复 Pydantic 模型问题

#### 3.1.1 重构 `ExperimentConfigSchema`

**文件**: `src/experiment_schemas.py`

- [ ] **为所有字段定义具体类型**
  - `name: str`
  - `description: str`
  - `data: dict[str, Any]`
  - `test_sets: list[str]`
  - `variants: list[dict[str, Any]]`
  - `evaluation: dict[str, Any]`
  - `force_overwrite: list[str] = []`
  - 验收标准: 所有字段有具体类型
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **移除手动验证方法**
  - 删除 `_validate_*` 方法
  - 使用 Pydantic 的 `Field` 约束和 `model_validator`
  - 验收标准: 验证逻辑由 Pydantic 自动处理
  - 优先级: P2
  - 预计耗时: 3小时

- [ ] **测试新的 schema 验证**
  - 创建测试用例验证类型检查
  - 验收标准: 所有测试通过
  - 优先级: P2
  - 预计耗时: 1小时

---

#### 3.1.2 修复 `extra = "allow"` 泛滥

**文件**: `src/config_schema.py`

- [ ] **分析所有 Pydantic 模型**
  - 列出所有使用 `extra = "allow"` 的模型
  - 验收标准: 完成模型清单
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **根模型保留 `extra = "allow"`**
  - `AppConfig` 保持 `extra = "allow"`
  - 验收标准: 根模型配置正确
  - 优先级: P2
  - 预计耗时: 15分钟

- [ ] **子模型改为 `extra = "forbid"`**
  - `RetrievalConfig`、`ChunkerConfig` 等所有子模型
  - 验收标准: 所有子模型使用 `extra = "forbid"`
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **测试配置拼写错误捕获**
  - 创建测试用例验证拼写错误被捕获
  - 验收标准: 拼写错误会抛出验证错误
  - 优先级: P2
  - 预计耗时: 1小时

---

#### 3.1.3 重构 `LLMEvaluatorConfig`

**文件**: `src/config_schema.py`

- [ ] **改为 `dict[str, LLMEvaluatorSubConfig]` 结构**
  - 替换 8 个独立字段为字典
  - 验收标准: 字段定义更新完成
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **更新所有访问点**
  - 搜索 `extract_statements`、`verify_statements` 等字段访问
  - 更新为字典访问方式
  - 验收标准: 所有访问点已更新，测试通过
  - 优先级: P2
  - 预计耗时: 2小时

---

#### 3.1.4 为裸 `dict` 字段定义 Pydantic 模型

**文件**: `src/config_schema.py`

- [ ] **定义 `RunConfigConfig` 模型**
  - 字段: `max_workers: int`, `timeout: int`, `max_retries: int`
  - 验收标准: 模型定义完成
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **更新 `EvaluationRagasConfig.run_config` 类型**
  - 从 `dict` 改为 `RunConfigConfig`
  - 验收标准: 类型更新完成，测试通过
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **定义 `ValidationConfig` 模型**
  - 字段: `check_proper_nouns: bool`
  - 验收标准: 模型定义完成
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **更新 `TestGenerationConfig.validation` 类型**
  - 从 `dict` 改为 `ValidationConfig`
  - 验收标准: 类型更新完成，测试通过
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **定义 `CheckpointConfig` 模型**
  - 字段: `db_path: str`
  - 验收标准: 模型定义完成
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **更新 `AgentConfig.checkpoint` 类型**
  - 从 `dict` 改为 `CheckpointConfig`
  - 验收标准: 类型更新完成，测试通过
  - 优先级: P2
  - 预计耗时: 30分钟

---

### 3.2 移除过度设计

#### 3.2.1 删除 `ExperimentReporter` 无用委托方法

**文件**: `eval/reporter/__init__.py:118-173`

- [ ] **分析 6 个 static 方法的调用点**
  - 搜索每个方法的调用
  - 验收标准: 完成调用点清单
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **更新调用点直接使用 `formatters.py` 函数**
  - 替换委托调用为直接调用
  - 验收标准: 所有调用点已更新
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **删除 6 个 static 方法**
  - 删除第 118-173 行
  - 验收标准: 方法已删除，测试通过
  - 优先级: P2
  - 预计耗时: 15分钟

---

#### 3.2.2 删除 `eval/metrics/utils.py` 不必要的间接层

**文件**: `eval/metrics/utils.py`

- [ ] **分析 `create_llm_client()` 的调用点**
  - 搜索所有调用
  - 验收标准: 完成调用点清单
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **更新调用点直接使用 `src.utils.create_llm_client`**
  - 替换间接调用为直接调用
  - 验收标准: 所有调用点已更新
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **删除 `create_llm_client()` 包装函数**
  - 删除薄包装
  - 验收标准: 函数已删除，测试通过
  - 优先级: P2
  - 预计耗时: 15分钟

---

#### 3.2.3 删除 `eval/experiment_reporter.py` 纯转发模块

**文件**: `eval/experiment_reporter.py`

- [ ] **分析重新导出的符号**
  - 列出所有导出的符号
  - 验收标准: 完成符号清单
  - 优先级: P2
  - 预计耗时: 15分钟

- [ ] **搜索所有导入点**
  - 搜索 `from eval.experiment_reporter import`
  - 验收标准: 完成导入点清单
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **更新导入点直接使用 `eval.reporter`**
  - 替换导入路径
  - 验收标准: 所有导入点已更新
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **删除 `experiment_reporter.py` 文件**
  - 移入 `.trashbin/`
  - 验收标准: 文件已删除，测试通过
  - 优先级: P2
  - 预计耗时: 15分钟

---

#### 3.2.4 移除 `src/issue/migrate.py` 到 scripts/

**文件**: `src/issue/migrate.py`

- [ ] **确认迁移已完成**
  - 检查是否还有未迁移的 backlog
  - 验收标准: 确认迁移完成
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **移动文件到 `scripts/` 目录**
  - 从 `src/issue/` 移动到 `scripts/`
  - 验收标准: 文件已移动
  - 优先级: P2
  - 预计耗时: 15分钟

- [ ] **更新导入路径（如有）**
  - 搜索并更新所有导入
  - 验收标准: 无导入错误
  - 优先级: P2
  - 预计耗时: 30分钟

---

### 3.3 统一 dataclass/Pydantic 使用策略

**文件**: `src/experiment.py`, `src/experiment_reuse.py`, `src/config_schema.py`

- [ ] **制定统一策略**
  - 决定何时使用 dataclass，何时使用 Pydantic
  - 文档化决策
  - 验收标准: 策略文档完成
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **重构 `ExperimentConfig` 为 Pydantic 模型**
  - 从 dataclass 转换为 BaseModel
  - 验收标准: 转换完成，测试通过
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **重构 `ResumeConfig` 为 Pydantic 模型**
  - 从 dataclass 转换为 BaseModel
  - 验收标准: 转换完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **重构 `ReportReuseConfig` 为 Pydantic 模型**
  - 从 dataclass 转换为 BaseModel
  - 验收标准: 转换完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **删除手写序列化方法**
  - 删除 `to_dict()` 和 `from_dict()` 方法
  - 使用 `model_dump()` 和 `model_validate()`
  - 验收标准: 序列化逻辑由 Pydantic 处理
  - 优先级: P2
  - 预计耗时: 2小时

---

### 3.4 修复其他架构问题

#### 3.4.1 修复 `ExperimentFingerprint` 字段不一致

**文件**: `src/experiment_reuse.py`

- [ ] **统一 `matches()`、`diff()`、`compute_hash()` 字段集合**
  - 决定使用哪些字段
  - 更新所有方法使用相同字段
  - 验收标准: 三个方法使用一致的字段集合
  - 优先级: P2
  - 预计耗时: 2小时

---

#### 3.4.2 提取 `ExperimentManager._update_manifest()` 辅助方法

**文件**: `src/experiment.py`

- [x] **分析 5 个重复的 manifest 读写模式**
  - `update_manifest_status()`
  - `mark_variant_completed()`
  - `update_manifest_field()`
  - `mark_resumed()`
  - `invalidate_variant()`
  - 验收标准: 完成重复分析文档
  - 优先级: P1
  - 预计耗时: 1小时

- [x] **提取 `_update_manifest()` 辅助方法**
  - 参数: `exp_dir`, `updater_fn`
  - 封装读写模式和错误处理
  - 验收标准: 方法提取完成，单元测试通过
  - 优先级: P1
  - 预计耗时: 2小时

- [x] **重构 5 个方法使用 `_update_manifest()`**
  - 更新所有方法
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P1
  - 预计耗时: 2小时

---

#### 3.4.3 拆分 `src/pipeline.py` 的 `build_index()` 方法

**文件**: `src/pipeline.py:225-466`

- [ ] **分析 `build_index()` 职责**
  - 识别 meal 文件扫描、hash 计算、缓存路径解析、PDF 解析、分块、索引构建、BM25 索引构建等职责
  - 验收标准: 完成职责分析文档
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **提取 `_scan_meal_files()` 函数**
  - 职责: meal 文件扫描
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **提取 `_compute_file_hash()` 函数**
  - 职责: hash 计算
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **提取 `_resolve_cache_path()` 函数**
  - 职责: 缓存路径解析
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **提取 `_parse_pdf()` 函数**
  - 职责: PDF 解析
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **提取 `_build_vector_index()` 函数**
  - 职责: 向量索引构建
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **提取 `_build_bm25_index()` 函数**
  - 职责: BM25 索引构建
  - 验收标准: 函数提取完成，测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **重构 `build_index()` 为编排函数**
  - 调用上述提取的子函数
  - 验收标准: 主函数 < 50 行，功能验证通过
  - 优先级: P2
  - 预计耗时: 2小时

---

#### 3.4.4 消除 `use_meal()` 中重复的配置读取

**文件**: `src/pipeline.py:615-626, 189-199`

- [ ] **提取 `_get_hybrid_retriever_config()` 函数**
  - 封装逐层 `.get()` 取值逻辑
  - 验收标准: 函数提取完成，单元测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **重构两处使用新函数**
  - 更新 `use_meal()` (615-626行)
  - 更新 `_setup_retrievers()` (189-199行)
  - 验收标准: 无重复代码，功能验证通过
  - 优先级: P2
  - 预计耗时: 30分钟

---

## Phase 4: 测试质量（P5 测试问题）

### 4.1 删除假测试和框架测试

#### 4.1.1 删除假测试

**文件**: `tests/test_run_experiment.py:1130-1132`

- [ ] **删除 `test_dual_backend_results_have_namespace_prefix()`**
  - 已在 Phase 1 完成
  - 验收标准: 函数已删除
  - 优先级: P0
  - 预计耗时: 已完成

---

#### 4.1.2 删除框架测试

**文件**: `tests/test_agent.py`, `tests/test_experiment.py`, `tests/test_meal.py`, `tests/test_run_experiment.py`, `tests/test_evaluators.py`

- [ ] **删除 `TestLLMClientCaching` 测试类**
  - 文件: `test_agent.py`
  - 原因: 测试 `functools.lru_cache` 的缓存行为
  - 验收标准: 测试类已删除
  - 优先级: P1
  - 预计耗时: 15分钟

- [ ] **删除 `TestMaintenanceStateNewFields` 测试类**
  - 文件: `test_agent.py`
  - 原因: 测试 TypedDict 能否存储新字段
  - 验收标准: 测试类已删除
  - 优先级: P1
  - 预计耗时: 15分钟

- [ ] **删除 `test_to_dict` 测试（experiment.py）**
  - 文件: `test_experiment.py`
  - 原因: 测试 dict 的赋值行为
  - 验收标准: 测试已删除
  - 优先级: P1
  - 预计耗时: 15分钟

- [ ] **删除 `test_to_dict` 测试（meal.py）**
  - 文件: `test_meal.py`
  - 原因: 测试 dataclass 的序列化行为
  - 验收标准: 测试已删除
  - 优先级: P1
  - 预计耗时: 15分钟

- [ ] **删除 `test_result_merging_builtin_and_ragas` 测试**
  - 文件: `test_run_experiment.py`
  - 原因: 测试 `dict.update()` 的行为
  - 验收标准: 测试已删除
  - 优先级: P1
  - 预计耗时: 15分钟

- [ ] **删除 `TestEvaluationResult` 测试类**
  - 文件: `test_evaluators.py`
  - 原因: 测试 dataclass 的创建和 `to_dict`
  - 验收标准: 测试类已删除
  - 优先级: P1
  - 预计耗时: 15分钟

- [ ] **删除 `TestMaintenanceState` 测试类**
  - 文件: `test_agent.py`
  - 原因: 测试 Python TypedDict 的赋值和取值行为
  - 验收标准: 测试类已删除
  - 优先级: P1
  - 预计耗时: 15分钟

---

### 4.2 重构测试使用 parametrize

#### 4.2.1 重构 `TestNormalizeSource` (16→1)

**文件**: `tests/test_metrics.py`

- [ ] **分析 16 个测试的模式**
  - 识别输入路径 → 断言归一化结果的模式
  - 验收标准: 完成模式分析文档
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **创建参数化测试**
  - 使用 `@pytest.mark.parametrize`
  - 合并 16 个测试为 1 个
  - 验收标准: 测试数量减少，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 4.2.2 重构 `TestToolFunctions` + `TestNewTools` (15→1)

**文件**: `tests/test_agent.py`

- [ ] **分析 15 个测试的模式**
  - 识别 `.name` 断言模式
  - 验收标准: 完成模式分析文档
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **创建参数化测试**
  - 使用 `@pytest.mark.parametrize`
  - 合并 15 个测试为 1 个
  - 验收标准: 测试数量减少，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 4.2.3 重构 `TestBuildSystemPrompt` (6→1)

**文件**: `tests/test_agent.py`

- [ ] **分析 6 个测试的模式**
  - 识别字符串包含测试模式
  - 验收标准: 完成模式分析文档
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **创建参数化测试**
  - 使用 `@pytest.mark.parametrize`
  - 合并 6 个测试为 1 个
  - 验收标准: 测试数量减少，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 4.2.4 重构 `TestCLICommands` (8→1)

**文件**: `tests/test_agent.py`

- [ ] **分析 8 个测试的模式**
  - 识别命令存在性测试模式
  - 验收标准: 完成模式分析文档
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **创建参数化测试**
  - 使用 `@pytest.mark.parametrize`
  - 合并 8 个测试为 1 个
  - 验收标准: 测试数量减少，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 4.2.5 重构 `TestChunkTextChineseRoundtrip` (7→1)

**文件**: `tests/test_chunker.py`

- [ ] **分析 7 个测试的模式**
  - 识别 roundtrip 测试模式
  - 验收标准: 完成模式分析文档
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **创建参数化测试**
  - 使用 `@pytest.mark.parametrize`
  - 合并 7 个测试为 1 个
  - 验收标准: 测试数量减少，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

#### 4.2.6 重构 `TestRagasEvaluatorConfigReading` (4→1)

**文件**: `tests/test_evaluators.py`

- [ ] **分析 4 个测试的模式**
  - 识别配置读取测试模式
  - 验收标准: 完成模式分析文档
  - 优先级: P1
  - 预计耗时: 30分钟

- [ ] **创建参数化测试**
  - 使用 `@pytest.mark.parametrize`
  - 合并 4 个测试为 1 个
  - 验收标准: 测试数量减少，功能验证通过
  - 优先级: P1
  - 预计耗时: 1小时

---

### 4.3 改进测试质量

#### 4.3.1 为工具函数添加行为测试

**文件**: `tests/test_agent.py`

- [ ] **分析 7 个工具函数的预期行为**
  - `list_meals`
  - `get_meal_details`
  - `get_chunk_details`
  - `save_experience`
  - `search_experiences`
  - `get_current_time`
  - `get_current_date`
  - 验收标准: 完成行为分析文档
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **为每个工具函数创建行为测试**
  - 测试正常输入输出
  - 测试错误处理
  - 验收标准: 每个工具函数有至少 2 个测试用例
  - 优先级: P2
  - 预计耗时: 4小时

---

#### 4.3.2 减少 `test_pipeline.py` 的 mock 层数

**文件**: `tests/test_pipeline.py`

- [ ] **分析当前 mock 策略**
  - 识别 6 个 `@patch` 装饰器的必要性
  - 验收标准: 完成 mock 分析文档
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **重构测试使用真实组件**
  - 使用真实的 `Embedder`、`Retriever` 等
  - 只 mock 外部依赖（LLM API、文件系统）
  - 验收标准: mock 层数减少到 2-3 个
  - 优先级: P2
  - 预计耗时: 4小时

- [ ] **删除构造函数参数断言**
  - 移除 `mock_embedder.assert_called_once_with(...)` 等
  - 改为断言行为结果
  - 验收标准: 无构造函数参数断言
  - 优先级: P2
  - 预计耗时: 2小时

---

#### 4.3.3 补充关键缺失测试

##### Pipeline 错误处理测试

**文件**: `tests/test_pipeline.py`

- [ ] **添加 retriever 失败错误处理测试**
  - 测试 retriever 抛出异常时的行为
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **添加 generator 超时错误处理测试**
  - 测试 generator 超时时的行为
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **添加 `build_index` 文件系统操作测试**
  - 测试文件不存在、权限错误等场景
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **添加并发 query 线程安全测试**
  - 测试多线程调用 query 的安全性
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 3小时

---

##### Generator 错误处理测试

**文件**: `tests/test_generator.py`

- [ ] **添加 LLM 调用失败测试**
  - 测试 LLM API 返回错误时的行为
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **添加 LLM 调用超时测试**
  - 测试 LLM 调用超时时的行为
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **添加重试机制测试**
  - 测试重试逻辑是否正确
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **添加生成问题质量校验测试**
  - 测试生成的问题是否符合预期格式
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 2小时

---

##### Experiment Manager 测试

**文件**: `tests/test_experiment.py`

- [ ] **添加 `ExperimentManager` 核心流程测试**
  - 测试创建实验
  - 测试运行实验
  - 测试列出实验
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 3小时

- [ ] **添加 `deep_merge` 边界情况测试**
  - 测试空字典、嵌套字典、冲突键等
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

---

##### Test Set Manager 测试

**文件**: `tests/test_test_set_manager.py`

- [ ] **添加 test set 合并冲突测试**
  - 测试合并时的冲突处理
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **添加失效策略测试**
  - 测试 test set 失效时的行为
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **添加审计日志测试**
  - 测试审计日志是否正确记录
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 1小时

---

##### Metrics 测试

**文件**: `tests/test_metrics.py`

- [ ] **添加 `calculate_faithfulness` 测试**
  - 测试正常输入
  - 测试边界情况
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **添加 `calculate_answer_relevancy` 测试**
  - 测试正常输入
  - 测试边界情况
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **添加 `calculate_hallucination_rate` 测试**
  - 测试正常输入
  - 测试边界情况
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 2小时

---

##### Agent 端到端测试

**文件**: `tests/test_agent_e2e.py` (新建)

- [ ] **创建端到端测试文件**
  - 新建 `tests/test_agent_e2e.py`
  - 验收标准: 文件创建完成
  - 优先级: P2
  - 预计耗时: 10分钟

- [ ] **添加完整对话流程测试**
  - 测试从用户输入到最终响应的完整流程
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 4小时

- [ ] **添加工具调用结果正确性测试**
  - 测试每个工具的调用和返回
  - 验收标准: 测试通过
  - 优先级: P2
  - 预计耗时: 3小时

---

## Phase 5: 清理（P4-P6 其他问题）

### 5.1 删除遗留代码

#### 5.1.1 删除 `_save_experience_legacy` 方法

**文件**: `src/agent/memory/experience_store.py`

- [ ] **确认迁移已完成**
  - 检查是否还有使用 legacy 格式的数据
  - 验收标准: 确认迁移完成
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **删除 `_save_experience_legacy` 方法**
  - 删除遗留方法
  - 验收标准: 方法已删除，测试通过
  - 优先级: P2
  - 预计耗时: 15分钟

---

#### 5.1.2 标记 `prepare_legacy_test_set()` 为待移除

**文件**: `eval/runner/preparation.py`

- [ ] **添加 `DeprecationWarning`**
  - 在函数开头添加警告
  - 验收标准: 警告已添加
  - 优先级: P2
  - 预计耗时: 15分钟

- [ ] **添加 TODO 注释**
  - 标记计划移除的版本
  - 验收标准: 注释已添加
  - 优先级: P2
  - 预计耗时: 10分钟

---

#### 5.1.3 删除 `del pipeline` + `gc.collect()` 反模式

**文件**: `eval/runner/core.py`

- [ ] **删除 `del pipeline` 语句**
  - 移除手动删除
  - 验收标准: 语句已删除
  - 优先级: P2
  - 预计耗时: 5分钟

- [ ] **删除 `gc.collect()` 调用**
  - 移除手动 GC
  - 验收标准: 调用已删除
  - 优先级: P2
  - 预计耗时: 5分钟

---

### 5.2 修复代码异味

#### 5.2.1 修复 `asset_verifier.py` 使用已废弃的 `pkg_resources`

**文件**: `eval/runner/asset_verifier.py`

- [ ] **替换 `pkg_resources` 为 `importlib.metadata`**
  - 更新导入
  - 更新 API 调用
  - 验收标准: 无 `pkg_resources` 导入，功能验证通过
  - 优先级: P2
  - 预计耗时: 1小时

---

#### 5.2.2 修复函数属性作为全局状态

**文件**: `src/agent/tools.py`

- [ ] **分析 `save_experience_tool._store` 使用场景**
  - 识别为什么需要全局状态
  - 验收标准: 完成使用场景分析
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **重构为闭包或类**
  - 使用闭包或类封装状态
  - 验收标准: 无函数属性作为全局状态
  - 优先级: P2
  - 预计耗时: 2小时

---

#### 5.2.3 统一 JSON 提取正则

**文件**: `eval/metrics/generation.py`

- [ ] **分析不同正则的差异**
  - `r"\{[^{}]*\}"` vs `r"\{[\s\S]*\}"`
  - 验收标准: 完成正则差异分析
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **选择统一的正则表达式**
  - 决定使用哪个正则
  - 更新所有使用点
  - 验收标准: 所有 JSON 提取使用相同正则
  - 优先级: P2
  - 预计耗时: 1小时

---

#### 5.2.4 修复 "best variant" 选择逻辑

**文件**: `eval/runner/comparison.py`

- [ ] **分析当前选择逻辑**
  - 仅基于 `hit_rate`
  - 验收标准: 完成选择逻辑分析
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **设计多指标选择策略**
  - 考虑多个指标
  - 文档化决策
  - 验收标准: 策略设计完成
  - 优先级: P2
  - 预计耗时: 1小时

- [ ] **实现新的选择逻辑**
  - 更新 `_find_best_variant()`
  - 验收标准: 新逻辑实现完成，测试通过
  - 优先级: P2
  - 预计耗时: 2小时

- [ ] **删除 `comparison.py` 中的重复逻辑**
  - 使用 `template_variant.py` 中的 `_find_best_variant()`
  - 验收标准: 无重复逻辑
  - 优先级: P2
  - 预计耗时: 30分钟

---

#### 5.2.5 修复 `pipeline_profiler.py` 编号逻辑 bug

**文件**: `eval/pipeline_profiler.py`

- [ ] **分析编号逻辑 bug**
  - `suggestions` 列表条目已以 `"1. "` 开头
  - 后续又用 `enumerate(suggestions, 1)` 重新编号
  - 验收标准: 完成 bug 分析
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **修复编号逻辑**
  - 移除重复编号或调整逻辑
  - 验收标准: 编号正确，无重复前缀
  - 优先级: P2
  - 预计耗时: 1小时

---

#### 5.2.6 处理 `eval/visualize.py` 可能的死代码

**文件**: `eval/visualize.py`

- [ ] **搜索 `aggregated_metrics` 字段**
  - 确认是否有代码生成此字段
  - 验收标准: 确认字段存在性
  - 优先级: P2
  - 预计耗时: 30分钟

- [ ] **删除或更新 `extract_metrics()` 函数**
  - 如无使用，移入 `.trashbin/`
  - 如有使用，更新为正确字段
  - 验收标准: 函数已处理
  - 优先级: P2
  - 预计耗时: 1小时

---

## 统计摘要

### 按优先级统计

| 优先级 | 任务数 | 预计总耗时 |
|--------|--------|-----------|
| P0 | 15 | ~2小时 |
| P1 | 87 | ~120小时 |
| P2 | 78 | ~100小时 |
| **总计** | **180** | **~222小时** |

### 按类别统计

| 类别 | 任务数 | 预计总耗时 |
|------|--------|-----------|
| 止血（P0） | 15 | ~2小时 |
| 瘦身（P1） | 87 | ~120小时 |
| 治本（P2-P3） | 78 | ~100小时 |
| 测试质量（P5） | 0 | 0小时 |
| 清理（P4-P6） | 0 | 0小时 |

### 按文件统计（Top 10）

| 文件 | 任务数 | 预计总耗时 |
|------|--------|-----------|
| `src/test_generation/generator.py` | 5 | ~12小时 |
| `eval/runner/core.py` | 12 | ~15小时 |
| `src/app_pages/maintenance.py` | 9 | ~11小时 |
| `src/agent/tools.py` | 5 | ~10小时 |
| `src/agent/cli.py` | 7 | ~9小时 |
| `eval/runner/metrics.py` | 10 | ~11小时 |
| `eval/evaluators/builtin_evaluator.py` | 4 | ~8小时 |
| `src/experiment_schemas.py` | 3 | ~6小时 |
| `src/config_schema.py` | 9 | ~6小时 |
| `tests/test_pipeline.py` | 3 | ~7小时 |

---

## 进度跟踪

### Phase 1: 止血（P0 严重问题）

- [ ] 开始日期: ___
- [ ] 完成日期: ___
- [ ] 完成任务: 0/15
- [ ] 完成百分比: 0%

### Phase 2: 瘦身（P1 臃肿与重复）

- [ ] 开始日期: ___
- [ ] 完成日期: ___
- [ ] 完成任务: 0/87
- [ ] 完成百分比: 0%

### Phase 3: 治本（P2-P3 架构问题）

- [ ] 开始日期: ___
- [ ] 完成日期: ___
- [ ] 完成任务: 0/78
- [ ] 完成百分比: 0%

### Phase 4: 测试质量（P5 测试问题）

- [ ] 开始日期: ___
- [ ] 完成日期: ___
- [ ] 完成任务: 0/0
- [ ] 完成百分比: 0%

### Phase 5: 清理（P4-P6 其他问题）

- [ ] 开始日期: ___
- [ ] 完成日期: ___
- [ ] 完成任务: 0/0
- [ ] 完成百分比: 0%

---

## 验收标准

### 每个 Phase 的验收标准

1. **Phase 1**: 所有 P0 问题已修复，代码库无假测试、死代码、拼写错误、规范违反
2. **Phase 2**: 所有 God 文件/God 函数已拆分，重复代码已消除，代码行数减少 15-20%
3. **Phase 3**: Pydantic 模型正确使用，架构问题已修复，dataclass/Pydantic 使用统一
4. **Phase 4**: 测试质量显著提升，无假测试和框架测试，关键缺失测试已补充
5. **Phase 5**: 所有遗留代码已清理，代码异味已修复

### 最终验收标准

- [ ] 所有测试通过 (`pixi run test-all`)
- [ ] Lint 检查通过 (`pixi run lint`)
- [ ] 代码覆盖率提升 10%+
- [ ] 无 P0-P2 级别的问题
- [ ] 文档已更新

---

## 风险与依赖

### 风险

1. **重构影响范围大**: God 文件拆分可能影响大量调用点，需要充分测试
2. **Pydantic 重构**: 可能破坏现有配置文件兼容性
3. **测试重构**: 删除假测试可能暴露隐藏的 bug

### 依赖

1. **测试环境**: 需要完整的测试环境验证重构
2. **时间投入**: 预计需要 222 小时（约 28 个工作日）
3. **团队协作**: 需要团队成员理解重构意图并配合

---

## 备注

- 本进度报告基于审计报告 `code-quality-audit-report-260509.md` 创建
- 所有任务假设问题确实存在，未进行代码验证
- 预计耗时为估算值，实际耗时可能因具体情况而异
- 建议按 Phase 顺序执行，每个 Phase 完成后进行验收
