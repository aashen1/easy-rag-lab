# Tasks

- [x] Task 1: 为核心链路模块补全 docstring — `src/pipeline.py`, `src/retriever.py`, `src/indexer.py`, `src/embedder.py`
  - [x] SubTask 1.1: `src/pipeline.py` — RAGPipeline.__init__, build_index, use_meal, query
  - [x] SubTask 1.2: `src/retriever.py` — Retriever.__init__, retrieve
  - [x] SubTask 1.3: `src/indexer.py` — VectorIndexer.__init__, create_collection, index_chunks, build_index, get_collection_info, delete_collection, close
  - [x] SubTask 1.4: `src/embedder.py` — Embedder.__init__, _encode_batch, embed_texts, embed_query, get_embedding_dimension
  - [x] SubTask 1.5: git commit（msg: `docs(src): add docstrings to core pipeline modules`）

- [x] Task 2: 为工具函数模块补全 docstring — `src/utils.py`, `src/parser.py`, `src/chunker.py`
  - [x] SubTask 2.1: `src/utils.py` — load_config, setup_logger, get_llm_config, get_env_var, ensure_dir
  - [x] SubTask 2.2: `src/parser.py` — parse_pdf, parse_all_pdfs
  - [x] SubTask 2.3: `src/chunker.py` — chunk_text, process_parsed_files；同时删除 L71 尾随空格
  - [x] SubTask 2.4: git commit（msg: `docs(src): add docstrings to utility modules`）

- [x] Task 3: 为数据管理模块补全 docstring — `src/meal.py`, `src/test_generator.py`
  - [x] SubTask 3.1: `src/meal.py` — compute_file_sha256, compute_data_id, compute_parser_config_hash, compute_chunker_config_hash, compute_embedding_config_hash, compute_index_key, generate_collection_name, validate_meal_name, generate_timestamp_name, ArtifactCache 方法, MealManager 方法
  - [x] SubTask 3.2: `src/test_generator.py` — TestSetGenerator.__init__, generate_test_set, _load_meal_chunks, _group_chunks_by_source, _select_chunks, _select_chunks_for_factual, _select_chunks_for_boundary, _select_chunks_for_multi_hop, _generate_question_with_llm, _parse_llm_response, _save_test_set
  - [x] SubTask 3.3: git commit（msg: `docs(src): add docstrings to data management modules`）

- [x] Task 4: 补全缺失的类型标注（15 处）
  - [x] SubTask 4.1: `main.py` — _build_sampling_config 返回类型改为 Optional[SamplingConfig]；各 handler 函数添加 -> None；_handle_generate_test_set 的 config: dict 改为 Dict[str, Any]；_print_query_result 的 result: dict 改为 Dict[str, Any]；_handle_create_meal 和 _handle_generate_test_set 的 args 参数添加类型
  - [x] SubTask 4.2: `src/pipeline.py` — use_meal 添加 -> MealConfig
  - [x] SubTask 4.3: `src/retriever.py` — __init__ 添加 -> None
  - [x] SubTask 4.4: `src/test_generator.py` — _load_meal_chunks 的 meal_config 添加 MealConfig 类型；_generate_question_with_llm 的 generator 添加 Generator 类型
  - [x] SubTask 4.5: git commit（msg: `fix(src): add missing type annotations to public functions`）

- [x] Task 5: 为 `src/meal.py` 的 7 处 IO 操作补全 try/except
  - [x] SubTask 5.1: compute_file_sha256 — 文件读取添加 try/except
  - [x] SubTask 5.2: ArtifactCache.save_manifest — 文件写入添加 try/except
  - [x] SubTask 5.3: ArtifactCache.load_manifest — 文件读取添加 try/except
  - [x] SubTask 5.4: MealManager.create_meal — manifest 写入添加 try/except
  - [x] SubTask 5.5: MealManager.rename_meal — manifest 写入添加 try/except
  - [x] SubTask 5.6: MealManager.copy_meal — manifest 写入添加 try/except
  - [x] SubTask 5.7: MealManager.repair_meal — manifest 写入添加 try/except
  - [x] SubTask 5.8: git commit（与 Task 3 docstring 合并提交）

- [x] Task 6: 修复 `src/utils.py` loguru sink 中的 print()
  - [x] SubTask 6.1: 将 `lambda msg: print(msg, end="")` 替换为 `lambda msg: sys.stdout.write(msg)`
  - [x] SubTask 6.2: git commit（与 Task 4 类型标注合并提交）

- [x] Task 7: 更新 `02-code-quality-standards.md` 文档状态
  - [x] SubTask 7.1: 将建议 3（docstring）状态更新为 ✅ 已修复
  - [x] SubTask 7.2: 将建议 4（类型标注）状态更新为 ✅ 已修复
  - [x] SubTask 7.3: 将建议 5（IO try/except）状态更新为 ✅ 已修复
  - [x] SubTask 7.4: 将建议 6（代码风格）状态更新为 ✅ 已修复（尾随空格已删除；重复 import 已修复）
  - [x] SubTask 7.5: 更新建议 2（print）状态：标注 utils.py sink 已修，CLI print 不修并注明理由
  - [x] SubTask 7.6: 更新建议总览表格
  - [x] SubTask 7.7: git commit（msg: `docs: update code-quality-standards review status`）

- [x] Task 8: 更新 TODO.md
  - [x] SubTask 8.1: 在 L76 打勾并戳完成时间
  - [x] SubTask 8.2: git commit（msg: `chore: mark code quality review as completed in TODO`）

- [x] Task 9: 全量测试运行验证
  - [x] SubTask 9.1: 运行 `pixi run pytest tests/ -v` 确保所有测试通过（400 passed in 267.63s）

# Task Dependencies

- Task 1-3 之间无依赖，可并行执行
- Task 4-6 之间无依赖，可并行执行
- Task 1-6 可全部并行执行
- Task 7 依赖 Task 1-6 全部完成
- Task 8 依赖 Task 7 完成
- Task 9 依赖 Task 1-6 全部完成
