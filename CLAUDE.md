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

### 文件删除与回收站
- **禁止永久删除文件**：不得使用 `DeleteFile`、`rm`、`del` 等操作直接删除文件
- 所有需要删除的文件/目录必须移入 `.trashbin/` 目录，带时间戳子目录避免冲突
- 例外：AI 当次会话自建的临时文件、`__pycache__` 目录可直接删除
- 完整规范见 `.trae/rules/trashbin-rule.md`

### 项目记忆
- 本项目文档系统同时服务于人类与 AI，是跨 session 的项目记忆系统
- 新 session 启动时必须先读 CLAUDE.md + `.issues/context.md` + version-history.md 理解项目状态
- 代码变更必须同步更新文档，确保下个 session 能理解本次变更意图
- 详细方法论：调用 skill `project-memory`；完整参考：[docs/methodology.md](docs/methodology.md)

### Issue 系统
- 项目使用 `.issues/` 目录管理 issue，替代旧的 `docs/backlog.md`
- 所有 issue 通过 CLI 管理：`pixi run issue <command>`
- 常用命令：
  - `pixi run issue create -t <type> -T "<title>"` — 创建 issue
  - `pixi run issue list` — 列出活跃 issue
  - `pixi run issue show <id>` — 查看 issue 详情
  - `pixi run issue start <id>` — 开始处理 issue
  - `pixi run issue done <id>` — 完成 issue
  - `pixi run issue summary` — 生成统计摘要
  - `pixi run issue context` — 显示当前聚焦 issue
- Issue 类型：`bug` / `feat` / `rf` / `opt` / `inv` / `test`
- Issue 状态流：`todo → in_progress → review → done`（可延期或取消）
- 目录结构：`.issues/active/`（活跃）、`.issues/completed/`（已完成）、`.issues/deferred/`（延期）、`.issues/cancelled/`（取消）

---

## 文档维护规则

- 创建新功能时，同步创建 `docs/guides/<feature>.md`
- 修复疑难 bug 时，创建 `docs/troubleshooting/<bug-name>.md`
- 版本发布后，创建 `docs/reviews/vX.X.X/` 目录下的验收报告
- 代码变更必须同步更新相关文档
- 文档文件名统一使用英文
- code-review 中"建议单开"的内容必须同时创建 issue（使用 `pixi run issue create`）
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
- 归档流程：调用 todo-archiver skill，使用 `pixi run issue create` 创建 issue 文件
- 归档后在 TODO.md 原条目追加 `📋 YYYY-MM-DD 归档为 [ID]` 时间戳，不删除原内容，不打钩
- 如发现已归档 issue 在 `.issues/` 中已完成，则打钩、追加 `✅ YYYY-MM-DD 该issue已确认完成` 时间戳、移动到对应日期标题下
- 为每个日期标题的 verbose 生成 summary 摘要

---

## 当前状态

**版本**：v0.1.13（RAG 可视化）

**版本叙事**：量得准 → 解得开 → 合得拢 → 管得住 → 看得见

| 版本 | 主题 | 一句话 |
|------|------|--------|
| v0.1.9 | 评测双引擎 | 有了可信的尺子 |
| v0.1.10 | 解析新纪元 | 有了自由的源头 |
| v0.1.11 | 链路统一 | 有了统一的基准 |
| v0.1.12 | 项目治理 | 有了可持续的节奏 |
| v0.1.13 | RAG 可视化 | 有了可展示的产品 |

**待做事项**：参见 `.issues/active/` 目录或运行 `pixi run issue list`

**下版本方向**：透明版完整实验报告（FEAT-010）、"花头"效果验证、指标得分上下限确认

---

## 文档索引

详细文档请参阅 [docs/README.md](docs/README.md)。
