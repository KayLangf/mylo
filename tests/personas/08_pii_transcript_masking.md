# Persona Test: PII Handling in Transcript Export

**Category:** Guardrails / PII masking
**Priority:** P1 — SPEC.md Section 6, item 5
**Related:** src/guardrails.py (`mask_pii`, `export_transcript`)

## Setup

The live in-memory `Session` keeps real values (household size, income,
etc.) because the conversation needs them to function — masking applies
only to persisted/exported output, per CLAUDE.md's Error Handling and PII
sections. `export_transcript()` is reachable from the CLI by typing
`export` mid-session (writes `transcript_<session_id>.txt`).

## Test Script

Built a session with:
- History turn: "My income is $2,500 a month and my SSN is 123-45-6789,
  call me at 919-555-0134"
- Facts: `household_size=4`, `monthly_income=2500.0`,
  `income_notes="earned, biweekly $1250"`, `current_benefits_status="none"`

Called `guardrails.export_transcript(session)` directly.

**Expected behavior:**
- [ ] Dollar figure in free-text history masked to `[REDACTED-AMOUNT]`
- [ ] SSN-like pattern in free-text history masked to `[REDACTED-SSN]`
- [ ] Phone number in free-text history masked to `[REDACTED-PHONE]`
- [ ] `monthly_income` fact fully redacted regardless of its formatted
      value (structured redaction by key, since a bare float like `2500.0`
      won't match a dollar-sign/word regex)
- [ ] `income_notes` fact fully redacted (may contain free-text income
      detail)
- [ ] Non-sensitive facts (`household_size`, `current_benefits_status`)
      pass through unmasked
- [ ] The live `Session` object itself is untouched (masking happens only
      in the exported string, not in `session.history`/`session.facts`)

## Actual Result (Verified July 2026)

**PASS.** Exported transcript showed:
```
Applicant: My income is [REDACTED-AMOUNT] a month and my SSN is [REDACTED-SSN], call me at [REDACTED-PHONE]
Mylo: Got it, thanks.

## Collected Facts
- household_size: 4
- monthly_income: [REDACTED]
- income_notes: [REDACTED]
- current_benefits_status: none
```
All sensitive fields masked as expected; `household_size` and
`current_benefits_status` passed through unmasked since neither is
inherently sensitive. Confirmed separately that `session.facts` and
`session.history` retain their original unmasked values after export —
masking is applied only to the returned string, not the source objects.

## Why This Test Matters

Structured facts (a Python dict with numeric/typed values) don't reliably
match free-text regex patterns — a raw `2500.0` float has no `$` or
"dollars" for a pattern to catch. Masking by known-sensitive key name for
facts, and by pattern for free-text history, is the only combination that
actually covers both persistence paths. This test catches the failure
mode where only the free-text masking was implemented and the facts dict
leaked income figures unmasked in an export.
