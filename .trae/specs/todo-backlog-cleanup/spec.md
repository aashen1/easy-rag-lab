# TODO Backlog Cleanup Spec

## Why

TODO.md 中积压了大量待办事项，部分已修复但未更新状态，部分属于小修小补可以快速完成，部分规模较大需要单独规划。需要一次性清理，完成能做的，批复需要延后的。同时，所有涉及的待办文档都需要标注状态变化，确保用户翻到任何文档都不用猜测其是否过时。

## What Changes

### 已修复确认（更新文档状态即可）
- 调试钩子代码残留 → 已从 4 个入口文件中删除
- Generator 未使用 API system 参数 → 已修复（generator.py:124）
- Indexer 资源未释放 → 已添加 close()/__enter__/__exit__（pipeline.py:139-154）
- chunk_comparison.yaml 无效策略名 → 已改为 multi_hop
- Meal total_chunks 偏差 → 已修复，初始化为 0
- 重复导入（run_eval.py, run_experiment.py）→ 已修复

### 本次完成的小修补
- `eval/experiment_reporter.py` 添加 `__test__ = False` 修复 PytestCollectionWarning
- `src/chunker.py` 移除尾随空格（第 68 行）
- `CHANGELOG.md` 清洗：将已修复的 Known Issues 移除，保留未修复的
- `TODO.md` 全面更新：标记已完成的，批复需要延后的
- `tests/test_e2e_experiment.py` 删除重复的本地 `temp_project_dir` fixture（test-review-suggestions #1）
- `tests/conftest.py` mock_embedder fixture 使用固定向量替代随机向量（test-review-suggestions #10）

### 本次文档状态标注
对所有涉及的待办文档逐项标注状态变化，状态标签包括：
- `✅ 已修复` — 代码已修复，无需进一步操作
- `📋 已安排` — 已规划在未来修复（附建议方式：spec/plan）
- `❌ 已弃用` — 用户拒绝接受该修复建议，不再执行
- `⏳ 待定` — 需要进一步评估

涉及文档：
- `.trae/documents/test-suite/test-review-suggestions.md` — 11 条建议逐项标注
- `.trae/documents/test-suite/test-future-directions.md` — 6 个方向逐项标注
- `.trae/code_reviews/v0.1.5/02-code-quality-standards.md` — 7 类问题逐项标注
- `.trae/code_reviews/v0.1.5/04-known-bugs-functional-issues.md` — 13 个问题逐项标注
- `.trae/code_reviews/v0.1.5/05-open-source-readiness.md` — 阻塞项和建议项逐项标注

### 本次批复延后的事项（维护文档记录意见）
- 重写问题生成策略 → 规模大，需 spec 模式单独规划
- 实验报告 sources 字段细化 → 与问题生成策略耦合，一并延后
- 项目结构整理 → 需评估影响范围，建议 spec 模式
- 优化新用户链路性能 → 需性能基准测试，建议 plan 模式
- 验证可扩展性 → 依赖黄金测试集落地
- 日志系统分析 → 需调研最佳实践，建议 plan 模式
- test-future-directions.md → 6 个方向，每个可独立推进，建议逐个 spec
- 全面更新文档 → 规模大，建议 spec 模式
- integration 测试时间优化 → 需分析瓶颈，建议 plan 模式
- 02-code-quality-standards.md 优化代码 → docstring/类型标注/IO try/except 工作量大，建议 spec 模式
- 更新 README 和 CLAUDE 文件 → 需同步到当前版本，建议 plan 模式
- 04-known-bugs-functional-issues.md 核实修复 → 部分已修，剩余需逐项验证
- 核实 05-open-source-readiness.md → 需逐项检查，建议 plan 模式
- 实验资产包记录 token summary → 需了解现有资产包结构
- Source path format mismatch → 核心评测 bug，需 spec 模式单独修复
- print() 违规 → CLI 输出有意使用 print，需分类处理，建议 spec 模式

## Impact

- Affected files: `eval/experiment_reporter.py`, `src/chunker.py`, `CHANGELOG.md`, `TODO.md`, `tests/test_e2e_experiment.py`, `tests/conftest.py`, `.trae/documents/test-suite/test-review-suggestions.md`, `.trae/documents/test-suite/test-future-directions.md`, `.trae/code_reviews/v0.1.5/02-code-quality-standards.md`, `.trae/code_reviews/v0.1.5/04-known-bugs-functional-issues.md`, `.trae/code_reviews/v0.1.5/05-open-source-readiness.md`
- No breaking changes
- No functional behavior changes (only cleanup, bugfix, and documentation updates)

## ADDED Requirements

### Requirement: PytestCollectionWarning 修复
系统 SHALL 在 `TestCaseResult` dataclass 上添加 `__test__ = False` 属性。

#### Scenario: pytest 运行无收集警告
- WHEN 用户运行 `pixi run pytest tests/ -v`
- THEN 不出现 PytestCollectionWarning

### Requirement: CHANGELOG 清洗
CHANGELOG.md SHALL 只记录已确认的变更和已知问题，已修复的 Known Issues SHALL 被移除。

### Requirement: TODO 更新与批复
TODO.md SHALL 反映所有待办事项的最新状态：已完成的标记完成，延后的附上批复意见。

### Requirement: 待办文档状态标注
所有涉及的待办文档（test-review-suggestions.md、test-future-directions.md、02-code-quality-standards.md、04-known-bugs-functional-issues.md、05-open-source-readiness.md）中的每一项 SHALL 标注当前状态（✅已修复/📋已安排/❌已弃用/⏳待定），确保用户翻到任何文档都能立即判断该项是否过时。

### Requirement: 频繁提交
每完成一个独立任务 SHALL 进行一次 git commit，commit message 仅使用英文 ASCII 字符，遵循 Conventional Commits 格式。

## MODIFIED Requirements

无修改项。

## REMOVED Requirements

无移除项。
