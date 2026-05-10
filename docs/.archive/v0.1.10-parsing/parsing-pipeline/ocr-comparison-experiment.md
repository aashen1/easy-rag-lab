# OCR 对比实验方案

## 目标

控制变量：只改 OCR 开关（开→关），保持同一套 PDF 文件，对比性能差异。

## 核心问题分析

### 缓存机制的三层隔离

系统设计已经天然支持不同配置的缓存隔离：

```
data/artifacts/
  {data_id[:12]}/                    ← 按 PDF 文件集合分组
    parsed_{parser_hash}/            ← 解析结果按 parser hash 隔离
    chunks_{chunker_hash}/           ← 分块结果按 chunker hash 隔离

data/vector_store/
  collection m_{index_key[:12]}      ← 向量索引按 index_key 隔离
```

- **data_id** 由 PDF 文件的 SHA-256 哈希决定，与配置无关 → **同一套 PDF = 同一 data_id**
- **parser_hash** 由 parser 配置（含 OCR 设置）决定 → **OCR 开/关 = 不同 parser_hash**
- **index_key** = hash(data_id + parser_hash + chunker_hash + embedding_hash) → **任一配置变化 = 不同 index_key**

### 结论：**不存在缓存污染风险**

关闭 OCR 后，parser_hash 会变化，系统会自动使用新的缓存路径：
- 旧解析结果：`parsed_e936d3e3/`（OCR 开）
- 新解析结果：`parsed_{新hash}/`（OCR 关）

旧的 `parsed_e936d3e3/` 目录完全不受影响。

### Meal 复用问题

现有 meal `1kpage` 的 manifest 中记录了 `config_hashes.parser = "e936d3e3"`（OCR 开）。
如果直接复用这个 meal，系统会认为解析结果已存在，不会重新解析。

**解决方案**：创建新 meal（如 `1kpage_no_ocr`），使用相同的 seed=42 采样，确保 PDF 文件集合一致。

由于 `determine_sample()` 使用 `random.seed(42)` 控制采样，相同 seed + 相同 PDF 目录 = 相同采样结果 = 相同 data_id。

## 实施方案

### Step 1：创建新实验配置

创建 `exp_configs/baseline/baseline_1kpage_no_ocr.yaml`：

```yaml
name: "baseline-1kpage-no-ocr"
description: "1000页PDF性能评估实验 - OCR关闭对比"

data:
  meal: "1kpage_no_ocr"           # 新 meal 名称
  create_if_missing:
    sample_pages: 1000
    seed: 42                       # 与 1kpage 相同的 seed，确保同一套 PDF

test_sets:
  - name: "baseline_test_1kpage_no_ocr"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 10
      seed: 42                     # 与 1kpage 相同的 seed，确保同一套问题

variants:
  - name: "baseline"
    description: "基线配置 (chunk_size: 512, chunk_overlap: 0, OCR关闭)"
    config_overrides: {}

evaluation:
  llm_preset: "default"
  llm_report: false
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
      - "chunk_hit_rate"
      - "chunk_mrr"
      - "chunk_ndcg"
      - "dedup_hit_rate"
      - "dedup_mrr"
      - "dedup_ndcg"
      - "false_positive_rate"
    generation:
      - "faithfulness"
      - "answer_relevancy"

llm:
  question_generation: "default"
  answering: "default"
```

### Step 2：修改 config.yaml 关闭 OCR

将 `config.yaml` 中的 OCR 设置改为 `false`：

```yaml
parser:
  pymupdf4llm:
    use_ocr: false     # 原来是 true
    # ocr_language: chi_sim+eng  # OCR 关闭后不需要
```

### Step 3：运行实验

```bash
pixi run exp baseline/baseline_1kpage_no_ocr
```

系统会自动：
1. 创建新 meal `1kpage_no_ocr`，使用 seed=42 采样 → **同一套 PDF**
2. 计算新的 parser_hash（因 OCR 关闭，hash 不同）
3. 在 `data/artifacts/7f0264494ae5/parsed_{新hash}/` 创建新的解析结果
4. 复用相同的 chunks（chunker 配置未变，chunker_hash 相同）
5. 创建新的 Qdrant collection（index_key 不同）

### Step 4：恢复 OCR 配置

实验完成后，将 `config.yaml` 恢复为 `use_ocr: true`。

### Step 5：对比分析

对比两次实验的 profiling 报告：
- `exp_20260425_034425_baseline_1kpage/`（OCR 开）
- `exp_{timestamp}_baseline_1kpage_no_ocr/`（OCR 关）

## 缓存安全性验证

| 场景 | 旧缓存 | 新缓存 | 是否冲突 |
|------|--------|--------|---------|
| 解析结果 | `parsed_e936d3e3/` | `parsed_{新hash}/` | ✅ 不同目录 |
| 分块结果 | `chunks_4fdf68a4/` | `chunks_4fdf68a4/` | ✅ 相同目录，配置未变 |
| 向量索引 | `m_cc7a1b93ca1a` | `m_{新key}/` | ✅ 不同 collection |
| Meal 配置 | `1kpage/manifest.json` | `1kpage_no_ocr/manifest.json` | ✅ 不同 meal |
| 测试集 | `baseline_test_1kpage.json` | `baseline_test_1kpage_no_ocr.json` | ✅ 不同文件 |

**结论：完全安全，旧缓存不受影响，新实验使用独立缓存路径。**

## 预期结果

| 指标 | OCR 开 | OCR 关 | 预期变化 |
|------|--------|--------|---------|
| S1 PDF解析 | 412.35s | ~100-150s | -65~75% |
| 解析质量 | OCR 增强文本 | 仅原生文本 | 可能略降 |
| 总耗时 | 526.46s | ~200-250s | -50~60% |
| 内存 | ~1.9GB | ~1.9GB | 基本不变 |

## 注意事项

1. **OCR 关闭后解析质量可能下降**：对于扫描件 PDF，关闭 OCR 后可能无法提取文本
2. **测试集不同**：虽然 seed 相同，但测试集名称不同，会重新生成问题。如果需要完全相同的问题，可以手动复制测试集文件
3. **config.yaml 需要手动恢复**：实验完成后记得将 OCR 改回 true
