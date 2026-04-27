# Issue 系统重构 Spec

## Why

当前 issue 管理系统存在四大痛点：
1. 多 worktree 并行开发时递增编号冲突
2. TODO.md 与 backlog.md 状态同步延迟
3. 单文件 token 消耗过大（backlog.md 280+ 行）
4. issue 详情分散，信息粒度不统一

## What Changes

- **新增** `.issues/` 目录，每个 issue 一个 Markdown 文件
- **新增** `src/issue/` 模块，提供 CLI 工具
- **新增** 分布式唯一 ID 格式：`<TYPE>-<YYYYMMDD>-<SEQ>-<WTID>`
- **新增** 基于路径自动识别 wt_id 的机制
- **新增** 四状态流转：`todo → in_progress → review → done`
- **新增** 汇总表生成命令
- **新增** context.md AI 上下文管理
- **迁移** 现有 70+ issue 从 backlog.md 到新系统
- **BREAKING** 废弃 `docs/backlog.md` 作为 issue 主存储

## Impact

- Affected specs: todo-archiver skill, project-memory skill
- Affected code: 新增 `src/issue/` 模块，修改 pixi.toml, .gitignore, CLAUDE.md

---

## ADDED Requirements

### Requirement: Issue 文件存储

系统 SHALL 将每个 issue 存储为独立的 Markdown 文件，位于 `.issues/` 目录下。

#### Scenario: 创建 issue 文件

- **WHEN** 用户运行 `pixi run issue create --type bug --title "xxx"`
- **THEN** 系统在 `.issues/active/` 下创建 `<ID>-<slug>.md` 文件
- **AND** 文件包含 YAML front matter 和正文结构

### Requirement: 分布式唯一 ID

系统 SHALL 生成格式为 `<TYPE>-<YYYYMMDD>-<SEQ>-<WTID>` 的唯一 ID。

#### Scenario: ID 生成

- **WHEN** 创建新 issue
- **THEN** ID 格式为 `BUG-260427-003-wt1`
- **AND** 同一 worktree 同一日期序号递增
- **AND** 不同 worktree 的 ID 天然隔离

### Requirement: 路径识别 wt_id

系统 SHALL 基于当前工作目录路径自动识别 wt_id。

#### Scenario: 自动识别

- **WHEN** CLI 启动
- **THEN** 系统获取当前路径，在 `worktree_mapping` 中查找匹配
- **AND** 返回对应的 wt_id

#### Scenario: 未映射路径

- **WHEN** 当前路径未在 mapping 中配置
- **THEN** 系统提示用户运行 `pixi run issue worktree add` 添加映射

### Requirement: 四状态流转

系统 SHALL 支持四状态流转：`todo → in_progress → review → done`。

#### Scenario: 合法流转

- **WHEN** 用户运行 `pixi run issue start BUG-260427-003-wt1`
- **THEN** 状态从 `todo` 变为 `in_progress`
- **AND** 文件保持在 `active/` 目录

#### Scenario: 完成流转

- **WHEN** 用户运行 `pixi run issue done BUG-260427-003-wt1`
- **THEN** 状态变为 `done`
- **AND** 文件移动到 `completed/YYYY-MM/` 目录

#### Scenario: 非法流转

- **WHEN** 用户尝试从 `done` 回退到 `todo`
- **THEN** 系统拒绝操作并返回错误提示

### Requirement: CLI 命令

系统 SHALL 提供以下 CLI 命令：

| 命令 | 功能 |
|------|------|
| `issue create` | 创建 issue |
| `issue show` | 查看单个 issue |
| `issue list` | 列出 issue（支持过滤） |
| `issue update` | 更新 issue 字段 |
| `issue start/review/done/defer/cancel` | 状态流转 |
| `issue summary` | 生成汇总表 |
| `issue context` | 管理 context.md |
| `issue worktree` | 管理 worktree 映射 |
| `issue migrate` | 迁移旧系统数据 |

### Requirement: 汇总表生成

系统 SHALL 支持生成汇总表。

#### Scenario: CLI 打印

- **WHEN** 用户运行 `pixi run issue summary`
- **THEN** 系统打印 Markdown 格式的汇总表到终端

#### Scenario: 保存文件

- **WHEN** 用户运行 `pixi run issue summary --save`
- **THEN** 系统保存汇总表到 `.issues/_summary.md`

### Requirement: context.md 管理

系统 SHALL 维护 `.issues/context.md` 作为 AI 上下文。

#### Scenario: 自动生成

- **WHEN** 用户运行 `pixi run issue context`
- **THEN** 系统扫描 `in_progress` 状态的 issue，生成简洁摘要

#### Scenario: 手动聚焦

- **WHEN** 用户运行 `pixi run issue focus BUG-260427-003-wt1`
- **THEN** 该 issue 添加到 context.md

### Requirement: 数据迁移

系统 SHALL 支持从 `docs/backlog.md` 一次性迁移。

#### Scenario: 迁移执行

- **WHEN** 用户运行 `pixi run issue migrate --from-backlog`
- **THEN** 系统解析 backlog.md 表格，生成 issue 文件
- **AND** 保留原始编号作为 `legacy_id` 字段

---

## MODIFIED Requirements

### Requirement: todo-archiver skill

原流程：写入 `docs/backlog.md` 表格

新流程：调用 `pixi run issue create` 创建 issue 文件

### Requirement: project-memory skill

原流程：读取 `docs/backlog.md` 获取状态统计

新流程：读取 `.issues/context.md` 或调用 `pixi run issue summary`

---

## REMOVED Requirements

### Requirement: backlog.md 作为 issue 主存储

**Reason**: 单文件 token 消耗过大，多 worktree 冲突

**Migration**: 迁移后归档到 `docs/archive/`
