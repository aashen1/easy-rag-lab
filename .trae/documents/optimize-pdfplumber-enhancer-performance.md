# 优化 PdfPlumberEnhancer 解析性能

## 背景

Profiling 实验表明，开启 pdfplumber 表格补强后解析时间平均增加 **104%**（翻倍），每页额外开销约 0.216 秒。核心瓶颈是 `enhance()` 方法在**每一页**都调用 `_extract_tables()`，而后者每次都执行 `pdfplumber.open(pdf_path)` 重新打开 PDF 文件。

## 优化方案

### 优化 1：只打开 PDF 一次（主要收益）

**现状**：`_extract_tables(pdf_path, page_idx)` 每次调用都 `pdfplumber.open(pdf_path)`，一个 28 页 PDF 就打开/关闭 28 次。

**改法**：
- 在 `enhance()` 入口处一次性打开 pdfplumber PDF 对象
- 新增私有方法 `_extract_all_tables(pdf_path, page_count)` → 返回 `dict[int, list[str]]`（page_idx → tables）
- 在 `enhance()` 中查字典取表格，而非逐页打开文件
- 删除旧的 `_extract_tables(self, pdf_path, page_idx)` 方法

**预期收益**：消除重复文件 I/O 和 PDF 解析开销，预计可降低 40-60% 的增强时间。

### 优化 2：跳过不可能有表格的页面

**现状**：对每一页都调用 `find_tables()`，即使该页是纯文字。

**改法**：
- 在 `enhance()` 循环中，先检查主解析器输出中是否有 markdown 表格（`_find_md_table_spans`）
- 如果该页**没有** markdown 表格，且文本内容很短（如 < 50 字符），跳过 pdfplumber 提取
- 对于有 markdown 表格的页面，仍然执行 pdfplumber 提取（用于替换/增强）
- 对于没有 markdown 表格但文本较长的页面，仍执行 pdfplumber 提取（因为可能存在主解析器遗漏的表格）

**注意**：这个优化需要谨慎——不能漏掉主解析器未能识别的表格。所以只跳过"短文本且无表格"的页面，这是最安全的策略。

**预期收益**：对于年报摘要等文档，很多页面是纯文字，可减少 30-50% 的 `find_tables()` 调用。

### 优化 3：更新测试

现有测试通过 monkey-patch `_extract_tables` 方法来注入 mock 数据。优化 1 会删除 `_extract_tables`，需要：
- 更新 `TestEnhanceAppendMode` 和 `TestNoDuplicateTables` 中的 mock 方式
- 新增 `_extract_all_tables` 的 mock 注入点
- 确保所有现有测试用例通过

## 实施步骤

1. **修改 `PdfPlumberEnhancer`**：
   - 新增 `_extract_all_tables(self, pdf_path, page_count) -> dict[int, list[str]]`
   - 重写 `enhance()` 方法：一次性提取所有页表格 → 查字典 → 后续逻辑不变
   - 删除旧的 `_extract_tables(self, pdf_path, page_idx)` 方法
   - 在 `enhance()` 中加入短文本页跳过逻辑

2. **更新测试**：
   - 修改 `tests/test_parsers_fitz_pdfplumber.py` 中所有 monkey-patch `_extract_tables` 的地方
   - 改为 monkey-patch `_extract_all_tables`，返回 `{0: [...]}` 格式
   - 新增测试：验证短文本页跳过逻辑
   - 新增测试：验证 `_extract_all_tables` 的正常行为

3. **运行 profiling 验证**：
   - 用 `scripts/profile_table_enhancement.py` 重新跑 benchmark
   - 对比优化前后的时间数据

4. **运行全量测试**：
   - `pixi run test` 确保无回归

## 文件变更清单

| 文件 | 变更类型 |
|------|----------|
| `src/parsers/pdfplumber_enhancer.py` | 重写 `enhance()` + 新增 `_extract_all_tables()` + 删除 `_extract_tables()` |
| `tests/test_parsers_fitz_pdfplumber.py` | 更新 mock 方式 + 新增测试用例 |
