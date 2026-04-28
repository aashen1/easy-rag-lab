# 文档深度重构计划

> 目标：提升文档条理性与叙事性，打造"项目博物馆"效果，满足开源与简历展示需求

---

## 一、现状诊断

### 1.1 目录结构现状

```
docs/
├── README.md                    # 导航索引（严重过时）
├── getting-started.md           # 快速上手
├── version-history.md           # 版本演进年轮（质量好）
├── methodology.md               # 抛接球年轮方法论
├── dev-story.md                 # 开发随笔（高质量人文内容）
│
├── user-guides/                 # 17 篇用户指南
├── dev-guides/                  # 8 篇开发指南
│
└── .archive/                    # 历史归档（组织度不足）
    ├── plans/uncatogarized/     # ~70 篇计划文档，拼写错误
    ├── reviews/                 # 版本验收报告（部分有版本目录）
    ├── specs/uncatogarized/     # ~30 个 spec 目录，拼写错误
    ├── troubleshooting/         # 故障排查文档
    └── (散落文件)               # inbox-log.md, idea-ai-era-git-practice.md 等
```

### 1.2 核心问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **77 处失效链接** | 🔴 严重 | README.md 有 25 处，遍及 15+ 文件 |
| **README.md 完全过时** | 🔴 严重 | 仍指向旧 `guides/operations/` 结构，目录树示意图也是旧的 |
| **归档目录组织度不足** | 🟡 中等 | `uncatogarized/` 拼写错误+内容杂乱，散落文件未归类 |
| **部分文档分类不当** | 🟡 中等 | `rag-optimization-implementation.md`（dev 向）在 user-guides/，`test-layering-and-time-budgets-chat-log.md`（聊天记录）在 dev-guides/ |
| **缺少"博物馆导览"** | 🟡 中等 | 有丰富的历史素材，但缺少叙事性的索引/导览文档 |
| **methodology.md 过时引用** | 🟡 中等 | 引用已不存在的 `backlog.md`、`.trae/skills/` 路径 |

---

## 二、重构方案

### 总体思路

**不搞大搬家，做精准手术。** 归档目录已有 100+ 文件，全面按版本重新分拣成本极高且容易引入新错误。策略是：

1. **活跃文档**（user-guides/、dev-guides/、docs 根目录）：精准修复，确保零失效链接
2. **归档文档**（.archive/）：轻量整理 + 新增"博物馆导览"索引，用叙事串联已有素材
3. **README.md**：完全重写，作为项目文档的"门面"

### 2.1 Phase 1：活跃文档分类调整

**目标**：确保 user-guides/ 和 dev-guides/ 中的文档分类准确

| 操作 | 文件 | 原因 |
|------|------|------|
| user-guides/ → dev-guides/ | `rag-optimization-implementation.md` | 文档自称"面向开发者"，介绍实现细节和测试策略 |
| user-guides/ → dev-guides/ | `profiling-configuration.md` | 性能分析配置是开发/调优场景，非普通用户需求 |
| dev-guides/ → .archive/ | `test-layering-and-time-budgets-chat-log.md` | AI 聊天记录，非指南文档，应归档 |
| dev-guides/ → .archive/ | `ruff-usage-guide.md` | 检查后决定：如内容与 `lint-and-precommit.md` 高度重复则归档，否则保留 |

调整后：

```
user-guides/  (14 篇，纯用户向)
├── cli-reference.md
├── config-reference.md
├── pdf-parsing.md
├── question-generation.md
├── evaluation-metrics.md
├── ragas-evaluation.md
├── experiment-system.md
├── hyperparameter-guide.md
├── golden-testset-generation.md
├── golden-test-review.md
├── test-set-management.md
├── meal-system.md
├── streamlit-web-demo.md
├── token-tracking.md
└── issue-system.md

dev-guides/  (7~8 篇，纯开发向)
├── architecture.md
├── testing.md
├── test-layering-and-time-budgets.md
├── rag-optimization-implementation.md    ← 从 user-guides 移入
├── profiling-configuration.md            ← 从 user-guides 移入
├── lint-and-precommit.md
├── commit-conventions.md
└── release-cadence.md
```

### 2.2 Phase 2：归档目录整理

**目标**：修复明显问题，新增导览索引，不做全面重分拣

#### 2.2.1 修复拼写错误

- `plans/uncatogarized/` → `plans/unattributed/`
- `specs/uncatogarized/` → `specs/unattributed/`

> 改名理由：`uncatogarized` 是拼写错误，且 `unattributed`（未归属版本）比 `uncategorized`（未分类）更准确地描述这些文件的状态——它们有分类（plan/spec），只是没有归属到具体版本。

#### 2.2.2 归档散落文件

将 `.archive/` 根目录下的散落文件移入合适子目录：

| 文件 | 目标位置 | 理由 |
|------|---------|------|
| `inbox-log.md` | `.archive/operational/` | 运营日志类 |
| `idea-ai-era-git-practice.md` | `.archive/operational/` | 随笔/想法类 |
| `hybrid-metrics-fix.md` | `.archive/troubleshooting/` | 故障修复类 |
| `backlog-2026-04-28.md` | `.archive/operational/` | 历史快照类 |
| `issue-system-dev-notes.md` | `.archive/operational/` | 开发笔记类 |
| `pdf-preview-lightweight-plan.md` | `.archive/plans/unattributed/` | 计划文档类 |

#### 2.2.3 新增"博物馆导览"文档

创建 `.archive/timeline.md`，作为归档区的叙事索引：

```markdown
# 项目演进时间线

> 这是归档区的导览文档。每个版本都是一圈"年轮"，记录着当时的决策、挣扎和突破。

## 时间线总览

| 版本 | 主题 | 一句话 | 关键文档 |
|------|------|--------|---------|
| v0.1.0 | MVP 基础链路 | ... | ... |
| v0.1.1~5 | MVP + 评测 + 自动化 | ... | ... |
| ... | ... | ... | ... |

## 各版本详情

### v0.1.0 — MVP 基础链路 (2026-04-15)
- 决策背景：...
- 关键计划：[链接]
- 验收报告：[链接]
- 经验教训：...

### v0.1.9 — 评测双引擎 (2026-04-21)
- ...
```

这个文档的价值：
- 为访客提供**叙事入口**，不需要在 100+ 文件中翻找
- 将散落在 `unattributed/` 中的文件**通过链接关联到对应版本**
- 物理文件不需要移动，但逻辑上通过导览串联

#### 2.2.4 更新 `.archive/README.md`

重写归档区说明，明确"项目博物馆"定位：

```markdown
# 项目博物馆

这里存放着项目从 git init 以来的所有开发痕迹。

## 如何浏览

1. **时间线导览**：[timeline.md](timeline.md) — 按版本浏览项目演进
2. **按类型浏览**：plans/ | specs/ | reviews/ | troubleshooting/
3. **给 AI 看**：这些文档主要供 AI 在开发时追溯决策背景

## 目录说明

- `plans/` — 开发计划文档（TRAE /plan 模式产出）
  - `v0.1.9/` — 已归属版本的计划
  - `unattributed/` — 未归属具体版本的计划
- `specs/` — 规范文档（TRAE /spec 模式产出，三件套：spec.md + tasks.md + checklist.md）
- `reviews/` — 版本验收报告
- `troubleshooting/` — 故障排查记录
- `operational/` — 运营日志、历史快照
```

### 2.3 Phase 3：docs 根目录文档调整

**目标**：优化根目录文档的定位和内容

| 文件 | 操作 | 说明 |
|------|------|------|
| `README.md` | **完全重写** | 作为项目文档门面，反映新结构 |
| `getting-started.md` | 修复链接 | 4 处失效链接需修复 |
| `version-history.md` | 修复链接 | 6 处失效链接需修复 |
| `methodology.md` | 修复链接+更新过时引用 | 4 处失效链接 + `backlog.md` 引用需更新 |
| `dev-story.md` | 保持不变 | 高质量内容，无需修改 |

#### README.md 重写方案

新的 README.md 应包含：

1. **项目一句话介绍** — 金融研报 RAG 问答系统
2. **三通道导航** — 面向不同受众的快速入口
   - 👤 用户通道 → user-guides/
   - 🔧 开发者通道 → dev-guides/
   - 🏛️ 项目博物馆 → .archive/timeline.md
3. **亮点文档推荐** — dev-story.md、version-history.md
4. **目录结构图** — 反映真实当前结构
5. **文档规范** — 保留命名规范和状态标签说明

### 2.4 Phase 4：全面修复失效链接

**目标**：零失效链接

#### 修复策略

按文件优先级分批修复：

**批次 1：README.md（25 处）**
- 旧 `guides/operations/` → `user-guides/`
- 旧 `guides/development/` → `dev-guides/`
- `troubleshooting/` → `.archive/troubleshooting/`
- `architecture.md` → `dev-guides/architecture.md`
- `cli-reference.md` → `user-guides/cli-reference.md`
- `config-reference.md` → `user-guides/config-reference.md`
- 删除指向不存在文件的链接（`artifact-path-migration.md`、`issue-system-dev-notes.md`）

**批次 2：根目录文档（14 处）**
- `getting-started.md`：4 处路径修正
- `version-history.md`：6 处归档路径修正 + 删除 `.trae/specs/` 引用
- `methodology.md`：4 处修正（`backlog.md` → `.issues/`，归档路径修正）

**批次 3：user-guides/ 内部（~25 处）**
- `config-reference.md`：5 处 `guides/` → 同目录
- `evaluation-metrics.md`：2 处归档路径 + 1 处 config 路径
- `question-generation.md`：1 处归档路径 + 1 处 config 路径
- `pdf-parsing.md`：2 处路径修正
- `streamlit-web-demo.md`、`meal-system.md`、`token-tracking.md`、`hyperparameter-guide.md`、`experiment-system.md`、`rag-optimization-implementation.md`：各 1~2 处
- `test-set-management.md`：5 处（`.trae/specs/` 引用 + `guides/` 引用）

**批次 4：dev-guides/ 内部（~5 处）**
- `testing.md`：2 处路径修正
- `architecture.md`：2 处 `guides/` → `../user-guides/`
- `release-cadence.md`：1 处路径修正
- `test-layering-and-time-budgets.md`：1 处路径修正

**批次 5：归档文档内部链接**
- 检查 `.archive/` 内部文档的交叉引用，按需修复

#### 链接修复规则

| 场景 | 修复方式 |
|------|---------|
| 目标文件在 user-guides/ | 从同目录引用用 `filename.md`，从 dev-guides/ 引用用 `../user-guides/filename.md` |
| 目标文件在 dev-guides/ | 从同目录引用用 `filename.md`，从 user-guides/ 引用用 `../dev-guides/filename.md` |
| 目标文件在 docs/ 根目录 | 从子目录引用用 `../filename.md` |
| 目标文件已归档到 .archive/ | 根据上下文决定：如仍有参考价值则指向 `.archive/` 路径；如已完全过时则删除链接 |
| 目标文件完全不存在 | 删除链接，保留文字说明 |

### 2.5 Phase 5：验证与收尾

1. **链接验证**：用脚本扫描所有 markdown 文件，确认零失效链接
2. **目录结构验证**：确认 README.md 中的目录树与实际一致
3. **内容抽检**：抽查 5+ 文档，确认链接可点击、内容可访问
4. **提交**：按逻辑单元分批提交

---

## 三、执行顺序与提交策略

```
Phase 1 (分类调整)
  ├── 移动 rag-optimization-implementation.md → dev-guides/
  ├── 移动 profiling-configuration.md → dev-guides/
  ├── 移动 test-layering-and-time-budgets-chat-log.md → .archive/
  └── 评估 ruff-usage-guide.md 是否归档
  → commit: "refactor: reclassify docs between user-guides and dev-guides"

Phase 2 (归档整理)
  ├── 重命名 uncatogarized/ → unattributed/
  ├── 创建 .archive/operational/ 并移入散落文件
  ├── 创建 .archive/timeline.md
  ├── 重写 .archive/README.md
  └── 更新 .archive/archive-log.md
  → commit: "docs: restructure archive with timeline guide and proper organization"

Phase 3 (根目录文档)
  ├── 重写 docs/README.md
  ├── 修复 getting-started.md 链接
  ├── 修复 version-history.md 链接
  └── 修复 methodology.md 链接和过时引用
  → commit: "docs: rewrite README and fix root-level doc links"

Phase 4 (链接修复)
  ├── 批次 1: README.md 链接（已在 Phase 3 中完成）
  ├── 批次 2: 根目录文档链接（已在 Phase 3 中完成）
  ├── 批次 3: user-guides/ 内部链接
  ├── 批次 4: dev-guides/ 内部链接
  └── 批次 5: .archive/ 内部链接
  → commit: "docs: fix all broken links in user-guides"
  → commit: "docs: fix all broken links in dev-guides"
  → commit: "docs: fix broken links in archive docs"

Phase 5 (验证)
  ├── 全量链接扫描
  ├── 目录结构验证
  └── 内容抽检
  → commit: "docs: verify and finalize documentation restructure"
```

---

## 四、风险与注意事项

1. **文件移动后 git 历史**：使用 `git mv` 保留文件历史
2. **归档文档内部链接**：归档文档之间可能也有交叉引用，移动文件后需检查
3. **CLAUDE.md 引用**：CLAUDE.md 中引用了 `docs/guides/<feature>.md` 和 `docs/troubleshooting/<bug-name>.md`，需同步更新
4. **不过度整理归档**：归档区的 100+ 文件不需要逐一按版本重分拣，通过 `timeline.md` 导览文档实现逻辑组织即可
5. **保留 .archive/ 的隐藏属性**：归档区以 `.` 开头，在 GitHub 上默认不显眼，适合存放"博物馆"内容而不干扰主文档导航

---

## 五、预期成果

重构后的文档体系：

```
docs/
├── README.md                    # 🚪 门面 — 三通道导航
├── getting-started.md           # ⚡ 快速上手
├── version-history.md           # 📜 版本年轮（叙事入口）
├── methodology.md               # 🧠 方法论
├── dev-story.md                 # ✍️ 开发随笔（人文入口）
│
├── user-guides/                 # 👤 用户通道（14 篇）
│   ├── cli-reference.md
│   ├── config-reference.md
│   ├── pdf-parsing.md
│   ├── ...
│
├── dev-guides/                  # 🔧 开发者通道（7~8 篇）
│   ├── architecture.md
│   ├── testing.md
│   ├── rag-optimization-implementation.md
│   ├── ...
│
└── .archive/                    # 🏛️ 项目博物馆
    ├── README.md                # 博物馆指南
    ├── timeline.md              # 时间线导览（新增）
    ├── archive-log.md
    │
    ├── plans/                   # 计划文档
    │   ├── v0.1.9/
    │   └── unattributed/
    │
    ├── specs/                   # 规范文档
    │   ├── v0.1.9/
    │   └── unattributed/
    │
    ├── reviews/                 # 版本验收
    │   ├── v0.1.5/
    │   ├── v0.1.6/
    │   ├── ...
    │   ├── sessions/
    │   └── investigations/
    │
    ├── troubleshooting/         # 故障排查
    │   └── resolved/
    │
    └── operational/             # 运营日志（新增分类）
```

**不同受众的体验**：

| 受众 | 入口 | 体验 |
|------|------|------|
| 普通用户 | README → user-guides/ | 14 篇精选指南，零噪音 |
| 开发者 | README → dev-guides/ | 架构、测试、规范，直入技术 |
| 项目历史爱好者 | README → .archive/timeline.md | 按版本浏览演进历程，每版有故事 |
| 面试官/简历审阅者 | README → dev-story.md + version-history.md | 人文+技术双线叙事 |
