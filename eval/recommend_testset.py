"""Test set recommendation generator.

Given a meal name and target question count, analyzes the meal's MD files
(by text size, not PDF size) and generates a recommended question distribution
across documents and question types.

Usage:
    pixi run python eval/recommend_testset.py --meal 5kpage --num-questions 50
"""

import argparse
import json
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.meal import MealConfig

QUESTION_TYPES = {
    "single_fact": "\u5355\u77e5\u8bc6\u70b9\u67e5\u8be2",
    "multi_fact": "\u591a\u77e5\u8bc6\u70b9\u7efc\u5408",
    "reasoning": "\u63a8\u7406\u578b\u95ee\u9898",
    "comparative": "\u5bf9\u6bd4\u5206\u6790",
    "missing": "\u7f3a\u5931\u77e5\u8bc6\u70b9",
    "irrelevant": "\u65e0\u5173\u95ee\u9898",
}

DOC_BOUND_TYPES = {"single_fact", "multi_fact", "reasoning", "comparative"}
FREE_TYPES = {"missing", "irrelevant"}

TYPE_DISTRIBUTION = {
    "single_fact": 0.28,
    "multi_fact": 0.22,
    "reasoning": 0.16,
    "comparative": 0.12,
    "missing": 0.12,
    "irrelevant": 0.10,
}

CATEGORY_TYPE_AFFINITY = {
    "annual_report": {
        "single_fact": 0.20,
        "multi_fact": 0.35,
        "reasoning": 0.20,
        "comparative": 0.25,
    },
    "research_report": {
        "single_fact": 0.40,
        "multi_fact": 0.25,
        "reasoning": 0.20,
        "comparative": 0.15,
    },
}

SIZE_TIERS = {
    "large": {"min_kb": 200, "max_questions_per_doc": 5},
    "medium": {"min_kb": 50, "max_questions_per_doc": 3},
    "small": {"min_kb": 0, "max_questions_per_doc": 1},
}


def get_md_path_for_pdf(pdf_path: str, parsed_dir: Path) -> Path | None:
    stem = Path(pdf_path).stem
    for md_file in parsed_dir.rglob("*.md"):
        if md_file.stem == stem:
            return md_file
    return None


def classify_size(text_kb: float) -> str:
    for tier_name, tier_config in SIZE_TIERS.items():
        if text_kb >= tier_config["min_kb"]:
            return tier_name
    return "small"


def analyze_meal(meal: MealConfig, parsed_dir: Path) -> list[dict]:
    results = []
    for pdf_file in meal.pdf_files:
        md_path = get_md_path_for_pdf(pdf_file.path, parsed_dir)
        if md_path is None or not md_path.exists():
            logger.warning(f"MD not found for {pdf_file.path}")
            continue

        text = md_path.read_text(encoding="utf-8")
        text_kb = len(text.encode("utf-8")) / 1024
        size_tier = classify_size(text_kb)

        pdf_path_str = Path(pdf_file.path).as_posix()
        category = (
            "annual_report" if "annual_reports" in pdf_path_str else "research_report"
        )

        results.append(
            {
                "pdf_path": pdf_path_str,
                "md_path": md_path.as_posix(),
                "md_name": md_path.stem,
                "display_name": f"{md_path.parent.name}/{md_path.stem}",
                "text_kb": round(text_kb, 1),
                "text_chars": len(text),
                "size_tier": size_tier,
                "category": category,
            }
        )
    return results


def _allocate_type_counts(
    num_questions: int,
    type_distribution: dict[str, float],
) -> dict[str, int]:
    type_counts = {}
    for qtype, ratio in type_distribution.items():
        type_counts[qtype] = max(1, round(ratio * num_questions))

    diff = num_questions - sum(type_counts.values())
    if diff != 0:
        sorted_types = sorted(
            type_counts.keys(), key=lambda t: type_counts[t], reverse=True
        )
        for i in range(abs(diff)):
            if diff > 0:
                type_counts[sorted_types[i % len(sorted_types)]] += 1
            else:
                type_counts[sorted_types[i % len(sorted_types)]] = max(
                    0, type_counts[sorted_types[i % len(sorted_types)]] - 1
                )
            diff -= 1 if diff > 0 else -1
            if diff == 0:
                break
    return type_counts


def distribute_questions(
    doc_info: list[dict],
    num_questions: int,
    type_distribution: dict[str, float] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    if type_distribution is None:
        type_distribution = TYPE_DISTRIBUTION

    type_counts = _allocate_type_counts(num_questions, type_distribution)

    free_count = sum(type_counts.get(t, 0) for t in FREE_TYPES)
    doc_bound_count = num_questions - free_count

    total_text_kb = sum(d["text_kb"] for d in doc_info)
    if total_text_kb == 0:
        logger.error("Total text size is 0, cannot distribute questions")
        return [], type_counts

    for d in doc_info:
        d["weight"] = d["text_kb"] / total_text_kb
        d["raw_allocation"] = d["weight"] * doc_bound_count

    raw_total = sum(d["raw_allocation"] for d in doc_info)
    for d in doc_info:
        d["raw_allocation"] = d["raw_allocation"] / raw_total * doc_bound_count

    tier_limits = {
        tier: cfg["max_questions_per_doc"] for tier, cfg in SIZE_TIERS.items()
    }
    for d in doc_info:
        cap = tier_limits[d["size_tier"]]
        d["capped_allocation"] = min(d["raw_allocation"], cap)

    overflow = doc_bound_count - sum(d["capped_allocation"] for d in doc_info)
    if overflow > 0:
        uncapped = sorted(
            [
                d
                for d in doc_info
                if d["capped_allocation"] < tier_limits[d["size_tier"]]
            ],
            key=lambda d: d["weight"],
            reverse=True,
        )
        idx = 0
        while overflow > 0.01 and uncapped:
            d = uncapped[idx % len(uncapped)]
            cap = tier_limits[d["size_tier"]]
            add = min(overflow, cap - d["capped_allocation"], 1.0)
            if add > 0.01:
                d["capped_allocation"] += add
                overflow -= add
            idx += 1
            if idx > doc_bound_count * 3:
                break

    for d in doc_info:
        d["num_questions"] = max(0, round(d["capped_allocation"]))

    rounding_diff = doc_bound_count - sum(d["num_questions"] for d in doc_info)
    if rounding_diff != 0:
        by_weight = sorted(doc_info, key=lambda d: d["weight"], reverse=True)
        for i in range(abs(rounding_diff)):
            if rounding_diff > 0:
                by_weight[i % len(by_weight)]["num_questions"] += 1
            else:
                by_weight[i % len(by_weight)]["num_questions"] = max(
                    0, by_weight[i % len(by_weight)]["num_questions"] - 1
                )
            rounding_diff -= 1 if rounding_diff > 0 else -1
            if rounding_diff == 0:
                break

    recommendations = []
    for d in doc_info:
        if d["num_questions"] <= 0:
            continue

        affinity = CATEGORY_TYPE_AFFINITY.get(
            d["category"],
            {k: v for k, v in type_distribution.items() if k in DOC_BOUND_TYPES},
        )
        doc_types = {}
        remaining = d["num_questions"]
        for qtype, aff_ratio in affinity.items():
            alloc = round(aff_ratio * d["num_questions"])
            doc_types[qtype] = alloc
            remaining -= alloc

        if remaining != 0:
            sorted_aff = sorted(
                affinity.keys(), key=lambda t: affinity[t], reverse=True
            )
            for i in range(abs(remaining)):
                if remaining > 0:
                    doc_types[sorted_aff[i % len(sorted_aff)]] += 1
                else:
                    doc_types[sorted_aff[i % len(sorted_aff)]] = max(
                        0, doc_types[sorted_aff[i % len(sorted_aff)]] - 1
                    )
                remaining -= 1 if remaining > 0 else -1
                if remaining == 0:
                    break

        recommendations.append(
            {
                "pdf_path": d["pdf_path"],
                "md_name": d["md_name"],
                "display_name": d["display_name"],
                "text_kb": d["text_kb"],
                "size_tier": d["size_tier"],
                "category": d["category"],
                "num_questions": d["num_questions"],
                "question_types": {k: v for k, v in doc_types.items() if v > 0},
            }
        )

    return recommendations, type_counts


def format_recommendation(
    recommendations: list[dict],
    type_counts: dict[str, int],
    num_questions: int,
) -> str:
    lines = []
    lines.append(f"# Test Set Recommendation ({num_questions} questions)")
    lines.append("")

    lines.append("## Question Type Distribution")
    lines.append("")
    lines.append("| Type | Count | Ratio | Description |")
    lines.append("|------|-------|-------|-------------|")
    for qtype in QUESTION_TYPES:
        count = type_counts.get(qtype, 0)
        ratio = f"{count / num_questions:.0%}" if num_questions > 0 else "0%"
        lines.append(f"| {qtype} | {count} | {ratio} | {QUESTION_TYPES[qtype]} |")
    lines.append("")

    free_total = sum(type_counts.get(t, 0) for t in FREE_TYPES)
    lines.append(f"**Document-bound questions**: {num_questions - free_total}")
    lines.append(f"**Free-floating questions** (missing/irrelevant): {free_total}")
    lines.append("")
    lines.append(
        "> missing/irrelevant questions do not need to be tied to a specific document."
    )
    lines.append("> For missing: pick a document, ask about info it does NOT contain.")
    lines.append(
        "> For irrelevant: ask something completely unrelated to any document."
    )
    lines.append("")

    tier_order = {
        "large": "Large (>=200KB)",
        "medium": "Medium (50-200KB)",
        "small": "Small (<50KB)",
    }
    for tier_key, tier_label in tier_order.items():
        tier_docs = [r for r in recommendations if r["size_tier"] == tier_key]
        if not tier_docs:
            continue
        tier_total = sum(r["num_questions"] for r in tier_docs)
        lines.append(f"## {tier_label} ({len(tier_docs)} docs, {tier_total} questions)")
        lines.append("")
        lines.append("| # | Document | Text Size | Category | Questions | Types |")
        lines.append("|---|----------|-----------|----------|-----------|-------|")
        for i, r in enumerate(
            sorted(tier_docs, key=lambda x: x["text_kb"], reverse=True), 1
        ):
            types_str = ", ".join(f"{k}:{v}" for k, v in r["question_types"].items())
            lines.append(
                f"| {i} | {r['display_name'][:50]} | {r['text_kb']:.0f}KB | {r['category']} | {r['num_questions']} | {types_str} |"
            )
        lines.append("")

    lines.append("## Per-Document Detail")
    lines.append("")
    for i, r in enumerate(recommendations, 1):
        lines.append(f"### {i}. {r['display_name']}")
        lines.append(f"- PDF: `{r['pdf_path']}`")
        lines.append(f"- Text size: {r['text_kb']:.1f}KB")
        lines.append(f"- Category: {r['category']}")
        lines.append(f"- Total questions: {r['num_questions']}")
        lines.append("- Question types:")
        for qtype, count in r["question_types"].items():
            lines.append(f"  - {qtype} ({QUESTION_TYPES[qtype]}): {count}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate test set recommendations")
    parser.add_argument("--meal", required=True, help="Meal name (e.g. 5kpage)")
    parser.add_argument(
        "--num-questions", type=int, default=50, help="Target number of questions"
    )
    parser.add_argument(
        "--output", default=None, help="Output file path (default: stdout)"
    )
    args = parser.parse_args()

    meals_dir = Path("data/meals")
    meal_dir = meals_dir / args.meal
    manifest_path = meal_dir / "manifest.json"

    if not manifest_path.exists():
        logger.error(f"Meal manifest not found: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, encoding="utf-8") as f:
        meal_data = json.load(f)

    meal = MealConfig.from_dict(meal_data)

    parsed_dir = Path("data/parsed")
    if not parsed_dir.exists():
        logger.error(f"Parsed directory not found: {parsed_dir}")
        sys.exit(1)

    doc_info = analyze_meal(meal, parsed_dir)
    if not doc_info:
        logger.error("No documents found for analysis")
        sys.exit(1)

    logger.info(f"Analyzed {len(doc_info)} documents for meal '{args.meal}'")

    recommendations, type_counts = distribute_questions(doc_info, args.num_questions)
    output = format_recommendation(recommendations, type_counts, args.num_questions)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        logger.success(f"Recommendation written to {args.output}")
    else:
        out_path = (
            Path("data/exp_reports")
            / f"testset_recommendation_{args.meal}_n{args.num_questions}.md"
        )
        out_path.write_text(output, encoding="utf-8")
        logger.success(f"Recommendation written to {out_path}")


if __name__ == "__main__":
    main()
