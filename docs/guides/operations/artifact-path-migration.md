# Artifact 路径迁移完成报告

**日期**：2026-04-26
**关联 Issue**：RF-020（全量测试路径重构 data/parsed→artifacts）
**关联 TODO**：FEAT-014（透明版报告）

---

## 1. 问题背景

项目在引入 Artifact 机制后，存在两套路径体系并存：

| 体系 | 路径示例 | 管理方式 |
|------|----------|----------|
| 旧路径 | `data/parsed`, `data/chunks` | config.yaml 配置 + 硬编码默认值 |
| Artifact | `data/artifacts/{data_id[:16]}/parsed_{hash}/` | ArtifactCache 类管理 |

**核心矛盾**：部分代码走 Artifact 路径，部分仍走旧路径，导致全量解析后分块步骤找不到输入文件，或 BM25 索引构建失败。此外，Artifact 路径含 hash 不直观，用户难以快速定位全量解析产物。

---

## 2. 解决的问题清单

### Phase 1：清除旧路径，全面适配 Artifact（必做）

| # | 问题 | 文件 | 修复方式 |
|---|------|------|----------|
| 1 | BM25 索引构建仍用 `chunker_config["output_dir"]` | `src/pipeline.py:349` | 改为 `str(chunks_dir)`（ArtifactCache 解析的路径） |
| 2 | chunker 独立运行仍用 config 中的旧路径 | `src/chunker.py:679-697` | 引入 ArtifactCache，计算 data_id/hash 获取实际路径 |
| 3 | `_resolve_parsed_dir()` 回退到 `data/parsed` | `src/test_generator.py:1089` | 删除回退分支，仅保留 ArtifactCache 解析 |
| 4 | `_resolve_chunks_dir()` 回退到 `data/chunks` | `src/test_generator.py:1123` | 删除回退分支，仅保留 ArtifactCache 解析 |
| 5 | `find_adjacent_chunks()` 回退到 `data/chunks` | `src/test_generator.py:3044` | 删除回退分支，无路径时返回空列表 |
| 6 | `recommend_testset.py` 3 处硬编码路径 | `eval/recommend_testset.py:340,353,373` | 改为从 config 读取 + ArtifactCache 解析 |
| 7 | `MealManager.chunks_dir` 引用旧路径 | `src/meal.py:746-748` | 删除该属性（经确认无其他引用） |
| 8 | config.yaml 中 `parser.output_dir` / `chunker.input_dir` / `chunker.output_dir` | `config.yaml:69,104,105` | 删除这三个配置项，添加说明注释 |
| 9 | `indexer.py` 硬编码 `data/vector_store` 默认值 | `src/indexer.py:18` | 改为 `None`，运行时从 config 读取 |
| 10 | 脚本文件引用旧路径 | `scripts/generate_golden_testset.py`, `scripts/analyze_tokenizer_diff.py` | 更新帮助文本 |
| 11 | 测试文件中 11 处旧路径引用 | `tests/test_test_generator.py` | 清除 mock 配置中的旧路径，改用 artifact 路径 |
| 12 | `data/README.md` 描述旧目录结构 | `data/README.md` | 全面重写，反映 artifact 体系 |

### Phase 2：UX 优化

| # | 功能 | 文件 | 实现方式 |
|---|------|------|----------|
| 1 | Pointer 文件机制 | `src/meal.py` | ArtifactCache 新增 `save_pointer()` / `resolve_pointer()` 方法 |
| 2 | 全量解析自动保存 pointer | `src/parser.py`, `src/pipeline.py` | parse 完成后保存 `full_parsed.pointer`，build_index 完成后保存 `full_chunks.pointer` |
| 3 | CLI 查询工具 | `src/artifact_cli.py` | 新增 `list` / `pointer` / `info` 三个子命令 |
| 4 | 日志友好输出 | `src/pipeline.py` | 全量构建完成后输出 artifact 路径和 pointer 位置 |

---

## 3. 技术方案细节

### 3.1 Pointer 文件机制

```
data/artifacts/
├── _pointers/
│   ├── full_parsed.pointer    # 内容: d3a711e69a4e/parsed_a1b2c3d4
│   └── full_chunks.pointer    # 内容: d3a711e69a4e/chunks_e5f6g7h8
├── d3a711e69a4e.../
│   ├── manifest.json
│   ├── parsed_a1b2c3d4/
│   └── chunks_e5f6g7h8/
```

- Pointer 文件是纯文本，内容为相对于 `data/artifacts/` 的路径
- 使用文本文件而非 symlink（Windows symlink 需要管理员权限）
- 全量解析/构建完成后自动更新
- 用户可通过 CLI 或直接读取 pointer 文件定位产物

### 3.2 CLI 工具

```bash
# 列出所有 artifact 组
pixi run python -m src.artifact_cli list

# 查看全量解析指向
pixi run python -m src.artifact_cli pointer full_parsed

# 显示某个 artifact 组的详细信息（支持前缀匹配）
pixi run python -m src.artifact_cli info d3a711e6
```

### 3.3 config.yaml 变更

删除的配置项：
- `parser.output_dir`（原值 `"data/parsed"`）
- `chunker.input_dir`（原值 `"data/parsed"`）
- `chunker.output_dir`（原值 `"data/chunks"`）

保留的配置项：
- `parser.input_dir`（`"data/raw"`）— 源文件目录，不属于 artifact 体系
- `vector_store.persist_dir`（`"data/vector_store"`）— Qdrant 本地持久化，通过 collection_name 区分数据

---

## 4. 验证方法

### 4.1 静态验证：旧路径残留检查

```bash
# 搜索源代码中是否还有 data/parsed 或 data/chunks 的硬编码引用
grep -rn '"data/parsed"\|"data/chunks"' src/ eval/
```

预期结果：无匹配（`data/raw` 和 `data/vector_store` 是合法保留项）。

### 4.2 配置验证

```bash
# 确认 config.yaml 中已无 parser.output_dir / chunker.input_dir / chunker.output_dir
grep -n 'output_dir\|chunker.input_dir' config.yaml
```

预期结果：无匹配。

### 4.3 Lint 验证

```bash
pixi run lint
```

预期结果：`All checks passed!`

### 4.4 测试验证

```bash
pixi run pytest tests/ -q
```

预期结果：1400+ passed（2 个预先存在的失败测试与本次修改无关，已在旧代码上确认失败）。

### 4.5 功能验证（需实际数据）

1. **全量解析**：`pixi run python src/parser.py`
   - 验证产物在 `data/artifacts/{data_id}/parsed_{hash}/`
   - 验证 `data/artifacts/_pointers/full_parsed.pointer` 已生成

2. **全量构建**：通过 pipeline `build_index()`
   - 验证 chunks 产物在 `data/artifacts/{data_id}/chunks_{hash}/`
   - 验证 `data/artifacts/_pointers/full_chunks.pointer` 已生成
   - 验证 BM25 索引使用 artifact 路径

3. **CLI 工具**：
   - `pixi run python -m src.artifact_cli list` 列出 artifact 组
   - `pixi run python -m src.artifact_cli pointer full_parsed` 解析 pointer
   - `pixi run python -m src.artifact_cli info {data_id_prefix}` 查看详情

---

## 5. 已知遗留

1. **2 个预先存在的测试失败**（与本次修改无关）：
   - `TestDocumentBasedQuestionsSourceFiles::test_source_files_set_in_generated_questions`
   - `TestGenerateDocumentBasedQuestionsSupplemental::test_supplemental_loop_fills_gap`
   - 原因：hybrid question 生成逻辑在无 chunks 时无法生成 evidence-based 问题

2. **文档中的旧路径引用**：`docs/archive/` 和部分 `docs/reviews/` 中的历史文档仍引用 `data/parsed` / `data/chunks`，这些是历史记录，不需要更新。

3. **`data/vector_store` 保留**：Qdrant 的 persist_dir 与 artifact 体系性质不同，通过 collection_name 区分不同 meal 的数据，保留 `data/vector_store` 是合理的。

---

## 6. Commit 记录

| Commit | 说明 |
|--------|------|
| `fix: use artifact chunks_dir for BM25 index build in pipeline` | pipeline.py BM25 修复 |
| `refactor: use ArtifactCache for chunker standalone run mode` | chunker.py 独立运行迁移 |
| `refactor: remove old path fallbacks from test_generator resolve methods` | test_generator.py 回退逻辑移除 |
| `refactor: replace hardcoded paths with config/artifact resolution in recommend_testset` | recommend_testset.py 硬编码修复 |
| `refactor: remove unused self.chunks_dir from MealManager` | meal.py 属性清理 |
| `refactor: remove deprecated path config fields from config.yaml` | config.yaml 配置清理 |
| `refactor: remove hardcoded persist_dir default from VectorIndexer` | indexer.py 默认值修复 |
| `docs: update script help text to reference artifact paths` | 脚本帮助文本更新 |
| `refactor: remove old path references from test_test_generator mock configs` | 测试文件清理 |
| `docs: update data/README.md to reflect artifact system` | README 更新 |
| `feat: add pointer file mechanism to ArtifactCache for UX optimization` | Pointer 机制 |
| `feat: add artifact CLI for querying artifact status and pointers` | CLI 工具 |
| `feat: add friendly artifact path logging after full pipeline build` | 日志友好输出 |
