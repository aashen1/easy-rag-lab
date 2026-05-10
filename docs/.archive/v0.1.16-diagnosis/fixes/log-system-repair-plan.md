# 日志系统修复计划

## 问题诊断

### 现象
1. 日志分散在多个文件：`logs/app_2026-05-01.log`、`data/exp_reports/.../experiment.log`
2. `experiment.log` 在 `09:45:43` 停止记录，但终端显示 `10:46:18` 还有日志
3. 部分日志只存在于主日志文件，不在 `experiment.log` 中

### 根本原因

**调用链分析：**
```
run_experiment() [L387]
  → setup_logger(system_config)  # 初始化主日志
  → logger.add(experiment.log)   # L403: 添加实验日志 handler

run_variant_evaluation() [L74]
  → RAGPipeline.__init__() [L83]
    → setup_logger(self.config)  # 问题所在！调用 logger.remove() 移除所有 handler
```

**问题代码位置：**
1. `src/pipeline.py:83` - `RAGPipeline.__init__()` 中调用 `setup_logger()`
2. `src/utils.py:92` - `setup_logger()` 调用 `logger.remove()` 移除所有 handler
3. `eval/runner/core.py:403` - 添加 `experiment.log` handler 后没有保护机制

**问题本质：**
- `setup_logger()` 被多次调用，每次都会移除所有现有 handler
- `experiment.log` handler 在 `RAGPipeline` 初始化时被意外移除
- 日志初始化应该只在程序入口点执行一次，而不是在类初始化时

---

## 修复方案

### 方案设计原则

1. **单一初始化点**：日志只在程序入口点初始化一次
2. **应存尽存**：主日志文件记录所有日志
3. **实验日志作为副本**：`experiment.log` 是主日志的子集副本，不是独立的日志流
4. **handler 生命周期管理**：使用上下文管理器管理临时 handler

### 具体修改

#### 1. 移除 `RAGPipeline.__init__()` 中的 `setup_logger()` 调用

**文件**: `src/pipeline.py`
**修改**: 删除第83行 `setup_logger(self.config)`

**原因**:
- 日志应该在程序入口点初始化，而不是在类初始化时
- `RAGPipeline` 不应该负责日志配置

#### 2. 改进 `setup_logger()` 函数

**文件**: `src/utils.py`
**修改**:
- 添加 `force` 参数控制是否移除现有 handler
- 默认 `force=False`，不移除现有 handler
- 只有在明确需要重新配置时才使用 `force=True`

```python
def setup_logger(config: dict[str, Any], force: bool = False) -> None:
    """Setup loguru logger with file and console handlers.

    Args:
        config: Application configuration dictionary.
        force: If True, remove all existing handlers before setup.
               If False, only add handlers if not already configured.
    """
    if force:
        logger.remove()
    # ... 其余代码
```

#### 3. 使用上下文管理器管理实验日志 handler

**文件**: `eval/runner/core.py`
**修改**:
- 创建上下文管理器 `experiment_log_context()`
- 在 `run_experiment()` 中使用 `with` 语句管理 handler 生命周期
- 确保实验结束后 handler 被正确移除

```python
from contextlib import contextmanager

@contextmanager
def experiment_log_context(exp_dir: Path):
    """Context manager for experiment log handler."""
    experiment_log_path = exp_dir / "experiment.log"
    handler_id = logger.add(
        str(experiment_log_path),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        encoding="utf-8",
    )
    try:
        yield
    finally:
        logger.remove(handler_id)
```

#### 4. 清理其他地方的 `logger.remove()` 调用

**文件**: `scripts/benchmark_use_ocr.py`
**修改**: 移除模块级别的 `logger.remove()` 调用（第27行）

**原因**: 模块级别调用 `logger.remove()` 会影响全局日志配置

**文件**: `src/issue/cli.py`
**修改**: 保留 `_setup_cli_logger()` 中的 `logger.remove()`，因为这是 CLI 工具的独立入口点

---

## 实施步骤

### Step 1: 修改 `src/utils.py`
- 添加 `force` 参数到 `setup_logger()`
- 默认行为改为不移除现有 handler

### Step 2: 修改 `src/pipeline.py`
- 移除 `RAGPipeline.__init__()` 中的 `setup_logger()` 调用

### Step 3: 修改 `eval/runner/core.py`
- 创建 `experiment_log_context()` 上下文管理器
- 修改 `run_experiment()` 使用上下文管理器

### Step 4: 修改 `scripts/benchmark_use_ocr.py`
- 移除模块级别的 `logger.remove()` 调用

### Step 5: 添加测试
- 测试日志 handler 不会被意外移除
- 测试实验日志正确记录

### Step 6: 验证
- 运行实验，验证日志正确记录到所有目标

---

## 预期结果

1. **主日志文件** (`logs/app_YYYY-MM-DD.log`): 记录所有日志
2. **实验日志** (`data/exp_reports/.../experiment.log`): 记录实验期间的日志副本
3. **终端**: 显示所有日志
4. **无日志丢失**: 所有日志都能在主日志文件中找到
