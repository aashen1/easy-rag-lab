# 独立 Issue 批量处理 Spec

## Why

backlog 中有多个独立 issue 待处理，涵盖调查分析、代码风格重构和功能补全。这些 issue 之间无依赖关系，可并行推进，批量处理可提高效率。

## What Changes

### INV-019：测试并行化可行性评估
- 评估 pytest-xdist 在当前测试体系中的可行性
- 产出分析报告，包含：当前测试瓶颈、并行化收益预估、潜在风险、推荐方案

### INV-021：文件路径安全检查
- 审计所有从配置/用户输入构造文件路径的代码路径
- 产出分析报告，包含：当前风险点清单、已有保护措施、缺失保护、推荐修复方案

### RF-017：自定义异常类型定义
- 在 `src/exceptions.py` 中定义业务异常层次结构
- 替换现有 `raise ValueError` / `raise Exception` 为对应自定义异常
- **纯代码风格变更，无逻辑变更**：所有异常的触发条件、错误消息、捕获行为保持不变

### RF-002：项目结构整理
- 评估根目录 `.py` 文件（`main.py`、`interactive.py`）迁移影响范围
- 产出评估报告，包含：迁移方案、影响范围、风险点、是否建议执行

### FEAT-011：补做 LLM 报告功能
- 新增 CLI 命令 `--llm-report-only <exp_dir>`，支持对已完成实验追溯生成 LLM 报告
- 复用现有 `ExperimentReporter` 的 LLM 报告生成能力

## Impact

- Affected specs: 无其他 spec 受影响
- Affected code:
  - INV-019/INV-021：仅产出分析报告文档，不修改代码
  - RF-017：`src/` 和 `eval/` 中约 117 处 `raise` 语句，新增 `src/exceptions.py`
  - RF-002：仅产出评估报告，不修改代码（本次不执行迁移）
  - FEAT-011：修改 `main.py`（新增 CLI 参数）和 `eval/run_experiment.py`（新增独立报告生成函数）

## ADDED Requirements

### Requirement: INV-019 测试并行化可行性评估

系统 SHALL 产出一份分析报告，评估 pytest-xdist 在当前测试体系中的可行性。

#### Scenario: 评估完成
- **WHEN** 分析当前测试体系（1077 个测试函数、29 个测试文件、3 个 marker）
- **THEN** 报告包含以下内容：
  1. 当前测试执行时间基线（unit vs integration 分类）
  2. 并行化兼容性分析（fixture 隔离性、共享状态、文件系统竞争）
  3. pytest-xdist 配置建议（worker 数量、分发策略）
  4. 风险点清单（如 integration 测试共享 Qdrant 实例）
  5. 推荐方案（是否建议启用、分阶段启用策略）

### Requirement: INV-021 文件路径安全检查

系统 SHALL 产出一份分析报告，审计文件路径处理的安全性。

#### Scenario: 审计完成
- **WHEN** 审计所有从配置/用户输入构造文件路径的代码路径
- **THEN** 报告包含以下内容：
  1. 所有路径构造入口清单（配置驱动 vs 用户输入 vs 硬编码）
  2. 已有保护措施（如 `meal.py` 的 `relative_to()` 检查）
  3. 缺失保护清单（配置路径无校验、CLI 参数无规范化、无 `.resolve()` 调用）
  4. 风险等级评估（高/中/低）
  5. 推荐修复方案（统一路径验证函数、白名单校验等）

### Requirement: RF-017 自定义异常类型定义

系统 SHALL 提供业务异常层次结构，替换现有通用异常。

#### Scenario: 异常层次结构定义
- **WHEN** 创建 `src/exceptions.py`
- **THEN** 包含以下异常类：
  1. `RAGPipelineError` — 所有业务异常的基类，继承 `Exception`
  2. `ConfigurationError(RAGPipelineError)` — 配置校验失败
  3. `ParsingError(RAGPipelineError)` — PDF/文档解析失败
  4. `RetrievalError(RAGPipelineError)` — 检索执行失败
  5. `IndexingError(RAGPipelineError)` — 索引构建/查询失败
  6. `GenerationError(RAGPipelineError)` — LLM 生成/调用失败
  7. `MealError(RAGPipelineError)` — Meal 管理相关错误
  8. `TestSetError(RAGPipelineError)` — 测试集管理相关错误
  9. `EvaluationError(RAGPipelineError)` — 评估计算相关错误

#### Scenario: 替换现有异常
- **WHEN** 将 `src/` 和 `eval/` 中的 `raise ValueError` / `raise Exception` 替换为对应自定义异常
- **THEN**:
  1. 所有 `raise ValueError` 用于配置校验的 → `ConfigurationError`
  2. 所有 `raise ValueError` 用于解析参数的 → `ParsingError`
  3. 所有 `raise ValueError` 用于检索参数的 → `RetrievalError`
  4. 所有 `raise Exception from e` 用于 LLM 调用失败的 → `GenerationError`
  5. 所有 `raise ValueError` 用于 Meal 管理的 → `MealError`
  6. 所有 `raise ValueError` 用于测试集管理的 → `TestSetError`
  7. 所有 `raise ValueError` 用于评估的 → `EvaluationError`
  8. 错误消息文本保持不变
  9. `from e` 链式异常保持不变

#### Scenario: 向后兼容
- **WHEN** 外部代码捕获 `ValueError` 或 `Exception`
- **THEN** 由于自定义异常继承自 `RAGPipelineError` → `Exception`，`except Exception` 仍可捕获；但 `except ValueError` 将不再捕获，需确认项目内部无此依赖

### Requirement: RF-002 项目结构整理评估

系统 SHALL 产出一份评估报告，分析根目录 `.py` 文件迁移的影响范围。

#### Scenario: 评估完成
- **WHEN** 分析 `main.py`（704 行）和 `interactive.py`（79 行）的迁移可行性
- **THEN** 报告包含以下内容：
  1. 两个文件的依赖关系图
  2. `interactive.py` 与 `main.py` 功能重叠分析
  3. 迁移方案选项（移入 `src/cli/`、保持根目录、合并为一个文件）
  4. 影响范围（pixi.toml 入口脚本、文档引用、用户习惯）
  5. 推荐方案及理由

### Requirement: FEAT-011 补做 LLM 报告功能

系统 SHALL 支持对已完成的实验追溯生成 LLM 报告。

#### Scenario: 通过 CLI 追溯生成报告
- **WHEN** 用户执行 `pixi run python main.py --llm-report-only <exp_dir>`
- **THEN**:
  1. 加载指定实验目录下的 `variant_results/*.json`、`meal_snapshot.json`、`config_snapshot.yaml`、`manifest.json`
  2. 构造 `ExperimentReporter` 所需数据
  3. 调用 `generate_variant_comparison_report(use_llm=True)` 生成 LLM 报告
  4. 报告保存到 `{exp_dir}/experiment_report_llm.md`
  5. Token 消耗被 `token_tracker` 记录

#### Scenario: 实验目录不存在
- **WHEN** 用户指定的 `exp_dir` 不存在或缺少必要文件
- **THEN** 输出明确的错误提示，不崩溃

#### Scenario: LLM API 不可用
- **WHEN** LLM API 调用失败
- **THEN** 记录日志，输出错误提示，不崩溃

## MODIFIED Requirements

无修改的需求。

## REMOVED Requirements

无移除的需求。
