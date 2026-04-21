# 精调测试集设计计划书

## 一、执行流程总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        执行流程                                  │
├─────────────────────────────────────────────────────────────────┤
│  [你点击执行]                                                    │
│       ↓                                                          │
│  [我] 运行 recommend_testset.py，生成推荐列表                     │
│       ↓                                                          │
│  [我] 停下来，把推荐列表给你 ← 你来这里                           │
│       ↓                                                          │
│  [你] 打开 PDF，手工出题，提供页码+标题                           │
│       ↓                                                          │
│  [我] 映射到精确 chunk，生成测试集 JSON                           │
│       ↓                                                          │
│  [我] 运行实验，生成报告                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、推荐列表生成（自动化）

### 2.1 工具

使用 `eval/recommend_testset.py`，基于 **MD 文件大小**（而非 PDF 文件大小）分配问题数量。

```bash
pixi run python eval/recommend_testset.py --meal <meal_name> --num-questions <N>
```

### 2.2 分配逻辑

1. **规模分层**：按 MD 文件文本大小分为 Large (>=200KB)、Medium (50-200KB)、Small (<50KB)
2. **问题分配**：按文本大小加权分配，每层有最大问题数上限
3. **类型分配**：
   - **文档绑定类型**（single_fact, multi_fact, reasoning, comparative）：按类别亲和度分配到具体文档
   - **自由浮动类型**（missing, irrelevant）：不绑定到特定文档

### 2.3 类别-类型亲和度

| 类型 | 年报 (annual_report) | 研报 (research_report) |
|------|---------------------|----------------------|
| single_fact | 20% | 40% |
| multi_fact | 35% | 25% |
| reasoning | 20% | 20% |
| comparative | 25% | 15% |

**设计理由**：
- 年报结构化程度高，适合多知识点综合和对比分析
- 研报信息密度高，适合单知识点查询；且容易构造缺失知识点问题

---

## 三、问题类型与数量分配

### 3.1 默认分配比例

| 类型 | 占比 | 说明 |
|------|------|------|
| `single_fact` | 28% | 单知识点，测试基础检索 |
| `multi_fact` | 22% | 多知识点，测试信息整合 |
| `reasoning` | 16% | 推理型，测试因果分析 |
| `comparative` | 12% | 对比型，测试跨段落对比 |
| `missing` | 12% | 缺失知识点，测试拒答能力 |
| `irrelevant` | 10% | 无关问题，测试正确拒绝 |

### 3.2 设计理由

- **single_fact 占比最高**：这是 RAG 最基础的使用场景，需要充分测试
- **missing/irrelevant 合计 22%**：比之前 15% 大幅增加，因为"拒答能力"是 RAG 系统的重要短板
- **comparative 占比适中**：需要跨段落信息，对检索和生成都提出更高要求

---

## 四、Step-by-Step 手调流程

### Step 1：我生成推荐列表（自动化）

运行 `recommend_testset.py`，输出包含：
- 每个文档的推荐问题数量和类型
- 按规模分层的汇总

**停止点**：生成推荐列表后，我会停下来，把列表给你。

### Step 2：你打开 PDF，手工出题

**你需要提供的信息**：

```
问题 1：
- 问题文本：XXX公司2023年营业收入是多少？
- 答案：XXX亿元
- PDF 文件：XXX公司2023年年度报告.pdf
- 页码：第 15 页
- 最近标题：第三节 公司简介和主要财务指标
- 问题类型：single_fact
- 难度：easy
```

**对于 missing 类型**：
- 选择一个文档，问它**不包含**的信息
- 例如：问一份白酒行业研报中"红酒的进口数据"

**对于 irrelevant 类型**：
- 问一个与所有文档都无关的问题
- 例如："最近美联储加息对A股科技股有什么影响？"

### Step 3：我映射到精确 chunk（自动化）

**输入**：你提供的问题 + 页码 + 标题
**输出**：精确的 source_chunks

**映射逻辑**：
1. 读取该 PDF 对应的 chunk 文件
2. 利用 `page_separators` 标记定位页码范围
3. 利用章节标题交叉验证
4. 确定精确 chunk_id

---

## 五、核心设计原则

### 5.1 "问题→答案"对是核心资产

问题集与 chunk/page/标题是**松耦合**的：
- 先获得高质量的"问题→答案"对
- chunk 映射是后续自动化的工作
- 即使 PDF→MD→chunk 流程重构，问题集仍然有效

### 5.2 MD 文件大小比 PDF 文件大小更准确

PDF 文件大小受图片、装饰等影响，不能准确反映文本量。
MD 文件大小（纯文本）能更客观地反映文档的信息量。

### 5.3 missing/irrelevant 不绑定文档

这两种类型的问题不需要绑定到特定文档：
- missing：选择一个文档，问它不包含的信息
- irrelevant：问完全无关的问题

---

## 六、Parser 优化（已完成）

### 6.1 pymupdf4llm 参数优化

在 `config.yaml` 中新增了 `pymupdf4llm` 配置项：

```yaml
parser:
  pymupdf4llm:
    header: false          # 去除重复页眉
    footer: false          # 去除重复页脚
    page_separators: true  # 标记页面边界（--- end of page=N ---）
    ignore_images: true    # 不处理图片
    write_images: false    # 不写入图片文件
```

**关键改进**：`page_separators: true` 为 chunk→页码映射提供了基础。

### 6.2 代码改动

- `src/parser.py`：`parse_pdf()` 支持 `**kwargs` 透传 pymupdf4llm 参数
- `src/meal.py`：从配置中读取 `pymupdf4llm` 参数并传递

---

## 七、相关文件

| 文件 | 说明 |
|------|------|
| `eval/recommend_testset.py` | 推荐列表生成器 |
| `src/parser.py` | PDF 解析器（支持 pymupdf4llm 参数） |
| `config.yaml` | parser.pymupdf4llm 配置 |
| `src/test_generator.py` | source_chunks 生成逻辑（已收紧） |
| `eval/run_eval.py` | 评估逻辑（已修复特殊问题跳过） |
