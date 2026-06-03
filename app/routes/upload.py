"""Image upload routes — used when the agent emails a customer an upload link."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.config.logging_config import get_logger
from app.database.session import db_manager
from app.dependencies import (
    UploadedImage,
    get_upload_service,
    resolve_active_upload_link,
    validate_image_payload,
)
from app.models.upload_link import UploadLink, UploadStatus
from app.services.upload_service import UploadError, UploadService
from app.services.vision_service import VisionService

logger = get_logger(__name__)
router = APIRouter(tags=["upload"])


_UPLOAD_PAGE = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Diagnostic — Upload your photo</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 480px;
            margin: 4rem auto; padding: 0 1rem; color:#222; }}
    h1 {{ font-size: 1.4rem; }}
    form {{ display: flex; flex-direction: column; gap: 1rem; }}
    input[type=file] {{ padding: 0.6rem; border: 1px solid #ccc; border-radius: 6px; }}
    button {{ background: #003366; color: white; border: 0; padding: 0.8rem;
              border-radius: 6px; font-size: 1rem; cursor: pointer; }}
    .note {{ color:#666; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>Upload a photo of your appliance</h1>
  <p class="note">Token: <code>{token}</code></p>
  <form action="/upload/{token}" method="post" enctype="multipart/form-data">
    <input type="file" name="file" accept="image/*" required />
    <button type="submit">Upload</button>
  </form>
</body>
</html>
"""


@router.get("/upload/{token}", response_class=HTMLResponse)
async def upload_form(
    token: str,
    link: UploadLink = Depends(resolve_active_upload_link),
) -> HTMLResponse:
    if link.status in (UploadStatus.UPLOADED, UploadStatus.ANALYZED):
        return HTMLResponse(
            "<h2>Thank you — we already have your photo.</h2>", status_code=200
        )
    return HTMLResponse(_UPLOAD_PAGE.format(token=token))


@router.post("/upload/{token}")
async def upload_post(
    token: str,
    background: BackgroundTasks,
    link: UploadLink = Depends(resolve_active_upload_link),  # noqa: ARG001
    image: UploadedImage = Depends(validate_image_payload),
    service: UploadService = Depends(get_upload_service),
) -> dict:
    try:
        stored = await service.store_upload(
            token=token, filename=image.filename, content=image.content
        )
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background.add_task(_run_vision_analysis, token, stored)
    return {"status": "ok", "message": "Upload received. Analysis in progress."}


async def _run_vision_analysis(token: str, image_path: Path) -> None:
    """Background task — runs vision analysis and stores the summary.

    Lives outside the request lifecycle, so it manages its own DB session
    via ``db_manager.session()`` rather than going through ``Depends``.
    """
    try:
        analysis = await VisionService().analyze_image(image_path)
        async with db_manager.session() as session:
            await UploadService(session).attach_analysis(token, analysis.summary)
        logger.info("Vision analysis complete | token={}", token)
    except Exception:
        logger.exception("Vision analysis failed | token={}", token)
