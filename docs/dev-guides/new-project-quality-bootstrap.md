# 新项目质量体系引导：从 git init 到健康成长

> 本文档面向从零开始创建新 Python 项目的开发者，介绍如何从第一天就建立完整的代码质量防线，确保项目在 Ruff 检查、pytest 测试、pre-commit 钩子、Conventional Commits 等规范下健康成长。
>
> 这些实践提炼自 ash-easy-rag 项目（v0.1.0 ~ v0.1.16）的真实演进经验——该项目在无规范期积累了近 1000 个 lint 错误，最终花了多个版本才清偿完毕。本文的目标是让你不必重蹈覆辙。

---

## 1. 为什么要从第一天就建防线？

ash-easy-rag 的教训：

| 阶段 | 状况 | 代价 |
|------|------|------|
| v0.1.0 ~ v0.1.5（无规范期） | 无 Linter、无 pre-commit、无测试分层 | 积累 982 个 lint 错误 |
| v0.1.6（手动规范期） | 靠人工审查改进代码质量 | 无法系统性覆盖，改进随时间退化 |
| v0.1.7 ~ v0.1.8（拖延期） | 引入 Ruff 但积压未清 | 15 个 lint 错误长期存在，"以后再修"永远不会修 |
| v0.1.8+（清偿期） | 配置收紧 + 一次性修复 | 额外花费大量时间理解、判断、逐个修复 |

**核心结论**：越晚引入质量工具，成本越高。在项目第一天就配置好，问题在写代码的瞬间被捕获，修复成本接近零。

---

## 2. 质量防线全景图

完成本文所有步骤后，你的项目将拥有以下防线：

```
代码提交流程中的质量防线
═══════════════════════════════════════════════════════════

  写代码
    ↓
  git add
    ↓
  git commit ──→ 【防线 1】pre-commit 钩子自动触发
    │              ├── ruff check --fix    （代码问题检查+自动修复）
    │              ├── ruff format         （代码格式化）
    │              ├── trailing-whitespace （行尾空格清理）
    │              ├── end-of-file-fixer   （文件末尾换行）
    │              ├── check-yaml          （YAML 语法检查）
    │              └── check-merge-conflict（合并冲突检测）
    │
    │  不通过 → commit 被阻止，修复后重新 add + commit
    │  通过   → commit 成功
    ↓
  git merge ──→ 【防线 2】post-merge 钩子自动触发
                  └── pixi run test        （标准测试套件）

  手动防线
  ══════════
  pixi run lint        → 检查+自动修复+格式化（每次改完代码跑一遍）
  pixi run test-unit   → 纯单元测试（开发中秒级反馈）
  pixi run test        → 标准测试（功能完成后验证）
  pixi run test-all    → 全量测试（发版前验证）
```

---

## 3. 前置条件

| 工具 | 用途 | 安装方式 |
|------|------|---------|
| **Git** | 版本控制 | 系统包管理器 |
| **pixi** | Python 环境与任务管理 | [pixi.sh](https://pixi.sh) |
| **Trae / Claude Code**（可选） | AI 辅助开发，读取项目规则 | IDE 插件 |

> 本文以 pixi 作为包管理器和任务运行器。如果你使用 uv / poetry / pip，请自行替换对应的依赖安装和脚本定义方式，但质量工具的配置逻辑完全相同。

---

## 4. 逐步搭建

### Step 1：初始化项目

```bash
mkdir my-project && cd my-project
git init
pixi init
```

此时项目中有 `pixi.toml`。编辑它，设置基本信息：

```toml
[workspace]
name = "my-project"
version = "0.1.0"
channels = ["conda-forge"]
platforms = ["win-64"]  # 按你的系统修改

[dependencies]
python = "3.12.*"
```

### Step 2：添加质量工具依赖

```bash
pixi add --pypi ruff
pixi add --pypi pre-commit
pixi add --pypi pytest
pixi add --pypi pytest-xdist
```

> **原则**：质量工具作为项目依赖纳入 pixi 管理，确保所有开发者环境一致。不要依赖全局安装。

### Step 3：创建项目骨架

```bash
mkdir src tests
touch src/__init__.py tests/__init__.py
touch pyproject.toml
```

> `src/` 放业务代码，`tests/` 放测试代码，`pyproject.toml` 放工具配置。这是 Python 社区最主流的结构。

### Step 4：配置 Ruff

在 `pyproject.toml` 中添加：

```toml
[tool.ruff]
target-version = "py312"
line-length = 88
extend-exclude = [
    "data",
    ".pixi",
    ".venv",
]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

**配置说明**：

| 配置项 | 值 | 理由 |
|--------|-----|------|
| `select` | `E, W, F, I, UP, B, SIM` | 覆盖错误检测、风格检查、import 排序、新版写法、bug 模式、简化建议 |
| `ignore` | 仅 `E501` | 行过长由 formatter 自动处理；其他规则不要全局忽略 |
| `per-file-ignores` | `__init__.py` → `F401` | init 文件职责是重新导出，未使用导入是预期行为 |
| `line-length` | `88` | Black 默认值，社区最广泛使用的标准 |

**关于 `ignore` 的原则**：

- ✅ `E501`：formatter 会自动折行，linter 不需要重复检查
- ✅ `B008`：**仅在使用 FastAPI 时添加**，其他项目不需要
- ❌ `SIM108`：不要全局忽略。如果某处 if-else 确实更清晰，用 `# noqa: SIM108` 行级忽略
- ❌ `E402`：不要全局忽略。如果某处 import 必须延迟，用 `# noqa: E402` 行级忽略
- ❌ 其他规则：先不要忽略，遇到真正需要忽略的再按行处理

> **经验教训**：全局忽略是隐性债务。ash-easy-rag 曾全局忽略 `SIM108` 和 `E402`，导致新代码中本应修复的违规也被放行，直到移除全局忽略时才发现遗漏。

### Step 5：配置 pytest

在 `pyproject.toml` 中添加：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: marks tests as pure unit tests (no external dependencies)",
    "integration: marks tests that touch external systems (API, database, real files)",
    "slow: marks tests as slow (heavy imports or execution time >5s)",
]
addopts = "--basetemp=.pytest_tmp"
tmp_path_retention_count = 0
tmp_path_retention_policy = "failed"
```

**配置说明**：

| 配置项 | 值 | 理由 |
|--------|-----|------|
| `testpaths` | `["tests"]` | 只在 tests 目录找测试 |
| `markers` | unit / integration / slow | 三层测试分层，按需选择运行深度 |
| `addopts` | `--basetemp=.pytest_tmp` | 临时文件放在项目根目录，方便清理和 .gitignore |
| `tmp_path_retention_count` | `0` | 通过的测试自动清理临时文件 |
| `tmp_path_retention_policy` | `"failed"` | 只保留失败测试的临时文件用于调试 |

创建 `tests/conftest.py`，添加基础 fixture：

```python
import pytest


def pytest_configure(config):
    """注册自定义 marker（消除 pytest 警告）"""
    pass


@pytest.fixture
def sample_data():
    """示例 fixture，按需替换"""
    return {"key": "value"}
```

### Step 6：配置 pre-commit 钩子

创建 `.pre-commit-config.yaml`：

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff
        name: ruff (linter)
        entry: pixi run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: ruff (formatter)
        entry: pixi run ruff format
        language: system
        types: [python]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict

  - repo: local
    hooks:
      - id: post-merge-test
        name: run tests after merge
        entry: pixi run test
        language: system
        stages: [post-merge]
        always_run: true
        pass_filenames: false

exclude: |
  (?x)^(
    data/|
    \.pixi/|
    \.trae/|
    pixi\.lock
  )
```

**为什么用 `repo: local`？**

| | 远程 repo | `repo: local` |
|---|---------|-------------|
| 速度 | 每次 commit 先检查版本，慢几秒 | 直接执行，毫秒级 |
| 网络 | 需要连 GitHub | 不需要网络 |
| 版本管理 | 钩子独立 venv | 用项目 pixi 环境的版本 |

对于个人项目或 AI 辅助开发，`repo: local` 更快更稳定。如果项目开源需要版本锁定，可改用 `repo: https://github.com/astral-sh/ruff-pre-commit`。

安装钩子：

```bash
pixi run pre-commit install
pixi run pre-commit install --hook-type post-merge
```

### Step 7：定义 pixi 任务

在 `pixi.toml` 的 `[tasks]` 中添加：

```toml
[tasks]

[tasks.ruff-check]
cmd = "ruff check src/ tests/"

[tasks.ruff-format]
cmd = "ruff format src/ tests/"

[tasks.lint]
cmd = "ruff check --fix src/ tests/ && ruff format src/ tests/"

[tasks.pre-commit-install]
cmd = "pre-commit install && pre-commit install --hook-type post-merge"

[tasks.pre-commit-run]
cmd = "pre-commit run --all-files"

[tasks.test-unit]
cmd = "pytest tests/ -m \"unit\" --tb=short -q --durations=5 -n auto"

[tasks.test]
cmd = "pytest tests/ -m \"not integration and not slow\" --tb=short -q --durations=10 -n auto"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -q --durations=10 -n auto"
```

**三层测试命令的设计逻辑**：

| 命令 | 跑什么 | 排除什么 | 预期耗时 | 使用场景 |
|------|--------|---------|---------|---------|
| `pixi run test-unit` | `@pytest.mark.unit` | integration + slow | ~10s | 开发中频繁运行 |
| `pixi run test` | 排除 integration 和 slow | integration + slow | ~35s | 功能完成后验证 |
| `pixi run test-all` | 全量 | 无 | ~60s+ | 发版前验证 |

> **关键原则**：每个阶段只跑该跑的测试。commit 级必须 < 10 秒，否则开发者会习惯性 `--no-verify` 跳过。

**ruff 路径覆盖原则**：ruff 的检查路径必须覆盖**所有** Python 源文件目录，不留盲区。如果后续新增了 `eval/` 目录或根目录的 `main.py`，记得同步更新 ruff 任务路径。

### Step 8：配置 .gitignore

创建 `.gitignore`：

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/

# 虚拟环境
.venv/
env/

# pixi
.pixi/*
!.pixi/config.toml

# pytest
.pytest_cache/
.pytest_tmp/

# Ruff
.ruff_cache/

# 环境变量（敏感信息不得提交）
.env
.envrc

# IDE
# .vscode/
# .idea/

# 项目数据（按需调整）
data/*
!data/README.md

# 自定义
.trashbin/
```

> `.trashbin/` 是安全删除规则的要求——禁止永久删除文件，必须移入 `.trashbin/`。

### Step 9：配置环境变量模板

创建 `.env.example`：

```
# API Configuration
API_KEY="your-api-key-here"
API_BASE_URL="https://your-api-endpoint.example.com/"

# Optional: Integration Tests
# RUN_INTEGRATION_TESTS=false
```

**原则**：
- `.env.example` 提交到 Git，告诉协作者需要哪些环境变量
- `.env` 包含真实密钥，**绝对不能提交**（已在 .gitignore 中排除）
- 任何人都**禁止读取** `.env` 文件的内容

### Step 10：配置 AI 助手规则（可选但推荐）

如果你使用 Trae / Claude Code 等 AI 辅助开发工具，创建 `.trae/rules/` 目录来定义项目级规则。

#### `.trae/rules/commit-rule.md`

```markdown
---
alwaysApply: true
scene: git_message
---
# Atomic Git Commit Rules

## Core Invariants

1. **Only commit YOUR changes**: Run `git status` + `git diff` before staging. Only stage files you modified. NEVER use `git add -A` or `git add .`.
2. **Commit immediately after each logical unit of work**: todo item completed, function implemented, test created, bug fixed, config/doc changed, or any logical unit finished.
3. **Conventional Commits in English ASCII only**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` — imperative mood, concise, no non-ASCII.

## Enforcement

- All working modes (Agent/Plan/Spec): commit after each step, never batch.
- Before starting new work: check for uncommitted changes; commit first if any.
- When in doubt: **commit first, then continue.** Over-commit > under-commit.
```

#### `.trae/rules/trashbin-rule.md`

```markdown
---
alwaysApply: true
scene: file_operations
---
# Trashbin Rule — Safe File Deletion

## Core Rule

**NEVER permanently delete files.** Move to `.trashbin/` instead.

## How

```bash
mkdir -p .trashbin && mv <target> .trashbin/<target>_$(date +%Y%m%d_%H%M%S)
```
```

### Step 11：创建项目根文档

创建 `CLAUDE.md`（或 `AGENTS.md`），作为 AI 助手的项目入口文档：

```markdown
## 项目简介

- **功能**：一句话描述项目功能
- **开发目标**：核心目标

---

## 开发规范

### 版本控制

完成逻辑工作单元后立即提交，只 stage 自己修改的文件。Conventional Commits 英文格式（祈使语气）。

### 测试

Red/Green TDD 开发，每步附带 pytest 测试。

三层测试命令：

| 命令 | 用途 | 预期耗时 |
|------|------|---------|
| `pixi run test-unit` | 只跑 unit marker，开发中秒级反馈 | ~10s |
| `pixi run test` | 排除 integration 和 slow，post-merge 验证 | ~35s |
| `pixi run test-all` | 全量测试，发版前验证 | ~60s |

### 代码质量

- **日志**：使用 `loguru`，禁止 `print`
- **Lint**：修改后运行 `pixi run lint`；仅检查用 `pixi run ruff-check`

### 配置与环境

- 超参数、模型名、路径等写入配置文件，禁止硬编码
- 环境变量参考 `.env.example`，敏感信息不得提交

### 文件删除

禁止永久删除文件，必须移入 `.trashbin/`。
```

### Step 12：首次提交

```bash
git add pixi.toml pyproject.toml .pre-commit-config.yaml .gitignore .env.example
git add src/__init__.py tests/__init__.py tests/conftest.py
git add .trae/rules/commit-rule.md .trae/rules/trashbin-rule.md
git add CLAUDE.md
git commit -m "chore: initialize project with quality infrastructure"
```

此时 pre-commit 钩子会自动运行，检查所有 Python 文件。因为是空项目，应该全部通过。

### Step 13：验证

```bash
# 验证 Ruff
pixi run ruff-check
# 预期输出：All checks passed!

# 验证 pytest
pixi run test-unit
# 预期输出：collected 0 items（空项目无测试）

# 验证 pre-commit
pixi run pre-commit-run
# 预期输出：全部 Passed

# 验证 lint
pixi run lint
# 预期输出：无错误
```

---

## 5. 日常开发工作流

### 写代码

```
写代码 → 保存 → pixi run lint → 修复问题 → git add → git commit
                                                      ↓
                                                pre-commit 自动检查
                                                      ↓
                                                 通过 → commit 成功
                                                 不通过 → 修复后重新 add + commit
```

### 写测试

```python
import pytest

@pytest.mark.unit
def test_parse_config():
    """纯单元测试：mock 所有外部依赖"""
    result = parse_config("test.yaml")
    assert result["key"] == "expected_value"

@pytest.mark.integration
def test_query_real_api():
    """集成测试：触及真实外部系统"""
    result = query_api("https://real-api.example.com")
    assert result.status_code == 200

@pytest.mark.slow
def test_heavy_computation():
    """慢速测试：耗时 >5s 或需要重导入"""
    result = train_model(large_dataset)
    assert result.accuracy > 0.8
```

### 提交代码

```bash
# 1. 检查改了什么
git status
git diff

# 2. 只 stage 自己修改的文件
git add src/new_feature.py tests/test_new_feature.py

# 3. 提交（pre-commit 自动运行）
git commit -m "feat: add new feature with unit tests"
```

**Conventional Commits 格式**：

| Type | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: add hybrid retrieval support` |
| `fix` | Bug 修复 | `fix: resolve NDCG out-of-range values` |
| `docs` | 仅文档 | `docs: update evaluation guide` |
| `test` | 测试 | `test: add unit tests for chunker` |
| `refactor` | 重构 | `refactor: extract create_anthropic_client` |
| `chore` | 构建/配置/工具 | `chore: update ruff configuration` |

### 合并代码

```bash
git merge feature-xxx
# 合并完成后，post-merge 钩子自动运行 pixi run test
# 如果测试失败，可以回滚：git reset --hard ORIG_HEAD
```

---

## 6. 遇到 Ruff 报错时的决策树

```
Ruff 报了一个错误
       ↓
是真正的 bug 或代码质量问题吗？
       ↓
   ┌───┴───┐
   是      否
   ↓       ↓
 修复它   这个建议合理吗？
   ↓      ↓
 完成    ┌──┴──┐
        合理  不合理
         ↓     ↓
      接受   用 # noqa: RULE 忽略
      建议   并在旁边注释原因
```

**`# noqa` 使用规范**：

1. **精确指定规则**：用 `# noqa: E402` 而非 `# noqa`
2. **就近忽略**：只忽略出问题的那一行，不要用全局 `ignore` 代替
3. **注释原因**：对于不明显的忽略，加简短说明
4. **定期审查**：搜索 `# noqa` 确认每个忽略仍然必要

---

## 7. 渐进式引入策略（适用于已有项目）

如果项目已经有一定规模，不要试图一次性修复所有问题。分阶段启用规则：

| 阶段 | 启用规则 | 目标 |
|------|---------|------|
| 第 1 周 | `E, W, F` | 修复真正的错误和风格问题 |
| 第 2 周 | `+ I` | 统一 import 排序 |
| 第 3 周 | `+ UP` | 升级到新版 Python 写法 |
| 第 4 周 | `+ B, SIM` | 启用 bug 模式检测和简化建议 |

每个阶段用 `ruff check --fix` 自动修复能修的，手动处理剩余的，确保零错误后再进入下一阶段。

---

## 8. 常见问题

### Q: pre-commit 太慢怎么办？

Ruff 的速度是毫秒级的，通常不会感觉慢。如果确实慢，检查是否钩子配置过多，或是否有大文件被意外包含。

### Q: 可以用 `git commit --no-verify` 跳过钩子吗？

**只在紧急情况下使用**。跳过钩子意味着未经检查的代码入库，后续需要手动补检。

### Q: ruff check 报了很多错，我该一个个修吗？

不用。大部分问题可以自动修复：`pixi run ruff check --fix src/ tests/`。修完后再 `pixi run ruff-format` 格式化一下。

### Q: 如何运行单个测试方法？

```bash
pixi run pytest tests/test_file.py::TestClass::test_method -v
```

### Q: 新增了源代码目录，需要更新什么？

1. `pixi.toml` 中的 ruff 任务路径
2. `pyproject.toml` 中的 `extend-exclude`（如果需要排除）
3. `.pre-commit-config.yaml` 中的 `exclude`（如果需要排除）

### Q: 如何处理 lint 盲区？

确保 ruff 的检查路径覆盖**所有** Python 源文件。ash-easy-rag 曾因 ruff task 仅覆盖 `src/ eval/ tests/`，导致根目录的 `main.py` 包含 17 个 lint 错误而不被发现。

---

## 9. 配置文件速查表

| 文件 | 用途 | 关键配置 |
|------|------|---------|
| `pyproject.toml` | Ruff + pytest 配置 | `[tool.ruff]`, `[tool.pytest.ini_options]` |
| `pixi.toml` | 依赖 + 任务定义 | `[pypi-dependencies]`, `[tasks]` |
| `.pre-commit-config.yaml` | Git 钩子配置 | ruff, 通用检查, post-merge-test |
| `.gitignore` | Git 忽略规则 | `__pycache__/`, `.env`, `.pixi/`, `.trashbin/` |
| `.env.example` | 环境变量模板 | API key, 配置项 |
| `.trae/rules/commit-rule.md` | AI 提交规则 | Conventional Commits, 原子提交 |
| `.trae/rules/trashbin-rule.md` | AI 安全删除规则 | 禁止永久删除 |
| `CLAUDE.md` | AI 项目入口文档 | 开发规范、测试命令、代码质量要求 |

---

## 10. 质量体系成熟度自检

完成所有步骤后，对照以下清单验证：

- [ ] `pixi run ruff-check` 输出 All checks passed
- [ ] `pixi run lint` 无错误
- [ ] `pixi run test-unit` 可正常运行
- [ ] `pixi run test` 可正常运行
- [ ] `pixi run test-all` 可正常运行
- [ ] `pixi run pre-commit-run` 全部 Passed
- [ ] `git commit` 时 pre-commit 钩子自动触发
- [ ] `git merge` 后 post-merge 钩子自动触发
- [ ] `.gitignore` 排除了 `.env`、`__pycache__/`、`.pixi/`
- [ ] `.env.example` 已创建且不含真实密钥
- [ ] AI 规则文件已创建（如使用 AI 助手）
- [ ] 所有 Python 源文件目录都在 ruff 检查范围内

---

## 相关文档

- [Lint 与 pre-commit 入门指南](lint-and-precommit.md) — Linter/Ruff/pre-commit 概念入门
- [Ruff 使用指南](ruff-usage-guide.md) — 本项目 Ruff 实操手册
- [Ruff 经验与最佳实践](../.archive/v0.1.12-governance-era/project-governance/ruff-experience-and-best-practices.md) — 演进历史与新项目建议
- [测试运行指南](testing.md) — 如何运行和管理项目测试
- [测试分层与耗时预算](test-layering-and-time-budgets.md) — 分层原则与耗时预算
- [Commit Conventions](commit-conventions.md) — 提交规范深度参考
