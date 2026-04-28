# Issue 系统重构开发手记

> 面向 AI 和开发者的上下文恢复文档。新 session 读此文档即可理解系统设计意图与实现细节。

---

## 一、背景与痛点

原系统使用 `docs/backlog.md`（单文件 280+ 行 Markdown 表格）+ `TODO.md` 管理 issue，存在四大痛点：

1. **多 worktree 编号冲突**：全局递增编号（BUG-032）在多 worktree 并行开发时必然撞车
2. **状态同步延迟**：TODO.md ↔ backlog.md 双向同步依赖手动触发
3. **Token 消耗过大**：AI 每次归档需完整读取 280+ 行文件
4. **信息粒度不统一**：高优先级 issue 有详情文件，普通 issue 只有表格一句话

## 二、设计决策记录

### 2.1 ID 格式

**最终方案**：`<TYPE>-<YYYYMMDD>-<SEQ>-<WTID>`

示例：`BUG-260427-003-wt1`

| 决策因素 | 分析 |
|----------|------|
| 唯一性 | 时间戳 + worktree_id 天然隔离，不同 worktree 不会冲突 |
| 可读性 | 人类可读，一眼看出类型、日期、序号、来源 worktree |
| 序号管理 | 每个 worktree 每日独立序列号，存储在 `.issues/sequences/{wt_id}/{YYYYMMDD}.txt` |
| 备选方案 | ULID（不可读）、UUID（不可读）、集中分配（需 CI） |

### 2.2 目录位置

**最终方案**：`.issues/`（隐藏目录）

理由：issue 系统是基础设施而非文档，与 `.trae/` 风格一致。`docs/` 更聚焦于项目文档。

### 2.3 wt_id 识别机制

**最终方案**：基于路径映射自动识别

```yaml
# .issues/config.yml（只有一份，通过 git 同步）
worktree_mapping:
  "w1-easy-rag": wt1
  "w1-easy-rag-feature-x": wt2
```

关键设计：**不在每个 worktree 维护独立 config.yml**，而是只有一份配置文件，通过路径子串匹配自动识别。这避免了多 worktree 的 config.yml merge 冲突。

### 2.4 状态流转

**最终方案**：四状态 + 两个终态

```
todo → in_progress → review → done
  ↓
deferred   cancelled
```

合法流转规则（定义在 `src/issue/manager.py` 的 `STATUS_TRANSITIONS`）：
- `done` 不可回退
- `deferred` 可回到 `todo`
- `cancelled` 可回到 `todo`

### 2.5 汇总表

**最终方案**：脚本按需生成，不自动维护

- `pixi run issue summary` 打印到终端
- `pixi run issue summary --save` 保存到 `.issues/_summary.md`（gitignore）
- 可选自动生成（config.yml 中 `summary.auto_generate`），默认关闭

### 2.6 context.md

**最终方案**：混合维护

- AI 自动扫描 `in_progress` 状态的 issue（★ 标记）
- 人类可手动 `pixi run issue focus <id>` 添加（☆ 标记）
- 存储在 `.issues/context.md`

### 2.7 字段设计

所有字段全写上，后续可删：

`id, title, type, status, priority, labels, assignee, milestone, created_at, updated_at, source, legacy_id`

其中 `legacy_id` 用于迁移时保留原编号（如 `BUG-032`）。

## 三、实现架构

### 3.1 模块结构

```
src/issue/
├── __init__.py        # 模块入口，导出核心类
├── cli.py             # Click CLI 命令定义
├── config.py          # 配置读取 + wt_id 自动识别
├── id_generator.py    # 分布式 ID 生成
├── manager.py         # IssueManager 核心管理类（CRUD + 状态流转）
├── migrate.py         # backlog.md 迁移脚本
└── models.py          # Pydantic 数据模型
```

### 3.2 依赖

- `click`：CLI 框架
- `pydantic`：数据验证
- `python-frontmatter`：YAML front matter 解析
- `pyyaml`：YAML 处理

### 3.3 文件格式

每个 issue 是一个 Markdown 文件，YAML front matter + 正文：

```yaml
---
id: BUG-260427-003-wt1
title: "xxx"
type: BUG
status: todo
priority: medium
labels: []
assignee: null
milestone: null
created_at: 2026-04-27T14:30:22+08:00
updated_at: 2026-04-27T14:30:22+08:00
source: TODO.md
legacy_id: BUG-032
---

## 问题描述
（待填写）

## 根因分析
（待填写）

## 修复方向
（待填写）

## 更新记录
- 2026-04-27：创建
```

### 3.4 目录结构

```
.issues/
├── config.yml                    # 全局配置
├── context.md                    # AI 上下文
├── _summary.md                   # 汇总表快照（gitignore）
├── sequences/                    # ID 序列号
│   └── wt1/
│       └── 20260428.txt
├── active/                       # todo + in_progress + review
├── completed/                    # done（按月归档）
│   └── 2026-04/
├── deferred/                     # 延期
└── cancelled/                    # 取消
```

### 3.5 CLI 命令一览

| 命令 | 功能 |
|------|------|
| `issue create -t <type> -T "<title>"` | 创建 issue |
| `issue show <id>` | 查看详情（支持部分 ID 匹配） |
| `issue list` | 列出活跃 issue |
| `issue list --all` | 包含已完成 |
| `issue list --status todo --type bug` | 过滤 |
| `issue update <id> --priority high` | 更新字段 |
| `issue start <id>` | todo → in_progress |
| `issue review <id>` | in_progress → review |
| `issue done <id>` | review → done，移动文件 |
| `issue defer <id>` | → deferred |
| `issue cancel <id>` | → cancelled |
| `issue summary` | 打印汇总表 |
| `issue summary --save` | 保存到文件 |
| `issue context` | 显示 AI 上下文 |
| `issue focus <id>` | 添加到上下文 |
| `issue unfocus <id>` | 从上下文移除 |
| `issue worktree` | 显示当前 worktree |
| `issue worktree add <path> <wt_id>` | 添加映射 |
| `issue worktree remove <wt_id>` | 删除映射 |
| `issue worktree list` | 列出映射 |
| `issue worktree name <wt_id> <name>` | 设置名称 |
| `issue migrate --from-backlog` | 迁移旧数据 |
| `issue migrate --verify` | 验证迁移 |

## 四、迁移记录

- **来源**：`docs/backlog.md`（169 条 issue）
- **目标**：`.issues/` 目录
- **结果**：47 active + 114 completed + 8 deferred = 169 条
- **旧文件**：归档到 `docs/archive/backlog-2026-04-28.md`
- **legacy_id**：所有迁移的 issue 保留原编号（如 `BUG-032`）

## 五、已知局限与未来方向

### 当前局限

1. **无测试**：CLI 工具尚未编写 pytest 测试
2. **无 MCP**：AI 通过 `RunCommand` 调用 CLI，未来可改为 MCP server
3. **slug 编码**：中文标题生成的 slug 在 Windows 文件名中可能出现编码问题
4. **无 Web UI**：纯 CLI 交互

### 未来方向

1. **MCP Server**：实现 MCP 工具层，AI 可直接调用
2. **自动汇总**：config.yml 中 `summary.auto_generate: true` 时，issue 变更自动更新汇总
3. **Issue 关联**：支持 `related: [BUG-xxx]` 字段
4. **评论系统**：支持在 issue 文件中追加评论
5. **GitHub Issues 同步**：本地为主，GitHub 为辅

## 六、参考文档

- 设计方案讨论：`.trae/documents/issue_system_design.md`
- 实施计划书：`.trae/documents/issue-system-refactor-plan.md`
- Spec 三件套：`.trae/specs/implement-issue-system/`
