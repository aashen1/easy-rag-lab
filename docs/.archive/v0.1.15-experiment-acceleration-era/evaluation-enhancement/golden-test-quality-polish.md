# Golden Test 生成质量打磨计划

## 问题评估

基于 20 题试跑结果，5 个问题按修复信心排序：

| # | 问题             | 信心  | 根因                                                                       |
| - | -------------- | --- | ------------------------------------------------------------------------ |
| 1 | 专有名词分词 bug     | ⭐⭐⭐ | 正则 `[\u4e00-\u9fff]{2,8}` 不允许数字开头，"3月银行理财市场"被拆成"3"+"月银行理财市场"             |
| 2 | missing 类型生成低效 | ⭐⭐⭐ | 已有专用方法 `_generate_missing_question` + `MISSING_INDEPENDENT_PROMPT` 但未被调用 |
| 3 | 数值幻觉只警告不拦截     | ⭐⭐⭐ | `_validate_answer_evidence_consistency` 只记录 issues 不拒绝，问题照样入库            |
| 4 | 年报文档零覆盖        | ⭐⭐  | round-robin 分配时文档列表顺序固定，20 题只触及前 20 个文档（全是研报）                            |
| 5 | 表格 Markdown 残渣 | ⭐⭐  | 根因在解析阶段：pymupdf4llm 输出退化表格行，解析器无后处理；在解析阶段清理即可                            |

***

## 修复步骤

### Step 1: 修复专有名词分词 bug

**文件**: `src/test_generation/validators.py` 第 274-290 行

**问题**:

* 专有名词正则 `[\u4e00-\u9fff]{2,8}(?:股份|集团|公司|行业|市场|技术|产品|业务)` 要求以中文字符开头

* "3月银行理财市场" 以数字开头，正则匹配不到完整词

* 数字提取正则把 "3" 从 "3月银行理财市场" 中剥离，剩下 "月银行理财市场" 被错误匹配

**修复方案**:

1. 专有名词正则改为允许数字开头：`[\d\u4e00-\u9fff]{2,8}(?:股份|集团|公司|行业|市场|技术|产品|业务)`
2. 数字提取时排除 "数字+月/年/季度" 等时间表达式，避免将 "3月" 中的 "3" 当作裸数字提取
3. 在专有名词匹配时增加"去数字前缀"的回退匹配：如果 "3月银行理财市场" 整体不在证据中，去掉数字前缀后检查 "月银行理财市场" 是否在证据中（因为证据中可能以 "3月银行理财市场" 形式存在）

**测试**: 更新 `tests/test_golden_testset.py` 添加分词边界测试

***

### Step 2: 启用 missing 类型专用生成方法

**文件**: `src/test_generation/generator.py` 第 2062-2205 行

**问题**:

* `_generate_missing_question` 方法已定义但未被调用

* missing 类型仍走 `_generate_question_with_evidence`（使用 `EVIDENCE_AWARE_PROMPT`），该 prompt 要求 LLM 基于证据生成问题，与 missing "不应有证据" 的定义矛盾

* 导致 LLM 反复为 missing 问题生成 evidence，触发重试循环

**修复方案**:

1. 在 `_generate_hybrid_question` 中，当 `question_type == "missing"` 时，调用 `_generate_missing_question` 而非 `_generate_question_with_evidence`
2. 保持现有的重试逻辑（如果 missing 问题有 evidence 则重试）

**测试**: 验证 missing 类型问题生成成功率提升、重试次数下降

***

### Step 3: 数值幻觉从"警告"升级为"拦截"

**文件**: `src/test_generation/generator.py` 第 1700-1730 行附近

**问题**:

* `_validate_answer_evidence_consistency` 返回 `(is_valid, issues)`

* 当前代码只将 issues 记录到 `metadata.answer_evidence_issues`，不拒绝问题入库

* 导致 golden\_005 中 "21,093""25,043""35%" 等编造数值照样入库

**修复方案**:

1. 在 `generate_golden_testset` 主循环中，当 `_validate_answer_evidence_consistency` 返回 `is_valid=False` 时，将该问题标记为"需重试"
2. 增加 `max_evidence_issues` 阈值（默认 3），超过则拒绝入库
3. 对数值类 issue（`数值 'xxx' 未在证据中找到`）单独计数，数值幻觉 > 1 个即拒绝
4. 保留原有 warning 日志，同时增加 rejection 日志

**测试**: 验证有数值幻觉的问题被拒绝、重试后生成合规问题

***

### Step 4: 文档分配时随机打乱顺序

**文件**: `src/test_generation/generator.py` 第 3232-3256 行

**问题**:

* `_distribute_questions_across_docs` 使用 round-robin，文档列表顺序固定

* 20 题只触及前 20 个文档，恰好全是研报

* 年报文档排在后面，永远轮不到

**修复方案**:

1. 在 `_distribute_questions_across_docs` 中，使用 seed 对 `doc_names` 做 shuffle 后再 round-robin
2. seed 来自 `generate_golden_testset` 的参数，保证可复现

**测试**: 验证不同 seed 下文档覆盖更均匀

***

### Step 5: 退化表格清理 — 可配置开关

**文件**: `src/parsers/pymupdf4llm_parser.py` + `config.yaml` + `scripts/generate_golden_testset.py`

**问题**:

* PDF 解析后表格变成 Markdown 残渣（如 `|||||2023-2025中国生物制药交易数量|||`）

* 根因：pymupdf4llm 遇到复杂/退化表格时，只输出管道符 `|` 而没有实际内容

* 当前解析器无后处理，残渣原样透传到 chunk → 生成阶段

**修复方案**（双层设计：解析层治本 + 生成层可开关）:

#### 层1：解析器增加退化表格清理（治本）

1. 在 `PyMuPDF4LLMParser.parse()` 返回结果前，对每页 text 做退化表格清理
2. 清理规则：

   * 检测 markdown 表格块（连续的 `|` 开头行）

   * 对表格块内的每一行，检查单元格是否有实际内容（非空、非纯 `-`）

   * 移除所有单元格为空的退化行（如 `|||||`）

   * 如果整个表格的所有数据行都是退化行，移除整个表格

   * 保留有实际内容的表格行（如 `| 项目 | 2023 | 2024 |`）
3. 清理逻辑提取为独立函数 `clean_degenerate_tables(text: str) -> str`，放在 `src/parsers/pymupdf4llm_parser.py` 中

#### 层2：配置开关穿透到 exp\_config（可 A/B 测试）

1. `config.yaml` 新增配置项：

   ```yaml
   parser:
     pymupdf4llm:
       clean_degenerate_tables: true   # 新增：清理退化表格行
   ```
2. `PyMuPDF4LLMParser.__init__()` 从 config 中读取 `clean_degenerate_tables`，不在 `self._options` 中透传给 pymupdf4llm（这是我们的后处理选项，不是 pymupdf4llm 的参数）
3. `parse()` 方法根据该选项决定是否调用 `clean_degenerate_tables()`
4. 实验配置可通过 `config_overrides` 覆盖：

   ```yaml
   variants:
     - name: "no_table_cleaning"
       config_overrides:
         parser:
           pymupdf4llm:
             clean_degenerate_tables: false
   ```
5. CLI 脚本增加 `--no-clean-degenerate-tables` 参数，方便命令行 A/B 测试

**不丢数据保证**：

* 只移除单元格全部为空的退化行，有内容的表格行完整保留

* 开关关闭时行为与修改前完全一致

**测试**: 验证退化表格行被清理、有内容表格行保留、开关可切换

***

## 不修的项

无——5 个问题全部纳入计划，按信心从高到低执行。

***

## 验证方式

每步修复后：

1. 运行 `pixi run lint` 确保代码格式合规
2. 运行 `pixi run python -m pytest tests/test_golden_testset.py -v` 确保测试通过
3. 重新生成 20 题 golden test 对比修复前后质量指标
