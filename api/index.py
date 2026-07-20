"""Web API for Mylo, deployed as a Vercel Python serverless function.

Serverless invocations are stateless and share no memory between
requests (SPEC.md Section 10), so this layer holds no session state of
its own: each request carries the full session (history + facts) from
the client, `agent.Session.from_dict` rebuilds a fresh, isolated Session
object for that request only, and the updated state is handed back to
the client to resend next turn. This is a stronger form of the same
isolation guarantee the CLI gets from one Session per process — there is
no server-side store at all for sessions to leak across.

All conversational logic (retrieval, guardrails, eligibility, the LLM
call) is unchanged from `agent.py` / `cli.py` — this module only adapts
that existing, already-tested logic to a request/response shape.
"""

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import agent  # noqa: E402
import guardrails  # noqa: E402
from cli import GREETING, MAX_INPUT_CHARS, _check_input_length  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

load_dotenv()

app = FastAPI()

# Frontend is served from the same Vercel deployment (same origin), so
# CORS isn't required for the shipped app. Left permissive only so the
# API is also usable standalone (e.g. local frontend dev on a different
# port) without becoming a separate configuration surface to maintain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Every route that touches the LLM/embeddings APIs (i.e. costs real
# money) sits behind a single shared password, since this is a public
# deployment with no per-user accounts and no rate limiting (SPEC.md
# Section 7 explicitly cuts rate limiting) — the password is the only
# thing standing between this URL and an open token-drain. Set
# MYLO_ACCESS_PASSWORD in the deployment environment (and locally in
# .env to exercise this locally); unset means "reject everything"
# (fail closed), not "allow everything", so a missed env var in
# production can't accidentally leave the app open.
ACCESS_PASSWORD = os.environ.get("MYLO_ACCESS_PASSWORD")


def require_password(x_mylo_password: str = Header(default="", alias="X-Mylo-Password")):
    """FastAPI dependency gating access to paid endpoints. Uses a
    constant-time comparison so response timing doesn't leak how much
    of the password guess was correct."""
    if not ACCESS_PASSWORD or not secrets.compare_digest(x_mylo_password, ACCESS_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid or missing password")


class SessionState(BaseModel):
    session_id: str | None = None
    history: list[dict] = []
    facts: dict = {}


class ChatRequest(BaseModel):
    message: str
    session: SessionState | None = None


class ChatResponse(BaseModel):
    reply: str
    session: SessionState


@app.get("/api/greeting", dependencies=[Depends(require_password)])
def greeting():
    # GREETING bakes in a "Mylo: " prefix for the CLI's plain-text
    # format; the web UI already attributes the message to the agent
    # via bubble styling, so strip it here rather than in cli.py.
    text = GREETING.removeprefix("Mylo: ")
    return {"greeting": text, "max_input_chars": MAX_INPUT_CHARS}


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(require_password)])
def chat(req: ChatRequest):
    session = agent.Session.from_dict(req.session.model_dump() if req.session else None)

    length_error = _check_input_length(req.message)
    if length_error is not None:
        return ChatResponse(reply=length_error, session=SessionState(**session.to_dict()))

    reply = agent.send_message(session, req.message)
    return ChatResponse(reply=reply, session=SessionState(**session.to_dict()))


@app.post("/api/export", dependencies=[Depends(require_password)])
def export(session: SessionState):
    restored = agent.Session.from_dict(session.model_dump())
    return {"transcript": guardrails.export_transcript(restored)}
