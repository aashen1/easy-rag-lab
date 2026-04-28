# 文档导航索引

> 最后更新: 2026-04-29

本文档是项目文档的唯一入口，提供全局导航。

---

## 三通道导航

### 👤 用户通道

面向普通用户，使用系统功能：

1. [快速上手](getting-started.md) — 5 分钟内跑通系统
2. [CLI 参考](user-guides/cli-reference.md) — 命令行使用指南
3. [配置参考](user-guides/config-reference.md) — config.yaml 完整说明

**功能指南**：

- [Streamlit Web Demo](user-guides/streamlit-web-demo.md)
- [Meal 数据管理系统](user-guides/meal-system.md)
- [实验评测系统](user-guides/experiment-system.md)
- [PDF 解析指南](user-guides/pdf-parsing.md)
- [文档级问题生成](user-guides/question-generation.md)
- [评测指标详解](user-guides/evaluation-metrics.md)
- [RAGAS 评测系统](user-guides/ragas-evaluation.md)
- [Token 追踪](user-guides/token-tracking.md)
- [Issue 管理系统](user-guides/issue-system.md)
- [RAG 泛超参数使用指南](user-guides/hyperparameter-guide.md)
- [测试集管理](user-guides/test-set-management.md)
- [Golden Testset 生成](user-guides/golden-testset-generation.md)
- [Golden Test 审查](user-guides/golden-test-review.md)

### 🔧 开发者通道

面向开发人员，了解技术实现：

1. [系统架构](dev-guides/architecture.md) — 系统整体设计
2. [测试运行指南](dev-guides/testing.md) — 测试策略与运行
3. [RAG 优化实现与测试保障](dev-guides/rag-optimization-implementation.md) — 优化实现细节
4. [性能分析配置](dev-guides/profiling-configuration.md) — 性能调优
5. [Lint 与 pre-commit](dev-guides/lint-and-precommit.md) — 代码规范
6. [Commit 规范](dev-guides/commit-conventions.md) — 提交规范
7. [Ruff 使用指南](dev-guides/ruff-usage-guide.md) — Ruff 实操手册
8. [发版节奏](dev-guides/release-cadence.md) — 版本节奏与流程
9. [测试分层与时间预算](dev-guides/test-layering-and-time-budgets.md) — 测试架构

### 🏛️ 项目博物馆

> 本部分内容、未归档的trae文档以及issue系统均被列入 export-ignore，不会包含在正式发版中，需要通过`git clone`获取

面向项目历史爱好者：

1. [时间线导览](.archive/timeline.md) — 按版本浏览项目演进（推荐入口）
2. [版本演进年轮](version-history.md) — 项目版本迭代历程
3. [开发随笔](dev-story.md) — 一些开发感想
4. [抛接球年轮方法论](methodology.md) — AI 时代的版本演进管理方法论

---

## 文档目录结构

```
docs/
├── README.md                    # 本文档（导航索引）
├── getting-started.md           # 快速上手
├── version-history.md           # 版本演进年轮
├── methodology.md               # 抛接球年轮方法论
├── dev-story.md                 # 开发随笔
│
├── user-guides/                 # 👤 用户指南
│   ├── cli-reference.md
│   ├── config-reference.md
│   ├── streamlit-web-demo.md
│   ├── meal-system.md
│   ├── experiment-system.md
│   ├── pdf-parsing.md
│   ├── question-generation.md
│   ├── evaluation-metrics.md
│   ├── ragas-evaluation.md
│   ├── token-tracking.md
│   ├── issue-system.md
│   ├── hyperparameter-guide.md
│   ├── test-set-management.md
│   ├── golden-testset-generation.md
│   └── golden-test-review.md
│
├── dev-guides/                  # 🔧 开发者指南
│   ├── architecture.md
│   ├── testing.md
│   ├── rag-optimization-implementation.md
│   ├── profiling-configuration.md
│   ├── lint-and-precommit.md
│   ├── commit-conventions.md
│   ├── ruff-usage-guide.md
│   ├── release-cadence.md
│   └── test-layering-and-time-budgets.md
│
└── .archive/                    # 🏛️ 项目博物馆
    ├── README.md                # 博物馆指南
    ├── timeline.md              # 时间线导览
    ├── archive-log.md           # 归档日志
    ├── v0.1.0-v0.1.5-mvp-era/
    ├── v0.1.6-hygiene-era/
    ├── v0.1.7-evaluation-era/
    ├── v0.1.8-testset-era/
    ├── v0.1.9-dual-eval-era/
    ├── v0.1.10-parsing-era/
    ├── v0.1.11-unification-era/
    ├── v0.1.12-governance-era/
    ├── v0.1.13-visualization-era/
    ├── v0.1.14-code-health-era/
    └── cross-version/
```

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
| 临时想法/TODO | 运行 `pixi run issue create` 创建 issue |
| AI 对话原始记录 | 精简后入库，或直接删除 |
