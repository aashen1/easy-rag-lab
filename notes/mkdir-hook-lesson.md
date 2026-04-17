# mkdir 钩子埋点经验总结

## 问题背景

项目中出现了一个"幽灵"目录 `output_dir`，时不时会在项目根目录被创建。为了定位问题，采用了替换 `os.mkdir` 和 `os.makedirs` 的方式埋钩子追踪调用栈。

## 钩子实现

```python
import os
import traceback
from datetime import datetime

_DEBUG_LOG_FILE = "output_dir_debug.log"

def _log_hook(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(_DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

_original_mkdir = os.mkdir
_original_makedirs = os.makedirs

def _debug_mkdir(path, *args, **kwargs):
    if "output_dir" in str(path).lower():
        _log_hook("=" * 50)
        _log_hook(f"[HOOK] 检测到创建目录: {path}")
        _log_hook("调用堆栈:")
        for line in traceback.format_stack()[:-1]:
            _log_hook(line.strip())
        _log_hook("=" * 50)
    return _original_mkdir(path, *args, **kwargs)

def _debug_makedirs(path, *args, **kwargs):
    if "output_dir" in str(path).lower():
        _log_hook("=" * 50)
        _log_hook(f"[HOOK] 检测到递归创建目录: {path}")
        _log_hook("调用堆栈:")
        for line in traceback.format_stack()[:-1]:
            _log_hook(line.strip())
        _log_hook("=" * 50)
    return _original_makedirs(path, *args, **kwargs)

os.mkdir = _debug_mkdir
os.makedirs = _debug_makedirs
```

## 遗漏的问题

实际修复 commit (`fe64c09`) 显示问题出在 `src/parser.py` 和 `src/chunker.py` 中的 `ensure_dir()` 调用。但钩子**没有捕获到**这个调用。

### 根本原因

`ensure_dir()` 函数的实现使用了 `pathlib.Path.mkdir()`：

```python
def ensure_dir(path: str) -> Path:
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)  # <-- 这里！
    return dir_path
```

**`pathlib.Path.mkdir()` 是一个独立的方法，与 `os.mkdir` 和 `os.makedirs` 完全无关。**

## 经验教训：如何更全面地埋钩子

### 1. 识别所有可能的目录创建入口

Python 中创建目录的方式不止一种：

| 方式 | 模块 | 说明 |
|------|------|------|
| `os.mkdir(path)` | `os` | 创建单层目录 |
| `os.makedirs(path)` | `os` | 递归创建目录 |
| `Path.mkdir()` | `pathlib` | Path 对象的方法 |
| `Path.mkdir(parents=True)` | `pathlib` | 等价于 makedirs |
| `tempfile.mkdtemp()` | `tempfile` | 创建临时目录 |
| `shutil.rmtree()` 的反向操作 | - | 无，但要注意 |

### 2. 更全面的钩子实现

```python
import os
import traceback
from datetime import datetime
from pathlib import Path

_DEBUG_LOG_FILE = "output_dir_debug.log"

def _log_hook(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(_DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

# 保存原始函数
_original_os_mkdir = os.mkdir
_original_os_makedirs = os.makedirs
_original_path_mkdir = Path.mkdir

def _debug_os_mkdir(path, *args, **kwargs):
    if "output_dir" in str(path).lower():
        _log_hook(f"[os.mkdir] {path}")
        for line in traceback.format_stack()[:-1]:
            _log_hook(line.strip())
    return _original_os_mkdir(path, *args, **kwargs)

def _debug_os_makedirs(path, *args, **kwargs):
    if "output_dir" in str(path).lower():
        _log_hook(f"[os.makedirs] {path}")
        for line in traceback.format_stack()[:-1]:
            _log_hook(line.strip())
    return _original_os_makedirs(path, *args, **kwargs)

def _debug_path_mkdir(self, *args, **kwargs):
    if "output_dir" in str(self).lower():
        _log_hook(f"[Path.mkdir] {self}")
        for line in traceback.format_stack()[:-1]:
            _log_hook(line.strip())
    return _original_path_mkdir(self, *args, **kwargs)

# 替换
os.mkdir = _debug_os_mkdir
os.makedirs = _debug_os_makedirs
Path.mkdir = _debug_path_mkdir  # 关键！
```

### 3. 其他注意事项

1. **类方法需要绑定到类上**：`Path.mkdir` 是实例方法，替换时要用 `Path.mkdir = debug_method`，而不是 `path.mkdir`

2. **第三方库可能有自己的封装**：如果项目使用了第三方库（如 `fsspec`、`smart_open`），它们可能有自己的目录创建逻辑

3. **考虑使用 `atexit` 记录总结**：可以在程序退出时打印"是否检测到目标目录创建"

4. **路径匹配策略**：
   - 精确匹配：`path == "output_dir"`
   - 包含匹配：`"output_dir" in str(path).lower()`
   - 正则匹配：更灵活但更复杂

### 4. 替代方案

如果钩子方式不够可靠，可以考虑：

1. **文件系统监控**：使用 `watchdog` 库监听目录创建事件
2. **strace/ltrace**：Linux 下可以用 `strace -e mkdir,mkdirat` 追踪系统调用
3. **IDE 调试断点**：在 `ensure_dir` 等关键函数打断点

## 总结

埋钩子追踪函数调用时，必须考虑**所有可能的调用路径**。Python 的标准库提供了多种创建目录的方式，`os` 模块和 `pathlib` 模块是独立的，需要分别处理。

**核心原则：找到目标函数的所有入口点，逐一替换。**
