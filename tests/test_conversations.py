"""Tests for AI title helpers + conversation persistence."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

TEST_DB = Path(__file__).resolve().parent / "_test_conversations.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB}"


@pytest.fixture(autouse=True)
def _fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    from app.config.settings import get_settings
    from app.database import session as session_mod
    import app.services.aria_web_service as aws
    import app.services.title_service as title_svc

    get_settings.cache_clear()
    session_mod.DatabaseManager._instance = None
    session_mod.db_manager = session_mod.DatabaseManager()
    aws.db_manager = session_mod.db_manager
    title_svc.db_manager = session_mod.db_manager

    async def _init():
        await session_mod.init_db()

    asyncio.run(_init())
    yield
    if TEST_DB.exists():
        TEST_DB.unlink(missing_ok=True)


def test_meaningful_and_sanitize():
    from app.services.title_service import (
        has_enough_title_context,
        is_meaningful_user_text,
        sanitize_title,
    )

    assert not is_meaningful_user_text("Hi")
    assert not is_meaningful_user_text("hello")
    assert is_meaningful_user_text("My oven turns on but doesn't heat.")
    assert has_enough_title_context(
        [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "How can I help?"},
        ]
    ) is False
    assert has_enough_title_context(
        [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "My dryer is making a strange noise."},
        ]
    )
    assert sanitize_title('"Oven Not Heating."') == "Oven Not Heating"
    assert sanitize_title("Customer Support Chat") is None


def test_create_and_persist_turn():
    from app.services import aria_web_service as svc

    async def _run():
        session = await svc.create_web_session("text")
        assert session["id"]
        assert session["messages"][0]["role"] == "assistant"
        cid = session["id"]

        from app.database.session import db_manager
        from app.repositories.conversation_repo import ConversationRepository

        async with db_manager.session() as db:
            repo = ConversationRepository(db)
            conv = await repo.get_by_public_id(cid)
            await repo.append_message(conv, role="user", content="My dryer isn't heating.")
            await repo.append_message(
                conv, role="assistant", content="Got it. Is it running otherwise?"
            )

        loaded = await svc.get_conversation(cid)
        assert loaded is not None
        assert loaded["title"] == "New conversation"
        roles = [m["role"] for m in loaded["messages"]]
        assert roles == ["assistant", "user", "assistant"]

        listed = await svc.list_conversations(mode="text")
        assert any(c["id"] == cid for c in listed)

        await svc.archive_conversation(cid)
        assert await svc.get_conversation(cid) is None

    asyncio.run(_run())


def test_voice_session_create():
    from app.services import aria_web_service as svc

    async def _run():
        session = await svc.create_web_session("voice")
        assert session["mode"] == "voice"
        assert session["external_sid"].startswith("voice-")

    asyncio.run(_run())


def test_ai_title_assignment_mocked(monkeypatch):
    from app.services import aria_web_service as svc
    from app.services import title_service as title_svc

    async def fake_gen(excerpt: str):
        assert "dryer" in excerpt.lower()
        return "Dryer Not Heating"

    monkeypatch.setattr(title_svc, "generate_title_from_excerpt", fake_gen)

    async def _run():
        session = await svc.create_web_session("text")
        cid = session["id"]
        from app.database.session import db_manager
        from app.repositories.conversation_repo import ConversationRepository

        async with db_manager.session() as db:
            repo = ConversationRepository(db)
            conv = await repo.get_by_public_id(cid)
            await repo.append_message(conv, role="user", content="My dryer isn't heating at all.")
            await repo.append_message(conv, role="assistant", content="Sorry to hear that.")

        title = await title_svc.maybe_assign_ai_title(cid)
        assert title == "Dryer Not Heating"
        loaded = await svc.get_conversation(cid)
        assert loaded["title"] == "Dryer Not Heating"
        # Second call must not regenerate
        again = await title_svc.maybe_assign_ai_title(cid)
        assert again == "Dryer Not Heating"

    asyncio.run(_run())
