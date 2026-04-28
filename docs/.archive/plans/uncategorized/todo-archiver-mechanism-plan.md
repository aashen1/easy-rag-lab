# TODO 归档机制实施计划

## 背景

项目已有"收件箱"机制（inbox），用于处理 AI 对话记录的入库。现在需要为 `TODO.md` 建立类似的归档机制，实现人类（TODO）与 AI（backlog）之间的异步 issue 同步。

## 核心设计

### 双文档职责划分

| 文档                | 管理者 | 性质           | 内容                                                               |
| ----------------- | --- | ------------ | ---------------------------------------------------------------- |
| `TODO.md`         | 人类  | 随笔式待办笔记      | 开发者随时记录的改进思路、待办事项                                                |
| `docs/backlog.md` | AI  | 结构化 issue 追踪 | 按 Bug/Feature/Refactor/Optimization/Investigation 分类的正式 issue 列表 |

### 归档流程（单向：TODO → backlog）

```
人类在 TODO.md 写下新 issue（- [ ] 格式）
    ↓
AI 检测到未归档的 issue
    ↓
分类 + 分配 ID → 写入 backlog.md
    ↓
在 TODO.md 原条目后追加归档时间戳：📋 YYYY-MM-DD 归档为 [RF-007]
（不删除原内容，不打钩，不移动位置）
    ↓
下次检查时，发现已归档且 backlog 中已完成的 issue
    ↓
打钩 + 追加完成时间戳：✅ YYYY-MM-DD 该issue已确认完成
    ↓
将条目移动到对应完成日期的标题下
```

### TODO.md 条目状态标记规范

| 状态  | 标记格式                                                             | 含义                         |
| --- | ---------------------------------------------------------------- | -------------------------- |
| 新建  | `- [ ] 描述内容`                                                     | 人类刚写，AI 尚未归档               |
| 已归档 | `- [ ] 描述内容 📋 2026-04-21 归档为 [RF-007]`                          | AI 已归入 backlog，原条目保留       |
| 已完成 | `- [x] 描述内容 📋 2026-04-21 归档为 [RF-007] ✅ 2026-04-22 该issue已确认完成` | backlog 中已标记完成，AI 同步回 TODO |

### 日期标题结构

每个日期标题下包含 summary 和 verbose 两个子节：

```markdown
## 2026-04-21

### summary

- [x] 硬编码配置提取到 config.yaml（RF-004）

### verbose

- [x] 硬编码配置值提取到 config.yaml 📋 2026-04-21 归档为 [RF-004] ✅ 2026-04-21 该issue已确认完成
```

* **verbose**：人类原始表述 + AI 追加的时间戳，保持原样

* **summary**：AI 根据 verbose 生成的简洁摘要，便于快速浏览

## 实施步骤

### Step 1: 创建 TODO 归档 Skill

**文件**: `.trae/skills/todo-archiver/SKILL.md`

创建一个 skill 来定义归档逻辑，原因：

* 归档逻辑较复杂（分类、ID分配、时间戳、完成检测、摘要生成），适合独立 skill

* 与 auto-commit-enforcer 类似，属于跨工作模式的通用能力

* 可被 CLAUDE.md 规则触发，也可手动调用

Skill 核心逻辑：

1. **读取 TODO.md**，解析所有 `- [ ]` 和 `- [x]` 条目
2. **识别未归档条目**（没有 `📋` 标记的 `- [ ]` 条目）
3. **对每个未归档条目**：
   a. 分析内容，判断类型（Bug/Feature/Refactor/Optimization/Investigation）
   b. 在 backlog.md 中分配下一个可用 ID
   c. 将 issue 写入 backlog.md 对应分类
   d. 更新 backlog.md 统计概览
   e. 在 TODO.md 原条目后追加 `📋 YYYY-MM-DD 归档为 [ID]`
4. **识别已归档但可能已完成的条目**（有 `📋` 标记的 `- [ ]` 条目）：
   a. 提取归档 ID
   b. 在 backlog.md 中查找该 ID 的状态
   c. 如果状态为 `✅ 已完成`：

   * 将 `- [ ]` 改为 `- [x]`

   * 追加 `✅ YYYY-MM-DD 该issue已确认完成`

   * 将条目从原位置移到对应完成日期的标题下
5. **为每个日期标题生成/更新 summary**：
   a. 读取该日期 verbose 下的条目
   b. 生成简洁摘要写入 summary
6. **更新 backlog.md 的"最后更新"日期和统计概览**

### Step 2: 更新 CLAUDE.md — 添加 TODO 归档检查规则

在 CLAUDE.md 的"文档维护规则"部分，紧跟"收件箱检查规则"之后，添加"TODO归档检查规则"：

```markdown
### TODO归档检查规则

- 每次对话开始时，检查 `TODO.md` 中是否有未归档的 issue（即 `- [ ]` 且无 `📋` 标记的条目）
- 如有未归档 issue，提示用户"发现 TODO.md 有 N 条未归档 issue，是否执行归档？"
- 用户说"打扫卫生""归档TODO"等指令时，也触发归档流程
- 归档流程：调用 todo-archiver skill，将 issue 单向归档到 `docs/backlog.md`
- 归档后在 TODO.md 原条目追加时间戳，不删除原内容，不打钩
- 如发现已归档 issue 在 backlog 中已完成，则打钩、追加完成时间戳、移动到对应日期标题下
- 为每个日期标题的 verbose 生成 summary 摘要
```

### Step 3: 更新 docs/methodology.md — 添加 TODO 归档机制描述

在 methodology.md 的"待做事项管理"章节中，补充 TODO ↔ backlog 的双向异步机制说明：

* TODO.md 是人类的随笔笔记，backlog.md 是 AI 的结构化 issue 追踪

* 归档是单向的（TODO → backlog），AI 不修改人类原始表述

* 完成同步是反向的（backlog 完成 → TODO 打钩移动）

* 两者通过归档时间戳和 ID 关联

### Step 4: 执行首次归档

对当前 TODO.md 中 "My Backlog" 部分的未归档条目执行首次归档：

（注意，其中可能已经含有已归档至backlog，或者已经完成的issue，这些按前述规则判断，增加归档时间戳、完成时间戳、移动位置）

当前未归档条目（约 22 条 `- [ ]` 项当中确认为未归档的部分）需要：

1. 逐条分类并分配 ID&#x20;
2. 写入 backlog.md
3. 在 TODO.md 中追加归档时间戳
4. 为已有日期标题补充 summary

### Step 5: 更新 docs/README.md

在文档索引中补充 TODO 归档机制的说明。

## 技术决策

### 为什么用 Skill 而不是 Rule？

| 方案                          | 优点           | 缺点                          |
| --------------------------- | ------------ | --------------------------- |
| **Rule** (`.trae/rules/`)   | 简单，自动加载      | 归档逻辑太复杂，rule 不适合承载大量步骤      |
| **Skill** (`.trae/skills/`) | 可承载复杂逻辑，结构清晰 | 需要被触发（通过 CLAUDE.md 规则或手动）   |
| **CLAUDE.md 内联**            | 始终可见         | 会让 CLAUDE.md 更长，违反"渐进式披露"原则 |

**选择 Skill**，原因：

1. 归档逻辑包含分类、ID分配、时间戳、完成检测、摘要生成等多个步骤，需要详细的操作指南
2. 与 auto-commit-enforcer 同级别，适合 skill 形式
3. 通过 CLAUDE.md 中的简短规则触发，保持 CLAUDE.md 简洁
4. 符合用户提到的"渐进式披露"方向（TODO.md 第 87 行提到要分离 rule/skill）

### 触发方式

* **自动触发**：CLAUDE.md 中的规则，每次对话开始时检查

* **手动触发**：用户说"打扫卫生""归档TODO""check TODO"等

* **Skill 调用**：AI 主动调用 todo-archiver skill

## 风险与注意事项

1. **ID 冲突**：归档时必须检查 backlog.md 中已有的最大 ID，避免冲突
2. **分类准确性**：AI 需要准确判断 issue 类型，不确定时可标注为 Investigation
3. **TODO.md 格式保护**：归档操作只能追加时间戳和修改 checkbox，不能修改人类原始文字
4. **backlog.md 一致性**：每次归档后必须更新统计概览和最后更新日期
5. **首次归档量大**：当前约 22 条未归档条目，首次归档需要仔细处理
