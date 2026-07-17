# Persona Test: Concurrent Session Isolation

**Category:** Architecture / correctness (not a conversational persona, but the "hostile timing" equivalent)
**Priority:** P0 — required by SPEC.md Section 10's design rule
**Related:** SPEC.md Section 10, Section 14; CLAUDE.md Learned Rules

## Setup

Two separate `Session` instances, run through genuinely concurrent live conversations (real threads, live Anthropic + ChromaDB calls in flight simultaneously) — not sequential calls that merely look concurrent.

## Test Script

**Session A (Thread 1):** Provide household size 2, income $1,800/month
**Session B (Thread 2), running at the same time:** Provide household size 7, mention current TANF benefits

## Expected Behavior

- [ ] `session_a.facts` and `session_b.facts` remain fully distinct — no shared keys, no bleed
- [ ] Each session retains its own distinct `session_id`
- [ ] Neither session's responses reference or leak information from the other's conversation
- [ ] No crash or exception from underlying shared resources (ChromaDB client, in particular) under concurrent first-access

## Actual Result (Verified July 2026)

**PASS, after one fix.**

Initial run (no client warm-up): crashed with `AttributeError: 'RustBindingsAPI' object has no attribute 'bindings'` → `ValueError: Could not connect to tenant default_tenant`. Root cause: ChromaDB's `PersistentClient` is not thread-safe on first instantiation against a shared on-disk path when `retrieval.py`'s `_get_collection()` creates a fresh client per call (by design, to stay stateless per SPEC.md Section 10).

**Fix:** Double-checked locking in `_get_collection()` — client/collection handle created once behind a `threading.Lock`, reused across calls. This is a shared, read-only resource handle, not conversation state, so it does not violate the Session Isolation design rule (this distinction is documented directly in code comments and in CLAUDE.md, since a shared module-level handle could look like a violation at a glance).

Post-fix: reproduced the original crash scenario 3x directly against `retrieve()` and once end-to-end through `agent.send_message()` — zero failures. Session state fully isolated: `session_a.facts = {household_size: 2, monthly_income: 1800}`, `session_b.facts = {household_size: 7, current_benefits_status: "...TANF..."}` — distinct objects, distinct IDs, no cross-contamination in either direction.

## Why This Test Matters

The review meeting is live and interactive — Chip and Adil may run their own session while a demo session is also active, or run two sessions to test this exact scenario directly. This bug would have been invisible in any sequential/single-session testing and would only have surfaced under real concurrent load — exactly the kind of failure mode that's easy to miss without deliberately testing for it.
