"""
Media pipeline client.

Wraps the FFmpeg-based RTSP→mediamtx bridge. The C++ media agent binary
is used only for capability detection (hardware codec info); actual video
streaming is handled by FFmpeg which tolerates NVR timestamp quirks that
GStreamer (used by the C++ agent) does not.
"""
from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote

import httpx

from app.config import settings
from app.core import ffmpeg_bridge


async def get_media_capabilities() -> Dict[str, Any]:
    """Return native capabilities from the C++ agent, or a fallback."""
    try:
        async with httpx.AsyncClient(timeout=settings.media_agent_timeout_s) as client:
            response = await client.get(f"{settings.media_agent_url}/v1/capabilities")
            response.raise_for_status()
            return {
                "status": "ready",
                "url": settings.media_agent_url,
                "capabilities": response.json(),
            }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "status": "offline",
            "url": settings.media_agent_url,
            "detail": str(exc),
            "capabilities": None,
        }


def start_native_pipeline(camera_id: str, uri: str) -> bool:
    """Start an FFmpeg bridge from the NVR RTSP stream to mediamtx."""
    return ffmpeg_bridge.start(camera_id, uri)


def stop_native_pipeline(camera_id: str) -> None:
    ffmpeg_bridge.stop(camera_id)


def list_native_pipelines() -> List[Dict[str, Any]]:
    return ffmpeg_bridge.list_all()


def native_stream_url(camera_id: str) -> str:
    return f"http://localhost:8889/{quote(camera_id, safe='')}/whep"
