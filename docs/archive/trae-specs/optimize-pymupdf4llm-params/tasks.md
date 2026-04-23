# Tasks

- [x] Task 1: 修复 pipeline.py 的 parser_options 传递
  - [x] 1.1: 在 `RAGPipeline.build_index()` 中为 `parse_all_pdfs()` 添加 `parser_options=parser_config.get("pymupdf4llm")` 参数
  - [x] 1.2: 编写测试验证 pipeline 构建索引时 parser_options 被正确传递

- [x] Task 2: 修正 config.yaml 中无效的 ignore_images 配置
  - [x] 2.1: 移除 `ignore_images: true`，添加注释说明 Layout 模式下图片处理行为
  - [x] 2.2: 验证 `write_images: false` 已足够控制图片输出

- [x] Task 3: 扩展 parser config hash 包含 options
  - [x] 3.1: 修改 `compute_parser_config_hash()` 将 `options` 纳入 hash 计算
  - [x] 3.2: 修改 `_build_config_snapshot_and_hashes()` 在 parser 快照中包含 options
  - [x] 3.3: 编写测试验证不同 options 产生不同 hash

- [x] Task 4: 扩展 parse_pdf() 支持 page_chunks
  - [x] 4.1: 添加 `page_chunks: bool = False` 参数，返回类型改为 `str | list[dict]`
  - [x] 4.2: 更新 docstring 说明 page_chunks 参数和返回值
  - [x] 4.3: 编写测试验证 page_chunks=True 返回 list[dict]，page_chunks=False 返回 str

- [x] Task 5: 扩展 parse_all_pdfs() 处理页级输出
  - [x] 5.1: 当 parser_options 中 page_chunks=True 时，输出文件扩展名改为 `.pages.json`
  - [x] 5.2: 实现 `.pages.json` 的 JSON 序列化（包含 text、metadata、toc_items、tables）
  - [x] 5.3: 修改跳过逻辑：page_chunks=True 时检查 `.pages.json` 是否存在
  - [x] 5.4: 编写测试验证 `.pages.json` 输出格式和跳过逻辑

- [x] Task 6: 实现 chunk_text_page_aware()
  - [x] 6.1: 在 chunker.py 中新增 `chunk_text_page_aware()` 函数
  - [x] 6.2: 每页独立分块，chunk_id 格式为 `{source_name}_p{page_number}_{chunk_index:03d}`
  - [x] 6.3: 每个 chunk 的 metadata 包含 `page_number` 字段
  - [x] 6.4: 空页跳过逻辑
  - [x] 6.5: 编写测试验证页感知分块行为

- [x] Task 7: 实现 process_parsed_files_page_aware()
  - [x] 7.1: 在 chunker.py 中新增 `process_parsed_files_page_aware()` 函数
  - [x] 7.2: 扫描 `.pages.json` 文件，调用 `chunk_text_page_aware()` 分块
  - [x] 7.3: 输出 JSONL 中 chunk 的 strategy 为 `"page_aware_fixed"`，metadata 包含 `page_number`
  - [x] 7.4: 编写测试验证 `.pages.json` → JSONL 的完整流程

- [x] Task 8: 更新 meal.py 支持页感知分块
  - [x] 8.1: 修改 `build_chunks_if_needed()` 检测 `.pages.json` 文件，选择对应分块流程
  - [x] 8.2: 更新 `expected_md_names` 逻辑以适配 `.pages.json` 命名
  - [x] 8.3: 编写测试验证 meal 构建流程的页感知路径

- [x] Task 9: 更新 pipeline.py 支持页感知分块路径
  - [x] 9.1: 在 `build_index()` 中检测解析结果格式，选择对应分块流程
  - [x] 9.2: 更新 source_filter 逻辑以适配 `.pages.json` 文件
  - [x] 9.3: 编写测试验证 pipeline 的页感知分块路径

- [x] Task 10: 精调 config.yaml 参数
  - [x] 10.1: 添加 `page_chunks: true`、`ignore_code: true`、`force_text: true`、`ocr_language: "chi_sim+eng"`、`show_progress: true`
  - [x] 10.2: `page_separators` 改为 `false`（与 page_chunks=True 联动）
  - [x] 10.3: 验证参数组合在 Layout 模式下的实际效果

# Task Dependencies

- Task 1 → Task 4（先修复 bug，再扩展功能）
- Task 2 → Task 3（先修正配置，再扩展 hash）
- Task 4 → Task 5（parse_pdf 扩展是 parse_all_pdfs 扩展的前置）
- Task 5 → Task 6（parse_all_pdfs 输出 .pages.json 是页感知分块的前置）
- Task 6 → Task 7（chunk_text_page_aware 是 process_parsed_files_page_aware 的前置）
- Task 7 → Task 8, Task 9（分块函数实现后才能集成到 meal 和 pipeline）
- Task 3 → Task 8（hash 扩展需在 meal 集成前完成）
- Task 10 可与 Task 4-9 并行（参数精调独立于代码变更）
