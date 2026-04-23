# Checklist

## P0-1: Source 路径跨平台归一化

- [x] `src/chunker.py` 中所有 `source` 字段写入使用 `as_posix()` 格式（POSIX 正斜杠）
- [x] `src/semantic_chunker.py` 中 `source` 字段和 `source_filter` 比较使用 `as_posix()`
- [x] `src/pipeline.py` 中 `source_filter` 构建使用 `as_posix()`
- [x] `src/indexer.py` 中 `source_filter` 比较使用 `as_posix()`
- [x] `src/bm25_retriever.py` 中 `source_filter` 比较使用 `as_posix()`
- [x] `src/parsers/pymupdf4llm_parser.py` 中 `source` 元数据使用 `as_posix()`
- [x] `src/parsers/fitz_pdfplumber_parser.py` 中 `source` 元数据使用 `as_posix()`
- [x] `src/test_generator.py` 中路径使用 `as_posix()` 替代 `.replace("\\", "/")`
- [x] `eval/recommend_testset.py` 中路径使用 `as_posix()`
- [x] `eval/evaluators/builtin_evaluator.py` 无等价组时也对 source 进行 `normalize_source` 归一化比较
- [x] `eval/metrics/utils.py` 的 `normalize_source` 内部统一使用 `Path.as_posix()` 处理输入
- [x] `src/meal.py` 中路径统一使用 POSIX 格式
- [x] 跨平台测试：Windows 反斜杠路径和 POSIX 正斜杠路径归一化后结果一致
- [x] 相关测试通过

## P0-2: 等价组推断逻辑

- [x] `_infer_equivalence_groups()` 的 group_key 包含父目录信息
- [x] 不同目录下同名文件（如 `云南白药/2023年年度报告` vs `隆基绿能/2023年年度报告`）被分入不同等价组
- [x] 同一目录下同名不同版本文件（如 `_英文版_`、`摘要`）仍归为同一组
- [x] 相关测试通过

## P1-2: Generator 来源名称清理

- [x] `src/generator.py` 中来源名称不再包含 `.pages` 后缀
- [x] `clean_source_name()` 工具函数正确处理 `.pages.json`、`.json`、`.md` 等后缀
- [x] 非 page-aware 模式下来源名称显示保持不变
- [x] 相关测试通过

## P1-1: Tokenizer 统一

- [x] `src/chunker.py` 支持 `encoding: bge` 配置，使用 BGE tokenizer 切分
- [x] `src/embedder.py` 暴露 `get_tokenizer()` 方法
- [x] `config.yaml` 新增 `chunker.encoding` 配置项，默认 `bge`
- [x] 使用 BGE tokenizer 切分的 chunk 在 embedder 中不被截断
- [x] 向后兼容：`encoding: cl100k_base` 仍可使用
- [x] 相关测试通过

## P1-3: Score Threshold

- [x] `config.yaml` 中 `retrieval.score_threshold` 设为 `0.3`
- [x] 现有测试在阈值变更后仍通过

## P2-2: Context 截断保护

- [x] `config.yaml` 中 `generation.max_context_tokens` 设为 `8000`
- [x] 现有测试在截断启用后仍通过

## P2-1: 跨页 Chunk Overlap

- [x] `config.yaml` 新增 `chunker.cross_page_overlap` 配置项（默认 0）
- [x] `chunk_text_page_aware()` 支持 `cross_page_overlap > 0` 时跨页重叠
- [x] 跨页 chunk 的 metadata 包含 `cross_page: true` 和相关页码信息
- [x] `cross_page_overlap = 0` 时行为与修改前完全一致（向后兼容）
- [x] 相关测试通过

## 全局

- [x] `pixi run lint` 通过
- [x] `pixi run test` 全部通过（1145 passed, 10 skipped）
- [x] 无硬编码平台特定路径分隔符（已全面扫描并修复 src/ 和 eval/ 中的 `str(path)` → `as_posix()`）
