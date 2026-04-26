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

**版本**：v0.1.9（统一测试集生成链路）

**近期变更**：
- 旧路径体系（data/parsed、data/chunks）已全面迁移至 Artifact 体系
- ArtifactCache 新增 Pointer 文件机制（_pointers/full_parsed.pointer 等）
- 新增 artifact_cli.py 命令行工具，支持 list/pointer/info 子命令
- config.yaml 中 parser.output_dir / chunker.input_dir / chunker.output_dir 已删除

**新功能**：
- 统一测试集生成链路：Golden 生成逻辑收编入 TestSetGenerator
- adversarial 问题类型：对抗性问题支持，默认分布 0%
- 数值精度校验：10 倍换算错误自动检测修正（所有策略受益）
- excerpt 验证：ground_truth_excerpt 原文真实性验证（所有策略受益）
- 文档去重：内容重叠检测与补充文档排除（golden 策略专用）
- 全量 meal 查找：MealManager.find_full_dataset_meal()
- Golden 自动生成：resolve_test_set 中 golden 不存在时自动生成

**近期修复**（2026-04-26）：
- BUG-026：pipeline.py 全量缓存路径不一致 → 改用 ArtifactCache 动态计算
- BUG-027：Token 统计无法按 variant 区分 → 新增 get_summary_by_variant()
- FEAT-042：实验全部失败时跳过 LLM 报告生成
- OPT-009：chunker 逐文件日志降噪（INFO→DEBUG）
- RF-014：normalize_source 已确认使用 include_parent=True
- RF-020：Golden 独立生成链路收编入 TestSetGenerator，消除重复代码

**待做事项**：参见 [docs/backlog.md](docs/backlog.md)

**下版本方向**：参见 [docs/reviews/v0.1.9/release-summary.md](docs/reviews/v0.1.9/release-summary.md)

---

## 文档索引

详细文档请参阅 [docs/README.md](docs/README.md)。
