# v0.1.16 验收报告

> 版本主题：诊得明 | 日期：2026-05-04

## 版本概况

| 指标 | 数值 |
|------|------|
| 起止时间 | 2026-05-01 → 2026-05-04 |
| Commit 数 | 132 |
| 文件变更 | 185 files, +29,203 / -1,539 行 |
| 新增源码 | 34 个（src/ + eval/） |
| 新增测试 | 15 个 |
| Commit 类型 | feat:41, fix:37, docs:27, chore/style:12, refactor:6, test:6, perf:3 |

## L1: 代码质量

- [ ] `pixi run lint` 通过
- [ ] `pixi run test-all` 全绿

## L2: 归档完整性

- [x] .trae/documents/ 32 个 plan 文档全部归档到 docs/.archive/v0.1.16-diagnosis-era/
- [x] .trae/specs/ 12 个 spec 文档全部归档（按主题聚合）
- [x] 逐文件 diff 验证：44 文件全部 OK，无 MISSING、无 DIFF
- [x] 无重复文件（specs/ 扁平目录已清理）

## L3: 文档更新

- [x] version-history.md 新增 v0.1.16 章节
- [x] CHANGELOG.md 补充 v0.1.15 + 新增 v0.1.16
- [x] CLAUDE.md 版本号更新至 v0.1.16

## 四个故事线验收

### 故事线 1：Bad Case 闭环分析

| 组件 | 文件 | 状态 |
|------|------|------|
| Case 收集 | src/case_collector.py | 已实现 |
| Pipeline Trace | src/trace_models.py | 已实现 |
| Case 诊断 | src/case_diagnoser.py | 已实现 |
| 检索分析 | src/retrieval_analyzer.py | 已实现 |
| Ground Truth 定位 | src/ground_truth_finder.py | 已实现 |
| 查询历史 | src/query_history.py | 已实现 |
| 交互问答 | src/interactive_qa.py | 已实现 |
| Case Analyzer 页面 | src/app_pages/case_analyzer.py | 已实现 |
| 多轮对话 | chat_history 贯穿 Pipeline→Generator | 已实现 |

### 故事线 2：混合解析链路

| 组件 | 文件 | 状态 |
|------|------|------|
| CompositeParser | src/parsers/composite_parser.py | 已实现 |
| FitzParser | src/parsers/fitz_parser.py | 已实现 |
| PdfPlumberEnhancer | src/parsers/pdfplumber_enhancer.py | 已实现 |
| Parser Benchmark | eval/parser_benchmark/ | 已实现 |
| 默认链路确定 | pymupdf4llm + pdfplumber(text), OCR off | 已验证 |

### 故事线 3：实验系统增强

| 组件 | 文件 | 状态 |
|------|------|------|
| 报告复用 | src/experiment_reuse.py | 已实现 |
| 429 退避 | src/llm_retry.py | 已实现 |
| 缓存校验 | prepare_meal config_hashes 检查 | 已修复 |
| 日志修复 | setup_logger 生命周期管理 | 已修复 |

### 故事线 4：管线入口整合

| 组件 | 文件 | 状态 |
|------|------|------|
| TestSetComposer | src/testset_composer.py | 已实现 |
| testset_review | src/testset_review/ | 已实现 |
| testset_cli | src/testset_cli/ | 已实现 |
| Meal 系统统一 | get_or_create_full_meal() | 已实现 |
