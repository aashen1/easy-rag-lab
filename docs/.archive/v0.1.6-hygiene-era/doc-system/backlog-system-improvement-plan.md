# Backlog 管理系统改进方案

> 感觉不够好。先放着，之后出一版更合适的。

## 一、现状分析与痛点总结

### 1.1 当前系统架构

当前 backlog 管理系统由以下组件构成：

| 组件 | 文件 | 管理者 | 职责 |
|------|------|--------|------|
| TODO.md | 项目根目录 | 人类 | 随笔式待办笔记，按日期倒序 |
| docs/backlog.md | docs/ | AI | 结构化 issue 追踪，按类型分表 |
| docs/reviews/issues/ | docs/ | AI | issue 详情文件 |
| .trae/skills/todo-archiver/ | .trae/ | AI Skill | 归档流程指导 |
| .trae/skills/project-memory/ | .trae/ | AI Skill | 跨 session 记忆读写 |

### 1.2 三大核心痛点

#### 痛点 1：多 worktree 并行开发时 issue 编号冲突

**现象**：当前编号机制为递增式（BUG-001, BUG-002, ...），在多个 git worktree 并行开发时：
- worktree-A 创建了 BUG-032
- worktree-B 也创建了 BUG-032
- merge 时两个 BUG-032 描述不同，AI 甚至会误删其中一个

**根因**：递增编号依赖全局状态（当前最大编号），而 git worktree 各自独立，无法实时同步。

#### 痛点 2：issue 状态管理混乱

**现象**：
- 已完成与未完成 issue 混在同一文件中（backlog.md 281 行，已完成条目占 35%）
- 状态标签（📋 待处理 / 🔄 进行中 / ✅ 已完成 / ⏳ 已延期）缺乏自动流转机制
- 优先级仅在部分类型（Feature/Refactor）有"规模"字段，且无 P0/P1/P2 分级
- 统计概览表需手动维护，容易与实际不同步

**根因**：纯 Markdown 表格无法表达复杂状态机，且所有状态变更依赖 AI 手动操作。

#### 痛点 3：单文件过长导致 AI 读取 TOKEN 消耗过高

**现象**：
- backlog.md 约 281 行、30,000+ 字符，估算 15,000-20,000 token
- 每次 session 启动 Tier 1 必读，但 35% 内容是已完成条目
- TODO.md 也越来越长（289 行），verbose 条目大量冗余
- project-memory Skill 要求 Tier 1 必读 backlog.md 统计表，但实际 AI 往往读取全文

**根因**：单文件线性增长，无分页/分区机制，已完成条目不会自动归档。

---

## 二、方案评估与对比

### 2.1 方案 A：GitHub Issues 集成

#### 架构

```
TODO.md (人类随笔)
    ↓ gh issue create / AI CLI
GitHub Issues (集中式)
    ↓ gh issue list/read
AI Session (读取)
    ↓ gh issue close/edit
GitHub Issues (状态更新)
```

#### 优点
- **天然解决编号冲突**：GitHub 分配全局唯一 #ID，无撞车可能
- **状态管理成熟**：label（bug/feature/refactor）、milestone、assignee、project board
- **多 worktree 友好**：集中式存储，任何 worktree 操作的都是同一份数据
- **搜索与过滤强大**：`gh issue list --label bug --state open`
- **协作友好**：多人项目天然支持

#### 缺点
- **网络依赖**：AI 每次读取需调用 `gh` CLI 或 API，离线环境不可用
- **TOKEN 消耗未必降低**：`gh issue list` 返回 JSON 仍需 AI 解析，且 GitHub API 有速率限制
- **与现有文档体系割裂**：backlog.md 作为"年轮"的一部分，迁移到 GitHub 后失去文档内聚性
- **AI 交互复杂度增加**：需封装 `gh` 命令为 Skill，错误处理（网络超时、认证失败）增加
- **隐私顾虑**：如果项目未开源，issue 内容在 GitHub 上可见
- **违背项目哲学**：项目核心是"文档是意图源码"，GitHub Issues 将意图从文档中剥离

#### 可行性评分：⭐⭐⭐（3/5）

适合多人协作的开源项目，但对当前单开发者+AI 的场景过于重量级。

---

### 2.2 方案 B：本地轻量级 Issue 管理系统（SQLite + CLI）

#### 架构

```
TODO.md (人类随笔)
    ↓ issue_cli.py add
SQLite DB (docs/.issues/db.sqlite)
    ↓ issue_cli.py list/show
AI Session (读取)
    ↓ issue_cli.py update/close
SQLite DB (状态更新)
    ↓ issue_cli.py export
backlog.md (只读导出/报告)
```

#### 优点
- **彻底解决编号冲突**：使用 UUID 或 hash 指纹作为主键
- **状态管理自动化**：SQLite 支持事务、约束、触发器
- **TOKEN 消耗可控**：`issue_cli.py list --status open --priority high` 只返回活跃条目
- **离线可用**：纯本地，无网络依赖
- **查询灵活**：SQL 的强大过滤能力
- **与文档体系兼容**：可导出为 Markdown，保持"年轮"连续性

#### 缺点
- **新增依赖**：SQLite 是 Python 标准库自带，但需维护 schema 和 CLI
- **二进制文件与 git 冲突**：SQLite DB 是二进制文件，merge 困难
- **AI 交互需 CLI**：AI 需通过 `pixi run issue list` 等命令操作，增加工具链复杂度
- **学习成本**：需记住 CLI 命令，不如直接编辑 Markdown 直观
- **备份风险**：单文件 DB 损坏则全部丢失

#### 可行性评分：⭐⭐⭐⭐（4/5）

技术上最完善，但引入了二进制文件与 git 的根本矛盾。

---

### 2.3 方案 C：改进型 Markdown 分片系统（推荐方案）

#### 架构

```
TODO.md (人类随笔，不变)
    ↓ todo-archiver skill (改进)
docs/backlog/
    index.md          ← Tier 1 必读：统计概览 + 活跃 issue 索引
    active/
        bugs.md       ← 仅待处理/进行中的 Bug
        features.md   ← 仅待处理/进行中的 Feature
        refactors.md  ← 仅待处理/进行中的 Refactor
        optimizations.md
        investigations.md
        tests.md
    completed/
        YYYY-MM.md     ← 按月归档已完成条目
    detail/
        <short-id>-<slug>.md  ← issue 详情（原 reviews/issues/）
```

#### 核心设计

##### 2.3.1 编号生成：短哈希指纹

**算法**：`<TYPE>-<SHORT_HASH>`

```
输入：issue 类型前缀 + 创建时间戳 + worktree 标识 + 描述前 50 字符
处理：SHA-256 → 取前 6 位十六进制
输出：BUG-a3f7c2, FEAT-9b1e04, RF-d42a88
```

**冲突概率**：6 位十六进制 = 24 bit，约 1600 万种组合。按生日悖论，约 4000 个 issue 时才有 50% 概率出现一次冲突，远超项目需求。

**worktree 标识**：使用 `git rev-parse --show-toplevel` 的哈希后 4 位作为 worktree 标识，嵌入编号元数据中（不体现在编号本身，但记录在 issue 文件中）。

**对比递增编号的优势**：
- 无全局状态依赖，各 worktree 独立生成
- 编号本身携带信息量（可反推创建上下文）
- merge 时即使编号相同也可通过元数据区分

##### 2.3.2 状态管理：明确的状态机

```
┌──────────┐  start work  ┌──────────┐  complete  ┌──────────┐
│  待处理   │─────────────→│  进行中   │──────────→│  已完成   │
│ 📋 open  │              │ 🔄 wip   │           │ ✅ done  │
└──────────┘              └──────────┘           └──────────┘
     │                         │
     │ defer                   │ block
     ↓                         ↓
┌──────────┐              ┌──────────┐
│  已延期   │              │  阻塞    │
│ ⏳ defer │              │ 🚧 block │
└──────────┘              └──────────┘
```

**状态流转规则**：
- `open → wip`：AI 或人类开始处理时标记
- `wip → done`：代码提交 + 测试通过后标记
- `open → defer`：明确标注延期原因
- `wip → block`：标注阻塞原因和依赖
- `defer → open`：条件成熟时恢复
- `block → wip`：阻塞解除后恢复

**优先级体系**：

| 级别 | 标签 | 含义 | SLA |
|------|------|------|-----|
| P0 | 🔴 critical | 阻塞性问题，无法继续开发 | 24h 内响应 |
| P1 | 🟠 high | 重要功能或影响较大的 bug | 本周内处理 |
| P2 | 🟡 medium | 常规功能或优化 | 本迭代处理 |
| P3 | 🟢 low | 锦上添花 | 有空再做 |

**自动状态更新**：
- todo-archiver skill 在归档时自动设置初始状态和优先级
- AI 在开始处理 issue 时自动将状态从 `open` 改为 `wip`
- commit message 中引用 issue ID 时（如 `fix: resolve BUG-a3f7c2`），自动标记为 `done`

##### 2.3.3 TOKEN 优化：分片 + 按需加载

**核心思路**：将单一大文件拆分为多个小文件，AI 只读取当前需要的部分。

**Tier 1 必读（约 50 行，< 2000 token）**：

```markdown
# Backlog Index

> 最后更新：2026-04-27 | 活跃 issue: 23 | 已完成: 82

## 统计概览
| 类型 | 待处理 | 进行中 | 已延期 | 阻塞 | 本月完成 |
|------|--------|--------|--------|------|----------|
| Bug | 5 | 0 | 2 | 0 | 3 |
| Feature | 12 | 0 | 0 | 0 | 2 |
| ... | ... | ... | ... | ... | ... |

## 高优先级（P0/P1）
| ID | 类型 | 描述 | 状态 |
|----|------|------|------|
| BUG-a3f7c2 | Bug | expected_sources 标注错误 | 📋 open |
| FEAT-9b1e04 | Feature | 断点续传 | 📋 open |
```

**Tier 2 按需读取**：
- 需要处理 Bug → 读取 `active/bugs.md`
- 需要规划 Feature → 读取 `active/features.md`
- 需要了解历史 → 读取 `completed/2026-04.md`

**对比当前系统的 TOKEN 节省**：

| 场景 | 当前系统 | 改进后 | 节省 |
|------|---------|--------|------|
| 新 session 启动 | ~18,000 token (全文) | ~2,000 token (index) | 89% |
| 处理特定类型 issue | ~18,000 token | ~3,000 token (index+单类型) | 83% |
| 查看已完成 issue | ~18,000 token | ~4,000 token (单月) | 78% |

##### 2.3.4 与 AI 的交互方式

**todo-archiver skill 改进**：

1. **归档新 issue**：
   - 生成短哈希 ID（取代递增编号）
   - 写入对应类型的 `active/<type>.md`
   - 创建 `detail/<id>-<slug>.md`（如需详情）
   - 更新 `index.md` 统计表和高优先级列表
   - 在 TODO.md 追加归档标记

2. **状态更新**：
   - AI 开始工作时：`open → wip`
   - 代码提交后：`wip → done`，将条目从 `active/` 移至 `completed/YYYY-MM.md`
   - 更新 `index.md`

3. **查询**：
   - AI 读取 `index.md` 获取全局视图
   - 按需深入 `active/` 或 `completed/`

**project-memory skill 适配**：
- Tier 1 必读从 `docs/backlog.md` 改为 `docs/backlog/index.md`
- Tier 2 按需读取 `docs/backlog/active/<type>.md`

---

## 三、推荐方案详细设计（方案 C）

### 3.1 目录结构

```
docs/backlog/
├── index.md                    # 统计概览 + 高优先级索引（Tier 1 必读）
├── active/                     # 活跃 issue（仅 open/wip/defer/block）
│   ├── bugs.md                 # Bug 类型
│   ├── features.md             # Feature 类型
│   ├── refactors.md            # Refactor 类型
│   ├── optimizations.md        # Optimization 类型
│   ├── investigations.md       # Investigation 类型
│   └── tests.md                # Test 类型
├── completed/                  # 已完成 issue（按月归档）
│   ├── 2026-04.md
│   ├── 2026-05.md
│   └── ...
└── detail/                     # issue 详情文件
    ├── bug-a3f7c2-expected-sources.md
    ├── feat-9b1e04-resume-experiment.md
    └── ...
```

### 3.2 编号生成算法

```python
import hashlib
from datetime import datetime
from pathlib import Path

TYPE_PREFIXES = {
    "bug": "BUG",
    "feature": "FEAT",
    "refactor": "RF",
    "optimization": "OPT",
    "investigation": "INV",
    "test": "TEST",
}

def generate_issue_id(
    issue_type: str,
    description: str,
    worktree_root: Path | None = None,
) -> str:
    prefix = TYPE_PREFIXES[issue_type]
    timestamp = datetime.now().isoformat()
    worktree_id = ""
    if worktree_root:
        worktree_id = hashlib.sha256(
            str(worktree_root).encode()
        ).hexdigest()[:4]
    raw = f"{prefix}:{timestamp}:{worktree_id}:{description[:50]}"
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:6]
    return f"{prefix}-{short_hash}"

def check_id_exists(issue_id: str, backlog_dir: Path) -> bool:
    for md_file in backlog_dir.rglob("*.md"):
        if issue_id in md_file.read_text(encoding="utf-8"):
            return True
    return False

def generate_unique_id(
    issue_type: str,
    description: str,
    backlog_dir: Path,
    worktree_root: Path | None = None,
    max_retries: int = 3,
) -> str:
    for _ in range(max_retries):
        issue_id = generate_issue_id(issue_type, description, worktree_root)
        if not check_id_exists(issue_id, backlog_dir):
            return issue_id
    raise RuntimeError(f"Failed to generate unique ID after {max_retries} retries")
```

**关键设计决策**：
- 使用 SHA-256 前 6 位而非 UUID，因为 6 位十六进制已足够（1600 万种组合）
- worktree_root 哈希嵌入输入但不体现在输出编号中，保持编号简洁
- 冲突检测通过全文搜索实现（文件数量少，性能可接受）
- 如极端情况下冲突，重试最多 3 次（时间戳变化会改变哈希）

### 3.3 各文件格式

#### index.md（Tier 1 必读）

```markdown
# Backlog Index

> 最后更新：YYYY-MM-DD | 活跃 issue: N | 已完成: M

## 统计概览

| 类型 | 待处理 | 进行中 | 已延期 | 阻塞 | 本月完成 |
|------|--------|--------|--------|------|----------|
| Bug | N | N | N | N | N |
| Feature | N | N | N | N | N |
| Refactor | N | N | N | N | N |
| Optimization | N | N | N | N | N |
| Investigation | N | N | N | N | N |
| Test | N | N | N | N | N |

## P0/P1 高优先级

| ID | 类型 | 描述 | 状态 | 优先级 |
|----|------|------|------|--------|
| BUG-xxxxxx | Bug | ... | 📋 open | 🔴 P0 |

## 最近变更

| 日期 | ID | 变更 |
|------|-----|------|
| YYYY-MM-DD | BUG-xxxxxx | 新增 |
| YYYY-MM-DD | FEAT-xxxxxx | 状态: open → wip |
```

#### active/bugs.md

```markdown
# Active Bugs

## P0 🔴 Critical

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| BUG-xxxxxx | ... | ... | 📋 open | ... |

## P1 🟠 High

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|

## P2 🟡 Medium

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|

## P3 🟢 Low

| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|

## 已延期

| ID | 描述 | 来源 | 状态 | 延期原因 |
|----|------|------|------|----------|

## 阻塞

| ID | 描述 | 来源 | 状态 | 阻塞原因 |
|----|------|------|------|----------|
```

#### completed/2026-04.md

```markdown
# Completed Issues — 2026-04

## Bug

| ID | 描述 | 来源 | 完成日期 | 优先级 |
|----|------|------|---------|--------|
| BUG-xxxxxx | ... | ... | 2026-04-26 | P1 |

## Feature

| ID | 描述 | 来源 | 完成日期 | 优先级 | 规模 |
|----|------|------|---------|--------|------|
| FEAT-xxxxxx | ... | ... | 2026-04-24 | P2 | 中 |
```

### 3.4 迁移策略

#### 阶段 1：创建新结构（不破坏旧结构）

1. 创建 `docs/backlog/` 目录结构
2. 编写迁移脚本，将现有 backlog.md 中的条目转换为新格式
3. 旧 ID（BUG-021 等）保持不变，新 issue 使用短哈希 ID
4. 旧 `docs/backlog.md` 重命名为 `docs/backlog-legacy.md`，移入 `.trashbin/`

#### 阶段 2：更新 Skill 和规则

1. 更新 `todo-archiver` skill 适配新目录结构
2. 更新 `project-memory` skill 的 Tier 1 读取路径
3. 更新 `CLAUDE.md` 中的 backlog 引用
4. 更新 `docs/methodology.md` 中的 ID 命名规范

#### 阶段 3：验证与清理

1. 运行迁移脚本，验证数据完整性
2. 确认 AI session 能正确读取新结构
3. 清理旧文件

### 3.5 旧 ID 兼容方案

对于已存在的递增编号 issue（BUG-001 ~ BUG-031, FEAT-001 ~ FEAT-043 等）：

- **保留旧编号**：不强制迁移，旧 ID 继续有效
- **混合编号**：旧 issue 保持 BUG-021 格式，新 issue 使用 BUG-a3f7c2 格式
- **TODO.md 归档标记**：旧归档标记 `📋 2026-04-21 归档为 [RF-007]` 保持不变
- **自然过渡**：随着旧 issue 逐步完成归档，递增编号将自然消失

---

## 四、方案对比总结

| 维度 | 方案 A: GitHub Issues | 方案 B: SQLite + CLI | 方案 C: Markdown 分片 |
|------|----------------------|---------------------|---------------------|
| 编号冲突 | ✅ 完全解决 | ✅ 完全解决 | ✅ 完全解决 |
| 状态管理 | ✅ 成熟 | ✅ 最强 | ⚠️ 改善但非完美 |
| TOKEN 优化 | ⚠️ 有限 | ✅ 最优 | ✅ 优秀（89% 节省） |
| 离线可用 | ❌ 需网络 | ✅ 纯本地 | ✅ 纯本地 |
| git 友好 | ✅ 无文件冲突 | ❌ 二进制冲突 | ✅ 纯文本 |
| 学习成本 | ⚠️ 需学 gh CLI | ⚠️ 需学 issue CLI | ✅ 无新工具 |
| 文档内聚性 | ❌ 割裂 | ⚠️ 需导出 | ✅ 保持一致 |
| 实现复杂度 | 低（用现成平台） | 高（需开发 CLI） | 中（迁移 + Skill 更新） |
| 与现有体系兼容 | ❌ 需大幅改造 | ⚠️ 需适配层 | ✅ 渐进式迁移 |

---

## 五、实施计划

### Step 1：创建目录结构与迁移脚本
- 创建 `docs/backlog/` 完整目录结构
- 编写 Python 迁移脚本 `scripts/migrate_backlog.py`
- 将现有 backlog.md 条目按状态和类型拆分到对应文件
- 旧 ID 保持不变，验证数据完整性

### Step 2：实现短哈希 ID 生成
- 在迁移脚本中集成 ID 生成函数
- 编写 pytest 测试验证唯一性和冲突检测
- 旧 issue 保留递增编号，仅新 issue 使用短哈希

### Step 3：更新 todo-archiver Skill
- 适配新目录结构（写入 `active/<type>.md` 而非单文件）
- 集成短哈希 ID 生成逻辑
- 增加状态流转规则（open → wip → done）
- 增加优先级评估逻辑
- 完成后自动移动条目到 `completed/YYYY-MM.md`
- 更新 `index.md` 统计表

### Step 4：更新 project-memory Skill
- Tier 1 必读改为 `docs/backlog/index.md`
- Tier 2 按需读取 `docs/backlog/active/<type>.md`

### Step 5：更新项目规则与文档
- 更新 `CLAUDE.md` 中的 backlog 引用和 ID 命名规范
- 更新 `docs/methodology.md` 中的待做事项管理章节
- 更新 TODO.md 归档标记格式说明

### Step 6：验证与清理
- 新 session 测试完整归档流程
- 验证 AI 能正确读取分片结构
- 旧 `docs/backlog.md` 移入 `.trashbin/`
- 运行 lint 检查

---

## 六、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 迁移过程中数据丢失 | 高 | 先备份，迁移后逐条校验 |
| AI 不适应新目录结构 | 中 | Skill 文档详尽，含完整示例 |
| 短哈希 ID 可读性差 | 低 | 人类仍可通过描述识别，AI 通过 ID 精确引用 |
| 分片文件过多 | 低 | 活跃文件仅 7 个（index + 6 类型），可接受 |
| 旧 TODO.md 归档标记不兼容 | 低 | 旧标记保持不变，新标记使用新 ID 格式 |
