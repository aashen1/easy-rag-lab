# Tasks

- [x] Task 1: INV-015 — 创建 tiktoken/BGE tokenizer 差异量化分析脚本
  - [x] 1.1: 创建 `scripts/analyze_tokenizer_diff.py`，读取 JSONL chunks，分别用 tiktoken cl100k_base 和 BGE WordPiece tokenizer 计数
  - [x] 1.2: 输出统计报告：总 chunk 数、两种 tokenizer 的 token 数分布（min/max/mean/median）、超出 BGE 512 的 chunk 数和占比
  - [x] 1.3: 支持 `--input_dir` 参数指定 chunks 目录，无数据时输出提示不崩溃

- [x] Task 2: RF-013 — chunk_id 命名规范化（`_` → `::chunk::`）
  - [x] 2.1: 修改 `src/chunker.py:178` — chunk_id 格式改为 `f"{source_name}::chunk::{chunk['metadata']['chunk_index']:03d}"`
  - [x] 2.2: 修改 `src/semantic_chunker.py:409` — 同上，保持一致
  - [x] 2.3: 重写 `eval/metrics/utils.py` 的 `_parse_chunk_id` — 优先按 `::chunk::` 分割，旧格式 fallback 到 `rfind("_")`
  - [x] 2.4: 更新 `tests/test_chunker.py` 中 `test_process_parsed_files_chunk_id_format` 断言为新格式
  - [x] 2.5: 在 `tests/test_metrics.py` 中增加 `_parse_chunk_id` 新格式测试和旧格式向后兼容测试
  - [x] 2.6: 更新其他测试文件中硬编码的旧格式 chunk_id（test_bm25_retriever、test_test_generator、test_run_experiment、test_evaluators、test_regression 等）

- [x] Task 3: RF-014 — normalize_source 匹配精度提升
  - [x] 3.1: 增强 `eval/metrics/utils.py` 的 `normalize_source` — 增加 `include_parent: bool = False` 参数，返回 `{parent_name}/{stem}` 格式
  - [x] 3.2: 更新 `normalize_source_with_equivalence` — 内部调用 `normalize_source` 时传递 `include_parent` 参数
  - [x] 3.3: 更新 `eval/metrics/retrieval.py` — 调用 `normalize_source` 时传递 `include_parent=True`
  - [x] 3.4: 更新 `eval/metrics/dedup.py` — 调用 `normalize_source` 时传递 `include_parent=True`
  - [x] 3.5: 更新 `eval/evaluators/builtin_evaluator.py` — 调用 `normalize_source_with_equivalence` 时传递 `include_parent=True`
  - [x] 3.6: 在 `config.yaml` 的 evaluation 段增加 `normalize_source_include_parent: true` 配置项
  - [x] 3.7: 在 `tests/test_metrics.py` 的 `TestNormalizeSource` 中增加含父目录的测试用例

- [x] Task 4: INV-010 — 元数据增强（PDF 页码 + MD 标题层级）
  - [x] 4.1: 修改 `src/parser.py` — 将 pymupdf4llm 的页码分隔符替换为 `<!-- page: N -->` 标记
  - [x] 4.2: 修改 `src/chunker.py` — 增加 `_extract_page_markers`、`_extract_headings`、`_get_page_range` 辅助函数，在 `process_parsed_files()` 中为每个 chunk 记录 `page_start`、`page_end`、`headings`
  - [x] 4.3: 修改 `src/semantic_chunker.py` — 同步增加元数据增强
  - [x] 4.4: 在 `tests/test_parser.py` 中增加页码标记测试
  - [x] 4.5: 在 `tests/test_chunker.py` 中增加元数据测试（页码范围、标题层级、无标记兼容）

- [x] Task 5: OPT-007 — 基线 chunk_overlap 非零优化
  - [x] 5.1: 创建 `exp_configs/experiments/overlap_comparison.yaml` — 对比 overlap 值 0、32、64、128
  - [x] 5.2: 更新 `config.yaml` 中 `chunker.chunk_overlap` 的默认值为 64

# Task Dependencies

- Task 1 (INV-015) 独立执行，纯调研
- Task 2 (RF-013) 独立于 Task 1，可并行
- Task 3 (RF-014) 依赖 Task 2（normalize_source 需要与新 chunk_id 格式协调）
- Task 4 (INV-010) 依赖 Task 2（元数据增强时 chunk_id 已是新格式）和 Task 3（normalize_source 精度提升后 source 匹配更准确）
- Task 5 (OPT-007) 依赖 Task 1（调研结论决定 chunk_size 是否调整）和 Task 4（元数据增强后实验结果更有参考价值）
