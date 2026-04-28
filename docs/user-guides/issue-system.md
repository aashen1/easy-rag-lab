# Issue 管理系统使用指南

项目使用基于文件的 issue 管理系统，通过 CLI 工具操作，所有 issue 存储在 `.issues/` 目录下。

---

## 快速开始

```bash
# 创建一个 bug
pixi run issue create -t bug -T "解析 PDF 时内存溢出"

# 创建一个功能需求（带优先级和标签）
pixi run issue create -t feat -T "添加 reranker 支持" -p high -l "retrieval,enhancement"

# 查看所有活跃 issue
pixi run issue list

# 开始处理某个 issue
pixi run issue start BUG-260427-003-wt1

# 完成某个 issue
pixi run issue done BUG-260427-003-wt1
```

---

## Issue 类型

| 类型 | 缩写 | 用途 |
|------|------|------|
| `bug` | BUG | 缺陷、错误 |
| `feat` | FEAT | 新功能 |
| `rf` | RF | 重构（不改变行为） |
| `opt` | OPT | 性能优化 |
| `inv` | INV | 调研、分析 |
| `test` | TEST | 测试相关 |

## Issue 状态

```
todo → in_progress → review → done
  ↓
deferred   cancelled
```

| 状态 | 含义 |
|------|------|
| `todo` | 待处理 |
| `in_progress` | 正在处理 |
| `review` | 评审中 |
| `done` | 已完成 |
| `deferred` | 已延期 |
| `cancelled` | 已取消 |

## 优先级

| 优先级 | 含义 |
|--------|------|
| `high` | 高优先级，阻塞其他工作 |
| `medium` | 中优先级（默认） |
| `low` | 低优先级，有空再做 |

---

## 常用命令

### 创建 Issue

```bash
# 基本创建
pixi run issue create -t <type> -T "<title>"

# 完整参数
pixi run issue create -t bug -T "标题" -p high -l "label1,label2" -m v0.2.0 -s TODO.md
```

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--type` | `-t` | Issue 类型（必需） |
| `--title` | `-T` | 标题（必需） |
| `--priority` | `-p` | 优先级，默认 medium |
| `--labels` | `-l` | 标签，逗号分隔 |
| `--milestone` | `-m` | 里程碑 |
| `--source` | `-s` | 来源 |

### 查看 Issue

```bash
# 查看单个 issue（支持部分 ID 匹配）
pixi run issue show BUG-260427-003-wt1
pixi run issue show BUG-260427        # 部分匹配

# 列出活跃 issue
pixi run issue list

# 列出所有 issue（含已完成）
pixi run issue list --all

# 按条件过滤
pixi run issue list --status todo
pixi run issue list --type bug
pixi run issue list --priority high
pixi run issue list --labels retrieval
```

### 更新 Issue

```bash
# 更新字段
pixi run issue update <id> --priority high
pixi run issue update <id> --title "新标题"
pixi run issue update <id> --add-label urgent
pixi run issue update <id> --remove-label low-priority
```

### 状态流转

```bash
pixi run issue start <id>      # todo → in_progress
pixi run issue review <id>     # in_progress → review
pixi run issue done <id>       # review → done
pixi run issue defer <id>      # → deferred
pixi run issue cancel <id>     # → cancelled
```

> 注意：`done` 状态不可回退。如需恢复，使用 `deferred` 或 `cancelled` 的回退路径。

### 汇总统计

```bash
# 终端打印汇总表
pixi run issue summary

# 保存到文件
pixi run issue summary --save

# 指定输出路径
pixi run issue summary --save -o custom-path.md
```

### AI 上下文管理

```bash
# 查看当前聚焦的 issue
pixi run issue context

# 手动聚焦某个 issue
pixi run issue focus <id>

# 取消聚焦
pixi run issue unfocus <id>
```

---

## 目录结构

```
.issues/
├── config.yml          # 配置文件
├── context.md          # AI 上下文
├── active/             # 活跃 issue（todo/in_progress/review）
├── completed/          # 已完成（按月归档）
│   └── 2026-04/
├── deferred/           # 已延期
└── cancelled/          # 已取消
```

---

## Worktree 管理

如果你使用 git worktree 多分支并行开发，需要配置 worktree 映射：

```bash
# 查看当前 worktree
pixi run issue worktree

# 添加映射
pixi run issue worktree add "w1-easy-rag-feature-x" wt2

# 设置友好名称
pixi run issue worktree name wt2 "feature-x"

# 列出所有映射
pixi run issue worktree list

# 删除映射
pixi run issue worktree remove wt2
```

配置存储在 `.issues/config.yml` 中，通过 git 同步到所有 worktree。

---

## 与旧系统的关系

原 `docs/backlog.md` 已迁移至 `docs/archive/backlog-2026-04-28.md`。所有 169 条 issue 已迁移到新系统，原编号保存在 `legacy_id` 字段中。

如需查找原编号对应的 issue：

```bash
# 按旧编号搜索
pixi run issue list --all | grep BUG-032
```

---

## 常见问题

### Q: ID 太长记不住怎么办？

使用部分 ID 匹配，只需输入足够区分的部分即可：

```bash
pixi run issue show BUG-260427    # 省略序号和 wt_id
pixi run issue show 003-wt1       # 只输入序号和 wt_id
```

### Q: 误操作了状态怎么办？

`deferred` 和 `cancelled` 可以回到 `todo`：

```bash
pixi run issue update <id> --status todo
```

但 `done` 不可回退，这是有意设计，防止已完成 issue 被误操作。

### Q: 如何批量查看某类 issue？

组合使用过滤参数：

```bash
# 所有高优先级 bug
pixi run issue list --type bug --priority high

# 所有待处理的功能需求
pixi run issue list --type feat --status todo
```
