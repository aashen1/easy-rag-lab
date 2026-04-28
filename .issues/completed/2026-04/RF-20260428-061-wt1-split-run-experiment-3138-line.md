---
id: RF-20260428-061-wt1
title: split-run-experiment-3138-lines-god-file
type: RF
status: done
priority: high
labels:
- refactor
- god-object
assignee: null
milestone: null
created_at: '2026-04-28T03:45:00.955402'
updated_at: '2026-04-28T03:45:00.955402'
source: active\RF-20260428-061-wt1-split-run-experiment-3138-line.md
legacy_id: null
---
## 重构目标

将 `eval/run_experiment.py`（3138 行）拆分为多个职责单一的模块，消除 God Object 反模式。

## 问题分析

当前 `run_experiment.py` 一个文件承担了过多职责：
- 实验配置验证与资产校验（`verify_experiment_assets`）
- Meal 准备（`prepare_meal`）
- Test set 准备（`prepare_test_sets`、`_prepare_legacy_test_set`）
- Variant 索引准备（`prepare_index_for_variant`、`prepare_variant_chunks`）
- RAG 采样（`_collect_rag_samples`）
- Builtin 评估（`_evaluate_with_builtin`）
- RAGAS 评估（`_evaluate_with_ragas`）
- 聚合指标计算（`compute_aggregate_metrics`）
- LLM 报告生成（`generate_llm_report_only`）
- 实验对比（`compare_experiments` 及 3 个辅助函数）
- 实验复现（`reproduce_experiment`）
- CLI 入口（`main`）

导致：
- 任何一处修改都可能影响其他功能
- 无法独立测试各子流程
- 代码审查需要理解 3000+ 行上下文

## 重构范围

`eval/run_experiment.py` → 拆分为 `eval/runner/` 包

## 重构步骤

1. 创建 `eval/runner/` 包目录
2. 提取资产校验到 `eval/runner/asset_verifier.py`（`verify_experiment_assets`、`AssetVerificationResult`、`sanitize_config`）
3. 提取准备阶段到 `eval/runner/preparation.py`（`prepare_meal`、`prepare_test_sets`、`prepare_variant_chunks`、`prepare_index_for_variant`）
4. 提取评估执行到 `eval/runner/evaluation.py`（`_collect_rag_samples`、`_evaluate_with_builtin`、`_evaluate_with_ragas`、`evaluate_test_set`、`compute_aggregate_metrics`）
5. 提取报告生成到 `eval/runner/reporting.py`（`generate_llm_report_only`）
6. 提取实验对比到 `eval/runner/comparison.py`（`compare_experiments` 及辅助函数）
7. 提取实验复现到 `eval/runner/reproduction.py`（`reproduce_experiment`）
8. 保留 `eval/run_experiment.py` 作为 CLI 入口，调用 `eval/runner/` 中的编排逻辑
9. 更新所有 import 路径
10. 运行全量测试确保行为不变

## 验收标准

- 每个文件不超过 500 行
- 所有现有测试通过
- CLI 行为不变

## 更新记录

- 2026-04-28：创建
