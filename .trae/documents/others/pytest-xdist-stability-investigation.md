# pytest-xdist 并行测试稳定性调查报告

## 问题现象

在合并 `cleaning-issues` 分支时，post-merge hook 运行测试出现以下错误：

```
[gw1] node down: Not properly terminated
[gw4] node down: Not properly terminated
...
INTERNALERROR> MemoryError
INTERNALERROR> Windows fatal exception: stack overflow
```

## 根本原因分析

### 1. `-n auto` 过度并行化

当前配置使用 `-n auto`，会创建与 CPU 逻辑核心数相同的 worker 进程。

**问题**：
- Windows 上进程创建/销毁开销比 Linux 大得多
- 每个 worker 都是独立的 Python 进程，内存占用高
- 8-16 个 worker 同时运行容易导致内存耗尽

**证据**：
- 错误日志显示 `MemoryError` 和 `stack overflow`
- 多个 worker 同时崩溃（gw1, gw4 等）

### 2. Windows 平台特有问题

根据 [pytest-xdist issue #12671](https://github.com/pytest-dev/pytest/issues/12671) 和其他相关 issue：

- Windows 的进程管理比 Linux 更重
- 临时目录权限问题可能导致 worker 无法正常启动
- 文件系统竞争更频繁

### 3. 测试收集阶段竞争

根据 [pytest-xdist issue #432](https://github.com/pytest-dev/pytest-xdist/issues/432)：

- 多个 worker 同时收集测试可能导致测试列表不一致
- Windows 上更容易出现这个问题

## 改进方案

### 方案 1：限制 Worker 数量（推荐）

**修改 `pixi.toml`**：

```toml
[tasks.test-unit]
cmd = "pytest tests/ -m \"unit\" --tb=short -q --durations=5 -n 4"

[tasks.test]
cmd = "pytest tests/ -m \"not integration and not slow\" --tb=short -q --durations=10 -n 4"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10 -n 4"
```

**理由**：
- 固定 4 个 worker，避免过度并行化
- 在大多数 Windows 机器上稳定运行
- 仍然能获得显著的并行加速

### 方案 2：添加容错参数

**修改 `pixi.toml`**：

```toml
[tasks.test]
cmd = "pytest tests/ -m \"not integration and not slow\" --tb=short -q --durations=10 -n 4 --max-worker-restart=2"
```

**新增参数**：
- `--max-worker-restart=2`：限制 worker 重启次数，避免无限循环
- 可选：`--dist loadfile` 让同一文件的测试在同一个 worker 运行

### 方案 3：环境自适应配置

**在 `conftest.py` 中添加**：

```python
import os
import pytest

def pytest_configure(config):
    workers = config.getoption("numprocesses", default=None)
    if workers == "auto":
        cpu_count = os.cpu_count() or 4
        logical_cores = max(1, cpu_count)
        physical_cores = max(1, logical_cores // 2)
        if os.name == 'nt':  # Windows
            config.option.numprocesses = min(physical_cores, 4)
        else:  # Linux/macOS
            config.option.numprocesses = logical_cores
```

**优点**：
- 自动适配不同平台
- Windows 上保守，Linux 上激进

### 方案 4：分离 CI 和本地测试配置

**创建专门的 CI 测试命令**：

```toml
[tasks.test-ci]
cmd = "pytest tests/ -m \"not integration and not slow\" --tb=short -q --durations=10 -n 2 --max-worker-restart=1"
```

**理由**：
- CI 环境资源更受限
- 稳定性优先于速度

## 实施步骤

1. **立即修复**：将 `-n auto` 改为 `-n 4`
2. **添加容错**：添加 `--max-worker-restart=2`
3. **监控效果**：观察后续测试运行是否稳定
4. **可选优化**：如果仍有问题，考虑 `--dist loadfile`

## 风险评估

- **低风险**：方案 1 和 2 只修改命令行参数，不改变测试逻辑
- **中风险**：方案 3 需要修改 conftest.py，需要测试
- **无风险**：方案 4 只是新增命令，不影响现有流程

## 参考资料

- [pytest-xdist issue #1189](https://github.com/pytest-dev/pytest-xdist/issues/1189) - node down 问题
- [pytest-xdist issue #440](https://github.com/pytest-dev/pytest-xdist/issues/440) - max-worker-restart 参数
- [pytest issue #12671](https://github.com/pytest-dev/pytest/issues/12671) - Windows 缓存问题
- [pytest-xdist 文档](https://pytest-xdist.readthedocs.io/en/stable/known-limitations.html) - 已知限制
