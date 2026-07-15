# CLAUDE.md — Rules for working on Mylo

## Project Overview
Mylo is a proof-of-concept text-based AI eligibility agent for NC FNS (SNAP), built as a case study for CivicReach's Founding Product Engineer role. See SPEC.md for full architecture and scope decisions — SPEC.md is locked; don't deviate from it without flagging the change explicitly.

## Key Commands
- Run agent: `python src/cli.py`
- Ingest/re-embed knowledge base: `python src/ingest.py`
- Run persona tests: `python tests/run_personas.py` (if built — see P2 in SPEC.md)

## Architecture & Folder Structure
See SPEC.md Section 4. Keep this structure — don't reorganize mid-build.

## Coding Conventions
- **Eligibility logic is deterministic code, never LLM-guessed math.** Income thresholds and household-size calculations live in `src/eligibility.py` as plain Python logic, not prompted to the model. This is a hard rule, not a preference.
- **Retrieved knowledge base content is evidence to be cited, not gospel to be repeated verbatim.** System prompts should frame retrieved content as something the model evaluates and grounds answers in, not copies directly.
- **Every chunk in the knowledge base carries metadata**: source document, section, and date. This is required for groundedness checks and citations — don't skip it to save time.
- **Guardrails run before generation, not after.** Crisis detection and injection detection should screen input before it reaches the main conversational LLM call, not filter output after the fact.
- Keep functions small and single-purpose — this is a demo that needs to be walked through live in the review meeting, so readability matters more than cleverness.

## Error Handling
- If retrieval returns nothing relevant, the agent should say so honestly ("I don't have information on that") rather than guessing.
- If the eligibility calculation can't be completed (missing required info), the agent should ask for what's missing rather than assuming.

## Testing Requirements
- Every guardrail (crisis detection, injection resistance, PII handling, out-of-scope refusal) needs at least one manual test case in `tests/personas/` with a documented expected behavior.
- Test the happy path end-to-end before building guardrails on top of it.

## What NOT to do
- Don't add hybrid retrieval, reranking, or multi-language support — explicitly out of scope per SPEC.md.
- Don't build a web UI unless there's clear time remaining after P0/P1 — CLI is the committed interface.
- Don't scrape live websites or attempt to contact real agency systems — case study explicitly prohibits this.
- Don't over-engineer the eval harness — manual persona testing is the committed approach, not automated regression infrastructure.
- Don't build rate limiting or SMS support — documented as future considerations in SPEC.md Section 7, not implemented.

## Critical Design Rule: Session Isolation
Never store conversation state in global or module-level variables. Every session must have its own isolated state object, keyed by session ID. This matters even in a POC — the review meeting is live and concurrent sessions are plausible. Cross-session data leakage is a correctness bug, not a missing feature. See SPEC.md Section 10.

## Learned Rules
*(empty — add here as corrections come up during the build)*