# 打扫卫生与积压 Issue 检查计划

## 背景

当前处于 v0.1.8 发版后的打扫卫生阶段。需要完成两件事：

1. 执行"打扫卫生"流程（TODO 归档、收件箱检查、.trae 目录清理）
2. 审查 backlog 中所有积压 issue，标记已完成的，识别方便做的

***

## 第一部分：打扫卫生

### Step 1: TODO 归档

TODO.md 中有 **2 条未归档 issue**（无 📋 标记）：

1. **.trae 目录归档机制**（第86行）：关于 `.trae/documents/` 和 `.trae/specs/` 下的 plan/spec 文档定期归档
2. **docs 路径整洁度维护**（第87行）：打扫卫生时应考量 docs 目录的组织度

→ 调用 `todo-archiver` skill，将这 2 条归档到 `docs/backlog.md`

### Step 2: 收件箱检查

`docs/inbox/` 目录不存在（无待处理文件），无需操作。

### Step 3: .trae 目录清理

当前 `.trae/documents/` 下有 **13 个文档**，`.trae/specs/` 下有 **4 个 spec 目录**。

需要逐一判断状态并归档：

**documents/ 目录：**

| 文件                                             | 推测状态                   | 处理方式              |
| ---------------------------------------------- | ---------------------- | ----------------- |
| `documents-refactor/` (3文件)                    | 已完成（v0.1.6 文档重构）       | 归档到 docs/archive/ |
| `eval-system-acceptance-fix.md`                | 已完成（v0.1.7 修复）         | 归档                |
| `exp_configs_analysis_and_improvement_plan.md` | 已完成（RF-003）            | 归档                |
| `experiment-metrics-bug-fix-plan.md`           | 已完成                    | 归档                |
| `high-priority-dev-directions.md`              | 已完成（v0.1.8 已实现）        | 归档                |
| `merge-conflict-resolution-plan.md`            | 已完成                    | 归档                |
| `rag-eval-metrics-optimization-plan.md`        | 已完成                    | 归档                |
| `ragas-integration-analysis.md`                | 部分完成（分析已做，实装待 v0.1.11） | 归档分析部分            |
| `ragas-integration-implementation-plan.md`     | 未开始（v0.1.11 计划）        | 保留或归档             |
| `ragas-integration-plan.md`                    | 同上                     | 保留或归档             |
| `todo-archiver-mechanism-plan.md`              | 已完成（FEAT-009）          | 归档                |
| `v0.1.8 Release Plan...md`                     | 已完成                    | 归档                |
| `v0.1.8-merge-and-release-plan.md`             | 已完成                    | 归档                |

**specs/ 目录：**

| 目录                                 | 推测状态        | 处理方式 |
| ---------------------------------- | ----------- | ---- |
| `fix-eval-try-round-2/`            | 已完成         | 归档   |
| `fix-evaluation-granularity/`      | 已完成         | 归档   |
| `new-evaluation-system/`           | 已完成（v0.1.7） | 归档   |
| `test-set-independent-management/` | 已完成（v0.1.8） | 归档   |

> ⚠️ .trae 目录可能有 IDE 保护，需测试 AI 是否能修改。如遇权限问题，记录在案并跳过。

***

## 第二部分：积压 Issue 审查

### 已验证：无已完成的 issue

对 8 个可疑 issue 进行了代码级验证，**全部未完成**，与 backlog 标记一致。

### 适合立即做的 issue（小规模 + 低依赖）

按优先级排序：

| 优先级 | ID           | 描述                     | 规模 | 理由                                                                                                                   |
| --- | ------------ | ---------------------- | -- | -------------------------------------------------------------------------------------------------------------------- |
| ⭐1  | **INV-008**  | LLM 报告提示词更新（旧→新问题类型分类） | 极小 | 仅改提示词文本，factual/boundary/multi-hop → 新六类                                                                             |
| ⭐2  | **RF-010**   | lint/ruff 配置           | 小  | 添加 ruff 到 pixi 依赖 + pyproject.toml 配置（但本项目实际使用pixi.toml，需根据pixi官方文档[Home](https://pixi.prefix.dev/latest/)验证配置语法通用性） |
| ⭐3  | **RF-005**   | Anthropic 客户端创建统一抽象    | 小  | 4处重复代码提取为公共函数                                                                                                        |
| ⭐4  | **FEAT-018** | pre-commit 钩子          | 小  | 添加 .pre-commit-config.yaml                                                                                           |
| ⭐5  | **FEAT-016** | DATA\_DIR 配置项支持        | 小  | config.yaml 加一个字段 + 代码引用                                                                                             |
| 6   | **INV-006**  | golden test 更新到新策略     | 小  | 更新 golden\_qa.json 的 category 字段                                                                                     |
| 7   | **FEAT-011** | 补做 LLM 报告功能            | 小  | 新增 CLI 子命令                                                                                                           |

### 不建议现在做的 issue

| ID                  | 原因                    |
| ------------------- | --------------------- |
| FEAT-014 (透明版报告)    | 大规模，属于 v0.1.9 核心任务    |
| FEAT-012 (断点续传)     | 大规模，需设计               |
| INV-009 (问题集扩大)     | 依赖 v0.1.9 发版          |
| INV-002 (策略可扩展性)    | 依赖黄金测试集               |
| OPT-001/002/003/004 | 需性能基准测试或依赖其他工作        |
| RF-001 (172处print)  | 中规模，替换 loguru 会改变输出格式 |
| RF-004 (硬编码配置)      | 中规模，需仔细梳理             |
| RF-008 (backlog详情)  | 中规模，需设计               |
| RF-009 (渐进式披露)      | 中规模，需设计               |

***

## 执行计划

1. **调用 todo-archiver skill** 归档 2 条未归档 issue
2. **清理 .trae 目录**：将已完成的文档归档到 `docs/archive/specs/` 等位置
3. **实施高优先级小 issue**（按用户确认的范围）：

   * INV-008：更新 LLM 报告提示词中的问题类型分类

   * RF-010：添加 ruff 配置

   * RF-005：统一 Anthropic 客户端创建

   * FEAT-018：添加 pre-commit 钩子

   * FEAT-016：添加 DATA\_DIR 配置项
4. 每完成一项立即提交（原子提交）

