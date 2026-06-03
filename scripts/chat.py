"""Interactive text chat against the diagnostic agent.

Same agent, prompt, and tools as the voice path — but in your terminal,
no Twilio needed. Multi-turn conversation history is preserved so the
agent remembers what you said earlier.

Run via:  python -m scripts.chat

Special commands during the chat:
  /context   → dump the collected call context (what tools have stored)
  /reset     → clear conversation history (keeps DB session)
  /quit      → exit
"""
from __future__ import annotations

import asyncio

from agents import Runner

from app.agents.diagnostic_agent import diagnostic_agent_factory
from app.agents.tools import ToolContext
from app.config.logging_config import configure_logging, get_logger
from app.database.session import db_manager, dispose_db
from app.dto.call import CallContextDTO

configure_logging()
logger = get_logger("chat")


BANNER = """
┌─────────────────────────────────────────────────────────────┐
│  Aria — Diagnostic Agent  (text mode)                │
│  Multi-turn chat against the same agent the phone uses.    │
│                                                             │
│  Commands:  /context  /reset  /quit                        │
└─────────────────────────────────────────────────────────────┘
"""


async def main() -> None:
    print(BANNER)
    agent = diagnostic_agent_factory.build_agent()

    async with db_manager.session() as session:
        call_ctx = CallContextDTO(
            call_sid="cli-session",
            from_number="+13125550000",  # pretend caller-ID
        )
        tool_ctx = ToolContext(session=session, call=call_ctx)

        history: list = []

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue

            cmd = user_input.lower()
            if cmd in ("/quit", "/exit", "exit", "quit"):
                break
            if cmd == "/reset":
                history = []
                print("(history cleared — call context preserved)\n")
                continue
            if cmd == "/context":
                print(call_ctx.model_dump_json(indent=2, exclude={"transcript_lines"}))
                print()
                continue

            history.append({"role": "user", "content": user_input})
            try:
                result = await Runner.run(agent, history, context=tool_ctx)
            except Exception as exc:
                logger.exception("Agent run failed")
                print(f"(error: {exc})\n")
                continue

            print(f"Aria: {result.final_output}\n")
            history = result.to_input_list()

        print("\n--- Final call context ---")
        print(call_ctx.model_dump_json(indent=2, exclude={"transcript_lines"}))

    await dispose_db()


if __name__ == "__main__":
    asyncio.run(main())
