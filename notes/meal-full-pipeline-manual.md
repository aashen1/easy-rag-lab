# RAG 套餐系统 + 问题生成 + 评测系统 — 全链路使用手册

> 版本：v1.0
> 创建时间：2026-04-16
> 适用对象：开发人员、评测人员

---

## 一、系统概述

本 RAG 系统包含三个核心子系统，形成完整的**实验-评测闭环**：

```
[1] 套餐系统 (Meal)  →  [2] 问题生成系统 (Test Generator)  →  [3] 评测系统 (Evaluation)
  创建数据子集快照        LLM 自动生成测试问答对               自动跑评测、输出量化报告
  - 内容寻址去重           - 三种难度策略                      - Hit Rate / MRR / NDCG
  - 缓存复用               - Prompt 模板定制                    - 结构化 JSON 报告
  - 独立向量索引           - 容错重试机制                       - 多套餐对比
```

### 核心工作流

1. **创建套餐**：从全量 PDF 中抽样，创建命名快照（包含独立的向量索引）
2. **生成测试集**：LLM 阅读文档片段，自动生成覆盖不同难度的问答对
3. **运行评测**：用测试集提问，对比检索结果与预期来源，输出量化指标
4. **对比分析**：多次实验，对比不同数据规模、不同配置的评测结果

---

## 二、前置准备

### 2.1 环境

```bash
# 确认 pixi 环境正常
pixi run python --version

# 确认 PDF 文件就位
ls data/raw/
```

### 2.2 配置文件

所有超参数在 `config.yaml` 中管理。评测相关配置：

```yaml
# 套餐存储
meals:
  dir: "data/meals"
  collection_prefix: "m_"

# 产物缓存
artifacts:
  dir: "data/artifacts"

# 测试集生成
test_generation:
  default_strategy: "factual"     # 默认策略
  default_num_questions: 20       # 默认问题数
  max_retries: 3                  # LLM 生成重试次数
```

---

## 三、第一步：创建套餐

套餐是从全量 PDF 中抽样的**持久化快照**，包含选中的文件列表、向量索引、配置快照。

### 3.1 三种抽样模式

| 模式 | 参数 | 适用场景 |
|------|------|----------|
| 固定数量 | `--sample-count N` | 抽取 N 个 PDF |
| 页数上限 | `--sample-pages N` | 抽样直到总页数达到 N |
| 比例抽样 | `--sample-ratio R` | 抽样比例 0.0-1.0 |

### 3.2 创建示例

```bash
# 示例1：抽 10 个 PDF，命名为 small
pixi run python main.py --create-meal small --sample-count 10

# 示例2：抽 5% 的 PDF，命名为 test1
pixi run python main.py --create-meal test1 --sample-ratio 0.05

# 示例3：抽样直到总页数 5000，命名为 medium
pixi run python main.py --create-meal medium --sample-pages 5000

# 示例4：自动命名（生成时间戳名称）
pixi run python main.py --create-meal --sample-count 10
```

### 3.3 可选参数

| 参数 | 说明 |
|------|------|
| `--seed N` | 随机种子，确保抽样可复现 |
| `--force-parse` | 强制重新解析 PDF（忽略缓存） |
| `--config path` | 指定配置文件路径 |

### 3.4 创建结果

```
Meal 'test1' created [e0bb1cb3d28a]
  - 11 PDFs
  - 625 pages
  - 1080 chunks
  - Collection: m_0a089058544d
  - Status: available
```

### 3.5 查看套餐

```bash
# 列表
pixi run python main.py --list-meals

# 详情
pixi run python main.py --meal-info test1
```

**`--list-meals` 输出说明**：

| 列 | 含义 |
|----|------|
| Name | 套餐名称 |
| DataID | 数据指纹（PDF 合集的 SHA-256） |
| Status | 状态（available / files_changed / missing） |
| PDFs | 文件数量 |
| Pages | 总页数 |
| Chunks | 分块数量 |
| Config | 配置简写（chunk size / overlap） |
| Created | 创建时间 |

---

## 四、第二步：使用套餐问答

### 4.1 单轮问答

```bash
pixi run python main.py --meal test1 --query "药明康德2024年营收多少？"
```

### 4.2 交互式问答

```bash
pixi run python main.py --meal test1
```

交互模式会持续等待输入，直到输入 `quit` / `exit` / `q`：

```
Interactive Q&A mode (meal: test1)
Type your question, or 'quit'/'exit'/'q' to exit.

Q> 药明康德2024年营收多少？
A: 药明康德2024年营业收入为...

  Sources:
    1. annual_reports/2024/药明康德/2024年年度报告.pdf (0.8234)
    2. research_reports/医药行业周报.pdf (0.7156)

Q> quit
Exiting.
```

---

## 五、第三步：生成测试集

测试集由 LLM 自动生成。系统会阅读套餐中的文档片段（chunk），针对每个片段生成一个问题。

### 5.1 三种策略

| 策略 | 难度 | 说明 | 适用场景 |
|------|------|------|----------|
| `factual` | easy | 基于单个 chunk 生成事实性问题 | 基础检索能力评估 |
| `boundary` | medium | 生成需要跨越 chunk 边界回答的问题 | 测试边界信息检索 |
| `multi_hop` | hard | 生成需要综合多段信息的问题 | 测试多跳推理能力 |

### 5.2 生成命令

```bash
pixi run python main.py --generate-test-set test1 [选项]
```

**参数**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--strategy` | 生成策略 | factual |
| `--num-questions N` | 问题数量 | 20 |
| `--llm-preset` | LLM 模型 | default |
| `--seed N` | 随机种子 | 无 |

### 5.3 生成示例

```bash
# 生成 20 个事实性问题
pixi run python main.py --generate-test-set test1 --strategy factual --num-questions 20

# 生成 10 个边界测试问题
pixi run python main.py --generate-test-set test1 --strategy boundary --num-questions 10

# 生成 5 个多跳推理问题（使用更强模型）
pixi run python main.py --generate-test-set test1 --strategy multi_hop --num-questions 5 --llm-preset opus
```

### 5.4 生成结果

测试集保存在 `data/meals/{name}/test_sets/auto_{strategy}.json`

每个测试集文件结构：

```json
{
  "name": "auto_factual",
  "meal_data_id": "e0bb1cb3d28a...",
  "meal_name": "test1",
  "strategy": "factual",
  "created_at": "2026-04-16T19:15:38.251165",
  "generation_config": {
    "num_questions": 20,
    "llm_preset": "default",
    "seed": null
  },
  "questions": [
    {
      "question": "以有源耦合为例，封装工序可以分为多少步？",
      "answer": "6步",
      "difficulty": "easy",
      "id": "q001",
      "source_chunks": ["光模块设备行业深度_028"],
      "source_files": ["research_reports\\光模块设备行业深度.md"],
      "category": "factual"
    }
  ]
}
```

**字段说明**：

| 字段 | 含义 |
|------|------|
| `question` | LLM 生成的问题 |
| `answer` | 期望答案（基于原文） |
| `difficulty` | 难度等级 |
| `source_chunks` | 问题涉及的 chunk ID |
| `source_files` | 问题来源的 PDF 文件路径 |
| `category` | 策略类别 |

---

## 六、第四步：运行评测

评测脚本会自动加载套餐、读取测试集、逐个提问、计算指标。

### 6.1 基本命令

```bash
pixi run python eval/run_eval.py --meal test1
```

这会自动：
1. 加载套餐 `test1`
2. 找到第一个测试集（按文件名排序）
3. 逐条提问并计算检索指标
4. 保存报告到 `data/meals/test1/baseline_report.json`

### 6.2 指定测试集

```bash
# 使用 factual 测试集
pixi run python eval/run_eval.py --meal test1 --test-set auto_factual

# 使用 boundary 测试集
pixi run python eval/run_eval.py --meal test1 --test-set auto_boundary

# 使用 multi_hop 测试集
pixi run python eval/run_eval.py --meal test1 --test-set auto_multi_hop
```

### 6.3 评测指标

| 指标 | 全称 | 说明 | 取值范围 |
|------|------|------|----------|
| **Hit Rate** | 命中率 | 检索到的来源中有多少是预期的 | 0.0 - 1.0 |
| **MRR** | Mean Reciprocal Rank | 第一个正确来源的排名倒数的平均值 | 0.0 - 1.0 |
| **NDCG** | Normalized Discounted Cumulative Gain | 考虑排序位置的检索质量 | 0.0 - ~2.3 |

**指标解读**：
- **Hit Rate = 1.0**：所有预期来源都被检索到
- **MRR = 1.0**：所有问题的第一个正确来源都在检索结果第一条
- **NDCG 越高**：排序质量越好

### 6.4 评测输出

终端输出示例：

```
2026-04-16 19:30:15 | INFO     | Running evaluation on 20 test cases
2026-04-16 19:30:15 | INFO     | Processing test case 1/20: q001
2026-04-16 19:30:22 | SUCCESS  | Test case q001: HR=1.00, MRR=1.00, NDCG=2.28 (6.53s)
...

============================================================
EVALUATION SUMMARY
============================================================
Timestamp: 2026-04-16T19:39:18.395691
Meal Data ID: e0bb1cb3d28aec6884f690f0136181ff...
Total test cases: 20
Total time: 130.56s
Avg time per case: 6.53s

Retrieval Metrics:
  Hit Rate: 0.9500
  MRR:      0.9500
  NDCG:     1.8833
============================================================
```

### 6.5 评测报告

报告保存在 `data/meals/{name}/baseline_report.json`，包含：

```json
{
  "timestamp": "2026-04-16T19:39:18.395691",
  "meal_data_id": "e0bb1cb3d28a...",
  "total_test_cases": 20,
  "total_time_seconds": 130.56,
  "avg_time_per_case": 6.53,
  "retrieval_metrics": {
    "avg_hit_rate": 0.95,
    "avg_mrr": 0.95,
    "avg_ndcg": 1.8833
  },
  "results": [
    {
      "id": "q001",
      "question": "...",
      "answer": "LLM生成的回答",
      "retrieval": {
        "hit_rate": 1.0,
        "mrr": 1.0,
        "ndcg": 2.28
      },
      "sources": ["实际检索到的来源"],
      "time_seconds": 6.53
    }
  ]
}
```

---

## 七、全链路实战示例

### 场景 A：Baseline 评测（快速验证）

目标：用少量数据快速验证系统是否能正常工作。

```bash
# 1. 创建小套餐（10 个 PDF）
pixi run python main.py --create-meal baseline_small --sample-count 10 --seed 42

# 2. 生成测试集
pixi run python main.py --generate-test-set baseline_small --strategy factual --num-questions 10

# 3. 运行评测
pixi run python eval/run_eval.py --meal baseline_small --test-set auto_factual

# 4. 查看报告
cat data/meals/baseline_small/baseline_report.json
```

### 场景 B：配置对比实验

目标：对比不同 chunk size 对检索质量的影响。

```bash
# 1. 创建套餐 A（chunk_size=512）
pixi run python main.py --create-meal exp_512 --sample-count 20 --seed 42

# 2. 创建套餐 B（chunk_size=1024，需要先修改 config.yaml 中的 chunk_size）
# 修改 config.yaml: chunker.chunk_size = 1024
pixi run python main.py --create-meal exp_1024 --sample-count 20 --seed 42

# 3. 分别为两个套餐生成测试集
pixi run python main.py --generate-test-set exp_512 --strategy factual --num-questions 20
pixi run python main.py --generate-test-set exp_1024 --strategy factual --num-questions 20

# 4. 分别评测
pixi run python eval/run_eval.py --meal exp_512 --test-set auto_factual
pixi run python eval/run_eval.py --meal exp_1024 --test-set auto_factual

# 5. 对比两个报告
cat data/meals/exp_512/baseline_report.json | jq '.retrieval_metrics'
cat data/meals/exp_1024/baseline_report.json | jq '.retrieval_metrics'
```

### 场景 C：数据规模对比

目标：对比不同数据量对检索质量的影响。

```bash
# 1. 创建不同规模的套餐（使用相同 seed 确保抽样一致性）
pixi run python main.py --create-meal scale_10 --sample-count 10 --seed 42
pixi run python main.py --create-meal scale_50 --sample-count 50 --seed 42
pixi run python main.py --create-meal scale_200 --sample-count 200 --seed 42

# 2. 为每个套餐生成测试集
pixi run python main.py --generate-test-set scale_10 --strategy factual --num-questions 20
pixi run python main.py --generate-test-set scale_50 --strategy factual --num-questions 20
pixi run python main.py --generate-test-set scale_200 --strategy factual --num-questions 20

# 3. 分别评测
pixi run python eval/run_eval.py --meal scale_10 --test-set auto_factual
pixi run python eval/run_eval.py --meal scale_50 --test-set auto_factual
pixi run python eval/run_eval.py --meal scale_200 --test-set auto_factual
```

### 场景 D：多策略综合评测

目标：全面评估系统在不同难度问题上的表现。

```bash
# 1. 创建套餐
pixi run python main.py --create-meal comprehensive --sample-count 20 --seed 42

# 2. 生成三种策略的测试集
pixi run python main.py --generate-test-set comprehensive --strategy factual --num-questions 20
pixi run python main.py --generate-test-set comprehensive --strategy boundary --num-questions 10
pixi run python main.py --generate-test-set comprehensive --strategy multi_hop --num-questions 5

# 3. 分别评测三种策略
pixi run python eval/run_eval.py --meal comprehensive --test-set auto_factual
pixi run python eval/run_eval.py --meal comprehensive --test-set auto_boundary
pixi run python eval/run_eval.py --meal comprehensive --test-set auto_multi_hop
```

---

## 八、全量评测（不使用套餐）

评测系统也支持不依赖套餐，直接对全量数据做评测。

### 8.1 使用手写测试集

```bash
# 准备测试数据文件 eval/test_data.json
pixi run python eval/run_eval.py --test-data eval/test_data.json
```

### 8.2 抽样评测

```bash
# 抽样 10 个 PDF 建索引后评测
pixi run python eval/run_eval.py --sample-count 10 --build-index

# 抽样 50% PDF 后评测
pixi run python eval/run_eval.py --sample-ratio 0.5 --build-index
```

---

## 九、套餐管理命令速查

### 9.1 生命周期管理

| 命令 | 说明 |
|------|------|
| `--create-meal [名称] --sample-count N` | 创建套餐 |
| `--meal [名称]` | 使用套餐问答 |
| `--list-meals` | 列出所有套餐 |
| `--meal-info [名称]` | 查看套餐详情 |
| `--rename-meal [旧名] [新名]` | 重命名 |
| `--copy-meal [源] [目标]` | 复制（浅拷贝） |
| `--delete-meal [名称]` | 删除套餐 |
| `--repair-meal [名称]` | 交互式修复 |

### 9.2 测试集管理

| 命令 | 说明 |
|------|------|
| `--generate-test-set [名称]` | 生成测试集 |
| `--strategy [类型]` | 指定生成策略 |
| `--num-questions N` | 指定问题数量 |
| `--llm-preset [模型]` | 指定 LLM 模型 |
| `--seed N` | 随机种子 |

### 9.3 评测管理

| 命令 | 说明 |
|------|------|
| `eval/run_eval.py --meal [名称]` | 评测指定套餐 |
| `--test-set [名称]` | 指定测试集 |
| `--test-data [路径]` | 指定外部测试数据 |
| `--build-index` | 评测前建索引 |
| `--rebuild` | 重建索引 |
| `--llm-preset [模型]` | 指定 LLM 模型 |

---

## 十、目录结构

完整产物目录：

```
data/
├── meals/
│   └── {meal_name}/
│       ├── manifest.json              # 套餐元数据
│       ├── test_sets/
│       │   ├── auto_factual.json      # 事实性测试集
│       │   ├── auto_boundary.json     # 边界测试集
│       │   └── auto_multi_hop.json    # 多跳测试集
│       └── baseline_report.json       # 评测报告
├── artifacts/
│   ├── parsed/                        # 解析产物缓存
│   │   └── {sha256}.pkl
│   └── chunks_{hash}/                # 分块产物缓存
│       └── {sha256}.pkl
└── vector_store/                      # Qdrant 向量存储
    └── collections/
        ├── m_xxxxxxxxxxxx/           # 套餐索引
        └── main/                     # 全量索引
```

---

## 十一、注意事项

### 11.1 路径分隔符

评测时，测试集中的 `source_files` 使用 `\\`（Windows 路径），而检索返回的 `sources` 使用 `/`（POSIX 路径）。当前版本的路径匹配使用 `source_files` 直接对比，在 Windows 环境下通常可以正常工作。如果路径匹配出现问题，可检查 `eval/run_eval.py` 中的路径归一化逻辑。

### 11.2 评测时间

评测耗时主要取决于：
- **测试集大小**：每个问题需要一次 LLM 调用
- **LLM 响应速度**：在线 API 延迟
- **Embedding 模型**：本地加载，影响较小

参考：20 个问题约 2 分钟。

### 11.3 缓存复用

套餐创建后，相同数据 + 相同配置会命中缓存，创建速度极快。如果修改了 `config.yaml` 中的分块或解析参数，缓存会失效并重新计算。

### 11.4 测试集格式兼容

评测脚本支持两种测试数据格式：
1. **JSON 数组**（旧格式）：直接包含 test cases 列表
2. **带 questions 字段的对象**（新格式）：测试生成系统输出的格式

两种格式均可被自动识别。

### 11.5 报告解读

- **Hit Rate < 1.0**：说明部分预期来源未被检索到，可能需要调整检索参数
- **MRR 低但 Hit Rate 高**：说明能检索到正确来源，但排序不佳
- **NDCG 低**：说明高质量来源排在后面，可能需要引入 Reranker

---

## 十二、快速上手 Checklist

```
[ ] 1. 确认 PDF 文件在 data/raw/ 下
[ ] 2. 创建第一个套餐：
      pixi run python main.py --create-meal test1 --sample-ratio 0.05
[ ] 3. 验证套餐：
      pixi run python main.py --list-meals
[ ] 4. 生成测试集：
      pixi run python main.py --generate-test-set test1 --strategy factual --num-questions 10
[ ] 5. 运行评测：
      pixi run python eval/run_eval.py --meal test1 --test-set auto_factual
[ ] 6. 查看报告：
      cat data/meals/test1/baseline_report.json
```
