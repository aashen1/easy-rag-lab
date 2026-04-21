# pytest tmp 目录 FileExistsError 排查记录

<!-- status: resolved -->

> 发现日期: 2026-04-21
> 解决日期: 2026-04-22

---

## 现象

在 Windows 上运行 pytest 时，`test_chunker.py` 等使用 `tmp_path` fixture 的测试偶发 `FileExistsError`。同时观察到 `.pytest_tmp` 目录在测试运行后残留大量临时文件和子目录，未被自动清理。

---

## 根因分析

### 背景

项目将 pytest 的 `--basetemp` 从系统默认的 `%TEMP%` 改为项目本地相对路径 `.pytest_tmp`，目的是减少对 C 盘 SSD 的写入量。配置位于 `pytest.ini`：

```ini
addopts = --basetemp=.pytest_tmp
```

### 问题根源

1. **pytest 清理机制差异**：当使用默认 `%TEMP%` 时，pytest 通过 `make_numbered_dir_with_cleanup` 创建带编号的子目录（如 `pytest-0`, `pytest-1`），自动保留最近 3 个并清理旧的。但当指定 `--basetemp` 时，pytest 使用 `ensure_reset_dir` 在会话开始时清空重建整个 basetemp 目录。

2. **Windows 文件锁**：如果上一次测试进程异常退出（IDE 强制终止、Ctrl+C 等），`.pytest_tmp` 内的文件可能被 Windows 文件锁锁定，导致 `ensure_reset_dir` 中的 `rm_rf` 失败，进而触发 `FileExistsError`。

3. **残留目录累积**：即使正常退出，相对路径模式下 pytest 的 `tmp_path_retention_count` 默认为 3，意味着测试完成后不会立即清理临时目录，导致 `.pytest_tmp` 持续膨胀。

---

## 解决方案

### 1. 配置 pytest 自动清理策略

在 `pytest.ini` 中添加：

```ini
tmp_path_retention_count = 0
tmp_path_retention_policy = failed
```

- `tmp_path_retention_count = 0`：测试完成后立即清理所有临时目录
- `tmp_path_retention_policy = failed`：仅保留失败测试的临时目录（便于调试），但由于 count=0，实际上全部清理

### 2. 添加会话级清理 hook

在 `tests/conftest.py` 中添加 `pytest_configure` hook，在每次测试会话开始前主动清理残留的 `.pytest_tmp` 目录：

```python
def pytest_configure(config):
    basetemp = config.getoption("basetemp", default=None)
    if basetemp is not None:
        basetemp_path = Path(basetemp)
        if basetemp_path.is_absolute():
            target = basetemp_path
        else:
            target = Path(config.rootdir) / basetemp_path
        if target.exists():
            with contextlib.suppress(OSError):
                shutil.rmtree(target)
```

这确保即使上一次会话异常退出留下了残留目录，新会话也能干净启动。

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `pytest.ini` | 添加 `tmp_path_retention_count` 和 `tmp_path_retention_policy` |
| `tests/conftest.py` | 添加 `pytest_configure` hook，会话开始前清理残留 basetemp |

---

## 经验总结

### 关键发现

1. **`--basetemp` 改变 pytest 清理行为**：从自动编号+保留最近 N 个变为每次清空重建，在 Windows 上可能因文件锁失败
2. **`tmp_path_retention_count`** 是 pytest 7.x 的配置项，控制保留多少个测试会话的临时目录，设为 0 可实现即时清理
3. **Windows 文件锁**是 Linux 上不会遇到的平台特有问题，需要额外的防御性清理

### 防范措施

1. **主动清理**：在 `pytest_configure` 中预清理残留目录，而非依赖 pytest 内部机制
2. **优雅降级**：清理失败时 `suppress(OSError)` 静默处理，不阻塞测试启动
3. **保留 SSD 保护**：`--basetemp=.pytest_tmp` 配置保留，仍将临时文件写入项目目录而非 C 盘

---

## 相关文档

- [pytest tmp_path 文档](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [ghost-folder-mkdir.md](ghost-folder-mkdir.md) — 类似的测试临时文件问题
