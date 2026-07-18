# Persona Test: Retrieval Top-K Widening and Topic-Shift Limitation

**Category:** Retrieval / architectural investigation — dilution, window sizing, and a confirmed known limitation
**Priority:** P0 — follow-on to the Section 17 fix, closes out the retrieval-scoping investigation
**Related:** SPEC.md Section 17.1, `10_retrieval_context_scoping.md` (the original fix this builds on), `agent.py` (`_build_retrieval_query`), `retrieval.py` (`DEFAULT_TOP_K`)

## Setup

After `10_retrieval_context_scoping.md`'s fix (retrieval queries built from
recent conversation history instead of the bare current turn), a related but
distinct symptom appeared: a conversation containing a long, topically-broad
assistant tangent (an appeals/denial-process explanation) caused a *different*
retrieval miss than the one that test fixed. This test documents the full
investigation into that symptom, the ablation testing across four
query-construction strategies, the resolution (widening `top_k`), and one
genuine, twice-confirmed limitation that resolution does not close.

## Part 1: Ablation Test — Four Query-Construction Strategies

**Test Script:** Two real reproducing scenarios, each tested against four
different retrieval query strategies:

**Scenario 1 (short answer, facts already known):**
`"2"` → `"2000"` → `"sorry i meant 2200"` → `"no"`

**Scenario 2 (verbose tangent dilution):**
Injection attempt → long appeals/denial-process question → `"I have 4 people
and make 3000 a month"`

**Strategies tested:**
- (a) Bare current turn only
- (b) Full recent-history concatenation (the `10_retrieval_context_scoping.md` fix, unmodified)
- (c) `session.facts` + current turn only, no raw history
- (d) `session.facts` + last assistant turn + current turn

**Expected behavior:**
- [ ] At least one strategy performs acceptably on both scenarios simultaneously

**Actual Result:**

| Strategy | Scenario 1 | Scenario 2 |
|---|---|---|
| (a) Bare current turn | MISS | HIT (borderline, rank 3-5) |
| (b) Full history | HIT | MISS |
| (c) Facts-only + current turn | HIT | MISS (counterfactual — facts for the current turn don't exist yet at retrieval time) |
| (d) Facts + last assistant turn | HIT | MISS (last assistant turn was itself the diluting tangent) |

**FAIL on the original expectation — no single strategy won both scenarios.**
This is treated as a genuine finding, not a failed test: it confirmed the two
failure modes (signal-starved short answers vs. signal-diluted verbose
tangents) pull in opposite directions for any fixed concatenation formula,
which redirected the investigation toward widening the retrieval window
instead of continuing to search for a better formula.

## Part 2: Top-K Widening

**Test Script:** Using strategy (b)'s query construction (unchanged), test
`top_k` at 5 (baseline), 8, and 10 against Scenario 2's confirmed miss.

**Expected behavior:**
- [ ] Target chunk appears within a reasonably widened window
- [ ] Chunks surrounding the target are not irrelevant noise
- [ ] All retrieved chunks (at whatever `top_k` is chosen) are actually
      forwarded into `<retrieved_evidence>`, not silently truncated downstream

**Actual Result:**
- `top_k=5`: MISS (confirmed baseline)
- `top_k=8`: **HIT at rank 7** — the target was never actually absent from
  the embedding space, just one position outside a 5-wide window
- `top_k=10`: unchanged from `top_k=8` (rank 7, no further improvement)
- Noise check: 0 genuinely off-topic chunks in the `top_k=10` results across
  all three tested queries (Scenario 1 fresh, Scenario 2 fresh, Scenario 2's
  captured genuine-miss case) — all filler content was plausibly adjacent
  SNAP/FNS material (other income-limit variants, application processing
  rules), not noise
- Forwarding check: `_format_evidence()` loops over the full chunk list with
  no slicing — confirmed empirically (8 chunks in → 8 `[i] source=...` blocks
  in the assembled evidence text). No separate truncation step existed.

**PASS.** `top_k` widened from 5 to 8 in `retrieval.py`'s `DEFAULT_TOP_K`.

## Part 3: Comprehensive Fresh-Conversation Regression Testing

**Test Script:** Five genuinely fresh, live conversations (new sessions, real
API calls, not replayed query strings) run against the `top_k=8` fix:

1. Original Section 17 scenario (short answer, facts sufficient)
2. Injection + tangent + income statement (verbose dilution risk)
3. Deduction follow-up question after several income-limit-focused turns (new — tests a topic-shift gap identified but not yet empirically confirmed)
4. Four consecutive short answers in a row (new stress test)
5. Single long, rambling, multi-fact user turn (new — tests dilution risk from user-authored text, not just assistant text)

**Expected behavior (Tests 1, 2, 4, 5):**
- [ ] Target income-limit chunks retrieved and cited correctly
- [ ] Cited figures match source-of-truth knowledge base content exactly (verified via direct grep, not from memory)
- [ ] Facts correctly extracted even from verbose/multi-fact input

**Expected behavior (Test 3 — exploratory, outcome genuinely unknown going in):**
- [ ] Determine whether a genuine topic shift (deductions, after several income-limit-focused turns) retrieves correctly or fails

**Actual Result:**

| Test | Result | Notes |
|---|---|---|
| 1 — Original short-answer case | **PASS** | Target hit every turn (ranks 6, 6, 2, 1). Household-of-2 figures ($2,292 / $1,763) cited exactly. |
| 2 — Verbose tangent dilution | **PASS** | Target hit at rank 4/8 on the historically-fragile turn. Household-of-4 figures ($5,360 / $3,483 / $2,680) cited exactly — previously missed entirely at `top_k=5`. |
| 3 — Deduction topic shift | **FAIL** | None of 8 retrieved chunks were Excess Shelter Deduction or Standard Utility Allowance content, despite both sections being confirmed present in the knowledge base via grep. All 8 slots went to income-limit/resource-limit content instead. Agent's reply was honest — listed deduction categories generically, explicitly stated it didn't have exact current dollar amounts on hand, did not fabricate figures. |
| 4 — Consecutive short answers | **PASS** | Target hit every turn (ranks 6, 1, 1, 1) across 4 short-answer turns. Household-of-4 figures cited exactly; final turn correctly identified rent as shelter-deduction-relevant without fabricating a specific amount. |
| 5 — Verbose rambling user turn | **PASS** | Facts extracted correctly (household_size=5, income≈4000, notes, benefits status) from a single deliberately messy, run-on message. Target hit at rank 4/8 on the very first turn. Household-of-5 figures ($6,276 / $4,079 / $3,138) cited exactly. |

## Part 4: Mitigation Attempt for Test 3 (Current-Turn Weighting)

**Test Script:** Modified `_build_retrieval_query` to repeat the current
turn's text at the end of the concatenated query (roughly doubling its
weight relative to older turns), keeping `top_k=8` and all else unchanged.
Re-ran Test 3 plus a full regression of Tests 1, 2, 4, 5.

**Expected behavior:**
- [ ] Test 3's deduction content now retrieves correctly
- [ ] No regression on Tests 1, 2, 4, 5

**Actual Result:**

| Test | Before this mitigation | After this mitigation |
|---|---|---|
| 1 | PASS | PASS (unchanged) |
| 2 | PASS | PASS (unchanged) |
| 3 | FAIL | **FAIL (unchanged)** — deduction content still not retrieved even with current-turn weighting |
| 4 | PASS | PASS (unchanged) |
| 5 | PASS | PASS (unchanged) |

**No regressions, but Test 3 remains unresolved.** Doubling the current
turn's weight was not strong enough to overcome several prior turns' worth
of income-limit-heavy accumulated history in the concatenated query's
embedding.

## Final Decision

**Accepted Test 3 as a documented, confirmed, twice-tested known limitation**
rather than pursuing a third fix attempt. Reasoning:

1. The gap is real and reproducible, confirmed independently in two separate
   investigation rounds (the original attempt to construct this scenario,
   and this formal re-test).
2. Two different fix strategies (top-k widening, current-turn weighting)
   were tried; neither closed it.
3. **Most importantly: the system fails safely.** In every single test of
   this gap, the agent's groundedness guardrail correctly declined to
   fabricate deduction figures it didn't have retrieved, instead stating
   honestly that it lacked exact current amounts. The failure mode is
   "unhelpfully honest," not "confidently wrong."
4. Given the ~20 hour project scope, the correct production fix (explicit
   topic-shift detection, re-weighting or resetting retrieval context when
   a shift is detected) is a larger architectural addition than fits this
   scope — documented under "What I'd Do With More Time" rather than
   attempted under time pressure.

## Why This Test Matters

This is the most complete demonstration of the failure-mode reasoning and
tradeoff reasoning this case study asks for, in a single arc: a hypothesis
tested and falsified (four query-construction strategies, none universally
correct), a resolution chosen based on evidence rather than intuition
(widening the window, because the "miss" was actually a near-miss), thorough
regression testing across fresh conversations, a good-faith attempt at
closing a newly-discovered gap, and — critically — the engineering judgment
to stop after two fix attempts and document a real limitation rather than
either ignoring it or over-investing further time chasing it, especially
once it was confirmed the system's fallback behavior (honest refusal) is
safe rather than harmful.