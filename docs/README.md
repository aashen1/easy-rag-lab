# 文档导航索引

> 最后更新: 2026-04-27

本文档是项目文档的唯一入口，提供全局导航。

---

## 快速导航

### 新用户

1. [快速上手](getting-started.md) — 5 分钟内跑通系统
2. [系统架构](architecture.md) — 了解系统整体设计
3. [CLI 参考](cli-reference.md) — 命令行使用指南

### 开发者

1. [版本演进年轮](version-history.md) — 项目版本迭代历程
2. [待做事项总表](backlog.md) — 项目"卫生情况"总入口
3. [抛接球年轮方法论](methodology.md) — AI 时代的版本演进管理方法论
4. [配置参考](config-reference.md) — config.yaml 完整说明

### 使用指南

- [Meal 数据管理系统](guides/operations/meal-system.md)
- [实验评测系统](guides/operations/experiment-system.md)
- [PDF 解析指南](guides/operations/pdf-parsing.md)
- [文档级问题生成](guides/operations/question-generation.md)
- [评测指标详解](guides/operations/evaluation-metrics.md)
- [RAGAS 评测系统](guides/operations/ragas-evaluation.md)
- [Token 追踪](guides/operations/token-tracking.md)
- [RAG 泛超参数使用指南](guides/operations/hyperparameter-guide.md)
- [RAG 优化实现与测试保障](guides/operations/rag-optimization-implementation.md)
- [测试集管理](guides/operations/test-set-management.md)
- [Golden Testset 生成](guides/operations/golden-testset-generation.md)
- [Artifact 路径迁移](guides/operations/artifact-path-migration.md)

### 开发指南

- [测试运行指南](guides/development/testing.md)
- [Lint 与 pre-commit](guides/development/lint-and-precommit.md)
- [Commit 规范](guides/development/commit-conventions.md)

### 故障排查

- [评测指标 Bug 修复](troubleshooting/eval-metrics-bugfix.md)
- [评测系统验收修复](troubleshooting/eval-system-acceptance-fix.md)
- [Irrelevant 问题指标修复](troubleshooting/irrelevant-question-metrics-fix.md)
- [缓存分析](troubleshooting/cache-analysis.md)

### 已解决问题归档

- [pytest tmp 目录 FileExistsError](troubleshooting/resolved/pytest-basetemp-fileexistserror.md)
- [幽灵文件夹问题](troubleshooting/resolved/ghost-folder-mkdir.md)

---

## 文档目录结构

```
docs/
├── README.md                  # 本文档（导航索引）
├── version-history.md         # 版本演进年轮
├── backlog.md                 # 待做事项总表
├── methodology.md             # 抛接球年轮方法论
├── inbox-log.md               # 收件箱处理日志
│
├── getting-started.md         # 快速上手
├── architecture.md            # 系统架构
├── cli-reference.md           # CLI 参考
├── config-reference.md        # 配置参考
│
├── guides/                    # 使用与开发指南
│   ├── operations/            # 系统运维与使用指南
│   │   ├── meal-system.md
│   │   ├── experiment-system.md
│   │   ├── question-generation.md
│   │   ├── evaluation-metrics.md
│   │   ├── ragas-evaluation.md
│   │   ├── token-tracking.md
│   │   ├── hyperparameter-guide.md
│   │   ├── rag-optimization-implementation.md
│   │   ├── test-set-management.md
│   │   ├── golden-testset-generation.md
│   │   ├── pdf-parsing.md
│   │   └── artifact-path-migration.md
│   └── development/           # 开发规范与工具指南
│       ├── testing.md
│       ├── lint-and-precommit.md
│       └── commit-conventions.md
│
├── reviews/                   # 版本验收与审查报告
│   ├── v0.1.5/
│   ├── v0.1.6/
│   ├── v0.1.7/
│   ├── v0.1.8/
│   ├── sessions/              # 开发会话记录
│   │   ├── baseline-evaluation-fix-record.md
│   │   └── independent-issues-batch-session.md
│   └── investigations/        # 技术调研报告
│       ├── inv-017-boundary-condition-test-coverage.md
│       ├── inv-018-exception-path-test-coverage.md
│       ├── inv-019-test-parallelization.md
│       ├── inv-021-file-path-security.md
│       └── rf-002-project-structure.md
│
├── troubleshooting/           # 故障排查
│   ├── eval-metrics-bugfix.md
│   ├── eval-system-acceptance-fix.md
│   ├── irrelevant-question-metrics-fix.md
│   ├── cache-analysis.md
│   └── resolved/              # 已修复问题归档
│       ├── pytest-basetemp-fileexistserror.md
│       └── ghost-folder-mkdir.md
│
├── archive/                   # 历史归档
│   ├── archive-log.md         # 归档日志
│   ├── trae-documents/        # .trae 计划书归档
│   │   └── v0.1.9-completed-plans/
│   ├── trae-specs/            # .trae Spec 归档
│   │   └── v0.1.9-completed-specs/
│   ├── trae-plans/            # 旧版计划书归档
│   └── trae-reports/          # .trae 报告归档
│
├── inbox/                     # 待处理文档收件箱
└── inbox-processed/           # 已处理的原始文件
```

---

## 收件箱机制

将网页端导出的聊天记录放入 `docs/inbox/` 目录，AI 会在下次对话时提示处理。

处理结果记录在 `inbox-log.md` 中。

---

## TODO 归档机制

`TODO.md`（人类管理）与 `docs/backlog.md`（AI 管理）构成双向异步 issue 追踪体系：

- **归档**：AI 自动将 TODO.md 中未归档的 issue 单向归档到 backlog.md，追加 `📋` 时间戳
- **完成同步**：backlog 中已完成的 issue 同步回 TODO.md，打钩并移动到对应日期标题
- **触发**：每次对话开始自动检查，或用户说"打扫卫生""归档TODO"

详见 [抛接球年轮方法论](methodology.md) 中的"TODO ↔ Backlog 双向异步机制"章节。

---

## 文档规范

### 文件命名

- 使用英文，小写，连字符分隔
- 格式：`<类型>-<主题>.md`

### 状态标签

每个文档头部包含状态标签：

```markdown
<!-- status: active | archived | deprecated | needs-update -->
```

### 何时不创建文档

| 场景 | 替代方案 |
|------|---------|
| 代码注释能说明的问题 | 直接写在代码里 |
| API 变更 | 更新 `CHANGELOG.md` |
| 临时想法/TODO | 添加到 `docs/backlog.md` |
| AI 对话原始记录 | 精简后入库，或直接删除 |
