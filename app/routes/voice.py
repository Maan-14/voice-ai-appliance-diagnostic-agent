"""Twilio voice webhooks + Media Stream WebSocket bridge."""
from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket
from fastapi.responses import Response

from app.config.logging_config import get_logger
from app.dependencies import get_voice_service, register_inbound_call
from app.dto.call import CallContextDTO
from app.services.realtime_bridge import RealtimeBridge
from app.services.voice_service import VoiceService

logger = get_logger(__name__)
router = APIRouter(tags=["voice"])


@router.post("/voice/inbound")
async def inbound_call(
    call_ctx: CallContextDTO = Depends(register_inbound_call),
    voice: VoiceService = Depends(get_voice_service),
) -> Response:
    """Twilio webhook for inbound voice calls. Returns TwiML.

    Configure your Twilio number's "A CALL COMES IN" webhook to POST here.
    """
    twiml = voice.build_inbound_twiml(call_sid=call_ctx.call_sid)
    return Response(content=twiml, media_type="application/xml")


@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket) -> None:
    """Twilio Media Stream WebSocket — bridged to OpenAI Realtime."""
    bridge = RealtimeBridge(websocket)
    await bridge.run()
