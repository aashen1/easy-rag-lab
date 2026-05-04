# 低优先级代码质量修复计划

## 问题评估

| 问题 | 决策 | 理由 |
|------|------|------|
| `.trashbin` 路径硬编码 3 处 | ✅ 修 | 3 处不同解析策略 + tools.py 内重复逻辑，值得统一 |
| `data/maintenance_reports` 路径硬编码 2 处 | ✅ 修 | 与 config 中其他 `data/` 路径模式一致 |
| `subprocess timeout=30` 硬编码 3 处 | ✅ 修 | 3 处同文件，加一个 config key 即可 |
| 文本截断长度硬编码 | ❌ 不修 | 37+ 处、8 种不同长度、多为日志预览，配置化收益极低 |
| CLI 中 1 处 print() 应改 logger | ✅ 修 | 1 行改动，except 块中的错误信息应用 logger |

---

## 修复步骤

### Step 1: config.yaml — 新增 3 个配置项

在 `config.yaml` 的 `agent` 节下新增：

```yaml
agent:
  # ... 现有配置 ...
  trashbin_dir: ".trashbin"                    # NEW
  maintenance_reports_dir: "data/maintenance_reports"  # NEW
  subprocess_timeout: 30                       # NEW (秒)
```

### Step 2: tools.py — 统一 trashbin 路径 + 修复重复逻辑

**2a.** `_backup_to_trashbin()` 函数（L48-65）：从 config 读取 trashbin 路径

```python
def _backup_to_trashbin(source_path: Path, label: str) -> str | None:
    from src.utils import load_config
    config = load_config()
    trashbin_dir = config.get("agent", {}).get("trashbin_dir", ".trashbin")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trashbin = Path(trashbin_dir)
    # ... 其余不变
```

**2b.** `delete_source()` 函数（L435-450）：删除重复的 trashbin 逻辑，改用 `_backup_to_trashbin`

当前 L435-450 手动实现了 trashbin 备份逻辑（与 `_backup_to_trashbin` 重复），改为调用 `_backup_to_trashbin`：

```python
# 删除 L435-450 的手动备份逻辑，替换为：
backup_path = None
try:
    points_metadata = indexer.scroll_by_source(source, with_vectors=False)
    if points_metadata:
        source_hash = hashlib.md5(source.encode()).hexdigest()[:8]
        backup_file = Path(_backup_to_trashbin(
            Path(f"source_backup_{source_hash}"), f"source_{source_hash}"
        )) if _backup_to_trashbin(...) else None
```

实际上更简单的做法：把 points_metadata 写入临时文件再调用 `_backup_to_trashbin`，或者直接在 `_backup_to_trashbin` 中也读取 config 的 trashbin_dir，而 `delete_source` 中保留写入逻辑但改用 config 路径。

**最终方案**：`delete_source` 中保留写入逻辑（因为备份的是 JSON 数据而非已有文件），但将 `Path(".trashbin")` 改为从 config 读取。

**2c.** 3 处 `subprocess.run(..., timeout=30)` 改为从 config 读取：

```python
from src.utils import load_config
config = load_config()
timeout = config.get("agent", {}).get("subprocess_timeout", 30)
result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
```

同步更新 2 处 `TimeoutExpired` 的错误消息中的 "30 seconds" 为动态值。

### Step 3: case_collector.py — trashbin 路径从 config 读取

L563: `trashbin = cases_dir.parent.parent / ".trashbin"` 改为：

```python
from src.utils import load_config
config = load_config()
trashbin_dir = config.get("agent", {}).get("trashbin_dir", ".trashbin")
trashbin = Path(trashbin_dir)
if not trashbin.is_absolute():
    trashbin = cases_dir.parent.parent / trashbin_dir
```

这样既支持绝对路径也支持相对路径，保持向后兼容。

### Step 4: reporters — maintenance_reports 路径从 config 读取

**4a.** `maintenance_report.py` L120: `Path("data/maintenance_reports")` → 从 config 读取

**4b.** `comparison_report.py` L150: 同上

两个 reporter 都需要 `from src.utils import load_config`，然后：

```python
config = load_config()
reports_dir = Path(config.get("agent", {}).get("maintenance_reports_dir", "data/maintenance_reports"))
```

### Step 5: artifact_cli.py — print → logger

L118: `print(f"Failed to read manifest: {e}")` → `logger.error(f"Failed to read manifest: {e}")`

文件已有 `from loguru import logger` 导入。

### Step 6: 测试更新

- `tests/test_agent.py` L278, L353: 更新 trashbin 路径断言，适配 config 读取
- `tests/test_case_collector.py` L377: 同上
- `tests/test_agent_reporters.py` L129: 更新 maintenance_reports 路径断言

### Step 7: 运行 lint + 测试验证

```bash
pixi run lint
pixi run test
```

---

## 涉及文件清单

| 文件 | 改动类型 |
|------|---------|
| `config.yaml` | 新增 3 个配置项 |
| `src/agent/tools.py` | trashbin 路径统一 + subprocess timeout 配置化 |
| `src/case_collector.py` | trashbin 路径配置化 |
| `src/agent/reporters/maintenance_report.py` | 路径配置化 |
| `src/agent/reporters/comparison_report.py` | 路径配置化 |
| `src/artifact_cli.py` | print → logger |
| `tests/test_agent.py` | 适配断言 |
| `tests/test_case_collector.py` | 适配断言 |
| `tests/test_agent_reporters.py` | 适配断言 |
