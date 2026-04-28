# 计划：清除旧路径体系，全面适配 Artifact 逻辑 + UX 优化

## 背景

当前代码中存在两套路径体系并存的问题：

| 体系 | 路径示例 | 管理方式 |
|------|----------|----------|
| 旧路径 | `data/parsed`, `data/chunks`, `data/vector_store` | config.yaml 配置 + 硬编码默认值 |
| Artifact | `data/artifacts/{data_id[:16]}/parsed_{hash}/`, `data/artifacts/{data_id[:16]}/chunks_{hash}/` | ArtifactCache 类管理 |

---

## 重新审视：各问题点当前状态

### ✅ 已修复的问题

#### 1.1 `pipeline.py` 的 `build_index()` — **大部分已修复**

之前的问题（source_filter 使用旧路径、chunker/indexer 使用旧路径）现在状态：

- ✅ L233: `parsed_dir = cache.get_parsed_dir(data_id, parser_hash)` — 已通过 ArtifactCache 获取
- ✅ L249: `output_path.relative_to(parsed_dir)` — source_filter 已基于 artifact parsed_dir
- ✅ L255-262: `chunker_hash` 计算和 `chunks_dir = cache.get_chunks_dir(data_id, chunker_hash)` — 已通过 ArtifactCache 获取
- ✅ L282-284: `input_dir=str(parsed_dir), output_dir=str(chunks_dir)` — page_aware 分块已用 artifact 路径
- ✅ L294-296: `input_dir=str(parsed_dir), output_dir=str(chunks_dir)` — semantic 分块已用 artifact 路径
- ✅ L305-307: `input_dir=str(parsed_dir), output_dir=str(chunks_dir)` — fixed 分块已用 artifact 路径
- ✅ L321-322: `output_path.relative_to(chunks_dir)` — source_filter 已基于 artifact chunks_dir
- ✅ L331: `chunks_dir=str(chunks_dir)` — indexer 已用 artifact 路径

**但仍有 1 处遗漏**：
- ❌ L349: `chunks_dir=chunker_config["output_dir"]` — BM25 索引构建仍使用旧路径 `data/chunks`

#### 1.1b `pipeline.py` 的 `use_meal()` — **已修复**

- ✅ L412-419: BM25 切换 meal 时已通过 ArtifactCache 获取 chunks_dir

### ❌ 仍未修复的问题

#### 1.2 `chunker.py` 的独立运行模式 — **未修复**

- ❌ L687-689: `input_dir=chunker_config["input_dir"]`, `output_dir=chunker_config["output_dir"]` — 仍使用 config 中的 `data/parsed` / `data/chunks`

#### 1.3 `test_generator.py` 的旧路径回退逻辑 — **未修复**

- ❌ L1089: `_resolve_parsed_dir()` 回退到 `self.config.get("parser", {}).get("output_dir", "data/parsed")`
- ❌ L1123: `_resolve_chunks_dir()` 回退到 `self.config.get("chunker", {}).get("output_dir", "data/chunks")`
- ❌ L3044-3046: `find_adjacent_chunks()` 回退到 `self.config.get("chunker", {}).get("output_dir", "data/chunks")`

#### 1.4 `recommend_testset.py` 的硬编码路径 — **未修复**

- ❌ L340: `Path("data/meals")` 硬编码
- ❌ L353: `Path("data/parsed")` 硬编码
- ❌ L373: `Path("data/exp_reports")` 硬编码

#### 1.5 `meal.py` 中的旧路径引用 — **未修复**

- ❌ L746-748: `self.chunks_dir = Path(config.get("chunker", {}).get("output_dir", "data/chunks"))` — 属性仍存在
- 经 grep 确认 `self.chunks_dir` 仅在 L746 定义，未被其他地方引用（可安全删除）

#### 1.6 `config.yaml` 中的旧路径配置 — **未修复**

- ❌ L69: `parser.output_dir: "data/parsed"`
- ❌ L104: `chunker.input_dir: "data/parsed"`
- ❌ L105: `chunker.output_dir: "data/chunks"`

#### 1.7 `indexer.py` 默认值 — **未修复**

- ❌ L18: `persist_dir: str = "data/vector_store"` 硬编码默认值

#### 1.8 脚本文件 — **未修复**

- ❌ `scripts/generate_golden_testset.py` L1216/L1220: 默认参数 `data/parsed` / `data/chunks`
- ❌ `scripts/analyze_tokenizer_diff.py` L8: 硬编码 `data/chunks`

#### 1.9 测试文件 — **未修复**

- ❌ `tests/test_test_generator.py`: 11 处 `"output_dir": "data/parsed"` / `"data/chunks"`

#### 1.10 `data/README.md` — **未修复**

- ❌ 仍描述 `data/parsed/`、`data/chunks/`、`data/vector_store/` 目录结构

---

## 修订后的实施计划

### Phase 1 - 核心路径迁移（必做）

#### 1.1 修复 `pipeline.py` BM25 遗漏（1 处）

**文件**: [pipeline.py:349](file:///b:/project/w1-easy-rag/src/pipeline.py#L349)

将 `chunks_dir=chunker_config["output_dir"]` 改为 `chunks_dir=str(chunks_dir)`

#### 1.2 重构 `chunker.py` 独立运行模式

**文件**: [chunker.py:679-697](file:///b:/project/w1-easy-rag/src/chunker.py#L679-L697)

- 引入 ArtifactCache，计算 data_id、parser_hash、chunker_hash
- 从 ArtifactCache 获取 `parsed_dir` 和 `chunks_dir`
- 替代 `chunker_config["input_dir"]` / `chunker_config["output_dir"]`

#### 1.3 移除 `test_generator.py` 的旧路径回退逻辑（3 处）

**文件**: [test_generator.py](file:///b:/project/w1-easy-rag/src/test_generator.py)

- L1089: `_resolve_parsed_dir()` — 删除 `data/parsed` 回退
- L1123: `_resolve_chunks_dir()` — 删除 `data/chunks` 回退
- L3044-3046: `find_adjacent_chunks()` — 删除 `data/chunks` 回退

#### 1.4 修复 `recommend_testset.py` 硬编码路径（3 处）

**文件**: [recommend_testset.py](file:///b:/project/w1-easy-rag/eval/recommend_testset.py)

- L340: `Path("data/meals")` → 从 config 读取
- L353: `Path("data/parsed")` → 通过 ArtifactCache 解析
- L373: `Path("data/exp_reports")` → 从 config 读取

#### 1.5 清理 `meal.py` 中的 `self.chunks_dir`（1 处）

**文件**: [meal.py:746-748](file:///b:/project/w1-easy-rag/src/meal.py#L746-L748)

- 删除 `self.chunks_dir` 属性（经确认无其他引用）

#### 1.6 更新 `config.yaml`

**文件**: [config.yaml](file:///b:/project/w1-easy-rag/config.yaml)

- 删除 `parser.output_dir`（L69）
- 删除 `chunker.input_dir`（L104）
- 删除 `chunker.output_dir`（L105）
- 添加注释说明 parsed/chunks 路径现在由 artifact 体系自动管理

#### 1.7 更新 `indexer.py` 默认值

**文件**: [indexer.py:18](file:///b:/project/w1-easy-rag/src/indexer.py#L18)

- 将 `persist_dir: str = "data/vector_store"` 改为 `persist_dir: str | None = None`
- 在 `__init__` 中当 `persist_dir is None` 时从 config 读取

**注意**：`data/vector_store` 与 artifact 体系性质不同（Qdrant 通过 collection_name 区分数据），保留 config 中的配置项是合理的，只需消除硬编码默认值。

#### 1.8 更新脚本文件

- `scripts/generate_golden_testset.py` L1216/L1220: 默认参数改为通过 ArtifactCache 解析
- `scripts/analyze_tokenizer_diff.py` L8: 更新使用说明中的路径

#### 1.9 更新测试文件

- `tests/test_test_generator.py`: 11 处 `"output_dir": "data/parsed"` / `"data/chunks"` 需要更新

#### 1.10 更新 `data/README.md`

- 移除 `data/parsed/`、`data/chunks/` 的描述
- 添加 `data/artifacts/` 的目录结构说明
- 更新重建流程说明

### Phase 2 - UX 优化（在 Phase 1 基础上）

#### 2.1 Pointer 文件机制

在 `ArtifactCache` 中新增 pointer 管理功能：

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

**设计要点**：
- `_pointers/` 目录存放纯文本 `.pointer` 文件
- 全量解析完成后，`ArtifactCache` 自动更新对应的 pointer 文件
- pointer 文件内容为相对于 `data/artifacts/` 的路径
- Windows 兼容：使用文本文件而非 symlink

**新增方法**：
```python
class ArtifactCache:
    def save_pointer(self, name: str, target: str) -> None:
        """Save a pointer file pointing to an artifact path."""

    def resolve_pointer(self, name: str) -> Path | None:
        """Resolve a pointer to an actual artifact directory."""
```

#### 2.2 CLI 查询命令

新增 CLI 入口，让用户查询 artifact 状态：

```bash
pixi run python -m src.artifact list          # 列出所有 artifact 组
pixi run python -m src.artifact pointer full_parsed  # 查看全量解析指向
pixi run python -m src.artifact info d3a711e69a4e    # 显示详细信息
```

#### 2.3 在 pipeline 日志中输出友好路径

全量解析完成后输出：
```
✓ Full parse complete. Artifacts at: data/artifacts/d3a711e69a4e/parsed_a1b2c3d4/
  Quick access: data/artifacts/_pointers/full_parsed.pointer
```

### Phase 3 - 验证

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
