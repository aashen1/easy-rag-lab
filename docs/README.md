# 文档导航索引

> 最后更新: 2026-04-18

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

- [Meal 数据管理系统](guides/meal-system.md)
- [实验评测系统](guides/experiment-system.md)
- [评测指标详解](guides/evaluation-metrics.md)
- [Token 追踪](guides/token-tracking.md)
- [测试运行指南](guides/testing.md)

### 故障排查

- [幽灵文件夹问题](troubleshooting/ghost-folder-mkdir.md)

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
├── guides/                    # 使用指南
│   ├── meal-system.md
│   ├── experiment-system.md
│   ├── evaluation-metrics.md
│   ├── token-tracking.md
│   └── testing.md
│
├── reviews/                   # 版本验收报告
│   └── v0.1.5/
│       ├── code-review.md
│       ├── outcome.md
│       └── next-direction.md
│
├── troubleshooting/           # 故障排查
│   └── ghost-folder-mkdir.md
│
├── archive/                   # 历史归档
│   ├── specs/
│   └── ...
│
├── inbox/                     # 待处理文档收件箱
└── inbox-processed/           # 已处理的原始文件
```

---

## 收件箱机制

将网页端导出的聊天记录放入 `docs/inbox/` 目录，AI 会在下次对话时提示处理。

处理结果记录在 `inbox-log.md` 中。

---

## 文档规范

### 文件命名

- 使用英文，小写，连字符分隔
- 格式：`<类型>-<主题>.md`

### 状态标签

每个文档头部包含状态标签：

```markdown
<!-- status: active | archived | deprecated -->
```

### 何时不创建文档

| 场景 | 替代方案 |
|------|---------|
| 代码注释能说明的问题 | 直接写在代码里 |
| API 变更 | 更新 `CHANGELOG.md` |
| 临时想法/TODO | 添加到 `docs/backlog.md` |
| AI 对话原始记录 | 精简后入库，或直接删除 |
