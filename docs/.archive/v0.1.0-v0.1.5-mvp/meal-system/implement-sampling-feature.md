# 抽样测试功能实施计划

## 问题分析

当前 `--sample-size` 参数仅在 PDF 解析步骤（Step 1）生效，后续的分块（Step 2）和向量化索引（Step 3）各自独立扫描目录，处理磁盘上所有文件，导致抽样被绕过，回退到全量处理。

**根本原因**：各阶段通过文件系统目录解耦通信，每个阶段独立 `rglob` 发现输入文件，不感知上游的抽样决策。

## 解决方案

**核心思路**：在 Pipeline 层统一决定抽样文件集合，将抽样结果以 `source_filter`（源文件过滤集合）的形式贯穿所有下游阶段。

### 抽样模式

| 模式 | CLI 参数 | 说明 | 示例 |
|------|---------|------|------|
| 按文档数 | `--sample-count N` | 随机抽取 N 个 PDF | `--sample-count 10` |
| 按总页数 | `--sample-pages N` | 随机抽取 PDF 直到总页数 ≥ N | `--sample-pages 5000` |
| 按比例 | `--sample-ratio R` | 随机抽取 R 比例的文档 | `--sample-ratio 0.1` |

三个参数互斥，同时指定则报错。

### 数据流

```
Pipeline.build_index(sampling_config)
  │
  ├─ sampler.determine_sample(all_pdfs, sampling_config)
  │    → sampled_pdf_paths: List[Path]
  │
  ├─ Step 1: parse_all_pdfs(pdf_files=sampled_pdf_paths)
  │    → parse_results → 提取 output 路径 → source_filter_md: Set[str]
  │
  ├─ Step 2: process_parsed_files(source_filter=source_filter_md)
  │    → chunk_results → 提取 output 路径 → source_filter_jsonl: Set[str]
  │
  └─ Step 3: indexer.build_index(source_filter=source_filter_jsonl)
       → 仅索引过滤后的 chunks
```

### 关键设计决策

1. **抽样在 Pipeline 层决策**：`RAGPipeline.build_index()` 调用 `sampler.determine_sample()` 确定抽样集合，再传递给各阶段
2. **source_filter 机制**：chunker 和 indexer 接受可选的 `source_filter: Optional[Set[str]]`，仅处理匹配的文件
3. **抽样时自动重建索引**：当抽样激活时，强制 `rebuild=True`，清空向量库后仅索引抽样数据，避免残留旧数据污染检索结果
4. **保留已有数据**：不清除 `data/parsed/` 和 `data/chunks/` 中的已有文件，仅通过 filter 跳过非抽样文件
5. **页数统计使用 fitz**：`pymupdf4llm` 依赖 `pymupdf`（即 `fitz`），无需额外安装依赖

---

## 实施步骤

### Step 1: 创建 `src/sampler.py`

新建抽样逻辑模块：

- `SamplingConfig` dataclass：包含 `mode`（"count" / "pages" / "ratio"）、`value`（int 或 float）
- `determine_sample(pdf_files: List[Path], config: SamplingConfig) -> List[Path]`：
  - count 模式：`random.sample(pdf_files, min(count, len(pdf_files)))`
  - pages 模式：用 `fitz.open()` 统计每个 PDF 页数，随机打乱后贪心选取直到总页数 ≥ 目标值
  - ratio 模式：计算 `ceil(ratio * len(pdf_files))`，再 random.sample
- `count_pdf_pages(pdf_path: Path) -> int`：使用 fitz 统计页数
- 所有公共函数带类型标注和 docstring

### Step 2: 修改 `src/parser.py`

- `parse_all_pdfs()` 签名变更：
  - 移除 `sample_size: Optional[int] = None` 参数
  - 新增 `pdf_files: Optional[List[Path]] = None` 参数
  - 当 `pdf_files` 提供时，直接使用该列表（跳过目录扫描和抽样逻辑）
  - 当 `pdf_files` 为 None 时，保持原有行为（扫描 input_dir 全部 PDF）
- 移除 `parse_all_pdfs` 内部的 `random.sample` 逻辑（抽样职责上移到 sampler）

### Step 3: 修改 `src/chunker.py`

- `process_parsed_files()` 新增参数 `source_filter: Optional[Set[str]] = None`
- 在 `md_files = list(input_path.rglob("*.md"))` 之后，若 `source_filter` 不为 None，则过滤：
  ```python
  if source_filter is not None:
      md_files = [f for f in md_files if str(f.relative_to(input_path)) in source_filter]
  ```
- 记录日志：被过滤掉多少文件

### Step 4: 修改 `src/indexer.py`

- `build_index()` 新增参数 `source_filter: Optional[Set[str]] = None`
- 在 `jsonl_files = list(chunks_path.rglob("*.jsonl"))` 之后，若 `source_filter` 不为 None，则过滤：
  ```python
  if source_filter is not None:
      jsonl_files = [f for f in jsonl_files if str(f.relative_to(chunks_path)) in source_filter]
  ```
- 记录日志：被过滤掉多少文件

### Step 5: 修改 `src/pipeline.py`

- `build_index()` 签名变更：
  - 移除 `sample_size: int = None`
  - 新增 `sampling_config: Optional[SamplingConfig] = None`
- 在 Step 1 之前，调用 `sampler.determine_sample()` 确定抽样文件列表
- 将抽样文件列表传给 `parse_all_pdfs(pdf_files=sampled_pdfs)`
- 从 `parse_results` 提取 output 相对路径构建 `source_filter_md`
- 将 `source_filter_md` 传给 `process_parsed_files(source_filter=...)`
- 从 `chunk_results` 提取 output 相对路径构建 `source_filter_jsonl`
- 将 `source_filter_jsonl` 传给 `indexer.build_index(source_filter=...)`
- 当 `sampling_config` 不为 None 时，强制 `rebuild=True`
- 更新 `__main__` 块的 CLI 参数

### Step 6: 修改 `main.py`

- 替换 `--sample-size` 为三个互斥参数：
  - `--sample-count` (int)
  - `--sample-pages` (int)
  - `--sample-ratio` (float)
- 使用 `argparse.add_mutually_exclusive_group()` 确保互斥
- 将 CLI 参数转换为 `SamplingConfig` 传给 `pipeline.build_index()`

### Step 7: 修改 `eval/run_eval.py`

- 同样替换 `--sample-size` 为三个互斥参数
- `run_evaluation()` 函数中的 `sample_size` 参数保留（用于测试用例抽样，与文档抽样无关）
- `pipeline.build_index()` 调用改用 `sampling_config`

### Step 8: 添加测试

- `tests/test_sampler.py`：
  - 测试 count 模式抽样
  - 测试 pages 模式抽样（mock fitz）
  - 测试 ratio 模式抽样
  - 测试边界条件（sample 大于总数、ratio=0、ratio=1 等）
- 更新 `tests/test_parser.py`：适配 `pdf_files` 参数替代 `sample_size`
- 更新 `tests/test_chunker.py`：测试 `source_filter` 过滤功能

### Step 9: 更新 `config.yaml`

- 无需新增配置项。抽样参数完全通过 CLI 传入，不属于需要持久化的超参数。

---

## 涉及文件清单

| 文件 | 操作 |
|------|------|
| `src/sampler.py` | 新建 |
| `src/parser.py` | 修改 |
| `src/chunker.py` | 修改 |
| `src/indexer.py` | 修改 |
| `src/pipeline.py` | 修改 |
| `main.py` | 修改 |
| `eval/run_eval.py` | 修改 |
| `tests/test_sampler.py` | 新建 |
| `tests/test_parser.py` | 修改 |
| `tests/test_chunker.py` | 修改 |
