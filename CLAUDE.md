## 项目简介

- **功能**：金融研报 RAG 问答系统
- **文档来源**：企业年报 PDF、行业研报 PDF，位于 `data/raw/`
- **开发目标**：学习 RAG 核心原理，系统性探究超参数与技术选型对回答质量的影响

---

## 开发规范

### 版本控制

完成逻辑工作单元后立即提交，只 stage 自己修改的文件。Conventional Commits 英文格式（祈使语气）。完整规范见 `.trae/rules/commit-rule.md`。

### 测试

Red/Green TDD 开发，每步附带 pytest 测试。测试文件与源文件对应（如 `src/parser.py` → `tests/test_parser.py`）。

三层测试命令（均使用 pytest-xdist 并行）：

| 命令 | 用途 | 预期耗时 |
|------|------|---------|
| `pixi run test-unit` | 只跑 `@pytest.mark.unit`，开发中秒级反馈 | ~10s |
| `pixi run test` | 排除 `integration` 和 `slow`，post-merge 验证 | ~35s |
| `pixi run test-all` | 全量测试，发版前验证 | ~60s |

Marker 说明：`unit`（纯单元测试）、`integration`（外部系统）、`slow`（重导入如 ragas/torch）。详见 [docs/dev-guides/testing.md](docs/dev-guides/testing.md)。

### 代码质量

- **日志**：使用 `loguru`，禁止 `print`
- **Docstring**：公共函数须包含功能描述、Args、Returns、Raises
- **异常处理**：所有 IO 操作必须有 `try/except`，捕获异常后记录日志并优雅降级
- **Lint**：修改后运行 `pixi run lint`；仅检查用 `pixi run ruff-check`

### 配置与环境

- 超参数、模型名、路径等写入 `config.yaml`，禁止硬编码
- 环境变量参考 `.env.example`，敏感信息不得提交
- 变更依赖或技术选型须先告知

### 持久化

文档解析结果、向量索引等中间产物必须落盘。

### 文件删除

禁止永久删除文件，必须移入 `.trashbin/`。详见 `.trae/rules/trashbin-rule.md`。

### 项目记忆

文档系统是跨 session 记忆。新 session 先读 CLAUDE.md + `.issues/context.md` + version-history.md。代码变更须同步更新文档。详见 [docs/methodology.md](docs/methodology.md)。

### 活文档规范

功能 spec 使用活文档范式（四件套：spec.md / progress.md / handoff.md / checklist.md），禁止编号快照子目录。详见 [docs/dev-guides/living-spec.md](docs/dev-guides/living-spec.md)。

### Issue 系统

通过 CLI 管理：`pixi run issue <command>`。类型/状态流/目录结构详见 [docs/user-guides/issue-system.md](docs/user-guides/issue-system.md)。

---

## 文档维护

- 新功能同步创建 `docs/user-guides/<feature>.md` 或 `docs/dev-guides/<feature>.md`
- 代码变更须同步更新相关文档；文件名统一英文
- code-review 中"建议单开"的内容须同时创建 issue

### 收件箱

每次对话开始检查 `docs/inbox/`，有新文件则提示用户处理。详见 [docs/methodology.md](docs/methodology.md)。

### TODO 归档

每次对话开始检查 `TODO.md` 未归档条目，有则提示归档。详见 [docs/methodology.md](docs/methodology.md)。

---

## 当前状态

**版本**：v0.1.17（修得好）| **叙事**：量得准 → 解得开 → 合得拢 → 管得住 → 看得见 → 撑得住 → 跑得快 → 诊得明 → 修得好

**待做**：`pixi run issue list` | **下版本**：透明版完整实验报告（FEAT-010）、Baseline 标定与花头效果验证、dev→main 合并准备

---

## 文档索引

详细文档请参阅 [docs/README.md](docs/README.md)。
