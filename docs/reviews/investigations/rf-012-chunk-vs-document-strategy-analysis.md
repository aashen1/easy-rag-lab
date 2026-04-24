# Chunk-based 策略 vs Document 策略：问题生成质量对比分析

> 创建日期: 2026-04-24
> 关联 Issue: RF-012（旧格式 test_sets DeprecationWarning 清理）
> 代码来源: [src/test_generator.py](../../src/test_generator.py)

---

## 1. 背景

RF-012 原计划清理旧格式 test_sets 的 DeprecationWarning，移除 `factual`/`boundary`/`multi_hop` 三种 chunk-based 策略的兼容代码。但在分析中发现，这三种策略在特定场景下具有 document 策略无法替代的优势，不应简单删除，而应保留并改进。

---

## 2. 两种策略体系概览

### 2.1 Chunk-based 策略（旧策略）

| 策略 | 输入粒度 | 选择逻辑 | Prompt 特点 |
|------|---------|---------|------------|
| `factual` | 单个 chunk | 随机选取 | 直接基于 chunk 文本生成事实性问题 |
| `boundary` | 2 个相邻 chunk | 选取 chunk_index 连续的对 | 要求问题需同时参考两个片段 |
| `multi_hop` | 2 个非相邻 chunk | 同文档中间隔 2-4 的 chunk 对 | 要求综合多个片段信息 |

### 2.2 Document 策略（新策略）

| 维度 | 说明 |
|------|------|
| 输入粒度 | 完整 MD 文档（截断至 8000 字符） |
| 选择逻辑 | 按文档轮询分配问题类型 |
| 问题类型 | 6 种：single_fact(30%)、multi_fact(25%)、reasoning(15%)、comparative(15%)、missing(10%)、irrelevant(5%) |
| 质量控制 | 真实性检查（过滤学术化表述、模板化开头、过长问题）+ 质量指标 |

---

## 3. 核心差异分析

### 3.1 信息粒度：Chunk 级 vs 文档级

| 维度 | Chunk-based | Document |
|------|------------|----------|
| **输入上下文** | 精确的 chunk 文本（通常 500-2000 字） | 全文档截断（前 8000 字符） |
| **信息密度** | 高——LLM 聚焦于少量文本 | 低——LLM 需从大量文本中提取 |
| **上下文完整性** | 可能缺失上下文 | 保留完整上下文 |
| **与 chunk_size 的关系** | 强耦合 | 完全解耦 |

**关键洞察**：Chunk-based 策略的"强耦合"既是缺点也是优点——它天然地测试了 RAG 系统在特定分块粒度下的检索能力。

### 3.2 问题生成方式对比

**Chunk-based（factual 为例）**：
```
输入: 单个 chunk 的完整文本
Prompt: "根据以下文本片段，生成一个可以用该文本直接回答的事实性问题"
输出: {"question": "...", "answer": "...", "difficulty": "easy"}
```

**Document（single_fact 为例）**：
```
输入: 完整文档（截断至 8000 字符）
Prompt: "你是一位金融行业从业者...请生成一个【单知识点查询】类型的问题"
输出: {"question": "...", "answer": "...", "question_type": "...", "difficulty": "...", "reasoning": "...", "key_entities": [...], "answer_sources": [...]}
```

### 3.3 问题质量维度对比

| 质量维度 | Chunk-based | Document | 分析 |
|---------|------------|----------|------|
| **真实性** | ❌ 学术化、考试题风格 | ✅ 口语化、真实用户场景 | Document 策略有真实性检查机制 |
| **答案可定位性** | ✅ 精确到 chunk | ⚠️ 需事后匹配（`_locate_answer_chunks`） | Chunk-based 天然知道答案来自哪个 chunk |
| **检索难度可控性** | ✅ 可精确控制 | ❌ 不可控 | Chunk-based 可设计跨 chunk 问题测试检索 |
| **chunk_size 敏感度** | ✅ 天然反映分块效果 | ❌ 完全忽略分块边界 | 这是 chunk-based 的核心价值 |
| **问题多样性** | ❌ 仅 3 种类型 | ✅ 6 种类型 + 自定义分布 | Document 策略更丰富 |
| **边界情况覆盖** | ✅ boundary 策略专测边界 | ❌ 无专门边界测试 | Chunk-based 独有能力 |
| **拒答能力测试** | ❌ 不支持 | ✅ missing + irrelevant 类型 | Document 策略独有 |

---

## 4. Chunk-based 策略的不可替代优势

### 4.1 Boundary 策略：分块边界测试的唯一手段

`boundary` 策略是目前系统中**唯一**能系统性测试"信息被 chunk 边界切断"场景的方法。

```python
# boundary 策略的核心逻辑
for i in range(len(chunks) - 1):
    idx_i = chunks[i].get("metadata", {}).get("chunk_index", i)
    idx_next = chunks[i + 1].get("metadata", {}).get("chunk_index", i + 1)
    if idx_next == idx_i + 1:
        pairs.append([chunks[i], chunks[i + 1]])
```

这种测试对 RAG 系统至关重要：
- 分块边界是信息丢失的主要风险点
- 不同的 chunk_size 和 overlap 参数会显著影响边界处的信息完整性
- 只有基于实际 chunk 边界生成的问题，才能真实评估系统在边界场景下的表现

### 4.2 Factual 策略：chunk_size 敏感度测试

`factual` 策略虽然简单，但它直接反映了"在当前 chunk_size 下，单个 chunk 是否包含足够信息来回答问题"。

- 当 chunk_size 过小时，factual 问题可能无法从单个 chunk 中获得完整答案 → 暴露分块过细的问题
- 当 chunk_size 合适时，factual 问题应能被准确回答 → 验证分块粒度适当
- 这种"分块粒度验证"能力是 document 策略无法提供的

### 4.3 Multi-hop 策略：跨 chunk 检索能力测试

`multi_hop` 策略测试的是"需要从文档不同部分检索信息"的场景，与 document 策略的 `multi_fact` 类型有重叠，但关键区别在于：

- multi_hop 的问题**必然需要跨 chunk 检索**（因为输入就是非相邻 chunk）
- multi_fact 的问题可能只需要一次检索就能获得完整上下文（因为输入是全文档）

---

## 5. 当前 Chunk-based 策略的问题

### 5.1 与 chunk_size 强耦合

这是被标记为"已弃用"的主要原因。当 chunk_size 变化时：
- factual 策略可能选到信息不足的 chunk
- boundary 策略的相邻对可能完全改变
- multi_hop 策略的间距语义会变化

### 5.2 问题风格不够真实

Prompt 设计偏向"考试题"风格：
- "请根据以下文本片段，生成一个可以用该文本直接回答的事实性问题"
- 缺少真实性检查机制

### 5.3 缺少质量控制

没有 document 策略中的真实性检查、质量指标等机制。

---

## 6. 改进方案：Chunk-aware 策略

基于以上分析，建议不是删除 chunk-based 策略，而是将其升级为 **chunk-aware 策略**，核心改进是增加 chunk 智能判断：

### 6.1 核心改进：Chunk 语义完整性判断

```python
def _is_chunk_semantically_complete(self, chunk: dict) -> bool:
    """判断 chunk 是否语义完整，值得生成问题。

    检查规则：
    1. 文本长度 > 最小阈值（如 100 字符）
    2. 不以省略号或不完整句子结尾
    3. 包含至少一个完整句子（以句号/问号/感叹号结尾）
    4. 信息密度检查：包含数字、专有名词或领域术语
    """
    text = chunk.get("text", "")

    if len(text) < 100:
        return False

    if text.rstrip().endswith(("...", "…", "等", "包括")):
        return False

    has_complete_sentence = bool(re.search(r'[。！？]', text))
    if not has_complete_sentence:
        return False

    has_info_density = bool(re.search(r'\d|[\u4e00-\u9fff]{2,}(?:公司|技术|市场|增长|收入)', text))
    return has_info_density
```

### 6.2 策略升级映射

| 旧策略 | 升级策略 | 改进点 |
|--------|---------|--------|
| `factual` | `chunk_factual` | 增加 chunk 完整性过滤 + 真实性检查 |
| `boundary` | `chunk_boundary` | 增加 chunk 对语义关联性判断 + 真实性检查 |
| `multi_hop` | `chunk_multi_hop` | 增加 chunk 间距智能调整（根据 chunk_size 自适应）+ 真实性检查 |

### 6.3 自适应 chunk 间距

```python
def _adaptive_hop_distance(self, chunks: list[dict], base_distance: int = 3) -> int:
    """根据 chunk_size 自适应调整 multi_hop 的跳转距离。

    chunk_size 小 → 增大跳转距离（确保真正跨主题）
    chunk_size 大 → 减小跳转距离（避免跳过太多内容）
    """
    avg_chunk_size = sum(len(c.get("text", "")) for c in chunks) / len(chunks)

    if avg_chunk_size < 500:
        return base_distance + 2
    elif avg_chunk_size > 2000:
        return max(base_distance - 1, 2)
    return base_distance
```

### 6.4 统一真实性检查

将 document 策略的 `_check_authenticity_rules` 和 `_validate_question_quality` 复用到 chunk-aware 策略中，确保所有策略生成的问题风格一致。

---

## 7. 结论与建议

### 7.1 RF-012 处置建议

| 项目 | 建议 |
|------|------|
| **优先级** | 从"待处理"降级为"低优先级/暂缓" |
| **DeprecationWarning** | 保留，但修改措辞——从"即将移除"改为"即将升级" |
| **代码清理** | 暂不删除旧策略代码，等待 chunk-aware 策略实现后统一替换 |
| **下一步** | 将 chunk-aware 策略作为新 feature 规划 |

### 7.2 两种策略的定位

| 策略 | 定位 | 适用场景 |
|------|------|---------|
| **Document** | 主力策略 | 评测整体问答质量、真实用户场景模拟 |
| **Chunk-aware**（待实现） | 专项策略 | 评测分块效果、检索精度、边界处理能力 |

两种策略**互补而非替代**。Document 策略评测"系统能否回答真实问题"，Chunk-aware 策略评测"系统的分块和检索是否合理"。

### 7.3 实施路线

1. **短期**：保留旧策略代码，修改 DeprecationWarning 措辞
2. **中期**：实现 chunk-aware 策略（含 chunk 完整性判断、自适应间距、真实性检查）
3. **长期**：旧策略迁移到 chunk-aware 策略后，再清理旧代码

---

## 附录：代码位置索引

| 组件 | 文件 | 行号 |
|------|------|------|
| 旧策略 Prompt | [test_generator.py](../../src/test_generator.py#L18-L64) | 18-64 |
| 旧策略 chunk 选择 | [test_generator.py](../../src/test_generator.py#L528-L637) | 528-637 |
| 旧策略问题生成 | [test_generator.py](../../src/test_generator.py#L639-L700) | 639-700 |
| Document 策略 Prompt | [test_generator.py](../../src/test_generator.py#L66-L118) | 66-118 |
| Document 策略问题生成 | [test_generator.py](../../src/test_generator.py#L761-L989) | 761-989 |
| 真实性检查 | [test_generator.py](../../src/test_generator.py#L1497-L1538) | 1497-1538 |
| 质量验证 | [test_generator.py](../../src/test_generator.py#L1468-L1495) | 1468-1495 |
| 答案 chunk 定位 | [test_generator.py](../../src/test_generator.py#L1575-L1677) | 1575-1677 |
