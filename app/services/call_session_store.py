"""Thread-safe in-memory store for active call contexts.

Keyed by Twilio CallSid. Holds the ``CallContextDTO`` so agent tools and
the websocket bridge share a single mutable view of what we've collected
during the call. Persisted to DB at call end via the call repository.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Optional

from app.dto.call import CallContextDTO


class CallSessionStore:
    _instance: "CallSessionStore | None" = None

    def __new__(cls) -> "CallSessionStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions = {}  # type: ignore[attr-defined]
            cls._instance._lock = asyncio.Lock()  # type: ignore[attr-defined]
        return cls._instance

    def __init__(self) -> None:
        self._sessions: Dict[str, CallContextDTO]
        self._lock: asyncio.Lock

    async def create(self, ctx: CallContextDTO) -> CallContextDTO:
        async with self._lock:
            self._sessions[ctx.call_sid] = ctx
            return ctx

    async def get(self, call_sid: str) -> Optional[CallContextDTO]:
        async with self._lock:
            return self._sessions.get(call_sid)

    async def get_or_create(
        self, call_sid: str, from_number: Optional[str] = None
    ) -> CallContextDTO:
        async with self._lock:
            ctx = self._sessions.get(call_sid)
            if ctx is None:
                ctx = CallContextDTO(call_sid=call_sid, from_number=from_number)
                self._sessions[call_sid] = ctx
            return ctx

    async def remove(self, call_sid: str) -> Optional[CallContextDTO]:
        async with self._lock:
            return self._sessions.pop(call_sid, None)

    async def all(self) -> Dict[str, CallContextDTO]:
        async with self._lock:
            return dict(self._sessions)


call_session_store = CallSessionStore()
