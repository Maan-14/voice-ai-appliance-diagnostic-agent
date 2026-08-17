"""HTTP API for the ARIA product web UI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.services import aria_web_service as svc
from app.services.browser_realtime_bridge import BrowserRealtimeBridge

router = APIRouter(prefix="/api/aria", tags=["aria-web"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    call_context: Dict[str, Any]
    history: List[Any] = Field(default_factory=list)
    conversation_id: Optional[str] = None


class PersistRequest(BaseModel):
    call_context: Dict[str, Any]
    conversation_id: Optional[str] = None
    duration_seconds: Optional[int] = None


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.post("/session")
async def create_session(mode: str = Query(default="text")) -> Dict[str, Any]:
    if mode not in ("text", "voice"):
        mode = "text"
    return await svc.create_web_session(mode)


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    async def events():
        async for chunk in svc.stream_agent_turn(
            user_message=body.message.strip(),
            call_ctx_data=body.call_context,
            history=body.history,
            conversation_id=body.conversation_id,
        ):
            yield chunk

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def chat_turn(body: ChatRequest) -> Dict[str, Any]:
    return await svc.run_agent_turn_sync(
        user_message=body.message.strip(),
        call_ctx_data=body.call_context,
        history=body.history,
        conversation_id=body.conversation_id,
    )


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> Dict[str, str]:
    data = await file.read()
    text = await svc.transcribe_audio(data, filename=file.filename or "utterance.webm")
    return {"text": text}


@router.post("/speak")
async def speak(body: SpeakRequest) -> Response:
    audio = await svc.synthesize_speech(body.text.strip())
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/session/persist")
async def persist(body: PersistRequest) -> Dict[str, Any]:
    return await svc.persist_session(
        body.call_context,
        conversation_id=body.conversation_id,
        duration_seconds=body.duration_seconds,
    )


@router.get("/conversations")
async def list_conversations(
    mode: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    return await svc.list_conversations(mode=mode, query=q, limit=limit)


@router.get("/conversations/{public_id}")
async def get_conversation(public_id: str) -> Dict[str, Any]:
    data = await svc.get_conversation(public_id)
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return data


@router.patch("/conversations/{public_id}")
async def rename_conversation(public_id: str, body: RenameRequest) -> Dict[str, Any]:
    data = await svc.rename_conversation(public_id, body.title)
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return data


@router.delete("/conversations/{public_id}")
async def archive_conversation(public_id: str) -> Dict[str, str]:
    ok = await svc.archive_conversation(public_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "archived"}


@router.get("/appointments")
async def list_appointments(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    try:
        return await svc.list_appointments(status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/appointments/{appointment_id}")
async def get_appointment(appointment_id: int) -> Dict[str, Any]:
    data = await svc.get_appointment(appointment_id)
    if not data:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return data


@router.get("/ops")
async def ops() -> Dict[str, Any]:
    return await svc.ops_summary()


@router.get("/status")
async def status() -> Dict[str, Any]:
    settings = get_settings()
    return {
        "openai": bool(settings.openai.api_key and settings.openai.api_key.startswith("sk-")),
        "twilio": bool(
            settings.twilio.account_sid
            and settings.twilio.auth_token
            and settings.twilio.phone_number
        ),
        "app": settings.app.name,
        "env": settings.app.env,
    }


@router.websocket("/ws/realtime")
async def browser_realtime(ws: WebSocket) -> None:
    """Browser Talk-to-ARIA: speech ↔ OpenAI Realtime ↔ speech (PCM16)."""
    bridge = BrowserRealtimeBridge(ws)
    await bridge.run()
