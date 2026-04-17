# 开源准备度评估

> **状态标注版** — 标注日期：2026-04-18。各条目前添加了状态标记：✅ 已修复、📋 已安排、❌ 已弃用、⏳ 待定。

评估日期：2026-04-18
评估版本：v0.1.5（当前开发版）

---

## 总体评估

**当前状态：不建议直接开源。** 存在 5 个阻塞性问题需要先修复。

| 维度 | 评分 | 说明 |
|------|------|------|
| 安全性 | ⭐⭐⭐⭐ | 无密钥泄露，1 处本地路径需清理 |
| 代码质量 | ⭐⭐ | 调试代码残留、大量 print 违规、docstring 缺失 |
| 功能完整性 | ⭐⭐⭐ | 核心链路可用，但评测指标有严重 bug |
| 文档完备性 | ⭐⭐⭐⭐ | README 详尽，但标注"有 bug"影响印象 |
| 配置与部署 | ⭐⭐⭐ | 仅支持 Windows+CUDA，镜像源配置需说明 |
| 法律合规 | ⭐⭐⭐⭐⭐ | MIT License，无合规风险 |

---

## 阻塞性问题（必须修复才能开源）— 3❌ 2✅

### ✅ 已修复 阻塞 #1：调试钩子代码残留

**文件**：main.py, interactive.py, eval/run_eval.py, eval/run_experiment.py（第 1-38 行）

**风险**：
- Monkey-patching `os.mkdir`/`os.makedirs` 是危险操作，可能影响依赖库行为
- 开源后用户运行代码会产生 `output_dir_debug.log` 调试文件
- 代码看起来不专业，严重影响项目可信度

**修复工作量**：低（直接删除 4 个文件的前 38 行）

---

### ❌ 已弃用 阻塞 #2：pixi.toml 硬编码本地路径

**文件**：pixi.toml 第 105 行

**风险**：暴露 Windows 用户名 `xxxxxxx` 和本地磁盘结构

**修复工作量**：低（注释掉或改为环境变量引用）

---

### ❌ 已弃用 阻塞 #3：.gitignore 缺少 `.trae/` 条目

**风险**：IDE 配置目录可能被意外提交，暴露内部开发规划

**修复工作量**：低（添加一行 `.trae/`）

---

### ❌ 已弃用 阻塞 #4：CLAUDE.md 处理

**风险**：包含内部开发规范、当前目标、Backlog 等信息，且引用了 `.trae/` 和 `plgd/` 的死链

**修复工作量**：低（加入 .gitignore 或脱敏）

---

### ❌ 已弃用 阻塞 #5：README 中"有 bug"标注

**文件**：README.md 第 117 行 `### 2️⃣ ~~运行评测~~（有bug）`

**风险**：开源项目首页标注"有 bug"严重影响第一印象和可信度

**修复工作量**：低（改写为中性描述或修复 bug）

---

## 强烈建议修复（开源后应尽快处理）

| 序号 | 问题 | 严重程度 | 工作量 | 状态 |
|------|------|----------|--------|------|
| 1 | 📋 已安排 检索指标始终返回 0 | 🔴 严重 | 中等 | core bug, suggest spec mode |
| 2 | ✅ 已修复 Generator 未使用 API system 参数 | 🟠 中等 | 简单 | |
| 3 | ✅ 已修复 Indexer 资源未释放 | 🟠 中等 | 中等 | |
| 4 | 📋 已安排 大量 print() 违规 | 🟠 中等 | 中等 | CLI output intentional, suggest spec mode for non-CLI prints |
| 5 | 📋 已安排 IO 操作缺少 try/except | 🟠 中等 | 中等 | suggest spec mode |

---

## 开源必备文件检查

| 文件 | 状态 | 说明 |
|------|------|------|
| LICENSE | ✅ 已有 | MIT License, Copyright (c) 2026 Ash |
| README.md | ✅ 已有 | 内容详尽，但需修复"有 bug"标注 |
| CHANGELOG.md | ✅ 已有 | 格式规范，但 Known Issues 较多 |
| .env.example | ✅ 已有 | 模板规范，无真实密钥 |
| .gitignore | ⚠️ 需补充 | 缺少 `.trae/`、`CLAUDE.md` 条目 |
| .gitattributes | ✅ 已有 | pixi.lock 标记合理 |
| CONTRIBUTING.md | ❌ 缺失 | 非必须，但建议添加 |
| CODE_OF_CONDUCT.md | ❌ 缺失 | 非必须，但建议添加 |

---

## 开源前清理清单

### 必做（阻塞开源）

- [x] ✅ 已修复 删除 4 个入口文件中的调试钩子代码（第 1-38 行）
- [ ] ❌ 已弃用 移除 pixi.toml 中的 `B:/useradmin/torch_cache` 硬编码路径
- [ ] ❌ 已弃用 在 .gitignore 中添加 `.trae/` 和 `CLAUDE.md`
- [ ] ❌ 已弃用 处理 CLAUDE.md（加入 .gitignore 或脱敏）
- [ ] ❌ 已弃用 修复 README.md 中的"有 bug"标注
- [x] ✅ 已修复 确认 `output_dir_debug.log` 未被 git 跟踪（debug hooks removed, file no longer generated）
- [ ] ❌ 已弃用 确认 `.trae/` 目录未被 git 跟踪

### 建议做（提升品质）

- [ ] 📋 已安排 修复检索指标始终返回 0 的 bug
- [x] ✅ 已修复 修复 chunk_comparison.yaml 中的无效策略名
- [ ] 📋 已安排 添加平台兼容性说明（仅 Windows + CUDA 12.6）
- [ ] 📋 已安排 添加 PyPI 镜像源配置说明
- [ ] 📋 已安排 添加 torch 版本配置指南
- [ ] ⏳ 待定 确认个人邮箱是否愿意公开
- [ ] 📋 已安排 重命名 `notes/chat-幽灵文件夹排查指南.md` 为纯 ASCII 文件名
- [ ] 📋 已安排 移除 TODO.md 中指向 `.trae/` 的死链

### 可选做（锦上添花）

- [ ] 📋 已安排 补全公共函数的 docstring
- [ ] 📋 已安排 将非 CLI 的 print() 改为 loguru
- [ ] 📋 已安排 为 IO 操作添加 try/except
- [ ] 📋 已安排 添加 CONTRIBUTING.md
- [ ] 📋 已安排 添加 CODE_OF_CONDUCT.md
- [ ] 📋 已安排 统一 API 端点配置到 config.yaml

---

## 开源后维护建议

1. **Issue 模板**：创建 GitHub Issue 模板，引导用户报告 bug 和功能请求
2. **PR 模板**：创建 Pull Request 模板，确保贡献质量
3. **CI/CD**：配置 GitHub Actions 运行 pytest，确保代码质量
4. **文档站点**：考虑使用 MkDocs 或 Docusaurus 建立文档站点
5. **版本发布**：遵循 Semantic Versioning，使用 GitHub Releases 管理版本

---

## 与同类项目对比

| 特性 | 本项目 | 典型 RAG 开源项目 |
|------|--------|------------------|
| 核心链路完整性 | ✅ 完整 | ✅ |
| 评测系统 | ⚠️ 有 bug | ✅ |
| 多平台支持 | ❌ 仅 Windows | ✅ |
| 文档质量 | ✅ 详尽 | ✅ |
| 测试覆盖 | ⚠️ 部分缺失 | ✅ |
| 代码规范 | ⚠️ 有违规 | ✅ |
| 安装便捷性 | ⚠️ 需配置 torch | ✅ |

**差距主要在**：评测系统 bug、平台兼容性、测试覆盖。核心链路和文档质量是优势。
