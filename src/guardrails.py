"""Guardrails that screen input before it reaches the main conversational
LLM call: crisis detection, prompt injection detection, PII handling, and
out-of-scope refusal logic. Runs pre-generation, not as a post-hoc filter.

Detection here is deliberately pattern-based (per SPEC.md Section 6/7 —
committed approach, not an ML/LLM classifier), but patterns match
multi-word phrases with a first-person/personal-statement shape rather
than single keywords, so a policy question like "does an eviction affect
my SNAP eligibility" doesn't trip the same pattern as "I'm being evicted
tomorrow." Erring toward over-flagging is acceptable for crisis detection
(showing resources unprompted is low-cost); it is not acceptable for
out-of-scope detection (wrongly refusing a real SNAP question is
higher-cost), so those patterns are narrower and require an explicit
request shape, not just a topic mention.
"""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Crisis detection (Hour 12)
# ---------------------------------------------------------------------------

_FOOD_CRISIS_PATTERNS = [
    re.compile(r"\b(i|we)\b.{0,15}\b(haven'?t|have not)\b.{0,15}\beaten\b", re.I),
    re.compile(r"\bno food\b.{0,20}\b(house|home|left|today|tonight)\b", re.I),
    re.compile(r"\b(i'?m|i am|we'?re|we are)\b.{0,15}\b(out of food|starving)\b", re.I),
    re.compile(r"\bnothing (left )?to eat\b", re.I),
    re.compile(
        r"\b(kids?|children|my (son|daughter|child))\b.{0,20}"
        r"\b(haven'?t eaten|are hungry|nothing to eat)\b",
        re.I,
    ),
]

_HOUSING_CRISIS_PATTERNS = [
    re.compile(r"\b(i'?m|i am|we'?re|we are)\b.{0,10}\b(being |about to be )?evict(ed|ion)\b", re.I),
    re.compile(r"\beviction notice\b", re.I),
    re.compile(r"\b(losing|about to lose)\b.{0,10}\b(my|our)\b.{0,10}\b(house|apartment|home)\b", re.I),
    re.compile(r"\b(i'?m|we'?re)\b.{0,10}\b(going to be |about to be )?homeless\b", re.I),
    re.compile(r"\bsleeping in (my|our) car\b", re.I),
    re.compile(r"\b(sheriff|landlord)\b.{0,20}\b(lock(ing)? (me|us) out|evict\w*)\b", re.I),
]

_CHILD_SAFETY_PATTERNS = [
    re.compile(
        r"\b(my )?(child|kid|son|daughter|baby)\b.{0,25}"
        r"\b(unsafe|in danger|being hurt|being abused|not safe|left alone)\b",
        re.I,
    ),
    re.compile(r"\b(hurting|abusing|hitting)\b.{0,10}\b(my )?(child|kid|son|daughter)\b", re.I),
]

_SELF_HARM_PATTERNS = [
    re.compile(r"\bkill(ing)? myself\b", re.I),
    re.compile(r"\bend(ing)? my life\b", re.I),
    re.compile(r"\bwant(ing)? to die\b", re.I),
    re.compile(r"\bsuicid\w*\b", re.I),
    re.compile(r"\bhurt(ing)? myself\b", re.I),
    re.compile(r"\bno reason to live\b", re.I),
]

_DOMESTIC_VIOLENCE_PATTERNS = [
    re.compile(r"\bdomestic violence\b", re.I),
    re.compile(r"\b(he|she|they)'?s? (hitting|hurting|beating|threatening) me\b", re.I),
    re.compile(
        r"\bmy (husband|wife|partner|boyfriend|girlfriend)\b.{0,15}"
        r"\b(hit|hitting|hurt|hurting|abus\w*|threaten\w*)\b",
        re.I,
    ),
    re.compile(r"\bnot safe at home\b", re.I),
    re.compile(r"\bafraid (he|she|they) (will|is going to|are going to) hurt me\b", re.I),
]

_CRISIS_CATEGORIES = [
    ("self_harm", _SELF_HARM_PATTERNS),
    ("domestic_violence", _DOMESTIC_VIOLENCE_PATTERNS),
    ("child_safety", _CHILD_SAFETY_PATTERNS),
    ("food_crisis", _FOOD_CRISIS_PATTERNS),
    ("housing_crisis", _HOUSING_CRISIS_PATTERNS),
]

# Resource text lives here, not in the knowledge base, because crisis
# handling must bypass retrieval entirely (speed + reliability). The
# 2-1-1/Legal Aid numbers deliberately match what's already documented in
# data/knowledge_base/05_snap_noncitizen_eligibility.md; 988 and the
# National DV Hotline are added per Hour 12 spec since neither is in the
# knowledge base. Keep these in sync if the KB doc's numbers ever change.
CRISIS_RESPONSES = {
    "self_harm": (
        "I'm really glad you told me, and I want to make sure you get support "
        "for this right now — this matters more than any paperwork.\n\n"
        "If you're in immediate danger, please call 911.\n"
        "You can also call or text 988 (the Suicide & Crisis Lifeline) any "
        "time, day or night, to talk to someone.\n"
        "NC 2-1-1 (dial 2-1-1) can also connect you to local counseling and "
        "crisis support.\n\n"
        "I'm still here whenever you're ready to talk about SNAP, but there's "
        "no rush on that."
    ),
    "domestic_violence": (
        "I'm sorry you're going through this, and your safety comes first.\n\n"
        "If you're in immediate danger, please call 911.\n"
        "The National Domestic Violence Hotline is available 24/7 at "
        "1-800-799-7233 (or text START to 88788).\n"
        "NC 2-1-1 (dial 2-1-1) can also connect you to local shelter and "
        "safety resources.\n\n"
        "Whenever you're ready, I'm still here to help with SNAP questions too."
    ),
    "child_safety": (
        "Thank you for telling me — a child's safety comes first.\n\n"
        "If a child is in immediate danger, please call 911.\n"
        "You can report concerns to Child Protective Services through your "
        "county Department of Social Services, or call NC 2-1-1 (dial 2-1-1) "
        "and they'll connect you to the right local office.\n\n"
        "I'm still here for SNAP questions whenever you're ready."
    ),
    "food_crisis": (
        "That sounds really hard, and I want to point you toward help that "
        "can act faster than a benefits application.\n\n"
        "NC 2-1-1 (dial 2-1-1 or nc211.org) can connect you to a food pantry "
        "or meal program near you right now, 24/7.\n"
        "Your local county DSS office can also screen you for expedited/"
        "emergency SNAP, which can be approved much faster than a standard "
        "application when there's no food in the house.\n\n"
        "Once things are more stable, I'm glad to keep working through your "
        "SNAP eligibility with you."
    ),
    "housing_crisis": (
        "I'm sorry you're dealing with this — losing housing is serious and "
        "more urgent than a SNAP application.\n\n"
        "NC 2-1-1 (dial 2-1-1 or nc211.org) can connect you to emergency "
        "shelter and rental assistance resources near you.\n"
        "Legal Aid of North Carolina (1-866-219-5262) may be able to help if "
        "you're facing an eviction.\n"
        "Your local county DSS office can also screen you for expedited "
        "SNAP.\n\n"
        "I'm still here to help with your SNAP questions whenever you're "
        "ready."
    ),
}


def detect_crisis(text):
    """Return the matched crisis category name, or None. Checked in a
    fixed priority order (self-harm and domestic violence first) so that
    if a message trips more than one category, the response reflects the
    most safety-critical one."""
    for category, patterns in _CRISIS_CATEGORIES:
        if any(pattern.search(text) for pattern in patterns):
            return category
    return None


# ---------------------------------------------------------------------------
# Prompt injection resistance (Hour 13)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    re.compile(r"\bignore\b.{0,15}\b(previous|prior|above|earlier)\b.{0,15}\binstructions?\b", re.I),
    re.compile(r"\bdisregard\b.{0,15}\b(the )?(above|previous|prior)\b", re.I),
    re.compile(r"\byou are now\b", re.I),
    re.compile(r"\bact as\b.{0,10}\b(if you|a )\b", re.I),
    re.compile(r"\bpretend (you'?re|you are)\b", re.I),
    re.compile(r"\bforget (your|all)\b.{0,10}\binstructions?\b", re.I),
    re.compile(r"\bnew instructions?:", re.I),
    re.compile(r"\breveal (your )?(system )?prompt\b", re.I),
    re.compile(r"\bwhat (is|are) your (system )?(prompt|instructions)\b", re.I),
    re.compile(r"\byou'?re no longer\b", re.I),
]

INJECTION_RESPONSE = (
    "I can't take instructions that show up inside our conversation like "
    "that — I'm just here to help with your NC FNS/SNAP questions. What "
    "would you like to know?"
)


def detect_injection(text):
    """Return True if `text` looks like a prompt injection attempt.
    Supplements, not replaces, the structural <user_message> tagging in
    agent.py's system prompt."""
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# Out-of-scope refusal (Hour 15)
# ---------------------------------------------------------------------------

_LEGAL_ADVICE_PATTERNS = [
    re.compile(r"\bshould i sue\b", re.I),
    re.compile(r"\bfile for divorce\b", re.I),
    re.compile(r"\bcustody (battle|case|arrangement)\b", re.I),
    re.compile(r"\bcriminal charges?\b", re.I),
    re.compile(r"\bwrite (me )?a (will|contract|lease)\b", re.I),
]

_MEDICAL_ADVICE_PATTERNS = [
    re.compile(r"\bwhat medication\b", re.I),
    re.compile(r"\bdiagnose\b", re.I),
    re.compile(r"\bmy symptoms\b", re.I),
    re.compile(r"\bshould i take\b.{0,15}\b(medicine|medication|pills)\b", re.I),
    re.compile(r"\bis this a symptom of\b", re.I),
]

# Narrower than a topic mention: requires an explicit
# eligibility/enrollment request shape around the other program's name,
# so an FNS-relevant mention ("I'm on Medicaid, does that affect my SNAP
# application?") doesn't misfire.
_OTHER_BENEFITS_PATTERNS = [
    re.compile(
        r"\b(am i eligible for|do i qualify for|how do i apply for|can i get)\b"
        r".{0,15}\b(medicaid|tanf|medicare|unemployment( benefits)?|section 8|"
        r"housing choice voucher|social security disability|ssdi|ssi)\b",
        re.I,
    ),
]

_CHITCHAT_PATTERNS = [
    re.compile(r"\btell me a joke\b", re.I),
    re.compile(r"\bwhat'?s the weather\b", re.I),
    re.compile(r"\bwho won the\b", re.I),
    re.compile(r"\bsing me a song\b", re.I),
    re.compile(r"\byour favorite (movie|song|color)\b", re.I),
    re.compile(r"\bhow are you (feeling|doing) today\b", re.I),
]

_OUT_OF_SCOPE_CATEGORIES = [
    ("legal_advice", _LEGAL_ADVICE_PATTERNS),
    ("medical_advice", _MEDICAL_ADVICE_PATTERNS),
    ("other_benefits", _OTHER_BENEFITS_PATTERNS),
    ("chit_chat", _CHITCHAT_PATTERNS),
]

OUT_OF_SCOPE_RESPONSES = {
    "legal_advice": (
        "That's a legal question outside what I can help with — I'm focused "
        "on NC FNS/SNAP eligibility. Legal Aid of North Carolina "
        "(1-866-219-5262) handles questions like that. Is there anything "
        "about SNAP I can help with?"
    ),
    "medical_advice": (
        "That's a medical question, and I'm not able to help with that — "
        "I'm focused on NC FNS/SNAP eligibility. A doctor or NC 2-1-1 (dial "
        "2-1-1) can point you to the right care. Is there a SNAP question I "
        "can help with?"
    ),
    "other_benefits": (
        "That program isn't one I have information on — I'm focused "
        "specifically on NC FNS/SNAP. NC 2-1-1 (dial 2-1-1) can point you to "
        "the right office for that. Is there a SNAP/FNS question I can help "
        "with?"
    ),
    "chit_chat": (
        "I'm just set up to help with NC FNS/SNAP eligibility questions, so "
        "I'll leave the small talk aside. What can I help you figure out "
        "about SNAP?"
    ),
}


def detect_out_of_scope(text):
    """Return the matched out-of-scope category name, or None."""
    for category, patterns in _OUT_OF_SCOPE_CATEGORIES:
        if any(pattern.search(text) for pattern in patterns):
            return category
    return None


# ---------------------------------------------------------------------------
# Screening entry point
# ---------------------------------------------------------------------------


@dataclass
class GuardrailResult:
    category: str
    response: str


def screen(user_input):
    """Run all pre-generation guardrail checks on `user_input` in
    priority order (crisis, then injection, then out-of-scope) and return
    a GuardrailResult to short-circuit the normal LLM turn, or None if
    the message should proceed to retrieval + generation as usual."""
    crisis_category = detect_crisis(user_input)
    if crisis_category:
        return GuardrailResult(f"crisis:{crisis_category}", CRISIS_RESPONSES[crisis_category])

    if detect_injection(user_input):
        return GuardrailResult("injection", INJECTION_RESPONSE)

    scope_category = detect_out_of_scope(user_input)
    if scope_category:
        return GuardrailResult(f"out_of_scope:{scope_category}", OUT_OF_SCOPE_RESPONSES[scope_category])

    return None


# ---------------------------------------------------------------------------
# PII handling (Hour 14)
# ---------------------------------------------------------------------------

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_DOLLAR_PATTERN = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d{2})?|\b\d[\d,]*(?:\.\d{2})?\s*(?:dollars|/\s*month|a month|per month)\b",
    re.I,
)
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d{2})?")

# Fact keys that always hold sensitive values regardless of what they
# look like as text — redacted by key, not by pattern-matching the
# formatted value (a bare "2500.0" float won't match a dollar-sign or
# "dollars"-suffixed regex, so key-based redaction is the only reliable
# way to mask structured facts).
_SENSITIVE_FACT_KEYS = {"monthly_income", "income_notes"}


def _mask_non_dollar_pii(text):
    """Mask SSN-like numbers and phone numbers. These formats never
    appear in cited knowledge-base content, so it's safe to mask them
    unconditionally in any text, regardless of whether that text is a
    citation or restated personal data."""
    text = _SSN_PATTERN.sub("[REDACTED-SSN]", text)
    text = _PHONE_PATTERN.sub("[REDACTED-PHONE]", text)
    return text


def mask_pii(text):
    """Best-effort mask of SSN-like numbers, phone numbers, and dollar
    figures in free-text `text` that is entirely user-authored (a raw
    user turn, or a fact value) — dollar amounts are blanket-masked here
    since user-authored text has no policy-citation content to protect.

    Do NOT use this on agent-authored reply text: an agent turn mixes
    cited knowledge-base policy figures (income limits, deduction
    amounts — public data, not PII) with the agent restating what the
    applicant told it about their own situation (genuine PII). Blanket-
    masking every dollar figure there redacts the citations too, which
    is exactly the bug this function used to have (see CLAUDE.md Learned
    Rules). Use `_mask_agent_text` for agent-authored text instead."""
    text = _mask_non_dollar_pii(text)
    text = _DOLLAR_PATTERN.sub("[REDACTED-AMOUNT]", text)
    return text


def _personal_dollar_values(facts):
    """Collect the numeric dollar figures the applicant has stated about
    their own situation (income, a household member's income mentioned
    in free-text notes, etc.), from `session.facts` — the only source of
    truth for what's actually personal, since facts are populated
    exclusively from what the applicant said, never from retrieved
    knowledge-base content."""
    values = set()
    income = facts.get("monthly_income")
    if isinstance(income, (int, float)):
        values.add(round(float(income), 2))
    notes = facts.get("income_notes")
    if notes:
        for raw in _NUMBER_PATTERN.findall(str(notes)):
            try:
                values.add(round(float(raw.replace(",", "")), 2))
            except ValueError:
                continue
    return values


def _mask_personal_dollar_values(text, personal_values):
    """Redact only the dollar amounts in `text` that match a value the
    applicant is known to have stated about their own situation, leaving
    every other dollar amount (e.g. a cited income limit or deduction
    figure) untouched."""
    if not personal_values:
        return text

    def _replace(match):
        digits = re.sub(r"[^\d.]", "", match.group(0))
        try:
            amount = round(float(digits), 2)
        except ValueError:
            return match.group(0)
        return "[REDACTED-AMOUNT]" if amount in personal_values else match.group(0)

    return _DOLLAR_PATTERN.sub(_replace, text)


def _mask_agent_text(text, personal_values):
    """Mask PII in agent-authored reply text: SSNs/phone numbers
    unconditionally, but dollar amounts only when they match a known
    personal value — see `mask_pii` for why agent text can't be
    blanket-masked the way user text and fact values can."""
    text = _mask_non_dollar_pii(text)
    text = _mask_personal_dollar_values(text, personal_values)
    return text


def _mask_fact(key, value):
    if key in _SENSITIVE_FACT_KEYS:
        return "[REDACTED]"
    return mask_pii(str(value))


def export_transcript(session):
    """Render `session`'s history and collected facts as a masked
    transcript, for logging or the live demo audience. This is the only
    place PII gets scrubbed — the in-memory Session object itself is
    never touched.

    User turns and fact values are entirely applicant-authored, so
    dollar amounts there are blanket-masked. Agent turns mix cited
    knowledge-base figures with restated personal data, so dollar
    amounts there are only masked when they match a value pulled from
    `session.facts` — everything else (policy citations) is left
    visible, since a reviewer needs to see the actual eligibility math
    the agent performed."""
    personal_values = _personal_dollar_values(session.facts)

    lines = [f"# Mylo Transcript — session {session.session_id}", ""]
    for turn in session.history:
        if turn["role"] == "user":
            speaker, content = "Applicant", mask_pii(turn["content"])
        else:
            speaker, content = "Mylo", _mask_agent_text(turn["content"], personal_values)
        lines.append(f"{speaker}: {content}")

    lines.append("")
    lines.append("## Collected Facts")
    if not session.facts:
        lines.append("(none)")
    else:
        for key, value in session.facts.items():
            lines.append(f"- {key}: {_mask_fact(key, value)}")

    return "\n".join(lines)
