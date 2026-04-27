# Tasks

## Phase 1: 基础设施

- [x] Task 1: 创建目录结构和配置模板
  - [x] 1.1 创建 `.issues/` 目录结构（active/completed/deferred/cancelled）
  - [x] 1.2 创建 `.issues/config.yml` 模板文件
  - [x] 1.3 更新 `.gitignore` 忽略 `_summary.md`
  - [x] 1.4 添加依赖到 `pyproject.toml`（click, pydantic, python-frontmatter, pyyaml）

- [x] Task 2: 创建 `src/issue/` 模块骨架
  - [x] 2.1 创建 `src/issue/__init__.py`
  - [x] 2.2 创建 `src/issue/models.py` 定义数据模型（IssueConfig, Issue, IssueType, IssueStatus）
  - [x] 2.3 创建 `src/issue/config.py` 实现配置读取和 wt_id 自动识别
  - [x] 2.4 创建 `src/issue/id_generator.py` 实现 ID 生成逻辑
  - [x] 2.5 注册 pixi task `issue`

- [x] Task 3: 实现 worktree 管理命令
  - [x] 3.1 实现 `pixi run issue worktree` 显示当前 worktree 信息
  - [x] 3.2 实现 `pixi run issue worktree add <path> <wt_id>` 添加映射
  - [x] 3.3 实现 `pixi run issue worktree remove <wt_id>` 删除映射
  - [x] 3.4 实现 `pixi run issue worktree list` 列出所有映射
  - [x] 3.5 实现 `pixi run issue worktree name <wt_id> <name>` 设置名称

## Phase 2: 核心功能

- [x] Task 4: 实现 issue 创建命令
  - [x] 4.1 创建 `src/issue/manager.py` 核心管理类
  - [x] 4.2 实现 `pixi run issue create --type <type> --title <title>` 命令
  - [x] 4.3 支持可选参数：--priority, --labels, --milestone, --source
  - [x] 4.4 自动生成 YAML front matter 和正文模板
  - [x] 4.5 写入文件到 `.issues/active/`

- [x] Task 5: 实现 issue 查询命令
  - [x] 5.1 实现 `pixi run issue show <id>` 查看单个 issue
  - [x] 5.2 实现 `pixi run issue list` 列出 active issue
  - [x] 5.3 支持过滤参数：--status, --type, --priority, --labels
  - [x] 5.4 实现 `--all` 参数包含已完成 issue

- [x] Task 6: 实现 issue 更新命令
  - [x] 6.1 实现 `pixi run issue update <id> --status <status>` 更新状态
  - [x] 6.2 实现 `--priority`, `--title`, `--add-label`, `--remove-label` 参数
  - [x] 6.3 自动更新 `updated_at` 字段

- [x] Task 7: 实现状态流转命令
  - [x] 7.1 实现 `pixi run issue start <id>` (todo → in_progress)
  - [x] 7.2 实现 `pixi run issue review <id>` (in_progress → review)
  - [x] 7.3 实现 `pixi run issue done <id>` (review → done)，移动文件到 completed/
  - [x] 7.4 实现 `pixi run issue defer <id>` 移动到 deferred/
  - [x] 7.5 实现 `pixi run issue cancel <id>` 移动到 cancelled/
  - [x] 7.6 实现非法流转校验（如 done → todo）

## Phase 3: 辅助功能

- [x] Task 8: 实现汇总表生成
  - [x] 8.1 扫描所有 issue 文件
  - [x] 8.2 按类型、状态分组统计
  - [x] 8.3 生成 Markdown 表格
  - [x] 8.4 实现 `pixi run issue summary` 打印到终端
  - [x] 8.5 实现 `--save` 参数保存到 `_summary.md`

- [x] Task 9: 实现 context.md 管理
  - [x] 9.1 实现 `pixi run issue context` 扫描 in_progress issue 生成摘要
  - [x] 9.2 实现 `pixi run issue focus <id>` 添加到 context
  - [x] 9.3 实现 `pixi run issue unfocus <id>` 从 context 移除

## Phase 4: 迁移

- [x] Task 10: 实现迁移脚本
  - [x] 10.1 创建 `src/issue/migrate.py`
  - [x] 10.2 解析 `docs/backlog.md` 表格提取 issue 信息
  - [x] 10.3 生成 issue 文件，保留 `legacy_id` 字段
  - [x] 10.4 实现 `pixi run issue migrate --from-backlog`
  - [x] 10.5 实现 `--verify` 参数验证迁移结果

- [x] Task 11: 执行迁移
  - [x] 11.1 备份 `docs/backlog.md` 和 `TODO.md`
  - [x] 11.2 运行迁移脚本
  - [x] 11.3 验证迁移结果（数量一致、字段完整）
  - [x] 11.4 归档 `docs/backlog.md` 到 `docs/archive/`

## Phase 5: 集成

- [x] Task 12: 更新 todo-archiver skill
  - [x] 12.1 修改 SKILL.md 归档流程
  - [x] 12.2 改为调用 `pixi run issue create` 创建 issue

- [x] Task 13: 更新 project-memory skill
  - [x] 13.1 修改状态统计读取 `.issues/context.md`

- [x] Task 14: 更新 CLAUDE.md
  - [x] 14.1 添加 issue 系统使用说明
  - [x] 14.2 更新"当前状态"部分引用

---

# Task Dependencies

- Task 2 依赖 Task 1（需要目录结构和依赖）
- Task 3 依赖 Task 2（需要模块骨架）
- Task 4-7 依赖 Task 3（需要 wt_id 识别）
- Task 8-9 依赖 Task 4-7（需要核心功能）
- Task 10-11 依赖 Task 8（需要汇总验证）
- Task 12-14 依赖 Task 11（需要迁移完成）

# Parallelizable Work

- Task 1.1-1.4 可并行
- Task 2.2-2.5 可在骨架创建后并行
- Task 4-7 核心功能可串行开发
- Task 8-9 辅助功能可并行
- Task 12-14 集成工作可并行
