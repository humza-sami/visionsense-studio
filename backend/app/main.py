"""
VisionSense Studio — FastAPI application entry point.

Startup sequence:
1. Configure CORS (allow all origins for demo use)
2. Mount API routes
3. Start WebSocket telemetry broadcaster
4. Optionally serve compiled React SPA from frontend/dist
5. Expose health check

Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api import api_router
from app.api.websocket import get_broadcast_loop
from app.core.camera_manager import camera_manager

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    logger.info("VisionSense Studio backend starting...")

    # Pre-warm the default YOLO model in a background thread so the first
    # camera start doesn't stall the event loop.
    async def _prewarm():
        try:
            import threading
            def _load():
                from app.core.inference_engine import _load_model
                _load_model(settings.default_model, settings.yolo_device)
            t = threading.Thread(target=_load, daemon=True, name="prewarm")
            t.start()
        except Exception as e:
            logger.warning(f"Model pre-warm failed: {e}")

    asyncio.create_task(_prewarm())

    # Start telemetry broadcaster
    broadcast_task = asyncio.create_task(get_broadcast_loop())
    logger.info("Telemetry broadcaster task created")

    yield  # ← app runs here

    # Shutdown
    logger.info("Shutting down...")
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass
    camera_manager.shutdown()
    logger.info("Shutdown complete")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="VisionSense Studio API",
    description="AI-on-CCTV live demo platform — FastAPI backend",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],              # Open for demo; tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    return {
        "status": "ok",
        "ts": time.time(),
        "cameras": len(camera_manager.list()),
    }


# ── API routes ────────────────────────────────────────────────────────────────

app.include_router(api_router)


# ── SPA static file serving ───────────────────────────────────────────────────
# Mount the compiled React build if it exists.
# This makes FastAPI serve the full product from a single process.

_FRONTEND_DIST = settings.frontend_dist
_INDEX_HTML = _FRONTEND_DIST / "index.html"


def _setup_spa():
    if not _FRONTEND_DIST.exists():
        logger.info(
            f"Frontend dist not found at {_FRONTEND_DIST} — serving API only. "
            "Run `npm run build` inside frontend/ to enable SPA serving."
        )
        return

    # Mount the assets folder under /assets so Vite-generated hashed filenames work
    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    logger.info(f"Serving React SPA from {_FRONTEND_DIST}")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request):
        """
        SPA catch-all: serve index.html for any non-API, non-stream path.
        Static assets (js/css/images) are served directly from /assets.
        """
        # Check if it's a real static file first
        candidate = _FRONTEND_DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        # Fall through to index.html for client-side routing
        if _INDEX_HTML.exists():
            return FileResponse(str(_INDEX_HTML))
        return JSONResponse({"detail": "Frontend not built"}, status_code=404)


_setup_spa()
