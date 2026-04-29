"""Service layer.

Note: only lightweight services are re-exported here. Modules that depend on
the agents layer (``RealtimeBridge``, ``VoiceService``) must be imported
directly from their submodules to avoid a circular import via
``app.agents.tools`` -> ``app.services.*`` -> ``app.services.realtime_bridge``
-> ``app.agents.tool_registry``.
"""
from app.services.scheduling_service import SchedulingService
from app.services.vision_service import VisionService
from app.services.email_service import EmailService
from app.services.upload_service import UploadService
from app.services.call_session_store import CallSessionStore, call_session_store
from app.services.openai_client import OpenAIClientFactory, openai_client_factory

__all__ = [
    "SchedulingService",
    "VisionService",
    "EmailService",
    "UploadService",
    "CallSessionStore",
    "call_session_store",
    "OpenAIClientFactory",
    "openai_client_factory",
]
