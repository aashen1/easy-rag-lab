# Checklist

## Phase 1: 基础设施

- [x] `.issues/` 目录结构已创建（active/completed/deferred/cancelled）
- [x] `.issues/config.yml` 模板文件存在且格式正确
- [x] `.gitignore` 已添加 `_summary.md` 忽略规则
- [x] `pyproject.toml` 已添加 click, pydantic, python-frontmatter, pyyaml 依赖
- [x] `src/issue/__init__.py` 模块入口存在
- [x] `src/issue/models.py` 数据模型定义完整
- [x] `src/issue/config.py` 能正确读取配置并识别 wt_id
- [x] `src/issue/id_generator.py` 能生成正确格式的 ID
- [x] `pixi run issue` 命令可执行

## Phase 2: 核心功能

- [x] `pixi run issue create --type bug --title "test"` 能创建 issue 文件
- [x] 创建的 issue 文件位于 `.issues/active/`
- [x] issue 文件 YAML front matter 包含所有必需字段
- [x] `pixi run issue show <id>` 能正确显示 issue 内容
- [x] `pixi run issue list` 能列出 active 目录下的 issue
- [x] `pixi run issue list --status todo` 能按状态过滤
- [x] `pixi run issue list --type bug` 能按类型过滤
- [x] `pixi run issue update <id> --priority high` 能更新字段
- [x] `pixi run issue start <id>` 能将状态改为 in_progress
- [x] `pixi run issue done <id>` 能将状态改为 done 并移动文件
- [x] 非法状态流转（如 done → todo）被正确拒绝

## Phase 3: 辅助功能

- [x] `pixi run issue summary` 能打印汇总表到终端
- [x] `pixi run issue summary --save` 能保存到 `_summary.md`
- [x] 汇总表统计数据正确
- [x] `pixi run issue context` 能生成 context.md
- [x] `pixi run issue focus <id>` 能添加 issue 到 context
- [x] `pixi run issue unfocus <id>` 能从 context 移除 issue

## Phase 4: 迁移

- [x] `pixi run issue migrate --from-backlog` 能解析 backlog.md
- [x] 迁移后的 issue 文件包含 `legacy_id` 字段
- [x] 迁移数量与原 backlog.md 一致（169 条）
- [x] `docs/backlog.md` 已归档到 `docs/archive/backlog-2026-04-28.md`

## Phase 5: 集成

- [x] todo-archiver skill 已更新为调用 CLI
- [x] project-memory skill 已更新为读取 context.md
- [x] CLAUDE.md 已添加 issue 系统使用说明

## 整体验收

- [x] 所有 CLI 命令可正常执行
- [x] 多 worktree 场景下 ID 不冲突（基于路径映射）
- [x] 迁移后数据完整性验证通过
