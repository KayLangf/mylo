"""Diagnostic: check whether retrieval reliably surfaces the FNS 360
(2025) income-limit chunk across different phrasings of the same
underlying question, or whether it's sensitive to how the question is
worded. Read-only — does not modify retrieval.py, agent.py, or any
guardrail code; just calls retrieval.retrieve() and reports what comes
back.

Context: a live conversation turn responded "I don't have the exact
income limits table pulled up right now" to an income-limits question.
This script checks whether that was a genuine retrieval miss (the 2025
income-limit chunk didn't make the top-k for that phrasing) or just
inconsistent phrasing of a response when the chunk actually was
retrieved.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import retrieval

TARGET_SOURCE = "03_fns_360_benefit_levels_2025.md"
TOP_K = 4

QUERIES = [
    "What are the income limits for SNAP?",
    "What are the current income limits?",
    "Can you give me the income limits table?",
    "What is the income limit for a household of 4?",
    "income limits",
]


def main():
    results_summary = []

    for i, query in enumerate(QUERIES, 1):
        print(f"=== Query {i}: {query!r} ===")
        chunks = retrieval.retrieve(query, top_k=TOP_K)

        found = False
        for rank, chunk in enumerate(chunks, 1):
            is_target = chunk["source"] == TARGET_SOURCE
            found = found or is_target
            marker = "  <-- TARGET (FNS 360 2025)" if is_target else ""
            print(
                f"  [{rank}] source={chunk['source']} | "
                f"section={chunk['section_title']} | "
                f"effective_date={chunk['effective_date']} | "
                f"distance={chunk['distance']:.4f}{marker}"
            )

        print(f"  TARGET FOUND IN TOP {TOP_K}: {found}")
        print()
        results_summary.append((query, found))

    print("=== Summary ===")
    for query, found in results_summary:
        print(f"  [{'HIT ' if found else 'MISS'}] {query!r}")

    hits = sum(1 for _, found in results_summary if found)
    misses = len(results_summary) - hits
    print()
    print(f"{hits} hit(s), {misses} miss(es) out of {len(results_summary)} query variants.")
    if hits and misses:
        print(
            "MIXED RESULT: retrieval is inconsistent across phrasings of the "
            "same underlying question — this points to query phrasing "
            "sensitivity in retrieval, not an agent honesty/phrasing issue."
        )
    elif misses == len(results_summary):
        print("ALL MISSES: retrieval never surfaces the target chunk for any phrasing tried.")
    else:
        print("ALL HITS: retrieval reliably surfaces the target chunk regardless of phrasing.")


if __name__ == "__main__":
    main()
