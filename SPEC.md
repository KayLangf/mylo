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

## 11. Tradeoff: Manual Document Curation vs. Automated Ingestion

**What we're cutting:** Automated fetching, scraping, or versioning of source eligibility documents from live government websites.

**Why:** The case study explicitly prohibits scraping government systems. More importantly, this mirrors a real architectural principle discussed directly with Chip and Adil in the technical interview: "most up to date" is not a safe heuristic for determining source authority. An agency's own form may lag behind a state's updated guidance, and naive automatic ingestion of "the latest" document risks pulling in information that preempts a customer's actual current process. Manual curation means a human is verifying source authority before a document enters the system — which is the correct control point, not a shortcut being taken due to time constraints.

**What we'd do at scale:** Build a controlled ingestion pipeline with pinned document versioning per customer/agency (not "always fetch latest"), source authority review as a deliberate step before any document is promoted into the active knowledge base, and a way to track and reference prior versions when a form hasn't caught up to updated policy guidance. This is the same architecture proposed during the technical interview — the POC's manual process is a stand-in for that pipeline, not an argument against building it.

## 10. Concurrency & Session Isolation (Design Requirement, Not a Cut)

Even at POC scale, session state must be correctly isolated per conversation. This is a correctness requirement, not a nice-to-have — the review meeting is live and interactive, and cross-session data leakage would be a visible, embarrassing bug if two sessions run concurrently (e.g., two terminal instances, or Chip/Adil trying it alongside a demo session).

- Session state (conversation history, collected user info, eligibility inputs) must be scoped to a per-session object — never stored in global/module-level variables
- Each session gets its own identifier and its own isolated in-memory state container
- No shared mutable state between concurrent sessions at any layer (retrieval calls are stateless/read-only and safe to share; conversation state is not)

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