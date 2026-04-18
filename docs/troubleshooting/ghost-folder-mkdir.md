# 幽灵文件夹问题排查记录

<!-- status: active -->

> 发现日期: 2026-04-18
> 解决日期: 2026-04-18

---

## 现象

项目运行过程中，根目录会不时多出一个 `output_dir` 空文件夹，删除后继续运行又会重新出现。

---

## 根因分析

### 排查过程

1. **埋钩子**：在 Python 代码中替换 `os.mkdir` 和 `os.makedirs`，记录调用堆栈
2. **Process Monitor**：使用 ProcMon 监控文件系统操作
3. **发现遗漏**：钩子只覆盖了 `os.mkdir` 和 `os.makedirs`，但 `src/utils.py` 使用的是 `pathlib.Path.mkdir`

### 问题根源

幽灵文件夹 `output_dir` 由两个测试用例创建：

1. `tests/test_parser.py:51` - `test_parse_all_pdfs_input_dir_not_found`
2. `tests/test_chunker.py:65` - `test_process_parsed_files_input_dir_not_found`

两个函数都有相同的 bug：**先创建输出目录，后检查输入目录是否存在**。

---

## 解决方案

### 代码修复

| 文件 | 函数 | 修改 |
|------|------|------|
| `src/parser.py:41-48` | `parse_all_pdfs` | 先检查输入目录，再创建输出目录 |
| `src/chunker.py:86-93` | `process_parsed_files` | 先检查输入目录，再创建输出目录 |

### 修复前

```python
def parse_all_pdfs(...):
    os.makedirs(output_dir, exist_ok=True)  # 先创建
    if not input_dir.exists():              # 后检查
        raise FileNotFoundError(...)
```

### 修复后

```python
def parse_all_pdfs(...):
    if not input_dir.exists():              # 先检查
        raise FileNotFoundError(...)
    os.makedirs(output_dir, exist_ok=True)  # 后创建
```

---

## 经验总结

### 排查技巧

1. **埋钩子**：替换系统函数（如 `os.mkdir`）记录调用堆栈
2. **Process Monitor**：Windows 下的文件系统监控工具
3. **注意 pathlib**：`pathlib.Path.mkdir` 与 `os.mkdir` 是不同的实现

### 防范措施

1. **检查顺序**：先检查前置条件，再执行副作用操作
2. **测试隔离**：测试用例应清理创建的临时文件
3. **日志完整**：确保日志覆盖所有关键路径

---

## 相关文档

- [测试运行指南](../guides/testing.md)
