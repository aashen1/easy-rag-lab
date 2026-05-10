# Code Quality Fixup Checklist

## 建议 3：公共函数缺少 docstring

- [x] `src/pipeline.py` 所有公共方法有 docstring（含 Args、Returns、Raises）
- [x] `src/retriever.py` 所有公共方法有 docstring
- [x] `src/indexer.py` 所有公共方法有 docstring
- [x] `src/embedder.py` 所有公共方法有 docstring
- [x] `src/utils.py` 所有公共函数有 docstring
- [x] `src/parser.py` 所有公共函数有 docstring
- [x] `src/chunker.py` 所有公共函数有 docstring
- [x] `src/meal.py` 所有公共函数/方法有 docstring
- [x] `src/test_generator.py` 所有公共方法有 docstring

## 建议 4：公共函数缺少类型标注

- [x] `main.py` _build_sampling_config 返回类型为 Optional[SamplingConfig]
- [x] `main.py` 各 handler 函数有 -> None 返回类型
- [x] `main.py` dict 类型改为 Dict[str, Any]
- [x] `src/pipeline.py` use_meal 有 -> MealConfig 返回类型
- [x] `src/retriever.py` __init__ 有 -> None 返回类型
- [x] `src/test_generator.py` _load_meal_chunks 的 meal_config 有 MealConfig 类型
- [x] `src/test_generator.py` _generate_question_with_llm 的 generator 有 Generator 类型

## 建议 5：IO 操作缺少 try/except

- [x] `src/meal.py` compute_file_sha256 文件读取有 try/except
- [x] `src/meal.py` ArtifactCache.save_manifest 文件写入有 try/except
- [x] `src/meal.py` ArtifactCache.load_manifest 文件读取有 try/except
- [x] `src/meal.py` MealManager.create_meal manifest 写入有 try/except
- [x] `src/meal.py` MealManager.rename_meal manifest 写入有 try/except
- [x] `src/meal.py` MealManager.copy_meal manifest 写入有 try/except
- [x] `src/meal.py` MealManager.repair_meal manifest 写入有 try/except

## 建议 6：代码风格问题

- [x] `src/chunker.py` 尾随空格已删除
- [x] `src/utils.py` loguru sink 不使用 print（改为 sys.stdout.write）

## 文档状态同步

- [x] `02-code-quality-standards.md` 建议 3 状态更新为 ✅ 已修复
- [x] `02-code-quality-standards.md` 建议 4 状态更新为 ✅ 已修复
- [x] `02-code-quality-standards.md` 建议 5 状态更新为 ✅ 已修复
- [x] `02-code-quality-standards.md` 建议 6 状态更新为 ✅ 已修复
- [x] `02-code-quality-standards.md` 建议 2 状态更新为 ❌ 已弃用（utils.py sink 已修，CLI print 不修并注明理由）
- [x] 审查结论更新为"已修复"

## TODO.md 更新

- [x] TODO.md L76 已打勾并戳完成时间（2026-04-18）

## 全量验证

- [x] `pixi run pytest tests/ -v` 全部通过（400 passed in 267.63s）
