# 日志问题排查与修复计划

## 日志概览

`app_2026-05-05.log` 中共发现 **1 条 ERROR** 和 **约 100 条 WARNING**。经逐一核对源码，大部分 WARNING 是测试用例产生的预期行为，但存在 **5 个真实 bug/不一致** 和 **4 个设计改进点**。

---

## 一、需要修复的 Bug / 不一致（Priority 1）

### Bug 1: `sampler.py:62` — docstring 与实际抛出异常不一致

- **现状**: `count_pdf_pages` 的 docstring 写 `Raises: Exception`，但实际抛出 `ParsingError`
- **影响**: 误导调用方和文档读者
- **修复**: 将 docstring 修正为 `Raises: ParsingError`

### Bug 2: `sampler.py:111-113` — pages 模式全失败静默返回空列表

- **现状**: 当所有 PDF 都不可读时，`determine_sample` 返回空列表 `[]`；但当输入 `pdf_files` 为空时，抛出 `ConfigurationError`
- **影响**: 行为不一致。下游收到空列表可能空转，难以排查
- **修复**: 当 `pdf_page_counts` 为空时，抛出 `ConfigurationError("No PDFs could be read for page-based sampling")`，与空输入行为一致

### Bug 3: `document_loader.py:134-135` — 打印 `None` 无诊断价值

- **现状**: `resolve_chunks_dir` 返回 `None` 后，`load_document_chunks` 打印 `Chunks directory not found: None`
- **影响**: 无法区分"chunks_dir 未解析到"和"chunks_dir 有值但路径不存在"
- **修复**: 拆分为两个分支：
  ```python
  if not chunks_path:
      logger.warning("Chunks directory could not be resolved")
  elif not chunks_path.exists():
      logger.warning(f"Chunks directory does not exist: {chunks_path}")
  ```

### Bug 4: `document_loader.py:62-65` — resolve_chunks_dir 警告信息不足

- **现状**: WARNING 只打印 `data_id`，不打印 `config_hashes`、`chunker_hash`、计算出的路径
- **影响**: 无法区分三种触发原因（data_id 为空 / config_hashes 缺 chunker / 路径不存在）
- **修复**: 增加诊断信息，在 warning 中打印 `config_hashes` 和计算出的 `chunks_dir` 路径

### Bug 5: `test_set_manager.py:865-867` — 空 source_files 的非 irrelevant 问题被静默放行

- **现状**: 非 `irrelevant` 类型的问题如果 `source_files` 为空列表，直接放行不告警
- **影响**: 数据质量问题（无来源文档的问题）被静默接受
- **修复**: 对非 `irrelevant` 类型且 `source_files` 为空的问题，增加 WARNING 日志

---

## 二、设计改进（Priority 2）

### 改进 1: `testset_composer.py:100-101` — 过滤零结果警告缺少条件信息

- **现状**: `Filter returned zero questions` 没有打印过滤条件
- **修复**: 在 warning 中加入过滤条件：`f"Filter returned zero questions. Filters: types={question_types}, categories={categories}, difficulties={difficulties}"`

### 改进 2: `evaluation.py:379-381` — 串行路径跳过问题无审计记录

- **现状**: 串行版本用 `continue` 直接跳过空文本问题；并发版本返回 `{"_skip": True}` 记录
- **修复**: 串行版本也返回 `_skip` 记录，保持两条路径行为一致

### 改进 3: `semantic_chunker.py:416` / `chunk.py:99` — 调用方应提前检查空文本

- **现状**: 两个调用方（`process_parsed_files_semantic` 和 `chunk_parsed`）在调用 `chunk_text_semantic` 前不检查空文本
- **影响**: 产生不含文件名的 WARNING，难以定位
- **修复**:
  - `process_parsed_files_semantic`: 读取文件后检查 `text.strip()`，为空则跳过并记录文件名
  - `chunk_parsed`: 拼接后检查 `full_text.strip()`，为空则提前返回空列表

### 改进 4: `asset_verifier.py:155-197` — meal_snapshot.json 被解析两次

- **现状**: 第 136 行和第 158 行分别打开并解析 `meal_snapshot.json`
- **影响**: 冗余 IO；如果第一次解析失败，第二次仍会重复失败
- **修复**: 第一次解析成功后缓存结果，PDF 验证阶段直接复用

---

## 三、日志质量优化（Priority 3，可选）

### 优化 1: `validators.py:977` — 幻觉检测警告增加上下文

- 在 WARNING 中加入文档名和 segment 总数，帮助判断是 chunk 边界问题还是真正的幻觉

### 优化 2: `metric_resolver.py` — 消除重复 WARNING

- `validate()` 和 `_resolve_priority_fallback()` 对同一指标可能输出两条 WARNING
- 建议 `_resolve_priority_fallback` 中降为 DEBUG，由 `validate()` 统一输出汇总 WARNING

---

## 四、预期行为，无需修复

| 模块 | WARNING | 原因 |
|------|---------|------|
| experiment_reuse | Fingerprint mismatch / hash mismatch / mode ignored | 信息性提示，防御性设计 |
| generator | No adjacent/non-adjacent chunks / Failed to generate | 数据不足或 LLM 生成失败，有补充机制兜底 |
| generator | ground_truth_excerpt not found / Answer-evidence inconsistency | LLM 幻觉检测，质量守门机制 |
| asset_verifier | Invalid manifest / JSON decode error / SHA256 mismatch | 资产验证的正常发现 |
| chunk_locator | Chunks directory not found (deprecated) | 已废弃函数，应迁移到新 API |
| sampler | ERROR: Failed to count pages in bad.pdf | 测试用例故意传入损坏文件，错误处理正确 |

---

## 实施步骤

1. 修复 Bug 1-5（Priority 1）
2. 实施改进 1-4（Priority 2）
3. （可选）实施优化 1-2（Priority 3）
4. 运行 `pixi run test-unit` 确认无回归
5. 运行 `pixi run lint` 确认代码质量
