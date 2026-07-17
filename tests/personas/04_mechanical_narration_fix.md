# Persona Test: Mechanical Retrieval-Narration Fix Validation

**Category:** Conversational quality / prompt engineering regression testing
**Priority:** P1 — validates a real bug fix generalizes correctly
**Related:** SPEC.md Section 14, Section 16 Case C; CLAUDE.md Learned Rules

## Background

Original bug: agent's honest "I don't know" responses correctly refused to guess, but were expressed by narrating internal RAG mechanics ("I don't have that in my retrieved evidence," "this turn," "in what I've retrieved") — technically honest, but robotic and exposes system internals instead of reading like a person's honest uncertainty.

Fix: targeted system prompt addition instructing the agent to state substantive uncertainty directly, without referencing retrieval/evidence/turn-based framing, while explicitly preserving citation behavior (source + effective date) for information it DOES have.

## Test Script

Five questions run against BOTH the original and fixed prompts, same session/context each time:

1. **Known gap:** "What are the exact shelter and utility deduction amounts for my situation?"
2. **Known gap:** "Can you tell me the exact resource limit that applies to households with children?"
3. **Known gap:** "What's the process for appealing if my application gets denied?"
4. **Regression check (fully covered question):** "What's the current income limit for a household of 3?"
5. **Additional gap probe:** "Does my household's rental assistance count as income?"

## Expected Behavior

**For gap questions (1, 2, 3, 5):**
- [ ] BEFORE fix: response likely contains "in what I've retrieved," "in my retrieved evidence," "this turn," or similar
- [ ] AFTER fix: response states the substantive gap directly, with NO retrieval-process language
- [ ] AFTER fix: response quality/usefulness is maintained or improved (not just shorter/vaguer)

**For the regression check (4):**
- [ ] BEFORE and AFTER: correct figures cited ($4,442 / $2,888 / $2,221 for household of 3)
- [ ] AFTER fix: source document and effective date still explicitly cited
- [ ] AFTER fix: superseded-document distinction (2021 vs 2025) still correctly noted if relevant
- [ ] Citation discipline must NOT regress — this is the critical check that the fix didn't overcorrect

## Actual Results (Verified July 2026)

**PASS on all 5.**

- **Questions 1, 2, 3, 5 (before):** All contained the mechanical pattern ("I don't have that in my retrieved evidence," "in what I've retrieved," etc.)
- **Questions 1, 2, 3, 5 (after):** All mechanical language eliminated. Responses restated as direct, substantive uncertainty (e.g., "I don't have specific information on hand about whether rental assistance counts as income" instead of "I don't have specific information in my retrieved evidence about..."). In several cases the after-response was more useful, not just cleaner — e.g., Q5's after-response added the real distinction between housing subsidies paid to a landlord vs. cash assistance, which the before-response didn't surface.
- **Question 4 (regression check):** PASS. After-fix response cited $4,442 (200%), $2,888 (130%), $2,221 (100%) for household of 3, effective October 1, 2025, correctly — and was arguably more complete than the before-response, adding clarification about which limit category applies to which household types and correctly reframing the unrelated 165% "separate FNS unit" figure as a distinct rule rather than a competing general limit.

**Unplanned positive side effect:** After-fix responses consistently ended with a conversationally relevant follow-up question tied to what was just discussed, rather than mechanically returning to a previously-queued question regardless of relevance. This wasn't explicitly instructed — appears to be a natural consequence of the model no longer spending output "explaining its process" before responding.

## Why This Test Matters

Demonstrates the discipline of fixing a narrow, precisely-identified bug pattern rather than issuing a vague "sound more natural" instruction — which risks silently degrading unrelated good behaviors (like citation discipline) that happen to share surface-level characteristics with the bug (e.g., citing sources heavily could be mistaken for "sounding like a system" if the fix were too broad).
