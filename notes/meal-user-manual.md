# 套餐（Meal）系统使用手册

> 版本：v1.0
> 创建时间：2026-04-16
> 基于 `src/meal.py`、`main.py`、`eval/run_eval.py` 实现

---

## 一、概述

套餐（Meal）系统允许你从全量文档中创建一个**命名的、持久化的数据子集快照**，包含：
- 抽样配置和结果（哪些 PDF 被选中）
- 独立的向量索引（Qdrant collection）
- 关联的测试集（自动生成或手写）

你可以随时通过套餐名称加载对应的数据子集进行问答或评测。

### 核心优势

| 特性 | 说明 |
|------|------|
| **内容寻址** | 相同 PDF 合集 + 相同配置 = 相同索引，天然去重 |
| **缓存复用** | 解析和分块产物按内容哈希存储，避免重复计算 |
| **实验对比** | 同一数据搭配不同配置可创建多个套餐，便于对比 |
| **完整生命周期** | 创建、复制、重命名、修复、删除、状态检查 |

---

## 二、快速开始

### 1. 创建第一个套餐

```bash
# 从 PDF 中随机抽样 10 个文件创建套餐
pixi run python main.py --create-meal small_sample --sample-count 10

# 抽样直到总页数达到 5000 页
pixi run python main.py --create-meal 5k_pages --sample-pages 5000

# 抽样全部 PDF 的 10%
pixi run python main.py --create-meal ten_percent --sample-ratio 0.1
```

### 2. 使用套餐问答

```bash
# 单轮问答
pixi run python main.py --meal small_sample --query "药明康德2024年营收多少？"

# 交互式问答（持续提问直到退出）
pixi run python main.py --meal small_sample
```

### 3. 列出现有套餐

```bash
pixi run python main.py --list-meals
```

输出示例：
```
Name                 DataID         Status              PDFs   Pages   Chunks Config               Created
-------------------------------------------------------------------------------------------------------------------
small_sample         abc123def456   ✅ available           10     523     1847 sz=512 ov=0        2026-04-16T14:30
5k_pages             def456ghi789   ✅ available          100    5000    17234 sz=512 ov=0        2026-04-16T15:00
exp_overlap_50       abc123def456   ✅ available           10     523     2105 sz=512 ov=50       2026-04-16T15:30
  ↳ Same data group (2 meals share data_id=abc123def456)
```

> **注意**：`small_sample` 和 `exp_overlap_50` 共享相同的 `DataID`（数据相同），但配置不同（overlap 不同），所以有独立的向量索引。

---

## 三、完整功能参考

### 3.1 创建套餐

```bash
pixi run python main.py --create-meal [名称] --sample-count|--sample-pages|--sample-ratio [值] [选项]
```

**参数**：

| 参数 | 说明 | 必需 |
|------|------|------|
| `--create-meal [名称]` | 套餐名称（可省略，自动生成时间戳名称） | 可选 |
| `--sample-count N` | 抽样 N 个 PDF 文件 | 三选一 |
| `--sample-pages N` | 抽样直到总页数达到 N | 三选一 |
| `--sample-ratio R` | 抽样比例（0.0-1.0） | 三选一 |
| `--seed N` | 随机种子（确保可复现） | 可选 |
| `--force-parse` | 强制重新解析 PDF | 可选 |
| `--config path` | 配置文件路径 | 可选 |

**示例**：
```bash
# 自动命名
pixi run python main.py --create-meal --sample-count 10

# 指定随机种子确保可复现
pixi run python main.py --create-meal repro_exp --sample-count 10 --seed 42
```

**缓存行为**：
- 首次创建：解析 → 分块 → 建索引
- 相同数据 + 相同配置：全部缓存命中，秒级完成
- 相同数据 + 不同配置：解析缓存命中，重新分块和建索引
- 不同数据：全部重新执行

### 3.2 查看套餐

```bash
# 列出所有套餐
pixi run python main.py --list-meals

# 查看套餐详细信息
pixi run python main.py --meal-info small_sample
```

**`--meal-info` 输出包含**：
- 套餐基本信息（名称、Data ID、集合名、创建时间）
- 配置快照（parser、chunker、embedding、retrieval）
- 配置哈希（各阶段短哈希）
- 统计信息（PDF 数、页数、chunk 数）
- PDF 文件列表（含 SHA-256 校验和状态图标）
- 问题列表（缺失/变更的文件）
- 等价套餐列表（相同 data_id 的其他套餐）

### 3.3 使用套餐问答

```bash
# 单轮问答
pixi run python main.py --meal small_sample --query "你的问题"

# 交互式问答
pixi run python main.py --meal small_sample
```

**交互式模式**：
```
Interactive Q&A mode (meal: small_sample)
Type your question, or 'quit'/'exit'/'q' to exit.

Q> 药明康德2024年营收多少？
A: 药明康德2024年营业收入为...

  Sources:
    1. annual_reports/2024/药明康德/2024年年度报告.pdf (0.8234)

Q> quit
Exiting.
```

### 3.4 管理套餐

**重命名**：
```bash
pixi run python main.py --rename-meal old_name new_name
```

**复制**（浅拷贝，共享向量索引）：
```bash
pixi run python main.py --copy-meal source_meal target_meal
```

**删除**：
```bash
pixi run python main.py --delete-meal small_sample
```

> **注意**：如果向量索引被其他套餐共享，则仅删除套餐元数据，保留索引。

### 3.5 修复套餐

当套餐中的 PDF 文件缺失或变更时：

```bash
pixi run python main.py --repair-meal small_sample
```

**交互式修复流程**：
1. 显示文件状态检查（✅ 存在 / ❌ 缺失 / ⚠️ SHA256 变更）
2. 选择修复选项：
   - 选项 1：为缺失/变更的文件指定替代路径
   - 选项 2：跳过问题文件（仅保留可用文件）
   - 选项 3：取消修复
3. 选择修复模式：
   - 模式 1：创建新套餐（保留原套餐，新 data_id）
   - 模式 2：就地修复（更新当前套餐，data_id 变更）

### 3.6 生成测试集

```bash
pixi run python main.py --generate-test-set small_sample [选项]
```

**参数**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--strategy` | 生成策略（factual/boundary/multi_hop） | factual |
| `--num-questions N` | 生成问题数量 | 20 |
| `--llm-preset` | LLM 预设（default/opus/sonnet/haiku） | default |
| `--seed N` | 随机种子 | 可选 |

**策略说明**：

| 策略 | 描述 | 难度 | Chunk 选择 |
|------|------|------|-----------|
| `factual` | 基于单个 chunk 生成可回答的事实性问题 | easy | 随机选 1 个 |
| `boundary` | 生成需要跨越 chunk 边界才能回答的问题 | medium | 选相邻 2 个 |
| `multi_hop` | 生成需要综合多段信息的复杂问题 | hard | 选不相邻 2 个 |

**示例**：
```bash
# 生成 20 个事实性问题
pixi run python main.py --generate-test-set small_sample --strategy factual --num-questions 20

# 生成 10 个边界测试问题
pixi run python main.py --generate-test-set small_sample --strategy boundary --num-questions 10

# 使用 opus 模型生成高质量问题
pixi run python main.py --generate-test-set small_sample --strategy multi_hop --num-questions 5 --llm-preset opus
```

生成的测试集保存在 `data/meals/{name}/test_sets/auto_{strategy}.json`

### 3.7 评测

```bash
# 使用全量测试集评测
pixi run python python eval/run_eval.py --test-data eval/test_data.json

# 使用套餐的第一个测试集评测
pixi run python eval/run_eval.py --meal small_sample

# 指定测试集评测
pixi run python eval/run_eval.py --meal small_sample --test-set auto_factual

# 指定测试集 + 构建索引
pixi run python eval/run_eval.py --meal small_sample --test-set auto_boundary --build-index
```

**评测报告保存位置**：
- 全量评测：`data/eval/baseline_report.json`
- 套餐评测：`data/meals/{name}/baseline_report.json`

---

## 四、数据模型

### 4.1 目录结构

```
data/
├── raw/                          # 源 PDF 文件
├── artifacts/                    # 内容寻址产物缓存
│   └── abc123def456/             # 数据组目录（data_id 前 12 位）
│       ├── parsed/               # 解析产物（Markdown）
│       ├── chunks_c5d6e7f8/      # 分块产物（chunker 哈希）
│       └── manifest.json         # 数据组元信息
├── vector_store/                 # Qdrant 向量存储
│   └── collections:
│       ├── financial_reports     # 默认全量索引
│       └── m_a1b2c3d4e5f6        # 套餐索引（m_{index_key[:12]}）
├── meals/                        # 套餐元数据
│   └── small_sample/
│       ├── manifest.json         # 套餐配置
│       └── test_sets/
│           └── auto_factual.json # 测试集
├── parsed/                       # 全局解析产物（非套餐模式）
└── chunks/                       # 全局分块产物（非套餐模式）
```

### 4.2 身份模型

```
PDF SHA-256 列表排序 → data_id
data_id + parser_config_hash → 解析产物路径
parse_key + chunker_config_hash → 分块产物路径
chunk_key + embedding_config_hash → index_key
index_key → Qdrant collection 名称 (m_{index_key[:12]})
```

**关键原则**：
- 相同 PDF 合集 = 相同 `data_id`
- 相同 `data_id` + 相同配置 = 相同产物（缓存命中）
- 相同 `data_id` + 不同配置 = 共享解析产物，独立分块/索引

### 4.3 manifest.json 格式

```json
{
  "data_id": "abc123...",
  "name": "small_sample",
  "created_at": "2026-04-16T14:30:00",
  "sampling_config": {
    "mode": "count",
    "value": 10,
    "seed": 42
  },
  "collection_name": "m_a1b2c3d4e5f6",
  "pdf_files": [
    {
      "path": "annual_reports/2024/药明康德/2024年年度报告.pdf",
      "sha256": "...",
      "size_bytes": 123456
    }
  ],
  "config_snapshot": {
    "parser": {"algorithm": "pymupdf4llm", "input_dir": "data/raw"},
    "chunker": {"chunk_size": 512, "chunk_overlap": 0, "encoding": "cl100k_base"},
    "embedding": {"model_name": "BAAI/bge-large-zh-v1.5", "device": "cuda"},
    "retrieval": {"top_k": 5}
  },
  "config_hashes": {
    "parser": "a1b2c3d4",
    "chunker": "e5f6a7b8",
    "embedding": "c9d0e1f2"
  },
  "stats": {
    "total_pdfs": 10,
    "total_pages": 523,
    "total_chunks": 1847,
    "cache_hit_parse": true,
    "cache_hit_chunk": false
  }
}
```

---

## 五、典型使用场景

### 场景 1：同一数据，不同 chunk 配置对比

```bash
# 创建 baseline（overlap=0）
pixi run python main.py --create-meal baseline --sample-count 10 --seed 42

# 创建 overlap=50 的套餐（共享解析产物，独立分块）
pixi run python main.py --create-meal overlap_50 --sample-count 10 --seed 42
# 修改 config.yaml 中 chunk_overlap=50 后执行
```

### 场景 2：不同数据规模对比

```bash
# 小样本
pixi run python main.py --create-meal small --sample-count 10 --seed 42

# 中样本
pixi run python main.py --create-meal medium --sample-count 50 --seed 42

# 大样本
pixi run python main.py --create-meal large --sample-count 200 --seed 42

# 分别评测
pixi run python eval/run_eval.py --meal small
pixi run python eval/run_eval.py --meal medium
pixi run python eval/run_eval.py --meal large
```

### 场景 3：同一数据 + 同一配置，不同测试集

```bash
# 创建套餐
pixi run python main.py --create-meal exp --sample-count 10 --seed 42

# 生成多种测试集
pixi run python main.py --generate-test-set exp --strategy factual --num-questions 20
pixi run python main.py --generate-test-set exp --strategy boundary --num-questions 10
pixi run python main.py --generate-test-set exp --strategy multi_hop --num-questions 5
```

---

## 六、配置参考

### config.yaml 中的相关配置

```yaml
meals:
  dir: "data/meals"              # 套餐存储目录
  collection_prefix: "m_"        # Qdrant 集合名前缀

artifacts:
  dir: "data/artifacts"          # 内容寻址产物缓存目录

test_generation:
  default_strategy: "factual"    # 默认生成策略
  default_num_questions: 20      # 默认问题数量
  max_retries: 3                 # LLM 生成单条问答对的最大重试次数
```

---

## 七、命令速查表

| 命令 | 说明 |
|------|------|
| `--create-meal [名称] --sample-count N` | 创建套餐（抽样 N 个 PDF） |
| `--create-meal [名称] --sample-pages N` | 创建套餐（抽样到 N 页） |
| `--create-meal [名称] --sample-ratio R` | 创建套餐（抽样比例 R） |
| `--list-meals` | 列出所有套餐 |
| `--meal-info 名称` | 查看套餐详细信息 |
| `--meal 名称 --query "问题"` | 单轮问答 |
| `--meal 名称` | 交互式问答 |
| `--rename-meal 旧名 新名` | 重命名套餐 |
| `--copy-meal 源 目标` | 复制套餐 |
| `--delete-meal 名称` | 删除套餐 |
| `--repair-meal 名称` | 修复套餐 |
| `--generate-test-set 名称` | 生成测试集 |
| `--strategy 策略` | 指定测试集生成策略 |
| `--num-questions N` | 指定生成问题数量 |
| `--seed N` | 指定随机种子 |

---

## 八、注意事项

1. **套餐名限制**：仅允许字母、数字、下划线、连字符（如 `small_sample`、`5k-pages`）
2. **随机种子**：同一 `--seed` 值确保抽样结果可复现
3. **磁盘空间**：每个独立配置对应一个 Qdrant collection，会占用额外空间
4. **PDF 变更检测**：`--list-meals` 和 `--meal-info` 会显示文件 SHA-256 校验状态
5. **缓存共享**：相同 data_id 的套餐共享解析产物，节省磁盘空间
