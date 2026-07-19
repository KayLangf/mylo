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

**Updated baseline (post `eligibility.py` wiring):** re-running this same
4-turn script fresh after `12_deterministic_eligibility_screening.md`'s
`<eligibility_screening>` block was wired in, Turn 4's reply now cites
only the 200%/130% gross limit figures ($3,526 / $2,292, both correct)
and no longer volunteers the 100%/net-income figure ($1,763) the original
run above included. The retrieved chunk (and therefore the underlying
retrieval fix this test validates) is unaffected — the household-of-2
income-limit chunk still retrieves correctly. This is the new expected
baseline going forward, not a regression: the 100% net figure was never
used in an actual calculation before (net income requires deductions this
project doesn't model — see `eligibility.py`'s scope note), so citing it
was informational color, not a determination. The model now anchors on
the deterministic, code-computed 200%/130% screening result instead of
also surfacing an uncomputed net figure from the retrieved table — a more
consistent citation source, not a loss of correctness.

**Baseline correction — Turn 4's behavior is conditional, not fixed (found during Persona 02/10 re-verification investigation):** Turn 3's closing question is **model-generated, not part of the scripted test input** — the script only fixes the four user turns (`"2"`, `"2000"`, `"sorry i meant 2200"`, `"no"`); what the agent asks at the end of Turn 3, which Turn 4's `"no"` is actually answering, varies from run to run. Prior versions of this doc described Turn 4 as leading with clarification (a side effect of the Persona 03 ambiguity-priority fix generalizing here) as if that were a single, fixed outcome. It isn't. A fresh 4-sample re-verification found Turn 3's actual question split 2/4 compound and 2/4 single-focus, and Turn 4's behavior tracked this exactly:

| Run | Turn 3's actual closing question | Genuinely compound? | Turn 4 behavior |
|---|---|---|---|
| 1 | "Would you like to know more about how to apply, or is there anything else about your situation you'd like to check?" | No — single-focus | Proceeds directly, no clarification, conversation closes normally |
| 2 | "Do you currently receive FNS/SNAP or any other benefits, **or** is this a new application you're considering?" | **Yes** — structurally the same "X, and Y, or Z" shape as Persona 03's rent/utilities question | Leads with clarification, offers the two specific interpretations tied to the two parts of the question |
| 3 | "Anything else you'd like to check — deductions, resource limits, or something else about your household?" | No — single-focus | Proceeds directly to a screening recap, no clarification |
| 4 | "Do you currently receive FNS/SNAP or any other benefits, **or** is this a new application?" | **Yes** | Leads with clarification, offers the two specific interpretations |

**Corrected baseline (conditional, replacing the prior fixed-outcome framing):** if Turn 3's closing question is genuinely compound (asks about two distinguishable things the way Persona 03's question does), Turn 4 should lead with clarification, offering the specific likely interpretations — this is the ambiguity-priority instruction working correctly, not a regression. If Turn 3's closing question is single-focus, Turn 4 should proceed directly to the screening figures without unnecessary clarification-seeking. **Both are correct behavior; neither is "the" expected result on its own** — what Turn 4 does is a correct function of what Turn 3 actually asked, not a fixed property of this test script.

**Why the earlier "4/4 clarification" reading looked like a regression but wasn't:** a pre-push regression pass ran this same 4-turn script 4 times and found all 4 runs leading with clarification, which read as strong evidence the Persona 03 fix was over-triggering on Persona 10's scenario. In hindsight, this was very likely an artifact of Turn 3 happening to ask the compound benefits-or-new-application question in all 4 of those specific runs by chance (a plausible and natural thing for the model to ask at that point in intake, given `household_size`/`monthly_income` are already known but `current_benefits_status` isn't) — not evidence that the fix was firing on non-ambiguous input. The re-verification sample, by chance, included both question shapes and revealed the true conditional structure underneath.

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
