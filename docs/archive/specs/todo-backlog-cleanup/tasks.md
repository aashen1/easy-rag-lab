# Tasks

- [x] Task 1: 修复 PytestCollectionWarning，为 TestCaseResult 添加 `__test__ = False`
  - [x] 修改 eval/experiment_reporter.py
  - [x] commit: `fix: add __test__ = False to TestCaseResult to suppress PytestCollectionWarning`
- [x] Task 2: 修复 src/chunker.py 尾随空格（第 68 行）
  - [x] 修改 src/chunker.py
  - [x] commit: `fix: remove trailing whitespace in chunker.py`
- [x] Task 3: 删除 tests/test_e2e_experiment.py 中重复的本地 `temp_project_dir` fixture
  - [x] 修改 tests/test_e2e_experiment.py
  - [x] commit: `refactor: remove duplicate temp_project_dir fixture from test_e2e_experiment.py`
- [x] Task 4: 修改 tests/conftest.py mock_embedder fixture 使用固定向量
  - [x] 修改 tests/conftest.py
  - [x] commit: `refactor: use fixed vectors in mock_embedder fixture for deterministic tests`
- [x] Task 5: 清洗 CHANGELOG.md，移除已修复的 Known Issues
  - [x] 修改 CHANGELOG.md
  - [x] commit: `docs: clean up CHANGELOG.md by removing fixed Known Issues`
- [x] Task 6: 标注 test-review-suggestions.md 状态
  - [x] 逐项标注 11 条建议的状态
  - [x] commit: `docs: annotate status in test-review-suggestions.md`
- [x] Task 7: 标注 test-future-directions.md 状态
  - [x] 逐项标注 6 个方向的状态
  - [x] commit: `docs: annotate status in test-future-directions.md`
- [x] Task 8: 标注 02-code-quality-standards.md 状态
  - [x] 逐项标注 7 类问题的状态
  - [x] commit: `docs: annotate status in 02-code-quality-standards.md`
- [x] Task 9: 标注 04-known-bugs-functional-issues.md 状态
  - [x] 逐项标注 13 个问题的状态
  - [x] commit: `docs: annotate status in 04-known-bugs-functional-issues.md`
- [x] Task 10: 标注 05-open-source-readiness.md 状态
  - [x] 逐项标注阻塞项和建议项的状态
  - [x] commit: `docs: annotate status in 05-open-source-readiness.md`
- [x] Task 11: 全面更新 TODO.md，标记已完成项，批复延后项
  - [x] 修改 TODO.md
  - [x] commit: `docs: update TODO.md with completion status and deferral notes`
- [x] Task 12: 运行测试验证所有修改无回归
  - [x] `pixi run pytest tests/ -m "not integration" -v` — 全绿

# Task Dependencies

- Task 12 depends on Task 1-4（代码修改完成后才能验证）
- Task 5-11 可与 Task 1-4 并行（文档修改不影响代码）
- Task 6-10 之间无依赖，可并行
