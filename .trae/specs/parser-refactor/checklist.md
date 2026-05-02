# Checklist

## Phase 1: 架构重构

- [x] `TableEnhancer` 抽象基类已添加到 `src/parsers/base.py`，包含 `name` 属性和 `enhance` 抽象方法
- [x] `TableEnhancer` 已在 `src/parsers/__init__.py` 中导出
- [x] `FitzParser` 已创建于 `src/parsers/fitz_parser.py`，仅包含 fitz 文本提取逻辑，不含 pdfplumber 代码
- [x] `FitzParser` 支持配置化逻辑模块开关（header_filter, footer_filter, column_detection 等）
- [x] `PdfPlumberEnhancer` 已创建于 `src/parsers/pdfplumber_enhancer.py`，继承 `TableEnhancer`
- [x] `PdfPlumberEnhancer.enhance()` 实现精准触发（无表格页面跳过）、质量过滤、表格替换
- [x] `PdfPlumberEnhancer` 支持完整配置参数（strategy, table_settings, quality_filter）
- [x] `CompositeParser` 已创建于 `src/parsers/composite_parser.py`，继承 `BaseParser`
- [x] `CompositeParser.name` 返回 `"{primary}+{enhancer}"` 格式
- [x] `CompositeParser.parse()` 先执行主力解析再调用补强
- [x] `ParserRegistry` 已重构为双注册表（`_primaries` + `_enhancers`）
- [x] `ParserRegistry.get(primary, enhancer, ...)` 新接口可用
- [x] `ParserRegistry.get(name, config)` 旧接口向后兼容（`fitz_pdfplumber` → fitz + pdfplumber）
- [x] `ParserRegistry.list_primaries()` 和 `list_enhancers()` 方法可用
- [x] `src/parser.py` 已适配新配置格式，向后兼容旧格式
- [x] `src/meal/hashes.py` 的 `compute_parser_config_hash` 已适配新配置格式
- [x] `src/meal/manager.py` 的配置读取已适配新格式
- [x] `config.yaml` 已更新为新格式（primary + table_enhancer），旧字段有迁移注释
- [x] `FitzPdfPlumberParser` 已改为兼容层，内部委托 CompositeParser
- [x] `fitz_pdfplumber` 解析结果与重构前一致

## Phase 1: 测试

- [x] `tests/test_parsers_base.py` 包含 TableEnhancer 测试
- [x] `tests/test_parsers_fitz_pdfplumber.py` 已适配新架构
- [x] `tests/test_parsers_pymupdf4llm.py` 已适配新架构
- [x] `tests/test_parser_unified.py` 已适配新配置格式
- [x] `pixi run test` 全部通过

## Phase 2: 评测系统

- [x] `eval/parser_benchmark/` 目录结构已创建（__init__.py, runner.py, metrics.py, test_cases.py, report_generator.py）
- [x] 评测运行器可加载 YAML 配置并运行所有 pipeline
- [x] 评测运行器支持增量运行（基于 config hash 跳过已有结果）
- [x] 自动指标已实现：Markdown 合法性、表格统计（检出数、行数、列数、空值率）
- [x] 报告生成器可输出 JSON 结果和 Markdown 对比报告
- [x] 解析样本已保存（每个 pipeline 的 markdown 输出）
- [x] `eval/run_parser_benchmark.py` 入口脚本可用
- [x] `parser_configs/baseline.yaml` 基线评测配置已创建
- [x] `pixi.toml` 中已添加 `parser-bench` task
- [x] 评测模块有对应单元测试

## Phase 3: 集成验证

- [x] `pixi run parser-bench baseline.yaml` 可完整运行并生成报告
- [x] `pixi run test` 全部通过
- [x] `pixi run lint` 无报错
