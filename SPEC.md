# SPEC.md — Mylo: AI Eligibility Agent for Social Services

**Status:** Locked before development begins. This is a snapshot of intent — not a living doc. If scope needs to change mid-build, document the change and why in the README's tradeoffs section instead of editing this file.

## 1. What We're Building

A proof-of-concept text-based AI agent that holds a multi-turn conversation with a resident to help them understand whether they likely qualify for NC FNS (North Carolina's SNAP food-assistance program). The agent grounds its answers in a small curated knowledge base of public eligibility documents, uses deterministic logic for actual eligibility calculations, and handles adversarial/messy input gracefully.

Built for CivicReach's Founding Product Engineer case study.

## 2. Tech Stack (with reasoning)

| Layer | Choice | Why |
|---|---|---|
| Language | Python | Fast to prototype, strong ecosystem for RAG/embeddings, matches likely CivicReach stack |
| LLM | Claude (Anthropic API) | Strong instruction-following, good at admitting uncertainty when prompted, consistent with CivicReach's own stack |
| Embeddings | OpenAI `text-embedding-3-small` or similar | Cheap, fast, sufficient quality for a ~10-20 document corpus |
| Vector store | ChromaDB (local, file-based) | Zero infra setup, appropriate for POC scale, no hosted DB needed |
| Interface | CLI (Python `input()` loop) | Simplest reliable way to demo live in the review meeting; no frontend risk |
| State | In-memory Python object per session | No persistence needed for a single-session POC demo |

## 3. Data Sources

- NC FNS (SNAP) public eligibility documents: income limits, household size rules, application process, categorical eligibility rules
- Sourced from official NC DHHS / USDA FNS public documentation only
- **No live scraping, no real application submission, no contact with real agency systems** (per case study constraints)
- Each document manually reviewed and saved locally before ingestion — no automated crawling

## 4. Project Folder Structure

```
mylo/
├── README.md
├── SPEC.md
├── CLAUDE.md
├── requirements.txt
├── data/
│   └── knowledge_base/        # source eligibility documents (markdown/txt, manually curated)
├── src/
│   ├── ingest.py               # chunking + embedding pipeline
│   ├── retrieval.py            # vector search over knowledge base
│   ├── eligibility.py          # deterministic income/household-size logic
│   ├── guardrails.py           # crisis detection, injection detection, PII handling, refusals
│   ├── agent.py                # conversation loop, state tracking, orchestration
│   └── cli.py                  # entry point / CLI interface
├── tests/
│   └── personas/                # adversarial test scripts + expected behavior checklists
└── docs/
    └── tradeoffs.md             # what was cut and why (also summarized in README)
```

## 5. Core Agent Behavior (Happy Path)

1. Agent greets user, asks what they need help with
2. Agent asks clarifying questions one at a time (household size, income, current benefits status) — only what it doesn't already know
3. Agent retrieves relevant eligibility rules from knowledge base as needed, grounding responses in retrieved content (not parametric memory)
4. Agent runs deterministic eligibility calculation once it has sufficient information
5. Agent delivers an honest assessment — likely eligible / likely not eligible / uncertain, with the reasoning and source cited
6. Agent offers next steps (not a real application — a POC, so this is informational only)

## 6. Guardrails (Priority Order)

1. **Deterministic eligibility logic** — income thresholds and household-size calculations are code, never LLM-estimated
2. **Groundedness** — agent must not state eligibility facts unsupported by retrieved knowledge base content
3. **Crisis detection** — pattern-based detection of distress signals (e.g., statements about not having food, housing instability) → agent breaks from the standard flow, acknowledges, and provides a clear next-step/escalation message
4. **Prompt injection resistance** — system prompt explicitly separates instructions from user input as data; lightweight pattern detection for common injection phrasing ("ignore previous instructions," role-override attempts)
5. **PII handling** — no PII persisted beyond the session; any logged output masks sensitive fields (income figures, personal identifiers) in transcripts
6. **Out-of-scope refusal** — firm but warm redirection for off-topic requests (legal advice, unrelated programs), without being robotic or dismissive

## 7. What's Explicitly Out of Scope (P3 / Cut)

See `docs/tradeoffs.md` for full reasoning. Summary:
- Hybrid retrieval / reranking (dense retrieval only)
- Multi-state / multi-program support (NC FNS only)
- Spanish-language support (English only, documented rationale)
- ML-based injection classifier (pattern-based detection only)
- Automated eval harness / regression suite (manual persona testing only)
- Voice interface (text only, per case study spec)
- Real application submission or agency system contact (explicitly prohibited by case study)
- Rate limiting / abuse protection (not implemented for POC; documented as a production requirement)
- UI-layer injection attacks (e.g., malicious input via a future web frontend) — out of scope since CLI has no attack surface beyond stdin, but relevant the moment a web UI is added
- SMS channel support (documented as a future channel option, not built)
- Comparative model evaluation (e.g., Claude vs. GPT-4o performance benchmarking) — a single model is selected and used; systematic model comparison is a production-stage decision, not a POC one
- Automated document retrieval/versioning from live sources — see Section 11 below for full reasoning

## 8. Development Phases (Priority)

- **P0 (must ship):** Knowledge base + retrieval, conversation loop with state tracking, deterministic eligibility logic, happy-path end-to-end flow
- **P1 (must ship):** Crisis detection, prompt injection resistance, PII handling, out-of-scope refusal
- **P2 (should ship):** Adversarial persona test suite run + documented results
- **P3 (nice to have, cut if short on time):** Polish on conversational tone, additional edge-case personas beyond the core set

## 9. Constraints & Known Limitations

- ~20 hour time budget — scope is deliberately narrow, not feature-complete
- No real agency integration of any kind
- Single session only — no persistence across conversations
- Small knowledge base (~10-20 documents) — retrieval approach is intentionally simple given this scale
- English only
- Not a production system — a proof-of-concept demonstrating architectural judgment, guardrail thinking, failure-mode reasoning, and tradeoff reasoning

## 10. Concurrency & Session Isolation (Design Requirement, Not a Cut)

Even at POC scale, session state must be correctly isolated per conversation. This is a correctness requirement, not a nice-to-have — the review meeting is live and interactive, and cross-session data leakage would be a visible, embarrassing bug if two sessions run concurrently (e.g., two terminal instances, or Chip/Adil trying it alongside a demo session).

- Session state (conversation history, collected user info, eligibility inputs) must be scoped to a per-session object — never stored in global/module-level variables
- Each session gets its own identifier and its own isolated in-memory state container
- No shared mutable state between concurrent sessions at any layer (retrieval calls are stateless/read-only and safe to share; conversation state is not)

## 11. Tradeoff: Manual Document Curation vs. Automated Ingestion

**What we're cutting:** Automated fetching, scraping, or versioning of source eligibility documents from live government websites.

**Why:** The case study explicitly prohibits scraping government systems. More importantly, this mirrors a real architectural principle discussed directly with Chip and Adil in the technical interview: "most up to date" is not a safe heuristic for determining source authority. An agency's own form may lag behind a state's updated guidance, and naive automatic ingestion of "the latest" document risks pulling in information that preempts a customer's actual current process. Manual curation means a human is verifying source authority before a document enters the system — which is the correct control point, not a shortcut being taken due to time constraints.

**What we'd do at scale:** Build a controlled ingestion pipeline with pinned document versioning per customer/agency (not "always fetch latest"), source authority review as a deliberate step before any document is promoted into the active knowledge base, and a way to track and reference prior versions when a form hasn't caught up to updated policy guidance. This is the same architecture proposed during the technical interview — the POC's manual process is a stand-in for that pipeline, not an argument against building it.

## 12. Real-World Discovery: The FNS 360 Version Conflict

While manually sourcing knowledge base documents, we found a live, unplanned example of the exact source-authority problem discussed in the technical interview — not a hypothetical, a real one.

**What we found:** NC DHHS hosts an official policy manual document, "FNS 360 — Determining Benefit Levels," at a stable URL pattern on `policies.ncdhhs.gov`. Two versions exist simultaneously discoverable via search and direct link:

| | Change #15-2021 | Change #01-2025 (current) |
|---|---|---|
| Effective date | October 1, 2021 | October 1, 2025 |
| 200% Gross Income Limit (household of 1) | $2,148 | $2,610 |
| 200% Gross Income Limit (household of 4) | $4,418 | $5,360 |
| Standard deduction (household of 1) | $177 | $209 |
| Max resource limit (elderly/disabled) | $3,750 | $4,500 |

Both documents are hosted on the same official, authoritative domain. Nothing about the URL, domain, or presentation signals that one is stale — only the effective date embedded in the document content itself reveals the conflict.

**How we're handling it:**
- Both versions are included in the knowledge base as separate, fully-tagged documents (`02_fns_360_benefit_levels_2021.md` and `03_fns_360_benefit_levels_2025.md`), each carrying explicit `change_number` and `effective_date` metadata.
- The outdated document is annotated in its own content with a clear note directing to the current version, but is **not deleted or excluded** — deliberately, so the agent's retrieval and reasoning logic can be tested against the exact kind of conflict a production system will encounter constantly.
- The current authoritative eligibility logic (`eligibility.py`) uses only the Change #01-2025 figures.
- One adversarial persona test is built specifically around this conflict: verifying the agent surfaces the *current* effective-dated figures and does not silently blend or average numbers from both versions.

**Why this matters beyond the case study:** This is direct, first-hand evidence that the source-authority architecture discussed with Chip and Adil isn't a theoretical concern — it's a problem that exists today, in production government data, discoverable within an hour of real research. Any production ingestion pipeline for this domain needs pinned versioning and explicit effective-date awareness as a core requirement, not an edge case.

## 13. Estimated Project Cost

Given the ~20 hour scope, actual API/infrastructure costs are minimal:

| Item | Estimated Cost |
|---|---|
| LLM API calls (development, testing, adversarial personas, live demo) | $5-10 |
| Embeddings API (one-time ingestion of ~9 documents, ~60-100 chunks) | <$1 |
| Vector database (ChromaDB, local/file-based) | $0 |
| Hosting/infrastructure (CLI interface, no deployment) | $0 |
| **Total estimated cost** | **$10-20** |

This is comfortably within the $200 provided upfront to cover development and LLM costs. The largest cost driver is iterative testing during the adversarial persona phase (Hour 16-17), where repeated runs against edge cases consume the most tokens.

## 14. P0 Verification Results (Phase 2 Complete)

All core P0 requirements were verified end-to-end with live conversations, not just unit-level checks, before moving into Phase 3 guardrails.

**Grounded, recency-correct conflict resolution:** Queried the agent about income limits that exist in both the 2021 (superseded) and 2025 (current) FNS 360 documents. The agent correctly retrieved both versions, cited the current $5,360/$2,610 figures with the October 2025 effective date, and did not blend or confuse the two. On explicit follow-up asking for the historical figure, it correctly surfaced and clearly labeled the superseded 2021 figure as superseded — the full behavior specified in Section 12.

**Multi-turn state tracking:** Verified via live conversation that facts (household size, income, income type, benefits status) are captured once via a tool-call-based extraction mechanism and never re-asked. Session state (`facts` dict) correctly accumulated across 6+ turns.

**Concurrent session isolation:** Ran two live `Session` instances through simultaneous real conversations (concurrent threads, live Anthropic + ChromaDB calls in flight together). Confirmed zero cross-contamination — distinct session IDs, distinct fact dictionaries, no key bleed in either direction. This closes the concurrency gap flagged as untested in Section 10 prior to Phase 2.

**Concurrency bug found and fixed during this testing:** ChromaDB's `PersistentClient` is not safe to instantiate fresh, per-call, from multiple threads on first access to a given on-disk path — this caused a crash (`Could not connect to tenant default_tenant`) on the first concurrent test run before any client warm-up occurred. Fixed with double-checked locking in `retrieval.py` so the client/collection handle is created once and safely reused. This is a shared, read-only resource handle — not conversation state — and does not violate the Session Isolation design rule; the distinction is documented directly in code comments and CLAUDE.md.

**Groundedness on out-of-scope questions:** Asked the agent a question deliberately targeting a known knowledge base gap (unrelated-elderly-person household composition rules, governed by FNS 210, which is not in this project's knowledge base per Section 7's index). The agent correctly declined to guess, explicitly named what it could and couldn't confirm, cited adjacent information it did have (Simplified SNAP household-concept dependency, separate FNS unit status provision) without overstating its relevance, and redirected to the caseworker rather than fabricating an answer.

**Mechanical narration bug found and fixed:** During the household-composition conversation above, a secondary issue surfaced — the agent's honest uncertainty was correct in substance but expressed by narrating its own retrieval process ("in what I've retrieved," "this turn"), which read as robotic rather than conversational. This is a distinct failure mode from groundedness itself. Fixed via a targeted system prompt addition (see CLAUDE.md Learned Rules for full detail); verified via 5 before/after test questions that the fix eliminated the mechanical pattern while fully preserving citation discipline and the underlying honesty guardrail.

**`max_tokens` bug found and fixed:** Multi-part or nuanced user questions were coming back truncated mid-sentence in live testing. Initially this looked like a display/terminal truncation issue, since the symptom is identical from the outside — text just stops. Inspecting the raw API response (`response.stop_reason`, `response.usage`) revealed the actual cause: the Anthropic call was capped at `MAX_TOKENS = 1024`, and `response.usage.thinking_tokens` showed 530 of those 1024 tokens were being consumed by internal model reasoning before any visible reply text was generated — leaving too little budget for the actual answer. Fixed by raising `MAX_TOKENS` to 4096; re-ran the same reproducing question and confirmed a complete, properly-ending response. This is now a standing rule (see CLAUDE.md Learned Rules): when a response looks cut short, check `stop_reason` and `usage.thinking_tokens` before assuming it's a client-side display issue, since the two failure modes are visually indistinguishable but only one is fixable by adjusting `max_tokens`.

**Net result:** Phase 2 (core agent) is confirmed working correctly across grounding, conflict resolution, state tracking, concurrency, and honest gap acknowledgment — with three real bugs (one concurrency, one prompt-tone, one token-budget) found through deliberate adversarial testing and fixed before moving into Phase 3.

## 15. First Adversarial Test in Detail: The Household Composition Gap

Before building Phase 3's formal guardrails, the first deliberate adversarial test was run against the plain Phase 2 agent — no crisis detection, no injection defense yet, just the core retrieval + conversation loop. The goal: confirm the agent's groundedness holds under real pressure, not just on friendly happy-path questions.

**The test question (chosen deliberately, not randomly):**
> "My household includes my elderly mother who I'm not related to by blood — does she count as part of my household for FNS purposes, and does living with her change my certification period?"

This targets **FNS 210 (Household Composition)** — a section explicitly listed as absent from this knowledge base in Section 7's policy manual index (`07_fns_policy_manual_index.md`). It's a genuine gap, not a contrived one, and a realistic question a real applicant would ask.

**What a failing system would do:** Generate a plausible-sounding, textbook-style answer about blood relation and household composition rules — the classic RAG hallucination failure mode, where the model's parametric knowledge of "how these programs generally work" fills in for what should have been retrieved and wasn't.

**What Mylo actually did:**
- Explicitly named the gap: *"the retrieved evidence references Section 210 by name but doesn't include the actual criteria for who is required vs. optional to include in an FNS unit"*
- Cited real, adjacent information it did have without overstating relevance — the Simplified SNAP household-concept dependency (doc 09) and the separate FNS unit status provision for elderly individuals (doc 03) — while explicitly flagging that neither one resolves the actual question
- Correctly answered the certification-period sub-question using real retrieved figures (12-month vs. 6-month certification per FNS 600) while explicitly caveating that which one applies still depends on the unresolved household-composition question
- Redirected to the caseworker rather than guessing
- Kept the conversation productive — ended by asking for household size to continue building the eligibility picture, rather than dead-ending

**Follow-on discovery from the same test:** Continuing this conversation (providing household size, income, income type) surfaced a second, unrelated issue — the agent's honest uncertainty was being expressed via mechanical retrieval-process narration ("in what I've retrieved," "this turn"). This is documented and fixed separately (see Section 14 and CLAUDE.md Learned Rules) — the underlying groundedness was never wrong, only the tone of expressing it.

**Why this is the right first adversarial test to run:** It tests the single most important failure mode for a RAG system in this domain — confident fabrication when information is missing — before testing anything else. Guardrails like crisis detection and injection resistance (Phase 3) matter, but none of them help if the core retrieval-grounding contract is already broken. Confirming this first meant Phase 3 could be built on a verified-solid foundation rather than an assumed one.

## 16. Additional Adversarial Cases (Pre-Phase 3)

Continuing from the Section 15 test, the same conversation was extended into a longer, more realistic intake — deliberately pushing on ambiguity, incomplete answers, and a second gap area, rather than stopping once the first gap was confirmed handled well.

### Case A: Continued multi-fact intake with a genuine household-composition unknown

The conversation from Section 15 continued with real household size (6), income ($2,500/month), income type (earned), and current benefits status (none) — all correctly captured via the tool-call fact-extraction mechanism and never re-asked.

**Notable behavior:** Once household size was known, the agent proactively surfaced the current maximum allotment and standard deduction for a household of 6 ($1,421 and $299, both 2025 figures, correctly cited) — but explicitly caveated that these figures assume the mother is counted in the 6-person unit, which the agent still couldn't confirm given the Section 15 gap. It carried the unresolved uncertainty forward correctly across multiple turns instead of dropping it once a new fact was collected. This is a harder thing to get right than answering a single isolated question — it requires the system prompt's groundedness instruction to persist across turns, not just apply to the turn where the gap was first identified.

**Notable behavior:** When asked whether the $2,500 was earned or unearned income, the agent correctly applied the 20% earned income deduction rule from FNS 360 (2025) and explicitly noted that the same 20% figure appeared unchanged in the 2021 version — but cited the current document anyway. This shows the recency-preference rule operating correctly even when the two versions happen to agree, not just when they conflict (as in Section 12). Citing the current source by policy, not just when the numbers differ, is the more defensible behavior — the reasoning shouldn't depend on the answer already being known.

### Case B: Ambiguous user input on shelter/utility costs

**Test:** After several turns of straightforward fact-gathering, asked the agent about housing costs, and answered its follow-up question with a bare **"no"** — genuinely ambiguous, since it doesn't specify whether "no" means no rent/mortgage, no separate utility costs, or something else.

**Result:** The agent did not guess which interpretation of "no" was intended. It explicitly asked for clarification, offering the specific possible meanings ("no rent/mortgage payment at all," "rent but utilities included," "something else"), and proactively flagged — before even getting the clarification — that the specific shelter/utility deduction amounts might not be available in its retrieved evidence regardless of the answer, so as not to over-promise a precise figure.

**Why this matters:** This is the "ambiguous answers" failure mode named explicitly in the case study brief ("I make about $2,500/month" as an example). A weaker system either guesses at the most common interpretation of "no" (risking an incorrect eligibility picture) or asks a generic "can you clarify?" without offering concrete options, which is less efficient for the user. Mylo's response was efficient (offered the likely interpretations directly) and honest (flagged the potential downstream data gap in advance rather than after).

### Case C: Recency preference generalization test (5-question before/after set)

To validate the Section 14 mechanical-narration fix, 5 test questions were run against both the original and fixed system prompts — three targeting known knowledge gaps (exact shelter/utility deduction amounts, resource limits for households with children, the appeals process), one regression check (household-of-3 income limit, a fully-covered question), and one additional gap probe (rental assistance as income).

**Result across all 5:** The fix generalized correctly rather than being narrowly tuned to the original bug's exact phrasing. Every "before" response contained retrieval-process language ("in what I've retrieved," "in my retrieved evidence"); every "after" response eliminated it. The regression check confirmed citation discipline was fully intact post-fix — the household-of-3 answer after the fix was, if anything, more complete than before (it added clarifying context about which income limit category applies to which household types, and correctly reframed the 165% "separate FNS unit" figure as a distinct, specialized rule rather than a competing general eligibility limit).

**Unplanned positive side effect:** Post-fix responses consistently ended with a conversationally appropriate follow-up question tied to what was just discussed, rather than mechanically reciting a previously-queued question regardless of relevance (a minor issue visible in some "before" responses, e.g., returning to "circling back to finish gathering your info" immediately after answering an unrelated question). This wasn't explicitly instructed in the fix — it appears to be a natural consequence of the agent no longer needing to "explain its process" before responding, leaving more room for a genuinely responsive follow-up.

Full before/after transcripts available in `tests/personas/` (or reference the system prompt revision working doc if not yet moved into the formal test directory).

### Case D: Silent truncation from token budget, not display

**What happened:** While testing multi-part questions (like the household-composition question in Section 15, which requires a two-part answer covering both household inclusion and certification period), responses occasionally cut off mid-sentence. This looked identical to a terminal/display truncation issue — the text just stopped.

**Diagnosis:** Inspecting the raw API response object rather than just the printed text revealed the real cause: `response.stop_reason` was `max_tokens`, and `response.usage.thinking_tokens` showed 530 tokens out of the original 1024-token cap were consumed by internal model reasoning before any visible reply text was generated — over half the budget gone before the answer even started.

**Fix:** Raised `MAX_TOKENS` from 1024 to 4096. Re-ran the same reproducing question end-to-end and confirmed a complete response that ends properly (a real follow-up question) rather than cutting off mid-sentence.

**Why this is worth documenting as its own case:** The failure mode is genuinely difficult to diagnose from the outside — a client-side display truncation and a server-side `max_tokens` cutoff look identical to a user (or a developer glancing at printed output). The only way to tell them apart is inspecting `stop_reason` and `usage` directly on the response object. This is now a standing rule for any future debugging of "response looks cut short" symptoms (see CLAUDE.md Learned Rules).

## 17. Architectural Fix: Retrieval Query Scoping (Context-Blind Short Answers)

**Discovered while investigating an inconsistency:** the same category of question (household-of-2 income limits) got two different confidence postures across two separate conversations — one confidently cited exact figures, the other said it didn't have the income limits table available. Initial hypothesis was a retrieval-phrasing sensitivity issue; a 5-query diagnostic against varied phrasings of "what are the income limits" all reliably retrieved the correct FNS 360 (2025) chunk, ruling that out.

**Actual root cause, confirmed via direct instrumentation:** `retrieval.retrieve()` was called using only the literal, verbatim current-turn `user_input` as the query — with no conversation history or accumulated facts folded in. This works fine when a turn's literal text carries real semantic content (e.g., "2200" retrieves income-adjacent chunks reasonably). It fails completely when a turn's literal text is short and context-dependent — e.g., a bare "no" answering "are you receiving other benefits?" carries zero semantic signal about income limits, so nothing income-related surfaces in retrieval for that turn, regardless of how relevant income limits are to the actual conversation at that point.

**Confirmed via reproduction:** the exact 4-turn sequence (household size → income → correction → "no") was replayed with retrieval logging enabled. Turn 4's query was literally the string `"no"`. Its top-5 retrieved chunks were Contact info, Public Charge policy, an index of unincluded sections, language-assistance info, and Hearings — nothing about income limits. The model's groundedness instruction then correctly triggered ("I don't have that information"), because the information genuinely wasn't in its context for that call — this was the guardrail working exactly as designed, exposing a gap in the *retrieval* layer, not a flaw in the *generation* layer's honesty.

**Why this matters more than an isolated inconsistency:** any turn where the user's literal reply is short and context-dependent (yes/no answers, corrections, bare numbers) is at risk of retrieving irrelevant chunks and then honestly — but unhelpfully — declining to answer, even when the knowledge base clearly covers the topic and would have been retrieved under different phrasing. This directly affects the case study's Requirement 2 (grounding in retrieved knowledge) and Requirement 4 (tracking conversation state) — state was being tracked correctly in `session.facts`, but that state wasn't being used to inform *retrieval*, only fact extraction.

**Options considered:**
1. **LLM-based query reformulation** before each retrieval call — the "proper" production pattern, but adds a new model call per turn (latency, cost, and a new failure surface if the rewrite itself is poor). Rejected for this scope.
2. **Persist retrieved evidence across turns** rather than re-retrieving fresh every turn — avoids losing earlier-turn context, but risks accumulating stale or irrelevant evidence into the context window over a long conversation.
3. **Concatenate recent conversation turns into the retrieval query** (without adding any new model call) — cheap, deterministic, and directly targets the demonstrated failure.

**Decision: Option 3.** The retrieval query for a given turn is now built from the last 2-3 turns of conversation (e.g., recent facts and exchanges strung together) rather than the literal current-turn text alone. This is a change to the *retrieval-time input* only — it does not add tokens to the *generation-time* context window, does not add a new LLM call, and does not relax the groundedness discipline that correctly refuses to state ungrounded information. It simply gives retrieval enough topical signal to find genuinely relevant chunks even when the current turn's literal text (e.g., "no") doesn't carry that signal on its own.

**Why not the more sophisticated options, given the tradeoff being asked about explicitly:** the concern raised before choosing this fix was that adding more context risks hallucination, while too little context risks exactly this failure. The resolution is that these are two different context budgets that don't have to trade off against each other — the retrieval-query context (cheap, deterministic, doesn't reach the model) can be made richer without touching the generation-time context (the disciplined, citation-driven, groundedness-protected part). Conflating the two would create a real tradeoff; keeping them separate does not.

**What we'd do at scale:** proper query reformulation (Option 1) becomes worth the added latency/cost once conversation complexity grows beyond what simple turn-concatenation can handle well — e.g., very long conversations, or ones with many topic shifts where "last 2-3 turns" stops being a reliable proxy for "what this turn is actually about."

### 17.1 Follow-On Investigation: Dilution from Verbose Turns, and a Confirmed Remaining Gap

After the initial fix above, a related but distinct symptom appeared: the same category of question (household-of-4 income limits) missed retrieval entirely in a conversation where a long, topically-broad assistant reply (an appeals/denial-process explanation) sat between the relevant facts and the current turn. This looked similar to the original bug but had a different mechanism, confirmed via ablation testing rather than assumed.

**Ablation testing across four query-construction variants**, using two real reproducing scenarios (the original short-answer case, and the new verbose-tangent case):

| Variant | Scenario 1 (short answer) | Scenario 2 (verbose tangent) |
|---|---|---|
| (a) Bare current turn only | MISS | HIT (borderline, rank 3-5) |
| (b) Full recent-history concatenation (the Section 17 fix as originally built) | HIT | MISS |
| (c) `session.facts` + current turn only, no raw history | HIT | MISS (counterfactual — facts for the current turn don't exist yet at retrieval time) |
| (d) `session.facts` + last assistant turn + current turn | HIT | MISS (last assistant turn was itself the long, off-topic tangent) |

**No single query-construction formula won both scenarios.** This was a genuine, evidence-backed finding, not a failure to find the right formula — Scenario 1 needs *more* context folded in (a bare short answer has no signal on its own), while Scenario 2 needs *less* dilution from a single long, off-topic turn. These pull in different directions for any fixed concatenation approach.

**Resolution: widen `top_k` from 5 to 8, keep the Section 17 query construction unchanged.** Rather than continuing to search for the perfect query-construction formula, the retrieval window itself was widened. Testing confirmed the previously-missing target chunk in Scenario 2 was not absent from the embedding space — it was present but ranked just outside a 5-wide window (rank 7). At `top_k=8`, it's captured cleanly, with zero irrelevant noise in the surrounding results (every other chunk in the widened window was genuinely adjacent SNAP/FNS content, not off-topic filler). `top_k=10` added nothing beyond `top_k=8` for the cases tested, so 8 was chosen as sufficient rather than over-widening the window unnecessarily. Confirmed separately that all 8 retrieved chunks are forwarded into `<retrieved_evidence>` (no downstream truncation step existed that would have silently capped this at fewer chunks).

**Comprehensive fresh-conversation regression testing** (5 scenarios, all run live, not replayed query strings) confirmed the `top_k=8` fix resolves the original bug, the dilution-risk case, a 4-turn consecutive-short-answer stress test, and a single verbose multi-fact user turn — all four scenarios correctly retrieved and cited exact, source-verified figures with zero hallucination.

**One genuine, confirmed, unresolved gap: topic-shift retrieval dilution.** A follow-up question on a *different* topic than the preceding several turns (e.g., asking about deductions after multiple turns of income-limit discussion) can still fail to retrieve relevant content, because accumulated same-topic history dominates the query's embedding even at `top_k=8`. Tested a cheap mitigation — weighting the current turn's text more heavily by repeating it in the query — which did not close this gap on retest; deduction-related content still failed to surface. **Critically, the agent's groundedness discipline held up correctly under this failure both times it was tested**: rather than fabricating deduction figures, it explicitly stated it didn't have the exact amounts on hand. This is the guardrail working as designed on a retrieval-layer gap, exactly as intended.

**Decision: document as a known limitation rather than pursue further fixes.** This required two separate fix attempts (widening `top_k`, then current-turn weighting) and confirmed reproduction before being accepted as a genuine architectural limitation rather than an unexplored option. Given the ~20 hour scope, a third fix attempt (e.g., topic-aware query segmentation, or detecting topic shifts explicitly) was judged not worth pursuing further — the system fails safely (honest "I don't have that" rather than fabrication) even when this gap is hit, which is the more important property to have preserved.

**What we'd do at scale:** detect topic shifts explicitly (e.g., classify whether the current turn's topic matches the dominant topic of recent history) and either re-weight or reset the retrieval query context when a shift is detected, rather than always concatenating recent turns uniformly regardless of topical continuity.