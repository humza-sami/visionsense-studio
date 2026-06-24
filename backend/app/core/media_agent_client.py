"""Client for the native VisionSense media agent control API."""
from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote

import httpx

from app.config import settings


async def get_media_capabilities() -> Dict[str, Any]:
    """Return native capabilities or an explicit offline response."""
    try:
        async with httpx.AsyncClient(timeout=settings.media_agent_timeout_s) as client:
            response = await client.get(f"{settings.media_agent_url}/v1/capabilities")
            response.raise_for_status()
            capabilities = response.json()
        return {
            "status": "ready",
            "url": settings.media_agent_url,
            "capabilities": capabilities,
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "status": "offline",
            "url": settings.media_agent_url,
            "detail": str(exc),
            "capabilities": None,
        }


def start_native_pipeline(camera_id: str, uri: str) -> bool:
    """Start a native RTSP pipeline. Return False when the agent is unavailable."""
    try:
        response = httpx.post(
            f"{settings.media_agent_url}/v1/pipelines/{quote(camera_id, safe='')}",
            json={"uri": uri},
            timeout=settings.media_agent_timeout_s,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def stop_native_pipeline(camera_id: str) -> None:
    try:
        httpx.delete(
            f"{settings.media_agent_url}/v1/pipelines/{quote(camera_id, safe='')}",
            timeout=settings.media_agent_timeout_s,
        )
    except httpx.HTTPError:
        pass


def list_native_pipelines() -> List[Dict[str, Any]]:
    try:
        response = httpx.get(
            f"{settings.media_agent_url}/v1/pipelines",
            timeout=settings.media_agent_timeout_s,
        )
        response.raise_for_status()
        return response.json().get("pipelines", [])
    except (httpx.HTTPError, ValueError):
        return []


def native_stream_url(camera_id: str) -> str:
    return f"{settings.media_agent_url}/v1/streams/{quote(camera_id, safe='')}"
