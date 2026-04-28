# 本项目 Ruff 使用指南

> 本文档是 w1-easy-rag 项目的 Ruff 实操手册，涵盖当前配置、日常交互方式、常见场景处理。
> 概念入门请参阅 [Lint 与 pre-commit 入门指南](./lint-and-precommit.md)，经验沉淀请参阅 [Ruff 经验与最佳实践](../.archive/v0.1.12-governance-era/project-governance/ruff-experience-and-best-practices.md)。

---

## 1. 当前配置一览

### 配置文件

| 文件 | 作用 |
|------|------|
| `pyproject.toml` → `[tool.ruff]` | Ruff 主配置（规则、格式化、排除目录） |
| `pixi.toml` → `[tasks]` | 快捷命令定义 |
| `.pre-commit-config.yaml` | commit 前自动检查 |

### 启用的规则集

| 规则集 | 来源 | 检查什么 |
|--------|------|---------|
| E, W | pycodestyle | Python 官方风格（缩进、空格、空行等） |
| F | pyflakes | 真正的代码错误（未定义变量、重复导入等） |
| I | isort | import 语句排序 |
| UP | pyupgrade | 建议使用新版 Python 的更优写法 |
| B | flake8-bugbear | 常见 bug 模式（如盲异常断言、循环变量未使用） |
| SIM | flake8-simplify | 代码简化建议（如合并嵌套 with、三元表达式） |

### 忽略策略

**全局忽略**（`pyproject.toml` → `ignore`）：

| 规则 | 原因 |
|------|------|
| E501（行过长） | Formatter 会自动处理折行，linter 不需要重复检查 |
| B008（默认参数调用函数） | FastAPI 的 `Depends()` 常用此模式 |

**按需行级忽略**（代码中用 `# noqa: 规则名` 豁免）：

| 规则 | 典型场景 | 示例 |
|------|---------|------|
| SIM108（三元表达式） | 复杂条件分支用 if-else 更清晰时 | `# noqa: SIM108` |
| E402（import 不在文件顶部） | `sys.path.insert` 或 `warnings.warn` 后的 import 必须延迟 | `# noqa: E402` |

**per-file-ignores**：

| 文件 | 忽略规则 | 原因 |
|------|---------|------|
| `__init__.py` | F401 | init 文件职责是重新导出，未使用导入是预期行为 |

### 检查范围

当前 ruff 覆盖的路径：`src/`、`eval/`、`tests/`、`main.py`

---

## 2. 日常命令

| 命令 | 作用 | 何时使用 |
|------|------|---------|
| `pixi run ruff-check` | 检查代码问题（不修改文件） | 想看当前有哪些问题 |
| `pixi run ruff-format` | 格式化代码（会修改文件） | 想统一代码风格 |
| `pixi run lint` | 检查 + 自动修复 + 格式化 | **每次完成代码修改后** |
| `pixi run pre-commit-run` | 运行所有 pre-commit 钩子 | 想模拟 commit 前的完整检查 |

**推荐工作流**：

```bash
# 1. 写完代码后，先跑 lint
pixi run lint

# 2. 如果有无法自动修复的问题，手动修复后再次确认
pixi run ruff-check

# 3. 提交（pre-commit 会自动再检查一遍）
git add <修改的文件>
git commit -m "feat: ..."
```

---

## 3. 常见场景处理

### 场景 A：Ruff 报了一个真正的 bug

直接修复。例如：

```python
# Ruff 报错：F841 Local variable `result` is assigned to but never used
result = evaluator._build_run_config()

# 修复：如果确实不需要返回值
_ = evaluator._build_run_config()

# 修复：如果后续需要用到
result = evaluator._build_run_config()
assert result == expected
```

### 场景 B：Ruff 建议简化代码，且建议合理

接受建议。例如：

```python
# Ruff 报错：SIM117 Use a single `with` statement
with patch.object(Path, "mkdir", side_effect=OSError()):
    with pytest.raises(OSError):
        manager.create_experiment_dir(config)

# 修复：合并 with
with patch.object(Path, "mkdir", side_effect=OSError()), \
     pytest.raises(OSError):
    manager.create_experiment_dir(config)
```

### 场景 C：Ruff 建议简化代码，但接受后可读性更差

用 `# noqa: SIM108` 行级忽略。例如：

```python
# 如果三元表达式确实更清晰，直接改
pdf_path = pdf_input if isinstance(pdf_input, Path) else Path(pdf_input)

# 如果 if-else 确实更清晰，保留并加 noqa
if complex_condition_a and complex_condition_b:  # noqa: SIM108
    result = value_a
else:
    result = value_b
```

### 场景 D：import 必须延迟（sys.path.insert 之后）

在延迟的 import 行加 `# noqa: E402`。例如：

```python
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.meal import MealManager  # noqa: E402
from src.utils import load_config  # noqa: E402
```

**注意**：只给 `sys.path.insert` 之后的 import 加 `# noqa: E402`，之前的 import 不需要。

### 场景 E：Ruff 自动修复引入了问题

`ruff check --fix` 有时会误修（如把真正使用的变量名替换掉）。如果发生：

1. 用 `git diff` 检查自动修复的内容
2. 手动撤销不正确的修复
3. 在对应行加 `# noqa: RULE` 阻止 Ruff 再次修复

---

## 4. `# noqa` 使用规范

### 格式

```python
import something  # noqa: E402
```

- 精确指定规则编号：`# noqa: E402` 而非 `# noqa`
- 一个 `# noqa` 可以忽略多个规则：`# noqa: E402, F841`
- 放在行尾，与代码之间至少一个空格

### 原则

1. **能修复就不忽略**：`# noqa` 是最后手段，不是偷懒工具
2. **精确忽略**：只忽略出问题的规则，不要用裸 `# noqa` 忽略所有规则
3. **就近忽略**：只忽略出问题的那一行，不要用全局 `ignore` 代替
4. **定期审查**：运行 `ruff check --select noqa` 或搜索 `# noqa` 确认每个忽略仍然必要

### 添加全局忽略的判断标准

只有同时满足以下条件时才考虑添加到 `pyproject.toml` 的 `ignore` 列表：

1. 该规则在项目中**普遍**不适用
2. 行级忽略会导致大量重复标注
3. 忽略不会掩盖真正的代码质量问题

---

## 5. 配置变更记录

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-04-21 | 初始配置：`select = [E,W,F,I,UP,B,SIM]`，`ignore = [E501, B008, SIM108, E402]` | RF-010：添加代码检查工具 |
| 2026-04-25 | `ignore` 移除 `SIM108` 和 `E402` | 改为按需行级忽略，避免全局放行同类问题 |
| 2026-04-25 | 修复全部 15 个积压 lint 错误 | 一次性清偿技术债务 |

---

## 6. 与现有文档的关系

```
lint-and-precommit.md          ← 概念入门（Linter/Ruff/pre-commit 是什么）
    ↓
ruff-usage-guide.md（本文档）   ← 本项目实操手册（怎么用、常见场景怎么处理）
    ↓
ruff-experience-and-best-practices.md  ← 经验沉淀（演进历史、新项目最佳实践）
```

- 想了解概念 → 读 [lint-and-precommit.md](./lint-and-precommit.md)
- 想知道本项目怎么用 Ruff → 读本文档
- 想了解经验教训或开新项目 → 读 [ruff-experience-and-best-practices.md](../.archive/v0.1.12-governance-era/project-governance/ruff-experience-and-best-practices.md)
