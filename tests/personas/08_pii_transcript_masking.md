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

## Regression Test: Citation vs. Restated Personal Data (found and fixed)

**Bug (found in live export):** The original masking was a blanket dollar
regex applied to all rendered text, including agent turns. This masked
every dollar figure indiscriminately — including knowledge-base policy
figures (income limits, deduction amounts) that the agent cited as
sourced evidence, not just the applicant's own stated income. A
transcript where the agent cited the household-of-4 income limits
($5,360 / $3,483 / $2,680, from `03_fns_360_benefit_levels_2025.md`) came
back with those figures redacted too, alongside the applicant's own
income (which correctly should be redacted) — making the transcript
useless for a reviewer trying to see the actual eligibility math.

**Setup:** Session with:
- User turn: "What is the income limit for a household of 4?"
- Agent turn citing $5,360 (gross limit), $3,483 (net limit), $2,680 (max
  allotment), then restating "your stated monthly income of $2500.00"
- User turn confirming: "my income is $2,500 a month"
- Facts: `monthly_income=2500.0`, `income_notes="earned, paid biweekly"`

**Expected behavior:**
- [ ] The three cited policy figures ($5,360, $3,483, $2,680) remain
      visible, unmasked, in the agent's turn
- [ ] The agent's restated "$2500.00" (the applicant's own income, echoed
      back) IS masked in the same agent turn
- [ ] The user's own "$2,500" is masked in the user turn
- [ ] `household_size` and other non-income facts remain visible

**Fix:** Split masking by authorship rather than applying one blanket
regex to all rendered text. User turns and fact values are always
applicant-authored, so dollar amounts there are still blanket-masked
(`mask_pii`). Agent turns mix citations with restated personal data, so
dollar amounts there are only masked when they numerically match a value
pulled from `session.facts` (`_mask_agent_text` /
`_personal_dollar_values`) — SSNs and phone numbers are still masked
unconditionally in agent text, since those formats never appear in
policy citations.

**Actual Result (Verified July 2026):** PASS. Re-ran the exact scenario
above through `guardrails.export_transcript()`: all three cited figures
($5,360, $3,483, $2,680) remained visible; the agent's restated "$2500.00"
and the user's own "$2,500" were both masked to `[REDACTED-AMOUNT]`.
Confirmed separately that with no facts collected yet (`personal_values`
empty), agent-cited dollar figures pass through untouched, and that
SSN/phone patterns in agent text are still masked unconditionally
regardless of the facts state.
