# Issue 系统重构计划

## 一、决策摘要

| 决策项        | 结论                                                                                      |
| ---------- | --------------------------------------------------------------------------------------- |
| ID 格式      | `<TYPE>-<YYYYMMDD>-<SEQ>-<WTID>`，如 `BUG-260427-003-wt1`                                 |
| 目录位置       | `.issues/`                                                                              |
| 汇总表        | 脚本生成，可 CLI 打印或保存，可选自动/手动更新                                                              |
| 状态         | 四状态：`todo → in_progress → review → done`                                                |
| 字段         | 全部保留：id, title, status, priority, labels, assignee, milestone, created\_at, updated\_at |
| context.md | 混合维护（AI 自动生成 + 人类可手动调整）                                                                 |
| 实现优先级      | 先 CLI，MCP 后续                                                                            |
| 迁移策略       | 一次性迁移                                                                                   |

***

## 二、目录结构设计

```
.issues/
├── config.yml                    # 全局配置（worktree_id 映射等）
├── context.md                    # AI 上下文（当前聚焦的 3-5 条 issue）
├── _summary.md                   # 汇总表快照（gitignore，可选自动生成）
├── active/                       # 待处理 + 进行中 + 评审中
│   ├── BUG-260427-003-wt1-llm-report-prefix.md
│   ├── FEAT-260427-001-wt1-issue-system-refactor.md
│   └── ...
├── completed/                    # 已完成（按月归档）
│   └── 2026-04/
│       ├── RF-260421-001-wt1-project-structure.md
│       └── ...
├── deferred/                     # 已延期
│   └── ...
└── cancelled/                    # 已取消
    └── ...
```

***

## 三、Issue 文件格式

```yaml
---
id: BUG-260427-003-wt1
title: "LLM 报告开头'好的'毛病反复出现"
type: bug
status: todo
priority: medium
labels: [llm-report, prompt]
assignee: null
milestone: null
created_at: 2026-04-27T14:30:22+08:00
updated_at: 2026-04-27T14:30:22+08:00
source: TODO.md
---

## 问题描述

2026年4月26日9:29，LLM 报告开头出现"好的"前缀...

## 根因分析

（待填写）

## 修复方向

（待填写）

## 更新记录

- 2026-04-27：创建
```

***

## 四、config.yml 格式

```yaml
# .issues/config.yml（只有一份，在 main worktree 维护，通过 git 同步）
# 基于路径映射自动识别 wt_id，避免多 worktree 的 config.yml 冲突

worktree_mapping:
  "w1-easy-rag": wt1
  "w1-easy-rag-feature-x": wt2
  "w1-easy-rag-bugfix": wt3

worktree_names:
  wt1: main-dev
  wt2: feature-x
  wt3: bugfix-y

# 汇总表配置
summary:
  auto_generate: false              # 是否在 issue 变更时自动生成
  output_file: _summary.md          # 输出文件名

# 状态流转规则
status_flow:
  - todo
  - in_progress
  - review
  - done
  - deferred
  - cancelled
```

**wt\_id 识别逻辑**：

1. CLI 启动时获取 `os.getcwd()` 或 `git rev-parse --show-toplevel`
2. 提取路径中的文件夹名（如 `w1-easy-rag-feature-x`）
3. 在 `worktree_mapping` 中查找匹配的 key
4. 返回对应的 `wt_id`
5. 如果没找到，提示用户运行 `pixi run issue worktree add` 添加映射

***

## 五、CLI 命令设计

### 5.1 基础命令

```bash
# 创建 issue
pixi run issue create --type bug --title "xxx" --priority high --labels a,b

# 查看 issue
pixi run issue show BUG-260427-003-wt1

# 列出 issue
pixi run issue list                          # 默认列出 active
pixi run issue list --status todo            # 按状态过滤
pixi run issue list --type bug               # 按类型过滤
pixi run issue list --priority high          # 按优先级过滤
pixi run issue list --labels llm-report      # 按标签过滤
pixi run issue list --all                    # 包含已完成

# 更新 issue
pixi run issue update BUG-260427-003-wt1 --status in_progress
pixi run issue update BUG-260427-003-wt1 --priority high
pixi run issue update BUG-260427-003-wt1 --add-label urgent

# 状态流转
pixi run issue start BUG-260427-003-wt1      # todo → in_progress
pixi run issue review BUG-260427-003-wt1     # in_progress → review
pixi run issue done BUG-260427-003-wt1       # review → done
pixi run issue defer BUG-260427-003-wt1      # → deferred
pixi run issue cancel BUG-260427-003-wt1     # → cancelled
```

### 5.2 汇总命令

```bash
# 打印汇总表到 CLI
pixi run issue summary

# 保存汇总表到文件
pixi run issue summary --save

# 保存到指定文件
pixi run issue summary --save --output custom-summary.md
```

### 5.3 context.md 命令

```bash
# 生成 context.md（扫描 in_progress 状态的 issue）
pixi run issue context

# 手动添加到 context
pixi run issue focus BUG-260427-003-wt1

# 从 context 移除
pixi run issue unfocus BUG-260427-003-wt1
```

### 5.4 worktree 管理命令

```bash
# 查看当前 worktree 信息（自动检测）
pixi run issue worktree

# 添加新的 worktree 映射
pixi run issue worktree add "w1-easy-rag-new-feature" wt4

# 设置 worktree 名称（可选，用于人类可读）
pixi run issue worktree name wt4 "new-feature"

# 列出所有 worktree 映射
pixi run issue worktree list

# 删除 worktree 映射
pixi run issue worktree remove wt4
```

### 5.5 迁移命令

```bash
# 从 backlog.md 迁移（一次性）
pixi run issue migrate --from-backlog

# 验证迁移结果
pixi run issue migrate --verify
```

***

## 六、实现步骤

### Phase 1：基础设施（CLI 框架 + 目录结构）

1. **创建 CLI 入口**

   * 文件：`src/issue_cli.py`

   * 使用 Click/Typer 框架

   * 注册 pixi task：`issue`

2. **创建目录结构**

   * `.issues/` 目录

   * `.issues/config.yml` 模板

   * `.gitignore` 添加 `_summary.md`

3. **实现 config 管理**

   * 读取/写入 `.issues/config.yml`

   * 基于路径自动识别 wt\_id

   * worktree 映射管理（add/remove/list）

### Phase 2：核心功能（CRUD + 状态流转）

1. **实现 ID 生成器**

   * 格式：`<TYPE>-<YYYYMMDD>-<SEQ>-<WTID>`

   * 序列号管理：每个 worktree 独立序列

   * 类型枚举：BUG, FEAT, RF, OPT, INV, TEST

2. **实现 issue 创建**

   * 解析命令行参数

   * 生成 YAML front matter

   * 创建 MD 文件

3. **实现 issue 查询**

   * `show`：读取单个文件

   * `list`：扫描目录，支持过滤

4. **实现 issue 更新**

   * 修改 YAML front matter

   * 更新 `updated_at`

   * 状态流转校验

5. **实现状态流转命令**

   * `start/review/done/defer/cancel`

   * 文件移动（active → completed/deferred/cancelled）

### Phase 3：辅助功能（汇总 + context）

1. **实现汇总表生成**

   * 扫描所有 issue

   * 按类型分组统计

   * 生成 Markdown 表格

   * 支持 CLI 打印和文件保存

2. **实现 context.md 管理**

   * 扫描 `in_progress` 状态 issue

   * 生成简洁摘要

   * 支持 `focus/unfocus` 手动调整

### Phase 4：迁移

1. **编写迁移脚本**

   * 解析 `docs/backlog.md` 表格

   * 生成 issue 文件

   * 保留原始编号作为 `legacy_id` 字段

   * 迁移 TODO.md 中的归档标记

2. **执行迁移**

   * 备份现有文件

   * 运行迁移脚本

   * 验证迁移结果

3. **清理旧系统**

   * 归档 `docs/backlog.md` 到 `docs/archive/`

   * 更新 `TODO.md` 引用

### Phase 5：集成

1. **更新 todo-archiver skill**

   * 改为调用 CLI 创建 issue

   * 不再写入 backlog.md

2. **更新 project-memory skill**

   * 读取 `.issues/context.md`

   * 状态统计改为调用 CLI

3. **更新 CLAUDE.md**

   * 添加 issue 系统使用说明

   * 更新"当前状态"部分

***

## 七、文件清单

| 文件                                    | 用途                   | 新增/修改 |
| ------------------------------------- | -------------------- | ----- |
| `src/issue/__init__.py`               | 模块入口                 | 新增    |
| `src/issue/cli.py`                    | CLI 命令定义             | 新增    |
| `src/issue/manager.py`                | issue 管理核心逻辑         | 新增    |
| `src/issue/models.py`                 | 数据模型（Pydantic）       | 新增    |
| `src/issue/id_generator.py`           | ID 生成器               | 新增    |
| `src/issue/config.py`                 | 配置管理 + wt_id 识别      | 新增    |
| `src/issue/migrate.py`                | 迁移脚本                 | 新增    |
| `.issues/config.yml`                  | 配置文件                 | 新增    |
| `.issues/context.md`                  | AI 上下文               | 新增    |
| `.gitignore`                          | 忽略 `_summary.md`     | 修改    |
| `pyproject.toml`                      | 添加依赖（click/pydantic） | 修改    |
| `pixi.toml`                           | 添加 `issue` task      | 修改    |
| `.trae/skills/todo-archiver/SKILL.md` | 更新归档流程               | 修改    |
| `CLAUDE.md`                           | 添加 issue 系统说明        | 修改    |

***

## 八、依赖

* `click` 或 `typer`：CLI 框架

* `pydantic`：数据验证

* `python-frontmatter`：YAML front matter 解析

* `pyyaml`：YAML 处理

***

## 九、风险与缓解

| 风险             | 缓解措施                                     |
| -------------- | ---------------------------------------- |
| 迁移数据丢失         | 迁移前备份，保留 `legacy_id` 字段                  |
| worktree 路径未映射 | CLI 检测到未映射路径时提示用户运行 `worktree add`       |
| 序列号溢出          | 序列号用 3 位数，单 worktree 单日最多 999 个 issue，足够 |
| 状态流转误操作        | CLI 校验非法流转，返回错误提示                        |

***

## 十、验收标准

1. **功能验收**

   * [ ] `pixi run issue create` 能创建 issue 文件

   * [ ] `pixi run issue list` 能列出 issue

   * [ ] `pixi run issue show` 能查看详情

   * [ ] 状态流转命令正常工作

   * [ ] 汇总表生成正确

   * [ ] context.md 生成正确

2. **迁移验收**

   * [ ] 所有 backlog.md 中的 issue 已迁移

   * [ ] `legacy_id` 字段正确对应原编号

   * [ ] 统计数据一致

3. **集成验收**

   * [ ] todo-archiver skill 正常工作

   * [ ] CLAUDE.md 更新完整
