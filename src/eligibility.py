"""Deterministic income and household-size eligibility logic for NC FNS
(SNAP). Plain Python calculations only — eligibility math is never
LLM-guessed. If required inputs are missing, callers should prompt the
user for them rather than assuming values.

This module only screens GROSS monthly income against the 200%/130%
limits. Net income (after shelter, medical, and dependent-care
deductions) is a distinct, more complex calculation and is out of scope
here — see CLAUDE.md/SPEC.md for why (Mylo doesn't reliably collect the
inputs net income would require; see the topic-shift retrieval gap
documented in tests/personas/11_retrieval_topk_and_topic_shift.md).

This module never renders a final yes/no eligibility determination —
only a caseworker can do that, using net income, deductions, and other
factors this module doesn't model. It only reports where a household
falls relative to the gross income screening thresholds.
"""

from dataclasses import dataclass

# Source: data/knowledge_base/03_fns_360_benefit_levels_2025.md
# NC DHHS FNS 360 — Determining Benefit Levels, Change #01-2025,
# effective October 1, 2025. This is the CURRENT, non-superseded version
# (see SPEC.md Section 12 on the 2021 vs. 2025 FNS 360 conflict) — this
# module intentionally uses only the 2025 figures, never the 2021 ones
# in 02_fns_360_benefit_levels_2021.md.
SOURCE_DOCUMENT = "03_fns_360_benefit_levels_2025.md"
EFFECTIVE_DATE = "October 1, 2025"

# FNS 360.02, "Maximum Monthly Income" table: household_size -> (200%
# gross income limit, 130% gross income limit), in dollars.
GROSS_INCOME_LIMITS = {
    1: (2610, 1696),
    2: (3526, 2292),
    3: (4442, 2888),
    4: (5360, 3483),
    5: (6276, 4079),
    6: (7192, 4675),
    7: (8110, 5271),
    8: (9026, 5867),
}
# FNS 360.02 "Each additional member" row: (200% increment, 130% increment).
ADDITIONAL_MEMBER_INCOME_INCREMENT = (918, 596)

# FNS 360.01 "Standard Deduction" table: household_size -> dollars.
# Sizes 6 and above all use the same "6+" figure from the source table.
STANDARD_DEDUCTIONS = {
    1: 209,
    2: 209,
    3: 209,
    4: 223,
    5: 261,
}
STANDARD_DEDUCTION_6_PLUS = 299


@dataclass
class GrossIncomeScreeningResult:
    """Result of screening one household's gross monthly income against
    the current 200%/130% limits. `under_200_pct`/`under_130_pct` are
    True when income is at or under the limit (see `screen_gross_income`
    for why the limit itself counts as passing, not failing)."""

    household_size: int
    gross_monthly_income: float
    limit_200_pct: int
    limit_130_pct: int
    under_200_pct: bool
    under_130_pct: bool
    source_document: str = SOURCE_DOCUMENT
    effective_date: str = EFFECTIVE_DATE


def _gross_income_limits(household_size):
    if household_size <= 8:
        return GROSS_INCOME_LIMITS[household_size]
    extra_members = household_size - 8
    limit_200, limit_130 = GROSS_INCOME_LIMITS[8]
    inc_200, inc_130 = ADDITIONAL_MEMBER_INCOME_INCREMENT
    return (limit_200 + extra_members * inc_200, limit_130 + extra_members * inc_130)


def screen_gross_income(household_size, gross_monthly_income):
    """Screen `gross_monthly_income` against the current 200%/130% gross
    income limits for `household_size`. GROSS income only — no
    deductions are applied. Does not determine final eligibility; only
    reports where the household falls relative to these two thresholds.

    Boundary handling: income exactly AT a limit counts as under it
    (passes), not over it. FNS policy language (see
    06_change_of_circumstance_reporting.md: "income exceeding the gross
    income limit") frames the limit as a ceiling that must be exceeded
    to fail — being at the ceiling has not exceeded it.

    Raises ValueError if household_size < 1 or gross_monthly_income < 0,
    since those aren't valid inputs to screen rather than cases the
    caller should be silently guessing through.
    """
    if household_size < 1:
        raise ValueError("household_size must be at least 1")
    if gross_monthly_income < 0:
        raise ValueError("gross_monthly_income cannot be negative")

    limit_200, limit_130 = _gross_income_limits(household_size)
    return GrossIncomeScreeningResult(
        household_size=household_size,
        gross_monthly_income=gross_monthly_income,
        limit_200_pct=limit_200,
        limit_130_pct=limit_130,
        under_200_pct=gross_monthly_income <= limit_200,
        under_130_pct=gross_monthly_income <= limit_130,
    )


def get_standard_deduction(household_size):
    """Return the current standard deduction for `household_size`, from
    the same 2025 FNS 360 table. Exposed as its own function since it's
    real structured data already in the knowledge base, even though it
    isn't wired into a net income calculation in this pass."""
    if household_size < 1:
        raise ValueError("household_size must be at least 1")
    return STANDARD_DEDUCTIONS.get(household_size, STANDARD_DEDUCTION_6_PLUS)
