# MVP RAG + Baseline 评测 - 任务清单

## 阶段 1：基础设施搭建

### 1.1 配置管理
- [ ] 创建 `config.yaml` 配置文件
- [ ] 创建 `.env.example` 环境变量模板
- [ ] 创建 `.env` 文件（用户自行填写 API Key）
- [ ] 实现配置加载工具函数（`src/utils.py`）

### 1.2 日志配置
- [ ] 配置 loguru 日志格式
- [ ] 设置日志文件输出路径
- [ ] 在 `src/utils.py` 中实现日志初始化函数

### 1.3 项目结构
- [ ] 创建 `src/` 目录及 `__init__.py`
- [ ] 创建 `eval/` 目录及 `__init__.py`
- [ ] 创建 `tests/` 目录及 `__init__.py`
- [ ] 创建 `notes/` 目录
- [ ] 创建 `data/parsed/` 目录
- [ ] 创建 `data/chunks/` 目录
- [ ] 创建 `data/vector_store/` 目录

---

## 阶段 2：数据准备

### 2.1 测试数据
- [ ] 准备 2-3 个金融研报 PDF 样本（放入 `data/raw/`）
- [ ] 记录测试数据来源和基本信息

---

## 阶段 3：Pipeline 模块开发

### 3.1 PDF 解析模块（src/parser.py）

**开发任务**：
- [ ] 实现 `parse_pdf()` 函数
- [ ] 实现 `parse_all_pdfs()` 函数
- [ ] 添加异常处理（文件不存在、解析失败）
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_parser.py`
- [ ] 测试正常 PDF 解析
- [ ] 测试文件不存在异常
- [ ] 测试解析失败异常
- [ ] 测试批量解析功能

**提交**：`feat: add PDF parser module`

---

### 3.2 分块模块（src/chunker.py）

**开发任务**：
- [ ] 实现 `chunk_text()` 函数
- [ ] 实现 `process_parsed_files()` 函数
- [ ] 集成 tiktoken 进行 token 计数
- [ ] 生成 chunk_id 和 metadata
- [ ] 添加异常处理
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_chunker.py`
- [ ] 测试固定长度分块
- [ ] 测试 token 计数准确性
- [ ] 测试 metadata 生成
- [ ] 测试边界情况（空文本、超长文本）
- [ ] 测试批量处理功能

**提交**：`feat: add chunker module`

---

### 3.3 Embedding 模块（src/embedder.py）

**开发任务**：
- [ ] 实现 `Embedder` 类
- [ ] 实现 `__init__()` 方法（加载模型）
- [ ] 实现 `embed_texts()` 方法（批量编码）
- [ ] 实现 `embed_query()` 方法（单个查询编码）
- [ ] 添加 GPU/CPU 设备选择
- [ ] 添加异常处理（模型加载失败）
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_embedder.py`
- [ ] 测试模型加载
- [ ] 测试单个文本编码
- [ ] 测试批量文本编码
- [ ] 测试向量维度正确性
- [ ] 测试异常处理

**提交**：`feat: add embedder module`

---

### 3.4 向量索引模块（src/indexer.py）

**开发任务**：
- [ ] 实现 `VectorIndexer` 类
- [ ] 实现 `__init__()` 方法（初始化 Qdrant 客户端）
- [ ] 实现 `create_collection()` 方法
- [ ] 实现 `index_chunks()` 方法
- [ ] 实现 `build_index()` 方法
- [ ] 实现 `delete_collection()` 方法（用于重建）
- [ ] 添加异常处理（连接失败、写入失败）
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_indexer.py`
- [ ] 测试 Qdrant 连接
- [ ] 测试集合创建
- [ ] 测试向量写入
- [ ] 测试索引构建
- [ ] 测试索引重建
- [ ] 测试异常处理

**提交**：`feat: add vector indexer module`

---

### 3.5 检索模块（src/retriever.py）

**开发任务**：
- [ ] 实现 `Retriever` 类
- [ ] 实现 `__init__()` 方法
- [ ] 实现 `retrieve()` 方法
- [ ] 实现相似度计算
- [ ] 返回 top-k 结果及分数
- [ ] 添加异常处理（查询失败）
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_retriever.py`
- [ ] 测试单个查询检索
- [ ] 测试 top-k 参数
- [ ] 测试返回结果格式
- [ ] 测试相似度分数范围
- [ ] 测试异常处理

**提交**：`feat: add retriever module`

---

### 3.6 LLM 生成模块（src/generator.py）

**开发任务**：
- [ ] 实现 `Generator` 类
- [ ] 实现 `__init__()` 方法（初始化 Anthropic 客户端）
- [ ] 实现 `generate()` 方法
- [ ] 设计 Prompt 模板
- [ ] 集成 LongCat API
- [ ] 添加异常处理（API 调用失败）
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_generator.py`
- [ ] 测试 LLM 客户端初始化
- [ ] 测试回答生成（使用 Mock）
- [ ] 测试 Prompt 构建
- [ ] 测试异常处理
- [ ] 测试 API 超时处理

**提交**：`feat: add LLM generator module`

---

### 3.7 完整流水线（src/pipeline.py）

**开发任务**：
- [ ] 实现 `RAGPipeline` 类
- [ ] 实现 `__init__()` 方法（加载所有模块）
- [ ] 实现 `query()` 方法（串联所有步骤）
- [ ] 实现 `build_index()` 方法
- [ ] 添加配置文件加载
- [ ] 添加异常处理
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_pipeline.py`
- [ ] 测试完整查询流程
- [ ] 测试索引构建流程
- [ ] 测试配置加载
- [ ] 测试端到端功能
- [ ] 测试异常处理

**提交**：`feat: add RAG pipeline module`

---

### 3.8 主入口（main.py）

**开发任务**：
- [ ] 实现 CLI 参数解析
- [ ] 实现 `--query` 命令
- [ ] 实现 `--build-index` 命令
- [ ] 实现 `--rebuild` 命令
- [ ] 实现 `--config` 参数
- [ ] 添加用户友好的输出格式
- [ ] 添加异常处理
- [ ] 添加日志记录

**测试任务**：
- [ ] 测试 CLI 参数解析
- [ ] 测试查询命令执行
- [ ] 测试索引构建命令
- [ ] 测试错误参数处理

**提交**：`feat: add main CLI entry point`

---

## 阶段 4：评测系统开发

### 4.1 测试集构建

**开发任务**：
- [ ] 设计测试问题模板
- [ ] 构建至少 20 个问答对
- [ ] 覆盖不同问题类型（事实提取、总结、对比、分析）
- [ ] 创建 `eval/test_data.json`
- [ ] 记录每个问题的期望答案和来源文档

**提交**：`feat: add evaluation test dataset`

---

### 4.2 检索指标计算

**开发任务**：
- [ ] 实现 `calculate_hit_rate()` 函数
- [ ] 实现 `calculate_mrr()` 函数
- [ ] 实现 `calculate_ndcg()` 函数
- [ ] 添加单元测试
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_retrieval_metrics.py`
- [ ] 测试 Hit Rate 计算
- [ ] 测试 MRR 计算
- [ ] 测试 NDCG 计算
- [ ] 测试边界情况

**提交**：`feat: add retrieval metrics calculation`

---

### 4.3 生成指标计算

**开发任务**：
- [ ] 集成 RAGAS 框架
- [ ] 实现 Faithfulness 指标计算
- [ ] 实现 Answer Relevancy 指标计算
- [ ] 添加异常处理
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_generation_metrics.py`
- [ ] 测试 Faithfulness 计算
- [ ] 测试 Answer Relevancy 计算
- [ ] 测试异常处理

**提交**：`feat: add generation metrics calculation`

---

### 4.4 评测脚本（eval/run_eval.py）

**开发任务**：
- [ ] 实现 `run_evaluation()` 函数
- [ ] 实现评测结果汇总
- [ ] 实现结果保存（JSON 格式）
- [ ] 添加进度条显示
- [ ] 添加异常处理
- [ ] 添加日志记录
- [ ] 添加类型标注和 docstring

**测试任务**：
- [ ] 创建 `tests/test_run_eval.py`
- [ ] 测试评测流程
- [ ] 测试结果保存
- [ ] 测试异常处理

**提交**：`feat: add evaluation script`

---

## 阶段 5：集成测试与调试

### 5.1 端到端测试
- [ ] 运行完整 Pipeline 构建
- [ ] 测试查询功能
- [ ] 测试评测流程
- [ ] 修复发现的 Bug

### 5.2 性能测试
- [ ] 测试 Embedding 生成速度
- [ ] 测试检索响应时间
- [ ] 测试 LLM 生成时间
- [ ] 记录性能基线

---

## 阶段 6：Baseline 评测

### 6.1 运行评测
- [ ] 确保测试 PDF 已放入 `data/raw/`
- [ ] 构建向量索引
- [ ] 运行评测脚本
- [ ] 保存评测结果

### 6.2 结果分析
- [ ] 分析检索质量指标
- [ ] 分析生成质量指标
- [ ] 识别主要问题
- [ ] 提出优化方向

### 6.3 文档编写
- [ ] 创建 `notes/baseline_results.md`
- [ ] 记录评测配置
- [ ] 记录评测结果
- [ ] 分析结果并给出结论
- [ ] 提出后续优化建议

**提交**：`docs: add baseline evaluation report`

---

## 阶段 7：代码质量检查

### 7.1 代码格式化
- [ ] 使用 autopep8 格式化所有代码
- [ ] 检查 import 顺序
- [ ] 移除无用 import

### 7.2 类型检查
- [ ] 检查所有公共函数的类型标注
- [ ] 运行 mypy 类型检查（如有配置）

### 7.3 文档检查
- [ ] 检查所有公共函数的 docstring
- [ ] 确保 docstring 包含 Args、Returns、Raises

### 7.4 测试覆盖
- [ ] 运行所有测试：`pixi run pytest tests/ -v`
- [ ] 确保所有测试通过
- [ ] 检查测试覆盖率（如有配置）

---

## 阶段 8：最终验收

### 8.1 功能验收
- [ ] `pixi run python main.py --query "..."` 能返回回答
- [ ] `pixi run python eval/run_eval.py` 能完成评测
- [ ] 所有测试通过

### 8.2 文档验收
- [ ] `notes/baseline_results.md` 包含完整评测报告
- [ ] 报告包含所有指标数值

### 8.3 代码质量验收
- [ ] 所有公共函数有类型标注
- [ ] 所有公共函数有 docstring
- [ ] 所有 IO 操作有异常处理
- [ ] 使用 loguru 记录日志
- [ ] 代码通过 autopep8 格式化

---

## 任务统计

- **总任务数**：约 150 个
- **预计时间**：5-7 天
- **关键里程碑**：
  1. 基础设施搭建完成
  2. Pipeline 所有模块开发完成
  3. 评测系统开发完成
  4. Baseline 评测完成
  5. 最终验收通过
