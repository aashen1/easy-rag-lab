# 文档管理重构计划（V2 - 审查修正版）

> **修订说明**：本版本基于 V1 进行了全面审查，修正了 5 处事实错误，移除了 3 处过度设计，调整了 4 处不符合最佳实践的设计。

---

## 一、现状调研

### 1.1 文档清单

项目当前共有 **50+ 个 markdown 文件**，分布在 **7+ 个目录**中：

| 目录 | 文件数 | 用途 |
|------|--------|------|
| 根目录 | 4 | README、CLAUDE、TODO、CHANGELOG |
| `notes/` | 8 | 开发手记、功能手册、排障记录 |
| `.trae/code_reviews/v0.1.5/` | 5 | 代码审查发现 |
| `.trae/documents/test-suite/` | 6 | 测试体系分析与建议 |
| `.trae/documents/archived/` | 5+ | 已归档的功能计划与兼容性分析 |
| `.trae/specs/` (7个子目录) | 21 | 功能规格说明 |
| 其他 (`data/`, `exp_configs/`, `.trae/rules/`) | 3 | 目录说明、配置指南、规则 |

### 1.2 核心问题

#### 问题 A：结构混乱，分布零散

- 文档分散在 7+ 个目录中，无统一入口
- 文件命名风格不统一（中英文混用，如 `chat-幽灵文件夹排查指南.md`）
- 同类文档分布在不同位置（Meal 手册在 `notes/`，实验指南在 `exp_configs/`）
- 无全局索引或导航文件

#### 问题 B：内容重叠严重

| 重叠组 | 涉及文件 | 重叠内容 |
|--------|----------|----------|
| Meal 系统文档 | `notes/meal-user-manual.md`、`notes/meal-full-pipeline-manual.md`、`notes/meal-feature-issues.md` | Meal 概念、CLI 命令、使用流程 |
| 幽灵文件夹 | `notes/ghost-folder-issue-fix.md`、`notes/chat-幽灵文件夹排查指南.md` | 同一问题的排查与修复 |
| 实验系统 | `notes/experiment_system.md`、`exp_configs/README.md` | 实验配置、运行方式、报告解读 |
| 测试体系 | `.trae/documents/test-suite/` 下 6 个文件 | 测试分析、建议、设计方向 |
| 项目规范 | `CLAUDE.md`、`.trae/rules/commit-rule.md` | commit message 规则重复 |

#### 问题 C：文档与代码不一致

经核查，V1 中声称的"21 处不一致"存在多处误判：

| 类别 | 严重程度 | 数量 | 典型问题 | V1 是否有误判 |
|------|---------|------|----------|--------------|
| config.yaml 与文档参数不一致 | 高 | 2 | README 展示不存在的 `evaluation` 配置节 | 无（实际 config.yaml 中确实有 evaluation 节，但在 exp_configs 中使用，根 config 中也有） |
| CLI 命令文档与实际接口不一致 | **已修正** | ~~4~~ 0 | ~~引用不存在的 `interactive.py`~~ | **有误判**：`interactive.py` 实际存在且功能正常；`--sample-count` 含义描述在 README 中标注了"有bug"，并非错误 |
| Meal 系统文档与实现不一致 | 中 | 4 | 测试集文件名模式错误；NDCG 取值范围错误 | 待核查 |
| 实验系统文档与实现不一致 | 高 | 4 | `multi-hop` kebab-case 转换未实现；LLM 报告配置键名不一致 | 待核查 |
| 文档/代码功能缺失或遗漏 | 中 | 7 | token 追踪功能未文档化；README 项目结构严重过时 | 无（README 项目结构确实缺少 meal、sampler、test_generator、token_tracker、experiment 等模块） |

#### 问题 D：无生命周期管理

- 无法区分"当前有效"和"历史参考"文档
- spec 文件与活跃文档混放
- 已完成的 spec 仍保留在原位，无归档标记
- 代码审查发现部分已修复，但文档未更新状态

#### 问题 E：人类与 AI 可读性不足

- 无快速参考卡片（AI 需要精炼的上下文）
- 长文档缺乏清晰的章节导航
- 教程、参考、排障等不同目的的文档混在一起
- CLAUDE.md 承担了过多角色（规范 + 路线图 + 系统说明）

---

## 二、新文档管理实践设计

### 2.1 设计原则

1. **单一职责**：每个文档只解决一类问题，面向一类读者
2. **单一信源**：同一信息只在一处维护，其他位置通过引用链接
3. **分层组织**：从概览到细节，从通用到专业，逐层深入
4. **生命周期标注**：每个文档都有明确的状态标记（简化版）
5. **AI 友好**：关键文档结构化、精炼，便于 AI 快速理解上下文
6. **人类友好**：入口清晰、导航便捷、检索高效

### 2.2 新目录结构

```
docs/
├── README.md                    # 文档导航索引（唯一入口）
├── getting-started.md           # 快速上手指南
├── architecture.md              # 系统架构与模块说明
├── cli-reference.md             # CLI 命令速查手册
├── config-reference.md          # 配置文件参考手册
│
├── guides/                      # 使用指南（面向用户）
│   ├── meal-system.md           # Meal 数据管理系统
│   ├── experiment-system.md     # 实验评测系统
│   └── token-tracking.md        # Token 追踪与成本估算
│
├── dev-notes/                   # 开发手记（面向开发者）
│   ├── changelog.md             # 变更日志（从根目录迁入，见下方说明）
│   └── troubleshooting/         # 排障记录
│       └── ghost-folder-mkdir.md
│
└── archive/                     # 历史归档（只读，不再维护）
    ├── rag-pipeline-research.md
    ├── sampling-feature-plan.md
    ├── token-tracking-plan.md
    ├── flagembedding-compatibility.md
    ├── meal-feature-plan.md
    └── meal-identity-refactoring.md
```

**V2 重要调整（与 V1 对比）**：

| 调整项 | V1 设计 | V2 修正 | 原因 |
|--------|---------|---------|------|
| `reviews/` 目录 | 单独创建 `docs/reviews/` | **移除** | 代码审查记录属于工具产物，由 Trae 工具管理，不应迁入 docs。它们会随版本迭代失去参考价值，归入 `archive/` 即可 |
| `specs/` 目录 | 单独创建 `docs/specs/` 管理功能规格 | **移除** | `.trae/specs/` 是 Trae IDE 的 spec 工作流文件，位置由工具决定。在 docs 中维护副本会造成双信源，违反"单一信源"原则。已实现的 spec 应直接归入 `archive/` |
| `active/` vs `archived/` 分类 | specs 下分 `active/` 和 `archived/` 两个子目录 | **移除** | 当前所有 spec 均已实现，不存在 active 状态。即使未来有，也应直接在文件名或头部标注，无需额外目录层级 |
| CHANGELOG 位置 | 迁移至 `docs/dev-notes/changelog.md` | **保留在根目录**，同时在 `docs/dev-notes/changelog.md` 放置 | 行业最佳实践（Keep a Changelog、GitHub 项目惯例）均将 CHANGELOG.md 放在项目根目录，便于快速访问 |
| 元数据标签体系 | 每个文档头部必须包含完整的 frontmatter（status/last-reviewed/scope） | **简化为仅 status 标签** | 完整的 frontmatter 对个人项目是过度设计。`last-reviewed` 可通过 git log 查询，`scope` 可通过目录位置推断 |

### 2.3 根目录文件调整

| 文件 | 调整 |
|------|------|
| `README.md` | 精简为项目简介 + 指向 `docs/` 的链接，不再承载详细使用说明 |
| `CLAUDE.md` | 仅保留 AI 代理行为规范和项目约束，移除系统说明和路线图 |
| `TODO.md` | 保留，但精简格式，与 `docs/dev-notes/` 中的详细记录互补 |
| `CHANGELOG.md` | **保留在根目录**，同时在 `docs/dev-notes/changelog.md` 放置（可通过符号链接或文件包含实现同步） |

### 2.4 各文档职责与内容来源

#### `docs/README.md` — 文档导航索引

**职责**：唯一的文档入口，提供全局导航
**内容**：
- 文档目录树（带链接和一句话描述）
- 按角色的阅读路径（新用户 / 开发者 / AI 代理）

#### `docs/getting-started.md` — 快速上手

**职责**：5 分钟内让新用户跑通系统
**来源**：当前 `README.md` 的"三步上手"部分（修正所有错误）
**关键修正**：
- 保留 `interactive.py` 引用（**该文件实际存在且功能正常**）
- 标注 `eval/run_eval.py --sample-count` 当前存在 bug（与 README 一致）
- 更新项目结构图（补充 meal、sampler、test_generator、token_tracker、experiment 模块）
- 确认 config.yaml 配置段与实际一致

#### `docs/architecture.md` — 系统架构

**职责**：描述系统整体架构、模块关系、数据流
**来源**：当前 `README.md` 的架构部分 + `CLAUDE.md` 的链路描述
**关键修正**：
- 反映当前实际模块（含 meal、sampler、test_generator、token_tracker、experiment）
- 更新目录结构

#### `docs/cli-reference.md` — CLI 速查手册

**职责**：所有 CLI 命令的完整参考，按功能分组
**来源**：当前 `main.py` 的 argparse 定义 + `interactive.py` 的参数定义
**关键修正**：
- 确保与 `main.py` 和 `interactive.py` 的实际参数完全一致
- 包含 `--llm-preset` 等遗漏参数
- 明确区分 `main.py` 和 `interactive.py` 的命令集

#### `docs/config-reference.md` — 配置参考手册

**职责**：config.yaml 所有配置节的完整说明
**来源**：当前 `config.yaml` 的实际结构
**关键修正**：
- 确认 `evaluation` 节在根 config.yaml 中是否存在，如存在则保留说明
- 新增 `experiments`、`meals`、`artifacts`、`test_generation`、`token_cost`、`logging` 节的说明

#### `docs/guides/meal-system.md` — Meal 系统指南

**职责**：Meal 系统的完整使用指南
**来源**：合并 `notes/meal-user-manual.md` + `notes/meal-full-pipeline-manual.md` + `notes/meal-feature-issues.md`
**关键修正**：
- 修正测试集文件名模式（`auto_{strategy}_n{num}.json`）
- 修正 NDCG 取值范围（0.0-1.0）
- 补充 `MIXED` 状态说明
- 修正 artifacts 目录结构描述
- 修正 `pixi run python python` 重复命令

#### `docs/guides/experiment-system.md` — 实验系统指南

**职责**：实验评测系统的完整使用指南
**来源**：合并 `notes/experiment_system.md` + `exp_configs/README.md`
**关键修正**：
- 修正 `multi-hop` 策略命名（实际使用 `multi_hop`，无自动转换）
- 修正 LLM 报告配置键名（`llm_report: true/false`，非 `report_mode: "llm"`）
- 补充 `test_sets/` 子目录到实验目录结构

#### `docs/guides/token-tracking.md` — Token 追踪指南

**职责**：Token 追踪与成本估算功能说明
**来源**：当前代码中存在但完全未文档化的功能
**内容**：
- TokenTracker 的使用方式
- config.yaml 中 token_cost 配置说明
- 实验报告中的成本输出解读

#### `docs/dev-notes/changelog.md` — 变更日志

**职责**：项目版本变更记录（与根目录 `CHANGELOG.md` 同步）
**来源**：当前根目录 `CHANGELOG.md`

#### `docs/dev-notes/troubleshooting/ghost-folder-mkdir.md` — 排障记录

**职责**：记录已解决的典型问题及排查方法
**来源**：合并 `notes/ghost-folder-issue-fix.md` + `notes/chat-幽灵文件夹排查指南.md` + `notes/mkdir-hook-lesson.md`

#### `docs/archive/` — 历史归档

**职责**：只读历史文档，不再维护
**来源**：当前 `.trae/documents/archived/` + `.trae/documents/test-suite/` + `.trae/code_reviews/` + `.trae/specs/`（已实现的部分）
**调整**：文件名统一为英文

### 2.5 文档生命周期管理规范

#### 简化状态标签体系

每个文档头部包含简化元数据块：

```markdown
<!-- status: active | archived | deprecated -->
```

- `active`：当前有效，需随代码更新（默认状态，可省略标签）
- `archived`：历史参考，不再主动维护
- `deprecated`：已被其他文档替代，保留仅供溯源

**移除的字段**：
- `last-reviewed`：可通过 git log 查询最后修改时间
- `scope`：可通过文档所在目录位置推断（`guides/` = user, `dev-notes/` = developer）

#### 更新触发条件

以下代码变更必须同步更新文档：

| 变更类型 | 需更新的文档 |
|----------|-------------|
| CLI 参数变更 | `cli-reference.md` |
| config.yaml 结构变更 | `config-reference.md` |
| 新增/删除模块 | `architecture.md` |
| 新增功能 | 对应 `guides/*.md` |
| Bug 修复 | `dev-notes/troubleshooting/` 中的排障记录 |

#### 审查周期

- 每次发版前：检查所有 `active` 文档与代码的一致性
- 每月：审查 `active` 文档与代码的一致性（通过运行 `git log --since="1 month ago" --name-only` 识别可能过时的文档）

### 2.6 AI 可读性优化

#### CLAUDE.md 精简策略

当前 CLAUDE.md 承担了过多角色，重构后仅保留：

1. **项目约束**：编码规范、测试规范、提交规范
2. **AI 行为指引**：环境变量规则、pixi 命令规则
3. **文档索引**：指向 `docs/README.md` 的链接

移除的内容：
- 系统架构说明 → `docs/architecture.md`
- 自动化评测系统说明 → `docs/guides/experiment-system.md`
- 当前目标与路线图 → `TODO.md`
- 完成标准 → `docs/dev-notes/changelog.md`

#### 结构化文档模板

面向 AI 的关键文档（`architecture.md`、`cli-reference.md`、`config-reference.md`）采用结构化模板：

```markdown
# 标题

<!-- status: active -->

## 概要
<!-- 3-5 句话的精炼描述，AI 可快速理解 -->

## 详细说明
<!-- 完整内容 -->

## 与其他模块的关系
<!-- 依赖和被依赖关系 -->

## 常见变更点
<!-- 最常需要更新的部分，便于 AI 定位 -->
```

### 2.7 保留不动的文件

以下文件因特殊用途保持原位，不迁入 `docs/`：

| 文件 | 原因 |
|------|------|
| `CHANGELOG.md` | 行业惯例放在根目录，docs 中放置同步副本 |
| `data/README.md` | 数据目录的本地说明，与数据文件紧密关联 |
| `exp_configs/README.md` | 配置目录的本地说明，与配置文件紧密关联 |
| `.trae/rules/commit-rule.md` | Trae IDE 的自动执行规则，位置由工具决定 |
| `.trae/specs/*/spec.md` 等 | Trae 的 spec 工作流文件，位置由工具决定（已实现的在 archive 中归档） |
| `.trae/code_reviews/` | Trae 的代码审查产物，位置由工具决定（已实现的在 archive 中归档） |

---

## 三、实施步骤

### Phase 1：创建新目录结构与核心文档（高优先级）

1. 创建 `docs/` 目录及子目录
2. 创建 `docs/README.md`（文档导航索引）
3. 创建 `docs/getting-started.md`（从 README.md 提取并修正）
4. 创建 `docs/architecture.md`（从 README.md + CLAUDE.md 提取并修正）
5. 创建 `docs/cli-reference.md`（从 main.py + interactive.py argparse 提取）
6. 创建 `docs/config-reference.md`（从 config.yaml 提取）

### Phase 2：合并重叠文档（高优先级）

7. 合并 Meal 系统三文档 → `docs/guides/meal-system.md`
8. 合并实验系统两文档 → `docs/guides/experiment-system.md`
9. 创建 `docs/guides/token-tracking.md`（全新，当前无文档）
10. 合并幽灵文件夹三文档 → `docs/dev-notes/troubleshooting/ghost-folder-mkdir.md`

### Phase 3：迁移与归档（中优先级）

11. 在 `docs/dev-notes/changelog.md` 创建 CHANGELOG 的副本（根目录保留原版）
12. 归档代码审查 → `docs/archive/code-reviews-v0.1.5/`（重命名+状态标注）
13. 归档测试体系文档 → `docs/archive/test-suite-analysis/`
14. 归档已实现的 spec → `docs/archive/specs/`（标注"已实现"）
15. 归档历史文档 → `docs/archive/`（`.trae/documents/archived/` 下的文件）

### Phase 4：精简根目录与 CLAUDE.md（中优先级）

16. 精简 `README.md` 为项目简介 + docs 链接
17. 精简 `CLAUDE.md`，移除系统说明和路线图
18. 更新 `TODO.md` 格式

### Phase 5：清理旧文件（低优先级）

19. 删除已合并的旧文档（`notes/` 下的重叠文件）
20. 清理 `.trae/documents/test-suite/`（内容已归档）
21. 清理 `.trae/documents/archived/`（内容已迁入 `docs/archive/`）

### Phase 6：验证与收尾

22. 逐一验证所有新文档与代码的一致性
23. 更新 CLAUDE.md 中的文档索引
24. 提交并记录本次重构

---

## 四、新旧文件映射表

| 旧文件 | 新位置 | 处理方式 |
|--------|--------|----------|
| `README.md`（详细内容） | `docs/getting-started.md` + `docs/architecture.md` | 拆分+修正 |
| `CLAUDE.md`（系统说明部分） | `docs/architecture.md` | 提取 |
| `CLAUDE.md`（评测系统部分） | `docs/guides/experiment-system.md` | 提取 |
| `CHANGELOG.md` | **保留根目录** + `docs/dev-notes/changelog.md` | 保留+副本 |
| `notes/meal-user-manual.md` | `docs/guides/meal-system.md` | 合并后删除 |
| `notes/meal-full-pipeline-manual.md` | `docs/guides/meal-system.md` | 合并后删除 |
| `notes/meal-feature-issues.md` | `docs/guides/meal-system.md` | 合并后删除 |
| `notes/experiment_system.md` | `docs/guides/experiment-system.md` | 合并后删除 |
| `exp_configs/README.md` | 保留原位 + `docs/guides/experiment-system.md` 引用 | 保留+引用 |
| `notes/ghost-folder-issue-fix.md` | `docs/dev-notes/troubleshooting/ghost-folder-mkdir.md` | 合并后删除 |
| `notes/chat-幽灵文件夹排查指南.md` | `docs/dev-notes/troubleshooting/ghost-folder-mkdir.md` | 合并后删除 |
| `notes/mkdir-hook-lesson.md` | `docs/dev-notes/troubleshooting/ghost-folder-mkdir.md` | 合并后删除 |
| `notes/development_complete.md` | `docs/archive/` | 归档 |
| `.trae/code_reviews/v0.1.5/*` | `docs/archive/code-reviews-v0.1.5/` | 归档+重命名 |
| `.trae/documents/test-suite/*` | `docs/archive/test-suite-analysis/` | 归档 |
| `.trae/documents/archived/*` | `docs/archive/` | 迁移 |
| `.trae/specs/*/spec.md` | `docs/archive/specs/` | 归档（仅副本，原始保留在 `.trae/specs/`） |
| `data/README.md` | 保留原位 | 不动 |
| `.trae/rules/commit-rule.md` | 保留原位 | 不动 |

---

## 五、V1 错误与修正清单

### 事实错误

| # | V1 描述 | 实际情况 | 影响 |
|---|---------|----------|------|
| 1 | `interactive.py` 不存在，应在 getting-started 中移除引用 | `interactive.py` 实际存在，功能正常（[interactive.py](file:///b:/project/ash-easy-rag/interactive.py)） | 删除错误的"关键修正"项 |
| 2 | `--sample-count` 含义描述错误 | README 中已标注该功能"有bug"，并非文档错误 | 移除错误指控，保留 bug 标注 |
| 3 | 声称"21 处文档与代码不一致" | 实际不一致数量待核查，部分指控不成立 | 降低严重程度，标注"待核查" |
| 4 | config.yaml 中 `evaluation` 配置节不存在 | 根 config.yaml 中确实包含 `evaluation` 节 | 修正描述 |
| 5 | 迁移代码审查到 `docs/reviews/` | 代码审查是 Trae 工具产物，不应由 docs 管理 | 改为归档到 `archive/` |

### 过度设计

| # | V1 设计 | 问题 | V2 修正 |
|---|---------|------|---------|
| 1 | 完整的 frontmatter 元数据块（status/last-reviewed/scope） | 个人项目维护成本过高，`last-reviewed` 可通过 git 查询，`scope` 可通过目录推断 | 简化为仅 `status` 注释标签 |
| 2 | `docs/specs/` 目录，分 `active/` 和 `archived/` | 所有 spec 均已实现，无 active 状态；且与 `.trae/specs/` 形成双信源 | 移除，已实现的 spec 直接归档 |
| 3 | `docs/reviews/` 目录管理代码审查 | 代码审查是 Trae 工具产物，不应由 docs 管理 | 改为归档到 `archive/` |
| 4 | 严格的"每月审查 active 文档"流程 | 个人项目无此必要 | 简化为"发版前检查 + 每月通过 git log 快速审查" |

### 不符合最佳实践

| # | V1 设计 | 最佳实践 | V2 修正 |
|---|---------|----------|---------|
| 1 | CHANGELOG.md 迁移至 `docs/dev-notes/` | Keep a Changelog 规范、GitHub 项目惯例均要求 CHANGELOG 在根目录 | 保留根目录，docs 中放副本 |
| 2 | 删除 `.trae/specs/` 中的原始文件 | `.trae/specs/` 是 Trae IDE 的工作流文件，删除可能影响工具功能 | 仅归档副本，原始文件保留 |

---

## 六、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 迁移过程中遗漏内容 | 每个合并操作后对照原文校验 |
| 旧链接失效 | 旧文件删除前在原位留重定向说明 |
| AI 代理找不到新文档位置 | CLAUDE.md 中明确指向 `docs/README.md` |
| spec 迁移影响 Trae 工具 | `.trae/specs/` 保留原位不动，`docs/archive/specs/` 仅为副本 |
| 文档更新跟不上代码变更 | 在 CLAUDE.md 中加入"代码变更必须同步文档"的规则 |
| CHANGELOG 根目录与 docs 副本不同步 | 使用符号链接（Windows 下用 `mklink`）或文档构建脚本自动同步 |
