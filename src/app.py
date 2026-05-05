import os
import sys
import warnings
from pathlib import Path

os.environ["TRANSFORMERS_VERBOSITY"] = "error"

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

warnings.filterwarnings(
    "ignore",
    message="Accessing `__path__` from",
    category=FutureWarning,
)

from src.utils import load_config, setup_logger  # noqa: E402

config = load_config()
setup_logger(config)

import streamlit as st  # noqa: E402

from src.app_pages.about import render_about  # noqa: E402
from src.app_pages.case_analyzer import render_case_analyzer  # noqa: E402
from src.app_pages.maintenance import render_maintenance  # noqa: E402
from src.app_pages.qa_demo import render_pdf_preview, render_qa_demo  # noqa: E402

st.set_page_config(
    page_title="Easy RAG Lab",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.html(
    """
<style>
[data-testid="stDecoration"] { display: none !important; }
.stApp > header { display: none !important; }
[data-testid="stCodeBlock"] pre { white-space: pre-wrap !important; word-break: break-word !important; }
</style>
"""
)

tab_names = ["💬 问答演示", "🔍 Case 分析", "🔧 维修工", "📖 系统信息"]
has_pdf = bool(st.session_state.get("_pdf_preview_path"))
if has_pdf:
    tab_names.append("📄 PDF 预览")

tabs = st.tabs(tab_names)

with tabs[0]:
    render_qa_demo()

with tabs[1]:
    render_case_analyzer()

with tabs[2]:
    render_maintenance()

with tabs[3]:
    render_about()

if has_pdf:
    with tabs[4]:
        render_pdf_preview()

if st.session_state.get("_switch_to_pdf_tab"):
    st.html(
        """
<script>
setTimeout(function() {
    var tabList = document.querySelector('[data-testid="stTabs"] [role="tablist"]');
    if (tabList) {
        var tabs = tabList.querySelectorAll('button[role="tab"]');
        for (var i = 0; i < tabs.length; i++) {
            if (tabs[i].textContent.includes("PDF")) {
                tabs[i].click();
                break;
            }
        }
    }
}, 300);
</script>
""",
        unsafe_allow_javascript=True,
    )
    st.session_state._switch_to_pdf_tab = False
