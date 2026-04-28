# Tasks

## P0 — 阻塞级（评测结果不可信）

- [x] Task 1: 修复 Source 路径跨平台归一化（P0-1）
  - [x] 1.1: 修改 `src/chunker.py` — 所有写入 `source` 字段的位置，将 `str(relative_path)` 改为 `relative_path.as_posix()`，确保 JSONL 中 source 使用 POSIX 格式
  - [x] 1.2: 修改 `eval/evaluators/builtin_evaluator.py` — 无等价组时也对 retrieved 和 expected 的 source 进行 `normalize_source` 归一化后再比较
  - [x] 1.3: 修改 `eval/metrics/utils.py` — `normalize_source` 函数内部统一使用 `Path.as_posix()` 处理输入路径
  - [x] 1.4: 修改 `src/meal.py` — 等价组推断和 meal_snapshot 生成中的路径统一使用 POSIX 格式
  - [x] 1.5: 编写/更新测试验证跨平台路径归一化行为

- [x] Task 2: 修复等价组推断逻辑（P0-2）
  - [x] 2.1: 修改 `src/meal.py::_infer_equivalence_groups()` — group_key 加入父目录信息（如 `云南白药/2023年年度报告` 而非仅 `2023年年度报告`）
  - [x] 2.2: 确保同一目录下同名不同版本文件（如 `_英文版_`、`摘要`）仍归为同一组
  - [x] 2.3: 编写测试验证不同目录同名文件被分入不同等价组

- [x] Task 3: 修复 Generator 来源名称显示（P1-2，与 P0-1 联动）
  - [x] 3.1: 修改 `src/generator.py` 第 198 行 — 将 `Path(sources[i]).stem` 替换为清理逻辑，去除 `.pages` 后缀
  - [x] 3.2: 提取 `clean_source_name(source: str) -> str` 工具函数，统一处理 `.pages.json`、`.json`、`.md` 等后缀
  - [x] 3.3: 编写测试验证来源名称清理逻辑

## P1 — 高优先级（严重影响回答质量）

- [x] Task 4: 统一 Chunker 与 Embedder 的 Tokenizer（P1-1）
  - [x] 4.1: 在 `src/chunker.py` 中新增 `BGETokenizerEncoder` 类，封装 BGE 模型的 tokenizer 用于 token 计数和文本切分
  - [x] 4.2: 在 `config.yaml` 的 `chunker` 节新增 `encoding` 配置项，支持 `cl100k_base`（默认，向后兼容）和 `bge`（使用 embedder 模型的 tokenizer）
  - [x] 4.3: 修改 `chunk_text()` 函数 — 根据 `encoding` 配置选择 tokenizer，当选择 `bge` 时使用 `BGETokenizerEncoder`
  - [x] 4.4: 修改 `src/embedder.py` — 暴露 `get_tokenizer()` 方法供 chunker 复用
  - [x] 4.5: 编写测试验证 BGE tokenizer 切分行为与 tiktoken 切分的差异
  - [x] 4.6: 更新 `config.yaml` 默认 `encoding` 为 `bge`（与 embedder 对齐）

- [x] Task 5: 启用 Score Threshold 配置（P1-3）
  - [x] 5.1: 修改 `config.yaml` — 将 `retrieval.score_threshold` 从 `0` 改为 `0.3`
  - [x] 5.2: 确认现有测试在阈值变更后仍通过

- [x] Task 6: 启用 Context 截断保护（P2-2）
  - [x] 6.1: 修改 `config.yaml` — 将 `generation.max_context_tokens` 从 `null` 改为 `8000`
  - [x] 6.2: 确认现有测试在截断启用后仍通过

## P2 — 中优先级（优化体验与稳定性）

- [x] Task 7: 增加跨页 Chunk Overlap 支持（P2-1）
  - [x] 7.1: 在 `config.yaml` 的 `chunker` 节新增 `cross_page_overlap` 配置项（默认 0，向后兼容）
  - [x] 7.2: 修改 `src/chunker.py::chunk_text_page_aware()` — 当 `cross_page_overlap > 0` 时，将上一页的最后 N tokens 拼接到下一页开头再分块
  - [x] 7.3: 为跨页 overlap 生成的 chunk 在 metadata 中标记 `cross_page: true` 和相关页码信息
  - [x] 7.4: 编写测试验证跨页 overlap 行为

- [x] Task 8: 全局验证与清理
  - [x] 8.1: 运行 `pixi run lint` 确保代码质量
  - [x] 8.2: 运行 `pixi run test` 确保所有测试通过
  - [x] 8.3: 检查是否有其他位置硬编码了平台特定的路径分隔符

# Task Dependencies

- Task 1 (P0-1 路径归一化) 是独立任务，优先级最高
- Task 2 (P0-2 等价组) 依赖 Task 1（路径归一化后等价组推断更可靠）
- Task 3 (P1-2 来源名称) 独立于 Task 1/2，可并行
- Task 4 (P1-1 tokenizer) 独立于 Task 1/2/3，可并行
- Task 5 (P1-3 score threshold) 独立，可并行
- Task 6 (P2-2 context 截断) 独立，可并行
- Task 7 (P2-1 跨页 overlap) 依赖 Task 4（如果 chunker 切换到 BGE tokenizer，跨页 overlap 的 token 计数方式需一致）
- Task 8 (全局验证) 依赖所有其他 Task
