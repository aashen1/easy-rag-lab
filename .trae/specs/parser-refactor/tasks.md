# Tasks

## Phase 1: 架构重构 — 两步链路解耦

- [x] Task 1: 新增 TableEnhancer 抽象基类
  - [x] SubTask 1.1: 在 `src/parsers/base.py` 中添加 `TableEnhancer` ABC，定义 `name` 属性和 `enhance(pdf_path, result)` 抽象方法
  - [x] SubTask 1.2: 更新 `src/parsers/__init__.py` 导出 `TableEnhancer`
  - [x] SubTask 1.3: 编写 `TableEnhancer` 的单元测试

- [x] Task 2: 拆出 FitzParser 主力解析器
  - [x] SubTask 2.1: 创建 `src/parsers/fitz_parser.py`，从 `fitz_pdfplumber_parser.py` 搬运 fitz 文本提取逻辑（`_extract_page_blocks`, `_detect_columns`, `_is_noise`, `_detect_heading`, `_blocks_to_markdown` 及 `_TextBlock` 数据类）
  - [x] SubTask 2.2: FitzParser 不包含任何 pdfplumber 相关代码（`_extract_tables_with_pdfplumber`, `_merge_text_and_tables`, `_table_to_markdown`）
  - [x] SubTask 2.3: FitzParser 支持配置化逻辑模块开关（header_filter, footer_filter, column_detection 等）
  - [x] SubTask 2.4: 编写 FitzParser 单元测试（复用 fitz_pdfplumber 的测试用例，验证纯文本输出一致）

- [x] Task 3: 拆出 PdfPlumberEnhancer 表格补强模块
  - [x] SubTask 3.1: 创建 `src/parsers/pdfplumber_enhancer.py`，从 `fitz_pdfplumber_parser.py` 搬运 pdfplumber 表格提取逻辑（`_extract_tables_with_pdfplumber`, `_table_to_markdown`, `_merge_text_and_tables`, `_bbox_overlap`）
  - [x] SubTask 3.2: PdfPlumberEnhancer 继承 `TableEnhancer`，实现 `enhance` 方法：检测主力结果中的 markdown 表格 → 用 pdfplumber 重新提取 → 质量过滤 → 替换
  - [x] SubTask 3.3: 支持完整配置参数（strategy, table_settings, quality_filter, replace_policy）
  - [x] SubTask 3.4: 编写 PdfPlumberEnhancer 单元测试

- [x] Task 4: 新建 CompositeParser 组合解析器
  - [x] SubTask 4.1: 创建 `src/parsers/composite_parser.py`，实现 `CompositeParser(BaseParser)`
  - [x] SubTask 4.2: `name` 属性返回 `"{primary_name}+{enhancer_name}"`
  - [x] SubTask 4.3: `parse` 方法先执行主力解析，再调用补强模块的 `enhance`
  - [x] SubTask 4.4: 编写 CompositeParser 单元测试

- [x] Task 5: 重构 ParserRegistry 双注册表
  - [x] SubTask 5.1: 在 `registry.py` 中新增 `_primaries` 和 `_enhancers` 两个注册表
  - [x] SubTask 5.2: 新增 `get(primary, enhancer, primary_config, enhancer_config)` 类方法
  - [x] SubTask 5.3: 保留旧 `get(name, config)` 接口作为向后兼容（`fitz_pdfplumber` → `primary="fitz" + enhancer="pdfplumber"`）
  - [x] SubTask 5.4: 新增 `list_primaries()` 和 `list_enhancers()` 方法
  - [x] SubTask 5.5: 更新 lazy import 映射，添加 `fitz` → `FitzParser`、`pdfplumber` → `PdfPlumberEnhancer`
  - [x] SubTask 5.6: 编写 Registry 重构的单元测试

- [x] Task 6: 适配上游代码
  - [x] SubTask 6.1: 更新 `src/parser.py` 支持新配置格式（`parser.primary` + `parser.table_enhancer`），向后兼容旧格式
  - [x] SubTask 6.2: 更新 `src/meal/hashes.py` 的 `compute_parser_config_hash` 适配新配置格式
  - [x] SubTask 6.3: 更新 `src/meal/manager.py` 的 `_build_config_snapshot_and_hashes` 和 `_parse_pdfs_with_registry` 适配新配置格式
  - [x] SubTask 6.4: 更新 `src/parsers/__init__.py` 导出新类

- [x] Task 7: 更新 config.yaml 配置格式
  - [x] SubTask 7.1: 将 `parser.algorithm` 改为 `parser.primary`，新增 `parser.table_enhancer`
  - [x] SubTask 7.2: 将 `parser.fitz_pdfplumber` 拆为 `parser.fitz` 和 `parser.pdfplumber` 两个独立配置段
  - [x] SubTask 7.3: 保留旧字段作为注释说明迁移方式

- [x] Task 8: 保留 fitz_pdfplumber_parser.py 为兼容层
  - [x] SubTask 8.1: 修改 `FitzPdfPlumberParser` 内部委托给 `CompositeParser(FitzParser, PdfPlumberEnhancer)`，保持对外接口不变
  - [x] SubTask 8.2: 验证 `fitz_pdfplumber` 的解析结果与重构前一致

- [x] Task 9: 更新测试
  - [x] SubTask 9.1: 更新 `tests/test_parsers_fitz_pdfplumber.py` 适配新架构
  - [x] SubTask 9.2: 更新 `tests/test_parsers_pymupdf4llm.py` 适配新架构
  - [x] SubTask 9.3: 更新 `tests/test_parsers_base.py` 添加 TableEnhancer 测试
  - [x] SubTask 9.4: 更新 `tests/test_parser_unified.py` 适配新配置格式
  - [x] SubTask 9.5: 运行 `pixi run test` 确保所有测试通过

## Phase 2: 解析器评测系统

- [x] Task 10: 创建评测模块目录结构
  - [x] SubTask 10.1: 创建 `eval/parser_benchmark/__init__.py`
  - [x] SubTask 10.2: 创建 `eval/parser_benchmark/runner.py` — 评测运行器
  - [x] SubTask 10.3: 创建 `eval/parser_benchmark/metrics.py` — 自动指标计算
  - [x] SubTask 10.4: 创建 `eval/parser_benchmark/test_cases.py` — 测试用例管理
  - [x] SubTask 10.5: 创建 `eval/parser_benchmark/report_generator.py` — 报告生成

- [x] Task 11: 实现评测运行器
  - [x] SubTask 11.1: 加载评测配置 YAML，解析 pipelines 和 test_pdfs
  - [x] SubTask 11.2: 对每个 pipeline + test_pdf 组合运行解析，存储结果
  - [x] SubTask 11.3: 支持增量运行（基于 config hash 跳过已有结果）
  - [x] SubTask 11.4: 生成 manifest.json 记录评测元数据

- [x] Task 12: 实现自动评测指标
  - [x] SubTask 12.1: 实现 Markdown 合法性检查（解析 markdown 表格语法）
  - [x] SubTask 12.2: 实现表格统计指标（检出数、行数、列数、空值率）
  - [x] SubTask 12.3: 指标计算需要 ground truth 标注数据支持，初始版本先实现无 ground truth 的统计指标

- [x] Task 13: 实现报告生成
  - [x] SubTask 13.1: 生成各 pipeline 的 JSON 结果文件
  - [x] SubTask 13.2: 生成对比报告 markdown
  - [x] SubTask 13.3: 保存解析样本（每个 pipeline 的 markdown 输出）

- [x] Task 14: 创建入口脚本和配置
  - [x] SubTask 14.1: 创建 `eval/run_parser_benchmark.py` 入口脚本
  - [x] SubTask 14.2: 创建 `parser_configs/baseline.yaml` 基线评测配置（6-12 种典型组合）
  - [x] SubTask 14.3: 在 `pixi.toml` 中添加 `parser-bench` task
  - [x] SubTask 14.4: 编写评测模块的单元测试

## Phase 3: 集成验证

- [x] Task 15: 端到端验证
  - [x] SubTask 15.1: 使用 badcase PDF 运行 `pixi run parser-bench baseline.yaml`，验证评测流程完整
  - [x] SubTask 15.2: 验证 `pixi run test` 全部通过
  - [x] SubTask 15.3: 验证 `pixi run lint` 无报错

# Task Dependencies

- Task 1 (TableEnhancer 基类) → Task 3 (PdfPlumberEnhancer), Task 4 (CompositeParser)
- Task 2 (FitzParser) → Task 4 (CompositeParser), Task 5 (Registry), Task 8 (兼容层)
- Task 3 (PdfPlumberEnhancer) → Task 4 (CompositeParser), Task 5 (Registry), Task 8 (兼容层)
- Task 4 (CompositeParser) → Task 5 (Registry)
- Task 5 (Registry 重构) → Task 6 (上游适配)
- Task 6 (上游适配) → Task 7 (config.yaml), Task 9 (测试更新)
- Task 7 (config.yaml) → Task 9 (测试更新)
- Task 8 (兼容层) → Task 9 (测试更新)
- Phase 1 全部完成 → Phase 2 (评测系统)
- Task 10 (目录结构) → Task 11, 12, 13
- Task 11 (运行器) → Task 14 (入口脚本)
- Task 12 (指标) → Task 13 (报告)
- Task 13 (报告) → Task 14 (入口脚本)
- Phase 2 全部完成 → Task 15 (端到端验证)
