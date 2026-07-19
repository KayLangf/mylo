"""Entry point / CLI interface. Runs an `input()` loop that drives a
single conversation session with the agent. Run via `python src/cli.py`.
"""

import agent
import guardrails

GREETING = (
    "Mylo: Hi, I'm Mylo. I can help you get a sense of whether you might "
    "qualify for NC FNS (SNAP) food assistance. What would you like help with today?"
)

# SPEC.md Section 21: a narrow guard against a single abnormally large
# input independently threatening the token budget (distinct from the
# prompt-growth-driven max_tokens exhaustion in CLAUDE.md Learned Rules).
# Enforced here, at the CLI layer, before input ever reaches the agent.
# Exactly MAX_INPUT_CHARS characters passes (the cap is a maximum, not an
# exclusive bound) — only strictly more is rejected.
MAX_INPUT_CHARS = 2000


def _check_input_length(user_input):
    """Return a rejection message if `user_input` exceeds the character
    cap, or None if it's within bounds. A pure function of the input
    string alone — no shared or module-level state, so there's nothing
    here that could leak between sessions or calls."""
    length = len(user_input)
    if length <= MAX_INPUT_CHARS:
        return None
    return (
        f"Your message is too long ({length}/{MAX_INPUT_CHARS} characters) "
        "— please shorten it and try again."
    )


def run():
    session = agent.Session()
    print(GREETING)
    print("(Type 'exit' or 'quit' to end the conversation, 'export' to save a masked transcript.)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nMylo: Take care.")
            break

        if not user_input:
            continue

        length_error = _check_input_length(user_input)
        if length_error is not None:
            print(f"Mylo: {length_error}\n")
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Mylo: Take care.")
            break
        if user_input.lower() == "export":
            path = f"transcript_{session.session_id}.txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(guardrails.export_transcript(session))
            print(f"Mylo: Saved a masked transcript to {path}\n")
            continue

        try:
            reply = agent.send_message(session, user_input)
        except KeyboardInterrupt:
            print("\nMylo: Take care.")
            break
        print(f"Mylo: {reply}\n")


if __name__ == "__main__":
    run()
