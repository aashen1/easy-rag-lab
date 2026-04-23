# Checklist

## INV-019 测试并行化可行性评估
- [x] 分析报告 `docs/reviews/inv-019-test-parallelization.md` 已创建
- [x] 报告包含当前测试时间基线数据
- [x] 报告包含 fixture 隔离性分析
- [x] 报告包含并行化风险点清单
- [x] 报告包含推荐方案（是否启用、分阶段策略）

## INV-021 文件路径安全检查
- [x] 分析报告 `docs/reviews/inv-021-file-path-security.md` 已创建
- [x] 报告包含所有路径构造入口清单
- [x] 报告包含已有保护措施说明
- [x] 报告包含缺失保护清单及风险等级
- [x] 报告包含推荐修复方案

## RF-017 自定义异常类型定义
- [x] `src/exceptions.py` 已创建，包含 RAGPipelineError 基类和 8 个子类
- [x] 每个自定义异常类有类型标注和 docstring
- [x] `src/pipeline.py` 中的 ValueError/Exception 已替换
- [x] `src/retriever.py`、`src/hybrid_retriever.py`、`src/bm25_retriever.py` 中的异常已替换
- [x] `src/parser.py`、`src/parsers/registry.py` 中的异常已替换
- [x] `src/experiment.py` 中的 ValueError 已替换
- [x] `src/meal.py` 中的 ValueError/FileNotFoundError 已替换
- [x] `src/test_set_manager.py` 中的 ValueError 已替换
- [x] `src/generator.py` 中的 Exception/ValueError 已替换
- [x] `eval/metrics/generation.py` 中的 Exception/ValueError 已替换
- [x] `eval/` 其他文件中的异常已替换
- [x] `src/__init__.py` 导出异常类
- [x] 所有替换保持错误消息文本不变
- [x] 所有替换保持 `from e` 链式异常不变
- [x] `pixi run lint` 通过
- [x] `pixi run pytest tests/ -m "not integration" -v` 全部通过

## RF-002 项目结构整理评估
- [x] 评估报告 `docs/reviews/rf-002-project-structure.md` 已创建
- [x] 报告包含 main.py 和 interactive.py 的依赖关系分析
- [x] 报告包含功能重叠分析
- [x] 报告包含迁移方案选项及推荐
- [x] 报告包含影响范围评估

## FEAT-011 补做 LLM 报告功能
- [x] `eval/run_experiment.py` 中新增 `generate_llm_report_only()` 函数
- [x] `main.py` 中新增 `--llm-report-only` CLI 参数
- [x] 目录不存在时输出明确错误提示，不崩溃
- [x] 文件缺失时输出明确错误提示，不崩溃
- [x] LLM API 不可用时记录日志，不崩溃
- [x] 生成的报告保存到 `{exp_dir}/experiment_report_llm.md`
- [x] Token 消耗被 token_tracker 记录
- [x] 测试覆盖 `--llm-report-only` 功能
- [x] `pixi run lint` 通过
- [x] `pixi run pytest tests/ -m "not integration" -v` 全部通过
