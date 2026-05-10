# 实验计划：确定最佳默认 PDF 解析链路

## 目标

通过抽样实验，确定最佳默认解析管线配置，并更新 `config.yaml`。

## 已有知识（无需重新验证）

| 结论 | 来源 | 数据 |
|------|------|------|
| OCR 应关闭 | OCR 对比实验 | 解析耗时 -63.2%, Faithfulness +4.8% |
| pymupdf4llm Layout 模式下 `table_strategy` 不生效 | 参数精调调研 | 参数被静默忽略 |
| 合并单元格表格是解析最大短板 | Bad Case 分析 | 香飘飘收盘价检索完全失败 |
| 两步法架构（CompositeParser）已就绪 | 代码实现 | primary + enhancer 组合 |

## 候选管线（6 种，全部 OCR 关闭）

| # | 管线名称 | 主力解析器 | 表格增强器 | 说明 |
|---|---------|-----------|-----------|------|
| 1 | pymupdf4llm_pure | pymupdf4llm | null | 当前默认（但 OCR 改为 off） |
| 2 | pymupdf4llm_pdfplumber_lines | pymupdf4llm | pdfplumber(lines) | 有边框表格增强 |
| 3 | pymupdf4llm_pdfplumber_text | pymupdf4llm | pdfplumber(text) | 无边框表格增强 |
| 4 | fitz_pure | fitz | null | 纯 fitz，无表格 |
| 5 | fitz_pdfplumber_lines | fitz | pdfplumber(lines) | fitz + 有边框表格 |
| 6 | fitz_pdfplumber_text | fitz | pdfplumber(text) | fitz + 无边框表格 |

## 抽样策略

- **总量**: 209 个 PDF（112 年报 + 97 研报）
- **抽样率**: 5%（≈10 个 PDF）
- **分层抽样**: 年报 5 个 + 研报 5 个
- **必选**: 食品饮料行业ETF周报（bad case PDF）
- **总计**: 11 个 PDF

抽样方法：从每个子目录中随机选取，确保覆盖不同年份、不同公司、不同文档类型。

## 实验步骤

### Step 1: 创建实验配置

创建 `parser_configs/default_pipeline_eval.yaml`，包含：
- 6 种管线定义（全部 `use_ocr: false`）
- 11 个测试 PDF 路径（10 个抽样 + 1 个必选 bad case）
- 输出目录 `data/parser_reports`

### Step 2: 运行 Parser Benchmark

```bash
pixi run python eval/run_parser_benchmark.py --config parser_configs/default_pipeline_eval.yaml
```

Benchmark 会自动：
- 对每个 PDF × 每个管线运行解析
- 计算结构质量指标（表格数、空单元率、标题数、有效页比例等）
- 记录解析耗时
- 保存解析样本到 `parsed_samples/` 目录
- 生成对比报告 `report.md`

### Step 3: 重点分析 bad case PDF

对食品饮料ETF周报的解析结果进行专项检查：
- 查看第 14 页表格是否正确展开（而非 `<br>` 堆叠）
- 检查"香飘飘"与"13.04"是否在同一行/同一单元格
- 比较各管线在该 PDF 上的表格质量指标

### Step 4: 综合评估与决策

评估维度（按优先级）：

1. **表格质量**（权重最高）
   - 表格数量：更多表格 = 更完整的结构识别
   - 空单元率：越低越好（数据完整性）
   - 行列数合理性：反映表格是否正确展开

2. **文本完整性**
   - 字符数/词数：不应显著低于其他管线
   - 有效页比例：不应有空白页

3. **结构保真度**
   - 标题数量：合理的标题层级

4. **性能**
   - 解析耗时：在质量相当的情况下选更快的

5. **Bad case 表现**
   - 食品饮料ETF周报的表格解析质量必须可接受

### Step 5: 更新默认配置

根据实验结论更新 `config.yaml`：
- `parser.primary`: 最佳主力解析器
- `parser.table_enhancer`: 最佳表格增强器（或 null）
- `parser.pymupdf4llm.use_ocr`: false（已有实验证据）
- 对应的子配置参数

### Step 6: 验证

- 用新默认配置重新解析 bad case PDF，确认表格质量改善
- 运行 `pixi run test-unit` 确保不破坏现有功能

## 快速决策原则

- 如果 3% 抽样就能明确得出结论（某管线在所有维度都显著领先），立即停止
- 如果结论模糊，扩大到 10% 抽样重新运行
- 重点关注表格质量差异，这是当前最大痛点

## 预期结论

基于已有知识，最可能的赢家是 **pymupdf4llm + pdfplumber(text)**：
- pymupdf4llm 的 Layout 模式在多栏检测、文本提取上优于 fitz
- pdfplumber(text) 策略适合金融研报中常见的无边框/半边框表格
- text 策略比 lines 策略对金融文档更通用（很多表格没有完整边框线）

但需要实验数据验证，特别是：
- pdfplumber 增强是否会误检测非表格区域
- fitz + pdfplumber 是否在某些文档类型上表现更好
- 性能开销是否可接受
