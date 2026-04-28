# 统一解析链路与全量解析支持

## 背景问题

- 旧 `parser.py` 直接调用 `pymupdf4llm`，输出到 `data/parsed/`
- Meal 流程通过 `ParserRegistry` + `ArtifactCache`，输出到 `data/artifacts/`
- 两套系统并存导致预解析结果无法复用
- Meal 是抽样机制，缺少"全量运行"的语义

## 设计目标

1. **统一解析链路**：所有解析都走 `ParserRegistry` + `ArtifactCache`
2. **支持全量模式**：无需 meal，直接解析所有 PDF
3. **严格缓存复用**：配置一致才复用，避免缓存污染
4. **直白的语义**：`pixi run python -m src.parser` = 全量解析，复用缓存

---

## 架构设计

### 全量模式的 `data_id` 计算

```python
# 全量模式使用固定的 data_id 前缀
# 基于 raw_dir 下所有 PDF 的 SHA256 组合
FULL_RAW_DATA_ID = compute_data_id(all_pdf_files_in_raw_dir)
```

### 目录结构

```
data/artifacts/
  ├── <full_data_id_12>
  │   ├── parsed_<parser_hash>/    # 全量解析结果
  │   ├── chunks_<chunker_hash>/   # 全量分块结果
  │   └── manifest.json
  └── <meal_data_id_12>/
      └── ...
```

### 缓存复用规则

| 检查项 | 验证方式 | 失败处理 |
|--------|---------|----------|
| 配置一致 | `parser_hash` 匹配 | 重新解析 |
| 文件完整 | 预期文件列表全部存在 | 重新解析 |
| 源文件未变 | PDF SHA256 对比 manifest | 重新解析 |

---

## 实现步骤

### 阶段 1：修改 `src/parser.py` 走统一链路

#### 1.1 改用 ParserRegistry

```python
# 旧：直接调用 pymupdf4llm
result = pymupdf4llm.to_markdown(str(pdf_file), page_chunks=page_chunks, **kwargs)

# 新：通过 ParserRegistry
parser = ParserRegistry.get(algorithm, parser_options)
result = parser.parse(str(pdf_file))
```

#### 1.2 输出到 Artifact 系统

```python
# 计算全量 data_id
all_pdfs = sorted(Path(config["parser"]["input_dir"]).rglob("*.pdf"))
all_files = [MealFile(path=rel, sha256=sha, size=stat) for rel in all_pdfs]
data_id = compute_data_id(all_files)

# 使用 ArtifactCache
artifacts_dir = Path(config.get("artifacts", {}).get("dir", "data/artifacts"))
cache = ArtifactCache(artifacts_dir)
parser_hash = compute_parser_config_hash(parser_config)
parsed_dir = cache.get_parsed_dir(data_id, parser_hash)
```

#### 1.3 复用缓存

```python
for pdf_file in pdf_files:
    output_file = parsed_dir / relative_path.with_suffix(".pages.json")

    if output_file.exists():
        # 还需要检查 manifest 确认源文件未变
        manifest = cache.load_manifest(data_id)
        if manifest and _is_cache_valid(pdf_file, manifest):
            logger.info(f"复用缓存: {pdf_file.name}")
            continue

    # 否则重新解析
    parser.parse(str(pdf_file))
```

---

### 阶段 2：修改 Meal 流程复用全局解析

#### 2.1 Meal 创建时检查全局缓存

```python
def create_meal(self, name, sampling_config, ...):
    # 先检查是否有全量解析结果
    full_data_id = self._compute_full_raw_data_id()
    full_parsed_dir = self.cache.get_parsed_dir(full_data_id, parser_hash)

    if full_parsed_dir.exists():
        logger.info("发现全量解析结果，复用")
        # 直接复用，无需重新解析
        self._reuse_full_parsed(meal_files, full_parsed_dir, parsed_dir)
    else:
        # 按原有逻辑解析
        self._parse_pdfs_with_registry(...)
```

#### 2.2 复制/硬链接策略

```python
def _reuse_full_parsed(self, meal_files, src_dir, dst_dir):
    for meal_file in meal_files:
        expected = Path(meal_file.path).with_suffix(".pages.json")
        src = src_dir / expected
        dst = dst_dir / expected

        if src.exists():
            # 方案 1: 硬链接（节省空间）
            os.link(src, dst)
            # 方案 2: 复制（更灵活）
            # shutil.copy2(src, dst)
```

---

### 阶段 3：增强缓存验证

#### 3.1 扩展 manifest 结构

```json
{
  "data_id": "...",
  "pdf_count": 100,
  "pdf_inventory": {
    "relative/path/file1.pdf": "sha256_hash_1",
    "relative/path/file2.pdf": "sha256_hash_2"
  },
  "parser_config_hash": "e936d3e3",
  "created_at": "2026-04-24T10:00:00"
}
```

#### 3.2 缓存有效性检查

```python
def _is_cache_valid(pdf_path: Path, manifest: dict) -> bool:
    """检查单个 PDF 是否可复用缓存"""
    rel = pdf_path.relative_to(raw_dir).as_posix()
    if rel not in manifest.get("pdf_inventory", {}):
        return False
    return compute_file_sha256(pdf_path) == manifest["pdf_inventory"][rel]

def validate_parsed_artifacts(parsed_dir: Path, manifest: dict) -> bool:
    """批量验证解析缓存"""
    for rel_path, expected_sha in manifest["pdf_inventory"].items():
        actual = parsed_dir / Path(rel_path).with_suffix(".pages.json")
        if not actual.exists():
            return False
        if compute_file_sha256(raw_dir / rel_path) != expected_sha:
            return False
    return True
```

---

### 阶段 4：修改 `ArtifactCache`

#### 4.1 新增方法

```python
class ArtifactCache:
    def get_full_parsed_dir(self, parser_hash: str) -> Path:
        """获取全量解析的 parsed 目录"""
        full_data_id = self._compute_full_data_id()
        return self.get_parsed_dir(full_data_id, parser_hash)

    def save_full_manifest(self, manifest: dict) -> Path:
        """保存全量解析的 manifest"""
        full_data_id = self._compute_full_data_id()
        return self.save_manifest(full_data_id, manifest)

    def load_full_manifest(self) -> dict | None:
        """加载全量解析的 manifest"""
        full_data_id = self._compute_full_data_id()
        return self.load_manifest(full_data_id)

    def _compute_full_data_id(self) -> str:
        """计算全量 raw_dir 的 data_id"""
        all_pdfs = sorted(self.raw_dir.rglob("*.pdf"))
        # 复用 Meal 的 compute_data_id 逻辑
        ...
```

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/parser.py` | 重构 | 改用 ParserRegistry + ArtifactCache |
| `src/meal.py` | 修改 | 增加全局缓存复用逻辑 |
| `src/meal.py` | 新增 | `ArtifactCache` 增加全量模式方法 |
| `tests/test_parser.py` | 新增 | 测试统一链路 |
| `tests/test_meal.py` | 修改 | 增加缓存复用测试 |

---

## 向后兼容

- `data/parsed/` 目录不再使用，但保留不删除
- Meal 的 `create_meal` API 不变
- 新增 `python -m src.parser --full` 全量解析命令（默认就是全量）

---

## 验证要点

1. 运行 `python -m src.parser` → 输出到 `data/artifacts/<full_id>/parsed_<hash>/`
2. 再次运行 → 显示"复用缓存"，不重新解析
3. 修改 `config.yaml` 中的 parser 参数 → 新 hash，重新解析
4. 创建 Meal → 复用步骤 1 的解析结果
5. 替换某个 PDF → 该文件重新解析，其他复用缓存
