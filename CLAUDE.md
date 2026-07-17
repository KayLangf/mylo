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

- **Chroma metadata truthiness, not key-presence:** When checking the `superseded` field on a retrieved chunk, use `meta.get("superseded")` (truthiness check), never `"superseded" in meta`. Chroma fills omitted metadata keys with `None` for chunks that never had the key written, when other chunks in the same get/query batch do have that key set. A chunk without a `superseded` key will still show up as present-with-value-None on read, which breaks presence checks but not truthiness checks. Verified during Hour 2 ingestion testing (`01_fns_overview.md` chunks, which have no version-conflict blockquote, surfaced as `superseded=None` rather than the key being absent).

- **Retrieval concurrency validated, session-state concurrency now also validated:** Two separate OS processes querying ChromaDB simultaneously (via independent `PersistentClient` instances against the same store) showed zero cross-contamination — confirms the stateless read path is safe to share across concurrent sessions. Session-state concurrency (SPEC.md Section 10) has since been tested directly: two `agent.py` `Session` instances driven through real concurrent `send_message()` calls (two threads, live Anthropic + ChromaDB calls in flight simultaneously) showed zero fact/history leakage between sessions — `Session` isolation is confirmed, not just assumed from the retrieval-layer result. Don't conflate "retrieval layer is concurrency-safe" with "conversation state is concurrency-safe" — they're different claims, but both are now tested.

- **ChromaDB `PersistentClient` concurrent first-init race:** Instantiating `chromadb.PersistentClient(path=...)` against the same on-disk path from two threads at the same time, when no client has been created yet in-process, can crash with `AttributeError: 'RustBindingsAPI' object has no attribute 'bindings'`, surfacing to callers as `ValueError: Could not connect to tenant default_tenant. Are you sure it exists?`. Reproduced via two threads both calling `agent.send_message()` for independent sessions simultaneously with no prior ChromaDB call in-process — one call crashed, the other succeeded. A single warm-up call before spawning concurrent work avoided it, confirming this is specifically a first-init race, not a per-query one.
  - **Fix (in `retrieval.py`):** `_get_collection()` now creates the client/collection handle once behind a `threading.Lock` using double-checked locking, then reuses that handle for every subsequent call. Verified fixed by reproducing the exact crashing scenario (two threads, no warm-up, first ChromaDB access of the process) 3x with no failures, both directly against `retrieval.retrieve()` and end-to-end through `agent.send_message()`.
  - This is a cached *shared read-only resource handle* (client/collection), not per-conversation state — it holds no session history/facts, so it does not violate the Session Isolation design rule, which governs per-conversation mutable data specifically.

- **`max_tokens` must budget for hidden reasoning, not just visible reply length:** `agent.py`'s Anthropic call was capped at `MAX_TOKENS = 1024`, and multi-part/nuanced user questions were coming back truncated mid-sentence — visible in both a raw REPL `repr()` and in live `cli.py` output, which initially looked like a terminal/display truncation issue rather than an API one. It wasn't: `response.stop_reason` was `max_tokens`, and `response.usage.thinking_tokens` was 530 out of the 1024-token cap — over half the budget was consumed by internal reasoning before any visible reply text was generated, leaving too little room for the actual answer. Confirmed by reproducing the exact failing question and inspecting `response.usage` directly.
  - **Fix:** raised `MAX_TOKENS` to 4096 in `agent.py`. Verified fixed by re-running the same reproducing question end-to-end through `send_message()` — full two-part answer, ends on a proper follow-up question instead of cutting off mid-sentence.
  - When a response looks cut short, check `response.stop_reason` and `response.usage` (especially `thinking_tokens`) before assuming it's a client-side/display truncation — the two look identical from the outside (text just stops), but only one is fixable by raising `max_tokens`.

- **Distance metric verification:** Before interpreting ChromaDB distance scores, confirm the collection's actual `hnsw:space` metadata (cosine vs. L2/Euclidean default) rather than assuming from score magnitude alone. Check via `collection.metadata` on the live collection object.
  - **Confirmed for this project:** `ingest.py` creates the collection without an explicit `hnsw:space` override, so ChromaDB defaults to **squared L2 (Euclidean)**, not cosine. Verified both via `collection.configuration_json` (`{'hnsw': {'space': 'l2', ...}}`) and by manually computing both distances for a known pair and confirming the returned value matches squared L2, not cosine.
  - Since `text-embedding-3-small` vectors are unit-normalized, squared L2 and cosine distance are monotonically related (`L2² = 2 · cosine_distance`), so rankings are identical either way — only the raw numeric scale differs (L2 values run ~2x cosine values). Decision: keep L2 default, don't re-ingest to switch to cosine, since it would cost a full re-embed for zero ranking difference. Document this relationship in `retrieval.py` so raw distance values aren't misread later as cosine-scale.