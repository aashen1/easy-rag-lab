# 新项目质量体系引导：从 git init 到健康成长

> 本文档面向从零开始创建新 Python 项目的开发者，介绍如何从第一天就建立完整的代码质量防线，确保项目在 Ruff 检查、pytest 测试、pre-commit 钩子、Conventional Commits 等规范下健康成长。
>
> 这些实践提炼自 easy-rag-lab 项目（v0.1.0 ~ v0.1.16）的真实演进经验——该项目在无规范期积累了近 1000 个 lint 错误，最终花了多个版本才清偿完毕。本文的目标是让你不必重蹈覆辙。

---

## 1. 为什么要从第一天就建防线？

easy-rag-lab 的教训：

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

> **经验教训**：全局忽略是隐性债务。easy-rag-lab 曾全局忽略 `SIM108` 和 `E402`，导致新代码中本应修复的违规也被放行，直到移除全局忽略时才发现遗漏。

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
| `addopts` | `--basetemp=.pytest_tmp` | 临时文件放在项目根目录，减轻系统盘SSD压力（默认会生成在C盘`Temp`文件夹） |
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

确保 ruff 的检查路径覆盖**所有** Python 源文件。easy-rag-lab 曾因 ruff task 仅覆盖 `src/ eval/ tests/`，导致根目录的 `main.py` 包含 17 个 lint 错误而不被发现。

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

## 11. GitHub Template Repo：把新手包变成一键模板

上面 Step 1 ~ Step 13 是手动搭建的完整流程。但每次建新项目都走一遍，即使有文档也很容易遗漏。GitHub 提供了 **Template Repository** 功能，可以把整套质量体系打包成一个模板，新建项目时一键复制。

### 11.1 Template Repo 是什么？

Template Repo 和 Fork 的区别：

| | Fork | Template Repo |
|---|------|-------------|
| 提交历史 | 继承父仓库全部历史 | **只有一次初始提交** |
| 贡献图 | 不计入个人贡献 | **计入个人贡献** |
| 与原仓库关系 | 持续关联，可提 PR | **完全独立**，无后续关联 |
| 适用场景 | 给已有项目贡献代码 | **从零开始新项目** |

简单说：Template Repo 就是"复制一份干净的起点"，没有历史包袱，也没有和原仓库的绑定关系。

### 11.2 创建 Template Repo

**第一步：准备模板仓库的内容**

按照本文 Step 1 ~ Step 13 搭建好一个空项目骨架，包含以下文件：

```
my-python-template/
├── .github/
│   └── workflows/
│       └── ci.yml              # CI 工作流（见第 12 节）
├── .trae/
│   └── rules/
│       ├── commit-rule.md
│       └── trashbin-rule.md
├── src/
│   └── __init__.py
├── tests/
│   ├── __init__.py
│   └── conftest.py
├── .gitignore
├── .pre-commit-config.yaml
├── .env.example
├── CLAUDE.md
├── pixi.toml
└── pyproject.toml
```

**第二步：推送到 GitHub**

```bash
git remote add origin git@github.com:your-name/my-python-template.git
git push -u origin main
```

**第三步：在 GitHub 上标记为模板**

1. 打开仓库页面 → **Settings**
2. 找到 **Repository template** 区域
3. 勾选 ✅ **Template repository**
4. 保存

就这样，模板仓库就创建好了。

### 11.3 从模板创建新项目

**方式一：GitHub 网页**

1. 打开模板仓库页面
2. 点击绿色的 **Use this template** 按钮
3. 输入新仓库名称、选择可见性
4. 点击 **Create repository from template**
5. 克隆新仓库到本地

**方式二：GitHub CLI**

```bash
gh repo create my-new-project --template your-name/my-python-template --private
git clone git@github.com:your-name/my-new-project.git
cd my-new-project
```

**方式三：直接克隆（离线使用）**

如果不想依赖 GitHub 模板功能，也可以直接把模板目录复制一份：

```bash
cp -r /path/to/my-python-template /path/to/my-new-project
cd /path/to/my-new-project
rm -rf .git
git init
```

### 11.4 创建后必做的初始化

从模板创建新项目后，需要做以下定制：

```bash
# 1. 安装 pixi 依赖
pixi install

# 2. 安装 pre-commit 钩子
pixi run pre-commit-install

# 3. 修改 CLAUDE.md 中的项目名称和描述

# 4. 修改 pixi.toml 中的项目名称

# 5. 修改 .env.example 中的环境变量（按新项目需求）

# 6. 验证质量体系
pixi run ruff-check
pixi run lint
pixi run test-unit
pixi run pre-commit-run
```

### 11.5 模板维护建议

- **模板仓库用 `main` 分支**，不需要开发分支
- **不要在模板里放业务代码**，只放质量基础设施和骨架
- **模板更新后，已创建的项目不会自动同步**——这是设计如此，因为每个项目已经独立了
- 如果想传播模板的改进，可以在 README 中写明"模板版本"，让使用者自行判断是否需要手动同步

---

## 12. CI/CD：让质量防线从本地延伸到云端

前面所有的防线（pre-commit、post-merge）都运行在本地。对于个人项目这已经足够，但一旦涉及多人协作，就需要 CI/CD 来做远程门控——确保推到远程仓库的代码也必须通过检查。

### 12.1 本地防线 vs 远程防线

| 防线 | 位置 | 触发时机 | 强制性 | 覆盖范围 |
|------|------|---------|--------|---------|
| pre-commit | 本地 | `git commit` 前 | 可被 `--no-verify` 跳过 | lint + format |
| post-merge | 本地 | `git merge` 后 | 非阻塞，仅通知 | 标准测试 |
| **CI** | 远程 | push / PR 时 | **不可跳过** | lint + 测试 + 更多 |
| **PR 门控** | 远程 | 合并 PR 时 | **不通过就不让合** | CI 全部通过 |

**核心价值**：CI 是"不可跳过的防线"。即使开发者本地 `--no-verify` 跳过了 pre-commit，CI 仍然会拦截不合格的代码。

### 12.2 最小 CI 工作流

创建 `.github/workflows/ci.yml`：

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          cache: true

      - name: Lint
        run: pixi run lint

      - name: Run tests
        run: pixi run test
```

**这个配置做了什么？**

1. 每次 push 到 `main`/`dev` 或创建 PR 时自动触发
2. 在 GitHub 提供的 Ubuntu 机器上运行
3. 用 `setup-pixi` 安装 pixi 并缓存依赖
4. 跑 lint（ruff check + format）
5. 跑标准测试（排除 integration 和 slow）

**前提条件**：项目的 `pixi.toml` 必须支持 `linux-64` 平台，且不硬依赖 GPU。如果你的项目目前只配了 `win-64`，需要添加平台支持（见第 13 节）。

### 12.3 增强版 CI 工作流

在最小版基础上，可以逐步添加更多能力：

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          cache: true
      - run: pixi run lint

  test-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          cache: true
      - run: pixi run test-unit

  test-standard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          cache: true
      - run: pixi run test

  test-full:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          cache: true
      - run: pixi run test-all
```

**增强点**：

| 特性 | 说明 |
|------|------|
| **Job 拆分** | lint / test-unit / test-standard / test-full 分开跑，更快定位问题 |
| **concurrency** | 同一分支的新 push 自动取消旧的运行，节省资源 |
| **条件执行** | `test-full` 只在 push 到 main 时跑，PR 中不跑全量 |
| **缓存** | pixi 依赖缓存，加速后续运行 |

### 12.4 PR 合并门控

在 GitHub 仓库设置中配置 **Branch Protection Rules**：

1. 进入 **Settings → Branches → Branch protection rules**
2. 点击 **Add rule**，目标分支填 `main`
3. 勾选以下选项：
   - ✅ **Require status checks to pass before merging**
   - ✅ **Require branches to be up to date before merging**
   - 在 Status checks 列表中选 `lint`、`test-unit`、`test-standard`
   - ✅ **Require pull request reviews before merging**（可选）

**效果**：PR 必须等 CI 全部通过 + 至少一人 review 后才能合并。任何人都无法绕过。

### 12.5 环境变量与密钥管理

CI 中需要的环境变量（如 API Key）通过 GitHub Secrets 管理：

1. 进入 **Settings → Secrets and variables → Actions**
2. 点击 **New repository secret**
3. 添加需要的密钥（如 `LLM_API_KEY`）

在 CI 工作流中引用：

```yaml
env:
  TORCH_DEVICE: cpu
  RUN_INTEGRATION_TESTS: false

jobs:
  test-integration:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: prefix-dev/setup-pixi@v0.8.1
      - run: pixi run test-all
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          RUN_INTEGRATION_TESTS: true
```

**原则**：
- 密钥只存在 GitHub Secrets 中，永远不写在代码或配置文件里
- integration 测试只在 main 分支的 push 中运行，不在 PR 中运行（避免消耗 API 额度）

---

## 13. CUDA/GPU 项目的 CI：从"跑不了"到"跑得通"

如果你的项目用到了 PyTorch + CUDA（像本项目一样），CI 就不是加一个 workflow 文件那么简单了。GitHub 提供的免费 runner 只有 CPU，没有 GPU。这意味着你需要额外处理 GPU 依赖的问题。

### 13.1 问题出在哪？

以本项目为例，`pixi.toml` 中有以下 CUDA 相关的硬编码：

```toml
[system-requirements]
cuda = "12.6"                          # ← 告诉 pixi：这个项目需要 CUDA 12.6

[pypi-dependencies]
torch = { version = "==2.6.0+cu126" } # ← 指定 CUDA 版本的 torch
torchvision = { version = "==0.21.0+cu126" }

[pypi-options]
find-links = [
    { path = 'B:/useradmin/torch_cache' },  # ← 本地缓存路径，CI 不存在
]
```

这三行在本地开发时没问题，但到了 CI 的 Ubuntu 机器上：

| 问题 | 原因 |
|------|------|
| `cuda = "12.6"` | CI 没有 GPU，也没有 CUDA Toolkit，pixi 解析依赖时可能报错 |
| `torch==2.6.0+cu126` | `+cu126` 是 CUDA 专用版本，CPU 环境装不了 |
| `find-links` 本地路径 | `B:/useradmin/torch_cache` 在 Linux 上不存在 |

### 13.2 解决方案：pixi feature 机制

pixi 提供了 `[feature]` 机制，可以在同一个 `pixi.toml` 中定义多套环境，按需切换。核心思路是：**本地开发用 GPU 环境，CI 用 CPU 环境**。

#### 修改后的 `pixi.toml` 结构

```toml
[workspace]
name = "my-project"
version = "0.1.0"
channels = ["conda-forge"]
platforms = ["win-64", "linux-64"]    # ← 添加 linux-64

[dependencies]
python = "3.12.*"

# ==============================
# 公共依赖（GPU/CPU 通用）
# ==============================
[pypi-dependencies]
loguru = ">=0.7.3, <0.8"
python-dotenv = ">=1.2.2, <2"
pyyaml = ">=6.0.3, <7"
# ... 其他非 torch 依赖 ...

# ==============================
# GPU 环境（本地开发）
# ==============================
[feature.cuda]
system-requirements = { cuda = "12.6" }

[feature.cuda.pypi-dependencies]
torch = "==2.6.0+cu126"
torchvision = "==0.21.0+cu126"

# ==============================
# CPU 环境（CI 用）
# ==============================
[feature.cpu.pypi-dependencies]
torch = "==2.6.0+cpu"
torchvision = "==0.21.0+cpu"

# ==============================
# 环境映射
# ==============================
[environments]
default = ["cuda"]    # pixi install 默认装 GPU 版
ci = ["cpu"]          # pixi run -e ci 使用 CPU 版
```

**使用方式**：

```bash
# 本地开发（默认 GPU 环境）
pixi install
pixi run test

# CI 中（CPU 环境）
pixi install -e ci
pixi run -e ci test
```

#### 处理 find-links 本地缓存

`find-links` 中的本地路径不应该提交到仓库。有两种处理方式：

**方式一：移到用户级 pixi 配置**

```bash
# 在 ~/.pixi/config.toml 中配置（不提交到仓库）
[pypi-config]
find-links = ["B:/useradmin/torch_cache"]
```

**方式二：改用 PyTorch 官方镜像源**

```toml
[pypi-options]
index-url = "https://pypi.org/simple"
extra-index-urls = ["https://download.pytorch.org/whl/cu126"]
```

这样 pixi 会直接从 PyTorch 官方下载 CUDA 版 wheel，不需要本地缓存。

### 13.3 CPU 环境的 CI 工作流

配置好 pixi feature 后，CI 工作流就很简单了：

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          environments: ci        # ← 使用 CPU 环境
          cache: true

      - name: Lint
        run: pixi run -e ci lint

      - name: Run tests
        run: pixi run -e ci test
        env:
          TORCH_DEVICE: cpu       # ← 告诉代码用 CPU
```

### 13.4 代码中处理 GPU/CPU 兼容

除了依赖管理，代码中也需要处理设备兼容性。典型做法是读取环境变量：

```python
import os
import torch

def get_device() -> str:
    """获取计算设备，支持环境变量覆盖"""
    device = os.getenv("TORCH_DEVICE", "cuda")
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    return device
```

配置文件中同理，把硬编码的 `device: "cuda"` 改为支持环境变量覆盖。

### 13.5 如果 CI 中也需要 GPU 怎么办？

有些测试确实需要 GPU 才能跑（比如验证 CUDA kernel 是否正确、模型是否真的在 GPU 上运行）。这种情况下，GitHub 免费的 CPU runner 就不够用了，需要 **自托管 GPU Runner**。

#### 方案一：自托管 Runner（自己买机器）

**你需要准备**：

1. **一台有 NVIDIA GPU 的服务器**（物理机或云主机）
   - 最低配置：一张 T4 / GTX 1080 即可
   - 推荐配置：A10 / V100（性价比好）
   - 操作系统：Ubuntu 22.04 LTS

2. **安装基础软件**：

```bash
# NVIDIA 驱动（确保 nvidia-smi 可用）
sudo apt install nvidia-driver-535

# Docker
curl -fsSL https://get.docker.com | sh

# NVIDIA Container Toolkit（让 Docker 能用 GPU）
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

# 验证
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi
```

3. **注册 GitHub Actions Runner**：

```bash
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
tar xzf ./actions-runner-linux-x64.tar.gz

# 在 GitHub 仓库的 Settings → Actions → Runners → New self-hosted runner
# 页面中获取 token，然后：
./config.sh --url https://github.com/your-org/your-repo --token YOUR_TOKEN

# 安装为系统服务（开机自启）
sudo ./svc.sh install
sudo ./svc.sh start
```

4. **给 Runner 打标签**：

注册时给 Runner 打上 `gpu` 标签，方便工作流指定：

```yaml
jobs:
  test-gpu:
    runs-on: [self-hosted, linux, gpu]   # ← 只在有 GPU 的 runner 上跑
    steps:
      - uses: actions/checkout@v4
      - run: pixi run test-all
```

#### 方案二：云 GPU Runner（按需租用）

如果不想自己维护服务器，可以用云服务提供的 GPU CI：

| 服务 | GPU 型号 | 大致价格 | 特点 |
|------|---------|---------|------|
| **GitHub-hosted GPU**（Beta） | T4 | ~$0.04/min | 官方支持，配置最简单 |
| **Lambda Cloud** | A100 / H100 | ~$1.10/hr | 性能强，按小时计费 |
| **RunPod** | A100 / A6000 | ~$1.64/hr | 支持 Serverless 模式 |
| **Google Cloud** | T4 / L4 / A100 | 按需定价 | GCP 生态集成 |

> **GitHub-hosted GPU Runner** 目前还在 Beta 阶段，需要申请。如果获批，使用方式和普通 runner 一样简单：
>
> ```yaml
> jobs:
>   test-gpu:
>     runs-on: ubuntu-24.04-gpu        # ← GitHub 提供的 GPU runner
>     steps:
>       - uses: actions/checkout@v4
>       - run: pixi run test-all
> ```

#### 方案三：Docker 容器 + GPU（推荐）

在自托管 Runner 上，用 Docker 容器隔离每次运行的环境：

```yaml
jobs:
  test-gpu:
    runs-on: [self-hosted, linux, gpu]
    container:
      image: pytorch/pytorch:2.6.0-cuda12.6-cudnn9-devel
      options: --gpus all --shm-size=2gb
    steps:
      - uses: actions/checkout@v4

      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          environments: cuda
          cache: true

      - name: Verify GPU
        run: python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0)}')"

      - name: Run all tests
        run: pixi run -e cuda test-all
```

**为什么推荐容器？**

| | 裸机运行 | Docker 容器 |
|---|---------|------------|
| 环境隔离 | ❌ 测试之间可能互相影响 | ✅ 每次运行都是干净环境 |
| 依赖管理 | 需要手动安装 | 镜像自带所有依赖 |
| 安全性 | 测试代码直接跑在宿主机 | 容器内运行，限制权限 |
| 可复现性 | 依赖宿主机状态 | 镜像版本锁定，完全可复现 |

### 13.6 推荐的渐进式实施路径

不要一上来就搞 GPU CI。按以下顺序逐步推进：

```
阶段 1：CPU-only CI（立即可做）
├── pixi.toml 添加 linux-64 平台
├── pixi.toml 添加 [feature.cpu] 环境
├── 代码中处理 TORCH_DEVICE 环境变量
├── 创建 .github/workflows/ci.yml
└── 配置 PR 合并门控

阶段 2：GPU 测试标记（准备期）
├── 给需要 GPU 的测试加 @pytest.mark.gpu
├── CI 中用 -m "not gpu" 排除 GPU 测试
└── 本地手动跑 GPU 测试验证

阶段 3：自托管 GPU Runner（按需实施）
├── 准备 GPU 服务器
├── 安装 NVIDIA 驱动 + Docker + Container Toolkit
├── 注册 GitHub Actions Runner
├── 配置 GPU CI 工作流
└── 验证 GPU 测试在 CI 中通过
```

**阶段 1 可以在半天内完成**，而且已经能覆盖 90% 的质量门控需求——大部分测试用 mock，不需要真 GPU。阶段 3 是锦上添花，等团队有需要再投入。

### 13.7 常见问题

#### Q: CPU 版 torch 和 CUDA 版 torch 的测试结果会不一样吗？

大部分不会。纯 Python 逻辑的计算结果在 CPU 和 GPU 上完全一致。只有以下情况可能不同：
- 浮点精度（GPU 的 FP16 和 CPU 的 FP32 有微小差异）
- CUDA 特有 API（如 `torch.cuda.synchronize()`）
- 显存相关行为（如 OOM 只在 GPU 上出现）

所以 CPU CI 跑的是"逻辑正确性"，GPU CI 跑的是"GPU 兼容性"。两者互补。

#### Q: pixi feature 机制成熟吗？

pixi 的 feature/environments 是其核心功能之一，已经稳定可用。详见 [pixi 官方文档](https://pixi.sh/latest/features/multi_environment/)。

#### Q: 自托管 Runner 安全吗？

自托管 Runner 有安全风险：恶意 PR 可能执行任意代码。建议：
- 只对可信的仓库启用
- 使用 Docker 容器隔离
- PR 中只跑 lint + unit test，不跑需要 secrets 的任务
- 参考 [GitHub 官方安全指南](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)

---

## 相关文档

- [Lint 与 pre-commit 入门指南](lint-and-precommit.md) — Linter/Ruff/pre-commit 概念入门
- [Ruff 使用指南](ruff-usage-guide.md) — 本项目 Ruff 实操手册
- [Ruff 经验与最佳实践](../.archive/v0.1.12-governance-era/project-governance/ruff-experience-and-best-practices.md) — 演进历史与新项目建议
- [测试运行指南](testing.md) — 如何运行和管理项目测试
- [测试分层与耗时预算](test-layering-and-time-budgets.md) — 分层原则与耗时预算
- [Commit Conventions](commit-conventions.md) — 提交规范深度参考
- [CI/CD 接入计划书](../.archive/v0.1.9-dual-eval-era/project-hygiene/cicd-integration-plan.md) — 本项目 CI/CD 接入的详细分析
