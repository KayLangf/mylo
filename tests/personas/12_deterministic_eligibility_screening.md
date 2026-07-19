# Persona Test: Deterministic Gross-Income Eligibility Screening

**Category:** Deterministic logic / groundedness (Requirement 3: structured logic instead of LLM-guessed math)
**Priority:** P0 — implements CLAUDE.md's hard rule that eligibility math is never LLM-guessed
**Related:** SPEC.md Sections 5, 6; `src/eligibility.py`; `agent.py`'s `<eligibility_screening>` block

## Setup

`src/eligibility.py` provides `screen_gross_income(household_size, gross_monthly_income)`,
a plain-Python screen against the current (2025, non-superseded) 200%/130%
FNS 360 gross income limits, plus `get_standard_deduction(household_size)`.
Neither function is exposed to the LLM as a callable tool — `agent.py`
calls them directly once `household_size` and `monthly_income` are both
present in `session.facts`, and injects the result as a new
`<eligibility_screening>` tagged block the model must cite, not recompute.

## Part 1: Unit Tests (`tests/test_eligibility.py`)

**Expected behavior:**
- [ ] Every household size 1-8's 200%/130% limits match `03_fns_360_benefit_levels_2025.md` exactly
- [ ] The "each additional member" formula is correct for household sizes 9-10
- [ ] Standard deduction lookup matches the same document for sizes 1-8 (6+ collapse to one figure)
- [ ] Boundary handling is verified, not assumed
- [ ] Invalid input (household_size < 1, negative income) raises rather than silently producing a number

**Actual Result:** **PASS.** 36 assertions, all green (`python tests/test_eligibility.py`). Boundary decision: income exactly AT a limit counts as **under** it (passes), not over — based on `06_change_of_circumstance_reporting.md`'s framing ("income *exceeding* the gross income limit"), which treats the limit as a ceiling that must be exceeded to fail. Verified `$1` over and `$1` under both limits (200% and 130%, household size 1) resolve correctly in the opposite direction from the at-limit case.

## Part 2: Live Conversation, End-to-End

**Test Script:** Fresh session — household of 4, gross monthly income $3,000.

**Expected behavior:**
- [ ] Agent calls `update_applicant_facts`, not LLM arithmetic, to record both facts
- [ ] Once both facts are present, the agent's reported limit figures exactly match `eligibility.screen_gross_income(4, 3000)`'s own output — no drift
- [ ] Response is framed as a screening estimate, not a final determination
- [ ] A second live case (household of 2, income $3,000 — over the 130% limit but under 200%) confirms the "over" framing renders correctly, not just the "under" case

**Actual Result:** **PASS.** Household of 4 / $3,000: agent reported 200% limit $5,360 (at or under) and 130% limit $3,483 (at or under) — exact match to `eligibility.py`'s table, correctly cited "effective October 1, 2025," explicitly caveated as gross-income-only and not a final determination. Household of 2 / $3,000: agent correctly reported $3,526 (200%, at or under) and $2,292 (130%, **over**) — confirms the mixed under/over case renders distinctly, not just a blanket "you're fine" regardless of the actual numbers.

**Architectural note:** the fact that completes the screening (e.g., income, arriving after household size) is recorded via the same tool call whose response generates the reply — so the `<eligibility_screening>` block built into that turn's initial prompt is stale (pre-update facts) by construction. Fixed by recomputing the screening from `session.facts` *after* `_apply_tool_calls` merges the new fact, and passing that fresh result back as part of the `tool_result` content for the follow-up model call (see `agent.py`'s `_build_tool_results`). Without this, the turn that completes both facts would report "not enough information yet" even though the reply itself needs to state the screening result.

## Part 3: Regression Check — Persona 01 (Source Authority Conflict)

**Test Script:** Replayed the exact two-turn script from `01_source_authority_conflict.md` against the updated `agent.py`/system prompt.

**Expected behavior:**
- [ ] Turn 1 still cites the current $2,610 (2025) figure, not 2021's $2,148
- [ ] Turn 2 still correctly surfaces and labels the superseded 2021 figure on explicit request

**Actual Result:** **PASS**, unchanged from the original persona 01 result. Turn 1: $2,610, effective October 1, 2025. Turn 2: $2,148, effective October 1, 2021, explicitly labeled as superseded by the current $2,610 figure. Confirms the new `<eligibility_screening>` block and system prompt addition didn't disturb the recency-preference/conflict-resolution behavior.

## Why This Test Matters

This is the case study's explicit Requirement 3 ("use tools/structured logic... instead of hand-waving the rules") and CLAUDE.md's hardest rule (eligibility math is never LLM-guessed). The risk this test guards against isn't just wrong math — it's *drift* between what the deterministic function calculates and what the agent says, which unit tests alone can't catch (they verify the function in isolation, not that the agent actually uses its output verbatim). The live end-to-end checks close that gap.
