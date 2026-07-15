"""Conversation loop, per-session state tracking, and orchestration
across retrieval, eligibility, and guardrails. Each session owns its own
isolated state object, keyed by session ID — no global or module-level
mutable session state.
"""
