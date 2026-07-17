"""Entry point / CLI interface. Runs an `input()` loop that drives a
single conversation session with the agent. Run via `python src/cli.py`.
"""

import agent

GREETING = (
    "Mylo: Hi, I'm Mylo. I can help you get a sense of whether you might "
    "qualify for NC FNS (SNAP) food assistance. What would you like help with today?"
)


def run():
    session = agent.Session()
    print(GREETING)
    print("(Type 'exit' or 'quit' to end the conversation.)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nMylo: Take care.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Mylo: Take care.")
            break

        reply = agent.send_message(session, user_input)
        print(f"Mylo: {reply}\n")


if __name__ == "__main__":
    run()
