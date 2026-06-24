"""System and hardware capability endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.media_agent_client import get_media_capabilities

router = APIRouter(tags=["system"])


@router.get("/system/capabilities")
async def system_capabilities():
    return await get_media_capabilities()
