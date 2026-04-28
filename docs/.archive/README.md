# 项目博物馆

这里存放着项目从 `git init` 以来的所有开发痕迹——计划、规范、验收、调研、故障排查。

## 如何浏览

1. **时间线导览**：[timeline.md](timeline.md) — 按版本浏览项目演进，推荐入口
2. **按版本浏览**：每个 `v0.1.X-xxx-era/` 目录对应一个版本的开发痕迹
3. **按主题浏览**：每个版本目录下按功能主题分组（如 ragas-integration/、parsing-pipeline/）

## 目录结构

```
.archive/
├── timeline.md              # 时间线导览（推荐入口）
├── archive-log.md           # 归档操作日志
│
├── v0.1.0-v0.1.5-mvp-era/   # MVP 时代
├── v0.1.6-hygiene-era/      # 项目卫生时代
├── v0.1.7-evaluation-era/   # 评测增强时代
├── v0.1.8-testset-era/      # TestSet 管理时代
├── v0.1.9-dual-eval-era/    # 评测双引擎时代
├── v0.1.10-parsing-era/     # 解析新纪元时代
├── v0.1.11-unification-era/ # 链路统一时代
├── v0.1.12-governance-era/  # 项目治理时代
├── v0.1.13-visualization-era/ # RAG 可视化时代
└── cross-version/           # 跨版本主题
```

## 文档类型说明

每个版本目录下的主题子目录可能包含：

- **计划文档**（原 TRAE /plan 模式产出）— 规划任务执行方向
- **规范文档**（原 TRAE /spec 模式产出，含 spec.md + tasks.md + checklist.md）— 完整规范、任务、验收
- **验收报告**（code-review、outcome、next-direction）— 版本交付对照
- **调研报告、会话记录、故障排查** — 开发过程中的辅助文档

同一功能的计划文档和规范文档放在一起，不再区分。

## 版本叙事

```
量得准 → 解得开 → 合得拢 → 管得住 → 看得见
  v0.1.9   v0.1.10   v0.1.11   v0.1.12   v0.1.13
```
