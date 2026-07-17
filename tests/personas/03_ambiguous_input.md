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
