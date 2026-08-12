"""AI-generated conversation titles (ChatGPT-style).

Uses the shared OpenAI client. Never raises into the chat/voice path —
failures leave the title as "New conversation".
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.database.session import db_manager
from app.repositories.conversation_repo import ConversationRepository
from app.services.openai_client import openai_client_factory

logger = get_logger(__name__)

_DEFAULT_TITLE = "New conversation"

_TITLE_SYSTEM = """\
You generate short titles for customer support conversations.

Based on the conversation below, generate a concise title that describes \
the customer's main issue or purpose.

Rules:
- 2–6 words maximum
- No quotation marks
- No punctuation at the end
- Do not include 'conversation', 'chat', 'support', or 'customer'
- Mention the appliance when relevant
- Focus on the customer's actual problem
- Use natural title capitalization
- Return ONLY the title
"""

_GREETING_ONLY = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hi there",
        "hello there",
        "hey there",
        "yo",
        "sup",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "yes",
        "no",
        "yeah",
        "yep",
    }
)


def is_meaningful_user_text(text: str) -> bool:
    """True when the user message is enough to name a conversation."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    cleaned = cleaned.strip(" .!?,")
    if len(cleaned) < 10:
        return False
    if cleaned in _GREETING_ONLY:
        return False
    # Greeting + short filler still not enough
    for g in ("hi ", "hello ", "hey "):
        if cleaned.startswith(g) and len(cleaned) < 18:
            return False
    return True


def has_enough_title_context(
    messages: Sequence[dict] | Iterable[object],
) -> bool:
    """Need at least one meaningful user utterance."""
    for m in messages:
        if isinstance(m, dict):
            role, content = m.get("role"), m.get("content") or ""
        else:
            role, content = getattr(m, "role", None), getattr(m, "content", "") or ""
        if role == "user" and is_meaningful_user_text(str(content)):
            return True
    return False


def format_title_excerpt(messages: Sequence[dict] | Iterable[object], *, limit: int = 8) -> str:
    lines: List[str] = []
    for m in list(messages)[:limit]:
        if isinstance(m, dict):
            role, content = m.get("role"), (m.get("content") or "").strip()
        else:
            role, content = getattr(m, "role", None), (getattr(m, "content", "") or "").strip()
        if not content:
            continue
        who = "CUSTOMER" if role == "user" else "ARIA"
        lines.append(f"{who}: {content[:400]}")
    return "\n".join(lines)


def sanitize_title(raw: str) -> Optional[str]:
    title = (raw or "").strip().strip('"').strip("'")
    title = title.splitlines()[0].strip() if title else ""
    title = re.sub(r"[.!?]+$", "", title).strip()
    banned = ("conversation", "chat", "support", "customer", "aria")
    lower = title.lower()
    if not title or any(b in lower for b in banned if b == lower or lower.startswith(b + " ")):
        # Allow appliance words; only reject if whole title is banned fluff
        fluff = {
            "home services assistant",
            "conversation with aria",
            "appliance diagnostic session",
            "customer support chat",
            "aria assistance",
            "new conversation",
        }
        if lower in fluff or lower in banned:
            return None
    words = title.split()
    if len(words) > 8:
        title = " ".join(words[:6])
    if len(title) > 80:
        title = title[:77].rstrip() + "…"
    return title or None


async def generate_title_from_excerpt(excerpt: str) -> Optional[str]:
    """Call the configured title model. Returns None on any failure."""
    if not excerpt.strip():
        return None
    settings = get_settings()
    if not settings.openai.api_key:
        return None
    model = settings.openai.title_model or "gpt-4o-mini"
    try:
        response = await openai_client_factory.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _TITLE_SYSTEM},
                {"role": "user", "content": f"Conversation:\n{excerpt}"},
            ],
            temperature=0.3,
            max_tokens=24,
        )
        raw = (response.choices[0].message.content or "").strip()
        return sanitize_title(raw)
    except Exception as exc:  # noqa: BLE001 — never break chat
        logger.warning("Title generation failed: {}", exc)
        return None


async def maybe_assign_ai_title(public_id: str) -> Optional[str]:
    """Generate + persist a title once if still 'New conversation' and context exists.

    Safe to call after every turn — no-ops when a real title already exists.
    """
    async with db_manager.session() as session:
        repo = ConversationRepository(session)
        conv = await repo.get_by_public_id(public_id)
        if conv is None:
            return None
        if (conv.title or "").strip() not in (_DEFAULT_TITLE, ""):
            return conv.title
        messages = list(conv.messages or [])
        if not has_enough_title_context(messages):
            return None
        excerpt = format_title_excerpt(messages)

    title = await generate_title_from_excerpt(excerpt)
    if not title:
        return None

    async with db_manager.session() as session:
        repo = ConversationRepository(session)
        conv = await repo.get_by_public_id(public_id)
        if conv is None:
            return None
        # Race-safe: only write if still default
        if (conv.title or "").strip() not in (_DEFAULT_TITLE, ""):
            return conv.title
        await repo.rename(conv, title)
        logger.info("Assigned AI title {!r} to conversation {}", title, public_id)
        return title
