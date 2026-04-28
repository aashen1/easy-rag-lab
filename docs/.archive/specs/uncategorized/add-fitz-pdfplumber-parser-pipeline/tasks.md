# Tasks

- [x] Task 1: 创建解析器抽象基类与数据结构
  - [x] SubTask 1.1: 创建 `src/parsers/__init__.py`
  - [x] SubTask 1.2: 创建 `src/parsers/base.py`
  - [x] SubTask 1.3: 创建 `src/parsers/registry.py`
  - [x] SubTask 1.4: 编写 `tests/test_parsers_base.py`

- [x] Task 2: 实现 PymuPDF4LLMParser 适配器
  - [x] SubTask 2.1: 创建 `src/parsers/pymupdf4llm_parser.py`
  - [x] SubTask 2.2: 支持 `page_chunks=True` 模式
  - [x] SubTask 2.3: 支持透传 pymupdf4llm 专属参数
  - [x] SubTask 2.4: 编写 `tests/test_parsers_pymupdf4llm.py`

- [x] Task 3: 实现 FitzPdfPlumberParser 核心逻辑
  - [x] SubTask 3.1: 创建 `src/parsers/fitz_pdfplumber_parser.py`
  - [x] SubTask 3.2: 实现文本提取
  - [x] SubTask 3.3: 实现标题检测
  - [x] SubTask 3.4: 实现页眉页脚过滤
  - [x] SubTask 3.5: 实现多栏布局检测
  - [x] SubTask 3.6: 实现图片占位
  - [x] SubTask 3.7: 编写 `tests/test_parsers_fitz_pdfplumber.py`

- [x] Task 4: 实现 pdfplumber 表格补强
  - [x] SubTask 4.1: 实现 `_extract_tables_with_pdfplumber()` 方法
  - [x] SubTask 4.2: 实现表格转 Markdown
  - [x] SubTask 4.3: 实现文本块与表格合并
  - [x] SubTask 4.4: 支持可配置的 pdfplumber 表格策略
  - [x] SubTask 4.5: 编写测试

- [x] Task 5: 扩展配置文件结构
  - [x] SubTask 5.1: 在 `config.yaml` 新增 `fitz_pdfplumber` 配置块
  - [x] SubTask 5.2: 确保 `algorithm` 默认值为 `"pymupdf4llm"`

- [x] Task 6: 修改 Meal 管线集成
  - [x] SubTask 6.1: 修改 `compute_parser_config_hash()`
  - [x] SubTask 6.2: 修改 `ArtifactCache.get_parsed_dir()`
  - [x] SubTask 6.3: 修改 `_build_config_snapshot_and_hashes()`
  - [x] SubTask 6.4: 修改 `create_meal()` 使用 ParserRegistry
  - [x] SubTask 6.5: 修改 `repair_meal()` 使用 ParserRegistry
  - [x] SubTask 6.6: `build_chunks_if_needed()` 兼容新格式
  - [x] SubTask 6.7: 验证 parser hash 计算、artifact 目录隔离

- [x] Task 7: 端到端验证与集成测试
  - [x] SubTask 7.1: fitz_pdfplumber 解析器处理金融 PDF 成功
  - [x] SubTask 7.2: pymupdf4llm 解析器处理同一 PDF 成功
  - [x] SubTask 7.3: 两种解析器 config hash 不同，产物可隔离
  - [x] SubTask 7.4: 向后兼容验证通过
  - [x] SubTask 7.5: `pixi run ruff check src/parsers/` 通过

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 3]
- [Task 5] depends on [Task 1]
- [Task 6] depends on [Task 1, Task 2, Task 3, Task 5]
- [Task 7] depends on [Task 6]
- [Task 2] and [Task 3] can be parallelized
