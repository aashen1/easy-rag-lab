# AI 时代的 Git 规范

<!-- status: archived -->

> 来源：网页端聊天记录
> 日期：2026-04-18
> 关联：本文档阐述的理念已纳入项目文档管理实践

---

## 核心观点

### 文档是意图源码，代码是编译产物

在 AI 辅助开发中，Spec/Roadmap/决策文档是"给 AI 编译的意图"。文档的重要性应高于传统实践。

**类比**：
- 传统开发：程序员 = 翻译官（需求 → 代码）
- AI 时代：程序员 = 架构师+质检员（意图设计 → AI 编译 → 边界验证 → 迭代约束）

### Git 角色的转变

Git 应从"代码历史存档"升级为"意图演化轨迹+生成过程审计账本"。

---

## 推荐目录结构

```
repo/
├── specs/                 # AI 意图源码区（核心资产）
│   ├── active/            # 当前正在开发/迭代的版本
│   └── completed/         # 已发版归档
├── src/                   # AI 生成代码
├── tests/                 # 验收用例
└── .ai-context.json       # 项目级 AI 上下文索引
```

---

## Commit Message 规范扩展

在传统 Conventional Commits 基础上增加 AI 维度：

```
feat(ai): 重构支付模块提示词，增加幂等性约束
- 更新 specs/payment-spec.md
- 同步生成 src/payment/ (auto-generated)
- Model: claude-3.5-sonnet-20241022
- Validation: 通过 tests/payment/integration.spec.ts
```

---

## .gitignore 策略调整

- ✅ **纳入版本控制**：`.md`, `.yaml`, `.json` 等意图/约束/测试文件
- ❌ **继续忽略**：临时对话日志、未结构化的 AI 输出缓存、敏感 API Key
- 🔄 **标记生成物**：在文件头插入 `AUTO-GENERATED FROM specs/xxx.md`

---

## 本项目实践

本项目的文档管理实践已采纳上述理念：

- `docs/reviews/vX.X.X/` — 版本验收报告（意图 → 交付对照）
- `docs/version-history.md` — 版本演进年轮
- `docs/backlog.md` — 待做事项总表

---

*原文档：`notes/chat-AI时代的新Git规范.md`（已删除）*
