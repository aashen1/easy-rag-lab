import streamlit as st


def render_about():
    st.title("📖 系统信息")

    st.markdown("## RAG 链路流程图")

    st.markdown("""
```mermaid
flowchart LR
    A[PDF 文档] --> B[PDF 解析]
    B --> C[文本分块]
    C --> D[向量化]
    D --> E[向量存储]
    E --> F[检索]
    F --> G[LLM 生成]
    G --> H[答案]

    subgraph 解析器
        B1[pymupdf4llm]
        B2[fitz+pdfplumber]
    end

    subgraph 分块策略
        C1[固定长度]
        C2[语义分块]
    end

    subgraph 检索策略
        F1[向量检索]
        F2[BM25]
        F3[混合检索]
        F4[Reranker]
    end
```
""")

    st.markdown("---")

    st.markdown("## 技术栈")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📄 PDF 解析")
        st.markdown("- **pymupdf4llm**: PDF 转 Markdown，支持 OCR")
        st.markdown("- **fitz + pdfplumber**: 表格提取优化")

        st.markdown("### 🔢 向量化")
        st.markdown("- **BAAI/bge-large-zh-v1.5**: 中文 Embedding 模型")
        st.markdown("- **Qdrant**: 向量数据库")

    with col2:
        st.markdown("### 🤖 LLM")
        st.markdown("- **Anthropic Claude API**: 答案生成")
        st.markdown("- **兼容 OpenAI API 格式**: 支持多种 LLM 服务")

        st.markdown("### 📊 评测")
        st.markdown("- **RAGAS**: RAG 评测框架")
        st.markdown("- **自研指标**: Hit Rate, MRR, NDCG, Recall@K")

    st.markdown("---")

    st.markdown("## 使用指南")

    st.markdown("""
### 快速开始

1. **准备数据**: 将 PDF 文件放入 `data/raw/` 目录
2. **构建索引**: 运行 `pixi run python main.py --build-index`
3. **启动 Web**: 运行 `pixi run web`
4. **开始问答**: 在 Web 界面输入问题

### 命令行使用

```bash
# 单次问答
pixi run python main.py --query "问题"

# 交互式问答
pixi run interactive

# 运行实验
pixi run exp baseline/baseline_1kpage

# 运行测试
pixi run test
```

### 更多文档

- [快速上手](../docs/getting-started.md)
- [系统架构](../docs/architecture.md)
- [CLI 参考](../docs/cli-reference.md)
- [配置参考](../docs/config-reference.md)
""")
