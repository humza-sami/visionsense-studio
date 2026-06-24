from fastapi import APIRouter
from .cameras import router as cameras_router
from .stream import router as stream_router
from .websocket import router as ws_router

api_router = APIRouter()
api_router.include_router(cameras_router, prefix="/api")
api_router.include_router(stream_router)
api_router.include_router(ws_router)

__all__ = ["api_router"]
