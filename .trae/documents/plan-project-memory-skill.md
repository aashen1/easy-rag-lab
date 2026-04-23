# Plan: 创建 project-memory Skill — 跨会话项目记忆系统

## 背景

项目的文档系统不仅是传统的"给人看"的文档，更是一个 **project-specific memory system**：
- 每次开发 session 的主题都沉淀在文档系统里
- 新的 stateless session 可以最小成本理解项目演进状态
- 对抗 AI 长线开发中的幻觉、注意力涣散、上下文受限导致的风格漂移
- 控制技术债积累速度

目前这个"抛接球"式的跨 session 开发策略尚未被显式提炼为 skill/rule，新 AI session 无法系统性地理解文档系统的正确使用方式。

## 方案设计

### 产物：Skill（而非 Rule）

**理由**：
- 这个概念包含大量上下文和操作指南，不适合作为始终加载的 Rule（会占用过多默认上下文）
- 与 `todo-archiver` 类似，属于"按需加载"的复杂流程
- Rule 适合简短不变式，Skill 适合详细方法论

### 命名：`project-memory`

**理由**：
- 直观表达"项目记忆"的核心概念
- 与现有 `todo-archiver`、`auto-commit-enforcer` 的命名风格一致（小写连字符）
- 避免使用"Project Context"这种过于泛化的名称
- 比"session-handoff"更准确——不只是交接，更是持续的记忆读写

### 三层渐进式披露架构

遵循项目已有的渐进式披露模式（参考 commit 规范的三层设计）：

| 层级 | 载体 | 加载方式 | 内容量 |
|------|------|---------|--------|
| Layer 1 | `CLAUDE.md` 新增 2-3 行 | 始终加载 | 核心不变式 |
| Layer 2 | `project-memory` SKILL.md | 按需加载 | 完整方法论 |
| Layer 3 | `docs/methodology.md` | 按需加载 | 抛接球年轮完整文档 |

## 实施步骤

### Step 1: 创建 `.trae/skills/project-memory/SKILL.md`

核心内容结构：

```
---
name: "project-memory"
description: "项目记忆系统使用指南。当新 session 启动、需要理解项目状态、
              或需要将工作成果写入项目记忆时调用。"
---

# Project Memory — 跨会话项目记忆系统

## 核心概念
- 文档系统 = 项目记忆（不只是给人看，更是给 AI 看的"演进年轮"）
- 每个 session 都是 stateless 的，唯一延续性来自文档系统
- 读写分离：读记忆理解状态，写记忆延续进度

## 读记忆：新 Session 启动清单
1. 读 CLAUDE.md → 了解项目定位、当前版本、开发规范
2. 读 docs/backlog.md 统计概览 → 了解 issue 积压与健康度
3. 读 docs/version-history.md → 了解版本演进脉络
4. 读 TODO.md My Backlog 区域 → 了解人类最新意图
5. 检查 docs/inbox/ → 是否有待处理文件
6. 根据任务需要，深入读取相关 docs/guides/ 和 docs/reviews/

## 写记忆：Session 结束前必须做的事
1. 代码变更 → 同步更新相关文档
2. 新功能 → 创建 docs/guides/<feature>.md
3. 疑难 bug → 创建 docs/troubleshooting/<bug-name>.md
4. 新发现的 issue → 归档到 docs/backlog.md
5. 重要决策 → 记录决策背景和理由到相关文档
6. 未完成的工作 → 在 TODO.md 或 backlog.md 中留下进度记录

## 跨 Session 接力原则
- 每个逻辑工作单元完成后立即 commit + 更新文档
- 不要假设下个 session 能理解你的隐式意图
- 关键设计决策必须文档化，不能只存在于代码注释中
- 遵循"文档是意图源码，代码是编译产物"

## 反模式（禁止）
- ❌ 不读文档就开始改代码
- ❌ 改了代码不更新文档
- ❌ 在文档中留下过时信息不标注
- ❌ 假设"下个 AI 会知道我为什么这么做"
- ❌ 将重要上下文只写在对话中而不沉淀到文档

## 与现有机制的关系
- todo-archiver skill：管理 issue 的归档与同步
- auto-commit-enforcer skill：确保原子提交
- inbox 机制：外部信息入库
- 年轮体系：版本验收报告
```

### Step 2: 更新 `CLAUDE.md`

在"开发规范"部分新增 2-3 行关于项目记忆的核心不变式：

```markdown
### 项目记忆
- 本项目文档系统同时服务于人类与 AI，是跨 session 的项目记忆系统
- 新 session 启动时必须先读 CLAUDE.md + backlog.md + version-history.md 理解项目状态
- 代码变更必须同步更新文档，确保下个 session 能理解本次变更意图
- 详细方法论：调用 skill `project-memory`；完整参考：[docs/methodology.md](docs/methodology.md)
```

### Step 3: 更新 `docs/methodology.md`

在末尾"相关文档"部分新增引用：

```markdown
- [项目记忆系统使用指南](../.trae/skills/project-memory/SKILL.md) — 跨 session 项目记忆读写方法论
```

同时在"核心理念"部分新增第 4 条：

```markdown
4. **文档即记忆**
   - 文档系统是项目的跨 session 记忆系统
   - 每个 AI session 都是 stateless 的，唯一延续性来自文档
   - 读写分离：读记忆理解状态，写记忆延续进度
   - 详见 `project-memory` skill
```

### Step 4: 归档 TODO.md 中的未归档条目

将 TODO.md 第 9 行的条目追加归档标记：

```
- [ ] 入库"AI编程协作策略"对话，创建`Project Context Skill`技能，实现对单个feature的跨session开发进度把控 📋 2026-04-24 归档为 [FEAT-029]
```

### Step 5: 在 `docs/backlog.md` 中新增 FEAT-029

在 Feature 表格中新增：

```markdown
| FEAT-029 | 项目记忆系统 Skill（project-memory） | [TODO.md](../TODO.md) | ✅ 已完成 | 中 | 跨 session 项目记忆读写方法论，替代原"Project Context Skill"概念 |
```

### Step 6: 更新 `docs/backlog.md` 统计表

更新 Feature 行的已完成数（20 → 21）和待处理数（17 → 17，因为 FEAT-029 直接标已完成）。

### Step 7: 原子提交

每完成一个逻辑步骤即提交，遵循 auto-commit-enforcer 规范。

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `.trae/skills/project-memory/SKILL.md` | 新建 |
| `CLAUDE.md` | 编辑（新增项目记忆段落） |
| `docs/methodology.md` | 编辑（新增核心理念第 4 条 + 相关文档引用） |
| `TODO.md` | 编辑（追加归档标记） |
| `docs/backlog.md` | 编辑（新增 FEAT-029 + 更新统计表） |
