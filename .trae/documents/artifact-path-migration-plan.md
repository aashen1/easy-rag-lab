# 计划：清除旧路径体系，全面适配 Artifact 逻辑 + UX 优化

## 背景

当前代码中存在两套路径体系并存的问题：

| 体系 | 路径示例 | 管理方式 |
|------|----------|----------|
| 旧路径 | `data/parsed`, `data/chunks`, `data/vector_store` | config.yaml 配置 + 硬编码默认值 |
| Artifact | `data/artifacts/{data_id[:16]}/parsed_{hash}/`, `data/artifacts/{data_id[:16]}/chunks_{hash}/` | ArtifactCache 类管理 |

**核心矛盾**：Pipeline 的 Step 1 (parse) 已经走 ArtifactCache，但 Step 2 (chunk) 和 Step 3 (index) 仍然使用 `chunker_config["input_dir"]` / `chunker_config["output_dir"]`（即 `data/parsed` / `data/chunks`），导致全量解析后分块步骤找不到输入文件。

---

## 第一部分（必做）：清除旧路径，全面适配 Artifact

### 1.1 重构 `pipeline.py` 的 `build_index()` 方法

**当前问题**：
- L238/L266: source_filter 计算使用 `parser_config["output_dir"]`（`data/parsed`）
- L271-274: chunker 调用使用 `chunker_config["input_dir"]` / `chunker_config["output_dir"]`
- L293: indexer 调用使用 `chunker_config["output_dir"]`
- L311: BM25 调用使用 `chunker_config["output_dir"]`

**改造方案**：
- parse 完成后，从 `parse_results` 或 `ArtifactCache` 获取实际的 `parsed_dir`
- 计算 `chunker_hash`，通过 `ArtifactCache.get_chunks_dir(data_id, chunker_hash)` 获取 `chunks_dir`
- 将 `parsed_dir` 和 `chunks_dir` 传入 chunker 和 indexer，替代从 config 读取的旧路径
- source_filter 的相对路径计算也基于实际的 `parsed_dir` / `chunks_dir`

### 1.2 重构 `chunker.py` 的独立运行模式

**当前问题**：`__main__` 块（L680-697）直接使用 `chunker_config["input_dir"]` / `chunker_config["output_dir"]`

**改造方案**：
- 引入 ArtifactCache，计算 data_id 和 parser_hash / chunker_hash
- 从 ArtifactCache 获取 `parsed_dir` 和 `chunks_dir`
- 传递给 `process_parsed_files()` 等函数

### 1.3 移除 `test_generator.py` 的旧路径回退逻辑

**当前问题**：
- `_resolve_parsed_dir()` L407: 回退到 `data/parsed`
- `_resolve_chunks_dir()` L441: 回退到 `data/chunks`
- `find_adjacent_chunks()` L1609: 回退到 `data/chunks`

**改造方案**：
- 删除回退分支，只保留 ArtifactCache 路径解析
- 如果 ArtifactCache 解析失败，返回 None 并记录 warning（而非静默回退到旧路径）

### 1.4 修复 `recommend_testset.py` 的硬编码路径

**当前问题**：
- L340: `Path("data/meals")` 硬编码
- L353: `Path("data/parsed")` 硬编码
- L373: `Path("data/exp_reports")` 硬编码

**改造方案**：
- 引入 `load_config()` 读取配置
- `data/meals` → 从 config 读取 `meals.dir`
- `data/parsed` → 通过 ArtifactCache 解析
- `data/exp_reports` → 从 config 读取 `experiments.dir`

### 1.5 清理 `meal.py` 中的旧路径引用

**当前问题**：
- L747: `self.chunks_dir = Path(config.get("chunker", {}).get("output_dir", "data/chunks"))` — 这个属性在 MealManager 中可能仍被使用

**改造方案**：
- 检查 `self.chunks_dir` 的所有使用点，替换为通过 `self.cache.get_chunks_dir()` 获取
- 删除 `self.chunks_dir` 属性

### 1.6 更新 `config.yaml`

**改造方案**：
- 将 `parser.output_dir`、`chunker.input_dir`、`chunker.output_dir` 标记为 deprecated
- 这些路径不再作为实际 I/O 路径使用，仅保留为向后兼容的注释说明
- 或者直接删除这些配置项（更彻底，但需要确认无其他依赖）

**倾向**：直接删除，因为这些路径在 artifact 体系下完全由 hash 决定，用户不应手动指定。

### 1.7 更新 `indexer.py` 默认值

**当前问题**：L18 `persist_dir: str = "data/vector_store"` 硬编码默认值

**改造方案**：
- 改为从 config 读取，或使用 `None` 作为默认值并在初始化时从 config 注入
- 在 Meal 模式下，Qdrant collection 名已经包含 hash 信息，persist_dir 可以保持不变（Qdrant 本地存储路径与 artifact 路径是不同概念）

**注意**：`data/vector_store` 是 Qdrant 的本地持久化目录，与 parsed/chunks 的 artifact 路径性质不同。Qdrant 通过 collection_name 区分不同 meal 的数据，persist_dir 只是 Qdrant 的数据根目录。这个路径可以保留，但应从 config 统一读取而非硬编码默认值。

### 1.8 更新脚本文件

- `scripts/generate_golden_testset.py`：默认参数从 `data/parsed` / `data/chunks` 改为通过 ArtifactCache 解析
- `scripts/analyze_tokenizer_diff.py`：硬编码 `data/chunks` 改为通过 ArtifactCache 解析

### 1.9 更新测试文件

- `tests/test_test_generator.py`：mock 配置中的 `"output_dir": "data/parsed"` / `"data/chunks"` 需要更新为 artifact 路径或移除
- `tests/test_run_experiment.py`：`"input_dir": "data/raw"` 可保留（raw 是源文件目录，不属于 artifact 体系）

### 1.10 更新 `data/README.md`

- 移除 `data/parsed/`、`data/chunks/`、`data/vector_store/` 的描述
- 添加 `data/artifacts/` 的目录结构说明
- 更新重建流程说明

---

## 第二部分（优化）：全量解析 UX 优化

### 问题

全量解析后，产物落在 `data/artifacts/d3a711e69a4e.../parsed_a1b2c3d4/`，用户很难直观找到。

### 方案：Pointer 文件 + CLI 查询

#### 2.1 Pointer 文件机制

在 `ArtifactCache` 中新增 pointer 管理功能：

```
data/artifacts/
├── _pointers/
│   ├── full_parsed.pointer    # 内容: d3a711e69a4e.../parsed_a1b2c3d4
│   └── full_chunks.pointer    # 内容: d3a711e69a4e.../chunks_e5f6g7h8
├── d3a711e69a4e.../
│   ├── manifest.json
│   ├── parsed_a1b2c3d4/
│   └── chunks_e5f6g7h8/
```

**设计要点**：
- `_pointers/` 目录存放纯文本 `.pointer` 文件，每行记录一个 artifact 相对路径
- 全量解析完成后，`ArtifactCache` 自动更新对应的 pointer 文件
- pointer 文件内容为相对于 `data/artifacts/` 的路径，如 `d3a711e69a4e/parsed_a1b2c3d4`
- 提供 `ArtifactCache.resolve_pointer(name)` 方法，读取 pointer 并返回完整 Path
- Windows 兼容：使用文本文件而非 symlink（symlink 需要管理员权限）

**新增方法**：
```python
class ArtifactCache:
    def save_pointer(self, name: str, target: str) -> None:
        """Save a pointer file pointing to an artifact path.

        Args:
            name: Pointer name (e.g., 'full_parsed', 'full_chunks').
            target: Relative path under artifacts_dir (e.g., 'd3a7.../parsed_a1b2').
        """

    def resolve_pointer(self, name: str) -> Path | None:
        """Resolve a pointer to an actual artifact directory.

        Args:
            name: Pointer name to resolve.

        Returns:
            Full Path to the artifact directory, or None if pointer/target doesn't exist.
        """
```

#### 2.2 CLI 查询命令

新增一个简单的 CLI 入口，让用户可以查询当前 artifact 状态：

```bash
# 列出所有 artifact 组
pixi run python -m src.artifact list

# 查看全量解析指向
pixi run python -m src.artifact pointer full_parsed

# 显示某个 artifact 组的详细信息
pixi run python -m src.artifact info d3a711e69a4e
```

**实现方式**：在 `src/` 下新增 `artifact_cli.py`（或作为 `meal.py` 的 `__main__` 扩展），提供上述命令。

#### 2.3 在 pipeline 日志中输出友好路径

全量解析完成后，在日志中输出：
```
✓ Full parse complete. Artifacts at: data/artifacts/d3a711e69a4e/parsed_a1b2c3d4/
  Quick access: data/artifacts/_pointers/full_parsed.pointer
```

---

## 实施顺序

1. **Phase 1 - 核心路径迁移**（必做）
   1.1 → 1.5：源代码中的旧路径清除
   1.6 → 1.7：配置和默认值清理
   1.8 → 1.10：脚本、测试、文档更新

2. **Phase 2 - UX 优化**（在 Phase 1 基础上）
   2.1：Pointer 文件机制
   2.2：CLI 查询命令
   2.3：日志友好输出

3. **Phase 3 - 验证**
   - 运行 `pixi run lint` 确保代码质量
   - 运行 `pixi run pytest` 确保测试通过
   - 手动验证全量解析流程：parse → chunk → index 全链路走 artifact 路径

---

## 风险与注意事项

1. **向后兼容**：删除旧路径配置后，如果用户有旧数据在 `data/parsed` / `data/chunks` 中，需要提供迁移说明
2. **测试覆盖**：每个改造步骤都需要同步更新测试，确保 TDD
3. **Windows 兼容**：pointer 文件方案避免了 symlink 权限问题
4. **Qdrant persist_dir**：这个路径与 artifact 体系不同，Qdrant 通过 collection_name 区分数据，persist_dir 可以保持为 `data/vector_store`
5. **`data/raw` 保留**：raw 目录是源文件目录，不属于 artifact 体系，保持不变
