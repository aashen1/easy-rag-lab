import threading
import uuid
from datetime import timedelta
from typing import Any

import streamlit as st
from loguru import logger

from src.meal import MealManager
from src.pipeline import RAGPipeline
from src.sampler import SamplingConfig
from src.utils import load_config

_query_store: dict[str, dict[str, Any]] = {}


@st.cache_resource
def get_pipeline(meal_name: str | None) -> RAGPipeline:
    return RAGPipeline(config_path="config.yaml", meal_name=meal_name)


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


def _run_query(query_id: str, question: str, meal_name: str | None) -> None:
    try:
        pipeline = get_pipeline(meal_name)
        result = pipeline.query(question)
        _query_store[query_id] = {"status": "done", "result": result}
    except Exception as e:
        logger.error(f"Query failed: {e}")
        _query_store[query_id] = {"status": "error", "error": str(e)}


def _display_result(result: dict[str, Any]):
    st.markdown("### 🤖 答案")
    st.success(result["answer"])

    tab1, tab2, tab3 = st.tabs(["来源文档", "检索片段", "评分详情"])

    with tab1:
        if "sources" in result and result["sources"]:
            for i, (src, score) in enumerate(
                zip(result["sources"], result["scores"], strict=False)
            ):
                src_name = src.split("\\")[-1] if "\\" in src else src.split("/")[-1]
                st.markdown(f"{i + 1}. **{src_name}** (相关度: {score:.4f})")
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


def _init_session_state():
    if "meals_cache" not in st.session_state:
        st.session_state.meals_cache = get_meals()
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "saved_question" not in st.session_state:
        st.session_state.saved_question = ""
    if "query_running" not in st.session_state:
        st.session_state.query_running = False
    if "current_query_id" not in st.session_state:
        st.session_state.current_query_id = None
    if "query_error" not in st.session_state:
        st.session_state.query_error = None


def _check_completed_query():
    query_id = st.session_state.get("current_query_id")
    if not query_id or not st.session_state.get("query_running"):
        return
    entry = _query_store.pop(query_id, None)
    if entry is None:
        return
    if entry["status"] == "done":
        st.session_state.last_result = entry["result"]
        st.session_state.query_running = False
        st.session_state.current_query_id = None
    elif entry["status"] == "error":
        st.session_state.query_running = False
        st.session_state.current_query_id = None
        st.session_state.query_error = entry["error"]


@st.fragment(run_every=timedelta(seconds=1))
def _render_query_status():
    query_id = st.session_state.get("current_query_id")
    if not query_id or not st.session_state.get("query_running"):
        return
    entry = _query_store.pop(query_id, None)
    if entry is not None:
        if entry["status"] == "done":
            st.session_state.last_result = entry["result"]
            st.session_state.query_running = False
            st.session_state.current_query_id = None
            st.rerun()
        elif entry["status"] == "error":
            st.session_state.query_running = False
            st.session_state.current_query_id = None
            st.session_state.query_error = entry["error"]
            st.rerun()
    else:
        with st.status("🔍 检索中...", expanded=True):
            st.write("正在检索相关文档并生成答案，可切换到其他页面等待...")


def render_qa_demo():
    _init_session_state()
    _check_completed_query()

    st.title("🏦 金融研报问答系统")
    st.markdown("基于 RAG 的金融研报智能问答演示")

    meals = st.session_state.meals_cache

    with st.sidebar:
        st.header("⚙️ 配置")

        meal_options = [m.name for m in meals] + ["(无 Meal)", "+ 新建 Meal"]
        selected_meal = st.selectbox("Meal", meal_options, key="meal_select")

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

    meal_name = None if selected_meal in ["(无 Meal)", "+ 新建 Meal"] else selected_meal

    default_question = st.session_state.saved_question
    question = st.text_area(
        "💬 输入问题",
        value=default_question,
        height=100,
        key="question_input_widget",
    )

    col_btn, col_clear = st.columns([1, 1])

    with col_btn:
        submit_clicked = st.button("提交", type="primary", key="submit_btn")

    with col_clear:
        clear_clicked = st.button("清空", key="clear_btn")

    if clear_clicked:
        st.session_state.last_result = None
        st.session_state.saved_question = ""
        st.session_state.query_running = False
        st.session_state.current_query_id = None
        st.session_state.query_error = None
        st.rerun()

    if submit_clicked:
        if not question.strip():
            st.warning("请输入问题")
        elif st.session_state.query_running:
            st.warning("已有查询正在进行中，请稍候")
        else:
            st.session_state.saved_question = question
            st.session_state.query_running = True
            st.session_state.last_result = None
            st.session_state.query_error = None
            query_id = str(uuid.uuid4())
            st.session_state.current_query_id = query_id
            thread = threading.Thread(
                target=_run_query,
                args=(query_id, question, meal_name),
                daemon=True,
            )
            thread.start()
            st.rerun()

    _render_query_status()

    if st.session_state.query_error:
        st.error(f"查询失败: {st.session_state.query_error}")
        st.session_state.query_error = None

    if st.session_state.last_result is not None:
        _display_result(st.session_state.last_result)
