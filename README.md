# Mylo — AI Eligibility Agent for Social Services

A proof-of-concept text-based AI agent that helps a resident understand whether they likely qualify for NC FNS (North Carolina's SNAP food-assistance program). Built for CivicReach's Founding Product Engineer case study.

Mylo holds a natural, multi-turn conversation, grounds its answers in a curated knowledge base of real NC DHHS public eligibility documents, uses deterministic logic for actual eligibility math, and is built to fail honestly rather than fabricate confidently when it doesn't know something.

## Access Mylo Directly
https://mylo-eta.vercel.app/

Request password for access 😊.

## Quick Start

```bash
git clone https://github.com/KayLangf/mylo.git
cd mylo
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # then add your API keys
python src/ingest.py   # builds the knowledge base index (run once)
python src/cli.py      # start a conversation
```

Requires an Anthropic API key and an embeddings API key (see `.env.example`).

**Web UI (local):**

```bash
pip install fastapi uvicorn
uvicorn api.index:app --reload   # serves the API; open public/index.html or deploy for the full app
```

**Deploy to Vercel:** `vercel deploy` from the project root (`vercel.json` wires `public/` as the static frontend and `api/index.py` as a Python serverless function). See "Web UI" below for the architecture this required.

## What Makes This Interesting: A Real Source-Authority Conflict

While sourcing knowledge base documents by hand (a deliberate choice — see Tradeoffs below), we found something we weren't looking for: NC DHHS currently hosts **two official versions of the same policy manual document** — "FNS 360: Determining Benefit Levels" — at the same authoritative domain, with materially different numbers:

| | 2021 version (superseded) | 2025 version (current) |
|---|---|---|
| 200% Gross Income Limit, household of 4 | $4,418 | $5,360 |
| Standard deduction, household of 1 | $177 | $209 |

Nothing about the URL or hosting signals which one is stale — only the effective date embedded in the content does. We measured the actual retrieval distance between a test query and both chunks: **0.9184 vs 0.9328**, a gap of only ~0.014. That's close enough that a naive top-1 retrieval system would have a real chance of surfacing the wrong figure.

Both versions are intentionally kept in the knowledge base, fully tagged with `effective_date` and `superseded` metadata. Retrieval doesn't filter either one out — conflict resolution happens in the agent's reasoning: prefer the more recent effective date, cite it explicitly, only reference the superseded figure if the user asks about historical rates. Verified live: asked for the current limit → got the 2025 figure correctly cited; asked "what was it before?" → got the 2021 figure, correctly labeled as superseded.

Full writeup: `SPEC.md`, Sections 12 and 15.

## Architecture

```
User input → Session (per-conversation state)
           → Retrieval (ChromaDB, dense embeddings over 9 NC DHHS documents)
           → Agent (Claude, grounds response in retrieved chunks + known facts)
           → Deterministic eligibility logic (Python, never LLM-estimated)
           → Response
```

- **Language:** Python
- **LLM:** Claude (Anthropic API)
- **Embeddings:** OpenAI `text-embedding-3-small`
- **Vector store:** ChromaDB (local, file-based — no hosted infra needed at this scale)
- **Interface:** CLI (original, committed) + web UI (added post-lock — see "Web UI" below)

See `SPEC.md` Section 2 for full reasoning behind each choice.

## Key Design Decisions

- **Deterministic eligibility math.** Income thresholds and household-size calculations are plain Python code, never something the model estimates. This is a hard rule, not a preference (see `CLAUDE.md`).
- **Fact extraction via tool call**, not regex/parsing free text — `update_applicant_facts` is an actual Claude tool call, closer to how a production system should extract structured state from conversation.
- **Session isolation is architectural, not assumed.** Conversation state is scoped per-session object, never global. This was explicitly tested under real concurrency (two simultaneous live sessions), not just designed and hoped for.
- **Prompt injection resistance via structural tagging.** `<retrieved_evidence>` and `<user_message>` explicitly frame both as data to reason over, not instructions to follow.

## Five Real Bugs Found Through Adversarial Testing

**Concurrency race in ChromaDB client creation.** Testing two simultaneous sessions for the first time surfaced a crash — ChromaDB's `PersistentClient` isn't thread-safe on first instantiation against a shared on-disk path. Fixed with double-checked locking so the client handle is created once and safely reused (a shared *read-only* resource, which doesn't conflict with the session-isolation rule for conversation state).

**Mechanical retrieval-process narration.** The agent's honest "I don't know" responses were substantively correct but exposed internal RAG mechanics ("I don't have that in my retrieved evidence," "this turn") instead of just stating the uncertainty like a person would. Fixed with a targeted system prompt addition; verified via 5 before/after test questions that the fix removed the mechanical pattern while fully preserving citation discipline.

**Silent truncation from token budget, not display.** Multi-part responses were occasionally cutting off mid-sentence — visually identical to a client-side display bug. The actual cause: over half the token budget (`response.usage.thinking_tokens`) was being consumed by internal reasoning before any visible reply was generated, and `max_tokens` was capped too low to leave room for the full answer. Fixed by raising the cap; the two failure modes (display truncation vs. token-budget truncation) are indistinguishable without inspecting the raw response object directly. **This recurred after later system-prompt growth**, this time producing completely empty replies rather than truncated ones — root-caused to a residual architectural gap (no retry path for a first call that exhausted its entire reasoning budget with no tool call and no text), closed with an explicit retry-then-fallback mechanism. Verified live: the underlying risk condition is real (fired in 6/20 conversations on the hardest question shapes), and every retry recovered a complete answer (0/20 empty replies after the fix).

**Retrieval blind to conversation context on short answers.** The same category of question (household income limits) got inconsistent confidence across two conversations — one cited exact figures, one said it didn't have the table. Root cause: retrieval queried using only the literal current-turn text, with no conversation history folded in. A bare "no" (answering "any other benefits?") carries zero semantic signal about income limits, so nothing relevant was retrieved for that turn — the model then correctly (and honestly) said it lacked the information, exposing a retrieval-layer gap rather than a generation-layer inconsistency. Fixed by building the retrieval query from the last 2-3 turns of conversation instead of the bare current turn, without adding any new model call or growing the generation-time context window — a cheap, deterministic fix that keeps retrieval-time and generation-time context budgets separate.

**Follow-on investigation: verbose-turn dilution, resolved by widening retrieval — plus one honestly-documented remaining gap.** A related symptom surfaced after the fix above: a long, off-topic assistant tangent sitting in recent history could dilute retrieval and cause a miss. Ablation-tested four different query-construction strategies across real reproducing scenarios — no single formula won every case, so instead of continuing to chase the perfect query construction, widened the retrieval window (`top_k` 5→8). This resolved every scenario tested across five fresh, live conversations, except one: a genuine topic shift (e.g., asking about deductions after several turns discussing income limits) can still miss retrieval, because accumulated same-topic history outweighs a short, on-topic current turn. Two separate fix attempts didn't close this gap. It's documented as a known limitation rather than force-fixed under time pressure — and importantly, the groundedness guardrail held up correctly under this failure every time it was tested: the agent stated it didn't have the information rather than fabricating an answer.

**Parametric hallucination on qualitative rules, not just missing figures.** A regression pass on Persona 02 (household composition) found the agent stating a specific, accurate-but-ungrounded claim about federal household-concept rules in 4/5 fresh runs — content it knew from training, not from anything retrieved. One run showed the model explicitly self-detecting the problem mid-generation and stating the claim anyway, revealing a real gap: the groundedness instruction covered dollar figures explicitly but not qualitative rules, and had no guidance for self-detected uncertainty beyond hedging. Fixed with a broadened instruction (rules and criteria, not just figures) plus an explicit "self-detected uncertainty means omit the claim, not hedge and include it" rule — carefully scoped with an explicit carve-out for user-stated facts, to avoid the fix overcorrecting into false hesitancy about legitimately-known information. Verified: fabrication rate dropped from 4/5 (80%) to 2/8 (25%) — real, substantial, but not complete. Accepted as a documented, measured improvement rather than pursued further, given the residual risk is true-but-ungrounded content rather than false content.

Full detail: `SPEC.md` Section 14, Section 17 (including 17.1), Sections 18-21, `CLAUDE.md` Learned Rules.

## The First Adversarial Test: Household Composition Gap

Before building formal guardrails (crisis detection, injection defense), the first adversarial test targeted the single most important RAG failure mode: **confident fabrication when information is missing.**

Test question: *"My household includes my elderly mother who I'm not related to by blood — does she count as part of my household for FNS purposes, and does living with her change my certification period?"*

This deliberately targets FNS 210 (Household Composition), a section this knowledge base doesn't include (see the honest gap list in `07_fns_policy_manual_index.md`). Mylo correctly declined to fabricate an answer, named the specific gap, cited real adjacent information without overstating its relevance, and redirected to a caseworker — rather than generating a plausible-sounding but ungrounded answer.

Full transcript and analysis: `SPEC.md` Section 15.

## More Adversarial Testing

Beyond the household-composition test above, additional cases probed different failure modes:

- **Carrying an unresolved gap correctly across turns** — once household size was confirmed, the agent surfaced relevant figures (max allotment, standard deduction) while still explicitly caveating that they depended on an earlier unresolved question, rather than dropping that caveat once new facts came in.
- **Ambiguous user input** ("no" as an answer to a question with multiple possible meanings) — the agent asked for clarification with concrete likely interpretations offered, rather than guessing or asking a generic follow-up.
- **Generalization of the mechanical-narration fix** — 5 before/after test questions (3 new gap probes, 1 regression check, 1 additional gap) confirmed the Section 14 fix eliminated the mechanical pattern broadly, not just for the exact phrasing of the original bug, while fully preserving citation discipline.

Full detail: `SPEC.md` Section 16.

## Tradeoffs — What We Cut and Why

Full reasoning for each in `SPEC.md` Sections 7 and 11. Summary:

| Cut | Why |
|---|---|
| Hybrid retrieval / reranking | Small single-program KB doesn't need it at this scale |
| Multi-state / multi-program support | Mirrors how CivicReach's actual customers are scoped |
| Spanish-language support | Translation risks the same stale-source problem as the FNS 360 conflict; needs a source-native KB, not a translation layer |
| ML-based injection classifier | Pattern-based detection + structural tagging covers the tested attack surface for this scope |
| Automated document ingestion | The manual process is what surfaced the FNS 360 conflict — a human verifying source authority is the correct control point, not a shortcut |
| Automated eval harness | Manual persona testing at this scale; mirrors what CivicReach does in production, just not automated |
| Rate limiting, SMS channel | Documented as real future needs, not built |
| Comparative model benchmarking | Out of scope for a POC — a single model is selected and used |

## Web UI (Post-Lock Deviation)

`SPEC.md` was locked with CLI as the committed interface (Section 2) and a web frontend explicitly named as future work, not committed scope (Section 7). That was deliberately reopened: a web UI was added (`api/index.py`, `public/index.html`, `vercel.json`), deployed as a Vercel Python serverless function, without removing or changing the CLI — both interfaces now share the same `agent.py`/`retrieval.py`/`eligibility.py`/`guardrails.py` logic unmodified.

Two real architecture changes were forced by the deployment target, not stylistic choices:

- **Session state now round-trips through the client instead of living in server memory.** Vercel functions are stateless between invocations, so the original in-memory `Session`-per-process design (`SPEC.md` Section 10) can't hold across requests. `agent.Session` gained `to_dict()`/`from_dict()`; the API rebuilds a fresh `Session` from whatever state the client sends each turn and hands the updated state back for the client to resend next time. There's no server-side session store at all, which makes cross-session leakage structurally impossible rather than tested-and-absent — a stronger version of the same guarantee Section 10 was written around, achieved differently than it originally assumed.
- **ChromaDB's on-disk store is copied to `/tmp` on cold start when deployed**, since Vercel's filesystem is read-only outside `/tmp` and `PersistentClient`/SQLite need write access to open the store even for read-only queries. The store is ~2MB, so this is cheap and only triggers in the deployed environment — local/CLI behavior is unchanged.

**Access is gated by a single shared password** (`MYLO_ACCESS_PASSWORD`), since a public URL with no rate limiting (Section 7 cuts that explicitly) would otherwise let anyone run up the Anthropic/OpenAI bill. Every `/api/*` route requires an `X-Mylo-Password` header, checked server-side with a constant-time comparison; missing the env var entirely fails closed (rejects everything) rather than open. The frontend shows a password gate before loading the chat UI and stores the password in `sessionStorage` only (cleared on tab close) — a demo-appropriate deterrent, not real per-user auth or a defense against a determined/targeted attacker.

**Deployed and live-verified:** `https://mylo-eta.vercel.app`. Beyond the earlier local `uvicorn` testing, the actual Vercel deployment was verified directly against production — password gate (no/wrong password → 401, correct → 200), a real multi-turn conversation exercising retrieval, fact extraction, and eligibility screening (confirms the bundled ~2MB ChromaDB store loads correctly from Vercel's read-only filesystem via the write-probe fallback in `retrieval._resolve_chroma_dir()`), the crisis guardrail, and that a fresh session carries zero state from a prior one. One deployment bug was caught and fixed in the process: the original `/tmp`-copy logic gated on Vercel's `VERCEL=1` env var, which turned out to require a per-project dashboard opt-in most people would never enable — replaced with a real write-probe (attempt a write, catch the failure) that needs no platform-specific detection at all. **The browser gap above was closed, and it found a real bug.** Installed Playwright locally and drove the actual production URL end-to-end: on first load, clicking "Unlock" after entering the correct password visibly did nothing — the `/api/greeting` call was succeeding (200), but the gate stayed on screen. Root cause: `#gate` and `.app` both set an explicit `display: flex` in the stylesheet, which — because author-stylesheet rules always beat user-agent-stylesheet rules at equal specificity — silently overrides the browser's default `[hidden] { display: none }` rule. Toggling the `hidden` property in JS was updating the DOM attribute correctly the whole time; it just had no visual effect. Fixed with one rule (`[hidden] { display: none !important; }`), redeployed, and re-verified with the same Playwright script: password gate now correctly hides after a successful unlock, and a full chat round-trip (greeting bubble → typed message → grounded reply bubble) renders correctly in an actual browser, not just via direct API calls.

Full detail: `CLAUDE.md` Learned Rules.

## What I'd Do With More Time

- Automated ingestion **with** proper source-authority controls (pinned versioning per customer, not naive "always fetch latest")
- Automated eval harness with synthetic personas generated from real usage
- Source-native Spanish-language knowledge base
- Real rate limiting / abuse detection for a deployed endpoint (a minimal 2000-character input-length guard was added — see `SPEC.md` Section 21 — but this is a narrow mitigation, not a substitute for real protection)
- Expand knowledge base coverage — FNS 210 (Household Composition) and FNS 700 (Hearings/Appeals) are both real, confirmed gaps surfaced during testing, not hypothetical ones
- **Explicit topic-shift detection for retrieval.** A confirmed, reproduced limitation: a genuine topic shift mid-conversation (e.g., asking about deductions after several turns discussing income limits) can still miss retrieval, because accumulated same-topic history outweighs a short, on-topic current turn in the concatenated query. Two fix attempts (widening `top_k`, weighting the current turn) didn't close this. The right production fix is detecting topic shifts explicitly and re-weighting or resetting retrieval context when one occurs, rather than always treating recent history uniformly. Importantly, the system fails safely here — groundedness held up correctly every time this was tested, with the agent honestly declining to fabricate figures it didn't have.
- **Closing the residual 25% on Persona 02's groundedness fix.** A parametric hallucination on qualitative household-composition rules was reduced from 80% to 25% occurrence via a broadened, carefully-scoped groundedness instruction, but not eliminated. The remaining failure mode is true-content-but-ungrounded, not false content — a materially lower-severity risk, which is why further iteration was deprioritized given the project's time constraints, but a production system would want this closer to zero.
- **Real large-input token-exhaustion attack prevention.** The 2000-character input-length guard (Section 21) closes the single-large-input case, but a determined attacker could still drive costly `thinking_tokens` consumption through many moderately-sized, adversarially-crafted inputs designed to maximize reasoning load per request, or through rapid repeated requests that each individually pass the length check. A production system would want request-level cost/token budgets, anomaly detection on reasoning-token consumption patterns, and possibly per-session or per-IP rate limiting tuned to token cost rather than just request count — this project's fix addresses the naive version of the attack, not a sophisticated one.
- **Automated regression testing, not manual re-verification.** Every fix in this project was regression-tested by manually re-running the relevant persona scripts fresh — which is how the Persona 03 and Persona 02 regressions (Sections 18.2, 19) and the max_tokens recurrence (Section 20) were all caught, but it doesn't scale and depends on remembering to run the full suite after each change. A `tests/run_personas.py` harness that runs all 12+ persona scripts automatically (referenced as a stretch goal in `CLAUDE.md`'s Key Commands but never built, given the ~20 hour scope) would catch this class of regression automatically rather than relying on manually deciding to re-check after each change — this is the single highest-leverage addition for maintaining correctness as the system grows further.

## Project Structure

```
mylo/
├── README.md
├── SPEC.md              # full architecture, tradeoffs, and verification log
├── CLAUDE.md             # build rules and learned corrections
├── requirements.txt
├── vercel.json           # web deployment config (see "Web UI" section)
├── data/knowledge_base/  # 9 NC DHHS source documents
├── src/
│   ├── ingest.py
│   ├── retrieval.py
│   ├── eligibility.py
│   ├── guardrails.py
│   ├── agent.py
│   └── cli.py
├── api/index.py          # FastAPI web API (Vercel Python serverless function)
├── public/index.html     # static chat frontend (vanilla JS, no build step)
├── tests/personas/
└── docs/tradeoffs.md
```

## Estimated Cost

~$10-20 in actual API usage (LLM calls + embeddings) against the $200 provided upfront. Full breakdown in `SPEC.md` Section 13. Vercel hosting for the web UI is $0 at this scale (Hobby tier covers a single low-traffic Python function + static site).

## Deterministic Eligibility Screening

`src/eligibility.py` implements gross-income screening (200%/130% limits) as plain, deterministic Python — no LLM math, per the hard rule in `CLAUDE.md`. Deliberately scoped to gross income only; net income calculation was intentionally left out since deduction data isn't reliably gathered (see the Section 17.1 retrieval limitation). No final eligibility verdict — reports where a household falls relative to thresholds, matching language the agent already used correctly. 36 unit test assertions, explicit boundary-case testing (at-limit counts as passing), and live end-to-end verification with no drift between calculated and cited figures.

**A real regression was found and fixed during full-suite testing after wiring this in:** the new "ready to report" screening block competed with existing ambiguity-handling instructions, causing the agent to sometimes skip clarification and deliver figures prematurely on an ambiguous "no." Root cause confirmed via monkeypatch isolation (3/3 correct with the block disabled, 4/4 broken with it active) — fixed with explicit system-prompt priority ordering, re-verified 4/4 clean.

**One open item, honestly flagged rather than hidden:** a separate, unrelated regression pass surfaced a possible ungrounded assertion in 2/3 samples of the household-composition test — a claim that's true in the real world but not present in the knowledge base. Not yet root-caused; tracked as an open investigation.

Full detail: `SPEC.md` Section 18.

## Status

Phase 2 (core agent — retrieval, conversation state, groundedness, conflict resolution), Phase 3 (guardrails — crisis detection, injection resistance, PII handling, out-of-scope refusal), and deterministic eligibility screening are complete and verified across 12 formal persona tests. One open, honestly-documented item remains under investigation (see above). A web UI was added post-lock (see "Web UI" section), deployed to `https://mylo-eta.vercel.app`, and verified live end-to-end at the API level; a real-browser click-through is the one remaining unverified layer.
