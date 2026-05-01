# Lint 与 pre-commit 入门指南

> 本文档面向 Python 开发初学者，讲解 Linter、Ruff 和 pre-commit 三个工具的概念与使用。

---

## 1. Linter 是什么？

**一句话**：Linter 是代码的"语法+风格检查器"。

### 类比理解

你写中文文章时，Word 会标出：
- 🔴 拼写错误（"recieve" → "receive"）→ 对应 Linter 的**错误检测**
- 🟡 语法不通（"他们的去了"）→ 对应 Linter 的**代码风格检查**
- 🔵 建议改写（"由于...的原因" → "因为"）→ 对应 Linter 的**简化建议**

Linter 对代码做同样的事，但更快、更准确。

### Linter 能发现什么？

| 问题类型 | 示例 | 后果 |
|---------|------|------|
| 未使用的导入 | `import os` 但从没用 `os` | 代码混乱，增加阅读负担 |
| 未定义变量 | 写了 `result` 但拼成了 `reslut` | 运行时报错 |
| 重复导入 | `import json` 写了两遍 | 代码冗余 |
| 不推荐的写法 | 用 `typing.List` 而非 `list` | 过时写法，新版本有更好的替代 |
| 代码风格不统一 | 有的地方 2 空格缩进，有的 4 空格 | 团队协作时难以阅读 |

### Linter 不能发现什么？

Linter 是**静态分析**工具——它只读代码，不运行代码。所以它发现不了：
- 逻辑错误（如把 `>` 写成 `>=`）
- 运行时错误（如除以零、文件不存在）
- 性能问题（如 O(n²) 算法）

这些需要**测试**和**性能分析**工具来发现。

---

## 2. Ruff 是什么？

**一句话**：Ruff 是一个用 Rust 写的超快 Python Linter + Formatter，一个工具替代多个老工具。

### 替代关系

```
以前你需要安装：          现在只需要：
├── flake8    (检查错误)   └── ruff (全包揽)
├── black     (格式化)
├── isort     (排序import)
├── pydocstyle(检查docstring)
└── ...更多插件
```

### 为什么 Ruff 更好？

| 对比项 | 传统方案 (flake8+black+isort) | Ruff |
|--------|------------------------------|------|
| 速度 | 几秒到几十秒 | 毫秒级（快 10-100 倍） |
| 安装 | 3+ 个包 + 插件 | 1 个包 |
| 配置 | 多个配置文件协调 | 1 个 pyproject.toml |
| 规则冲突 | 需要手动解决 | 内置兼容 |

### 本项目的 Ruff 配置

配置文件：`pyproject.toml` 中的 `[tool.ruff]` 部分

**启用的规则集**（初期宽松策略）：

| 规则集 | 来源 | 检查什么 |
|--------|------|---------|
| E, W | pycodestyle | Python 官方风格（缩进、空格、空行等） |
| F | pyflakes | 真正的代码错误（未定义变量、重复导入等） |
| I | isort | import 语句排序 |
| UP | pyupgrade | 建议使用新版 Python 的更优写法 |
| B | flake8-bugbear | 常见 bug 模式 |
| SIM | flake8-simplify | 代码简化建议 |

**全局忽略的规则**：

| 规则 | 原因 |
|------|------|
| E501 (行过长) | Formatter 会自动处理折行 |
| B008 (默认参数调用函数) | FastAPI 常用模式 |

**按需行级忽略的规则**（不全局忽略，在具体行用 `# noqa: 规则名` 豁免）：

| 规则 | 说明 | 典型场景 |
|------|------|----------|
| SIM108 (三元表达式) | 有时可读性更差 | 复杂条件分支用 if-else 更清晰时 |
| E402 (import 不在文件顶部) | `sys.path.insert` 或 `warnings.warn` 后的 import 必须延迟 | `run_eval.py`、`run_experiment.py` |

### 日常使用

```bash
# 检查代码问题（不修改文件，只报告）
pixi run ruff-check

# 格式化代码（会修改文件）
pixi run ruff-format

# 一键检查+格式化
pixi run lint

# 自动修复能修的问题
pixi run ruff check --fix src/ eval/ tests/
```

### 首次扫描结果

```
Found 982 errors.
[*] 832 fixable with the `--fix` option.
```

这是正常的——项目之前没用过 linter，积累了大量风格问题。其中大部分是：
- `UP006/UP007`：用 `list/dict` 替代 `typing.List/Dict`（Python 3.9+ 新写法）
- `I001`：import 语句排序
- `F401`：未使用的导入

**处理策略**：初期不强制修复，后续逐步收紧。可以按模块逐个 `ruff check --fix` 修复。

---

## 3. pre-commit 是什么？

**一句话**：pre-commit 是 Git 钩子管理器，在你 `git commit` 之前和 `git merge` 之后自动运行检查。

### 工作流程

#### commit 前检查（防止坏代码提交）

```
你执行 git commit
       ↓
pre-commit 自动运行所有钩子
       ↓
  ┌────┴────┐
  ↓         ↓
通过      不通过
  ↓         ↓
commit   commit 被阻止
成功      ↓
          钩子可能已自动修复了一些文件
          ↓
          你需要 git add 修改后的文件
          ↓
          再次 git commit
```

#### merge 后检查（确认合并没闯祸）

```
你在 dev/main 分支执行 git merge feature-xxx
       ↓
   合并成功完成
       ↓
post-merge 钩子自动触发
       ↓
   运行 pytest 单元测试
       ↓
  ┌────┴────┐
  ↓         ↓
通过      不通过
  ↓         ↓
一切正常   打印失败信息
继续工作    提示 git reset --hard ORIG_HEAD 回滚
```

**为什么合并后需要单独跑测试？** 两个功能分支各自测试都通过，但合到一起可能出问题——比如分支 A 改了某个函数的接口，分支 B 还在用旧接口调用。commit 前的 lint/format 检查抓不到这种问题，只有跑测试才能发现。

### 本项目配置的钩子

配置文件：`.pre-commit-config.yaml`

#### commit 前钩子（`git commit` 时自动触发）

| 钩子 | 做什么 | 为什么需要 |
|------|--------|-----------|
| ruff (linter) | 检查代码问题，能修的自动修 | 防止低质量代码入库 |
| ruff (formatter) | 格式化代码 | 统一代码风格 |
| trailing-whitespace | 删除行尾空格 | 避免无意义的 diff 噪音 |
| end-of-file-fixer | 确保文件末尾有换行符 | 符合 POSIX 标准 |
| check-yaml | 验证 YAML 语法 | 防止配置文件写错 |
| check-merge-conflict | 检测未解决的合并冲突 | 防止冲突标记入库 |

> **注意**：ruff 钩子使用 `repo: local` 配置，直接用 pixi 环境里的 ruff，
> 不需要连 GitHub，commit 速度快（毫秒级）。版本由 `pixi.toml` 控制。

#### merge 后钩子（`git merge` 完成后自动触发）

| 钩子 | 做什么 | 为什么需要 |
|------|--------|-----------|
| post-merge-test | 跑 pytest 标准测试（跳过 integration 和 slow 测试） | 确认合并后的代码整体没闯祸 |

### 日常使用

```bash
# 首次安装（只需一次，以后 commit 和 merge 自动触发）
pixi run pre-commit-install

# 手动运行所有钩子（不 commit 也能检查）
pixi run pre-commit-run

# 手动跑纯单元测试（秒级反馈，开发中频繁使用）
pixi run test-unit

# 手动跑标准测试（跳过 integration 和 slow）
pixi run test

# 手动跑全部测试（包括 integration 和 slow）
pixi run test-all

# 紧急跳过钩子（只在紧急情况使用！）
git commit --no-verify -m "emergency fix"
```

---

## 4. 两者配合的效果

### commit 前：格式与语法防线

```
写代码 → git add → git commit
                        ↓
                  pre-commit 触发
                        ↓
              ┌─────────┴─────────┐
              ↓                   ↓
         ruff check           ruff format
         (检查问题)           (格式化代码)
              ↓                   ↓
         有问题？             格式不对？
              ↓                   ↓
         自动修/报错          自动修好
              ↓                   ↓
              └─────────┬─────────┘
                        ↓
                  文件被修改了？
                   ↓         ↓
                  是         否
                   ↓         ↓
              commit失败   commit成功
              重新add再提交
```

### merge 后：功能正确性防线

```
功能分支各自开发、各自测试通过
                ↓
     git merge 合并到 dev/main
                ↓
        post-merge 钩子自动触发
                ↓
          运行 pytest 单元测试
                ↓
         ┌──────┴──────┐
         ↓             ↓
       通过          不通过
         ↓             ↓
     一切正常     提示回滚命令
     继续工作     git reset --hard ORIG_HEAD
```

**核心价值**：commit 前管格式和语法，merge 后管功能正确性，两层防线各管一段。

---

## 5. 常见问题

### Q: ruff check 报了很多错，我该一个个修吗？

不用。大部分问题可以自动修复：
```bash
pixi run ruff check --fix src/ eval/ tests/
```
修完后再 `ruff format` 格式化一下就行。

### Q: pre-commit 太慢了怎么办？

Ruff 的速度是毫秒级的，通常不会感觉慢。如果确实慢，检查是不是钩子配置太多了。

### Q: `repo: local` 和 `repo: https://...` 有什么区别？

pre-commit 的钩子有两种来源方式：

| | 远程 repo | `repo: local` |
|---|---------|-------------|
| 配置 | 指向 GitHub 仓库 | 直接运行本地命令 |
| 速度 | 每次先 `git fetch` 检查版本，慢几秒 | 直接执行，毫秒级 |
| 网络 | 需要能连 GitHub | 不需要网络 |
| 隔离性 | 钩子用独立 venv 环境 | 用项目当前环境 |
| 适用场景 | 多人协作项目，版本锁定 | 个人项目 / AI 开发 |

本项目使用 `repo: local`，因为：
1. 个人项目 + AI 开发，高频 commit 需要速度快
2. ruff 版本已由 pixi 管理，不需要钩子再维护一份
3. 不依赖 GitHub 网络，断网也能正常 commit

如果你想切回远程 repo 方式（比如项目开源后需要版本锁定），把 ruff 钩子
改回 `repo: https://github.com/astral-sh/ruff-pre-commit` 即可。

### Q: 我只想检查我改的文件，不想检查整个项目？

pre-commit 默认只检查你 staged（git add 了）的文件，不会检查整个项目。

### Q: ruff format 和 ruff check --fix 有什么区别？

- `ruff check --fix`：修复**代码问题**（如未使用的导入、排序不对的 import）
- `ruff format`：修复**格式问题**（如缩进、空格、换行）

两者互补，通常先 check 再 format。

### Q: 我不同意 ruff 的某个建议怎么办？

在 `pyproject.toml` 的 `[tool.ruff.lint]` → `ignore` 列表中添加该规则的编号。
例如不想检查行长度，就加 `"E501"`。

也可以在代码中用 `# noqa: E501` 忽略某一行的特定规则。
