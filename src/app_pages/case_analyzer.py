from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from src.case_collector import (
    CASE_TYPE_BAD,
    list_cases,
    load_case,
    save_diagnosis,
    save_ground_truth,
)
from src.case_diagnoser import diagnose
from src.ground_truth_finder import find_chunks_by_source_page
from src.trace_models import ROOT_CAUSES, GroundTruth


@st.cache_data(ttl=10)
def _cached_list_bad_cases() -> list[dict[str, Any]]:
    try:
        return list_cases(case_type=CASE_TYPE_BAD)
    except Exception as e:
        logger.error(f"Failed to list bad cases: {e}")
        return []


def _get_chunks_dir(case_data: dict[str, Any]) -> Path | None:
    meal_snapshot = case_data.get("meal_snapshot", {})
    config_snapshot = case_data.get("config_snapshot", {})

    data_id = meal_snapshot.get("data_id", "")
    if not data_id:
        return None

    from src.meal import ArtifactCache

    artifacts_config = config_snapshot.get("artifacts", {})
    artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
    raw_dir = Path(config_snapshot.get("parser", {}).get("input_dir", "data/raw"))
    cache = ArtifactCache(artifacts_dir, raw_dir)

    chunker_hash = ""
    config_hashes = meal_snapshot.get("config_hashes", {})
    if config_hashes:
        chunker_hash = config_hashes.get("chunker", "")
    if not chunker_hash:
        chunker_config = config_snapshot.get("chunker", {})
        if chunker_config:
            from src.meal import compute_chunker_config_hash

            chunker_hash = compute_chunker_config_hash(
                {
                    "chunk_size": chunker_config.get("chunk_size", 512),
                    "chunk_overlap": chunker_config.get("chunk_overlap", 0),
                    "encoding": chunker_config.get("encoding", "cl100k_base"),
                }
            )

    if chunker_hash:
        chunks_dir = cache.get_chunks_dir(data_id, chunker_hash)
        if chunks_dir.exists():
            return chunks_dir

    fallback = Path("data/artifacts") / data_id[:16]
    for child in fallback.iterdir():
        if child.is_dir() and child.name.startswith("chunks_"):
            return child

    return None


def _render_pipeline_trace_html(steps: list[dict[str, Any]]) -> None:
    stage_labels = {
        "query_rewrite": "查询改写",
        "retrieval": "检索",
        "rerank": "重排序",
        "context_assembly": "上下文组装",
        "generation": "答案生成",
    }
    stage_order = [
        "query_rewrite",
        "retrieval",
        "rerank",
        "context_assembly",
        "generation",
    ]
    present_stages = {s["stage"] for s in steps}

    stage_cells = []
    for stage in stage_order:
        label = stage_labels.get(stage, stage)
        present = stage in present_stages
        step_data = next((s for s in steps if s["stage"] == stage), None)

        if present and step_data:
            duration = step_data.get("duration_ms", 0)
            inp = step_data.get("input_data", {})
            out = step_data.get("output_data", {})
            input_count = ""
            output_count = ""
            if stage == "retrieval":
                input_count = "q: 1"
                output_count = f"结果: {len(out.get('results', []))}"
            elif stage == "rerank":
                input_count = f"输入: {len(inp.get('results', []))}"
                output_count = f"输出: {len(out.get('results', []))}"
            elif stage == "context_assembly":
                input_count = f"chunks: {inp.get('chunk_count', '?')}"
                output_count = f"tokens: {out.get('total_tokens', '?')}"
            elif stage == "query_rewrite":
                input_count = "q: 1"
                output_count = f"改写: {len(out.get('rewritten_queries', []))}"
            elif stage == "generation":
                input_count = f"tokens: {inp.get('total_tokens', '?')}"
                output_count = f"tokens: {out.get('output_tokens', '?')}"

            bg = "#d4edda"
            border = "#28a745"
            detail = f"<div style='font-size:0.7em;color:#555;'>{duration:.0f}ms</div>"
            if input_count or output_count:
                detail += f"<div style='font-size:0.65em;color:#888;'>{input_count} → {output_count}</div>"
        else:
            bg = "#e9ecef"
            border = "#adb5bd"
            detail = "<div style='font-size:0.7em;color:#999;'>未执行</div>"

        stage_cells.append(
            f"<div style='background:{bg};border:2px solid {border};border-radius:8px;"
            f"padding:8px 12px;text-align:center;min-width:100px;flex:1;'>"
            f"<div style='font-weight:bold;font-size:0.85em;'>{label}</div>"
            f"{detail}</div>"
        )

    arrows = " <div style='display:flex;align-items:center;color:#6c757d;font-size:1.2em;padding:0 2px;'>→</div> "
    html_content = (
        "<div style='display:flex;align-items:center;gap:0;overflow-x:auto;padding:8px 0;'>"
        + arrows.join(stage_cells)
        + "</div>"
    )
    st.html(html_content)


def _render_stage_detail(steps: list[dict[str, Any]]) -> None:
    stage_labels = {
        "query_rewrite": "🔍 查询改写",
        "retrieval": "🔎 检索",
        "rerank": "📊 重排序",
        "context_assembly": "📦 上下文组装",
        "generation": "🤖 答案生成",
    }

    for step in steps:
        stage = step.get("stage", "")
        label = stage_labels.get(stage, stage)
        inp = step.get("input_data", {})
        out = step.get("output_data", {})
        duration = step.get("duration_ms", 0)

        with st.expander(f"{label} ({duration:.0f}ms)"):
            if stage == "query_rewrite":
                original = inp.get("query", "")
                rewritten = out.get("rewritten_queries", [])
                st.markdown("**原始问题：**")
                st.info(original)
                if rewritten:
                    st.markdown("**改写结果：**")
                    for i, rq in enumerate(rewritten):
                        st.markdown(f"{i + 1}. {rq}")

            elif stage == "retrieval":
                results = out.get("results", [])
                if results:
                    rows = []
                    for r in results:
                        rows.append(
                            {
                                "chunk_id": r.get("chunk_id", ""),
                                "score": f"{r.get('score', 0):.4f}",
                                "source": r.get("source", ""),
                            }
                        )
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.info("无检索结果")

            elif stage == "rerank":
                before = inp.get("results", [])
                after = out.get("results", [])
                col_b, col_a = st.columns(2)
                with col_b:
                    st.markdown("**重排序前**")
                    for r in before:
                        st.markdown(
                            f"- `{r.get('chunk_id', '')}` score={r.get('score', 0):.4f}"
                        )
                with col_a:
                    st.markdown("**重排序后**")
                    for r in after:
                        st.markdown(
                            f"- `{r.get('chunk_id', '')}` score={r.get('score', 0):.4f}"
                        )

            elif stage == "context_assembly":
                truncated = out.get("truncated", False)
                total_tokens = out.get("total_tokens", 0)
                max_tokens = inp.get("max_context_tokens", 0)
                context_count = out.get("context_count", 0)
                st.markdown(f"**上下文 chunks 数：** {context_count}")
                st.markdown(f"**总 tokens：** {total_tokens} / {max_tokens}")
                if truncated:
                    st.warning("⚠️ 上下文被截断")

            elif stage == "generation":
                system_prompt = inp.get("system_prompt", "")
                user_message = inp.get("user_message", "")
                answer = out.get("answer", "")
                if system_prompt:
                    st.markdown("**System Prompt：**")
                    st.code(system_prompt, language="markdown")
                if user_message:
                    st.markdown("**User Message：**")
                    st.code(user_message, language="markdown")
                if answer:
                    st.markdown("**生成答案：**")
                    st.success(answer)


def _render_ground_truth_annotation(case_data: dict[str, Any], case_id: str) -> None:
    st.markdown("### 📍 Ground Truth 标注")

    meal_snapshot = case_data.get("meal_snapshot", {})
    pdf_files = meal_snapshot.get("pdf_files", [])
    existing_gt = case_data.get("ground_truth")

    if existing_gt:
        st.info(
            f"已有标注：source_pdf={existing_gt.get('source_pdf', '')}, "
            f"page={existing_gt.get('source_page', '')}, "
            f"chunk_ids={existing_gt.get('chunk_ids', [])}"
        )

    pdf_options = [pf.get("path", "") for pf in pdf_files] if pdf_files else []
    if not pdf_options:
        st.warning("Meal 快照中无 PDF 文件信息，无法标注")
        return

    selected_pdf = st.selectbox(
        "选择 PDF 文件",
        pdf_options,
        index=0,
        key=f"gt_pdf_{case_id}",
    )

    page_number = st.number_input(
        "页码",
        min_value=1,
        value=existing_gt.get("source_page", 1) if existing_gt else 1,
        key=f"gt_page_{case_id}",
    )

    answer_text = st.text_area(
        "参考答案（可选）",
        value=existing_gt.get("answer_text", "") if existing_gt else "",
        key=f"gt_answer_{case_id}",
    )

    found_chunks: list[dict[str, Any]] = []
    if st.button("查找 Chunk", key=f"gt_find_{case_id}"):
        chunks_dir = _get_chunks_dir(case_data)
        if chunks_dir is None:
            st.error("无法定位 chunks 目录，请检查 meal_snapshot 和 config_snapshot")
        else:
            with st.spinner("查找中..."):
                try:
                    found_chunks = find_chunks_by_source_page(
                        source_pdf=selected_pdf,
                        page_number=page_number,
                        chunks_dir=chunks_dir,
                    )
                    st.session_state[f"gt_found_chunks_{case_id}"] = found_chunks
                except Exception as e:
                    logger.error(f"Failed to find chunks: {e}")
                    st.error(f"查找失败: {e}")
                    st.session_state[f"gt_found_chunks_{case_id}"] = []

    found_chunks = st.session_state.get(f"gt_found_chunks_{case_id}", [])
    if found_chunks:
        st.markdown(f"**找到 {len(found_chunks)} 个 Chunk：**")
        for i, chunk in enumerate(found_chunks):
            with st.expander(f"Chunk {i + 1}: {chunk.get('chunk_id', '')}"):
                st.text(chunk.get("text", "")[:500])

    chunk_ids = [c.get("chunk_id", "") for c in found_chunks if c.get("chunk_id")]

    if st.button("确认保存", type="primary", key=f"gt_save_{case_id}"):
        gt = GroundTruth(
            answer_text=answer_text,
            source_pdf=selected_pdf,
            source_page=page_number,
            chunk_ids=chunk_ids or None,
            annotated_at=datetime.now().isoformat(),
            annotator="user",
        )
        try:
            save_ground_truth(case_id, gt)
            st.success("Ground Truth 已保存")
            st.session_state[f"gt_just_saved_{case_id}"] = True
            st.rerun()
        except Exception as e:
            logger.error(f"Failed to save ground truth: {e}")
            st.error(f"保存失败: {e}")


def _severity_color(severity: str) -> str:
    colors = {
        "low": "#28a745",
        "medium": "#fd7e14",
        "high": "#dc3545",
        "critical": "#7b0000",
    }
    return colors.get(severity, "#6c757d")


def _render_diagnosis(case_data: dict[str, Any], case_id: str) -> None:
    st.markdown("### 🩺 诊断报告")

    diagnosis = case_data.get("diagnosis")
    just_saved = st.session_state.get(f"gt_just_saved_{case_id}", False)

    if diagnosis is None and just_saved:
        trace_data = case_data.get("pipeline_trace")
        gt_data = case_data.get("ground_truth")
        if trace_data and gt_data:
            with st.spinner("正在自动诊断..."):
                try:
                    result = diagnose(trace_data, gt_data)
                    save_diagnosis(case_id, result)
                    diagnosis = result.to_dict()
                    st.session_state.pop(f"gt_just_saved_{case_id}", None)
                    st.success("诊断完成")
                except Exception as e:
                    logger.error(f"Auto-diagnosis failed: {e}")
                    st.error(f"诊断失败: {e}")
                    return
        else:
            st.warning("缺少 pipeline_trace 或 ground_truth，无法自动诊断")
            return

    if diagnosis is None:
        gt_data = case_data.get("ground_truth")
        if gt_data:
            st.info("已有 Ground Truth 但尚未诊断。请先保存 Ground Truth 触发诊断。")
        else:
            st.info("尚未标注 Ground Truth，无法生成诊断报告")
        return

    root_cause_id = diagnosis.get("root_cause_id", "")
    root_cause = diagnosis.get("root_cause", "")
    severity = diagnosis.get("severity", "")
    finding = diagnosis.get("finding", "")
    fix_suggestion = diagnosis.get("fix_suggestion", "")
    config_patch = diagnosis.get("config_patch", {})
    confidence = diagnosis.get("confidence", 1.0)

    rc_label = ROOT_CAUSES.get(root_cause_id, (root_cause, ""))[1]
    color = _severity_color(severity)

    st.html(
        f"<div style='display:flex;gap:12px;align-items:center;margin-bottom:12px;'>"
        f"<span style='background:{color};color:#fff;padding:6px 16px;border-radius:6px;"
        f"font-size:1.1em;font-weight:bold;'>{root_cause_id}: {rc_label}</span>"
        f"<span style='background:{color};color:#fff;padding:4px 12px;border-radius:4px;"
        f"font-size:0.9em;'>{severity.upper()}</span>"
        f"<span style='color:#888;font-size:0.85em;'>置信度: {confidence:.0%}</span>"
        f"</div>"
    )

    st.markdown("**发现：**")
    st.markdown(finding)

    if fix_suggestion:
        st.markdown("**修复建议：**")
        st.markdown(fix_suggestion)

    if config_patch:
        st.markdown("**配置建议：**")
        st.json(config_patch)


def render_case_analyzer() -> None:
    st.title("🔍 Bad Case 深度分析")

    cases = _cached_list_bad_cases()

    if not cases:
        st.info("暂无 Bad Case 记录。在问答页面标记 Badcase 后，这里会显示。")
        return

    options = []
    for c in cases:
        preview = c.get("question_preview", "unknown")
        created = c.get("created_at", "")
        has_gt = "✅" if c.get("has_ground_truth") else "⬜"
        has_diag = "🩺" if c.get("has_diagnosis") else "⬜"
        root_cause = c.get("root_cause", "")
        rc_tag = f"[{root_cause}]" if root_cause else ""
        options.append(
            f"{c.get('case_id', '')} | {preview} | {created[:16]} | GT:{has_gt} Diag:{has_diag} {rc_tag}"
        )

    selected_idx = st.selectbox(
        "选择 Case",
        range(len(options)),
        format_func=lambda i: options[i],
        key="case_selector",
    )

    if selected_idx is None:
        return

    selected_case = cases[selected_idx]
    case_id = selected_case.get("case_id", "")

    with st.spinner("加载 Case 数据..."):
        try:
            case_data = load_case(case_id)
        except Exception as e:
            logger.error(f"Failed to load case {case_id}: {e}")
            st.error(f"加载失败: {e}")
            return

    manifest = case_data.get("manifest", {})
    st.markdown(f"**问题：** {manifest.get('question_preview', '')}")
    st.caption(f"Case ID: {case_id} | 创建时间: {manifest.get('created_at', '')}")

    trace_data = case_data.get("pipeline_trace")
    if trace_data:
        steps = trace_data.get("steps", [])
        if steps:
            st.markdown("#### 管线追踪")
            _render_pipeline_trace_html(steps)
            _render_stage_detail(steps)
    else:
        st.info("此 Case 无管线追踪数据")

    query_result = case_data.get("query_result", {})
    if query_result:
        with st.expander("📋 查询结果详情"):
            answer = query_result.get("answer", "")
            if answer:
                st.success(answer)
            sources = query_result.get("sources", [])
            scores = query_result.get("scores", [])
            if sources:
                st.markdown("**来源：**")
                for i, (src, score) in enumerate(zip(sources, scores, strict=False)):
                    st.markdown(f"{i + 1}. {src} (score: {score:.4f})")

    _render_ground_truth_annotation(case_data, case_id)
    _render_diagnosis(case_data, case_id)
