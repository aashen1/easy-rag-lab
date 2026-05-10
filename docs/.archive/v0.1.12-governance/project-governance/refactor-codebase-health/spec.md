# 代码健康度重构 Spec

## Why

项目核心模块存在严重的 God Object 问题（`test_generator.py` 5097 行、`run_experiment.py` 3138 行、`meal.py` 2203 行），以及 DRY 违规（ArtifactCache 构建重复 6 处）、深层嵌套控制流（`pipeline.query()` 4 层 if-elif）、手动验证代码过长（`ExperimentConfig.validate()` 236 行）等问题。这些问题导致维护成本高、修改风险大、合并冲突频繁。需要系统性重构以提升代码可维护性。

## What Changes

- **RF-066**：将 `experiment.py` 中 9 处方法内 `import json` 移至文件顶部
- **RF-067**：清理 `pipeline.py` 的 `__main__` 块（其他模块已无 `__main__` 块）
- **RF-062**：将 `src/meal.py`（2203 行）拆分为 `src/meal/` 包（models/hashes/cache/manager/builders/utils）
- **RF-064**：提取 `create_artifact_cache()` 工厂函数，消除 6 处重复的 ArtifactCache 构建代码
- **RF-065**：用 Pydantic 模型替代 `ExperimentConfig.validate()` 的 236 行手动验证
- **RF-063**：用策略模式重构 `pipeline.query()` 的深层嵌套 if-elif
- **RF-061**：将 `eval/run_experiment.py`（3138 行）拆分为 `eval/runner/` 包
- **RF-060**：将 `src/test_generator.py`（5097 行）拆分为 `src/test_generation/` 包

## Impact

- Affected code: `src/meal.py`、`src/pipeline.py`、`src/experiment.py`、`src/test_generator.py`、`eval/run_experiment.py`
- Affected tests: `test_meal.py`、`test_pipeline.py`、`test_experiment.py`、`test_test_generator.py`、`test_run_experiment.py`、`test_e2e_experiment.py`、`test_run_eval.py`、`test_parser_unified.py`、`test_test_set_manager.py`、`test_golden_testset.py`、`test_regression.py`
- Affected specs: RF-20260428-016（Pipeline 类职责拆分，与 RF-063 部分重叠）、FEAT-20260428-024（配置验证系统，与 RF-065 重叠）
- **BREAKING**: 无。所有重构均保持公共 API 向后兼容（通过 facade 模式重新导出）

## ADDED Requirements

### Requirement: meal.py 模块化拆分

系统 SHALL 将 `src/meal.py` 拆分为 `src/meal/` 包，包含以下子模块：
- `src/meal/models.py`：`MealStatus`、`MealFile`、`MealConfig` 数据模型
- `src/meal/hashes.py`：6 个 `compute_*` 函数 + `generate_collection_name`
- `src/meal/cache.py`：`ArtifactCache` 类 + `create_artifact_cache()` 工厂函数
- `src/meal/manager.py`：`MealManager` 类
- `src/meal/builders.py`：`build_chunks_if_needed`、`build_index_from_chunks`
- `src/meal/utils.py`：`validate_meal_name`、`generate_timestamp_name`、`_infer_equivalence_groups`
- `src/meal/__init__.py`：重新导出所有公共 API

系统 SHALL 保留 `src/meal.py` 作为 facade 文件，从 `src/meal/` 重新导出所有公共符号，确保 `from src.meal import X` 仍然可用。

#### Scenario: 向后兼容导入
- **WHEN** 外部代码执行 `from src.meal import MealManager, ArtifactCache, MealConfig`
- **THEN** 导入成功，行为与拆分前完全一致

#### Scenario: 新风格导入
- **WHEN** 外部代码执行 `from src.meal.cache import ArtifactCache, create_artifact_cache`
- **THEN** 导入成功

### Requirement: ArtifactCache 工厂函数

系统 SHALL 在 `src/meal/cache.py` 中提供 `create_artifact_cache(config: dict[str, Any]) -> ArtifactCache` 工厂函数，统一 ArtifactCache 的构建逻辑。

#### Scenario: 工厂函数替代重复代码
- **WHEN** 代码需要创建 ArtifactCache 实例
- **THEN** 应使用 `create_artifact_cache(config)` 而非手动解析 artifacts 配置

#### Scenario: 所有重复点已替换
- **WHEN** 搜索 `ArtifactCache(` 的调用点
- **THEN** 除 `create_artifact_cache()` 内部和 `MealManager.__init__` 外，无其他手动构建代码

### Requirement: run_experiment.py 模块化拆分

系统 SHALL 将 `eval/run_experiment.py` 拆分为 `eval/runner/` 包，包含以下子模块：
- `eval/runner/asset_verifier.py`：`AssetVerificationResult`、`sanitize_config`、`verify_experiment_assets`、`collect_environment_info`
- `eval/runner/preparation.py`：`prepare_meal`、`prepare_test_sets`、`_prepare_legacy_test_set`、`prepare_variant_chunks`、`prepare_index_for_variant`
- `eval/runner/evaluation.py`：`_collect_rag_samples`、`_evaluate_with_builtin`、`_evaluate_with_ragas`、`evaluate_test_set`、`_create_evaluators`
- `eval/runner/metrics.py`：`compute_aggregate_metrics`、`_build_legacy_resolver`、`_namespace_result`、`_merge_result`
- `eval/runner/reporting.py`：`generate_llm_report_only`
- `eval/runner/comparison.py`：`compare_experiments`、`_build_comparison_data`、`_extract_category_metrics`、`_print_comparison_table`、`_generate_comparison_report`
- `eval/runner/reproduction.py`：`reproduce_experiment`
- `eval/runner/__init__.py`：重新导出所有公共 API

系统 SHALL 保留 `eval/run_experiment.py` 作为 CLI 入口，从 `eval/runner/` 导入并编排执行流程。

#### Scenario: CLI 行为不变
- **WHEN** 执行 `pixi run experiment run <config>`
- **THEN** 行为与拆分前完全一致

### Requirement: test_generator.py 模块化拆分

系统 SHALL 将 `src/test_generator.py` 拆分为 `src/test_generation/` 包，包含以下子模块：
- `src/test_generation/models.py`：问题类型枚举、分布配置等数据模型
- `src/test_generation/prompts.py`：所有提示词模板（FACTUAL_PROMPT、BOUNDARY_PROMPT 等）
- `src/test_generation/strategies/`：各策略独立模块
  - `src/test_generation/strategies/base.py`：策略基类
  - `src/test_generation/strategies/factual.py`
  - `src/test_generation/strategies/hypothetical.py`
  - `src/test_generation/strategies/adversarial.py`
  - `src/test_generation/strategies/document.py`
- `src/test_generation/validators.py`：数值精度校验、excerpt 验证、文档去重
- `src/test_generation/chunk_locator.py`：答案 chunk 定位逻辑
- `src/test_generation/generator.py`：`TestSetGenerator` 类（编排层）
- `src/test_generation/__init__.py`：重新导出 `TestSetGenerator`

系统 SHALL 保留 `src/test_generator.py` 作为 facade 文件。

#### Scenario: 向后兼容导入
- **WHEN** 外部代码执行 `from src.test_generator import TestSetGenerator`
- **THEN** 导入成功，行为与拆分前完全一致

### Requirement: pipeline.query() 策略模式重构

系统 SHALL 用策略模式重构 `RAGPipeline.query()` 方法，消除深层嵌套的 if-elif 控制流。

- 定义检索策略基类 `RetrievalStrategy`，接口为 `retrieve(query: str, config: dict) -> list[SearchResult]`
- 实现三个策略：`VectorStrategy`、`BM25Strategy`、`HybridStrategy`
- 定义查询改写策略基类 `QueryRewriteStrategy`，接口为 `rewrite(query: str) -> RewrittenQuery`
- 实现：`NoRewriteStrategy`、`HyDEStrategy`、`MultiQueryStrategy`
- `query()` 方法简化为：rewrite → retrieve → rerank → generate

#### Scenario: query 方法行数控制
- **WHEN** 查看 `RAGPipeline.query()` 方法
- **THEN** 方法体不超过 50 行

#### Scenario: 嵌套深度控制
- **WHEN** 查看 `RAGPipeline.query()` 方法
- **THEN** 无嵌套超过 2 层的 if-elif

#### Scenario: 新增策略扩展
- **WHEN** 需要新增一种检索策略
- **THEN** 只需实现 `RetrievalStrategy` 接口，无需修改 `query()` 方法

### Requirement: ExperimentConfig Pydantic 验证

系统 SHALL 用 Pydantic 模型替代 `ExperimentConfig.validate()` 中的手动验证代码。

- 定义 Pydantic 模型：`ParserConfigModel`、`ChunkerConfigModel`、`RetrieverConfigModel`、`RagasConfigModel`、`ExperimentConfigModel`
- 利用 `field_validator` 和 `model_validator` 实现字段间依赖检查
- 保留 `validate()` 方法作为兼容层，内部委托给 Pydantic 验证
- 可通过 `model_json_schema()` 生成 JSON Schema

#### Scenario: validate 方法简化
- **WHEN** 查看 `ExperimentConfig.validate()` 方法
- **THEN** 方法体不超过 30 行（委托给 Pydantic）

#### Scenario: 验证行为一致
- **WHEN** 使用 Pydantic 模型验证配置
- **THEN** 验证结果与原 `validate()` 方法完全一致（相同的错误类型和错误消息）

### Requirement: experiment.py import json 清理

系统 SHALL 将 `src/experiment.py` 中 9 处方法内 `import json` 移至文件顶部。

#### Scenario: 无内联 json 导入
- **WHEN** 搜索 `experiment.py` 中的 `import json`
- **THEN** 仅在文件顶部出现一次

### Requirement: pipeline.py __main__ 块清理

系统 SHALL 移除 `src/pipeline.py` 的 `if __name__ == "__main__"` 块（L608-L675），该功能已被 `eval/run_experiment.py` 的 CLI 完全覆盖。

#### Scenario: 无 __main__ 块
- **WHEN** 搜索 `pipeline.py` 中的 `if __name__`
- **THEN** 无匹配结果

## MODIFIED Requirements

无。所有重构保持行为不变。

## REMOVED Requirements

无。
