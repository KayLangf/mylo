# Persona Test: Source Authority Conflict (FNS 360)

**Category:** Groundedness / conflict resolution
**Priority:** P0 — this is the core architectural test case for the project
**Related:** SPEC.md Sections 11, 12, 15

## Setup

Knowledge base intentionally contains two versions of the same document:
- `02_fns_360_benefit_levels_2021.md` (superseded=True, effective_date="October 1, 2021")
- `03_fns_360_benefit_levels_2025.md` (superseded=False, effective_date="October 1, 2025")

## Test Script

**Turn 1:**
> "What is the 200 percent gross income limit for a household of 1?"

**Expected behavior:**
- [ ] Retrieval returns chunks from BOTH documents (verify via direct `retrieve()` call, not just agent response)
- [ ] Agent's response cites the CURRENT figure ($2,610)
- [ ] Agent explicitly states the effective date (October 1, 2025)
- [ ] Agent does NOT blend, average, or confuse the two figures
- [ ] Agent does NOT mention the 2021 figure unprompted

**Turn 2 (follow-up):**
> "What was it before the most recent update?"

**Expected behavior:**
- [ ] Agent correctly retrieves and surfaces the 2021 figure ($2,148)
- [ ] Agent explicitly labels it as superseded / no longer in effect
- [ ] Agent does not present the old figure as currently valid

## Actual Result (Verified July 2026)

**PASS.** Turn 1: agent cited $2,610, effective October 1, 2025, correctly, no blending. Direct `retrieve()` call confirmed both chunks returned with distance scores 0.9184 (2025) and 0.9328 (2021) — a gap of only ~0.014, confirming this is a genuine near-tie a naive system could get wrong. Turn 2: agent correctly surfaced $2,148 and explicitly labeled it as superseded by the current $2,610 figure.

## Why This Test Matters

This isn't a synthetic edge case — it's a real conflict discovered while sourcing documents from NC DHHS's own official domain. See SPEC.md Section 12 for the full discovery writeup.
