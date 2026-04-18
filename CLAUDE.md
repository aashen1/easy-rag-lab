## 项目简介

- **功能**：金融研报 RAG 问答系统
- **文档来源**：企业年报 PDF、行业研报 PDF，位于 `data/raw/`
- **开发目标**：学习 RAG 核心原理，系统性探究超参数与技术选型对回答质量的影响

---

## 开发规范

### 版本控制 - CRITICAL

**核心原则：完成任何逻辑工作单元后立即提交，绝不累积多个修改再提交**

**⚠️ 只提交自己做的改动：**
- 提交前必须运行 `git status` 和 `git diff` 确认
- **只 stage 自己在本次工作中修改的文件**
- **禁止使用 `git add -A` 或 `git add .`**（会包含他人的改动）
- 使用精确命令：`git add path/to/file1.py path/to/file2.py`
- 或使用交互式：`git add -p`

- ✅ 每完成一个 todo 项 → 立即提交
- ✅ 每实现一个函数/方法 → 立即提交  
- ✅ 每创建并通过一个测试 → 立即提交
- ✅ 每修复一个 bug → 立即提交
- ✅ 每修改配置/文档 → 立即提交

**适用所有工作模式**（Agent/Plan/Spec）：
- 每个步骤/任务完成后立即提交
- 禁止将所有实现累积到最后一次性提交
- **宁多勿少：过度提交优于提交不足**

- **commit message 仅允许英文 ASCII 字符**，遵循 Conventional Commits 格式：
  - `feat: add user authentication`
  - `fix: resolve null pointer in parser`
  - `test: add unit tests for validator`
  - 使用祈使语气（"add" 而非 "added"）

**自我检查机制**：开始新工作前，检查是否有未提交的修改。如有，先提交再继续。

### 测试
- 使用 Red/Green TDD 进行开发
- 每步开发必须附带 pytest 测试，确保行为符合预期
- 测试文件与源文件保持对应关系（如 `src/parser.py` → `tests/test_parser.py`）

### 代码质量
- **日志**：使用 `loguru`，禁止使用 `print`
- **类型标注**：所有公共函数必须标注参数类型与返回值类型
- **Docstring**：所有公共函数须包含功能描述、参数说明（Args）、返回值说明（Returns）、异常说明（Raises）
- **异常处理**：所有 IO 操作（PDF 读取、网络请求、文件写入）必须有 `try/except`，捕获异常后记录日志并优雅降级，禁止让程序直接崩溃
- **代码格式化**：使用 `autopep8` 自动格式化；如需固定 import 顺序，使用 `# noqa` 标注

### 配置与环境
- **超参数与配置**：所有超参数、模型名、路径等均写入 `config.yaml`，禁止在代码中硬编码
- **环境变量**：变量命名参考 `.env.example`，敏感信息（API Key 等）不得提交至仓库
- **依赖选型**：如需变更任何依赖或技术选型，须先告知，不得擅自替换

### 持久化
- 文档解析结果、向量索引等中间产物必须落盘，避免每次启动时重建

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

---

## 当前状态

**版本**：v0.1.6（项目卫生 + 文档系统重构）

**待做事项**：参见 [docs/backlog.md](docs/backlog.md)

**下版本方向**：参见 [docs/reviews/v0.1.6/next-direction.md](docs/reviews/v0.1.6/next-direction.md)

---

## 文档索引

详细文档请参阅 [docs/README.md](docs/README.md)。
