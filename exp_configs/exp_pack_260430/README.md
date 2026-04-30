# RAG系统对比实验配置集

> 本目录包含一套系统性的RAG对比实验配置，用于探究不同优化技术对问答质量的影响。

---

## 📋 实验配置概览

| 配置文件 | 实验主题 | 变体数 | 测试题数 | 预计耗时 | 运行命令 |
|---------|---------|-------|---------|---------|---------|
| `00_smoke_all_variants.yaml` | 冒烟测试（所有变体） | 20 | 3 | ~2分钟 | `pixi run exp resume_study/00_smoke_all_variants` |
| `01_chunking_strategy.yaml` | 分块策略对比 | 12 | 50 | ~15分钟 | `pixi run exp resume_study/01_chunking_strategy` |
| `02_retrieval_method.yaml` | 检索方式对比 | 12 | 50 | ~15分钟 | `pixi run exp resume_study/02_retrieval_method` |
| `03_reranker_effect.yaml` | 重排序效果验证 | 12 | 50 | ~15分钟 | `pixi run exp resume_study/03_reranker_effect` |
| `04_query_rewrite.yaml` | 查询改写对比 | 12 | 50 | ~15分钟 | `pixi run exp resume_study/04_query_rewrite` |
| `05_optimal_combination.yaml` | 最优组合探索 | 16 | 100 | ~30分钟 | `pixi run exp resume_study/05_optimal_combination` |

---

## 🎯 配置设计思路

### 1. 冒烟测试（00_smoke_all_variants.yaml）

**目的**：用最小数据量快速验证所有配置的正确性。

**设计原则**：
- **最小数据**：3题，约1分钟完成
- **最大覆盖**：20个变体，覆盖所有优化维度
- **快速验证**：确保所有配置语法正确、能正常运行

**适用场景**：
- 验证实验环境配置
- 测试新的优化技术
- CI/CD流水线中的自动化测试

---

### 2. 分块策略对比（01_chunking_strategy.yaml）

**核心问题**：
1. chunk_size多大最合适？
2. overlap能带来多少提升？
3. 语义分块 vs 固定分块哪个更好？

**实验设计**：
```
固定变量：vector检索，topk=5，无rerank
变化变量：chunk_size, chunk_overlap, chunker.strategy
```

**变体分组**：
- **基线组**：标准配置（512/0）
- **chunk_size对比**：256/512/768/1024
- **overlap对比**：0/32/64/128
- **语义分块对比**：threshold=0.3/0.5/0.7
- **组合探索**：小块+重叠、大块+重叠

**预期发现**：
- chunk_size=512可能是平衡点
- overlap=64可能有边际收益
- 语义分块在推理型问题上可能更好

**简历价值**：⭐⭐⭐⭐⭐
- 展示对RAG基础组件的深入理解
- 可以量化分块策略对性能的影响
- 适合写技术博客或论文

---

### 3. 检索方式对比（02_retrieval_method.yaml）

**核心问题**：
1. 纯向量 vs 纯BM25 vs 混合检索，哪个更好？
2. RRF融合 vs 加权融合，哪个更优？
3. 混合检索的权重如何配置？

**实验设计**：
```
固定变量：fixed/512/o0
变化变量：retrieval.method, hybrid.fusion, hybrid.*_weight
```

**变体分组**：
- **单一检索**：vector, bm25
- **RRF融合**：rrf_k=30/60/100
- **加权融合**：vector_weight=0.3/0.5/0.7
- **top_k影响**：top_k=3/5/10
- **BM25参数**：k1=1.2/2.0

**预期发现**：
- 混合检索应该优于单一检索
- RRF可能比加权融合更稳定
- vector_weight=0.7可能是最佳权重

**简历价值**：⭐⭐⭐⭐⭐
- 展示对检索算法的深入理解
- 可以量化混合检索的增量价值
- 适合技术决策文档

---

### 4. 重排序效果验证（03_reranker_effect.yaml）

**核心问题**：
1. Reranker能带来多少性能提升？
2. top_n参数如何选择？
3. Reranker与不同检索方式的交互效应？

**实验设计**：
```
固定变量：fixed/512/o0
变化变量：reranker.enabled, reranker.top_n, retrieval.method
```

**变体分组**：
- **基线组**：无重排序（vector/bm25/hybrid）
- **top_n对比**：top_n=3/5/7
- **检索方式组合**：vector+rerank, bm25+rerank, hybrid+rerank
- **候选集大小**：top_k=5/10/15
- **分块策略组合**：小块+rerank, 大块+rerank

**预期发现**：
- Reranker应该能显著提升MRR
- top_n=3可能是最佳值
- 在混合检索上效果可能更好

**简历价值**：⭐⭐⭐⭐
- 展示对重排序技术的理解
- 可以量化Reranker的增量价值
- 适合优化现有系统

---

### 5. 查询改写对比（04_query_rewrite.yaml）

**核心问题**：
1. HyDE vs Multi-Query，哪个效果更好？
2. 查询改写适用于什么场景？
3. 查询改写的成本效益如何？

**实验设计**：
```
固定变量：fixed/512/o0
变化变量：query_rewrite.strategy, query_rewrite.num_queries
```

**变体分组**：
- **基线组**：无查询改写
- **HyDE策略**：hyde+vector, hyde+hybrid, hyde+rerank
- **Multi-Query策略**：num_queries=2/3/5
- **组合探索**：multi_query+hybrid, multi_query+rerank
- **分块策略组合**：hyde+小块, hyde+大块

**预期发现**：
- HyDE可能在推理型问题上更好
- Multi-Query可能在召回不足时更好
- 查询改写会增加Token消耗

**简历价值**：⭐⭐⭐⭐
- 展示对查询理解技术的理解
- 可以对比两种主流策略
- 适合成本效益分析

---

### 6. 最优组合探索（05_optimal_combination.yaml）

**核心问题**：
1. 最佳配置组合是什么？
2. 组合优化的边际收益如何？
3. 成本效益最优的配置是什么？

**实验设计**：
```
递进式增加优化组件，观察边际收益
```

**变体分组**：
- **L0裸基线**：无优化
- **L1分块优化**：overlap, semantic
- **L2检索优化**：hybrid, hybrid+overlap
- **L3重排序优化**：rerank, hybrid+rerank
- **L4查询改写优化**：hyde, hybrid+rerank+hyde
- **L5全链路优化**：overlap+hybrid+rerank+hyde, semantic+hybrid+rerank+hyde
- **性价比配置**：低成本、中等成本
- **特殊配置**：精准配置、召回配置

**预期发现**：
- 组合优化应该有边际收益递减
- 中等复杂度配置可能性价比最高
- 全链路优化效果最好但成本也最高

**简历价值**：⭐⭐⭐⭐⭐
- 展示系统优化能力
- 可以找到最佳配置
- 适合生产环境部署

---

## 🚀 使用建议

### 1. 实验执行顺序

**推荐顺序**：
```
1. 冒烟测试 → 验证环境配置
2. 分块策略 → 理解基础影响
3. 检索方式 → 探索检索优化
4. 重排序效果 → 验证重排价值
5. 查询改写 → 测试查询优化
6. 最优组合 → 找到最佳配置
```

### 2. 实验规模建议

| 实验类型 | 测试集大小 | 变体数量 | 预计耗时 | Token成本 |
|---------|-----------|---------|---------|----------|
| 冒烟测试 | 3题 | 20个 | ~2分钟 | 极低 |
| 专题实验 | 50题 | 12个 | ~15分钟 | 中等 |
| 组合实验 | 100题 | 16个 | ~30分钟 | 较高 |

### 3. 成本控制建议

1. **先用冒烟测试验证**：确保配置正确
2. **分批运行实验**：避免一次性消耗过多Token
3. **使用 `metrics_preset: "core"`**：减少LLM调用
4. **利用缓存机制**：避免重复计算

---

## 📊 实验报告撰写建议

### 1. 报告结构

```markdown
# RAG系统优化技术对比实验报告

## 1. 实验背景与目标
## 2. 实验设计
## 3. 实验结果
   3.1 分块策略对比
   3.2 检索方式对比
   3.3 重排序效果
   3.4 查询改写对比
   3.5 最优组合探索
## 4. 关键发现
## 5. 结论与建议
```

### 2. 可视化建议

1. **性能对比柱状图**：各变体的Hit Rate/MRR/Faithfulness对比
2. **参数敏感性曲线**：chunk_size/top_k对性能的影响趋势
3. **问题类型热力图**：不同优化技术在不同问题类型上的表现
4. **成本效益散点图**：性能提升 vs Token消耗
5. **递进增强阶梯图**：每层优化的边际收益

### 3. 简历呈现建议

```
项目经历：
- 金融研报RAG问答系统（2024.03-至今）
  - 设计并实现完整的RAG评测体系，支持双评测引擎（自研+RAGAS）
  - 系统性对比8种优化技术（分块策略、检索方式、重排序、查询改写等）
  - 通过消融实验量化各组件贡献，混合检索比纯向量检索提升23% MRR
  - 发现最优配置组合，Faithfulness达到0.92，Answer Relevancy达到0.85
  - 技术栈：Python, PyTorch, Qdrant, BGE Embedding, BGE Reranker
```

---

## 🔧 高级用法

### 1. 自定义实验配置

可以基于这些配置进行修改：

```yaml
# 修改测试集大小
test_sets:
  - name: "custom_30q"
    generation:
      num_questions: 30  # 改为30题

# 修改采样比例
data:
  create_if_missing:
    sample_ratio: 0.1  # 改为10%采样

# 添加新的变体
variants:
  - name: "my_custom_variant"
    description: "我的自定义配置"
    config_overrides:
      chunker:
        chunk_size: 384  # 自定义chunk_size
```

### 2. 组合多个实验

可以创建一个总控配置，组合多个专题：

```yaml
# exp_configs/resume_study/master_all.yaml
name: "master_all_experiments"
description: "运行所有专题实验"

# 这里可以引用其他配置文件
# 或者直接复制所有变体
```

### 3. 生成LLM增强报告

```bash
# 运行实验并生成LLM增强报告
pixi run exp resume_study/01_chunking_strategy --llm-report
```

---

## 📚 相关文档

- [实验评测系统使用指南](../../docs/user-guides/experiment-system.md)
- [评测指标详解](../../docs/user-guides/evaluation-metrics.md)
- [RAG优化实现详解](../../docs/dev-guides/rag-optimization-implementation.md)
- [RAG泛超参数使用指南](../../docs/user-guides/hyperparameter-guide.md)

---

## 💡 常见问题

### Q1: 为什么冒烟测试用3题？

A: 3题足够验证配置正确性，同时保持极低的运行成本。如果配置有误，可以快速发现并修复。

### Q2: 为什么专题实验用50题？

A: 50题是中等规模，既能保证结果的统计显著性，又不会消耗太多时间和Token。

### Q3: 为什么组合实验用100题？

A: 组合实验是最终验证，需要更大规模的数据来确保结果的可靠性。

### Q4: 如何选择运行哪个实验？

A:
- 如果时间紧张，只运行冒烟测试和最优组合探索
- 如果想深入理解，按顺序运行所有专题
- 如果只想看最终结果，直接运行最优组合探索

### Q5: 实验结果如何解读？

A:
- 关注Hit Rate和MRR（检索质量）
- 关注Faithfulness和Answer Relevancy（生成质量）
- 对比不同变体的差异，找到最优配置

---

## 📝 更新日志

- 2026-04-30: 创建初始配置集，包含6个实验配置
