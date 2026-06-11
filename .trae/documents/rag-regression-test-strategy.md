# RAG 系统回归测试策略规划

> 规划日期：2026-05-21
> 目标：建立可持续、可复现、版权合规的端到端回归测试体系

***

## 一、核心问题分析

### 1.1 你的真实需求

| 维度       | 现状                            | 痛点               |
| -------- | ----------------------------- | ---------------- |
| **测试数据** | 网上抓了几百个金融 PDF，放在被 ignore 的文件夹 | 未纳入测试套件，无法版本控制   |
| **测试方式** | 人工挑选问题，知道预期答案和工具调用方式          | 每次更新后手动验证，效率低    |
| **回归目标** | 验证新版本是否"搞坏事"（召回质量、速度、稳定性、鲁棒性） | 缺乏自动化、可复现的回归机制   |
| **约束条件** | 版权顾虑、Git 仓库体积、测试数据管理          | 不能直接提交大量 PDF 到仓库 |

### 1.2 关键决策点

```
PDF 怎么选？      → 分层采样策略
选多少？          → 最小有效集合（MVP 思路）
放哪里？          → Git LFS / 外部存储 / 动态下载
怎么测？          → 三层测试金字塔
怎么管？          → 版本化测试集 + 确定性校验
```

***

## 二、推荐方案：分层回归测试体系

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: 全量回归测试（Nightly/发版前）                           │
│  ├─ 100+ 问题，覆盖全量 PDF                                       │
│  ├─ 完整指标：Hit Rate / MRR / NDCG / Faithfulness / Relevancy   │
│  ├─ 多 Variant 对比（Baseline vs 新版本）                         │
│  └─ 触发时机：定时任务、发版前、重大变更后                          │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 冒烟回归测试（Post-merge / CI）                          │
│  ├─ 20-30 个核心问题，覆盖关键场景                                 │
│  ├─ 核心指标：Hit Rate / Faithfulness                            │
│  ├─ 使用小型测试数据集（5-10 个精选 PDF）                          │
│  └─ 触发时机：每次合并到 dev/main 后                               │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 单元级回归（开发中）                                     │
│  ├─ Mock 外部依赖，验证逻辑正确性                                  │
│  ├─ 基于 fixtures 的确定性测试                                    │
│  └─ 触发时机：每次 commit 前（< 10s）                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 测试数据分层策略

#### 第一层：单元测试 fixtures（已存在）

```
tests/fixtures/
├── golden_qa.json              # 现有：10 个问题，用于基础格式校验
├── mock_pdfs/                  # 新增：程序生成的最小 PDF
│   ├── minimal_text.pdf        # 纯文本，1 页，用于解析测试
│   ├── with_table.pdf          # 包含表格，用于表格提取测试
│   └── with_image.pdf          # 包含图片，用于 OCR 测试
└── synthetic_chunks.json       # 预生成的 chunk 数据，用于检索测试
```

**Mock PDF 生成方案**：

* 不依赖外部文件，测试代码自动生成最小 PDF

* 使用 `fpdf2` 或纯文本 PDF 结构（如 `test_e2e_experiment.py` 中的方式）

* 包含特定内容，用于验证解析、分块、检索逻辑

#### 第二层：冒烟测试数据集（可提交到 Git）

```
tests/fixtures/smoke_test/
├── pdfs/                       # 5-10 个精选 PDF，总大小 < 10MB
│   ├── annual_report_sample.pdf    # 年报样本（公开数据）
│   ├── research_note_sample.pdf    # 研报样本（公开数据）
│   └── ...
├── testset.json                # 20-30 个问题
│   └── 每个问题包含：
│       - question: 问题文本
│       - expected_sources: 期望来源文档
│       - expected_keywords: 期望包含的关键词
│       - expected_tools: 期望调用的工具（如 reranker/query_rewrite）
│       - min_hit_rate: 最低命中率要求
│       - min_faithfulness: 最低忠实度要求
└── README.md                   # 数据来源说明、版权信息
```

**PDF 选择标准**：

1. **版权合规**：优先选择公开披露的信息（如上市公司年报、政府公开报告）
2. **内容稳定**：选择已发布一段时间、不会再更新的文档
3. **场景覆盖**：

   * 单知识点查询（如"某公司 2024 年营收"）

   * 多知识点综合（如"对比 A 公司和 B 公司的 ROE"）

   * 推理型问题（如"为什么 C 公司毛利率下降"）

   * 边界情况（如数值范围、表格数据）
4. **文件大小**：单个 PDF < 2MB，总数据集 < 10MB

#### 第三层：全量回归测试数据集（外部管理）

```
data/regression_test/           # 被 .gitignore，但提供下载脚本
├── download.py                 # 从外部源下载 PDF
│   └── 支持：本地缓存、校验和验证、断点续传
├── pdfs/                       # 100+ PDF，按需下载
├── testset_full.json           # 100+ 问题，审核通过
└── manifests/
    ├── v1.0.0.json             # 版本化清单（文件名 + SHA256）
    └── v1.1.0.json
```

**外部存储选项**：

| 方案                        | 优点             | 缺点          | 适用场景         |
| ------------------------- | -------------- | ----------- | ------------ |
| **Git LFS**               | 与 Git 集成好，版本控制 | 免费额度有限（1GB） | 小型数据集（< 1GB） |
| **对象存储**（OSS/S3）          | 容量大，成本低        | 需要额外配置      | 大型数据集        |
| **Hugging Face Datasets** | 专为 ML 设计，社区支持  | 公开数据        | 可公开的数据集      |
| **本地网络存储**                | 速度快，完全控制       | 仅限内网        | 企业环境         |

**推荐**：Git LFS 管理元数据 + 对象存储管理 PDF 文件

### 2.3 测试问题设计原则

#### 问题类型分布（参考现有 testset 系统）

```yaml
# tests/fixtures/smoke_test/testset.json 结构
{
  "metadata": {
    "name": "smoke_test_v1",
    "version": "1.0.0",
    "created_at": "2026-05-21",
    "data_coverage": "partial",
    "quality_status": "approved"
  },
  "questions": [
    {
      "id": "smoke_001",
      "question": "工商银行2024年不良贷款率是多少？",
      "question_type": "single_fact",
      "difficulty": "easy",
      "source_files": ["annual_report_sample.pdf"],
      "ground_truth_excerpt": "截至报告期末，本行不良贷款率为1.36%",
      "expected_keywords": ["1.36%", "不良贷款率"],
      "expect_retrieval": true,
      "expect_no_answer": false,
      "min_hit_rate": 1.0,
      "min_faithfulness": 0.9
    },
    {
      "id": "smoke_002",
      "question": "光模块行业2024年市场规模和2025年预测分别是多少？",
      "question_type": "multi_fact",
      "difficulty": "medium",
      "source_files": ["research_note_sample.pdf"],
      "ground_truth_excerpt": "2024年市场规模约120亿美元，预计2025年达到180亿美元",
      "expected_keywords": ["120亿", "180亿"],
      "expect_retrieval": true,
      "expect_no_answer": false,
      "min_hit_rate": 1.0,
      "min_faithfulness": 0.85
    },
    {
      "id": "smoke_003",
      "question": "某公司2024年营收增长的原因是什么？",
      "question_type": "reasoning",
      "difficulty": "hard",
      "source_files": ["annual_report_sample.pdf"],
      "ground_truth_excerpt": "营收增长主要得益于新产品销售增长和市场份额扩大",
      "expected_keywords": ["新产品", "市场份额"],
      "expect_retrieval": true,
      "expect_no_answer": false,
      "min_hit_rate": 0.8,
      "min_faithfulness": 0.8
    }
  ]
}
```

#### 关键设计点

1. **确定性答案**：每个问题都有明确的、可从文档中验证的答案
2. **关键词检查**：除了语义评估，还有关键词命中检查（更稳定）
3. **工具调用验证**：记录期望的工具调用链（如是否触发 reranker）
4. **阈值设定**：每个问题可设置不同的最低通过标准

***

## 三、实施方案

### 3.1 阶段一：基础 fixtures（1-2 天）

**目标**：建立不依赖外部数据的单元测试层

```python
# tests/fixtures/mock_pdf_generator.py
"""生成最小化测试用 PDF，不依赖外部文件"""

from io import BytesIO
from pathlib import Path
from typing import List


def create_minimal_text_pdf(text: str, output_path: Path) -> Path:
    """创建包含指定文本的最小 PDF"""
    # 使用 fpdf2 生成
    from fpdf import FPDF
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, text)
    pdf.output(str(output_path))
    return output_path


def create_pdf_with_table(data: List[List[str]], output_path: Path) -> Path:
    """创建包含表格的 PDF"""
    from fpdf import FPDF
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # 添加表格
    for row in data:
        for cell in row:
            pdf.cell(40, 10, cell, border=1)
        pdf.ln()
    
    pdf.output(str(output_path))
    return output_path


# 在 conftest.py 中提供 fixture
@pytest.fixture
def mock_annual_report(tmp_path) -> Path:
    """提供一个模拟年报 PDF"""
    content = """
    2024 年年度报告
    
    一、公司基本情况
    公司名称：测试科技
    股票代码：123456
    
    二、主要财务数据
    营业收入：150.56 亿元，同比增长 18.04%
    净利润：50.23 亿元，同比增长 15.32%
    不良贷款率：1.36%
    """
    return create_minimal_text_pdf(content, tmp_path / "annual_report.pdf")
```

### 3.2 阶段二：冒烟测试集（3-5 天）

**目标**：建立 20-30 个问题的冒烟测试集，可提交到 Git

**步骤**：

1. **选择 5-10 个公开 PDF**

   * 来源：上交所/深交所公开年报、行业协会公开报告

   * 标准：文件大小 < 2MB，内容稳定，覆盖不同场景

2. **人工设计 20-30 个问题**

   * 使用现有的 `testset generate` + `testset review` 流程

   * 人工审核确保质量

   * 记录期望答案和关键词

3. **创建测试配置**

   ```yaml
   # tests/fixtures/smoke_test/config.yaml
   name: "smoke_test"
   description: "冒烟回归测试集"

   data:
     pdf_dir: "tests/fixtures/smoke_test/pdfs"
     testset: "tests/fixtures/smoke_test/testset.json"

   thresholds:
     min_avg_hit_rate: 0.85
     min_avg_faithfulness: 0.80
     min_avg_relevancy: 0.85

   evaluation:
     backends: ["builtin"]
     metrics_preset: "core"
   ```

4. **实现冒烟测试脚本**

   ```python
   # tests/test_smoke_regression.py
   import pytest
   from pathlib import Path

   SMOKE_TEST_DIR = Path(__file__).parent / "fixtures" / "smoke_test"

   @pytest.mark.smoke
   @pytest.mark.integration
   def test_smoke_regression():
       """冒烟回归测试：验证核心功能是否正常"""
       # 加载测试集
       testset = load_testset(SMOKE_TEST_DIR / "testset.json")
       
       # 构建索引（使用测试专用配置）
       pipeline = build_test_pipeline(SMOKE_TEST_DIR / "config.yaml")
       
       # 运行测试
       results = run_evaluation(pipeline, testset)
       
       # 检查阈值
       assert results["avg_hit_rate"] >= 0.85, f"Hit rate {results['avg_hit_rate']} below threshold"
       assert results["avg_faithfulness"] >= 0.80, f"Faithfulness {results['avg_faithfulness']} below threshold"
   ```

### 3.3 阶段三：全量回归测试集（1-2 周）

**目标**：建立 100+ 问题的全量回归测试集，外部管理

**步骤**：

1. **选择 100+ PDF**

   * 从你的几百个 PDF 中分层采样

   * 按行业、年份、文档类型分层

2. **生成问题**

   ```bash
   # 使用现有工具生成
   pixi run testset generate --meal regression_full --strategy document --num 150
   pixi run testset enrich --input data/regression_full/test_sets/document_n150.json --auto-approve-tier-a
   pixi run testset review --input data/regression_full/test_sets/document_n150.json
   pixi run testset approve --input data/regression_full/test_sets/document_n150.json
   ```

3. **创建版本化清单**

   ```json
   {
     "version": "1.0.0",
     "created_at": "2026-05-21",
     "pdfs": [
       {
         "filename": "icbc_2024_annual.pdf",
         "sha256": "abc123...",
         "source_url": "https://...",
         "size_bytes": 1234567
       }
     ],
     "testset": "data/regression_full/test_sets/document_n120_approved.json",
     "testset_sha256": "def456..."
   }
   ```

4. **实现下载脚本**

   ```python
   # scripts/download_regression_data.py
   """下载回归测试数据集"""

   import argparse
   import json
   import hashlib
   from pathlib import Path
   import requests

   def download_regression_data(version: str, output_dir: Path):
       manifest = load_manifest(version)
       
       for pdf_info in manifest["pdfs"]:
           output_path = output_dir / pdf_info["filename"]
           
           if output_path.exists():
               if verify_sha256(output_path, pdf_info["sha256"]):
                   print(f"✓ {pdf_info['filename']} already exists and valid")
                   continue
               else:
                   print(f"✗ {pdf_info['filename']} checksum mismatch, re-downloading")
           
           download_file(pdf_info["source_url"], output_path)
           verify_sha256(output_path, pdf_info["sha256"])
   ```

### 3.4 阶段四：CI/CD 集成（2-3 天）

**目标**：自动化回归测试流程

```yaml
# .github/workflows/regression.yml
name: Regression Tests

on:
  push:
    branches: [main, dev]
  schedule:
    - cron: '0 2 * * *'  # 每天凌晨 2 点

jobs:
  smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Pixi
        uses: prefix-dev/setup-pixi@v0.8.0
      
      - name: Run Smoke Tests
        run: pixi run pytest tests/test_smoke_regression.py -v
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
  
  full-regression:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule' || contains(github.event.head_commit.message, '[regression]')
    steps:
      - uses: actions/checkout@v4
      
      - name: Download Regression Data
        run: pixi run python scripts/download_regression_data.py --version 1.0.0
        env:
          REGRESSION_DATA_URL: ${{ secrets.REGRESSION_DATA_URL }}
      
      - name: Run Full Regression
        run: pixi run pytest tests/test_full_regression.py -v
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
      
      - name: Upload Results
        uses: actions/upload-artifact@v4
        with:
          name: regression-results
          path: data/regression_results/
```

***

## 四、版权与合规建议

### 4.1 PDF 来源建议

| 来源类型       | 示例          | 版权状态       | 适用性   |
| ---------- | ----------- | ---------- | ----- |
| **上市公司年报** | 上交所、深交所披露   | 公开信息，可合理使用 | ⭐⭐⭐⭐⭐ |
| **政府公开报告** | 统计局、央行报告    | 公开信息       | ⭐⭐⭐⭐  |
| **行业协会报告** | 证券业协会、基金业协会 | 部分公开       | ⭐⭐⭐   |
| **学术预印本**  | arXiv、SSRN  | 通常可引用      | ⭐⭐⭐   |
| **自行生成**   | 模拟数据        | 完全可控       | ⭐⭐⭐⭐  |

### 4.2 合规措施

1. **仅使用公开信息**：不提交任何付费或内部文档
2. **数据脱敏**：如有敏感信息，进行脱敏处理
3. **版权声明**：在测试数据 README 中明确标注来源和版权状态
4. **最小化原则**：仅使用必要的文档片段，而非完整文档

### 4.3 替代方案：合成数据

如果版权顾虑较大，可以考虑：

```python
# 使用 LLM 生成合成年报
"""生成逼真的合成金融文档，用于测试"""

SYNTHETIC_ANNUAL_REPORT_TEMPLATE = """
{company_name} {year} 年年度报告

一、公司概况
公司名称：{company_name}
股票代码：{stock_code}
所属行业：{industry}

二、主要财务数据
营业收入：{revenue} 亿元，同比增长 {revenue_growth}%
净利润：{profit} 亿元，同比增长 {profit_growth}%
总资产：{total_assets} 亿元
净资产收益率：{roe}%
不良贷款率：{npl_ratio}%

三、经营情况分析
{business_analysis}
"""

# 使用 faker 生成随机但一致的数据
from faker import Faker
import random

def generate_synthetic_report(seed: int) -> str:
    fake = Faker()
    Faker.seed(seed)
    random.seed(seed)
    
    return SYNTHETIC_ANNUAL_REPORT_TEMPLATE.format(
        company_name=fake.company(),
        year=2024,
        stock_code=f"{random.randint(600000, 699999)}",
        industry=random.choice(["银行", "保险", "证券", "科技"]),
        revenue=round(random.uniform(50, 5000), 2),
        revenue_growth=round(random.uniform(-10, 30), 2),
        # ...
    )
```

***

## 五、与现有测试体系的整合

### 5.1 利用现有基础设施

| 现有组件                            | 如何复用       |
| ------------------------------- | ---------- |
| `test_regression.py`            | 扩展为三层测试入口  |
| `tests/fixtures/golden_qa.json` | 作为冒烟测试的基础  |
| `pixi run testset` CLI          | 用于生成和管理测试集 |
| `eval/run_experiment.py`        | 用于全量回归测试执行 |
| Meal 系统                         | 管理测试数据版本   |
| Artifact 系统                     | 缓存解析和分块结果  |

### 5.2 测试标记策略

```python
# pytest marker 设计

@pytest.mark.unit
def test_parse_logic():
    """纯单元测试，mock 所有依赖"""
    pass

@pytest.mark.smoke
@pytest.mark.integration
def test_smoke_regression():
    """冒烟测试，使用 fixtures 中的小型数据集"""
    pass

@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.slow
def test_full_regression():
    """全量回归测试，使用完整数据集"""
    pass
```

### 5.3 命令行接口

```bash
# 三层测试命令

# Layer 1: 单元测试（< 10s）
pixi run test-unit

# Layer 2: 冒烟回归（~1-2min）
pixi run test-smoke

# Layer 3: 全量回归（~30min-1h，取决于数据量）
pixi run test-regression

# 或指定版本
pixi run test-regression --version 1.0.0
```

***

## 六、总结与下一步

### 6.1 推荐实施顺序

```
Week 1:
  ├─ Day 1-2: 实现 mock PDF 生成器，完善单元测试
  └─ Day 3-5: 选择 5-10 个公开 PDF，建立冒烟测试集

Week 2:
  ├─ Day 1-3: 从你的几百个 PDF 中采样，建立全量回归测试集
  └─ Day 4-5: 实现下载脚本和 CI/CD 集成

Week 3:
  └─ 验证整个流程，调优阈值，文档化
```

### 6.2 关键决策点

| 决策       | 建议                                 | 理由                 |
| -------- | ---------------------------------- | ------------------ |
| PDF 放哪里？ | tests/fixtures/smoke\_test/ + 外部存储 | 小数据集入 Git，大数据集外部管理 |
| 选多少 PDF？ | 冒烟 5-10 个，全量 100+ 个                | 冒烟快速反馈，全量深度验证      |
| 版权问题？    | 优先公开年报 + 合成数据                      | 合规且可控              |
| 多久跑一次？   | 冒烟每次合并，全量每天/发版前                    | 平衡反馈速度与成本          |

### 6.3 预期收益

1. **版本更新信心**：每次更新后自动验证是否"搞坏事"
2. **问题快速定位**：分层测试快速缩小问题范围
3. **性能回归检测**：监控召回速度、生成质量趋势
4. **实验可复现**：版本化测试集确保实验可比性

***

## 附录：参考文档

* [测试运行指南](docs/dev-guides/testing.md)

* [测试集系统完整指南](docs/user-guides/test-system.md)

* [实验评测系统使用指南](docs/user-guides/experiment-system.md)

* [评测指标详解](docs/user-guides/evaluation-metrics.md)

