# Code Quality Fixup Checklist

## 建议 3：公共函数缺少 docstring

- [ ] `src/pipeline.py` 所有公共方法有 docstring（含 Args、Returns、Raises）
- [ ] `src/retriever.py` 所有公共方法有 docstring
- [ ] `src/indexer.py` 所有公共方法有 docstring
- [ ] `src/embedder.py` 所有公共方法有 docstring
- [ ] `src/utils.py` 所有公共函数有 docstring
- [ ] `src/parser.py` 所有公共函数有 docstring
- [ ] `src/chunker.py` 所有公共函数有 docstring
- [ ] `src/meal.py` 所有公共函数/方法有 docstring
- [ ] `src/test_generator.py` 所有公共方法有 docstring

## 建议 4：公共函数缺少类型标注

- [ ] `main.py` _build_sampling_config 返回类型为 Optional[SamplingConfig]
- [ ] `main.py` 各 handler 函数有 -> None 返回类型
- [ ] `main.py` dict 类型改为 Dict[str, Any]
- [ ] `src/pipeline.py` use_meal 有 -> MealConfig 返回类型
- [ ] `src/retriever.py` __init__ 有 -> None 返回类型
- [ ] `src/test_generator.py` _load_meal_chunks 的 meal_config 有 MealConfig 类型
- [ ] `src/test_generator.py` _generate_question_with_llm 的 generator 有 Generator 类型

## 建议 5：IO 操作缺少 try/except

- [ ] `src/meal.py` compute_file_sha256 文件读取有 try/except
- [ ] `src/meal.py` ArtifactCache.save_manifest 文件写入有 try/except
- [ ] `src/meal.py` ArtifactCache.load_manifest 文件读取有 try/except
- [ ] `src/meal.py` MealManager.create_meal manifest 写入有 try/except
- [ ] `src/meal.py` MealManager.rename_meal manifest 写入有 try/except
- [ ] `src/meal.py` MealManager.copy_meal manifest 写入有 try/except
- [ ] `src/meal.py` MealManager.repair_meal manifest 写入有 try/except

## 建议 6：代码风格问题

- [ ] `src/chunker.py` 尾随空格已删除
- [ ] `src/utils.py` loguru sink 不使用 print（改为 sys.stdout.write）

## 文档状态同步

- [ ] `02-code-quality-standards.md` 建议 3 状态更新为 ✅ 已修复
- [ ] `02-code-quality-standards.md` 建议 4 状态更新为 ✅ 已修复
- [ ] `02-code-quality-standards.md` 建议 5 状态更新为 ✅ 已修复
- [ ] `02-code-quality-standards.md` 建议 6 状态更新为 ✅ 已修复
- [ ] `02-code-quality-standards.md` 建议 2 状态更新（utils.py sink 已修，CLI print 不修并注明理由）
- [ ] 建议总览表格状态列已同步更新

## TODO.md 更新

- [ ] TODO.md L74 已打勾并戳完成时间

## 全量验证

- [ ] `pixi run pytest tests/ -v` 全部通过
