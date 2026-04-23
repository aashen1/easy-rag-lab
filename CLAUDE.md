## 项目简介

- **功能**：金融研报 RAG 问答系统
- **文档来源**：企业年报 PDF、行业研报 PDF，位于 `data/raw/`
- **开发目标**：学习 RAG 核心原理，系统性探究超参数与技术选型对回答质量的影响

---

## 开发规范

### 版本控制

完成逻辑工作单元后立即提交，只 stage 自己修改的文件。禁止 `git add -A` / `git add .`。Conventional Commits 英文格式（`feat:`/`fix:`/`test:`/`docs:`/`refactor:`/`chore:`，祈使语气）。完整规范见 `.trae/rules/commit-rule.md`。

### 测试
- 使用 Red/Green TDD 进行开发
- 每步开发必须附带 pytest 测试，确保行为符合预期
- 测试文件与源文件保持对应关系（如 `src/parser.py` → `tests/test_parser.py`）

### 代码质量
- **日志**：使用 `loguru`，禁止使用 `print`
- **类型标注**：所有公共函数必须标注参数类型与返回值类型
- **Docstring**：所有公共函数须包含功能描述、参数说明（Args）、返回值说明（Returns）、异常说明（Raises）
- **异常处理**：所有 IO 操作（PDF 读取、网络请求、文件写入）必须有 `try/except`，捕获异常后记录日志并优雅降级，禁止让程序直接崩溃
- **代码格式化**：使用 `ruff` 自动格式化和检查；如需忽略特定规则，使用 `# noqa: RULE` 标注
- **Lint 检查**：完成代码修改后，运行 `pixi run lint` 检查并格式化代码；也可用 `pixi run ruff-check` 仅检查不修改

### 配置与环境
- **超参数与配置**：所有超参数、模型名、路径等均写入 `config.yaml`，禁止在代码中硬编码
- **环境变量**：变量命名参考 `.env.example`，敏感信息（API Key 等）不得提交至仓库
- **依赖选型**：如需变更任何依赖或技术选型，须先告知，不得擅自替换

### 持久化
- 文档解析结果、向量索引等中间产物必须落盘，避免每次启动时重建

### 项目记忆
- 本项目文档系统同时服务于人类与 AI，是跨 session 的项目记忆系统
- 新 session 启动时必须先读 CLAUDE.md + backlog.md + version-history.md 理解项目状态
- 代码变更必须同步更新文档，确保下个 session 能理解本次变更意图
- 详细方法论：调用 skill `project-memory`；完整参考：[docs/methodology.md](docs/methodology.md)

---

## 文档维护规则

- 创建新功能时，同步创建 `docs/guides/<feature>.md`
- 修复疑难 bug 时，创建 `docs/troubleshooting/<bug-name>.md`
- 版本发布后，创建 `docs/reviews/vX.X.X/` 目录下的验收报告
- 代码变更必须同步更新相关文档
- 文档文件名统一使用英文
- code-review 中"建议单开"的内容必须同时添加到 `docs/backlog.md`
- 聊天记录入库前必须精简内容、规范命名

### 收件箱检查规则

- 每次对话开始时，检查 `docs/inbox/` 目录是否有新文件
- 如有新文件，提示用户"发现收件箱有 N 个待处理文件，是否处理？"
- 处理完成后，在 `docs/inbox-log.md` 中记录处理结果
- 原始文件移动到 `docs/inbox-processed/`

### TODO归档检查规则

- 每次对话开始时，检查 `TODO.md` 中是否有未归档的 issue（即 `- [ ]` 且无 `📋` 标记的条目）
- 如有未归档 issue，提示用户"发现 TODO.md 有 N 条未归档 issue，是否执行归档？"
- 用户说"打扫卫生""归档TODO"等指令时，也触发归档流程
- 归档流程：调用 todo-archiver skill，将 issue 单向归档到 `docs/backlog.md`
- 归档后在 TODO.md 原条目追加 `📋 YYYY-MM-DD 归档为 [ID]` 时间戳，不删除原内容，不打钩
- 如发现已归档 issue 在 backlog 中已完成，则打钩、追加 `✅ YYYY-MM-DD 该issue已确认完成` 时间戳、移动到对应日期标题下
- 为每个日期标题的 verbose 生成 summary 摘要

---

## 当前状态

**版本**：v0.1.8（评估系统可靠性增强与 TestSetManager 架构）

**新功能**：
- Context Precision、Context Recall、Chunk-level、Dedup、FPR 五项新指标
- TestSetManager 系统：结构化测试集生命周期管理
- 等价组支持：meal 推断与指标归一化
- 实验配置重组：templates + 分类目录结构
- 问题有效性检查与增量生成

**待做事项**：参见 [docs/backlog.md](docs/backlog.md)

**下版本方向**：参见 [docs/reviews/v0.1.8/release-summary.md](docs/reviews/v0.1.8/release-summary.md)

---

## 文档索引

详细文档请参阅 [docs/README.md](docs/README.md)。
