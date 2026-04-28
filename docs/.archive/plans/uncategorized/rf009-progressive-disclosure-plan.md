# RF-009: commit-rule 与 CLAUDE.md 渐进式披露

## 问题诊断

### 当前状态

| 文件 | 行数 | 加载方式 | 角色 |
|------|------|----------|------|
| `.trae/rules/commit-rule.md` | 100 | alwaysApply: true（每次会话自动加载） | Trae 项目规则 |
| `CLAUDE.md` → 版本控制段 | ~28 行 | 每次会话自动加载 | 项目全局指令 |
| `.trae/skills/auto-commit-enforcer/SKILL.md` | 145 | Skill 按需触发 | Trae 技能 |

**核心问题：三处内容高度重复，合计约 356 行，其中核心信息仅约 30-40 行。**

重复内容清单：
1. "只提交自己做的改动"（git status/diff 检查、禁止 git add -A/.）→ 三处全有
2. "原子提交触发条件"（todo完成/函数实现/测试通过/bug修复/配置变更/文档更新）→ 三处全有
3. "各模式提交要求"（Agent/Plan/Spec 每步提交）→ 三处全有
4. "Conventional Commits 格式"（英文ASCII、祈使语气）→ 三处全有
5. "自我检查机制"（开始新工作前检查未提交修改）→ 三处全有

### 上下文成本估算

- 三处合计约 356 行 × ~5 token/行 ≈ **1,780 token**
- 经渐进式披露优化后预估：MINI 约 40 行 ≈ **200 token**
- **节省约 1,580 token/会话**（约 89%）

### 业界最佳实践总结

来源：Anthropic 官方、Claude Code 创造者 Boris Cherny、Claude Code Guide、wordman.dev 等

| 原则 | 要点 |
|------|------|
| 少即是多 | CLAUDE.md < 300 行；前沿 LLM 可靠遵循约 150-200 条指令 |
| 渐进式披露 | MINI 文件（30-80 行）自动加载 + 完整文件按需读取 |
| Rules < 4k 字符 | 细节放 Skills，Rules 只留不变量 + 指针 |
| 指针优于副本 | 用 file:line 引用指向权威上下文，避免副本过时 |
| 触发式加载 | "当遇到 X 情况时，读取 Y 文件" 优于静态塞入 |
| 不让 LLM 做 Linter | 格式/风格由确定性工具（ruff/pre-commit）保证 |

---

## 实施方案

### 架构设计：三层渐进式披露

```
Layer 1: 自动加载（每次会话）
  ├── CLAUDE.md          → 项目简介 + 核心规范摘要 + 指针
  └── .trae/rules/commit-rule.md → 原子提交核心不变量（<4k字符）

Layer 2: 按需加载（Skill 触发 / 条件读取）
  └── .trae/skills/auto-commit-enforcer/SKILL.md → 完整提交规范 + 示例

Layer 3: 深度参考（AI 自行决定读取）
  └── docs/guides/commit-conventions.md → 详细示例 + 反模式 + 常见问题
```

### 具体改动

#### 1. 精简 `.trae/rules/commit-rule.md`（100行 → ~25行）

**目标**：只保留核心不变量，< 4k 字符，符合 Trae Rules 最佳实践。

精简后内容要点：
- frontmatter 保持 `alwaysApply: true` + `scene: git_message`
- 核心不变量（3条）：① 只提交自己的改动 ② 完成逻辑工作单元后立即提交 ③ Conventional Commits 英文格式
- 触发条件列表（精简为 1 行概括）
- 指针：`详细规范与示例：invoke skill auto-commit-enforcer`

删除内容（移至 Skill）：
- Safe staging 的 bash 示例代码块
- 各模式分别列出的提交要求（Agent/Plan/Spec 重复三遍）
- Self-Correction Protocol 的 5 步流程
- Enforcement Priority 段落

#### 2. 精简 `CLAUDE.md` 版本控制段（28行 → ~8行）

**目标**：只保留项目级约束，删除与 commit-rule 重复的内容。

精简后内容要点：
- 一句话核心原则："完成逻辑工作单元后立即提交，只 stage 自己修改的文件"
- 禁止项：`git add -A` / `git add .`
- Conventional Commits 英文格式（一句话）
- 指针：`完整规范见 .trae/rules/commit-rule.md`

删除内容：
- 与 commit-rule 完全重复的详细步骤
- 各模式的分别说明
- 自我检查机制（已在 commit-rule 中）

#### 3. 保留 `.trae/skills/auto-commit-enforcer/SKILL.md` 作为权威详细规范

**目标**：作为 Layer 2 的完整参考，由 Skill 触发加载。

改动：
- 在 SKILL.md 顶部添加说明："本文件是 commit-rule 的完整版，由 auto-commit-enforcer skill 触发加载"
- 修正 Examples 段落中的 `git add -A`（与核心规则矛盾！应改为精确 staging）
- 其余内容保持不变（这是权威详细规范的存放位置）

#### 4. 新建 `docs/guides/commit-conventions.md`（Layer 3 深度参考）

**目标**：提供详细示例、反模式、常见问题，供 AI 在复杂场景下自行读取。

内容要点：
- 完整的 Conventional Commits 类型列表与示例
- 原子提交的判断标准（什么算"逻辑工作单元"）
- 常见反模式与纠正
- 复杂场景处理（如：同时修了 bug 和重构了代码怎么提交？）
- 与 pre-commit 钩子的配合

---

## 文件改动清单

| 文件 | 操作 | 预估行数变化 |
|------|------|-------------|
| `.trae/rules/commit-rule.md` | 精简 | 100 → ~25 行 |
| `CLAUDE.md` | 精简版本控制段 | 111 → ~90 行 |
| `.trae/skills/auto-commit-enforcer/SKILL.md` | 小修（修正示例 + 添加说明） | 145 → ~150 行 |
| `docs/guides/commit-conventions.md` | 新建 | ~80 行 |

---

## 实施步骤

1. **精简 commit-rule.md**：重写为 MINI 版本，保留核心不变量 + 指针
2. **精简 CLAUDE.md 版本控制段**：删除重复内容，添加指针
3. **修正 SKILL.md**：修正 Examples 中的 `git add -A`，添加顶部说明
4. **新建 docs/guides/commit-conventions.md**：编写深度参考文档
5. **验证**：检查三处内容无矛盾、指针正确、无遗漏关键规则
6. **提交**：每个步骤完成后立即原子提交

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 精简后 AI 不再遵循提交规范 | commit-rule 仍 alwaysApply，核心不变量完整保留；Skill 可按需触发补充 |
| CLAUDE.md 与 commit-rule 指针断裂 | 使用相对路径引用，提交前验证文件存在 |
| SKILL.md 示例与规则矛盾 | 修正 git add -A 示例为精确 staging |
| docs/guides/ 文件不被读取 | 在 CLAUDE.md 和 commit-rule 中添加带触发条件的指针 |
