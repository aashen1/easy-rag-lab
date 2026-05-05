import streamlit as st


def _render_mermaid(chart: str):
    escaped = chart.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    st.iframe(
        f"""
        <style>
            #mc {{ position:relative; min-height:100px; padding:8px; }}
            #mc .toggle-bar {{
                position:absolute; top:8px; right:8px; z-index:10;
                display:inline-flex; border-radius:6px; overflow:hidden;
                border:1px solid #d1d5db; background:#fff;
            }}
            #mc .toggle-bar button {{
                border:none; padding:4px 12px; font-size:12px; cursor:pointer;
                background:#fff; color:#6b7280; font-family:system-ui,sans-serif;
                transition:all .15s;
            }}
            #mc .toggle-bar button.active {{
                background:#4b5563; color:#fff;
            }}
            #mc .toggle-bar button:not(.active):hover {{
                background:#f3f4f6;
            }}
            #mc #code-view {{
                display:none; font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;
                white-space:pre; background:#1e293b; padding:16px; border-radius:8px;
                font-size:13px; line-height:1.6; color:#e2e8f0; margin-top:36px;
                border:1px solid #334155;
            }}
            #mc #diagram-view {{ margin-top:36px; background:#1e293b; border-radius:8px; padding:12px; }}
        </style>
        <div id="mc">
            <div class="toggle-bar">
                <button id="btn-diagram" class="active" onclick="switchView('diagram')">Diagram</button>
                <button id="btn-code" onclick="switchView('code')">Code</button>
            </div>
            <div id="diagram-view" class="mermaid">{chart}</div>
            <div id="code-view">{escaped}</div>
        </div>
        <script>
            function switchView(mode) {{
                var dv = document.getElementById('diagram-view');
                var cv = document.getElementById('code-view');
                var bd = document.getElementById('btn-diagram');
                var bc = document.getElementById('btn-code');
                if (mode === 'diagram') {{
                    dv.style.display = 'block';
                    cv.style.display = 'none';
                    bd.classList.add('active');
                    bc.classList.remove('active');
                }} else {{
                    dv.style.display = 'none';
                    cv.style.display = 'block';
                    bd.classList.remove('active');
                    bc.classList.add('active');
                }}
            }}
            function loadMermaid(src, fallback) {{
                var s = document.createElement('script');
                s.src = src;
                s.onload = function() {{
                    mermaid.initialize({{
                        startOnLoad: false,
                        theme: 'dark',
                        flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }}
                    }});
                    mermaid.run();
                }};
                s.onerror = function() {{
                    if (fallback) {{
                        loadMermaid(fallback, null);
                    }} else {{
                        document.getElementById('diagram-view').innerHTML =
                            '<p style="color:#999;text-align:center;padding:40px;">' +
                            '⚠️ Mermaid CDN 加载失败，请切换到 Code 视图查看</p>';
                    }}
                }};
                document.head.appendChild(s);
            }}
            loadMermaid(
                'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js',
                'https://cdn.bootcdn.net/ajax/libs/mermaid/11.4.1/mermaid.min.js'
            );
        </script>
        """,
        height=400,
    )


_RAG_FLOWCHART = """flowchart LR
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
"""


def render_about():
    st.title("📖 系统信息")

    st.markdown("## RAG 链路流程图")

    _render_mermaid(_RAG_FLOWCHART)

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
