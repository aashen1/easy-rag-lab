# 套餐身份模型重构计划：从 UUID 到内容寻址

## 一、设计问题分析

### 你的核心洞察

1. **用 PDF 指纹合集作为唯一 ID** → 内容即身份，相同数据 = 相同 ID
2. **配置游离于身份之外** → 同一数据可搭配不同配置做对比实验
3. **配置变更导致中间产物不同** → 需要版本化存储 chunks、parsed 等产物

### 我的回答：分层内容寻址缓存（Layered Content-Addressable Cache）

核心思路来自构建系统（Make/Bazel/Nix）的成熟模式：**每个阶段的产物由"输入 + 配置"唯一确定**。

Pipeline 的推导链：

```
PDFs ──(parser_config)──→ Parsed Markdown ──(chunker_config)──→ Chunks ──(embedding_config)──→ Vectors
```

每一层的输出取决于：
- 上一层产物的身份（递归地取决于更上游的所有输入和配置）
- 本层的处理配置

因此，我们可以为每一层定义一个**缓存键**：

```
data_id     = hash(sorted(pdf_sha256_list))           # 纯数据身份
parse_key   = hash(data_id + parser_config)            # 解析产物身份
chunk_key   = hash(parse_key + chunker_config)         # 分块产物身份
index_key   = hash(chunk_key + embedding_config)       # 向量索引身份
```

**关键设计决策**：

| 问题 | 决策 | 理由 |
|------|------|------|
| 套餐唯一 ID | `data_id`（PDF 指纹合集的哈希） | 内容即身份，天然去重 |
| 配置是否纳入 ID | 不纳入，但存为快照 | 配置是实验变量，应可自由组合 |
| 中间产物如何存储 | 按缓存键分层存储，自动去重 | 相同输入+配置 = 相同产物，无需重复计算 |
| 向量索引如何命名 | 基于 `index_key` 派生 | 索引由数据+全链路配置唯一确定 |

---

## 二、新架构设计

### 2.1 身份模型

```
┌─────────────────────────────────────────────────┐
│  Meal（套餐）= 命名引用                           │
│  ├── data_id: 内容身份（PDF 指纹合集）             │
│  ├── config_snapshot: 配置快照（游离于身份之外）    │
│  ├── collection_name: 向量索引引用                 │
│  └── test_sets: 专属测试集                        │
└─────────────────────────────────────────────────┘
```

**data_id 计算方式**：
```python
def compute_data_id(pdf_files: List[MealFile]) -> str:
    sorted_hashes = sorted(f.sha256 for f in pdf_files)
    combined = "|".join(sorted_hashes)
    return hashlib.sha256(combined.encode()).hexdigest()
```

两个独立创建的套餐，只要包含相同的 PDF 文件（内容一致），就会有相同的 `data_id`。

### 2.2 配置快照

配置不纳入身份判定，但在 manifest 中完整保存，用于：
- 可复现性：知道当时用了什么配置
- 对比实验：diff 两个套餐的配置快照
- 缓存命中：检查是否已有相同配置的产物

```json
{
  "config_snapshot": {
    "parser": {"algorithm": "pymupdf4llm"},
    "chunker": {"chunk_size": 512, "overlap": 0, "encoding": "cl100k_base"},
    "embedding": {"model_name": "BAAI/bge-large-zh-v1.5", "device": "cuda"},
    "retrieval": {"top_k": 5}
  },
  "config_hashes": {
    "parser": "a1b2c3d4",
    "chunker": "e5f6a7b8",
    "embedding": "c9d0e1f2"
  }
}
```

### 2.3 产物存储结构

```
data/
├── raw/                                    # 源 PDF（不变）
├── artifacts/                              # 内容寻址产物缓存
│   └── {data_id[:12]}/                     # 数据组目录（短哈希，可读性）
│       ├── parsed/                         # 解析产物
│       │   └── *.md                        # Markdown 文件
│       ├── chunks_{chunker_hash[:8]}/      # 分块产物（按 chunker 配置版本化）
│       │   └── *.jsonl                     # JSONL 文件
│       └── manifest.json                   # 数据组元信息（PDF 列表、已有配置版本等）
├── vector_store/                           # Qdrant 持久化目录（不变）
│   └── collections: m_{index_key[:12]}     # 集合名由完整配置链派生
├── meals/                                  # 套餐元数据（薄引用）
│   └── {name}/
│       ├── manifest.json                   # data_id + config_snapshot + collection_name
│       └── test_sets/
│           └── *.json
```

### 2.4 缓存命中逻辑

创建套餐时的决策流程：

```
1. 计算 data_id
2. 检查 artifacts/{data_id}/ 是否存在
   ├── 不存在 → 创建目录，执行解析
   └── 存在 → 检查 parsed/ 是否完整
       ├── 不完整 → 重新解析缺失文件
       └── 完整 → 跳过解析（缓存命中 ✅）
3. 计算 chunker_config_hash
4. 检查 chunks_{chunker_hash}/ 是否存在
   ├── 不存在 → 执行分块
   └── 存在 → 跳过分块（缓存命中 ✅）
5. 计算 index_key（= hash(data_id + parser_config + chunker_config + embedding_config)）
6. 检查 Qdrant 中 m_{index_key[:12]} 集合是否存在
   ├── 不存在 → 构建索引
   └── 存在 → 跳过索引构建（缓存命中 ✅）
7. 写入套餐 manifest
```

### 2.5 典型使用场景

**场景 1：同一数据，不同 overlap**
```
data_id = abc123...（相同 PDF 集）

meal "baseline"     → chunker_hash = e5f6a7b8 (overlap=0)
                      → chunks_e5f6a7b8/  ← 独立目录
                      → collection: m_x1y2z3w4v5

meal "overlap_50"   → chunker_hash = g9h0i1j2 (overlap=50)
                      → chunks_g9h0i1j2/  ← 独立目录
                      → collection: m_k3l4m5n6o7

共享：artifacts/abc123.../parsed/  ← 同一份解析产物
```

**场景 2：同一数据 + 同一配置，不同测试集**
```
data_id = abc123...（相同 PDF 集）
chunker_hash = e5f6a7b8（相同 overlap）

meal "exp_a"  → test_sets/factual.json
meal "exp_b"  → test_sets/boundary.json

共享：parsed/、chunks_e5f6a7b8/、Qdrant collection ← 全部共享
差异：仅测试集不同
```

**场景 3：不同数据规模，同一配置**
```
meal "small"  → data_id = abc123... (10 PDFs)
meal "medium" → data_id = def456... (30 PDFs)
meal "large"  → data_id = ghi789... (100 PDFs)

配置相同，但数据不同 → 完全独立的产物目录
可用于观察检索效果随数据规模的变化
```

---

## 三、配置哈希计算

为每个 pipeline 阶段定义配置哈希，只包含**影响产物输出**的参数：

```python
def compute_parser_config_hash(parser_config: Dict) -> str:
    relevant = {"algorithm": parser_config.get("algorithm", "pymupdf4llm")}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]

def compute_chunker_config_hash(chunker_config: Dict) -> str:
    relevant = {
        "chunk_size": chunker_config["chunk_size"],
        "overlap": chunker_config["chunk_overlap"],
        "encoding": chunker_config.get("encoding", "cl100k_base"),
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]

def compute_embedding_config_hash(embedding_config: Dict) -> str:
    relevant = {
        "model_name": embedding_config["model_name"],
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]
```

**注意**：`device`、`batch_size` 等不影响产物内容的参数不纳入哈希。

---

## 四、实现步骤

### Phase 1：核心身份模型变更

**1.1 修改 `MealConfig` 数据结构**
- 移除 `uuid` 字段
- 新增 `data_id` 字段（PDF 指纹合集哈希）
- 新增 `config_snapshot` 字段（完整配置快照）
- 新增 `config_hashes` 字段（各阶段配置哈希）
- 保留 `collection_name` 字段（但生成逻辑变更）

**1.2 实现 `compute_data_id()` 函数**
- 输入：`List[MealFile]`
- 输出：SHA-256 哈希字符串
- 逻辑：对 PDF 的 SHA-256 指纹排序后拼接，再取哈希

**1.3 实现配置哈希函数**
- `compute_parser_config_hash()`
- `compute_chunker_config_hash()`
- `compute_embedding_config_hash()`
- `compute_index_key()`（组合 data_id + 全链路配置哈希）

**1.4 修改 `generate_collection_name()`**
- 从 `m_{uuid[:8]}` 改为 `m_{index_key[:12]}`
- 集合名现在由数据+配置唯一确定

**1.5 修改 `MealConfig.from_dict()`**
- 兼容旧格式（有 uuid 无 data_id）和 新格式（有 data_id 无 uuid）
- 旧格式加载时自动计算 data_id 并记录警告

### Phase 2：产物存储重构

**2.1 新增 `ArtifactCache` 类**
- 负责管理 `data/artifacts/` 目录
- 提供 `get_parsed_dir(data_id)` → 返回解析产物目录
- 提供 `get_chunks_dir(data_id, chunker_hash)` → 返回分块产物目录
- 提供 `cache_exists(data_id, stage, config_hash)` → 检查缓存是否命中
- 提供 `register_artifact(data_id, stage, config_hash, files)` → 注册产物

**2.2 修改 `parser.py`**
- `parse_all_pdfs()` 新增 `output_dir_override` 参数
- 当套餐模式时，输出到 `artifacts/{data_id}/parsed/` 而非全局 `data/parsed/`
- 非套餐模式行为不变

**2.3 修改 `chunker.py`**
- `process_parsed_files()` 新增 `output_dir_override` 参数
- 当套餐模式时，输出到 `artifacts/{data_id}/chunks_{chunker_hash}/`
- 非套餐模式行为不变

**2.4 修改 `indexer.py`**
- `build_index()` 新增 `chunks_dir_override` 参数
- 从正确的缓存目录读取 chunks
- 集合名使用新的 `m_{index_key[:12]}` 格式

### Phase 3：MealManager 适配

**3.1 修改 `create_meal()`**
- 计算 data_id 替代 UUID
- 保存 config_snapshot 和 config_hashes
- 使用 ArtifactCache 检查缓存命中
- 命中时跳过对应阶段，未命中时执行并缓存

**3.2 修改 `copy_meal()`**
- 保留 data_id（数据相同）
- 可选择是否继承配置（默认继承）
- 共享 Qdrant 集合（因为 data_id + config 相同 → index_key 相同）

**3.3 修改 `repair_meal()`**
- 重新计算 data_id（文件可能变更）
- 重建受影响的缓存层

**3.4 修改 `check_meal_status()`**
- 基于 data_id 检查数据组完整性
- 检查各缓存层是否完整

**3.5 新增 `find_equivalent_meals()`**
- 查找具有相同 data_id 的其他套餐
- 用于展示数据等价关系

### Phase 4：CLI 与展示更新

**4.1 修改 `--list-meals` 输出**
- 显示 data_id（短格式）
- 标注数据等价关系（相同 data_id 的套餐归为一组）
- 显示配置摘要（chunk_size, overlap, embedding model）

**4.2 新增 `--meal-info` 命令**
- 显示套餐详细信息：data_id、配置快照、缓存状态
- 显示与其他套餐的等价关系

**4.3 修改 `--create-meal` 命令**
- 支持 `--config-override` 参数（如 `--config-override chunker.chunk_overlap=50`）
- 创建时显示缓存命中情况

### Phase 5：测试更新

**5.1 更新 `tests/test_meal.py`**
- data_id 计算测试
- 配置哈希计算测试
- 缓存命中/未命中测试
- 数据等价检测测试

**5.2 更新 `tests/test_sampler.py`**
- 适配新的 MealConfig 结构

**5.3 新增 `tests/test_artifact_cache.py`**
- ArtifactCache 类的完整测试

### Phase 6：配置与文档

**6.1 更新 `config.yaml`**
- 新增 `artifacts.dir` 配置项
- 保留 `meals.dir` 和 `meals.collection_prefix`

**6.2 更新开发手记**
- 在 `notes/` 下记录本次重构的设计决策和实施过程

---

## 五、向后兼容与迁移

由于套餐功能刚实现，尚无生产数据，建议：
- **不提供自动迁移脚本**
- 旧格式 manifest 加载时发出警告并提示重新创建
- 删除旧的 `data/meals/` 目录后重新创建套餐

---

## 六、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 短哈希碰撞（data_id[:12]） | 概率极低（2^48 空间），加载时做完整哈希校验 |
| 缓存一致性问题 | 每次使用前校验 PDF 指纹，确保数据未变 |
| 磁盘空间增长 | 后续可添加缓存清理命令（按 LRU 或手动） |
| parser 配置变更导致 parsed 产物失效 | 当前 parser 无可调参数，暂不处理；未来加 parser_config_hash 子目录 |

---

## 七、关于"parser 算法变更"的特别说明

你提到"后面可能更改 PDF 到 markdown 的算法"。对此，我的建议是：

**现阶段**：parser 配置（pymupdf4llm）没有可调参数，所以 `parsed/` 目录不需要按配置版本化。所有使用同一 data_id 的套餐共享同一份解析产物。

**未来**：当引入多种解析算法或解析参数时，只需在 `artifacts/{data_id}/` 下增加 `parsed_{parser_hash}/` 子目录，与 `chunks_{chunker_hash}/` 采用相同的版本化模式。这是一个自然的扩展点，不需要提前实现。
