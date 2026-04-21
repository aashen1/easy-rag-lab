# Checklist

## INV-015 — tiktoken/BGE tokenizer 差异量化
- [x] `scripts/analyze_tokenizer_diff.py` 可运行，支持 `--input_dir` 参数
- [x] 脚本输出包含：总 chunk 数、两种 tokenizer 的 token 数分布（min/max/mean/median）、超出 BGE 512 的 chunk 数和占比
- [x] 无 JSONL 数据时脚本不崩溃，输出提示信息
- [x] 结论明确：是否需要调整 chunk_size 或切换 tokenizer

## RF-013 — chunk_id 命名规范化
- [x] `src/chunker.py` 生成的 chunk_id 格式为 `{source_name}::chunk::{index:03d}`
- [x] `src/semantic_chunker.py` 生成的 chunk_id 格式为 `{source_name}::chunk::{index:03d}`
- [x] `_parse_chunk_id` 能正确解析新格式 `::chunk::` 分隔的 chunk_id
- [x] `_parse_chunk_id` 能向后兼容解析旧格式 `_` 分隔的 chunk_id
- [x] 含下划线的文件名（如 `2023年度报告_英文版_`）不再产生解析歧义
- [x] `tests/test_chunker.py` 中 chunk_id 格式断言已更新
- [x] `tests/test_metrics.py` 中增加了 `_parse_chunk_id` 新旧格式测试
- [x] 其他测试文件中硬编码的旧格式 chunk_id 已更新
- [x] 所有现有测试通过

## RF-014 — normalize_source 匹配精度提升
- [x] `normalize_source("annual_reports/2025/贵州茅台.md", include_parent=True)` 返回 `"2025/贵州茅台"`
- [x] `normalize_source("贵州茅台.md", include_parent=True)` 返回 `"贵州茅台"`
- [x] `normalize_source("annual_reports/2025/贵州茅台.md", include_parent=False)` 返回 `"贵州茅台"`（旧行为）
- [x] `normalize_source_with_equivalence` 正确传递 `include_parent` 参数
- [x] `eval/metrics/retrieval.py` 调用 `normalize_source` 时传递 `include_parent`
- [x] `eval/metrics/dedup.py` 调用 `normalize_source` 时传递 `include_parent`
- [x] `config.yaml` 的 evaluation 段增加了 `normalize_source_include_parent` 配置项
- [x] `tests/test_metrics.py` 增加了含父目录的测试用例
- [x] 所有现有测试通过

## INV-010 — 元数据增强
- [x] `src/parser.py` 输出的 MD 文件包含 `<!-- page: N -->` 页码标记
- [x] `src/chunker.py` 每个 chunk 的 metadata 包含 `page_start`、`page_end`、`headings` 字段
- [x] `src/semantic_chunker.py` 同步增加了元数据增强
- [x] 无页码标记的旧 MD 文件兼容处理（page_start/page_end 为 None）
- [x] `tests/test_parser.py` 增加了页码标记测试
- [x] `tests/test_chunker.py` 增加了元数据测试
- [x] 所有现有测试通过

## OPT-007 — 基线 chunk_overlap 非零优化
- [x] `exp_configs/experiments/overlap_comparison.yaml` 可正常运行
- [x] `config.yaml` 中 `chunker.chunk_overlap` 已更新为实验推荐值
- [x] overlap 参数变更不破坏现有测试

## 全局
- [x] `pixi run lint` 通过
- [x] `pixi run test` 全部通过
