# Streamlit Web Demo 实验计划书

<!-- status: active -->

> 创建时间：2026-04-27
> 目标：为 Easy RAG Lab 项目添加 Web 可视化界面，提升简历展示效果

---

## 一、项目现状分析

### 1.1 核心接口

| 模块 | 关键类/函数 | 返回值 | 用途 |
|------|------------|--------|------|
| `src/pipeline.py` | `RAGPipeline.query(question)` | `dict{answer, contexts, scores, sources, chunk_ids, token_usage}` | 单次问答 |
| `src/pipeline.py` | `RAGPipeline.use_meal(meal_name)` | `MealConfig` | 切换数据集 |
| `src/meal.py` | `MealManager.list_meals()` | `list[MealConfig]` | 获取所有 meals |
| `src/experiment.py` | `ExperimentManager` | - | 实验管理 |

### 1.2 已有能力

- ✅ 完整的 RAG 链路（PDF→解析→分块→向量化→检索→生成）
- ✅ 多种检索策略（vector / bm25 / hybrid）
- ✅ Reranker 重排、查询改写（HyDE / Multi-Query）
- ✅ Meal 数据集快照管理
- ✅ Token 消耗追踪
- ✅ 实验对比系统（exp_configs/）

### 1.3 缺失能力

- ❌ Web 可视化界面
- ❌ 实验结果可视化展示
- ❌ PDF 来源预览
- ❌ 一键分享演示链接

---

## 二、功能设计

### 2.1 功能模块划分

```
Streamlit App
├── 📊 问答演示页（首页）
│   ├── 问题输入区
│   ├── 答案展示区
│   ├── 检索详情区（来源文档、chunks、分数）
│   └── Token 消耗统计
│
├── ⚙️ 配置面板（侧边栏）
│   ├── Meal 选择器
│   ├── 检索策略切换（vector/bm25/hybrid）
│   ├── Top-K 调节滑块
│   ├── Reranker 开关
│   └── 查询改写开关
│
├── 📈 实验对比页（可选，Phase 2）
│   ├── 实验结果加载
│   ├── 多变体指标对比表
│   └── 雷达图/柱状图可视化
│
└── 📖 系统信息页
    ├── 架构流程图
    ├── 技术栈说明
    └── 使用指南
```

### 2.2 页面详细设计

#### Page 1: 问答演示页（核心）

**布局**：
```
┌─────────────────────────────────────────────────────────┐
│  🏦 Easy RAG Lab - 金融研报问答系统                        │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐    │
│  │ 💬 输入问题：                                      │    │
│  │ [文本框 - 2行]                                    │    │
│  └─────────────────────────────────────────────────┘    │
│  [提交按钮]                                              │
├─────────────────────────────────────────────────────────┤
│  🤖 答案：                                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │ [Markdown 渲染区域]                               │    │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  📚 检索详情 [Tab: 来源文档 | 检索片段 | 评分详情]          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 1. 贵州茅台2023年年度报告.md (相关度: 0.8923)      │    │
│  │ 2. 中芯国际2024年年度报告.md (相关度: 0.7856)      │    │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  📊 Token 消耗：输入 1,234 | 输出 567 | 总计 1,801        │
└─────────────────────────────────────────────────────────┘
```

**侧边栏**：
```
┌─────────────────────┐
│ ⚙️ 配置              │
├─────────────────────┤
│ Meal: [下拉选择]     │
│ ├─ baseline_5kpage  │
│ ├─ baseline_1kpage  │
│ └─ golden_150       │
├─────────────────────┤
│ 检索策略: [下拉]     │
│ ├─ vector (默认)    │
│ ├─ bm25             │
│ └─ hybrid           │
├─────────────────────┤
│ Top-K: [滑块 1-10]  │
│ Reranker: [开关]    │
│ 查询改写: [开关]     │
└─────────────────────┘
```

#### Page 2: 实验对比页（Phase 2）

**功能**：
- 加载 `data/exp_reports/` 下的实验结果
- 展示多 variant 的指标对比表
- 生成雷达图/柱状图

**数据来源**：
- `data/exp_reports/{exp_name}/results.json`
- `data/exp_reports/{exp_name}/summary.json`

---

## 三、技术实现方案

### 3.1 依赖添加

```toml
# pixi.toml [pypi-dependencies] 新增
streamlit = ">=1.32.0, <2"
plotly = ">=5.18.0, <6"  # 可选，用于图表
```

### 3.2 文件结构

```
src/
├── app.py              # Streamlit 主入口（新增）
├── app_pages/          # 页面模块（新增）
│   ├── __init__.py
│   ├── qa_demo.py      # 问答演示页
│   ├── experiment.py   # 实验对比页（Phase 2）
│   └── about.py        # 系统信息页
└── ...
```

### 3.3 核心代码设计

#### 3.3.1 主入口 `src/app.py`

```python
import streamlit as st
from src.app_pages.qa_demo import render_qa_demo
from src.app_pages.about import render_about

st.set_page_config(
    page_title="Easy RAG Lab",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

page = st.sidebar.radio(
    "导航",
    ["问答演示", "系统信息"],
    label_visibility="collapsed"
)

if page == "问答演示":
    render_qa_demo()
else:
    render_about()
```

#### 3.3.2 问答演示页 `src/app_pages/qa_demo.py`

```python
import streamlit as st
from src.pipeline import RAGPipeline
from src.meal import MealManager
from src.utils import load_config

def render_qa_demo():
    # 初始化（使用 st.cache_resource 避免重复加载）
    @st.cache_resource
    def get_pipeline(meal_name: str | None):
        config = load_config()
        return RAGPipeline(config_path="config.yaml", meal_name=meal_name)

    @st.cache_data
    def get_meals():
        config = load_config()
        manager = MealManager(config)
        return manager.list_meals()

    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 配置")

        meals = get_meals()
        meal_names = [m.name for m in meals] + ["(无 Meal)"]
        selected_meal = st.selectbox("Meal", meal_names)

        retrieval_method = st.selectbox(
            "检索策略",
            ["vector", "bm25", "hybrid"]
        )
        top_k = st.slider("Top-K", 1, 10, 5)
        use_reranker = st.checkbox("启用 Reranker")
        use_query_rewrite = st.checkbox("启用查询改写")

    # 主界面
    st.title("🏦 金融研报问答系统")
    st.markdown("基于 RAG 的金融研报智能问答演示")

    question = st.text_area("💬 输入问题", height=100)

    if st.button("提交", type="primary"):
        if not question.strip():
            st.warning("请输入问题")
        else:
            with st.spinner("检索中..."):
                pipeline = get_pipeline(
                    selected_meal if selected_meal != "(无 Meal)" else None
                )
                result = pipeline.query(question)

            # 展示答案
            st.markdown("### 🤖 答案")
            st.success(result["answer"])

            # 展示检索详情
            tab1, tab2, tab3 = st.tabs(["来源文档", "检索片段", "评分详情"])

            with tab1:
                for i, (src, score) in enumerate(
                    zip(result["sources"], result["scores"])
                ):
                    st.markdown(f"{i+1}. **{src}** (相关度: {score:.4f})")

            with tab2:
                for i, ctx in enumerate(result["contexts"]):
                    with st.expander(f"片段 {i+1}"):
                        st.text(ctx[:500] + "..." if len(ctx) > 500 else ctx)

            with tab3:
                st.json({
                    "scores": result["scores"],
                    "chunk_ids": result.get("chunk_ids", [])
                })

            # Token 消耗
            if "token_usage" in result:
                tu = result["token_usage"]
                st.markdown("### 📊 Token 消耗")
                col1, col2, col3 = st.columns(3)
                col1.metric("输入", f"{tu['input_tokens']:,}")
                col2.metric("输出", f"{tu['output_tokens']:,}")
                col3.metric("总计", f"{tu['total_tokens']:,}")
```

### 3.4 Pixi Task 添加

```toml
# pixi.toml [tasks] 新增
[tasks.web]
cmd = "streamlit run src/app.py --server.port 8501"
```

---

## 四、实施计划

### Phase 1: MVP 问答演示（1-2 天）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 1.1 | 添加 streamlit 依赖 | `pixi.toml` 更新 |
| 1.2 | 创建 `src/app.py` 主入口 | 单文件 Demo |
| 1.3 | 实现 Meal 选择器 | 侧边栏配置 |
| 1.4 | 实现问答界面 | 答案 + 来源展示 |
| 1.5 | 添加 Token 消耗统计 | 指标卡片 |
| 1.6 | 添加 pixi task | `pixi run web` |
| 1.7 | 测试与调试 | 功能验证 |

**验收标准**：
- [ ] `pixi run web` 启动成功
- [ ] 可选择 Meal 进行问答
- [ ] 答案、来源、Token 消耗正确展示

### Phase 2: 配置热切换（0.5 天）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 2.1 | 实现检索策略切换 | vector/bm25/hybrid |
| 2.2 | 实现 Top-K 调节 | 滑块组件 |
| 2.3 | 实现 Reranker 开关 | 动态配置 |
| 2.4 | 实现查询改写开关 | HyDE/Multi-Query |

**技术难点**：
- 配置热切换需要重新初始化 Pipeline 或修改 `config_overrides`
- 建议方案：预设多个 Pipeline 实例，或使用 `st.session_state` 缓存

### Phase 3: 实验对比页（1 天，可选）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 3.1 | 实验结果加载器 | 读取 `data/exp_reports/` |
| 3.2 | 指标对比表 | st.dataframe |
| 3.3 | 可视化图表 | Plotly 雷达图/柱状图 |
| 3.4 | 多实验选择器 | 下拉菜单 |

**数据格式**：
```python
# 从 data/exp_reports/{exp_name}/summary.json 读取
{
    "variants": [
        {"name": "baseline", "metrics": {"hit_rate": 0.85, ...}},
        {"name": "hybrid", "metrics": {"hit_rate": 0.92, ...}}
    ]
}
```

### Phase 4: 部署与文档（0.5 天）

| 步骤 | 任务 | 产出 |
|------|------|------|
| 4.1 | Streamlit Cloud 部署 | 公网访问链接 |
| 4.2 | README 更新 | Web Demo 截图 + 链接 |
| 4.3 | 架构流程图 | docs/architecture.md 更新 |

---

## 五、风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|---------|
| Embedding 模型加载慢 | 首次启动 30s+ | 添加加载进度条，预热提示 |
| GPU 内存不足 | 多 Pipeline 实例 OOM | 使用单实例 + 配置热切换 |
| API Key 泄露 | 安全问题 | 使用 `.env` + Streamlit Secrets |
| 大规模数据检索慢 | 用户体验差 | 添加 loading 动画，异步处理 |

---

## 六、预期效果

### 6.1 简历展示价值

| 维度 | 提升点 |
|------|--------|
| **可视化** | 一图胜千言，面试官 30 秒理解项目价值 |
| **交互性** | 可现场演示，证明项目真实可用 |
| **工程能力** | 展示全栈能力（后端 RAG + 前端 Web） |
| **分享性** | 公网链接可随时分享给面试官/HR |

### 6.2 截图素材

完成后可获得：
1. **首页截图**：问答演示界面
2. **配置截图**：侧边栏配置面板
3. **结果截图**：答案 + 来源 + Token 消耗
4. **架构图**：RAG 链路流程图

---

## 七、后续扩展方向

1. **PDF 预览**：点击来源文档可预览 PDF 高亮片段
2. **历史记录**：保存问答历史，支持回溯
3. **批量评测**：上传问题集，批量评测并展示结果
4. **API 模式**：FastAPI 后端 + Streamlit 前端分离

---

## 八、总结

本计划书基于项目现有架构，设计了 Streamlit Web Demo 的完整实现方案。核心思路是：

1. **复用现有接口**：直接调用 `RAGPipeline.query()` 和 `MealManager`
2. **渐进式开发**：Phase 1 MVP → Phase 2 配置 → Phase 3 实验 → Phase 4 部署
3. **最小改动**：不修改现有代码，仅新增 `src/app.py` 和 `src/app_pages/`

预计总工作量 **2-3 天**，可显著提升项目的简历展示效果。
