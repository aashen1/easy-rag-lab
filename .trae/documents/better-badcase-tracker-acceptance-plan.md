# Better Badcase Tracker 分支深度验收计划

> GLM-5

## 分支概览

**分支名称**: `better-badcase-tracker`  
**基准分支**: `dev`  
**提交数量**: 18 commits  
**代码变更**: +5600 / -137 行，涉及 31 个文件  
**主要功能**: CLI查询历史管理 + 多轮对话支持 + Bad Case深度分析系统

---

## 一、功能模块清单

### 1.1 CLI查询历史管理 (4 commits)

**提交范围**: `b215b64` ~ `bc81ab3`

**核心功能**:
- 环形历史缓冲区 (`src/query_history.py`)
- 持久化去重机制
- Badcase/Goodcase类型转换
- CLI命令: `--history-list`, `--history-save`, `--history-show`

**关键文件**:
- `src/query_history.py` (245行新增)
- `main.py` (集成历史命令)
- `config.yaml` (新增query_history配置节)

**验收要点**:
- [ ] 历史记录自动保存到 `data/query_history/`
- [ ] 环形淘汰机制正确（超出max_entries时删除最旧记录）
- [ ] 去重逻辑：同类型case不能重复保存
- [ ] 类型转换：badcase→goodcase 正确删除旧case并创建新case
- [ ] CLI命令输出格式符合设计文档

---

### 1.2 多轮对话支持 (5 commits)

**提交范围**: `3bd5004` ~ `6b8e1a0`

**核心功能**:
- Generator支持chat_history参数
- Pipeline透传chat_history
- Web UI和CLI均支持多轮对话
- Case存储支持chat_history

**关键文件**:
- `src/generator.py` (+51/-8)
- `src/pipeline.py` (+146/-1)
- `src/interactive_qa.py` (327行新增)
- `src/case_collector.py` (扩展save_case_with_dedup)

**验收要点**:
- [ ] Generator.generate(chat_history=[...]) 正确构建多轮prompt
- [ ] Pipeline.query(chat_history=[...]) 透传参数
- [ ] Web UI qa_demo.py 支持多轮对话
- [ ] CLI interactive_qa.py 支持多轮对话
- [ ] Case存储正确保存chat_history

---

### 1.3 Bad Case深度分析系统 (9 commits)

**提交范围**: `10a23c9` ~ `167c39a`

**核心功能**:
- Pipeline Trace捕获（5个阶段）
- Ground Truth标注
- 检索质量分析
- 根因自动诊断（6类：RC-0~RC-5）
- Streamlit分析UI

**关键文件**:
- `src/trace_models.py` (227行新增)
- `src/ground_truth_finder.py` (100行新增)
- `src/retrieval_analyzer.py` (157行新增)
- `src/case_diagnoser.py` (207行新增)
- `src/app_pages/case_analyzer.py` (464行新增)

**验收要点**:
- [ ] Pipeline.query(capture_trace=True) 正确捕获5个阶段
- [ ] Trace数据模型序列化/反序列化正确
- [ ] Ground Truth查找：精确匹配 + 模糊匹配回退
- [ ] 检索质量指标计算正确（8个指标）
- [ ] 根因诊断：6类分类逻辑正确
- [ ] Streamlit UI：5个视图正常工作
- [ ] 向后兼容：capture_trace=False 时行为不变

---

## 二、测试覆盖验收

### 2.1 新增测试文件

| 测试文件 | 行数 | 覆盖模块 |
|---------|------|---------|
| `tests/test_query_history.py` | 215 | query_history.py |
| `tests/test_interactive_qa.py` | 166 | interactive_qa.py |
| `tests/test_trace_models.py` | 260 | trace_models.py |
| `tests/test_ground_truth_finder.py` | 130 | ground_truth_finder.py |
| `tests/test_retrieval_analyzer.py` | 238 | retrieval_analyzer.py |
| `tests/test_case_diagnoser.py` | 245 | case_diagnoser.py |
| `tests/test_generator.py` | 121 | generator.py (chat_history) |
| `tests/test_case_collector.py` | 340 | case_collector.py (扩展) |

**验收命令**:
```bash
pixi run test-unit     # 快速单元测试
pixi run test          # 常规测试（排除integration/slow）
pixi run test-all      # 全量测试
```

**验收要点**:
- [ ] 所有单元测试通过
- [ ] 测试覆盖率 ≥ 80%（核心模块）
- [ ] 无跳过的测试（除非有明确理由）
- [ ] 边界情况测试完整（如空输入、异常情况）

---

## 三、代码质量验收

### 3.1 代码规范检查

**验收命令**:
```bash
pixi run lint          # 自动修复 + 检查
pixi run ruff-check    # 仅检查
```

**验收要点**:
- [ ] 无 lint 错误
- [ ] 无未使用的导入
- [ ] 代码格式符合 ruff 规范
- [ ] 无硬编码的配置项（应从config.yaml读取）

### 3.2 日志规范

**验收要点**:
- [ ] 使用 `loguru`，无 `print` 语句
- [ ] IO操作有 try/except 包裹
- [ ] 异常捕获后记录日志并优雅降级
- [ ] 公共函数有 docstring（功能、Args、Returns、Raises）

### 3.3 类型注解

**验收要点**:
- [ ] 函数签名有类型注解
- [ ] 复杂数据结构使用 dataclass 或 TypedDict
- [ ] Optional 类型正确标注

---

## 四、向后兼容性验收

### 4.1 API兼容性

**关键变更**:
- `RAGPipeline.query()` 新增 `capture_trace=False` 参数（默认值保证兼容）
- `Generator.generate()` 新增 `return_prompt_details=False` 参数（默认值保证兼容）
- `save_case()` 新增 `trace=None` 参数（默认值保证兼容）

**验收要点**:
- [ ] 现有调用代码无需修改即可运行
- [ ] 默认参数值保持原有行为
- [ ] 无破坏性变更

### 4.2 数据兼容性

**验收要点**:
- [ ] 旧版 case 数据可正常加载
- [ ] 新增字段有默认值，不影响旧数据读取
- [ ] manifest.json 格式向后兼容

---

## 五、文档完整性验收

### 5.1 规划文档

**已有文档**:
- `.trae/documents/cli-query-history-badcase-plan.md`
- `.trae/documents/cli-interactive-qa-enhancement.md`
- `.trae/documents/cli-multiturn-case-collection.md`
- `.trae/specs/bad-case-deep-analysis/spec.md`
- `.trae/specs/bad-case-deep-analysis/tasks.md`
- `.trae/specs/bad-case-deep-analysis/checklist.md`

**验收要点**:
- [ ] 所有规划文档与实现一致
- [ ] Spec中的所有Requirement已实现
- [ ] Tasks.md中的所有任务已完成
- [ ] Checklist.md中的所有检查项已通过

### 5.2 用户文档

**验收要点**:
- [ ] 是否需要更新 `docs/user-guides/` 下的文档？
- [ ] 是否需要新增功能使用说明？
- [ ] CLI命令是否有帮助文本？

---

## 六、性能影响评估

### 6.1 Trace捕获开销

**验收要点**:
- [ ] `capture_trace=False` 时无性能损失
- [ ] `capture_trace=True` 时性能影响可接受（< 10%）
- [ ] Trace数据存储空间合理

### 6.2 历史记录开销

**验收要点**:
- [ ] 历史记录写入不影响查询响应时间
- [ ] 环形淘汰机制正确，不会无限增长
- [ ] 磁盘占用在可接受范围

---

## 七、集成测试场景

### 7.1 端到端场景1：CLI查询历史流转

```bash
# 1. 执行单行查询
pixi run python main.py --query "茅台营收增长率是多少？"

# 2. 查看历史
pixi run python main.py --history-list

# 3. 保存为badcase
pixi run python main.py --history-save qh_0001 --case-type bad

# 4. 转换为goodcase
pixi run python main.py --history-save qh_0001 --case-type good
```

**验收要点**:
- [ ] 每步操作成功
- [ ] 去重和转换逻辑正确
- [ ] 数据持久化正确

### 7.2 端到端场景2：多轮对话

```bash
# 启动交互式问答
pixi run python main.py -i

# 多轮对话
>>> 茅台的主营业务是什么？
>>> 它的营收增长率呢？  # 应理解"它"指茅台
>>> 和五粮液比呢？      # 应理解对比意图
```

**验收要点**:
- [ ] chat_history正确传递
- [ ] 上下文理解正确
- [ ] Case收集支持多轮对话

### 7.3 端到端场景3：Bad Case深度分析

```bash
# 1. 启动Web UI
pixi run streamlit run src/app.py

# 2. 在问答页面提问并标记badcase
# 3. 切换到"🔍 Bad Case 分析" Tab
# 4. 选择刚才的badcase
# 5. 查看管线链路总览
# 6. 标注Ground Truth（选择PDF + 页码）
# 7. 查看诊断报告
```

**验收要点**:
- [ ] Trace数据正确捕获
- [ ] UI展示正常
- [ ] Ground Truth查找正确
- [ ] 诊断结果合理

---

## 八、验收执行计划

### Phase 1: 自动化检查（5分钟）

```bash
# 1. 代码规范
pixi run lint

# 2. 单元测试
pixi run test-unit

# 3. 常规测试
pixi run test
```

### Phase 2: 功能验收（30分钟）

按照第七节的集成测试场景逐一验证

### Phase 3: 文档验收（10分钟）

检查文档完整性和一致性

### Phase 4: 性能评估（10分钟）

评估性能影响和资源占用

### Phase 5: 兼容性验收（5分钟）

验证向后兼容性

---

## 九、验收通过标准

### 必须项（阻塞合并）

- [ ] 所有单元测试通过
- [ ] 无 lint 错误
- [ ] 向后兼容性验证通过
- [ ] 核心功能端到端测试通过
- [ ] Spec中的所有Requirement已实现

### 建议项（不阻塞合并）

- [ ] 测试覆盖率 ≥ 80%
- [ ] 性能影响 < 10%
- [ ] 文档完整且与实现一致
- [ ] 无技术债务标记

---

## 十、风险与注意事项

### 10.1 已知风险

1. **Trace数据量**: 长期运行后可能占用大量磁盘空间
   - 建议：定期清理或设置上限

2. **多轮对话上下文**: 长对话可能导致token超限
   - 建议：实现上下文窗口管理

3. **Ground Truth标注**: 依赖用户手动标注，可能不准确
   - 建议：考虑半自动标注辅助

### 10.2 待优化项

1. Trace数据可考虑压缩存储
2. 诊断规则可配置化（目前硬编码）
3. 历史记录可支持导出功能

---

## 十一、验收报告模板

验收完成后，填写以下报告：

```markdown
# Better Badcase Tracker 分支验收报告

**验收人**: 
**验收时间**: 
**验收结果**: ✅ 通过 / ❌ 不通过

## 一、自动化检查结果

- Lint: ✅/❌
- 单元测试: ✅/❌ (通过率: XX/XX)
- 常规测试: ✅/❌

## 二、功能验收结果

- CLI查询历史: ✅/❌
- 多轮对话: ✅/❌
- Bad Case深度分析: ✅/❌

## 三、问题清单

| 序号 | 问题描述 | 严重程度 | 状态 |
|------|---------|---------|------|
| 1    | ...     | 高/中/低 | 待修复/已修复 |

## 四、建议

...

## 五、结论

该分支可以/不可以合并到dev分支。
```

---

## 附录：提交历史完整清单

```
167c39a docs: badcase tracker plan and spec docs
7d8d92b fix: add root cause label to case list and update smoke test tab count
17f62af style: ruff format case_analyzer.py
925c121 feat: add retrieval analyzer and root cause diagnoser for bad cases
7edd546 feat: extend case storage with trace/ground_truth/diagnosis and add chunk finder
10a23c9 feat: add pipeline trace capture for bad case deep analysis
c22c704 feat: enhance CLI interactive Q&A with multi-turn dialogue support and case collection
c668b9a fix: update pipeline test assertion to include chat_history=None parameter
6b8e1a0 test: add tests for chat_history, save_case_with_dedup, and interactive_qa
119f27c feat: refactor Web UI qa_demo to use save_case_with_dedup and pass chat_history for multi-turn
3c2664e feat: move _interactive_qa to src/interactive_qa.py with multi-turn chat and enhanced case collection
6287147 feat: add chat_history parameter to RAGPipeline.query() and pass through to generator
82959eb feat: add chat_history support to Generator.generate() for multi-turn conversations
3bd5004 feat: add save_case_with_dedup shared dedup function and chat_history support to save_case/load_case
d58c8a7 docs: implement CLI query history management and case conversion functionality
bc81ab3 feat: integrate query history into CLI and add --history-* commands with dedup/conversion
4d3d7cf feat: add delete_case, convert_case, find_case_by_question to case_collector
b215b64 feat: add QueryHistory ring buffer for CLI single-query mode
```
