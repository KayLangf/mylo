# Persona Test: Retrieval Query Context Scoping

**Category:** Retrieval / architectural fix — context-blind short answers
**Priority:** P0 — direct fix for a real, reproduced groundedness gap
**Related:** SPEC.md Section 17, `agent.py` (`_build_retrieval_query`)

## Setup

`retrieval.retrieve()` was originally called with only the literal
current-turn `user_input` as the query. This works fine for turns that
carry real semantic content on their own, but fails for short,
context-dependent replies (a bare "no," a bare number, a correction) that
carry no topical signal in isolation — even when the surrounding
conversation makes the topic obvious. See SPEC.md Section 17 for the
full root-cause writeup (retrieval-layer gap, not a generation-layer
honesty/consistency bug).

**Fix:** the retrieval query is now built from the last 3 conversational
exchanges (`session.history`, both user and assistant turns) plus known
`session.facts`, concatenated with the current turn — see
`agent._build_retrieval_query`. This is retrieval-input-only: no new LLM
call was added, and nothing changed about what's sent to the
generation-time API call beyond the (now more relevant) retrieved chunks.

## Test Script

Exact 4-turn sequence from the original failing conversation:

**Turn 1:** `"2"` (household size)
**Turn 2:** `"2000"` (income)
**Turn 3:** `"sorry i meant 2200"` (correction)
**Turn 4:** `"no"` (other benefits)

**Expected behavior (Turn 4):**
- [ ] Retrieval query for Turn 4 includes recent history/facts, not just the literal string `"no"` (verify via direct call to `agent._build_retrieval_query`)
- [ ] `03_fns_360_benefit_levels_2025.md`'s income-limit chunk (household size 2 row) is retrieved for Turn 4
- [ ] Agent's Turn 4 reply cites specific, correctly-sourced income-limit figures for household size 2, rather than saying it doesn't have the table
- [ ] Cited figures match the actual 2025 table exactly (no hallucination): 130% gross limit $2,292, 200% gross limit $3,526, 100% net limit $1,763, effective October 1, 2025
- [ ] Generation-time behavior is otherwise unaffected — facts still captured correctly via tool call, one clarifying question per turn, no new/different system prompt behavior

## Actual Result

### Before the fix

Reproduced the exact 4-turn sequence with retrieval logged. Turn 4's
retrieval query was the literal string `"no"`. Its top-5 chunks were:
Contact info, Public Charge policy, an index of sections not in the
knowledge base, language-assistance info, and Hearings (700 Series) —
nothing about income limits. Turn 4's reply:

> "Thanks for confirming — no current benefits. ... I don't calculate
> eligibility directly at this stage, but this information will help
> determine whether your household falls within the income guidelines
> for SNAP. If you have any policy questions in the meantime..."

No income-limit figures cited — consistent with the retrieved evidence
genuinely not containing any, confirming this was a retrieval miss, not
the model declining to cite information it had.

### After the fix

Same 4-turn sequence, same literal Turn 4 input (`"no"`). Verified
`_build_retrieval_query(session, "no")` at Turn 4 now returns a string
folding in Turns 1–3 (household size, income, the correction) plus
`household_size: 2; monthly_income: 2200` from `session.facts`, followed
by `"no"`. A direct `retrieve()` call against that query returned the
2025 FNS 360 household-of-2 income-limit chunk at rank 3 of 4 (distance
0.9356), where it had not appeared at all under the old bare-`"no"`
query.

**PASS.** End-to-end Turn 4 reply:

> "Got it, thanks for confirming — no one in your household is currently
> receiving FNS/SNAP or other public assistance.
>
> Here's where things stand based on what you've shared:
> - Household size: 2
> - Gross monthly income: $2,200
>
> For a household of 2, the current gross income limits (effective
> October 1, 2025) are $2,292/month at 130% of poverty and $1,763/month
> at 100% (net income limit). Your income of $2,200 is under the 130%
> gross limit, which is a positive sign, but slightly above the $1,763
> net limit — though net income accounts for deductions (like shelter,
> medical, or dependent care costs) that could bring it down further.
>
> I can't run the full eligibility calculation at this stage, but this
> gives a general sense of where you stand..."

Cross-checked all three cited figures ($2,292, $1,763, and Turn 2's
$3,526) directly against `03_fns_360_benefit_levels_2025.md`'s household-
of-2 row (200%: $3,526, 130%: $2,292, 100% net: $1,763) — exact match, no
hallucination, correct effective date cited. Facts were still captured
correctly across all 4 turns (`household_size=2`, `monthly_income=2200`,
`current_benefits_status` recorded), and the agent still asked exactly
one clarifying question per turn — confirming the fix only changed
retrieval relevance, not generation-time behavior.

## Why This Test Matters

This is the direct regression test for the root cause documented in
SPEC.md Section 17: any turn where the user's literal reply is short and
context-dependent (yes/no answers, corrections, bare numbers) was at
risk of silently retrieving irrelevant chunks and then honestly — but
unhelpfully — declining to answer, even when the knowledge base clearly
covered the topic. This test confirms the fix closes that gap for the
exact reproducing scenario without reintroducing the risks the other
rejected options carried (a new LLM call for query reformulation, or
growing the generation-time context window).
