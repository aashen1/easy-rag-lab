# Code Quality Standards Fixup Spec

## Why

代码质量审查文档（`02-code-quality-standards.md`）中有 5 条 📋 已安排但未修复的建议，需要逐条评估并实施合理的修复，同时维护原文档状态同步更新，并在完成后更新 TODO.md。

## What Changes

- 修改 `src/` 下 9 个文件：为 ~60 个公共函数/方法补全 docstring（含 Args、Returns、Raises）
- 修改 `main.py`、`src/pipeline.py`、`src/retriever.py`、`src/test_generator.py`：补全缺失的类型标注（15 处）
- 修改 `src/meal.py`：为 7 处 IO 操作补全 try/except 异常处理
- 修改 `src/utils.py`：将 loguru sink 中的 `print()` 替换为 `sys.stdout.write`
- 修改 `src/chunker.py`：删除尾随空格
- 维护 `02-code-quality-standards.md`：同步更新每条建议的修复状态
- 修改 `TODO.md`：在 L74 打勾并戳完成时间

## 不修的建议及理由

### 建议 2：print() 调用违规（CLI 面向用户的输出部分）— 不修

**理由：牵动太大，建议此条单开。** 172 处 print 全部为 CLI 面向用户的输出（main.py、interactive.py、eval/run_eval.py、eval/run_experiment.py），替换为 loguru 会：
1. 改变输出格式（loguru 添加时间戳、颜色、level 标记），破坏 CLI 用户体验
2. 需要重新设计 CLI 输出策略（哪些用 logger.info、哪些用 logger.success、哪些保留 print）
3. 涉及 4 个文件、172 处修改，单任务内难以保证质量

**但会修 `src/utils.py` 中的 loguru sink print**（改为 `sys.stdout.write`），并为 CLI 文件添加注释说明 print 使用策略。

### 建议 6（部分）：eval/run_experiment.py 函数级 import — 不修

**理由：部分函数级 import 是合理的工程实践。** 审计发现 4 处函数级 import：
- `L129 import yaml` — 延迟加载，避免模块加载时触发 yaml 依赖
- `L434 from src.indexer import VectorIndexer` — 避免循环依赖
- `L822 from src.token_tracker import ...` — 延迟加载
- `L1474-1475 import tempfile / import yaml` — 延迟加载

强制移到模块顶部可能引入循环导入或不必要的启动依赖。这些函数级 import 是有意为之，不属于代码质量问题。

## Impact

- Affected code: `src/parser.py`, `src/chunker.py`, `src/utils.py`, `src/meal.py`, `src/indexer.py`, `src/embedder.py`, `src/retriever.py`, `src/pipeline.py`, `src/test_generator.py`, `main.py`, `.trae/code_reviews/v0.1.5/02-code-quality-standards.md`, `TODO.md`
- 无 breaking changes，所有修改均为补全文档/类型/异常处理

## ADDED Requirements

### Requirement: 公共函数必须有 docstring

所有 `src/` 下的公共函数/方法 SHALL 包含 docstring，含功能描述、参数说明（Args）、返回值说明（Returns）、异常说明（Raises，如适用）。

### Requirement: 公共函数必须有完整类型标注

所有公共函数 SHALL 标注参数类型与返回值类型。`-> None` 不可省略。

### Requirement: IO 操作必须有 try/except

所有 IO 操作（文件读写、网络请求）SHALL 有 try/except，捕获异常后记录日志并优雅降级。

### Requirement: loguru sink 不使用 print

loguru console sink 配置 SHALL 使用 `sys.stdout.write` 而非 `print()`。

### Requirement: Code Review 文档状态同步

`02-code-quality-standards.md` SHALL 始终反映每条建议的最新修复状态。

### Requirement: TODO.md 完成标记

修复完成后 SHALL 在 TODO.md L74 打勾并戳完成时间。
