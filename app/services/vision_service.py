"""Vision service — analyses uploaded appliance photos via GPT-4o."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.dto.diagnosis import VisionAnalysisDTO
from app.services.openai_client import openai_client_factory

logger = get_logger(__name__)


_VISION_INSTRUCTIONS = (
    "You are a senior appliance repair technician examining a photo a customer "
    "sent in. Identify the appliance type if visible and describe any visible "
    "issues, leaks, error displays, damage, blockages, or unusual indicators. "
    "Return ONLY JSON matching this schema:\n"
    "{\n"
    '  "detected_appliance": string|null,\n'
    '  "visible_issues": string[],\n'
    '  "error_indicators": string[],\n'
    '  "severity_estimate": "low"|"medium"|"high"|"critical",\n'
    '  "summary": string\n'
    "}"
)


class VisionService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = openai_client_factory.client

    async def analyze_image(self, image_path: Path) -> VisionAnalysisDTO:
        if not image_path.exists():
            raise FileNotFoundError(image_path)

        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        suffix = image_path.suffix.lower().lstrip(".") or "jpeg"
        if suffix == "jpg":
            suffix = "jpeg"
        data_url = f"data:image/{suffix};base64,{b64}"

        response = await self._client.chat.completions.create(
            model=self._settings.openai.vision_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _VISION_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please analyse this appliance photo."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Vision returned non-JSON, falling back | raw={}", raw[:200])
            data = {"summary": raw, "visible_issues": [], "error_indicators": []}

        return VisionAnalysisDTO(**data)
