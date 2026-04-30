import pytest

from src.token_tracker import (
    DetailedTokenUsage,
    TokenRecord,
    TokenTracker,
    TokenUsage,
    compute_detailed_usage,
    estimate_tokens_tiktoken,
)


class TestTokenUsage:
    def test_default_values(self):
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_tokens == 0

    def test_custom_values(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_addition(self):
        a = TokenUsage(input_tokens=100, output_tokens=50)
        b = TokenUsage(input_tokens=200, output_tokens=80)
        c = a + b
        assert c.input_tokens == 300
        assert c.output_tokens == 130
        assert c.total_tokens == 430

    def test_addition_zero(self):
        a = TokenUsage(input_tokens=100, output_tokens=50)
        b = TokenUsage()
        c = a + b
        assert c.input_tokens == 100
        assert c.output_tokens == 50

    def test_to_dict(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        d = usage.to_dict()
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["total_tokens"] == 150


class TestDetailedTokenUsage:
    def test_default_values(self):
        usage = DetailedTokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.system_prompt_tokens == 0
        assert usage.contexts_tokens == 0
        assert usage.query_tokens == 0

    def test_custom_values(self):
        usage = DetailedTokenUsage(
            input_tokens=1000,
            output_tokens=300,
            system_prompt_tokens=200,
            contexts_tokens=600,
            query_tokens=200,
        )
        assert usage.total_tokens == 1300
        assert (
            usage.system_prompt_tokens + usage.contexts_tokens + usage.query_tokens
            == 1000
        )

    def test_to_dict(self):
        usage = DetailedTokenUsage(
            input_tokens=1000,
            output_tokens=300,
            system_prompt_tokens=200,
            contexts_tokens=600,
            query_tokens=200,
        )
        d = usage.to_dict()
        assert d["input_tokens"] == 1000
        assert d["output_tokens"] == 300
        assert d["total_tokens"] == 1300
        assert d["system_prompt_tokens"] == 200
        assert d["contexts_tokens"] == 600
        assert d["query_tokens"] == 200


class TestEstimateTokensTiktoken:
    def test_empty_string(self):
        assert estimate_tokens_tiktoken("") == 0

    def test_english_text(self):
        count = estimate_tokens_tiktoken("Hello, this is a test.")
        assert count > 0

    def test_chinese_text(self):
        count = estimate_tokens_tiktoken("贵州茅台2023年营业收入")
        assert count > 0

    def test_long_text(self):
        text = "This is a sentence. " * 100
        count = estimate_tokens_tiktoken(text)
        assert count > 100


class TestComputeDetailedUsage:
    def test_basic_breakdown(self):
        system_prompt = "You are a helpful assistant."
        contexts = ["Context 1 about finance.", "Context 2 about revenue."]
        query = "What is the revenue?"

        usage = compute_detailed_usage(
            api_input_tokens=100,
            api_output_tokens=50,
            system_prompt=system_prompt,
            contexts=contexts,
            query=query,
        )

        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150
        assert usage.system_prompt_tokens > 0
        assert usage.contexts_tokens > 0
        assert usage.query_tokens > 0
        assert (
            usage.system_prompt_tokens + usage.contexts_tokens + usage.query_tokens
            == 100
        )

    def test_no_contexts(self):
        usage = compute_detailed_usage(
            api_input_tokens=80,
            api_output_tokens=30,
            system_prompt="You are a helper.",
            contexts=[],
            query="What?",
        )

        assert usage.input_tokens == 80
        assert usage.contexts_tokens == 0
        assert usage.system_prompt_tokens + usage.query_tokens == 80

    def test_no_system_prompt(self):
        usage = compute_detailed_usage(
            api_input_tokens=60,
            api_output_tokens=20,
            system_prompt="",
            contexts=["Some context."],
            query="What?",
        )

        assert usage.input_tokens == 60
        assert usage.system_prompt_tokens == 0
        assert usage.contexts_tokens + usage.query_tokens == 60

    def test_zero_api_tokens(self):
        usage = compute_detailed_usage(
            api_input_tokens=0,
            api_output_tokens=0,
            system_prompt="Hello",
            contexts=["World"],
            query="?",
        )

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.system_prompt_tokens == 0
        assert usage.contexts_tokens == 0
        assert usage.query_tokens == 0

    def test_proportional_scaling(self):
        system_prompt = "A" * 100
        contexts = ["B" * 500]
        query = "C" * 50

        usage = compute_detailed_usage(
            api_input_tokens=1000,
            api_output_tokens=200,
            system_prompt=system_prompt,
            contexts=contexts,
            query=query,
        )

        assert usage.input_tokens == 1000
        assert usage.system_prompt_tokens > 0
        assert usage.contexts_tokens > 0
        assert usage.query_tokens > 0
        assert (
            usage.system_prompt_tokens + usage.contexts_tokens + usage.query_tokens
            == 1000
        )
        assert usage.contexts_tokens > usage.system_prompt_tokens
        assert usage.system_prompt_tokens > usage.query_tokens


class TestTokenRecord:
    def test_creation(self):
        usage = DetailedTokenUsage(input_tokens=100, output_tokens=50)
        record = TokenRecord(
            category="rag_qa",
            model_name="test-model",
            usage=usage,
            timestamp="2025-01-01T00:00:00",
            metadata={"question_id": "q1"},
        )
        assert record.category == "rag_qa"
        assert record.model_name == "test-model"
        assert record.usage.input_tokens == 100
        assert record.metadata["question_id"] == "q1"

    def test_to_dict(self):
        usage = DetailedTokenUsage(input_tokens=100, output_tokens=50)
        record = TokenRecord(
            category="rag_qa",
            model_name="test-model",
            usage=usage,
            timestamp="2025-01-01T00:00:00",
        )
        d = record.to_dict()
        assert d["category"] == "rag_qa"
        assert d["model_name"] == "test-model"
        assert d["usage"]["input_tokens"] == 100
        assert d["timestamp"] == "2025-01-01T00:00:00"


class TestTokenTracker:
    def test_empty_tracker(self):
        tracker = TokenTracker()
        assert tracker.record_count == 0
        total = tracker.get_total()
        assert total.input_tokens == 0
        assert total.output_tokens == 0

    def test_single_record(self):
        tracker = TokenTracker()
        usage = DetailedTokenUsage(input_tokens=100, output_tokens=50)
        tracker.record("rag_qa", "test-model", usage, question_id="q1")

        assert tracker.record_count == 1
        total = tracker.get_total()
        assert total.input_tokens == 100
        assert total.output_tokens == 50

    def test_multiple_records_same_category(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa", "model-a", DetailedTokenUsage(input_tokens=100, output_tokens=50)
        )
        tracker.record(
            "rag_qa", "model-a", DetailedTokenUsage(input_tokens=200, output_tokens=80)
        )

        assert tracker.record_count == 2
        total = tracker.get_total()
        assert total.input_tokens == 300
        assert total.output_tokens == 130

        summary = tracker.get_summary_by_category()
        assert "rag_qa" in summary
        assert summary["rag_qa"].input_tokens == 300

    def test_multiple_categories(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa", "model-a", DetailedTokenUsage(input_tokens=100, output_tokens=50)
        )
        tracker.record(
            "test_generation",
            "model-a",
            DetailedTokenUsage(input_tokens=80, output_tokens=30),
        )
        tracker.record(
            "report_generation",
            "model-a",
            DetailedTokenUsage(input_tokens=50, output_tokens=20),
        )

        summary = tracker.get_summary_by_category()
        assert len(summary) == 3
        assert summary["rag_qa"].input_tokens == 100
        assert summary["test_generation"].input_tokens == 80
        assert summary["report_generation"].input_tokens == 50

        total = tracker.get_total()
        assert total.input_tokens == 230
        assert total.output_tokens == 100

    def test_detailed_summary(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(
                input_tokens=100,
                output_tokens=50,
                system_prompt_tokens=20,
                contexts_tokens=60,
                query_tokens=20,
            ),
        )
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(
                input_tokens=200,
                output_tokens=80,
                system_prompt_tokens=40,
                contexts_tokens=120,
                query_tokens=40,
            ),
        )

        detailed = tracker.get_summary_by_category_detailed()
        assert "rag_qa" in detailed
        rag = detailed["rag_qa"]
        assert rag.input_tokens == 300
        assert rag.system_prompt_tokens == 60
        assert rag.contexts_tokens == 180
        assert rag.query_tokens == 60

    def test_get_records_by_category(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa", "model-a", DetailedTokenUsage(input_tokens=100, output_tokens=50)
        )
        tracker.record(
            "test_generation",
            "model-a",
            DetailedTokenUsage(input_tokens=80, output_tokens=30),
        )
        tracker.record(
            "rag_qa", "model-a", DetailedTokenUsage(input_tokens=200, output_tokens=80)
        )

        rag_records = tracker.get_records_by_category("rag_qa")
        assert len(rag_records) == 2
        test_records = tracker.get_records_by_category("test_generation")
        assert len(test_records) == 1

    def test_estimate_cost(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa",
            "test-model",
            DetailedTokenUsage(input_tokens=10000, output_tokens=5000),
        )

        cost_config = {
            "models": {
                "test-model": {
                    "input_price_per_1k": 0.001,
                    "output_price_per_1k": 0.002,
                    "conversion_factor": 1.0,
                }
            }
        }

        cost = tracker.estimate_cost(cost_config)
        assert cost["input_cost"] == 0.01
        assert cost["output_cost"] == 0.01
        assert cost["total_cost"] == 0.02
        assert cost["model"] == "test-model"

    def test_estimate_cost_empty_tracker(self):
        tracker = TokenTracker()
        cost_config = {"models": {}}
        cost = tracker.estimate_cost(cost_config)
        assert cost["total_cost"] == 0.0

    def test_estimate_cost_by_category(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa",
            "test-model",
            DetailedTokenUsage(input_tokens=10000, output_tokens=5000),
        )
        tracker.record(
            "test_generation",
            "test-model",
            DetailedTokenUsage(input_tokens=5000, output_tokens=2000),
        )

        cost_config = {
            "models": {
                "test-model": {
                    "input_price_per_1k": 0.001,
                    "output_price_per_1k": 0.002,
                }
            }
        }

        cost = tracker.estimate_cost(cost_config)
        assert "by_category" in cost
        assert "rag_qa" in cost["by_category"]
        assert "test_generation" in cost["by_category"]
        assert cost["by_category"]["rag_qa"]["total_cost"] == pytest.approx(0.02)
        assert cost["by_category"]["test_generation"]["total_cost"] == pytest.approx(
            0.009
        )

    def test_merge(self):
        tracker1 = TokenTracker()
        tracker1.record(
            "rag_qa", "model-a", DetailedTokenUsage(input_tokens=100, output_tokens=50)
        )

        tracker2 = TokenTracker()
        tracker2.record(
            "test_generation",
            "model-b",
            DetailedTokenUsage(input_tokens=80, output_tokens=30),
        )

        tracker1.merge(tracker2)
        assert tracker1.record_count == 2
        total = tracker1.get_total()
        assert total.input_tokens == 180

    def test_reset(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa", "model-a", DetailedTokenUsage(input_tokens=100, output_tokens=50)
        )
        assert tracker.record_count == 1

        tracker.reset()
        assert tracker.record_count == 0
        total = tracker.get_total()
        assert total.input_tokens == 0

    def test_to_dict(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(input_tokens=100, output_tokens=50),
            question_id="q1",
        )

        d = tracker.to_dict()
        assert "total" in d
        assert d["total"]["input_tokens"] == 100
        assert "by_category" in d
        assert "rag_qa" in d["by_category"]
        assert "records" in d
        assert len(d["records"]) == 1

    def test_get_detailed_table(self):
        tracker = TokenTracker()
        assert "No token usage" in tracker.get_detailed_table()

        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(
                input_tokens=1000,
                output_tokens=500,
                system_prompt_tokens=200,
                contexts_tokens=600,
                query_tokens=200,
            ),
        )

        table = tracker.get_detailed_table()
        assert "TOKEN USAGE SUMMARY" in table
        assert "rag_qa" in table
        assert "1,000" in table

    def test_get_summary_by_variant_empty(self):
        tracker = TokenTracker()
        summary = tracker.get_summary_by_variant()
        assert summary == {}

    def test_get_summary_by_variant_single_variant(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(input_tokens=100, output_tokens=50),
            variant_name="baseline",
        )
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(input_tokens=200, output_tokens=80),
            variant_name="baseline",
        )

        summary = tracker.get_summary_by_variant()
        assert "baseline" in summary
        assert "rag_qa" in summary["baseline"]
        assert summary["baseline"]["rag_qa"].input_tokens == 300
        assert summary["baseline"]["rag_qa"].output_tokens == 130

    def test_get_summary_by_variant_multiple_variants(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(input_tokens=100, output_tokens=50),
            variant_name="baseline",
        )
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(input_tokens=150, output_tokens=60),
            variant_name="rerank",
        )
        tracker.record(
            "test_generation",
            "model-a",
            DetailedTokenUsage(input_tokens=80, output_tokens=30),
            variant_name="baseline",
        )

        summary = tracker.get_summary_by_variant()
        assert len(summary) == 2
        assert "baseline" in summary
        assert "rerank" in summary
        assert summary["baseline"]["rag_qa"].input_tokens == 100
        assert summary["baseline"]["test_generation"].input_tokens == 80
        assert summary["rerank"]["rag_qa"].input_tokens == 150

    def test_get_summary_by_variant_no_variant_name(self):
        tracker = TokenTracker()
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(input_tokens=100, output_tokens=50),
        )
        tracker.record(
            "rag_qa",
            "model-a",
            DetailedTokenUsage(input_tokens=200, output_tokens=80),
            variant_name="baseline",
        )

        summary = tracker.get_summary_by_variant()
        assert "__none__" in summary
        assert "baseline" in summary
        assert summary["__none__"]["rag_qa"].input_tokens == 100
        assert summary["baseline"]["rag_qa"].input_tokens == 200

    def test_concurrent_record_thread_safety(self):
        import threading

        tracker = TokenTracker()
        num_threads = 10
        records_per_thread = 100

        def worker():
            for _ in range(records_per_thread):
                tracker.record(
                    "rag_qa",
                    "test-model",
                    DetailedTokenUsage(input_tokens=10, output_tokens=5),
                )

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tracker.record_count == num_threads * records_per_thread
