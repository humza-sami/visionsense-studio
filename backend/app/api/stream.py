"""
MJPEG streaming endpoint.

Route:
    GET /stream/{cam_id}

Returns a multipart/x-mixed-replace HTTP response.
Each part is a JPEG-encoded annotated frame pulled from the camera worker's queue.

The stream stays alive as long as the client is connected.
If the camera is idle or stopped, we serve a placeholder image.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.camera_manager import camera_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])

# ── Placeholder frame ─────────────────────────────────────────────────────────

def _make_placeholder(message: str, width: int = 640, height: int = 360) -> bytes:
    """Generate a simple dark-grey placeholder JPEG with a centered message."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (30, 30, 30)  # dark background

    # Centered text
    lines = message.split("\n")
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.7
    thickness = 1
    line_height = 35

    total_h = len(lines) * line_height
    y = (height - total_h) // 2

    for line in lines:
        (tw, th), _ = cv2.getTextSize(line, font, scale, thickness)
        x = (width - tw) // 2
        cv2.putText(img, line, (x, y + th), font, scale, (160, 160, 160), thickness, cv2.LINE_AA)
        y += line_height

    ret, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return buf.tobytes() if ret else b""


# ── Async frame generator ─────────────────────────────────────────────────────

async def _frame_generator(cam_id: str) -> AsyncGenerator[bytes, None]:
    """
    Async generator that yields MJPEG multipart chunks.
    Pulls frames from the camera worker queue via run_in_executor to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    BOUNDARY = b"--frame"
    CONTENT_TYPE = b"Content-Type: image/jpeg\r\n\r\n"

    camera = camera_manager.get(cam_id)
    if camera is None:
        placeholder = _make_placeholder(f"Camera '{cam_id}'\nnot found")
        chunk = BOUNDARY + b"\r\n" + CONTENT_TYPE + placeholder + b"\r\n"
        yield chunk
        return

    last_frame: bytes = _make_placeholder("Connecting...\nPlease wait")
    last_frame_time = 0.0
    IDLE_PLACEHOLDER_INTERVAL = 0.1  # 10 fps for placeholder frames

    try:
        while True:
            # Pull frame from worker queue (non-blocking via executor)
            frame_bytes: bytes | None = await loop.run_in_executor(
                None, camera_manager.get_frame, cam_id, 0.05  # 50ms timeout
            )

            if frame_bytes:
                last_frame = frame_bytes
                last_frame_time = time.monotonic()
            else:
                # No new frame — serve last known frame or placeholder
                cam = camera_manager.get(cam_id)
                status = cam.status if cam else "error"

                elapsed = time.monotonic() - last_frame_time
                if elapsed > 2.0 or status not in ("live", "connecting"):
                    # Camera not producing frames — show status placeholder
                    msg = {
                        "idle": "Camera idle\nPress Start",
                        "connecting": "Connecting...",
                        "error": f"Stream error\n{cam.error_message or ''}",
                        "stopped": "Camera stopped",
                    }.get(status, status)
                    last_frame = _make_placeholder(msg)

                # Throttle placeholder delivery
                await asyncio.sleep(IDLE_PLACEHOLDER_INTERVAL)

            chunk = BOUNDARY + b"\r\n" + CONTENT_TYPE + last_frame + b"\r\n"
            yield chunk

            # Small sleep to yield control back to asyncio event loop
            # Real frames come at camera FPS; this just prevents tight-loop on empties.
            await asyncio.sleep(0.001)

    except asyncio.CancelledError:
        # Client disconnected — normal exit
        logger.debug(f"[stream/{cam_id}] Client disconnected")
        return
    except Exception as e:
        logger.error(f"[stream/{cam_id}] Generator error: {e}", exc_info=True)
        return


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get(
    "/stream/{cam_id}",
    responses={
        200: {"content": {"multipart/x-mixed-replace; boundary=frame": {}}},
        404: {"description": "Camera not found"},
    },
)
async def mjpeg_stream(cam_id: str):
    """
    Stream annotated video for the given camera as MJPEG.

    Compatible with standard HTML `<img src="/stream/{cam_id}">`.
    """
    camera = camera_manager.get(cam_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    return StreamingResponse(
        _frame_generator(cam_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Access-Control-Allow-Origin": "*",
        },
    )
