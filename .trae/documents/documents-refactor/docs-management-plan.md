# 文档管理实践方案

> 提案日期: 2026-04-18
> 状态: 待审核

---

## 一、当前文档状态诊断

### 1.1 文档分布现状

| 位置 | 文件数 | 主要类型 | 问题 |
|------|--------|---------|------|
| 根目录 | 4 | README, CHANGELOG, TODO, CLAUDE | TODO.md 混杂开发日志与任务清单 |
| `notes/` | 8 | 开发手记、功能文档、故障排查 | 分类不清，部分内容重叠 |
| `.trae/documents/` | 9 | 测试体系、代码问题、归档 | 测试文档严重重叠（6 份相关文件） |
| `.trae/code_reviews/v0.1.5/` | 5 | 代码审查报告 | 版本特定，已失去时效性 |
| `.trae/specs/` | 7 目录 | 规格文档 (spec/tasks/checklist) | 管理良好，无需变更 |
| `exp_configs/README.md` | 1 | 配置说明 | 位置合理 |
| `data/README.md` | 1 | 数据说明 | 位置合理 |

### 1.2 核心问题

| # | 问题 | 影响 |
|---|------|------|
| P1 | **分类混乱** | 开发手记、故障排查、技术决策、代码审查混放 |
| P2 | **严重重叠** | 测试体系相关 6 份文档（design, analysis, redesign-response, coverage-guide, future-directions, suggestions）存在大量重复内容 |
| P3 | **版本失配** | `code_reviews/v0.1.5/` 中的问题大部分已修复，文档失去参考价值 |
| P4 | **TODO.md 超载** | 混杂了开发日志（带时间戳）、任务清单、文档引用、AI 生成标记 |
| P5 | **notes/ 命名不一致** | 中英文混杂，命名风格不统一 |
| P6 | **缺少索引** | 没有文档目录或索引文件，新开发者难以快速定位 |

### 1.3 具体重叠分析

#### 测试体系文档重叠群

```
.trae/documents/test-suite/
├── test-suite-design.md           ← 三层测试架构设计
├── test-suite-analysis.md         ← 测试套件分析（未读但存在）
├── test-suite-redesign-response.md ← 对 analysis 的回复
├── test-coverage-guide.md         ← 测试覆盖指南（已整合 design 内容）
├── test-future-directions.md      ← 未来方向（部分与 coverage-guide 重叠）
└── test-review-suggestions.md     ← 审查建议（已标注状态）
```

**建议**: 合并为 1 份 `docs/testing/testing-guide.md`，保留关键信息，去除重复。

#### Meal 文档重叠

```
notes/
├── meal-feature-issues.md         ← 潜在问题列表
├── meal-user-manual.md            ← 用户手册
├── meal-full-pipeline-manual.md   ← 完整流水线手册

.trae/documents/archived/meal/
├── meal-feature-plan.md           ← 实施计划（已归档）
└── meal-identity-refactoring-plan.md ← 重构计划（已归档）
```

**建议**: 保留 `meal-user-manual.md` 和 `meal-feature-issues.md`，将 `meal-full-pipeline-manual.md` 内容合并到用户手册中。

#### 幽灵文件夹排查重叠

```
notes/
├── ghost-folder-issue-fix.md          ← 修复记录
├── chat-幽灵文件夹排查指南.md         ← AI 对话记录（原始聊天记录）
└── mkdir-hook-lesson.md               ← 钩子埋点经验总结
```

**建议**: 保留 `ghost-folder-issue-fix.md`（修复记录）和 `mkdir-hook-lesson.md`（通用经验），将 `chat-幽灵文件夹排查指南.md` 归档（原始聊天记录，信息已提炼到其他文档）。

---

## 二、目标文档结构

```
ash-easy-rag/
│
├── README.md                          # 项目主文档（唯一入口）
├── CHANGELOG.md                       # 版本变更历史
├── CLAUDE.md                          # AI 工作规则（保持不变）
├── TODO.md                            # 仅保留任务清单，移除开发日志
│
├── docs/                              # 📁 文档根目录（新建）
│   ├── INDEX.md                       # 文档索引（新建）
│   │
│   ├── guides/                        # 📁 使用指南（面向用户/开发者）
│   │   ├── meal-user-manual.md        # Meal 功能用户手册
│   │   ├── experiment-system.md       # 自动化评测系统使用指南
│   │   └── testing-guide.md           # 测试体系完整指南（合并6份文档）
│   │
│   ├── decisions/                     # 📁 技术决策记录（ADR 格式）
│   │   ├── 0001-rag-mvp-choices.md    # MVP 技术选型记录
│   │   ├── 0002-meal-design.md        # Meal 系统设计决策
│   │   └── 0003-experiment-system.md  # 评测系统设计决策
│   │
│   ├── troubleshooting/               # 📁 故障排查记录
│   │   ├── output-dir-ghost-folder.md # 幽灵文件夹问题
│   │   └── mkdir-hook-lesson.md       # 钩子埋点经验
│   │
│   └── development/                   # 📁 开发过程记录
│       ├── dev-log-2026-04-15-mvp.md  # MVP 开发完成报告
│       └── dev-log-2026-04-16-meal.md # Meal 功能开发手记
│
├── specs/                             # 📁 规格文档（从 .trae/specs/ 迁移）
│   ├── automate-evaluation/
│   ├── code-quality-fixup/
│   ├── known-bugs-fixup/
│   ├── start/
│   ├── test-review-fixup/
│   ├── test-suite-redesign/
│   └── todo-backlog-cleanup/
│
├── .trae/                             # AI 工具内部目录
│   ├── code_reviews/                  # 代码审查（保留但归档）
│   │   └── v0.1.5/                    # 标记为 ARCHIVED
│   └── documents/
│       └── archived/                  # 历史归档
│           ├── flagembedding_to_transformers/
│           └── RAG项目链路调研2026-04-16.md
│
├── exp_configs/
│   └── README.md
│
└── data/
    └── README.md
```

### 2.1 目录职责定义

| 目录 | 用途 | 谁使用 | 更新频率 |
|------|------|--------|---------|
| `docs/guides/` | 系统使用指南、操作手册 | 用户、开发者 | 功能变更时更新 |
| `docs/decisions/` | 技术决策记录（ADR） | 开发者 | 重大决策时新增 |
| `docs/troubleshooting/` | 已解决故障的排查记录 | 遇到类似问题的开发者 | 发现新问题或新解法时 |
| `docs/development/` | 开发过程手记、经验总结 | 开发团队成员 | 每个开发阶段 |
| `specs/` | 待执行或已完成的功能规格 | 开发者、AI | 新功能开发时 |
| `.trae/code_reviews/` | 历史代码审查报告 | 参考 | 不再更新 |

---

## 三、文档分类标准

### 3.1 分类规则

| 类型 | 存放位置 | 命名格式 | 示例 |
|------|---------|---------|------|
| **使用指南** | `docs/guides/` | `<功能>-manual.md` 或 `<功能>-guide.md` | `meal-user-manual.md` |
| **技术决策** | `docs/decisions/` | `NNNN-<简短描述>.md` | `0001-rag-mvp-choices.md` |
| **故障排查** | `docs/troubleshooting/` | `<问题描述>.md` | `output-dir-ghost-folder.md` |
| **开发手记** | `docs/development/` | `dev-log-<日期>-<主题>.md` | `dev-log-2026-04-15-mvp.md` |
| **规格文档** | `specs/` | `<功能名>/{spec,tasks,checklist}.md` | `specs/start/` |
| **代码审查** | `.trae/code_reviews/` | `<版本>/<序号>-<主题>.md` | `v0.1.5/01-security.md` |

### 3.2 何时创建新文档

| 场景 | 操作 | 文档类型 |
|------|------|---------|
| 新功能上线 | 创建 `guides/<feature>-guide.md` | 使用指南 |
| 重大技术决策 | 创建 `decisions/NNNN-<topic>.md` | ADR |
| 解决疑难 bug | 创建 `troubleshooting/<bug-name>.md` | 故障排查 |
| 完成开发阶段 | 创建 `development/dev-log-<date>-<topic>.md` | 开发手记 |
| 新功能开发 | 创建 `specs/<feature>/` 目录 | 规格文档 |

### 3.3 何时不创建文档

| 场景 | 替代方案 |
|------|---------|
| 代码注释能说明的问题 | 直接写在代码里 |
| API 变更 | 更新 `CHANGELOG.md` |
| 临时想法/TODO | 更新 `TODO.md` 的 Backlog 部分 |
| AI 对话原始记录 | 不保存，仅保存提炼后的结论 |

---

## 四、文档生命周期管理

### 4.1 状态流转

```
[创建] → [活跃] → [过时] → [归档]
              ↓
           [更新]（循环）
```

| 状态 | 含义 | 存放位置 | 标记 |
|------|------|---------|------|
| **活跃** | 当前有效，与代码版本匹配 | 目标目录 | 无标记 |
| **过时** | 部分信息与当前代码不符 | 目标目录顶部加 ⚠️ 警告 | `> ⚠️ OUTDATED: ...` |
| **归档** | 仅保留历史参考价值 | `.trae/documents/archived/` | 文件名加 `archived-` 前缀 |

### 4.2 版本同步规则

1. **每次发版前**，检查 `docs/` 目录下所有文档是否与当前版本匹配
2. **不匹配的文档**，在顶部添加版本警告，或迁移至归档目录
3. **CHANGELOG.md** 是唯一的版本变更记录，其他文档不应重复记录版本历史

### 4.3 清理规则

| 条件 | 动作 |
|------|------|
| 文档内容已 100% 合并到其他文档 | 删除原文档 |
| 文档描述的功能已完全重写 | 标记为过时或更新 |
| AI 对话原始记录 | 不保存（仅保存提炼后的结论） |
| 代码审查中发现的问题已全部修复 | 归档至 `.trae/documents/archived/code_reviews/` |

---

## 五、具体迁移计划

### Phase 1: 创建新结构（不破坏现有引用）

1. 创建 `docs/` 目录结构
2. 创建 `docs/INDEX.md`（文档索引）
3. 创建 `specs/` 目录（从 `.trae/specs/` 复制或软链接）

### Phase 2: 合并重叠文档

| 源文件 | 目标 | 动作 |
|--------|------|------|
| `docs/test-suite/` 下 6 份文档 | `docs/guides/testing-guide.md` | 合并去重 |
| `notes/meal-user-manual.md` + `meal-full-pipeline-manual.md` | `docs/guides/meal-user-manual.md` | 合并 |
| `notes/experiment_system.md` | `docs/guides/experiment-system.md` | 移动 |

### Phase 3: 分类迁移

| 源文件 | 目标 | 动作 |
|--------|------|------|
| `notes/ghost-folder-issue-fix.md` | `docs/troubleshooting/output-dir-ghost-folder.md` | 移动+重命名 |
| `notes/mkdir-hook-lesson.md` | `docs/troubleshooting/mkdir-hook-lesson.md` | 移动 |
| `notes/development_complete.md` | `docs/development/dev-log-2026-04-15-mvp.md` | 移动+重命名 |
| `notes/meal-feature-issues.md` | 关联到 `docs/guides/meal-user-manual.md` | 内容合并或作为独立文档 |

### Phase 4: 归档过期文档

| 源文件 | 目标 | 原因 |
|--------|------|------|
| `.trae/code_reviews/v0.1.5/` 全部 | `.trae/documents/archived/code_reviews/v0.1.5/` | 问题已修复 |
| `notes/chat-幽灵文件夹排查指南.md` | `.trae/documents/archived/chat-log-ghost-folder.md` | 原始对话记录，信息已提炼 |
| `.trae/documents/archived/` 下已有文件 | 保持不变 | 已在归档目录 |

### Phase 5: 清理 TODO.md

- 移除开发日志部分（带时间戳的详细记录）
- 保留 Backlog 任务清单
- 开发日志迁移至 `docs/development/`

### Phase 6: 创建文档索引

在 `docs/INDEX.md` 中建立完整的文档目录和快速检索表。

---

## 六、文档模板

### 6.1 使用指南模板

```markdown
# <功能名称> 使用指南

> 最后更新: YYYY-MM-DD
> 适用版本: vX.X.X

## 概述
<简要说明功能是什么，解决什么问题>

## 快速开始
<最简使用步骤>

## 详细说明
<分章节详细说明>

## 常见问题
<FAQ>

## 相关文档
- [相关文档1](../decisions/NNNN-topic.md)
- [相关文档2](../troubleshooting/issue.md)
```

### 6.2 技术决策记录（ADR）模板

```markdown
# ADR NNNN: <决策标题>

> 日期: YYYY-MM-DD
> 状态: 已接受 / 已弃用 / 已替代

## 背景
<描述需要决策的问题和上下文>

## 决策
<描述做出的决策>

## 理由
<解释为什么做出这个决策，包括考虑过的替代方案>

## 后果
<这个决策带来的正面和负面影响>
```

### 6.3 故障排查模板

```markdown
# <问题名称> 排查记录

> 发现日期: YYYY-MM-DD
> 解决日期: YYYY-MM-DD
> 影响版本: vX.X.X

## 现象
<描述问题的表现>

## 根因分析
<分析过程和最终定位到的根本原因>

## 解决方案
<具体的修复步骤>

## 经验总结
<避免同类问题的建议>
```

### 6.4 开发手记模板

```markdown
# 开发手记: <主题>

> 开发日期: YYYY-MM-DD
> 开发阶段: <阶段描述>

## 做了什么
<描述完成的工作>

## 为什么这样设计
<关键设计决策的解释>

## 遇到的问题与解决
<问题描述、分析过程、解决方案>

## 后续优化方向
<未来可以考虑的改进点>
```

---

## 七、长期维护机制

### 7.1 责任人

- **文档所有者**: 功能开发者负责编写初始文档
- **文档维护者**: 每次功能变更时，变更者同步更新相关文档
- **文档审核**: 每次发版前，检查文档与代码的一致性

### 7.2 自动化检查（未来可选）

在 CI 中添加文档健康度检查：
- 检查 `docs/` 目录下是否有 `> ⚠️ OUTDATED` 标记的文档超过 30 天
- 检查新增功能是否有对应的使用指南

### 7.3 AI 协作规范

| 场景 | AI 行为 |
|------|---------|
| 创建新功能 | 同时创建 `docs/guides/<feature>-guide.md` |
| 修复 bug | 如属于疑难问题，创建 `docs/troubleshooting/` 记录 |
| 完成开发阶段 | 创建 `docs/development/dev-log-*.md` |
| 技术决策 | 创建 `docs/decisions/NNNN-*.md` |
| 文档更新 | 自动检查是否与其他文档重叠 |

---

## 八、预期效果

| 指标 | 当前 | 目标 |
|------|------|------|
| 文档总数 | 55+ | ~20（去除重复和归档后） |
| 文档分布位置 | 6 个分散目录 | 4 个明确目录 + 根目录 |
| 重叠文档 | 3 组严重重叠 | 0 |
| 版本失配文档 | 约 10 份 | 0（或明确标记） |
| 查找文档平均步骤 | 不确定在哪 | 查看 INDEX.md → 直达 |
| 新开发者理解成本 | 高（文档杂乱） | 低（结构清晰） |

---

## 九、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 迁移过程中链接失效 | 文档引用断裂 | 迁移前扫描所有文档中的内部链接，迁移后统一更新 |
| 合并文档时信息丢失 | 历史细节丢失 | 合并前先备份，保留所有原文档至归档目录 |
| 团队成员不熟悉新结构 | 文档继续乱放 | 在 CLAUDE.md 和 README 中明确文档规范 |
| 维护成本增加 | 文档逐渐失修 | 简化文档类型，减少不必要的文档创建 |

---

## 十、总结

本方案的核心原则：

1. **单一职责**: 每种文档类型有明确的存放位置和命名规范
2. **去重合并**: 合并内容重叠的文档，保留最有价值的版本
3. **版本同步**: 文档必须与代码版本保持一致，过期的明确标记
4. **易于查找**: 通过 INDEX.md 实现一键定位
5. **轻量维护**: 不创建不必要的文档，代码能说明的就不写文档
6. **归档而非删除**: 保留历史参考价值，但不影响日常使用
