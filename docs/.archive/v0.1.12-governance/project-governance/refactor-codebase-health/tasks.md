# Tasks

执行顺序按依赖关系和风险递增排列：先做简单独立的清理，再做基础模块拆分，最后做最复杂的拆分。

## Phase 1: 代码整洁清理（低风险，无依赖）

- [x] Task 1: RF-066 — experiment.py import json 移至顶部
  - [x] 1.1: 在 `src/experiment.py` 顶部添加 `import json`（如尚未存在）
  - [x] 1.2: 删除 `ExperimentManager` 中 9 处方法内 `import json`（L827, L837, L845, L905, L993, L1077, L1117 等）
  - [x] 1.3: 运行 `pixi run lint` 确认无问题
  - [x] 1.4: 运行 `pixi run pytest tests/test_experiment.py -x` 确认测试通过
  - [x] 1.5: 提交并更新 issue RF-20260428-066 状态为 done

- [x] Task 2: RF-067 — pipeline.py __main__ 块清理
  - [x] 2.1: 确认 `pipeline.py` 的 `__main__` 块（L608-L675）功能已被 `eval/run_experiment.py` CLI 覆盖
  - [x] 2.2: 删除 `pipeline.py` 的 `if __name__ == "__main__"` 块
  - [x] 2.3: 运行 `pixi run lint` 确认无问题
  - [x] 2.4: 运行 `pixi run pytest tests/test_pipeline.py -x` 确认测试通过
  - [x] 2.5: 提交并更新 issue RF-20260428-067 状态为 done

## Phase 2: meal.py 拆分（基础模块，后续依赖）

- [x] Task 3: RF-062 — 拆分 meal.py（2203 行）为 src/meal/ 包
  - [x] 3.1: 创建 `src/meal/` 包目录结构
  - [x] 3.2: 提取数据模型到 `src/meal/models.py`（`MealStatus`、`MealFile`、`MealConfig`）
  - [x] 3.3: 提取哈希计算到 `src/meal/hashes.py`（6 个 `compute_*` 函数 + `generate_collection_name`）
  - [x] 3.4: 提取缓存管理到 `src/meal/cache.py`（`ArtifactCache` 类）
  - [x] 3.5: 提取构建辅助到 `src/meal/builders.py`（`build_chunks_if_needed`、`build_index_from_chunks`）
  - [x] 3.6: 提取工具函数到 `src/meal/utils.py`（`validate_meal_name`、`generate_timestamp_name`、`_infer_equivalence_groups`）
  - [x] 3.7: 保留 `MealManager` 在 `src/meal/manager.py`
  - [x] 3.8: 创建 `src/meal/__init__.py`，重新导出所有公共 API
  - [x] 3.9: 将原 `src/meal.py` 改为 facade 文件，从 `src/meal/` 重新导出
  - [x] 3.10: 更新 `tests/test_meal.py` 的导入路径（如需要）
  - [x] 3.11: 运行 `pixi run pytest tests/test_meal.py -x` 确认测试通过
  - [x] 3.12: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 3.13: 运行 `pixi run lint` 确认无问题
  - [x] 3.14: 提交并更新 issue RF-20260428-062 状态为 done

- [x] Task 4: RF-064 — 提取 ArtifactCache 工厂函数
  - [x] 4.1: 在 `src/meal/cache.py` 中新增 `create_artifact_cache(config: dict[str, Any]) -> ArtifactCache` 工厂函数
  - [x] 4.2: 替换 `src/pipeline.py` 中 2 处重复的 ArtifactCache 构建代码
  - [x] 4.3: 替换 `eval/run_experiment.py` 中 3 处重复的 ArtifactCache 构建代码
  - [x] 4.4: 确认 `MealManager.__init__` 中的构建保持不变（使用 self.cache 成员变量）
  - [x] 4.5: 在 `src/meal/__init__.py` 和 `src/meal.py` facade 中导出 `create_artifact_cache`
  - [x] 4.6: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 4.7: 运行 `pixi run lint` 确认无问题
  - [x] 4.8: 提交并更新 issue RF-20260428-064 状态为 done

## Phase 3: 设计模式改进（中等风险）

- [x] Task 5: RF-065 — Pydantic 替代 ExperimentConfig.validate()
  - [x] 5.1: 定义 Pydantic 模型（`ExperimentConfigSchema` 等）
  - [x] 5.2: 利用 `model_validator` 实现字段验证和字段间依赖检查
  - [x] 5.3: 保留 `ExperimentConfig` dataclass 接口不变，`validate()` 内部委托给 Pydantic
  - [x] 5.4: 确保验证错误类型和消息与原实现一致
  - [x] 5.5: 运行 `pixi run pytest tests/test_experiment.py -x` 确认测试通过
  - [x] 5.6: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 5.7: 运行 `pixi run lint` 确认无问题
  - [x] 5.8: 提交并更新 issue RF-20260428-065 状态为 done
  - [x] 5.9: 更新 issue FEAT-20260428-024（配置验证系统）状态，标注与 RF-065 合并处理

- [x] Task 6: RF-063 — 策略模式重构 pipeline.query()
  - [x] 6.1: 定义检索策略基类 `RetrievalStrategy` 和 `RetrievalResult` 数据类
  - [x] 6.2: 实现 `VectorRetrievalStrategy`、`BM25RetrievalStrategy`、`HybridRetrievalStrategy`
  - [x] 6.3: 定义查询改写策略基类 `QueryRewriteStrategy` 和 `RewrittenQuery` 数据类
  - [x] 6.4: 实现 `NoRewriteStrategy`、`HyDERewriteStrategy`、`MultiQueryRewriteStrategy`
  - [x] 6.5: 重构 `RAGPipeline.query()` 为：rewrite → retrieve → rerank → generate
  - [x] 6.6: 移除 multi_query 的提前 return，统一流程
  - [x] 6.7: 运行 `pixi run pytest tests/test_pipeline.py -x` 确认测试通过
  - [x] 6.8: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 6.9: 运行 `pixi run lint` 确认无问题
  - [x] 6.10: 提交并更新 issue RF-20260428-063 状态为 done

## Phase 4: 大文件拆分（高风险，最大工作量）

- [x] Task 7: RF-061 — 拆分 run_experiment.py（3138 行）为 eval/runner/ 包
  - [x] 7.1: 创建 `eval/runner/` 包目录结构
  - [x] 7.2: 提取资产校验到 `eval/runner/asset_verifier.py`
  - [x] 7.3: 提取准备阶段到 `eval/runner/preparation.py`
  - [x] 7.4: 提取评估执行到 `eval/runner/evaluation.py`
  - [x] 7.5: 提取指标计算到 `eval/runner/metrics.py`
  - [x] 7.6: 提取报告生成到 `eval/runner/reporting.py`
  - [x] 7.7: 提取实验对比到 `eval/runner/comparison.py`
  - [x] 7.8: 提取实验复现到 `eval/runner/reproduction.py`
  - [x] 7.9: 创建 `eval/runner/__init__.py`，重新导出所有公共 API
  - [x] 7.10: 保留 `eval/run_experiment.py` 作为 CLI 入口，从 `eval/runner/` 导入并编排
  - [x] 7.11: 更新 `tests/test_run_experiment.py` 和 `tests/test_e2e_experiment.py` 中的局部导入路径
  - [x] 7.12: 运行 `pixi run pytest tests/test_run_experiment.py tests/test_e2e_experiment.py -x` 确认测试通过
  - [x] 7.13: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 7.14: 运行 `pixi run lint` 确认无问题
  - [x] 7.15: 提交并更新 issue RF-20260428-061 状态为 done

- [x] Task 8: RF-060 — 拆分 test_generator.py（5097 行）为 src/test_generation/ 包
  - [x] 8.1: 创建 `src/test_generation/` 包目录结构
  - [x] 8.2: 提取提示词模板到 `src/test_generation/prompts.py`
  - [x] 8.3: 提取数据模型到 `src/test_generation/models.py`
  - [x] 8.4: 提取验证逻辑到 `src/test_generation/validators.py`
  - [x] 8.5: 提取 chunk 定位到 `src/test_generation/chunk_locator.py`
  - [x] 8.6: 保留 `TestSetGenerator` 在 `src/test_generation/generator.py`（编排层）
  - [x] 8.7: 创建 `src/test_generation/__init__.py`，重新导出 `TestSetGenerator`
  - [x] 8.8: 将原 `src/test_generator.py` 改为 facade 文件
  - [x] 8.9: 更新测试 patch 路径
  - [x] 8.10: 运行 `pixi run pytest tests/test_test_generator.py tests/test_golden_testset.py -x` 确认测试通过
  - [x] 8.11: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 8.12: 运行 `pixi run lint` 确认无问题
  - [x] 8.13: 提交并更新 issue RF-20260428-060 状态为 done

## Task Dependencies

- Task 4 依赖 Task 3（需要 `src/meal/cache.py` 存在后才能添加工厂函数）
- Task 7 依赖 Task 4（拆分 run_experiment.py 时应使用 `create_artifact_cache` 工厂函数）
- Task 1、2、5、6、8 互相独立，但建议按 Phase 顺序执行以降低风险
- Task 5 和 FEAT-20260428-024 有重叠，合并处理
