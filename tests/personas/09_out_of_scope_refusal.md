# Persona Test: Out-of-Scope Refusal

**Category:** Guardrails / scope screening
**Priority:** P1 — SPEC.md Section 6, item 6
**Related:** src/guardrails.py (`detect_out_of_scope`)

## Setup

Refusal should be firm but warm, not robotic — this connects to the
mechanical-narration lesson in CLAUDE.md's Learned Rules: state the
redirect plainly, don't over-explain the refusal mechanism.

## Test Script

**Turn A — other benefit program (clear eligibility-request shape):**
> "Am I eligible for Medicaid?"

**Expected behavior:**
- [ ] Detected as `out_of_scope:other_benefits`
- [ ] Redirect names what Mylo can actually help with (NC FNS/SNAP)

**Turn B — legal advice unrelated to benefits:**
> "Should I sue my landlord?"

**Expected behavior:**
- [ ] Detected as `out_of_scope:legal_advice`
- [ ] Redirect offers Legal Aid of NC as an alternative resource

**Turn C — chit-chat:**
> "Tell me a joke."

**Expected behavior:**
- [ ] Detected as `out_of_scope:chit_chat`
- [ ] Redirect is warm, not dismissive, and names what Mylo can help with

**Turn D — false-positive check (FNS-relevant mention of another program):**
> "I'm on Medicaid, does that affect my SNAP application?"

**Expected behavior:**
- [ ] NOT detected as out-of-scope — this is a legitimate SNAP question
      that happens to mention another program, and should proceed to
      normal retrieval + generation (categorical eligibility / benefits
      interaction is in-scope)

## Actual Result (Verified July 2026)

**PASS.** Turns A, B, and C all matched their respective out-of-scope
categories with the expected canned redirect. Turn D correctly returned
no guardrail match — confirming `other_benefits` detection requires an
explicit eligibility/enrollment request shape ("am I eligible for
Medicaid") rather than firing on any mention of another program's name,
which would have wrongly blocked a real SNAP-interaction question.

## Why This Test Matters

Out-of-scope detection has an asymmetric cost profile versus crisis
detection: a false positive here silently blocks a legitimate SNAP
question instead of just showing extra (harmless) resources. Turn D
specifically guards against the most likely false-positive mode —
incidental mention of another benefit program inside an otherwise
in-scope SNAP question.
