# Golden Test 交互式审核脚本全面优化方案

## 一、现状分析

### 当前脚本 `scripts/review_golden_testset.py` 提供的功能
- **交互式审核模式**：逐题审核，支持 Approve/Edit/Reject/Skip/Quit
- **审计模式**：生成质量报告（文档分布偏斜、数值精度、内容重复等）
- **自动审批模式**：基于规则的质量检查（excerpt验证、数值修正、长度检查等）

### 当前痛点
1. **人工审核量大**：150道题全部需人工审核，auto-approve 仅做简单规则过滤
2. **缺少信源对照**：审核时无法快速查看PDF原文，需手动打开文件翻页
3. **交互效率低**：每题需多次按键，缺少上下文信息展示，无法形成心流

---

## 二、改进方案

### 改进1：AI 预审核与智能筛选

#### 1.1 AI 质量评分系统

新增 `AIReviewer` 类，利用项目已有的 LLM 基础设施（Anthropic SDK + LongCat API）对每道题进行自动评估。

**评分维度**（每项 1-5 分）：
- **问题清晰度**：问题是否明确无歧义
- **答案准确性**：答案与 ground_truth_excerpt 是否一致
- **答案完整性**：答案是否充分回答了问题
- **信源一致性**：ground_truth_excerpt 是否真正支撑答案

**综合评分** = 加权平均 → 映射为 A/B/C 三级：
- **A级（≥4.0）**：高质量，建议自动通过
- **B级（3.0-3.9）**：存疑，需人工审核
- **C级（<3.0）**：低质量，建议拒绝或重点审核

**实现要点**：
- 复用 `src/utils.py` 中的 `get_llm_config()` + `create_llm_client(mode="sdk")` 创建 LLM 客户端
- 使用 `test_generation.model_name`（LongCat-Flash-Lite）作为默认审核模型，控制成本
- 批量调用：每5题一组发送，减少API调用次数
- 结果缓存：评分结果写入 question.metadata.ai_review，避免重复调用
- 新增 CLI 参数 `--ai-review` 触发AI预审核
- 新增 CLI 参数 `--llm-preset` 指定审核用LLM

#### 1.2 分级审核流程

```
150道题 → AI预审核 → A级(自动通过) + B级(人工审核) + C级(重点审核)
                      ↓                ↓                ↓
                   标记auto_approved   正常审核流程     标记needs_revision
```

**新增 `--tiered-review` 模式**：
1. 先运行 AI 预审核，为所有题目打分
2. A级题目自动标记为 `auto_approved`，附带AI评分理由
3. B级题目进入正常交互式审核，但展示AI评分作为参考
4. C级题目进入审核时，高亮标记"AI建议拒绝"，展示具体问题

**预期效果**：150题中约40-60%可被AI自动通过，人工只需审核60-90题。

#### 1.3 AI审核Prompt设计

```
你是一个金融研报问答系统的质量审核专家。请评估以下问答对的质量。

评估维度（每项1-5分）：
1. question_clarity: 问题是否清晰、无歧义、可独立理解
2. answer_accuracy: 答案是否与提供的原文片段(ground_truth_excerpt)一致
3. answer_completeness: 答案是否充分回答了问题
4. source_consistency: 原文片段是否真正支撑了答案

题目信息：
- 问题类型: {question_type}
- 问题: {question}
- 答案: {answer}
- 原文片段: {ground_truth_excerpt}

请以JSON格式返回评分和理由：
{
  "question_clarity": {"score": X, "reason": "..."},
  "answer_accuracy": {"score": X, "reason": "..."},
  "answer_completeness": {"score": X, "reason": "..."},
  "source_consistency": {"score": X, "reason": "..."},
  "overall_comment": "一句话总结",
  "suggested_action": "approve/review/reject"
}
```

---

### 改进2：PDF自动调用与Chunk内容展示

#### 2.1 PDF自动打开与页面定位

**方案A（首选）：SumatraPDF 命令行调用**

SumatraPDF 支持 `-page <pageNo>` 参数直接跳转到指定页面：
```bash
SumatraPDF.exe -page 15 "B:\path\to\report.pdf"
```

实现方式：
1. 检测系统是否安装 SumatraPDF（常见路径 + PATH 环境变量）
2. 若已安装，审核题目时自动调用 `subprocess.Popen` 打开PDF并跳转
3. 使用 `-reuse-instance` 参数复用已打开的窗口（切换页面而非新开窗口）

**方案B（备选）：Edge浏览器**

Edge支持通过URL fragment跳转页面：`msedge "file:///path/to/file.pdf#page=15"`

**方案C（兜底）：纯文本展示**

若外部PDF查看器不可用，从 `.pages.json` 中提取对应页面文本，在终端中直接展示。

#### 2.2 页面定位逻辑

需要建立 question → PDF page 的映射链：

```
question.source_files[0]  →  data/raw/{source_file}.pdf  (原始PDF路径)
question.source_chunks    →  chunks JSONL  →  metadata.page_number  (页码)
question.ground_truth_excerpt  →  .pages.json  →  模糊匹配定位页码
```

**具体实现**：
1. 通过 `ArtifactCache.resolve_pointer("full_parsed")` 获取解析结果目录
2. 根据 `source_files[0]` 定位对应的 `.pages.json` 文件
3. 若题目有 `source_chunks`，从 chunk 的 `metadata.page_number` 获取页码
4. 若无 chunk 页码，在 `.pages.json` 中用 `ground_truth_excerpt` 模糊匹配定位页码
5. 原始PDF路径 = `data/raw/{source_file}`

新增 `PDFViewer` 类封装此逻辑：
- `open_at_page(pdf_path, page_number)`: 调用外部查看器
- `locate_page_for_question(question)`: 返回 (pdf_path, page_number)
- `detect_viewer()`: 自动检测可用的PDF查看器

#### 2.3 Chunk内容内嵌展示

在审核界面中直接展示相关chunk文本，无需用户手动查找：

```
  ┌─ CHUNK CONTEXT ──────────────────────────────────┐
  │ [p3_002] Page 3 | 512 tokens                     │
  │ 公司2024年营收达到100亿元，同比增长15%。其中...    │
  │ 净利润为50亿元，较上年增长8%...                    │
  └──────────────────────────────────────────────────┘
```

**实现**：
1. 通过 `ArtifactCache.resolve_pointer("full_chunks")` 获取chunk目录
2. 根据 `source_files[0]` 定位对应的 `.jsonl` 文件
3. 若题目有 `source_chunks`，直接按 chunk_id 查找
4. 若无，用 `ground_truth_excerpt` 在chunk文本中模糊匹配
5. 展示匹配的chunk文本（截断到合理长度）

---

### 改进3：交互流程优化（Paper Please 风格）

#### 3.1 信息密度优化

重新设计 `display_question()`，一屏展示所有关键信息：

```
══════════════════════════════════════════════════════════════════════
  #042/150  │ golden_042  │ single_fact  │ easy  │ ⚠ AI: B(3.2)
══════════════════════════════════════════════════════════════════════

  Q: 该公司2024年营收增长率是多少？

  A: 该公司2024年营收同比增长15%。

  📄 EXCERPT: "公司2024年营收达到100亿元，同比增长15%"
     ✓ Excerpt verified  ✗ Numerical auto-corrected

  ┌─ CHUNK [p3_002] Page 3 ──────────────────────────────────────┐
  │ 公司2024年营收达到100亿元，同比增长15%。其中主营业务收入...   │
  └──────────────────────────────────────────────────────────────┘

  📖 PDF: reports/annual_report.pdf → Page 3  [p] Open PDF

  [a]✓  [e]✏  [r]✗  [s]⏭  [p]📖  [q]🚪
══════════════════════════════════════════════════════════════════════
```

#### 3.2 快捷键优化

- **单键操作**：`a`=通过, `e`=编辑, `r`=拒绝, `s`=跳过, `p`=打开PDF, `q`=退出
- **新增 `p` 键**：按 `p` 打开PDF到对应页面（再按 `p` 关闭/切换）
- **新增 `c` 键**：切换显示/隐藏chunk上下文
- **新增 `i` 键**：显示AI审核详情（评分、理由）
- **进度条**：在顶部显示审核进度 `[████████░░░░░░░░] 42/150 (28%)`

#### 3.3 审核会话状态管理

- 记录审核会话统计：通过数、拒绝数、跳过数、平均审核时间
- 退出时显示本次会话摘要
- 支持按AI评分排序审核（先审C级，再审B级）

---

## 三、实现步骤

### Step 1: 新增 AI 预审核模块
- 创建 `scripts/ai_reviewer.py`，实现 `AIReviewer` 类
- 包含：LLM客户端初始化、评分prompt、批量评估、结果缓存
- 编写单元测试 `tests/test_ai_reviewer.py`

### Step 2: 新增 PDF 查看器模块
- 创建 `scripts/pdf_viewer.py`，实现 `PDFViewer` 类
- 包含：查看器检测、页面定位、PDF打开、chunk内容提取
- 编写单元测试 `tests/test_pdf_viewer.py`

### Step 3: 重构交互式审核界面
- 修改 `scripts/review_golden_testset.py`
- 重写 `display_question()`：信息密度优化、chunk内嵌、AI评分展示
- 重写 `review_question()`：新增快捷键 p/c/i
- 新增进度条显示
- 新增 `--ai-review`、`--tiered-review`、`--llm-preset`、`--sort-by-score` CLI参数

### Step 4: 集成分级审核流程
- 在 `review_golden_testset.py` 中实现 `run_tiered_review()`
- AI预审核 → 自动通过A级 → 交互式审核B/C级
- 审核结果持久化到 question.metadata

### Step 5: 端到端测试与验证
- 使用 `tests/fixtures/golden_qa.json` 进行功能验证
- 运行 `pixi run lint` 确保代码质量
- 运行 `pixi run test` 确保所有测试通过

---

## 四、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/ai_reviewer.py` | 新建 | AI预审核模块 |
| `scripts/pdf_viewer.py` | 新建 | PDF查看器+Chunk提取模块 |
| `scripts/review_golden_testset.py` | 修改 | 交互界面重构+新CLI参数+分级审核 |
| `tests/test_ai_reviewer.py` | 新建 | AI预审核测试 |
| `tests/test_pdf_viewer.py` | 新建 | PDF查看器测试 |
| `tests/test_golden_testset.py` | 修改 | 新增分级审核相关测试 |

---

## 五、技术决策说明

1. **LLM选型**：使用 `LongCat-Flash-Lite`（test_generation默认模型）进行AI审核，兼顾质量与成本
2. **PDF查看器**：优先支持 SumatraPDF（轻量、命令行友好），备选 Edge，兜底纯文本
3. **页面定位**：优先使用chunk的 `metadata.page_number`，其次用excerpt在pages.json中模糊匹配
4. **评分缓存**：AI审核结果写入 `question.metadata.ai_review`，避免重复API调用
5. **向后兼容**：所有新功能通过CLI参数启用，不影响现有审核流程
