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
from src.app_pages.qa_demo import render_qa_demo  # noqa: E402

st.set_page_config(
    page_title="Easy RAG Lab",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

tab1, tab2 = st.tabs(["💬 问答演示", "📖 系统信息"])

with tab1:
    render_qa_demo()

with tab2:
    render_about()
