# 套餐（Meal）功能实施计划

## 问题分析

当前抽样功能的局限：

1. **抽样结果不持久**：`--sample-count/pages/ratio` 仅在 `build_index` 阶段生效，抽样后的向量索引覆盖默认的 `financial_reports` collection，无法保留，也无法后续基于该抽样进行问答
2. **无法基于抽样做问答**：抽样 → 建索引后就结束了，没有 `--query` 或交互式问答的入口
3. **测试集与抽样不匹配**：手写的 `test_data.json` 引用特定文档（如贵州茅台），若该文档未被抽中则测试无效
4. **抽样规模无法作为实验变量**：无法方便地对比不同数据规模下 RAG 系统的效果差异

## 解决方案概述

引入 **"套餐"（Meal）** 概念——一个命名的、持久化的数据子集快照，包含：

* 抽样配置和结果（哪些 PDF 被选中）

* 独立的向量索引（Qdrant collection）

* 关联的测试集（自动生成或手写）

用户可以随时通过套餐名称加载对应的数据子集进行问答或评测。

### 核心数据流

```
创建套餐：
  python main.py --create-meal small_sample --sample-count 10
    → 抽样 10 个 PDF → 解析 → 分块 → 索引到 Qdrant collection "meal_small_sample"
    → 保存 manifest.json 到 data/meals/small_sample/

使用套餐问答：
  python main.py --meal small_sample --query "药明康德2024年营收多少？"
    → 加载套餐 → 使用 collection "meal_small_sample" 检索 → 生成回答

交互式问答：
  python main.py --meal small_sample
    → 进入交互循环，持续问答

生成测试集：
  python main.py --generate-test-set small_sample --strategy factual --num-questions 20
    → 从套餐的 chunks 中选取 → LLM 生成问答对 → 保存到 data/meals/small_sample/test_sets/

基于套餐评测：
  python eval/run_eval.py --meal small_sample --test-set auto_factual
    → 加载套餐和测试集 → 运行评测 → 输出报告
```

***

## 数据模型

### 套餐目录结构

```
data/meals/
├── small_sample/
│   ├── manifest.json              # 套餐元数据
│   └── test_sets/
│       ├── auto_factual.json      # 自动生成的事实性测试集
│       ├── auto_boundary.json     # 自动生成的边界测试集
│       └── manual_v1.json         # 手写测试集
├── 5k_pages/
│   ├── manifest.json
│   └── test_sets/
│       └── ...
```

### manifest.json 格式

```json
{
  "name": "small_sample",
  "created_at": "2026-04-16T14:30:00",
  "sampling_config": {
    "mode": "count",
    "value": 10
  },
  "pdf_files": [
    "annual_reports/2024/药明康德/2024年年度报告.pdf",
    "research_reports/半导体行业3月份月报.pdf"
  ],
  "collection_name": "meal_small_sample",
  "stats": {
    "total_pdfs": 10,
    "total_pages": 523,
    "total_chunks": 1847
  }
}
```

### 测试集 JSON 格式

```json
{
  "name": "auto_factual",
  "meal_name": "small_sample",
  "strategy": "factual",
  "created_at": "2026-04-16T14:35:00",
  "generation_config": {
    "num_questions": 20,
    "llm_preset": "default"
  },
  "questions": [
    {
      "id": "q001",
      "question": "药明康德2024年的营业收入是多少？",
      "expected_answer": "药明康德2024年营业收入为XXX亿元。",
      "category": "factual",
      "source_chunks": ["2024年年度报告_042"],
      "source_files": ["annual_reports/2024/药明康德/2024年年度报告.pdf"],
      "difficulty": "easy"
    }
  ]
}
```

### 向量存储策略

套餐的向量数据存储在**同一个 Qdrant 实例**中，使用不同的 collection name 隔离：

| 用途                | Collection Name     | 说明                 |
| ----------------- | ------------------- | ------------------ |
| 默认全量索引            | `financial_reports` | config.yaml 中的默认值  |
| 套餐 `small_sample` | `meal_small_sample` | 命名规则：`meal_{name}` |
| 套餐 `5k_pages`     | `meal_5k_pages`     | 同上                 |

**优势**：

* 无需复制 `data/parsed/` 和 `data/chunks/`（共享中间产物）

* Qdrant 原生支持多 collection，无额外依赖

* 套餐之间完全隔离，互不干扰

* 默认全量索引不受影响

***

## 实施步骤

### Step 1: 创建 `src/meal.py` — 套餐管理模块

新建套餐生命周期管理模块，包含：

**`MealConfig`** **dataclass**：

* `name: str` — 套餐名称

* `created_at: str` — 创建时间

* `sampling_config: Optional[SamplingConfig]` — 抽样配置

* `pdf_files: List[str]` — 抽中的 PDF 相对路径列表

* `collection_name: str` — 对应的 Qdrant collection 名

* `stats: Dict[str, Any]` — 统计信息（PDF 数、页数、chunk 数）

**`MealManager`** **类**：

```python
class MealManager:
    def __init__(self, config: Dict[str, Any])

    def create_meal(
        self,
        name: str,
        sampling_config: SamplingConfig,
        force_parse: bool = False,
    ) -> MealConfig
    # 流程：抽样 → 解析 → 分块 → 索引(到 meal collection) → 保存 manifest

    def load_meal(self, name: str) -> MealConfig
    # 从 manifest.json 加载套餐元数据

    def list_meals(self) -> List[MealConfig]
    # 扫描 data/meals/ 下所有套餐

    def delete_meal(self, name: str) -> None
    # 删除套餐目录 + 删除对应 Qdrant collection

    def meal_exists(self, name: str) -> bool

    def get_meal_dir(self, name: str) -> Path
    # 返回 data/meals/{name}/

    def get_collection_name(self, name: str) -> str
    # 返回 "meal_{name}"
```

**`create_meal`** **详细流程**：

1. 校验套餐名（不含特殊字符、不与已有套餐重名）
2. 调用 `determine_sample()` 确定抽样文件列表
3. 统计抽样 PDF 的总页数（复用 `count_pdf_pages`）
4. 调用 `parse_all_pdfs(pdf_files=sampled_pdfs)` 解析
5. 构建 `source_filter_md`，调用 `process_parsed_files(source_filter=...)` 分块
6. 构建 `source_filter_jsonl`，调用 `indexer.build_index(source_filter=..., collection_name=meal_collection_name)` 索引
7. 统计 chunk 总数
8. 保存 `manifest.json`
9. 创建 `test_sets/` 空目录

**关键设计**：`create_meal` 需要创建一个使用套餐 collection name 的 `VectorIndexer` 实例，而非使用 pipeline 默认的 indexer。因此 `MealManager` 需要接收或创建 `Embedder` 和 `VectorIndexer`。

### Step 2: 修改 `src/pipeline.py` — 支持套餐查询

**修改** **`RAGPipeline.__init__`**：

* 新增 `meal_name: Optional[str] = None` 参数

* 当 `meal_name` 不为 None 时，使用 `meal_{meal_name}` 作为 collection\_name 初始化 indexer 和 retriever

* 加载套餐 manifest 验证套餐存在

**新增** **`use_meal`** **方法**：

```python
def use_meal(self, meal_name: str) -> None
# 重新初始化 indexer 和 retriever，使用套餐的 collection name
```

**修改** **`build_index`**：

* 新增 `collection_name: Optional[str] = None` 参数

* 当 `collection_name` 不为 None 时，创建临时 indexer 使用该 collection name

* 这样 `MealManager.create_meal()` 可以复用 pipeline 的解析和分块逻辑，但指定不同的 collection

### Step 3: 创建 `src/test_generator.py` — 测试集生成模块

**`TestSetConfig`** **dataclass**：

* `strategy: str` — 生成策略（"factual" / "boundary" / "multi\_hop"）

* `num_questions: int` — 生成问题数量

* `llm_preset: str` — 使用的 LLM 预设

**`TestSetGenerator`** **类**：

```python
class TestSetGenerator:
    def __init__(self, config: Dict[str, Any])

    def generate_test_set(
        self,
        meal_name: str,
        strategy: str = "factual",
        num_questions: int = 20,
        llm_preset: str = "default",
    ) -> Dict[str, Any]

    def _load_meal_chunks(self, meal_config: MealConfig) -> List[Dict[str, Any]]
    # 从 data/chunks/ 加载套餐对应的 chunk 数据

    def _group_chunks_by_source(self, chunks: List[Dict]) -> Dict[str, List[Dict]]
    # 按源文件分组

    def _select_chunks_for_factual(
        self, grouped_chunks: Dict[str, List[Dict]], num_questions: int
    ) -> List[List[Dict]]
    # 随机选取单个 chunk

    def _select_chunks_for_boundary(
        self, grouped_chunks: Dict[str, List[Dict]], num_questions: int
    ) -> List[List[Dict]]
    # 选取同一源文件中相邻的 chunk 对

    def _select_chunks_for_multi_hop(
        self, grouped_chunks: Dict[str, List[Dict]], num_questions: int
    ) -> List[List[Dict]]
    # 选取同一源文件中不相邻的多个 chunk

    def _generate_question_with_llm(
        self, chunks: List[Dict], strategy: str, generator: Generator
    ) -> Optional[Dict[str, Any]]
    # 调用 LLM 生成单个问答对

    def _save_test_set(
        self, meal_name: str, test_set: Dict[str, Any], filename: str
    ) -> Path
    # 保存测试集到 data/meals/{name}/test_sets/{filename}.json
```

**三种生成策略**：

| 策略          | Chunk 选择方式             | Prompt 要点            | 难度     |
| ----------- | ---------------------- | -------------------- | ------ |
| `factual`   | 随机选 1 个 chunk          | 基于文本生成可回答的事实性问题      | easy   |
| `boundary`  | 选同一文档中相邻 2 个 chunk     | 生成需要跨越 chunk 边界信息的问题 | medium |
| `multi_hop` | 选同一文档中不相邻的 2-3 个 chunk | 生成需要综合多段信息的问题        | hard   |

**LLM Prompt 模板**（factual 策略示例）：

```
你是一个金融研报问答系统的测试工程师。请根据以下文本片段，生成一个可以用该文本直接回答的事实性问题。

要求：
1. 问题必须能用提供的文本完全回答
2. 问题应该具体、明确，避免过于宽泛
3. 答案应该简洁准确，直接引用文本中的关键数据或结论
4. 不要生成需要外部知识才能回答的问题

文本片段：
---
{chunk_text}
---

请严格以以下JSON格式输出（不要输出其他内容）：
{"question": "你的问题", "answer": "期望的答案", "difficulty": "easy"}
```

**boundary 策略 Prompt**：

```
你是一个金融研报问答系统的测试工程师。以下两个文本片段是同一份文档中相邻的部分。请注意，重要信息可能恰好被分割在两个片段之间。

请生成一个需要同时参考两个片段才能完整回答的问题。这个问题应该测试系统在信息被 chunk 边界切断时的检索和回答能力。

片段1：
---
{chunk1_text}
---

片段2：
---
{chunk2_text}
---

请严格以以下JSON格式输出（不要输出其他内容）：
{"question": "你的问题", "answer": "期望的答案", "difficulty": "medium"}
```

**multi\_hop 策略 Prompt**：

```
你是一个金融研报问答系统的测试工程师。以下文本片段来自同一份文档的不同部分。请生成一个需要综合多个片段中的信息才能回答的复杂问题。

要求：
1. 问题不能仅凭单个片段回答
2. 需要对比、综合或推理多个片段的信息
3. 答案应明确指出信息来自哪些片段

片段：
---
{chunk_texts}
---

请严格以以下JSON格式输出（不要输出其他内容）：
{"question": "你的问题", "answer": "期望的答案", "difficulty": "hard"}
```

**生成流程**：

1. 加载套餐 manifest → 获取 PDF 文件列表
2. 从 `data/chunks/` 加载对应的 chunk 数据（通过 source\_filter）
3. 按源文件分组
4. 根据策略选取 chunk 组合
5. 逐个调用 LLM 生成问答对（带重试机制，最多 3 次）
6. 解析 LLM 返回的 JSON，校验格式
7. 保存测试集到套餐目录

### Step 4: 修改 `main.py` — 扩展 CLI

**新增参数**：

| 参数                    | 类型   | 说明                                              |
| --------------------- | ---- | ----------------------------------------------- |
| `--create-meal`       | str  | 创建套餐（需配合 --sample-count/pages/ratio）            |
| `--meal`              | str  | 使用指定套餐进行问答                                      |
| `--list-meals`        | flag | 列出所有套餐                                          |
| `--delete-meal`       | str  | 删除指定套餐                                          |
| `--generate-test-set` | str  | 为指定套餐生成测试集                                      |
| `--strategy`          | str  | 测试集生成策略（factual/boundary/multi\_hop，默认 factual） |
| `--num-questions`     | int  | 生成问题数量（默认 20）                                   |

**使用示例**：

```bash
# 创建套餐
python main.py --create-meal small_sample --sample-count 10
python main.py --create-meal 5k_pages --sample-pages 5000
python main.py --create-meal ten_percent --sample-ratio 0.1

# 列出套餐
python main.py --list-meals

# 使用套餐进行单轮问答
python main.py --meal small_sample --query "药明康德2024年营收多少？"

# 使用套餐进入交互式问答
python main.py --meal small_sample

# 生成测试集
python main.py --generate-test-set small_sample --strategy factual --num-questions 20
python main.py --generate-test-set small_sample --strategy boundary --num-questions 10

# 删除套餐
python main.py --delete-meal small_sample
```

**交互式问答模式**：

* 当指定 `--meal` 但不指定 `--query` 时，进入交互循环

* 用户输入问题，系统返回回答，输入 `quit` / `exit` / `q` 退出

* 每次回答后显示来源和相关性分数

### Step 5: 修改 `eval/run_eval.py` — 支持套餐评测

**新增参数**：

| 参数           | 类型  | 说明                                 |
| ------------ | --- | ---------------------------------- |
| `--meal`     | str | 使用指定套餐进行评测                         |
| `--test-set` | str | 指定测试集名称（不含 .json 后缀），默认使用套餐的第一个测试集 |

**修改** **`run_evaluation`** **函数**：

* 当指定 `--meal` 时，从套餐目录加载测试集

* pipeline 使用套餐的 collection name

* 评测报告保存到 `data/meals/{name}/` 目录下（而非 `data/eval/`）

**使用示例**：

```bash
# 使用套餐的自动生成测试集评测
python eval/run_eval.py --meal small_sample

# 指定测试集评测
python eval/run_eval.py --meal small_sample --test-set auto_factual

# 仍支持原有的全量评测方式
python eval/run_eval.py --test-data eval/test_data.json
```

### Step 6: 修改 `config.yaml`

新增套餐相关配置：

```yaml
meals:
  dir: "data/meals"           # 套餐存储目录
  collection_prefix: "meal_"  # collection name 前缀

test_generation:
  default_strategy: "factual"
  default_num_questions: 20
  max_retries: 3              # LLM 生成单条问答对的最大重试次数
```

### Step 7: 添加测试

**新建** **`tests/test_meal.py`**：

* 测试 `MealConfig` dataclass 创建和序列化

* 测试 `MealManager.create_meal()`（mock sampler、parser、chunker、indexer）

* 测试 `MealManager.load_meal()`

* 测试 `MealManager.list_meals()`

* 测试 `MealManager.delete_meal()`

* 测试套餐名校验（特殊字符、重名）

* 测试 collection name 生成规则

**新建** **`tests/test_test_generator.py`**：

* 测试 chunk 加载和分组

* 测试三种策略的 chunk 选择逻辑

* 测试 LLM 生成问答对（mock Generator）

* 测试 JSON 解析和校验

* 测试测试集保存和加载

* 测试边界条件（空 chunks、num\_questions 大于可用 chunks 等）

**更新** **`tests/test_pipeline.py`**（如存在）：

* 测试 `use_meal()` 方法

* 测试 `meal_name` 参数初始化

***

## 涉及文件清单

| 文件                             | 操作     | 说明                                                               |
| ------------------------------ | ------ | ---------------------------------------------------------------- |
| `src/meal.py`                  | **新建** | 套餐管理模块（MealConfig、MealManager）                                   |
| `src/test_generator.py`        | **新建** | 测试集生成模块（TestSetGenerator）                                        |
| `src/pipeline.py`              | **修改** | 新增 meal\_name 参数、use\_meal() 方法、build\_index 支持 collection\_name |
| `main.py`                      | **修改** | 新增套餐相关 CLI 参数、交互式问答模式                                            |
| `eval/run_eval.py`             | **修改** | 新增 --meal、--test-set 参数，支持套餐评测                                   |
| `config.yaml`                  | **修改** | 新增 meals 和 test\_generation 配置段                                  |
| `tests/test_meal.py`           | **新建** | 套餐管理模块测试                                                         |
| `tests/test_test_generator.py` | **新建** | 测试集生成模块测试                                                        |

***

## 实施优先级

1. **P0 — 套餐持久化与查询**（Step 1 + Step 2 + Step 4 部分 + Step 6）

   * 创建 `src/meal.py`

   * 修改 `src/pipeline.py`

   * 修改 `main.py`（创建/列表/删除/查询套餐）

   * 修改 `config.yaml`

   * 这是核心功能，必须先完成

2. **P1 — 交互式问答**（Step 4 部分）

   * `python main.py --meal xxx` 进入交互循环

   * 依赖 P0

3. **P2 — 测试集自动生成**（Step 3 + Step 4 部分）

   * 创建 `src/test_generator.py`

   * 修改 `main.py`（--generate-test-set）

   * factual 和 boundary 策略优先，multi\_hop 作为进阶

4. **P3 — 套餐评测集成**（Step 5）

   * 修改 `eval/run_eval.py`

   * 依赖 P0 + P2

5. **P4 — 测试**（Step 7）

   * 随各步骤同步编写，TDD 方式

***

## 风险与注意事项

1. **Qdrant 多 collection 管理**：同一 persist\_dir 下多个 collection 共存，需确保 collection name 不冲突。套餐名需限制为合法的 collection name 字符（字母、数字、下划线）。

2. **LLM 生成质量**：自动生成的测试集质量取决于 LLM 能力，可能存在：

   * 生成的问题过于简单或与文本无关

   * JSON 格式不规范导致解析失败

   * 需要重试机制和人工审核入口

3. **磁盘空间**：每个套餐对应一个 Qdrant collection，会占用额外磁盘空间。应提供 `--delete-meal` 清理不需要的套餐。

4. **抽样随机性**：同一抽样配置多次执行会产生不同结果。套餐通过 manifest 记录具体抽中了哪些文件，确保可复现。若要完全复现，需支持 random seed（可作为后续优化）。

5. **parsed/chunks 共享**：套餐与全量索引共享 `data/parsed/` 和 `data/chunks/` 目录。如果删除这些目录中的文件，套餐的向量索引不受影响（已持久化在 Qdrant 中），但重新构建套餐时需要重新解析和分块。

