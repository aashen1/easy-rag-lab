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

import src.app_pages as _app_pages  # noqa: E402
from src.app_pages.about import render_about  # noqa: E402
from src.app_pages.pdf_server import start_pdf_server  # noqa: E402
from src.app_pages.qa_demo import render_pdf_preview, render_qa_demo  # noqa: E402

_pdf_server = start_pdf_server(config.get("parser", {}).get("input_dir", "data/raw"))
_app_pages._pdf_server_ref = _pdf_server

st.set_page_config(
    page_title="Easy RAG Lab",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

tab_names = ["💬 问答演示", "📖 系统信息"]
has_pdf = bool(st.session_state.get("_pdf_preview_path"))
if has_pdf:
    tab_names.append("📄 PDF 预览")

tabs = st.tabs(tab_names)

with tabs[0]:
    render_qa_demo()

with tabs[1]:
    render_about()

if has_pdf:
    with tabs[2]:
        render_pdf_preview()
