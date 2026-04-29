"""Singleton OpenAI client factory.

Centralises construction of the AsyncOpenAI client so credentials and base
configuration live in one place — every service that talks to OpenAI pulls
its client from here rather than instantiating its own.
"""
from __future__ import annotations

from openai import AsyncOpenAI

from app.config.settings import get_settings


class OpenAIClientFactory:
    _instance: "OpenAIClientFactory | None" = None
    _client: AsyncOpenAI | None = None

    def __new__(cls) -> "OpenAIClientFactory":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            settings = get_settings()
            self._client = AsyncOpenAI(api_key=settings.openai.api_key)
        return self._client


openai_client_factory = OpenAIClientFactory()
