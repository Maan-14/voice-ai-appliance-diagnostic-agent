from app.routes.aria import router as aria_router
from app.routes.health import router as health_router
from app.routes.upload import router as upload_router
from app.routes.voice import router as voice_router

__all__ = ["aria_router", "health_router", "voice_router", "upload_router"]
