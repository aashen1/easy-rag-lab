# Plan: Stream 2 — 分块层 + 指标工具层 Issue 链修复

## 概述

本计划解决 Stream 2 的 5 个 issue，按依赖顺序执行：

1. **INV-015** — tiktoken/BGE tokenizer 差异量化（调研）
2. **RF-013** — chunk_id 命名规范化
3. **RF-014** — normalize_source 匹配精度提升
4. **INV-010** — 元数据增强（PDF 页码 + MD 标题层级）
5. **OPT-007** — 基线 chunk_overlap 非零优化

---

## Step 1: INV-015 — tiktoken 与 BGE tokenizer 差异量化

### 目标
量化 tiktoken cl100k_base 与 BGE WordPiece tokenizer 对同一文本的 token 计数差异，判断当前 chunk_size=512 (tiktoken) 是否导致 BGE 向量化时截断。

### 实现方案
创建分析脚本 `scripts/analyze_tokenizer_diff.py`：
1. 读取现有 chunks JSONL 文件（从 `data/chunks/` 或 `data/artifacts/`）
2. 对每个 chunk 的 text 字段，分别用 tiktoken cl100k_base 和 BGE tokenizer 计数
3. 输出统计报告：每个 chunk 的两种 token 数、比例、超出 512 BGE token 的 chunk 数量和占比
4. 如果差异显著（如 >10% 的 chunk 超出 BGE 512 token），在报告中给出建议

### 涉及文件
- **新建**：`scripts/analyze_tokenizer_diff.py`
- **只读**：`src/embedder.py`（参考 BGE tokenizer 加载方式）、`src/chunker.py`（参考 tiktoken 使用方式）

### 验收标准
- 脚本可运行，输出包含：总 chunk 数、两种 tokenizer 的 token 数分布（min/max/mean/median）、超出 BGE 512 的 chunk 数和占比
- 结论明确：是否需要调整 chunk_size 或切换 tokenizer

### 注意
- 此步骤为纯调研，不修改任何现有代码
- 如果项目 `data/` 下无 chunks 数据，脚本应支持指定任意 JSONL 目录

---

## Step 2: RF-013 — chunk_id 命名规范化

### 目标
将 chunk_id 格式从 `{source_name}_{chunk_index:03d}` 改为 `{source_name}::chunk::{chunk_index:03d}`，使用 `::chunk::` 作为分隔符，彻底消除文件名含下划线时的解析歧义。

### 当前问题
- `chunk_id = f"{source_name}_{chunk['metadata']['chunk_index']:03d}"` （[chunker.py:178](file:///b:/project/w1-easy-rag/src/chunker.py#L178)）
- `_parse_chunk_id` 使用 `rfind("_")` 分割（[metrics/utils.py:72](file:///b:/project/w1-easy-rag/eval/metrics/utils.py#L72)）
- 文件名如 `贵州茅台2023年年度报告_英文版_` 含下划线，导致 `rfind("_")` 可能截断 doc_stem

### 实现方案

#### 2a. 修改 chunk_id 生成格式
- **`src/chunker.py:178`**：`chunk_id = f"{source_name}::chunk::{chunk['metadata']['chunk_index']:03d}"`
- **`src/semantic_chunker.py:409`**：同上，保持一致

#### 2b. 修改 _parse_chunk_id 解析逻辑
- **`eval/metrics/utils.py:57-81`**：重写为按 `::chunk::` 分割
```python
def _parse_chunk_id(chunk_id: str) -> tuple:
    separator = "::chunk::"
    if separator in chunk_id:
        parts = chunk_id.split(separator)
        doc_stem = parts[0]
        try:
            chunk_index = int(parts[1])
            return (doc_stem, chunk_index)
        except (ValueError, IndexError):
            return (chunk_id, -1)
    # 向后兼容：旧格式 {doc_stem}_{index:03d}
    last_underscore = chunk_id.rfind("_")
    if last_underscore == -1:
        return (chunk_id, -1)
    doc_stem = chunk_id[:last_underscore]
    suffix = chunk_id[last_underscore + 1:]
    try:
        chunk_index = int(suffix)
        return (doc_stem, chunk_index)
    except ValueError:
        return (chunk_id, -1)
```

#### 2c. 更新测试
- **`tests/test_chunker.py:162-179`**：`test_process_parsed_files_chunk_id_format` 断言更新为 `::chunk::` 格式
- **`tests/test_metrics.py`**：增加 `_parse_chunk_id` 新格式测试 + 旧格式向后兼容测试
- **其他测试文件**中硬编码的 chunk_id（如 `test_bm25_retriever.py`、`test_test_generator.py`、`test_run_experiment.py`、`test_evaluators.py`、`test_regression.py`）逐步更新为新格式

#### 2d. 向后兼容
- `_parse_chunk_id` 同时支持新旧格式（新格式优先，旧格式 fallback）
- 已有的 Qdrant 索引和 JSONL 文件中的旧格式 chunk_id 仍可被正确解析
- 新生成的 chunk 使用新格式

### 涉及文件
| 文件 | 改动类型 |
|------|----------|
| `src/chunker.py` | 修改 chunk_id 生成格式 |
| `src/semantic_chunker.py` | 修改 chunk_id 生成格式 |
| `eval/metrics/utils.py` | 重写 _parse_chunk_id |
| `tests/test_chunker.py` | 更新断言 |
| `tests/test_metrics.py` | 增加 _parse_chunk_id 测试 |
| `tests/test_bm25_retriever.py` | 更新测试数据中的 chunk_id |
| `tests/test_test_generator.py` | 更新测试数据中的 chunk_id |
| `tests/test_run_experiment.py` | 更新测试数据中的 chunk_id |
| `tests/test_evaluators.py` | 更新测试数据中的 chunk_id |
| `tests/test_regression.py` | 更新测试数据中的 chunk_id |

### 验收标准
- 所有现有测试通过（含旧格式 chunk_id 的向后兼容）
- 新生成的 chunk_id 格式为 `{source_name}::chunk::{index:03d}`
- `_parse_chunk_id` 能正确解析新旧两种格式
- 含下划线的文件名（如 `2023年度报告_英文版_`）不再产生解析歧义

---

## Step 3: RF-014 — normalize_source 匹配精度提升

### 目标
将 `normalize_source` 从纯 stem 匹配提升为"stem + 父目录路径"匹配，避免不同版本/目录的同名文档被误判为同一文档。

### 当前问题
- `normalize_source("annual_reports/2025/贵州茅台.md")` → `"贵州茅台"`
- `normalize_source("annual_reports/2024/贵州茅台.md")` → `"贵州茅台"`
- 两个不同年份的同名文档被归一化为同一标识符

### 实现方案

#### 3a. 增强 normalize_source
- **`eval/metrics/utils.py`**：增加 `normalize_source_v2` 函数，返回 `{parent_dir_stem}/{stem}` 格式
```python
def normalize_source(source: str, include_parent: bool = True) -> str:
    p = Path(source)
    stem = p.stem
    if include_parent and p.parent != Path("."):
        parent_name = p.parent.name
        if parent_name:
            return f"{parent_name}/{stem}"
    return stem
```

#### 3b. 保持向后兼容
- 默认行为不变（`include_parent=True`），但调用方可通过参数控制
- 逐步在各指标函数中启用 `include_parent=True`
- 增加配置项 `evaluation.normalize_source_include_parent`（默认 True），允许回退到旧行为

#### 3c. 更新 normalize_source_with_equivalence
- 内部调用 `normalize_source` 时传递 `include_parent` 参数
- 等价组匹配逻辑相应适配

#### 3d. 更新测试
- `tests/test_metrics.py` 中 `TestNormalizeSource` 增加含父目录的测试用例
- 验证不同目录下同名文档不再被误判

### 涉及文件
| 文件 | 改动类型 |
|------|----------|
| `eval/metrics/utils.py` | 增强 normalize_source |
| `eval/metrics/retrieval.py` | 调用 normalize_source 时传递 include_parent |
| `eval/metrics/dedup.py` | 调用 normalize_source 时传递 include_parent |
| `eval/evaluators/builtin_evaluator.py` | 调用 normalize_source_with_equivalence 时传递 include_parent |
| `config.yaml` | 增加 evaluation.normalize_source_include_parent 配置 |
| `tests/test_metrics.py` | 增加测试 |

### 验收标准
- `normalize_source("annual_reports/2025/贵州茅台.md")` → `"2025/贵州茅台"`（含父目录）
- `normalize_source("贵州茅台.md")` → `"贵州茅台"`（无父目录时不变）
- 所有现有测试通过
- 等价组匹配逻辑正常工作

---

## Step 4: INV-010 — 元数据增强（PDF 页码 + MD 标题层级）

### 目标
在 chunk 元数据中增加 PDF 页码范围和 MD 标题层级信息，改善 chunk 命中逻辑和检索结果的可解释性。

### 实现方案

#### 4a. parser.py 增强：输出页码标记
- **`src/parser.py`**：修改 `parse_pdf()` 使用 pymupdf4llm 的页码分隔功能
- pymupdf4llm 已支持 `page_separators=True`（当前配置已启用），输出中会插入 `-----` 分隔符
- 增强解析逻辑：将页码分隔符替换为结构化标记，如 `<!-- page: 3 -->`
- 在 `parse_all_pdfs()` 的输出中记录每个 PDF 的总页数

#### 4b. chunker.py 增强：记录页码范围和标题层级
- **`src/chunker.py`**：
  - 在 `chunk_text()` 中增加对 `<!-- page: N -->` 标记的识别
  - 在 `process_parsed_files()` 中，为每个 chunk 记录：
    - `page_start`：该 chunk 起始页码
    - `page_end`：该 chunk 结束页码
    - `headings`：该 chunk 包含的 Markdown 标题层级列表（如 `["# 公司概况", "## 主营业务"]`）
  - 这些信息写入 chunk 的 metadata 字典

#### 4c. semantic_chunker.py 同步增强
- **`src/semantic_chunker.py`**：与 chunker.py 保持一致的元数据增强

#### 4d. 更新测试
- 验证含页码标记的 MD 文件能正确提取页码范围
- 验证含标题层级的 MD 文件能正确提取 headings

### 涉及文件
| 文件 | 改动类型 |
|------|----------|
| `src/parser.py` | 增加页码标记输出 |
| `src/chunker.py` | 增加 page_start/page_end/headings 元数据 |
| `src/semantic_chunker.py` | 同步增加元数据 |
| `tests/test_parser.py` | 增加页码标记测试 |
| `tests/test_chunker.py` | 增加元数据测试 |

### 验收标准
- 解析后的 MD 文件包含 `<!-- page: N -->` 标记
- 每个 chunk 的 metadata 包含 `page_start`、`page_end`、`headings` 字段
- 无页码标记的旧 MD 文件兼容处理（page_start/page_end 为 null）
- 所有现有测试通过

---

## Step 5: OPT-007 — 基线 chunk_overlap 非零优化

### 目标
通过对比实验确定合适的非零 chunk_overlap 值，解决当前 overlap=0 导致的跨 chunk 边界信息丢失问题。

### 前置条件
- Step 1 (INV-015) 的结论：确认 chunk_size 是否需要调整
- Step 4 (INV-010) 的元数据增强已就位

### 实现方案

#### 5a. 创建对比实验配置
- **新建**：`exp_configs/experiments/overlap_comparison.yaml`
- 对比 overlap 值：0（基线）、32、64、128
- 其他参数保持基线不变

#### 5b. 在 config.yaml 中更新基线默认值
- 根据 Step 1 的结论和对比实验结果，更新 `chunker.chunk_overlap` 的默认值
- 预期推荐值：64（约为 chunk_size 的 12.5%）

#### 5c. 验证 overlap 对现有指标的影响
- 运行对比实验，观察 hit_rate、mrr、ndcg 在不同 overlap 下的变化
- 确认 overlap > 0 不会导致 chunk 数量暴增

### 涉及文件
| 文件 | 改动类型 |
|------|----------|
| `exp_configs/experiments/overlap_comparison.yaml` | 新建实验配置 |
| `config.yaml` | 更新 chunk_overlap 默认值（实验完成后） |

### 验收标准
- overlap_comparison.yaml 可正常运行
- 对比实验结果记录在实验报告中
- 基线 config.yaml 的 chunk_overlap 更新为实验推荐值
- 所有现有测试通过（overlap 参数变更不应破坏测试）

---

## 执行顺序与依赖关系

```
Step 1 (INV-015)  ──调研结论──→  Step 5 (OPT-007)
                                          ↑
Step 2 (RF-013)  ──chunk_id新格式──→  Step 4 (INV-010)
       ↓                                    ↑
Step 3 (RF-014)  ──────────────────────→  Step 4 (INV-010)
```

- Step 1 独立执行，纯调研
- Step 2 → Step 3 有逻辑依赖（RF-014 的 normalize_source 需要与 RF-013 的新 chunk_id 格式协调）
- Step 4 依赖 Step 2（元数据增强时 chunk_id 已是新格式）和 Step 3（normalize_source 精度提升后，元数据中的 source 字段匹配更准确）
- Step 5 依赖 Step 1（调研结论决定 chunk_size 是否调整）和 Step 4（元数据增强后实验结果更有参考价值）

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| chunk_id 格式变更导致旧数据不兼容 | _parse_chunk_id 同时支持新旧格式，旧数据无需迁移 |
| normalize_source 精度提升可能降低现有 hit_rate | 通过配置项 allow_fallback 控制是否回退旧行为 |
| 元数据增强增加 JSONL 文件体积 | page_start/page_end/headings 字段为可选，无数据时为 null |
| overlap 变更影响基线对比 | 保留 overlap=0 的基线配置用于对比 |
