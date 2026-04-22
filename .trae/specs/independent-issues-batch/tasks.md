# Tasks

## Phase 1：调查分析（并行，产出报告）

- [x] Task 1: INV-019 测试并行化可行性评估
  - [x] SubTask 1.1: 运行 `pixi run pytest tests/ -m "not integration" -v --durations=0` 获取当前测试时间基线
  - [x] SubTask 1.2: 分析 fixture 隔离性（temp_project_dir、mock_embedder 等）是否支持并行
  - [x] SubTask 1.3: 识别共享状态风险点（文件系统竞争、Qdrant 实例共享等）
  - [x] SubTask 1.4: 撰写分析报告 `docs/reviews/inv-019-test-parallelization.md`

- [x] Task 2: INV-021 文件路径安全检查
  - [x] SubTask 2.1: 审计所有从配置/用户输入构造文件路径的代码入口
  - [x] SubTask 2.2: 标注已有保护措施（如 meal.py 的 relative_to 检查）
  - [x] SubTask 2.3: 评估缺失保护的风险等级
  - [x] SubTask 2.4: 撰写分析报告 `docs/reviews/inv-021-file-path-security.md`

## Phase 2：代码风格重构（纯替换，无逻辑变更）

- [x] Task 3: RF-017 自定义异常类型定义
  - [x] SubTask 3.1: 创建 `src/exceptions.py`，定义异常层次结构（RAGPipelineError 及 8 个子类）
  - [x] SubTask 3.2: 在 `src/pipeline.py` 中替换 ValueError/Exception 为对应自定义异常
  - [x] SubTask 3.3: 在 `src/retriever.py`、`src/hybrid_retriever.py`、`src/bm25_retriever.py` 中替换
  - [x] SubTask 3.4: 在 `src/parser.py`、`src/parsers/registry.py` 中替换
  - [x] SubTask 3.5: 在 `src/experiment.py` 中替换（约 7 处 ValueError）
  - [x] SubTask 3.6: 在 `src/meal.py` 中替换（约 20 处 ValueError + 1 处 FileNotFoundError）
  - [x] SubTask 3.7: 在 `src/test_set_manager.py` 中替换（约 10 处 ValueError）
  - [x] SubTask 3.8: 在 `src/generator.py` 中替换（2 处 Exception + 1 处 ValueError）
  - [x] SubTask 3.9: 在 `eval/metrics/generation.py` 中替换（4 处 Exception + 4 处 ValueError）
  - [x] SubTask 3.10: 在 `eval/experiment_reporter.py`、`eval/run_experiment.py` 等其他 eval/ 文件中替换
  - [x] SubTask 3.11: 更新 `src/__init__.py` 导出异常类
  - [x] SubTask 3.12: 运行 `pixi run lint` 确保代码格式正确
  - [x] SubTask 3.13: 运行 `pixi run pytest tests/ -m "not integration" -v` 确保测试通过

## Phase 3：评估报告（产出报告，不修改代码）

- [x] Task 4: RF-002 项目结构整理评估
  - [x] SubTask 4.1: 分析 main.py 和 interactive.py 的依赖关系和功能重叠
  - [x] SubTask 4.2: 评估迁移方案（src/cli/ vs 根目录 vs 合并）
  - [x] SubTask 4.3: 检查 pixi.toml 入口脚本、文档引用等影响范围
  - [x] SubTask 4.4: 撰写评估报告 `docs/reviews/rf-002-project-structure.md`

## Phase 4：功能开发

- [x] Task 5: FEAT-011 补做 LLM 报告功能
  - [x] SubTask 5.1: 在 `eval/run_experiment.py` 中新增 `generate_llm_report_only(exp_dir)` 函数
  - [x] SubTask 5.2: 在 `main.py` 中新增 `--llm-report-only` CLI 参数
  - [x] SubTask 5.3: 添加错误处理（目录不存在、文件缺失、API 不可用）
  - [x] SubTask 5.4: 编写测试 `tests/test_run_experiment.py` 补充 llm-report-only 相关测试
  - [x] SubTask 5.5: 运行 `pixi run lint` 确保代码格式正确
  - [x] SubTask 5.6: 运行 `pixi run pytest tests/ -m "not integration" -v` 确保测试通过

# Task Dependencies

- Task 1 和 Task 2 可并行执行（均为调查分析，互不依赖）
- Task 3 独立于 Task 1/2（代码风格变更，不依赖调查结果）
- Task 4 独立于其他 Task
- Task 5 独立于其他 Task
- Task 3 的 SubTask 3.2-3.10 可并行执行（不同文件的替换互不影响），但需在 SubTask 3.1 完成后开始
- Task 3 的 SubTask 3.12-3.13 需在所有替换完成后执行
