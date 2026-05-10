# 清理分支独立 Issue 处理计划

> 分支：`cleaning`（w1-easy-rag）
> 日期：2026-04-26
> 前提：避开 `golden-qa-150`（问题生成器）和 `verify-baseline`（核心问答与评测链路）两个 worktree 正在处理的模块

---

## 其他 Worktree 占用范围

| Worktree | 分支 | 占用模块 | 占用文件 |
|----------|------|----------|----------|
| ash-easy-rag | golden-qa-150 | 问题生成器、Meal 管理、缓存安全 | `test_generator.py`, `test_set_manager.py`, `meal.py`, `document_loader.py`, `parser.py` |
| w0-easy-rag | verify-baseline | 评测链路、实验配置、证据追踪 | `pipeline.py`, `experiment.py`, `chunker.py`, `retriever.py`, `eval/` |

**安全区**：`main.py`, `interactive.py`, `artifact_cli.py`, `llm_client.py`, `token_tracker.py`, `utils.py`, `exceptions.py`, `embedder.py`, `indexer.py`, `reranker.py`, `query_rewriter.py`, `bm25_retriever.py`, `hybrid_retriever.py`, `sampler.py`, `semantic_chunker.py`, 配置文件, 文档, 测试

---

## 选取的 Issue 及执行顺序

### Issue 1: RF-002 — 合并 interactive.py 到 main.py（方案 C）

**规模**：小→中 | **风险**：低 | **占用文件**：`main.py`, `interactive.py`

**依据**：[RF-002 评估报告](../docs/reviews/investigations/rf-002-project-structure.md)推荐方案 C

**执行步骤**：

1. 在 `main.py` 中新增 `--interactive` 参数
2. 将 `interactive.py` 的 UX 优化（中文界面、emoji、来源数量限制、启动时显示 chunk 数量）融入 `--interactive` 模式
3. `--interactive` 不指定 `--meal` 时使用默认 Pipeline（等价原 `interactive.py` 行为）
4. 保留 `--meal <name>`（无 `--query`）时的隐式交互模式（行为不变）
5. 删除 `interactive.py`
6. 更新文档引用（约 4 处）：`README.md`, `docs/getting-started.md`, `docs/architecture.md`, `docs/cli-reference.md`
7. 更新 `pixi.toml`：新增 `interactive` task 别名
8. 更新 `.trae/rules` 中如有引用 `interactive.py` 的地方
9. 运行 `pixi run lint` 确认代码质量
10. 运行 `pixi run pytest tests/ -m "not integration" -v` 确认无回归
11. 提交

**不涉及**：pipeline.py、eval/、test_generator.py、test_set_manager.py

---

### Issue 2: FEAT-034 — 开源准备度完善

**规模**：中 | **风险**：极低 | **占用文件**：纯文档

**执行步骤**：

1. 创建 `CONTRIBUTING.md`：开发环境搭建、代码规范、提交规范、PR 流程
2. 更新 `README.md`：
   - 版本徽章 v0.1.5 → v0.1.8
   - 项目结构（删除 interactive.py、新增 artifact_cli.py 等）
   - 补充 Meal/Artifact 体系说明
   - 更新致谢列表
3. 可选创建 `SECURITY.md`：安全漏洞报告流程
4. 提交

**不涉及**：任何源码文件

---

### Issue 3: RF-001 — CLI 输出规范化（缩减范围）

**规模**：小 | **风险**：低 | **占用文件**：`pipeline.py`（4 处 print）

**说明**：原 issue 提到 172 处 print，但实际扫描仅 24 处，其中 20 处在 `artifact_cli.py`（CLI 工具的 print 是合理的），仅 `pipeline.py` 有 4 处违规 print。

**⚠️ 风险评估**：`pipeline.py` 正在 `verify-baseline` worktree 中被修改。需评估冲突风险：
- 4 处 print 位于 L668-L675 的交互式问答展示区
- `verify-baseline` 主要修改评测指标和证据追踪，不太会动交互展示区
- **但如果对冲突有顾虑，可跳过此 issue**

**执行步骤**（如果执行）：

1. 将 `pipeline.py` 中 4 处 `print()` 替换为 `logger.info()` 或 `logger.success()`
2. 运行 lint 和测试
3. 提交

**备选**：如果跳过 RF-001，改为处理 **RF-008**（backlog issue 详细信息记录），纯文档/工具改进。

---

### Issue 4: RF-008 — backlog issue 详细信息记录

**规模**：中 | **风险**：极低 | **占用文件**：`docs/backlog.md`, `.trae/skills/todo-archiver/`

**执行步骤**：

1. 在 `docs/` 下新建 `docs/reviews/issues/` 目录，用于存放各 issue 的详细描述
2. 为当前待处理的高优先级 issue（BUG-024/025, FEAT-014, FEAT-028 等）创建详细描述文件
3. 在 `backlog.md` 的表格备注列中添加超链接指向详细文件
4. 更新 todo-archiver skill，在归档新 issue 时自动创建详情文件模板
5. 提交

**不涉及**：任何源码文件

---

## 执行优先级

| 顺序 | Issue | 预计工作量 | 依赖 |
|------|-------|-----------|------|
| 1 | RF-002（合并 interactive.py） | 中 | 无 |
| 2 | FEAT-034（开源准备度） | 中 | RF-002 完成后（README 需反映新结构） |
| 3 | RF-001 或 RF-008（二选一） | 小 | 无 |

**总计**：3-4 个 issue，预计可在一次 session 内完成。

---

## 不选取的 Issue 及理由

| Issue | 不选理由 |
|-------|---------|
| FEAT-028（配置验证 Pydantic） | 需新增 pydantic 依赖，按规范须先告知用户 |
| FEAT-033（日志增强 pytest-loguru） | 需新增 pytest-loguru 依赖 |
| FEAT-017（CI/CD） | 需研究 GitHub Actions 配置，工作量较大 |
| FEAT-024/035/037 | 涉及 parser/chunker，与 golden-qa-150 或 verify-baseline 冲突 |
| FEAT-012/014/041/043 | 涉及 experiment.py，与 verify-baseline 冲突 |
| BUG-024/025/028 | 涉及评测链路 source_chunks，与 verify-baseline 冲突 |
| OPT-002/008/010 | 需要实际运行性能测试，依赖环境配置 |
| INV-022 | 纯调研，无代码产出 |
