# WSL2 迁移后跨平台兼容性修复计划

## 问题概述

从 Windows 迁移到 WSL2 后，5 个测试失败。项目已声明支持 `["win-64", "linux-64", "osx-arm64"]`，需要从跨平台兼容性角度审视修复方案。

***

## 问题 1: `normalize_source` 函数 — **源代码跨平台缺陷**

### 失败测试

| 测试                                              | 预期                      | 实际                      |
| ----------------------------------------------- | ----------------------- | ----------------------- |
| `test_normalize_source[annual_report\\贵州茅台...]` | `annual_report/贵州茅台...` | `annual_report\贵州茅台...` |
| `test_windows_backslash_normalizes_to_posix`    | 两种分隔符输出相同               | 不同                      |
| `test_mixed_separators_normalize_consistently`  | 两种分隔符输出相同               | 不同                      |
| `test_windows_backslash_no_parent`              | 两种分隔符输出相同               | 不同                      |

### 根因分析

**位置**: [eval/metrics/utils.py:110](file:///home/eetaa/projects/ash-easy-rag/easy-rag-lab/eval/metrics/utils.py#L110)

```python
p = Path(Path(source).as_posix())
```

**问题**:

* `Path("a\\b\\c")` 在 Linux 上把整个字符串当作**单个文件名**，因为 Linux 不识别 `\` 为路径分隔符

* `as_posix()` 只对已解析的路径结构进行转换，无法修复错误的解析结果

* 这导致 Windows 风格路径在 Linux 上无法正确规范化

**影响范围**:

* 数据文件可能包含 Windows 风格路径（如迁移过来的数据、跨平台共享的数据）

* 这是**源代码的跨平台兼容性缺陷**，不是测试问题

### 修复方案

**修改文件**: `eval/metrics/utils.py`

**修改内容**:

```python
def normalize_source(source: str, include_parent: bool = False) -> str:
    # 先将 Windows 反斜杠转换为 POSIX 正斜杠，确保跨平台一致性
    normalized_path = source.replace("\\", "/")
    p = Path(normalized_path)
    stem = p.stem
    if include_parent and p.parent != Path("."):
        parent_name = p.parent.name
        if parent_name:
            return f"{parent_name}/{stem}"
    return stem
```

***

## 问题 2: PDF Viewer 测试 — **平台特定功能待完善**

### 失败测试

`test_open_edge`: 测试 Windows Edge 浏览器打开 PDF 功能

### 根因分析

**位置**: [scripts/pdf\_viewer.py](file:///home/eetaa/projects/ash-easy-rag/easy-rag-lab/scripts/pdf_viewer.py)

**当前状态**:

* 只检测 Windows 特定的 PDF 查看器（SumatraPDF、Edge）

* 这是开发辅助工具，用于 golden test set review

**错误**:

```python
file_url = pdf_path.as_uri()  # 相对路径无法转换为 URI
```

测试使用 Windows 路径 `r"C:\test\report.pdf"`，在 Linux 上被解析为相对路径。

### 修复方案

**阶段 1（本次）**: 临时跳过测试，标记 TODO

**修改文件**: `tests/test_pdf_viewer.py`

```python
import sys
import pytest

class TestPDFViewerOpenAtPage:
    # ... 其他测试 ...
    
    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="TODO: Add Linux/macOS PDF viewer support (see FEAT-XXX)"
    )
    @patch("subprocess.Popen")
    def test_open_edge(self, mock_popen):
        # ... 原有测试代码 ...
```

**阶段 2（后续）**: 创建 Issue 跟踪多平台 PDF 查看器支持

```bash
pixi run issue create -t feat -T "支持 Linux/macOS PDF 查看器" -p low -l "enhancement,platform"
```

**Linux/macOS 常用 PDF 查看器**:

* Linux: `evince`, `okular`, `xdg-open` (系统默认)

* macOS: `open` (系统默认), `Preview.app`, `Skim`

***

## 实施步骤

### 步骤 1: 修复 `normalize_source` 源代码

* 修改 `eval/metrics/utils.py`

* 在创建 Path 对象前统一路径分隔符

### 步骤 2: 修复 PDF Viewer 测试

* 修改 `tests/test_pdf_viewer.py`

* 为 `test_open_edge` 添加平台跳过条件

* 在跳过原因中引用后续 Issue

### 步骤 3: 创建 Issue 跟踪多平台支持

```bash
pixi run issue create -t feat -T "支持 Linux/macOS PDF 查看器" -p low -l "enhancement,platform"
```

### 步骤 4: 验证修复

```bash
pixi run test
```

***

## 测试策略说明

| 测试类型          | 跨平台策略                    |
| ------------- | ------------------------ |
| 核心功能测试        | 必须在所有平台通过                |
| 平台特定功能测试（已支持） | 在对应平台运行                  |
| 平台特定功能测试（待开发） | 临时跳过，标记 TODO，创建 Issue 跟踪 |

**原则**:

* 测试的目标是验证**功能在当前平台的正确性**

* 平台特定功能应明确标记

* 跳过测试时必须创建 Issue 跟踪后续完善

