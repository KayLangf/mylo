"""Unit tests for src/eligibility.py — the deterministic gross-income
screening logic. Plain assertions, no pytest dependency (none is in
requirements.txt). Run via `python tests/test_eligibility.py`.

Expected figures below are copied directly from
data/knowledge_base/03_fns_360_benefit_levels_2025.md (FNS 360, Change
#01-2025, effective October 1, 2025) so this test catches drift between
the module's table and the actual knowledge base source of truth.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import eligibility  # noqa: E402

# household_size -> (200% limit, 130% limit), from 03_fns_360_benefit_levels_2025.md
EXPECTED_LIMITS = {
    1: (2610, 1696),
    2: (3526, 2292),
    3: (4442, 2888),
    4: (5360, 3483),
    5: (6276, 4079),
    6: (7192, 4675),
    7: (8110, 5271),
    8: (9026, 5867),
}

# household_size -> standard deduction, from the same document
EXPECTED_DEDUCTIONS = {
    1: 209,
    2: 209,
    3: 209,
    4: 223,
    5: 261,
    6: 299,
    7: 299,
    8: 299,
}

failures = []


def check(label, actual, expected):
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


# --- 1. Every row of the 2025 table, household sizes 1-8 ---
for size, (expected_200, expected_130) in EXPECTED_LIMITS.items():
    result = eligibility.screen_gross_income(size, 0)
    check(f"household={size} limit_200_pct", result.limit_200_pct, expected_200)
    check(f"household={size} limit_130_pct", result.limit_130_pct, expected_130)

# --- 1b. "Each additional member" formula, household size 9 and 10 ---
# 9 = size-8 limits + 1 * increment; 10 = size-8 limits + 2 * increment
limit_200_8, limit_130_8 = EXPECTED_LIMITS[8]
result_9 = eligibility.screen_gross_income(9, 0)
check("household=9 limit_200_pct", result_9.limit_200_pct, limit_200_8 + 918)
check("household=9 limit_130_pct", result_9.limit_130_pct, limit_130_8 + 596)
result_10 = eligibility.screen_gross_income(10, 0)
check("household=10 limit_200_pct", result_10.limit_200_pct, limit_200_8 + 2 * 918)
check("household=10 limit_130_pct", result_10.limit_130_pct, limit_130_8 + 2 * 596)

# --- 2. Standard deduction lookup, household sizes 1-8 ---
for size, expected in EXPECTED_DEDUCTIONS.items():
    check(f"deduction household={size}", eligibility.get_standard_deduction(size), expected)

# --- 3. Boundary cases: at limit, $1 over, $1 under ---
# Household of 1: 200% limit = $2,610, 130% limit = $1,696
result_at_200 = eligibility.screen_gross_income(1, 2610)
check("at 200% limit -> under_200_pct (inclusive)", result_at_200.under_200_pct, True)

result_over_200 = eligibility.screen_gross_income(1, 2611)
check("$1 over 200% limit -> under_200_pct", result_over_200.under_200_pct, False)

result_under_200 = eligibility.screen_gross_income(1, 2609)
check("$1 under 200% limit -> under_200_pct", result_under_200.under_200_pct, True)

result_at_130 = eligibility.screen_gross_income(1, 1696)
check("at 130% limit -> under_130_pct (inclusive)", result_at_130.under_130_pct, True)

result_over_130 = eligibility.screen_gross_income(1, 1697)
check("$1 over 130% limit -> under_130_pct", result_over_130.under_130_pct, False)

result_under_130 = eligibility.screen_gross_income(1, 1695)
check("$1 under 130% limit -> under_130_pct", result_under_130.under_130_pct, True)

# --- 4. Invalid input raises rather than silently guessing ---
try:
    eligibility.screen_gross_income(0, 1000)
    failures.append("household_size=0 should raise ValueError")
except ValueError:
    pass

try:
    eligibility.screen_gross_income(1, -100)
    failures.append("negative income should raise ValueError")
except ValueError:
    pass

# --- Report ---
total_checks = len(EXPECTED_LIMITS) * 2 + 4 + len(EXPECTED_DEDUCTIONS) + 6 + 2
if failures:
    print(f"FAILED ({len(failures)} issue(s)):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print(f"PASSED — all eligibility.py checks passed ({total_checks} assertions).")
