# PDF 搜索框修复计划：总数缺漏 + 公司名标签缺失

## 问题分析

### 问题 1：PDF 总数不对 / 有缺漏

**根因**：`st_searchbox` 的 `default_options` 参数被限制为 `pdf_files[:50]`，即只显示前 50 个 PDF。

* `all_meal` 共有 210 个 PDF，但下拉框默认只展示 50 个

* 用户打开下拉框时看到只有 50 个选项，以为其余 PDF 缺失

* 搜索功能本身是搜索全量 `pdf_files` 的，但用户不输入关键词时看不到完整列表

**数据验证**：

* `data/raw/` 下共 210 个 PDF

* `all_meal` manifest.json 中记录了 210 个 PDF（数据完整，无实际缺漏）

* `default_options = [(Path(mf.path).name, mf.path) for mf in pdf_files[:50]]` ← 此处截断

**涉及位置**：

* [qa\_demo.py:386](file:///b:/project/ash-easy-rag/src/app_pages/qa_demo.py#L386) — `default_options = [...pdf_files[:50]]`

* [case\_analyzer.py:272](file:///b:/project/ash-easy-rag/src/app_pages/case_analyzer.py#L272) — `default_pdf_options = [...pdf_options[:50]]`

### 问题 2：公司名标签缺失（重名不可区分）

**根因**：搜索框下拉选项的显示文本只用了文件名 `Path(p).name`，没有附加公司名标签。

* 210 个 PDF 中有 45 个重名文件（8 种重名模式）

* 最严重的情况：`2024年年度报告.pdf` 出现 9 次（格力电器、比亚迪、隆基绿能等 9 家公司）

* 用户在下拉框中看到 9 个一模一样的 "2024年年度报告.pdf"，完全无法区分

* 公司名标签（`🏢 贵州茅台`）只在**选中后**的详情区域显示，不在下拉选项中

**重名统计**：

| 文件名                  | 重复次数 |
| -------------------- | ---- |
| 2024年年度报告.pdf        | 9    |
| 2024年年度报告摘要.pdf      | 9    |
| 2023年年度报告摘要.pdf      | 9    |
| 2023年年度报告.pdf        | 9    |
| 2025年年度报告.pdf        | 6    |
| 2025年年度报告摘要.pdf      | 6    |
| 2023年年度报告\_英文版\_.pdf | 3    |
| 2024年年度报告\_英文版\_.pdf | 2    |

**涉及位置**：

* [qa\_demo.py:374-384](file:///b:/project/ash-easy-rag/src/app_pages/qa_demo.py#L374-L384) — `_search_pdf_files` 返回 `(file_name, mf.path)`

* [qa\_demo.py:386](file:///b:/project/ash-easy-rag/src/app_pages/qa_demo.py#L386) — `default_options` 同样只用 `file_name`

* [case\_analyzer.py:260-270](file:///b:/project/ash-easy-rag/src/app_pages/case_analyzer.py#L260-L270) — `_search_gt_pdfs` 返回 `(name, p)`

* [case\_analyzer.py:272](file:///b:/project/ash-easy-rag/src/app_pages/case_analyzer.py#L272) — `default_pdf_options` 同样只用 `name`

***

## 修复方案

### 修复 1：移除 default\_options 的 50 条截断

将 `pdf_files[:50]` / `pdf_options[:50]` 改为全量传入。`st_searchbox` 是搜索型组件，210 条选项不会造成性能问题（它内部是虚拟化渲染，不会一次性渲染所有 DOM 节点）。

**qa\_demo.py L386**：

```python
# Before
default_options = [(Path(mf.path).name, mf.path) for mf in pdf_files[:50]]
# After
default_options = [(Path(mf.path).name, mf.path) for mf in pdf_files]
```

**case\_analyzer.py L272**：

```python
# Before
default_pdf_options = [(Path(p).name, p) for p in pdf_options[:50]]
# After
default_pdf_options = [(Path(p).name, p) for p in pdf_options]
```

### 修复 2：在下拉选项中附加公司名标签

**核心思路**：利用已有的 `_extract_company_name()` 函数，在搜索结果和默认选项的显示文本中附加公司名。

**显示格式**：`文件名 🏢 公司名`（公司名不存在时只显示文件名）

例如：

* `2023年年度报告.pdf 🏢 贵州茅台`

* `2026年光伏行业分析.pdf`（无公司名，不附加）

#### 2a. qa\_demo.py — `_search_pdf_files` 和 `default_options`

```python
def _search_pdf_files(searchterm: str) -> list[tuple[str, str]]:
    results = []
    for mf in pdf_files:
        file_name = Path(mf.path).name
        if (
            not searchterm
            or searchterm.lower() in file_name.lower()
            or searchterm.lower() in mf.path.lower()
        ):
            company = _extract_company_name(mf.path)
            label = f"{file_name} 🏢 {company}" if company else file_name
            results.append((label, mf.path))
    return results

default_options = []
for mf in pdf_files:
    file_name = Path(mf.path).name
    company = _extract_company_name(mf.path)
    label = f"{file_name} 🏢 {company}" if company else file_name
    default_options.append((label, mf.path))
```

#### 2b. case\_analyzer.py — `_search_gt_pdfs` 和 `default_pdf_options`

case\_analyzer.py 目前没有 `_extract_company_name` 函数。需要将此函数提取为共享工具函数，或在 case\_analyzer.py 中复制一份。

**推荐方案**：将 `_extract_company_name` 提取到共享模块 `src/app_pages/_utils.py`（如已有则复用），两处统一导入。

```python
# src/app_pages/_utils.py (新建或追加)
import re
from pathlib import Path

def extract_company_name(rel_path: str) -> str | None:
    parts = Path(rel_path).parts
    if len(parts) < 3:
        return None
    top_level_categories = {"annual_reports", "research_reports"}
    if parts[0] not in top_level_categories:
        return None
    if re.match(r"^\d{4}$", parts[-2]):
        if len(parts) >= 4:
            return parts[-3]
        return None
    if parts[-2] in top_level_categories:
        return None
    return parts[-2]
```

然后 qa\_demo.py 和 case\_analyzer.py 都从 `_utils` 导入。

#### 2c. 选中后的详情展示保持不变

选中文件后，详情区域仍然使用现有的公司名标签样式（蓝色 span），无需修改。只需确保通过 `mf.path` 匹配到正确的 MealFile 即可（当前逻辑 `next((mf for mf in pdf_files if mf.path == selected), None)` 已经正确）。

***

## 修改文件清单

| 文件                               | 修改内容                                                                                                                               |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `src/app_pages/_utils.py`        | 新建（或追加），提取 `extract_company_name` 公共函数                                                                                             |
| `src/app_pages/qa_demo.py`       | 1. 删除本地 `_extract_company_name`，改为从 `_utils` 导入2. `_search_pdf_files` 返回带公司名的 label3. `default_options` 移除 `[:50]` 截断 + 带公司名 label |
| `src/app_pages/case_analyzer.py` | 1. 从 `_utils` 导入 `extract_company_name`2. `_search_gt_pdfs` 返回带公司名的 label3. `default_pdf_options` 移除 `[:50]` 截断 + 带公司名 label       |

***

## 实施步骤

1. 创建 `src/app_pages/_utils.py`，提取 `extract_company_name` 公共函数
2. 修改 `qa_demo.py`：

   * 删除本地 `_extract_company_name`，改为从 `_utils` 导入

   * 修改 `_search_pdf_files` 返回带公司名的 label

   * 修改 `default_options`：移除 `[:50]` + 带公司名 label
3. 修改 `case_analyzer.py`：

   * 从 `_utils` 导入 `extract_company_name`

   * 修改 `_search_gt_pdfs` 返回带公司名的 label

   * 修改 `default_pdf_options`：移除 `[:50]` + 带公司名 label
4. 运行 `pixi run lint` 验证代码质量
5. 运行 `pixi run test-unit` 验证无回归
6. 启动 `pixi run web` 手动验证搜索框功能

***

## 验收标准

* [ ] 搜索框默认显示全部 PDF（不再截断为 50 条）

* [ ] 重名文件在下拉选项中可通过公司名区分（如 `2023年年度报告.pdf 🏢 贵州茅台`）

* [ ] 无公司名的文件（如 research\_reports 下的研报）只显示文件名

* [ ] 选中文件后详情区域的公司名标签样式不变

* [ ] case\_analyzer.py 的 Ground Truth 标注搜索框同样具备公司名标签

* [ ] lint 和 unit test 通过
