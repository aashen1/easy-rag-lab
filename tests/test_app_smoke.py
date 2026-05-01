import pytest

from src.exceptions import RetrievalError

pytestmark = pytest.mark.unit


class TestAppLoad:
    def test_app_loads_no_exception(self, app):
        assert not app.exception

    def test_tab_count(self, app):
        assert len(app.tabs) == 2


class TestQADemoTab:
    def test_title_renders(self, app):
        assert len(app.title) > 0
        assert "金融研报" in app.title[0].value

    def test_sidebar_meal_selector_exists(self, app):
        meal_selectboxes = [sb for sb in app.selectbox if sb.label == "Meal"]
        assert len(meal_selectboxes) >= 1

    def test_meal_selector_options(self, app):
        meal_sb = next(sb for sb in app.selectbox if sb.label == "Meal")
        options = meal_sb.options
        assert "(无 Meal)" in options
        assert "+ 新建 Meal" in options

    def test_select_existing_meal(self, app):
        meal_sb = next(sb for sb in app.selectbox if sb.label == "Meal")
        meal_sb.select("测试Meal").run(timeout=30)
        assert not app.exception

    def test_select_no_meal(self, app):
        meal_sb = next(sb for sb in app.selectbox if sb.label == "Meal")
        meal_sb.select("(无 Meal)").run(timeout=30)
        assert not app.exception

    def test_select_new_meal_form(self, app):
        meal_sb = next(sb for sb in app.selectbox if sb.label == "Meal")
        meal_sb.select("+ 新建 Meal").run(timeout=30)
        assert not app.exception
        name_inputs = [ti for ti in app.text_input if ti.label == "Meal 名称（可选）"]
        assert len(name_inputs) >= 1

    def test_new_meal_sample_mode_switch(self, app):
        meal_sb = next(sb for sb in app.selectbox if sb.label == "Meal")
        meal_sb.select("+ 新建 Meal").run(timeout=30)
        sample_sb = next(sb for sb in app.selectbox if sb.label == "采样方式")
        assert not app.exception
        sample_sb.select("count").run(timeout=30)
        assert not app.exception

    def test_retrieval_method_selector(self, app):
        method_sb = next(sb for sb in app.selectbox if sb.label == "检索策略")
        assert not app.exception
        method_sb.select("bm25").run(timeout=30)
        assert not app.exception
        method_sb.select("hybrid").run(timeout=30)
        assert not app.exception

    def test_top_k_slider(self, app):
        sliders = [s for s in app.slider if s.label == "Top-K"]
        assert len(sliders) >= 1
        assert not app.exception

    def test_reranker_checkbox(self, app):
        checkboxes = [cb for cb in app.checkbox if cb.label == "启用 Reranker"]
        assert len(checkboxes) >= 1
        checkboxes[0].check().run(timeout=30)
        assert not app.exception

    def test_query_rewrite_checkbox(self, app):
        checkboxes = [cb for cb in app.checkbox if cb.label == "启用查询改写"]
        assert len(checkboxes) >= 1
        checkboxes[0].check().run(timeout=30)
        assert not app.exception

    def test_query_rewrite_strategy_appears(self, app):
        checkboxes = [cb for cb in app.checkbox if cb.label == "启用查询改写"]
        checkboxes[0].check().run(timeout=30)
        strategy_sbs = [sb for sb in app.selectbox if sb.label == "改写策略"]
        assert len(strategy_sbs) >= 1

    def test_query_rewrite_strategy_select(self, app):
        checkboxes = [cb for cb in app.checkbox if cb.label == "启用查询改写"]
        checkboxes[0].check().run(timeout=30)
        strategy_sb = next(sb for sb in app.selectbox if sb.label == "改写策略")
        strategy_sb.select("multi_query").run(timeout=30)
        assert not app.exception

    def test_clear_conversation(self, app):
        clear_btns = [b for b in app.button if "清空" in (b.label or "")]
        assert len(clear_btns) >= 1

    def test_chat_input_exists(self, app):
        assert len(app.chat_input) >= 1

    def test_chat_input_send(self, app, ui_mock_pipeline):
        app.chat_input[0].set_value("什么是ROE？").run(timeout=30)
        assert not app.exception

    def test_chat_input_bm25_error(self, app, ui_mock_pipeline):
        ui_mock_pipeline.query.side_effect = RetrievalError(
            "BM25 index not found: no chunks available"
        )
        app.chat_input[0].set_value("测试BM25错误").run(timeout=30)
        error_msgs = [e.value for e in app.error]
        assert any("BM25" in msg for msg in error_msgs)

    def test_chat_input_reranker_error(self, app, ui_mock_pipeline):
        ui_mock_pipeline.query.side_effect = RetrievalError(
            "Reranker model loading failed: model file not found"
        )
        app.chat_input[0].set_value("测试Reranker错误").run(timeout=30)
        error_msgs = [e.value for e in app.error]
        assert any("Reranker" in msg for msg in error_msgs)


class TestAboutTab:
    def test_about_renders(self, app):
        assert not app.exception
        titles = [t.value for t in app.title]
        assert any("系统信息" in t for t in titles)

    def test_about_contains_tech_stack(self, app):
        md_texts = [m.value for m in app.markdown]
        combined = " ".join(md_texts)
        assert "技术栈" in combined


class TestPDFPreviewTab:
    def test_no_pdf_no_tab(self, app):
        assert len(app.tabs) == 2

    def test_pdf_tab_appears_with_path(self, app_with_pdf):
        assert len(app_with_pdf.tabs) == 3
        assert not app_with_pdf.exception

    def test_close_pdf_preview(self, app_with_pdf):
        close_btns = [
            b for b in app_with_pdf.button if b.key and "close_pdf_preview" in b.key
        ]
        if close_btns:
            close_btns[0].click().run(timeout=30)
            assert not app_with_pdf.exception
