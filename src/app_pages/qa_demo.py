import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger
from streamlit_searchbox import st_searchbox

from src.app_pages.pdf_server import PdfServer, get_or_create_pdf_server
from src.case_collector import (
    CASE_TYPE_BAD,
    CASE_TYPE_GOOD,
    DEDUP_STATUS_DUPLICATE,
    DEDUP_STATUS_TYPE_CHANGED,
    build_chat_history,
    list_cases,
    save_case_with_dedup,
)
from src.meal import MealConfig, MealManager
from src.pipeline import RAGPipeline
from src.sampler import SamplingConfig, count_pdf_pages
from src.utils import load_config


@st.cache_resource
def get_pipeline(meal_name: str | None) -> RAGPipeline:
    return RAGPipeline(config="config.yaml", meal_name=meal_name)


def _ensure_pdf_server() -> PdfServer:
    config = load_config()
    raw_dir = config.get("parser", {}).get("input_dir", "data/raw")
    return get_or_create_pdf_server(raw_dir)


def get_meals() -> list[Any]:
    config = load_config()
    manager = MealManager(config)
    return manager.list_meals()


def create_new_meal(
    name: str | None,
    sample_mode: str,
    sample_value: int | float,
    seed: int | None,
) -> Any:
    config = load_config()
    manager = MealManager(config)

    sampling_config = SamplingConfig(mode=sample_mode, value=sample_value)

    return manager.create_meal(
        name=name,
        sampling_config=sampling_config,
        seed=seed,
    )


def _get_raw_dir() -> Path:
    config = load_config()
    return Path(config.get("parser", {}).get("input_dir", "data/raw"))


def _format_file_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def _source_to_pdf_path(source: str, meal_config: MealConfig | None) -> str | None:
    if meal_config is None:
        return None
    raw_dir = _get_raw_dir()
    source_pdf = Path(source).with_suffix(".pdf").as_posix()
    for mf in meal_config.pdf_files:
        if mf.path == source_pdf:
            return str(raw_dir / mf.path)
    source_stem = Path(source).stem
    for mf in meal_config.pdf_files:
        if Path(mf.path).stem == source_stem:
            return str(raw_dir / mf.path)
    return None


def _open_pdf_preview(file_path: str, file_name: str) -> None:
    st.session_state._pdf_preview_path = file_path
    st.session_state._pdf_preview_name = file_name
    st.session_state._pdf_preview_page = 1


@st.cache_data
def _get_pdf_page_count(file_path: str) -> int:
    try:
        return count_pdf_pages(Path(file_path))
    except Exception:
        return 0


def render_pdf_preview() -> None:
    file_path = st.session_state.get("_pdf_preview_path", "")
    file_name = st.session_state.get("_pdf_preview_name", "")

    if not file_path or not Path(file_path).exists():
        st.error(f"文件不存在: {file_name}")
        if st.button("关闭", key="close_pdf_missing"):
            st.session_state.pop("_pdf_preview_path", None)
            st.session_state.pop("_pdf_preview_name", None)
            st.session_state.pop("_pdf_preview_page", None)
            st.rerun()
        return

    col_title, col_close = st.columns([8, 1])
    with col_title:
        st.markdown(f"### 📄 {file_name}")
    with col_close:
        if st.button("✕", key="close_pdf_preview", help="关闭 PDF 预览"):
            st.session_state.pop("_pdf_preview_path", None)
            st.session_state.pop("_pdf_preview_name", None)
            st.session_state.pop("_pdf_preview_page", None)
            st.rerun()

    total_pages = _get_pdf_page_count(file_path)
    current_page = st.session_state.get("_pdf_preview_page", 1)

    col_prev, col_info, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀ 上一页", disabled=(current_page <= 1), key="prev_page"):
            st.session_state._pdf_preview_page = current_page - 1
            st.rerun()
    with col_info:
        page_label = (
            f"第 **{current_page}** / {total_pages} 页"
            if total_pages > 0
            else f"第 **{current_page}** 页"
        )
        st.markdown(
            f"<div style='text-align:center; padding-top:8px'>{page_label}</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button(
            "下一页 ▶",
            disabled=(total_pages > 0 and current_page >= total_pages),
            key="next_page",
        ):
            st.session_state._pdf_preview_page = current_page + 1
            st.rerun()

    with st.form("pdf_page_jump_form"):
        col_page, col_jump = st.columns([1, 1])
        with col_page:
            page_num = st.number_input(
                "跳转到页码",
                min_value=1,
                max_value=total_pages if total_pages > 0 else 9999,
                value=current_page,
            )
        with col_jump:
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("跳转")
        if submitted:
            st.session_state._pdf_preview_page = page_num
            st.rerun()

    server = _ensure_pdf_server()
    raw_dir = _get_raw_dir()
    rel_path = os.path.relpath(file_path, raw_dir).replace("\\", "/")
    encoded_path = urllib.parse.quote(rel_path)
    pdf_url = f"{server.base_url}/{encoded_path}#page={current_page}"
    st.markdown(
        f'<iframe src="{pdf_url}" width="100%" height="800" '
        f'style="border:none;"></iframe>',
        unsafe_allow_html=True,
    )


def _do_save_case(
    case_type: str,
    msg: dict[str, Any],
    meal_config: MealConfig | None,
    chat_history: list[dict[str, Any]] | None = None,
) -> bool:
    saved_case_type = msg.get("saved_case_type")
    saved_case_id = msg.get("saved_case_id")

    result = msg.get("result", {})
    config_overrides = msg.get("config_overrides", {})
    meal_name = msg.get("meal_name")
    trace_data = msg.get("trace")
    question = result.get("question", "")
    try:
        base_config = load_config()
        case_dir, status = save_case_with_dedup(
            case_type=case_type,
            question=question,
            result=result,
            config_overrides=config_overrides,
            base_config=base_config,
            meal_config=meal_config,
            meal_name=meal_name,
            chat_history=chat_history,
            trace=trace_data,
            saved_case_type=saved_case_type,
            saved_case_id=saved_case_id,
        )

        if status == DEDUP_STATUS_DUPLICATE:
            label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"
            st.toast(f"已标记为 {label}，无需重复保存", icon="⚠️")
            return False

        if status == DEDUP_STATUS_TYPE_CHANGED:
            msg["saved_case_type"] = case_type
            msg["saved_case_id"] = case_dir.name
            old_label = "Badcase" if saved_case_type == CASE_TYPE_BAD else "Goodcase"
            new_label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"
            icon = "🚨" if case_type == CASE_TYPE_BAD else "✅"
            st.toast(
                f"{icon} 已将 {old_label} 转换为 {new_label}: {case_dir.name}",
                icon=icon,
            )
            return True

        msg["saved_case_type"] = case_type
        msg["saved_case_id"] = case_dir.name
        label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"
        st.toast(
            f"{label} 已保存: {case_dir.name}",
            icon="🚨" if case_type == CASE_TYPE_BAD else "✅",
        )
        if case_type == CASE_TYPE_BAD:
            st.toast(
                "可到「🔍 Bad Case 分析」标签页进行深度分析",
                icon="🔬",
            )
        return True
    except Exception as e:
        logger.error(f"Failed to save case: {e}")
        st.error(f"保存失败: {e}")
        return False


def _display_result(
    result: dict[str, Any],
    meal_config: MealConfig | None,
    msg_index: int = 0,
    chat_history: list[dict[str, Any]] | None = None,
):
    st.markdown("### 🤖 答案")
    st.success(result["answer"])

    tab1, tab2, tab3 = st.tabs(["来源文档", "检索片段", "评分详情"])

    with tab1:
        if "sources" in result and result["sources"]:
            for i, (src, score) in enumerate(
                zip(result["sources"], result["scores"], strict=False)
            ):
                src_name = src.split("\\")[-1] if "\\" in src else src.split("/")[-1]
                col_src, col_btn = st.columns([4, 1])
                with col_src:
                    st.markdown(f"{i + 1}. **{src_name}** (相关度: {score:.4f})")
                with col_btn:
                    pdf_path = _source_to_pdf_path(src, meal_config)
                    if pdf_path and st.button(
                        "📄预览",
                        key=f"src_preview_{msg_index}_{i}",
                        help="预览此来源 PDF 文件",
                        on_click=_open_pdf_preview,
                        args=(pdf_path, Path(pdf_path).name),
                    ):
                        st.toast("📄 已打开 PDF 预览，请点击「PDF 预览」标签页查看")
        else:
            st.info("无来源文档")

    with tab2:
        if "contexts" in result and result["contexts"]:
            for i, ctx in enumerate(result["contexts"]):
                with st.expander(f"片段 {i + 1}"):
                    display_text = ctx[:500] + "..." if len(ctx) > 500 else ctx
                    st.text(display_text)
        else:
            st.info("无检索片段")

    with tab3:
        if "scores" in result:
            st.json(
                {
                    "scores": result["scores"],
                    "chunk_ids": result.get("chunk_ids", []),
                }
            )
        else:
            st.info("无评分详情")

    if "token_usage" in result and result["token_usage"]:
        tu = result["token_usage"]
        st.markdown("### 📊 Token 消耗")
        col1, col2, col3 = st.columns(3)
        col1.metric("输入", f"{tu['input_tokens']:,}")
        col2.metric("输出", f"{tu['output_tokens']:,}")
        col3.metric("总计", f"{tu['total_tokens']:,}")

    st.markdown("---")
    saved_case_type = (
        msg.get("saved_case_type")
        if (msg := st.session_state.messages[msg_index])
        else None
    )
    col_bad, col_good = st.columns(2)
    with col_bad:
        bad_label = "🚨 Badcase ✓" if saved_case_type == CASE_TYPE_BAD else "🚨 Badcase"
        if st.button(
            bad_label,
            key=f"badcase_{msg_index}",
            help="标记此回答为坏例，完整落盘以便复现",
            disabled=saved_case_type == CASE_TYPE_BAD,
        ):
            _do_save_case(CASE_TYPE_BAD, msg, meal_config, chat_history=chat_history)
    with col_good:
        good_label = (
            "✅ Goodcase ✓" if saved_case_type == CASE_TYPE_GOOD else "✅ Goodcase"
        )
        if st.button(
            good_label,
            key=f"goodcase_{msg_index}",
            help="标记此回答为好例，完整落盘用于回归测试",
            disabled=saved_case_type == CASE_TYPE_GOOD,
        ):
            _do_save_case(CASE_TYPE_GOOD, msg, meal_config, chat_history=chat_history)


def _init_session_state():
    if "meals_cache" not in st.session_state:
        st.session_state.meals_cache = get_meals()
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "query_error" not in st.session_state:
        st.session_state.query_error = None


def _extract_company_name(rel_path: str) -> str | None:
    parts = Path(rel_path).parts
    if len(parts) < 3:
        return None
    top_level_categories = {"annual_reports", "research_reports"}
    if parts[0] not in top_level_categories:
        return None
    if re.match(r"^\d{4}$", parts[-2]):
        if len(parts) >= 4:
            return parts[-3]
        return None
    if parts[-2] in top_level_categories:
        return None
    return parts[-2]


def _render_meal_files(meal_config: MealConfig | None) -> None:
    if meal_config is None:
        return
    pdf_files = meal_config.pdf_files
    if not pdf_files:
        return
    with st.expander(f"📂 当前 Meal 文件 ({len(pdf_files)})"):
        raw_dir = _get_raw_dir()

        def _search_pdf_files(searchterm: str) -> list[tuple[str, str]]:
            results = []
            for mf in pdf_files:
                file_name = Path(mf.path).name
                if (
                    not searchterm
                    or searchterm.lower() in file_name.lower()
                    or searchterm.lower() in mf.path.lower()
                ):
                    results.append((file_name, mf.path))
            return results

        default_options = [(Path(mf.path).name, mf.path) for mf in pdf_files[:50]]
        selected = st_searchbox(
            _search_pdf_files,
            placeholder="搜索 PDF 文件名...",
            key=f"meal_pdf_search_{meal_config.name}",
            default_options=default_options,
            label="搜索 PDF",
        )

        if selected:
            mf_match = next((mf for mf in pdf_files if mf.path == selected), None)
            if mf_match:
                file_name = Path(mf_match.path).name
                size_str = _format_file_size(mf_match.size_bytes)
                company = _extract_company_name(mf_match.path)
                show_company = company is not None and company not in file_name
                if show_company:
                    st.markdown(
                        f"📄 **{file_name}** "
                        f'<span style="background-color:#e8f0fe;color:#1a73e8;'
                        f"padding:1px 6px;border-radius:4px;font-size:0.75em;"
                        f'vertical-align:middle;">🏢 {company}</span>'
                        f"  ({size_str})",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f"📄 **{file_name}**  ({size_str})")
                full_path = str(raw_dir / mf_match.path)
                if Path(full_path).exists():
                    if st.button(
                        "📄 预览",
                        key=f"meal_file_preview_{mf_match.path}",
                        help=f"预览 {file_name}",
                        on_click=_open_pdf_preview,
                        args=(full_path, file_name),
                    ):
                        st.toast("📄 已打开 PDF 预览，请点击「PDF 预览」标签页查看")
                else:
                    st.caption("文件缺失")


def render_qa_demo():
    _init_session_state()

    st.title("🏦 金融研报问答系统")
    st.markdown("基于 RAG 的金融研报智能问答演示")

    meals = st.session_state.meals_cache

    with st.sidebar:
        st.header("⚙️ 配置")

        meal_options = [m.name for m in meals] + ["(无 Meal)", "+ 新建 Meal"]
        selected_meal = st.selectbox("Meal", meal_options, key="meal_select")

        meal_config: MealConfig | None = None
        meal_name: str | None = None
        if selected_meal not in ("(无 Meal)", "+ 新建 Meal"):
            meal_name = selected_meal
            meal_config = next((m for m in meals if m.name == selected_meal), None)

        _render_meal_files(meal_config)

        if selected_meal == "+ 新建 Meal":
            st.markdown("---")
            st.subheader("📝 新建 Meal")

            new_meal_name = st.text_input(
                "Meal 名称（可选）",
                value="",
                key="new_meal_name",
                help="留空则自动生成时间戳名称",
            )

            sample_mode = st.selectbox(
                "采样方式",
                ["pages", "count", "ratio"],
                index=0,
                key="sample_mode",
                format_func=lambda x: {
                    "pages": "按页数",
                    "count": "按文件数",
                    "ratio": "按比例",
                }[x],
            )

            if sample_mode == "pages":
                sample_value = st.number_input(
                    "目标页数",
                    min_value=100,
                    max_value=50000,
                    value=1000,
                    step=100,
                    key="sample_pages",
                )
            elif sample_mode == "count":
                sample_value = st.number_input(
                    "文件数量",
                    min_value=1,
                    max_value=100,
                    value=5,
                    key="sample_count",
                )
            else:
                sample_value = st.slider(
                    "采样比例",
                    min_value=0.1,
                    max_value=1.0,
                    value=0.1,
                    step=0.05,
                    key="sample_ratio",
                )

            seed = st.number_input(
                "随机种子",
                min_value=0,
                value=42,
                key="new_meal_seed",
                help="用于可重复采样",
            )

            if st.button("创建 Meal", type="primary", key="create_meal_btn"):
                with st.spinner("创建中..."):
                    try:
                        meal_name_input = (
                            new_meal_name.strip() if new_meal_name.strip() else None
                        )
                        new_meal = create_new_meal(
                            name=meal_name_input,
                            sample_mode=sample_mode,
                            sample_value=sample_value,
                            seed=seed if seed > 0 else None,
                        )
                        st.session_state.meals_cache = get_meals()
                        st.success(f"Meal '{new_meal.name}' 创建成功！")
                        st.rerun()
                    except Exception as e:
                        logger.error(f"Failed to create meal: {str(e)}")
                        st.error(f"创建失败: {str(e)}")

        st.markdown("---")

        _retrieval_method = st.selectbox(
            "检索策略",
            ["vector", "bm25", "hybrid"],
            index=0,
            key="retrieval_method",
        )

        _top_k = st.slider("Top-K", 1, 10, 5, key="top_k")

        _use_reranker = st.checkbox("启用 Reranker", value=False, key="use_reranker")

        _use_query_rewrite = st.checkbox(
            "启用查询改写", value=False, key="use_query_rewrite"
        )

        if _use_query_rewrite:
            _query_rewrite_strategy = st.selectbox(
                "改写策略",
                ["hyde", "multi_query"],
                index=0,
                key="query_rewrite_strategy",
                format_func=lambda x: {
                    "hyde": "HyDE（假设性文档）",
                    "multi_query": "Multi-Query（多查询）",
                }[x],
            )

        st.markdown("---")
        try:
            bad_count = len(list_cases(case_type=CASE_TYPE_BAD))
            good_count = len(list_cases(case_type=CASE_TYPE_GOOD))
            st.caption(f"🚨 Badcase: {bad_count}  |  ✅ Goodcase: {good_count}")
        except Exception:
            pass

    if st.button("🗑️ 清空对话", key="clear_btn"):
        st.session_state.messages = []
        st.session_state.query_error = None
        st.rerun()

    if st.session_state.query_error:
        st.error(f"查询失败: {st.session_state.query_error}")
        st.session_state.query_error = None

    for msg_index, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg["content"])
            else:
                chat_history_for_msg = build_chat_history(
                    st.session_state.messages, msg_index
                )
                _display_result(
                    msg["result"],
                    meal_config,
                    msg_index=msg_index,
                    chat_history=chat_history_for_msg,
                )

    if st.session_state.messages:
        st.html(
            """
<style>
  #st-scroll-nav { position:fixed; z-index:9999; transition:all .3s ease; cursor:pointer;
    width:44px; height:44px; border-radius:50%; display:flex; align-items:center;
    justify-content:center; font-size:22px; box-shadow:0 2px 8px rgba(0,0,0,.25);
    background:#fff; border:1px solid #e0e0e0; user-select:none; }
  #st-scroll-nav:hover { box-shadow:0 4px 14px rgba(0,0,0,.3); transform:scale(1.1); }
  #st-scroll-nav.nav-bottom { bottom:80px; right:24px; }
  #st-scroll-nav.nav-top    { top:80px;  right:24px; }
</style>
<div id="st-scroll-nav" class="nav-bottom">↓</div>
<script>
  const btn = document.getElementById('st-scroll-nav');
  if (btn) {
    const chatInput = document.querySelector('[data-testid="stChatInput"]');
    function isNearBottom() {
      return (window.innerHeight + window.scrollY) >= (document.body.scrollHeight - 80);
    }
    function updateBtn() {
      if (isNearBottom()) {
        btn.className = 'nav-top'; btn.textContent = '↑';
        btn.onclick = () => window.scrollTo({top:0, behavior:'smooth'});
      } else {
        btn.className = 'nav-bottom'; btn.textContent = '↓';
        btn.onclick = () => {
          if (chatInput) { chatInput.scrollIntoView({behavior:'smooth', block:'end'}); }
          else { window.scrollTo({top:document.body.scrollHeight, behavior:'smooth'}); }
        };
      }
    }
    window.addEventListener('scroll', updateBtn);
    updateBtn();
  }
</script>
            """,
            unsafe_allow_javascript=True,
        )

    question = st.chat_input(
        "输入问题，Enter 发送，Shift+Enter 换行",
        key="chat_input_widget",
    )

    if question:
        st.session_state.query_error = None

        config_overrides = {
            "retrieval": {
                "method": st.session_state.retrieval_method,
                "top_k": st.session_state.top_k,
                "reranker": {"enabled": st.session_state.use_reranker},
                "query_rewrite": {
                    "enabled": st.session_state.use_query_rewrite,
                    "strategy": st.session_state.get("query_rewrite_strategy", "hyde"),
                },
            }
        }

        with st.spinner("🔍 正在检索相关文档并生成答案..."):
            try:
                pipeline = get_pipeline(meal_name)
                chat_history_for_query = build_chat_history(st.session_state.messages)
                st.session_state.messages.append({"role": "user", "content": question})
                result = pipeline.query(
                    question,
                    config_overrides=config_overrides,
                    chat_history=chat_history_for_query,
                    capture_trace=True,
                )
                trace_data = result.pop("trace", None)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "result": result,
                        "config_overrides": config_overrides,
                        "meal_name": meal_name,
                        "trace": trace_data,
                    }
                )
            except Exception as e:
                logger.error(f"Query failed: {e}")
                error_str = str(e)
                if "BM25" in error_str or "chunks" in error_str:
                    st.session_state.query_error = (
                        f"BM25 索引不可用：{error_str}\n\n"
                        "💡 提示：请先构建索引或选择一个已构建的 Meal。"
                    )
                elif "reranker" in error_str.lower() or "model" in error_str.lower():
                    st.session_state.query_error = (
                        f"Reranker 加载失败：{error_str}\n\n"
                        "💡 提示：请检查模型文件是否已下载，或取消勾选「启用 Reranker」。"
                    )
                else:
                    st.session_state.query_error = error_str

        st.rerun()
