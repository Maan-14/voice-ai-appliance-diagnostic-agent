"""Twilio voice service — generates TwiML for inbound calls.

Returns a `<Connect><Stream>` TwiML response that points Twilio Media
Streams at our /ws/voice WebSocket, which is the bridge to OpenAI Realtime.
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config.logging_config import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)


class VoiceService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _media_stream_ws_url(self) -> str:
        public = self._settings.app.public_url.rstrip("/")
        parsed = urlparse(public)
        scheme = "wss" if parsed.scheme in ("https", "wss") else "ws"
        return urlunparse((scheme, parsed.netloc, "/ws/voice", "", "", ""))

    def build_inbound_twiml(self, call_sid: str | None = None) -> str:
        """Build TwiML that bridges the call to our Realtime WebSocket."""
        response = VoiceResponse()
        response.say(
            "Connecting you to our diagnostic assistant. One moment please.",
            voice="Polly.Joanna",
        )
        connect = Connect()
        connect.stream(url=self._media_stream_ws_url())
        response.append(connect)
        twiml = str(response)
        logger.info(
            "Built inbound TwiML | sid={} stream_url={}",
            call_sid, self._media_stream_ws_url(),
        )
        return twiml
