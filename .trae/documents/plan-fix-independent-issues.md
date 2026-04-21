# 修复独立 Issue 实施计划

> 根据 `independent-issues-for-current-tasks.md` 文档分析，按优先级依次修复 4 个独立 issue

---

## Issue 1: RF-004 — 硬编码配置值提取到 config.yaml（优先级最高）

### 问题描述

以下文件中存在大量硬编码的配置值（model_name, base_url, temperature, max_tokens），应统一提取到 `config.yaml`：

| 文件 | 硬编码内容 |
|------|-----------|
| `eval/metrics/generation.py` | model_name="LongCat-Flash-Lite", base_url, temperature, max_tokens |
| `eval/metrics/llm_retrieval.py` | model_name="LongCat-Flash-Lite", base_url, temperature, max_tokens |
| `eval/experiment_reporter.py` | model_name="LongCat-Flash-Lite", base_url, temperature, max_tokens |
| `src/test_generator.py` | temperature=0.7, max_tokens=512/1024, system_prompt |

### 实施步骤

#### Step 1: 扩展 config.yaml 配置结构

在 `config.yaml` 中新增 `llm_evaluator` 和 `test_generation` 配置段：

```yaml
# LLM 评测器配置（用于 metrics 计算）
llm_evaluator:
  model_name: "LongCat-Flash-Lite"
  base_url: "https://api.longcat.chat/anthropic"
  # statement 提取
  extract_statements:
    temperature: 0.0
    max_tokens: 1024
  # statement 验证
  verify_statements:
    temperature: 0.0
    max_tokens: 1024
  # faithfulness 评估
  faithfulness:
    temperature: 0.0
    max_tokens: 512
  # answer relevancy 评估
  answer_relevancy:
    temperature: 0.0
    max_tokens: 512
  # context precision
  context_precision:
    temperature: 0.0
    max_tokens: 256
  # context recall
  context_recall:
    temperature: 0.0
    max_tokens: 256
  # context relevance 判断
  context_relevance:
    temperature: 0.0
    max_tokens: 256
  # 可推断性判断
  infer_check:
    temperature: 0.0
    max_tokens: 64
  # 报告生成
  report_generation:
    model_name: "LongCat-Flash-Lite"
    temperature: 0.3
    max_tokens: 4096

# 测试集生成配置
test_generation:
  model_name: "LongCat-Flash-Lite"
  temperature: 0.7
  max_tokens: 1024
  supplement_max_tokens: 1024
  initial_max_tokens: 512
  system_prompt: "..." # 提取 system prompt
```

#### Step 2: 修改 `eval/metrics/generation.py`

- 新增 `_get_eval_config()` 辅助函数，从 config.yaml 读取 llm_evaluator 配置
- 修改 `_extract_statements()` 函数，使用配置替代硬编码值
- 修改 `_verify_statements()` 函数，使用配置替代硬编码值
- 修改 `calculate_faithfulness()` 函数，使用配置替代硬编码值
- 修改 `calculate_answer_relevancy()` 函数，使用配置替代硬编码值

#### Step 3: 修改 `eval/metrics/llm_retrieval.py`

- 新增 `_get_eval_config()` 辅助函数，从 config.yaml 读取 llm_evaluator 配置
- 修改 `_judge_context_relevance()` 函数，使用配置替代硬编码值
- 修改 `calculate_context_precision()` 函数，使用配置替代硬编码值
- 修改 `_can_infer_from_context()` 函数，使用配置替代硬编码值
- 修改 `calculate_context_recall()` 函数，使用配置替代硬编码值

#### Step 4: 修改 `eval/experiment_reporter.py`

- 查找 report 生成中硬编码的 LLM 调用
- 修改为从 config.yaml 的 `llm_evaluator.report_generation` 读取配置

#### Step 5: 修改 `src/test_generator.py`

- 修改 `TestSetGenerator.__init__()` 方法，从 config.yaml 读取 test_generation 配置
- 修改 `generate_document_based_questions()` 方法，使用配置替代硬编码值
- 修改 `supplement_document_based_questions()` 方法，使用配置替代硬编码值
- 修改 `_generate_single_document_question()` 方法，使用配置替代硬编码值

#### Step 6: 测试验证

- 运行现有测试，确保配置提取后功能正常
- 检查是否有任何遗漏的硬编码值

---

## Issue 2: OPT-003 — 问题生成 token 消耗优化

### 问题描述

`src/test_generator.py` 中每个问题生成消耗 5-6k token，主要原因：
- 每次输入完整 MD 文档
- 无缓存机制
- prompt 可能过长

### 实施步骤

#### Step 1: 分析 token 消耗热点

- 审查 `test_generator.py` 中生成问题的完整流程
- 识别 token 消耗最大的环节（通常是输入文档 + prompt）

#### Step 2: 实现文档内容缓存

- 为已处理的文档内容添加缓存机制
- 避免同一文档重复发送到 LLM

#### Step 3: 优化 prompt 长度

- 审查 system prompt 和用户 prompt，精简冗余描述
- 将 system prompt 提取到配置，方便调整

#### Step 4: 添加 token 使用统计

- 在生成过程中记录 token 消耗
- 输出统计信息，便于评估优化效果

#### Step 5: 测试验证

- 对比优化前后的 token 消耗

---

## Issue 3: INV-012 — 测试体系深度审查

### 问题描述

`tests/` 目录中有 883 条测试，需要审查：
- 是否存在重复测试
- 是否存在无意义测试
- 集成测试的必要性评估

### 实施步骤

#### Step 1: 审查测试目录结构

- 列出 `tests/` 下所有测试文件
- 分类统计：单元测试、集成测试、冒烟测试

#### Step 2: 识别重复测试

- 查找功能重叠的测试
- 识别测试相同场景的多个用例

#### Step 3: 评估测试价值

- 标记无断言或断言薄弱的测试
- 评估集成测试是否可以简化为单元测试

#### Step 4: 输出审查报告

- 生成测试审查报告，列出建议删除/合并/保留的测试
- 等待确认后执行清理

---

## Issue 4: FEAT-019 — .trae 目录归档机制

### 问题描述

`.trae/documents/` 和 `.trae/specs/` 中的已完成 plan/spec 需要定期归档到 `docs/archive/`

### 实施步骤

#### Step 1: 创建归档脚本

- 编写 `scripts/archive-trae-docs.py` 脚本
- 将 `.trae/documents/*.md` 和 `.trae/specs/*.md` 移动到 `docs/archive/`

#### Step 2: 创建归档目录结构

- 创建 `docs/archive/` 目录
- 按日期或类别组织归档文件

#### Step 3: 测试归档脚本

- 运行脚本，验证归档结果
- 确保原始文件被正确移动

---

## 执行顺序

1. **RF-004** → 立即开始（最高优先级）
2. **OPT-003** → RF-004 完成后开始
3. **INV-012** → 只读分析，可随时插入
4. **FEAT-019** → 文档操作，可与其他任务并行

每个 issue 完成后立即提交。
