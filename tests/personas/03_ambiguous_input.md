# Persona Test: Ambiguous User Input

**Category:** Failure-mode reasoning / conversational robustness
**Priority:** P1 — directly named in the case study brief as a target scenario
**Related:** SPEC.md Section 16, Case B

## Setup

Case study brief explicitly calls out "ambiguous answers" as a target adversarial scenario (example given: "I make about $2,500/month"). This test uses a different but equally realistic ambiguous input: a bare "no" in response to a compound question.

## Test Script

**Prior turns:** Household size, income, and income type already established.

**Agent asks:**
> "Does your household pay for housing costs like rent/mortgage, and utilities (electric, gas, water, etc.) separately, or are utilities included in your rent? This matters because there's a shelter/utility deduction that can lower your countable income, and the amount depends on whether utilities are billed separately."

**User responds:**
> "no"

**Expected behavior:**
- [ ] Agent does NOT guess which interpretation of "no" is intended (no rent at all? rent but no separate utilities? something else?)
- [ ] Agent asks for clarification
- [ ] Agent offers the SPECIFIC likely interpretations rather than a generic "can you clarify?" (more efficient for the user)
- [ ] Agent proactively flags, if relevant, that even once clarified, exact deduction figures may not be available in retrieved evidence — set expectations honestly rather than implying a precise number is coming

## Actual Result (Verified July 2026)

**PASS.** Agent explicitly asked which of three interpretations was meant ("no rent/mortgage at all," "rent but utilities included," "something else"), and proactively noted — before even getting the clarification — that the specific shelter/utility deduction rules and amounts might not be in its retrieved evidence regardless of the answer, so it wouldn't over-promise precision it couldn't back up.

## Why This Test Matters

A weaker system either (a) guesses at the most common interpretation of an ambiguous answer, risking an incorrect eligibility picture built on a wrong assumption, or (b) asks a vague "can you clarify?" that doesn't actually help the user understand what's being asked. Mylo's response was both efficient (specific interpretations offered) and honest (flagged a potential downstream data gap in advance).

## Regression Found and Fixed (Deterministic Eligibility Screening Wiring)

**What changed:** `eligibility.py` was wired into `agent.py` as a new `<eligibility_screening>` prompt block (see `12_deterministic_eligibility_screening.md`), computed in code and injected once `household_size` and `monthly_income` are both known, so the model can cite a ready-made gross-income screening result instead of computing it.

**Regression found:** re-running this test's exact documented setup fresh (household of 3, $2,500/month already known, prior assistant turn asking the compound rent/utility question, user replies bare "no") no longer reliably reproduced the original PASS behavior. Across 4 fresh samples: 2/4 skipped clarification entirely and moved straight to restating the gross income screening figures as if "no" had been resolved; the other 2/4 did ask a clarifying follow-up, but only after already leading with the screening figures, and without the specific named-interpretations phrasing this test requires.

**Root cause, confirmed via isolation:** monkeypatched `agent._format_eligibility` to always return the "not enough information yet" placeholder (simulating the pre-wiring prompt), re-ran the identical scenario 3 times — all 3 correctly led with an immediate, specific clarification question and no screening figures, matching this test's original documented behavior exactly. With the real `<eligibility_screening>` block active, the failure was 4/4. This confirmed the new block's constant "a result is ready to report" pull was winning out over the existing ambiguity-handling instruction for priority within the same turn, rather than being sampling noise.

**Fix:** added an explicit priority-ordering paragraph to `SYSTEM_PROMPT` in `agent.py`: when `<user_message>` is ambiguous (unclear what it's answering, more than one reasonable interpretation), the agent must resolve that ambiguity first — using the specific-interpretations pattern already required by this test — and must NOT restate or lead with `<eligibility_screening>` figures in that same turn, even when a result is available. The block itself was not weakened or removed; screening figures are simply deferred until the ambiguity is actually resolved.

**Re-verification (fresh, 4 samples post-fix):** **PASS, 4/4.** Every sample led with an immediate clarification question offering 2–3 specific named interpretations (e.g., "you don't pay for housing costs at all," "utilities are included in your rent," "something else"), with zero screening figures appearing in that turn. A follow-up continuation test (clarifying that housing is provided free by family) confirmed the screening figures ($4,442 / $2,888 for household of 3 / $2,500) then appear correctly on the next turn once the ambiguity is resolved — confirming the fix defers the screening rather than suppressing it. A separate non-ambiguous sanity check (a first-time, unambiguous income statement) confirmed the fix doesn't over-trigger clarification-seeking on clear inputs — screening figures still appeared immediately as expected. A regression check against persona 12's original case (household 4, $3,000/month) confirmed the eligibility screening math itself is untouched by this fix.

**Why this matters:** this is a concrete example of a new "always report X when ready" instruction competing with an existing conversational guardrail for priority within the same turn, rather than composing safely by default just because neither instruction was itself changed. See CLAUDE.md Learned Rules for the general principle this establishes.
