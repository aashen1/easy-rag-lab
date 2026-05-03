# 全面优化表格补强逻辑

## 背景

当前 `PdfPlumberEnhancer` 的 `better_wins` 策略仅比较 `data_rows`（数据行数）一个维度来决定是否替换原始表格，存在以下问题：

1. **质量判断过于简单**：只看行数，忽略了空单元格率、合并单元格等关键质量指标
2. **默认保留原始结果**：当质量难以判断时，当前逻辑保留原始表格，但用户要求默认使用补强结果
3. **合并单元格无法检测**：pymupdf4llm 输出的表格中，合并单元格常以 `<br>` 标签分隔多个值的形式出现，这是低质量的明确信号，但当前无法识别

## 目标

1. **无重复**：最终结果中每个表格只出现一次，不会同时出现原始和补强两种版本
2. **质量优先**：最终保留的是两种方式中质量较好的版本
3. **默认补强**：当质量难以判断时，默认使用补强（pdfplumber）的结果

## 实现步骤

### Step 1: 扩展质量度量 — 新增合并单元格检测

在 `_count_table_quality()` 中新增 `merged_ratio` 指标。

**合并单元格的检测逻辑**：
- pymupdf4llm 输出的 Markdown 表格中，合并单元格表现为一个单元格内包含 `<br>` 标签（如 `| 茅台<br>五粮液<br>泸州老窖 |`）
- 这种 `<br>` 标签意味着多个本应独立的值被挤在了一个单元格里，是表格解析质量差的明确信号

修改 `_count_table_quality()` 返回值从 `tuple[int, int, int, float]` 扩展为 `tuple[int, int, int, float, float]`，新增第5个元素 `merged_ratio`（含 `<br>` 的单元格数 / 总单元格数）。

**文件**：`src/parsers/pdfplumber_enhancer.py`

**具体改动**：
- `_count_table_quality()` 方法：遍历每个单元格，检测是否包含 `<br>` 标签，计算 merged_ratio
- 返回 `(total_rows, col_count, data_rows, empty_ratio, merged_ratio)`

### Step 2: 实现综合质量比较方法 `_is_better_quality()`

替换当前 `_replace_tables()` 中的简单 `data_rows > data_rows` 比较。

**比较逻辑**（按优先级）：

```
def _is_better_quality(self, orig_md, plumber_md) -> bool:
    """判断 plumber 表格是否比原始表格质量更好。

    Returns:
        True 表示应使用 plumber 版本，False 表示保留原始版本。
    """
    orig_q = self._count_table_quality(orig_md)   # (rows, cols, data_rows, empty_ratio, merged_ratio)
    plumber_q = self._count_table_quality(plumber_md)

    # 1. 原始表格有合并单元格（merged_ratio > 0），plumber 没有 → plumber 胜
    if orig_q[4] > 0 and plumber_q[4] == 0:
        return True

    # 2. plumber 表格有合并单元格，原始没有 → 原始胜
    if plumber_q[4] > 0 and orig_q[4] == 0:
        return False

    # 3. 空单元格率差异显著（>15pp）→ 空单元格率低的胜
    if abs(orig_q[3] - plumber_q[3]) > 0.15:
        return plumber_q[3] < orig_q[3]

    # 4. 数据行数差异显著（>30%）→ 行数多的胜
    if orig_q[2] > 0 and plumber_q[2] > 0:
        row_diff = abs(plumber_q[2] - orig_q[2]) / max(orig_q[2], plumber_q[2])
        if row_diff > 0.3:
            return plumber_q[2] > orig_q[2]

    # 5. 质量难以判断 → 默认使用 plumber（补强结果）
    return True
```

**设计要点**：
- 合并单元格是最强的质量信号，优先级最高
- 空单元格率差异 >15 个百分点才算"显著"
- 数据行数差异 >30% 才算"显著"，避免因1-2行差异就切换
- 默认使用 plumber 结果，符合用户"如果不好判断就默认使用补强"的要求

### Step 3: 更新 `_replace_tables()` 使用新比较方法

将 `_replace_tables()` 中的比较逻辑：

```python
# 旧逻辑
should_replace = plumber_quality[2] > orig_quality[2]

# 新逻辑
should_replace = self._is_better_quality(original_tables[span_idx], plumber_md)
```

同时更新 `_filter_low_quality()` 方法，适配 `_count_table_quality()` 的新返回值格式（5元组）。

### Step 4: 确保无重复表格

当前逻辑已经基本保证无重复（`_replace_tables()` 中要么替换要么保留原始，不会两者都出现），但需验证以下场景：

1. **原始有表格、plumber 也有表格**：`_replace_tables()` 逐一替换或保留 → ✅ 无重复
2. **原始无表格、plumber 有表格**：`_append_tables()` 追加 → ✅ 无重复
3. **plumber 多出的表格**：追加到文末 → 需确认这些"多出的表格"不会与原始文本中的非表格内容重复

对于场景3，当前逻辑直接追加，可能存在 plumber 表格与原始文本中的表格数据（非 Markdown 格式）重复的问题。但由于原始文本中的非 Markdown 表格数据很难精确检测和去重，这个问题暂不处理，作为已知限制记录。

### Step 5: 编写测试

新增测试类 `TestQualityComparison`，覆盖以下场景：

1. **合并单元格检测**：含 `<br>` 的表格 merged_ratio > 0
2. **合并单元格 → plumber 胜**：原始有合并单元格，plumber 没有
3. **plumber 有合并单元格 → 原始胜**：plumber 有合并单元格，原始没有
4. **空单元格率差异显著**：一方空单元格率远高于另一方
5. **数据行数差异显著**：一方行数远多于另一方
6. **质量相近 → 默认 plumber**：两者质量指标接近时，选择 plumber
7. **无重复表格**：验证最终结果中不会同时出现原始和 plumber 版本

**文件**：`tests/test_parsers_fitz_pdfplumber.py`（在现有文件中追加测试类）

### Step 6: 运行测试和 lint

- `pixi run test-unit` 确保所有单元测试通过
- `pixi run lint` 确保代码风格合规

## 影响范围

| 文件 | 改动类型 |
|------|----------|
| `src/parsers/pdfplumber_enhancer.py` | 核心改动：质量度量扩展、比较逻辑重写 |
| `tests/test_parsers_fitz_pdfplumber.py` | 新增测试类 |

**不改动**的文件：
- `base.py`：接口不变
- `composite_parser.py`：调用方式不变
- `config.yaml`：配置项不变（`replace_policy: "better_wins"` 语义增强，无需改配置）
- `fitz_pdfplumber_parser.py`：无变化

## 风险与注意事项

1. **`_count_table_quality()` 返回值变更**：从4元组变为5元组，需确保所有调用点适配
2. **默认行为变更**：`better_wins` 在质量相近时从"保留原始"变为"使用 plumber"，这是有意为之的行为变更
3. **`<br>` 检测的局限性**：仅检测 Markdown 中的 `<br>` 标签，无法检测其他形式的合并单元格表现（如 pdfplumber 的 `None` 值）
