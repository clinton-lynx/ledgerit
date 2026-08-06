"""Routing accuracy check: does the model classifier send natural-language
questions to the right analysis category?

Standalone script — no pytest dependency (none is installed in the target
environment, and the brief forbids adding one). Run directly:

    python3 tests/test_routing.py

`test_routing_accuracy()` is also exposed so pytest can pick this file up if
pytest happens to be available; either way the real work is in
`run_routing_eval()`.

This exercises the actual local model (SmolLM3 via llama_cpp, same as
explain.classify in production) — it is not a mock. The question set below
was written to be a realistic sample of how a Nigerian shop owner might
actually ask, including several deliberately awkward or indirect phrasings
per category. It was NOT tuned to whatever the classifier currently gets
right — a couple of these are expected to be closer calls, and if the model
misses them, that is real signal for the report, not a bug in the test.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from explain import classify  # noqa: E402

ALL_CATEGORIES = {
    "ranking_by_product", "worst_by_product", "monthly_trend",
    "ranking_by_vendor", "ranking_by_channel", "ranking_by_payment",
    "quiet_days", "revenue_summary",
}

# (question, expected category, deliberately awkward/indirect phrasing?)
#
# Category labels below were renamed for parallel structure (see
# docs/routing-evaluation.md, "rename for parallel structure"):
#   top_products -> ranking_by_product, bottom_products -> worst_by_product,
#   by_vendor -> ranking_by_vendor, by_channel -> ranking_by_channel,
#   by_payment -> ranking_by_payment. Rename only — questions and phrasings
# are exactly as originally written, none tuned to any measured result.
CASES: list[tuple[str, str, bool]] = [
    # -- ranking_by_product ---------------------------------------------
    ("What are my best-selling products?", "ranking_by_product", False),
    ("Which items bring in the most money?", "ranking_by_product", False),
    ("What are my top sellers this month?", "ranking_by_product", False),
    ("What should I make sure I never run out of?", "ranking_by_product", True),
    ("Which products are really carrying this business?", "ranking_by_product", True),
    # Added after a real demo chip ("What are my best sellers?") misrouted
    # to the fallback summary. classify() logs the raw completion for each:
    # every one of these gets the literal token "bestsellers" echoed back
    # (e.g. 'bestsellers\n\nI chose "bestsellers'), pulled straight out of
    # the ranking_by_product line in CATEGORIES ("...most popular selling
    # products; bestsellers; what sells the most..."), instead of the label
    # key ranking_by_product. classify()'s own parser correctly rejects
    # that stray word (it isn't in _CATEGORY_LABELS) and returns None — the
    # miss is a real vocabulary collision in CATEGORIES's description text,
    # not model incapacity or a parsing bug. Left in as failures, not
    # tuned away: see docs/routing-evaluation.md for the honest number.
    ("What are my best sellers?", "ranking_by_product", False),
    ("Show me my best sellers.", "ranking_by_product", False),
    ("What sells the most?", "ranking_by_product", False),
    ("What's my most popular product?", "ranking_by_product", False),
    ("What do customers buy most often?", "ranking_by_product", False),
    ("What are people buying the most?", "ranking_by_product", True),
    ("What's flying off the shelves?", "ranking_by_product", True),

    # -- worst_by_product --------------------------------------------------
    ("What's not selling well?", "worst_by_product", False),
    ("Which products should I stop carrying?", "worst_by_product", False),
    ("What are my worst performers?", "worst_by_product", False),
    ("What's just sitting on the shelf gathering dust?", "worst_by_product", True),
    ("What should I discount just to clear it out?", "worst_by_product", True),

    # -- monthly_trend ----------------------------------------------------
    ("Is my revenue growing or shrinking?", "monthly_trend", False),
    ("How has business changed over the months?", "monthly_trend", False),
    ("Show me the sales trend over time.", "monthly_trend", False),
    ("Are things getting better or worse lately?", "monthly_trend", True),
    ("Did last month beat the one before it?", "monthly_trend", True),

    # -- ranking_by_vendor ----------------------------------------------------
    ("Which vendor brings in the most revenue?", "ranking_by_vendor", False),
    ("Compare my suppliers.", "ranking_by_vendor", False),
    ("Which branch is doing best?", "ranking_by_vendor", False),
    ("Who am I buying the most product from?", "ranking_by_vendor", True),
    ("Break down sales by outlet.", "ranking_by_vendor", False),

    # -- ranking_by_channel -----------------------------------------------
    ("Do I sell more through the app or walk-ins?", "ranking_by_channel", False),
    ("Which sales channel performs best?", "ranking_by_channel", False),
    ("Are online orders bigger than in-store ones?", "ranking_by_channel", False),
    ("Compare delivery sales against walk-in sales.", "ranking_by_channel", True),
    ("Where are most of my orders actually coming from?", "ranking_by_channel", True),

    # -- ranking_by_payment -----------------------------------------------
    ("Do customers pay more by cash or transfer?", "ranking_by_payment", False),
    ("Which payment method is most common?", "ranking_by_payment", False),
    ("Compare card sales against cash sales.", "ranking_by_payment", False),
    ("How much comes in via POS?", "ranking_by_payment", True),
    ("Are people paying by transfer more than card these days?", "ranking_by_payment", True),

    # -- quiet_days -------------------------------------------------------
    ("When is my shop dead?", "quiet_days", True),
    ("What's my slowest day of the week?", "quiet_days", False),
    ("When should I close early?", "quiet_days", True),
    ("Which day has no customers?", "quiet_days", True),
    ("When is business the quietest?", "quiet_days", False),
    ("Is it even worth opening on Mondays?", "quiet_days", True),

    # -- revenue_summary --------------------------------------------------
    ("How is my business doing overall?", "revenue_summary", False),
    ("What's my total revenue?", "revenue_summary", False),
    ("Give me the big picture on sales.", "revenue_summary", True),
    ("How many orders have I had in total?", "revenue_summary", False),
    ("Summarize my sales for me.", "revenue_summary", False),
]


def run_routing_eval(cases=CASES, verbose: bool = True) -> dict:
    per_category = defaultdict(lambda: [0, 0])  # expected -> [correct, total]
    misses = []
    latencies = []

    for question, expected, awkward in cases:
        t0 = time.perf_counter()
        got = classify(question)
        latencies.append(time.perf_counter() - t0)

        per_category[expected][1] += 1
        ok = got == expected
        if ok:
            per_category[expected][0] += 1
        else:
            misses.append((question, expected, got, awkward))
        if verbose:
            mark = "OK  " if ok else "MISS"
            tag = " [awkward]" if awkward else ""
            print(f"  [{mark}] {question!r}{tag} -> got={got!r} expected={expected!r}")

    total_correct = sum(c for c, _ in per_category.values())
    total_n = sum(t for _, t in per_category.values())
    mean_latency = sum(latencies) / len(latencies) if latencies else 0.0

    if verbose:
        print("\n--- Per-category accuracy ---")
        for cat in sorted(per_category):
            correct, total = per_category[cat]
            print(f"  {cat:<16} {correct}/{total}  ({correct / total:.0%})")

        print(f"\nOverall: {total_correct}/{total_n} ({total_correct / total_n:.0%})")
        print(f"Mean latency: {mean_latency:.2f}s/question "
              f"(total {sum(latencies):.1f}s for {len(cases)} questions)")

        if misses:
            print("\nMisrouted questions:")
            for question, expected, got, awkward in misses:
                tag = " [awkward]" if awkward else ""
                print(f"  {question!r}{tag}: expected {expected!r}, got {got!r}")
        else:
            print("\nNo misroutes.")

    return {
        "per_category": {k: tuple(v) for k, v in per_category.items()},
        "misses": misses,
        "total_correct": total_correct,
        "total_n": total_n,
        "mean_latency": mean_latency,
        "total_latency": sum(latencies),
    }


def test_routing_accuracy():
    """pytest entry point, if pytest happens to be installed in this env."""
    results = run_routing_eval(verbose=False)
    assert results["total_n"] == len(CASES)
    for cat in ALL_CATEGORIES:
        assert cat in results["per_category"], f"no test cases written for {cat}"
    # This suite exists to report an honest number, not to gate on one — a
    # single low-confidence miss shouldn't fail CI. It does fail if routing
    # falls apart wholesale, which would mean something is badly broken.
    assert results["total_correct"] / results["total_n"] >= 0.5


if __name__ == "__main__":
    n_awkward = sum(1 for *_, awkward in CASES if awkward)
    print(f"Running routing accuracy over {len(CASES)} questions "
          f"({n_awkward} deliberately awkward)...\n")
    run_routing_eval()
