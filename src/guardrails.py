"""Guardrails that screen input before it reaches the main conversational
LLM call: crisis detection, prompt injection detection, PII handling, and
out-of-scope refusal logic. Runs pre-generation, not as a post-hoc filter.
"""
