# 代码质量修复计划书 - Phase 5 清理任务

> 基于：`code-quality-fix-progress.md` | 创建日期：2026-05-16 | 目标：完成 Phase 5 中的低风险清理任务

---

## 背景

根据进度报告，Phase 1-2 和 Phase 4 已完成，Phase 3（治本）和 Phase 5（清理）待完成。

**本计划选择 Phase 5 中 3 个相对独立、风险较低的任务**，这些任务：
- 不涉及架构变更
- 不影响现有配置兼容性
- 改动范围小，易于验证

---

## 任务清单

### 任务 1：删除 `del pipeline` + `gc.collect()` 反模式

**文件**: `eval/runner/core.py`

**问题描述**:
Python 的 GC 不需要手动干预。`del` 只减少引用计数，`gc.collect()` 在正常场景下是多余的。

**当前代码位置**:
- 第 93-94 行：`del pipeline` + `gc.collect()`
- 第 1186 行：`gc.collect()`

**修改方案**:
1. 删除第 93-94 行的 `del pipeline` 和 `gc.collect()`
2. 删除第 1186 行的 `gc.collect()`
3. 删除第 1184 行的 `import gc`（如果不再需要）

**验收标准**:
- 无 `del pipeline` 和 `gc.collect()` 调用
- 所有测试通过 (`pixi run test`)
- Lint 检查通过 (`pixi run lint`)

**预计耗时**: 10 分钟

---

### 任务 2：修复 `asset_verifier.py` 使用已废弃的 `pkg_resources`

**文件**: `eval/runner/asset_verifier.py`

**问题描述**:
`pkg_resources` 已废弃，应改用 `importlib.metadata`。

**当前代码** (第 235-256 行):
```python
import pkg_resources

key_packages = [...]
installed = {}
for pkg in pkg_resources.working_set:
    if pkg.key.lower() in key_packages:
        installed[pkg.key] = pkg.version
```

**修改方案**:
```python
from importlib.metadata import distributions

key_packages = [...]
installed = {}
for dist in distributions():
    if dist.metadata.get("Name", "").lower().replace("-", "_") in key_packages:
        installed[dist.metadata["Name"]] = dist.version
```

**验收标准**:
- 无 `pkg_resources` 导入
- 功能验证通过（`collect_environment_info()` 返回正确的包版本）
- 所有测试通过

**预计耗时**: 30 分钟

---

### 任务 3：修复 `pipeline_profiler.py` 编号逻辑 bug

**文件**: `eval/pipeline_profiler.py`

**问题描述**:
`suggestions` 列表中的条目已经以 `"1. "` 开头，但后面又用 `enumerate(suggestions, 1)` 重新编号并 `s[3:]` 截取前缀，导致编号混乱。

**当前代码** (第 535-571 行):
```python
suggestions = []
if ...:
    suggestions.append("1. **PDF解析优化**: ...")
if ...:
    suggestions.append("1. **向量嵌入优化**: ...")
# ... 每个都是 "1. " 开头

for i, s in enumerate(suggestions, 1):
    lines.append(f"{i}. {s[3:]}")
```

**问题分析**:
- 所有 suggestions 都以 `"1. "` 开头
- `enumerate(suggestions, 1)` 会重新编号为 1, 2, 3...
- `s[3:]` 截取去掉前 3 个字符（即 `"1. "`）
- 最终输出是正确的编号，但代码逻辑混乱且脆弱

**修改方案**:
方案 A（推荐）：移除 suggestions 中的编号前缀，让 enumerate 统一编号
```python
suggestions = []
if ...:
    suggestions.append("**PDF解析优化**: ...")
if ...:
    suggestions.append("**向量嵌入优化**: ...")

for i, s in enumerate(suggestions, 1):
    lines.append(f"{i}. {s}")
```

**验收标准**:
- 编号逻辑清晰，无重复前缀
- 生成的报告编号正确
- 所有测试通过

**预计耗时**: 20 分钟

---

## 执行顺序

1. **任务 1** - 最简单，删除代码
2. **任务 3** - 修复逻辑 bug
3. **任务 2** - 替换废弃 API

---

## 验收流程

每个任务完成后：
1. 运行 `pixi run lint` 检查代码风格
2. 运行 `pixi run test` 确保测试通过
3. 提交 commit（遵循 Conventional Commits）

全部完成后：
1. 运行 `pixi run test-all` 完整测试
2. 更新 `code-quality-fix-progress.md` 进度

---

## 风险评估

| 任务 | 风险等级 | 说明 |
|------|---------|------|
| 任务 1 | 低 | 仅删除冗余代码，不影响功能 |
| 任务 2 | 低 | API 替换，功能等价 |
| 任务 3 | 低 | 修复 bug，输出更清晰 |

---

## 不在本计划中的任务

以下任务风险较高或需要更多时间，不在本次计划中：

1. **Phase 3 Pydantic 模型重构** - 可能影响配置兼容性
2. **Phase 3 dataclass/Pydantic 统一** - 涉及大量代码变更
3. **Phase 5 其他任务** - 如遗留代码删除、函数属性重构等

这些任务建议在后续迭代中完成。
