# Checklist

## 解析器抽象层

- [x] `BaseParser` ABC 定义了 `name` 属性和 `parse()` 抽象方法
- [x] `ParsedPage` dataclass 包含 `page_number`（1-indexed）、`text`（Markdown）、`metadata`
- [x] `ParseResult` dataclass 包含 `pages: list[ParsedPage]` 和 `metadata: dict`
- [x] `ParserRegistry` 支持 `register()`、`get()`、`list_names()` 方法
- [x] `ParserRegistry.get("unknown")` 抛出 `ValueError` 并列出已注册名称
- [x] `ParserRegistry` 默认注册了 `"pymupdf4llm"` 和 `"fitz_pdfplumber"`

## PymuPDF4LLMParser 适配器

- [x] `PymuPDF4LLMParser.parse()` 委托调用 `pymupdf4llm.to_markdown()`
- [x] 整篇模式：返回 `ParseResult` 包含单个 `ParsedPage(page_number=1)`
- [x] page_chunks 模式：每页映射为独立 `ParsedPage`，携带 `page_number`
- [x] pymupdf4llm 专属参数（header, footer, table_strategy 等）正确透传
- [x] `name` 属性返回 `"pymupdf4llm"`

## FitzPdfPlumberParser 实现

- [x] 使用 `fitz.Page.get_text("dict")` 提取文本块，保留字体元信息
- [x] 基于 span `size` 和 `flags`（bold bit）检测标题层级，生成 Markdown 标题标记
- [x] 页眉页脚过滤：基于 y 坐标区域 + 正则模式匹配
- [x] 多栏布局检测：分析 bbox x 坐标分布，双栏按左→右→y 排序
- [x] 图片占位：输出 `[图片: 页{N}]` 标记
- [x] `name` 属性返回 `"fitz_pdfplumber"`

## pdfplumber 表格补强

- [x] 使用 `pdfplumber.Page.find_tables()` 提取表格
- [x] 表格转 Markdown：处理合并单元格（None 填充）、列数对齐
- [x] 文本块与表格合并：基于 bbox 重叠度替换 fitz 文本块
- [x] 支持可配置的表格策略（lines / text）和容差参数
- [x] pdfplumber 提取失败时静默降级，不影响主流程

## 配置文件

- [x] `config.yaml` 新增 `fitz_pdfplumber` 配置块，含合理默认值
- [x] `algorithm` 默认值为 `"pymupdf4llm"`（向后兼容）
- [x] 配置加载后各解析器专属配置可正确解析

## Meal 管线集成

- [x] `compute_parser_config_hash()` 将 `algorithm` + `options` 纳入 hash
- [x] 旧配置（仅 algorithm 无 options）的 hash 与旧版一致
- [x] `ArtifactCache.get_parsed_dir()` 支持 `parser_hash` 参数，目录为 `parsed_{parser_hash}/`
- [x] 不提供 `parser_hash` 时使用默认 `parsed/` 目录（向后兼容）
- [x] `create_meal()` 通过 `ParserRegistry` 获取解析器并调用 `parse()`
- [x] `repair_meal()` 同步使用 `ParserRegistry`
- [x] `build_chunks_if_needed()` 能正确读取新格式的解析产物

## A/B 对比实验框架

- [x] 不同 `algorithm` 配置创建的 Meal 可共享相同 PDF 文件集和测试集
- [x] Meal 的 `config_snapshot.parser.algorithm` 可区分解析器
- [x] 实验配置 `config_overrides` 可覆盖 `parser.algorithm`

## 测试与质量

- [x] 所有新增模块有对应的 pytest 测试（59 tests passed）
- [x] `pixi run ruff check src/parsers/` 通过（新增代码无 lint 错误）
- [x] 向后兼容：使用旧配置运行 Meal 创建流程行为不变
