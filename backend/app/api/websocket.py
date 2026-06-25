"""
WebSocket telemetry endpoint.

Route:
    WS /ws/telemetry

The server broadcasts a JSON message every ~200ms for each active camera:
{
    "cam_id":             "cam_01",
    "fps":                24.3,
    "video_fps":          25.0,
    "ai_fps":             8.2,
    "inference_ms":       18,
    "counts":             {"person": 7},
    "detections":         [{"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.7}],
    "application_outputs": { ... },
    "alerts":             [{"type": "...", "ts": ..., "detail": "..."}]
}

Multiple clients can connect simultaneously; all receive the same broadcast.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.camera_manager import camera_manager, set_detection_push_cb

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


# ── Connection registry ───────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info(f"WS connected: {ws.client}  total={len(self._connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)
        logger.info(f"WS disconnected: {ws.client}  total={len(self._connections)}")

    async def broadcast(self, payload: dict):
        """Send JSON payload to all connected clients; silently drop failed sends."""
        msg = json.dumps(payload)
        dead: list = []
        async with self._lock:
            conns = set(self._connections)
        for ws in conns:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


_manager = ConnectionManager()


# ── Background broadcaster task ───────────────────────────────────────────────

async def _telemetry_broadcast_loop():
    """
    Runs as a background asyncio task (started in main.py on_startup).

    Two-tier broadcast:
    1. Immediate — inference thread pushes detections via set_detection_push_cb();
       this loop wakes instantly and broadcasts to all WS clients.
    2. Periodic fallback (200ms) — polls video-only cameras for fps/status updates.
    """
    loop = asyncio.get_running_loop()
    push_q: asyncio.Queue = asyncio.Queue(maxsize=500)

    def _push_from_thread(payload: dict) -> None:
        try:
            loop.call_soon_threadsafe(push_q.put_nowait, payload)
        except Exception:
            pass

    set_detection_push_cb(_push_from_thread)
    interval = settings.telemetry_interval_ms / 1000.0
    logger.info(f"Telemetry broadcaster started (immediate push + {interval}s fallback poll)")

    while True:
        try:
            # Wake immediately when a detection arrives; timeout → periodic poll
            payload = await asyncio.wait_for(push_q.get(), timeout=interval)
            if _manager.count > 0:
                await _manager.broadcast(payload)
                # Drain any additional frames that queued during the broadcast
                while not push_q.empty():
                    try:
                        await _manager.broadcast(push_q.get_nowait())
                    except asyncio.QueueEmpty:
                        break
        except asyncio.TimeoutError:
            # No inference pushes for `interval` seconds — poll for video-only cameras
            try:
                if _manager.count > 0:
                    for tele in camera_manager.get_all_telemetry():
                        await _manager.broadcast(tele)
            except Exception as e:
                logger.error(f"Telemetry poll error: {e}", exc_info=True)


# ── WebSocket route ───────────────────────────────────────────────────────────

@router.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket):
    """
    WebSocket endpoint for real-time telemetry.

    Clients connect and receive JSON pushes every ~200ms for each active camera.
    Clients may optionally send JSON commands (currently unused but reserved for
    future bidirectional control).
    """
    await _manager.connect(ws)
    try:
        # Send an initial "connected" acknowledgement
        await ws.send_text(json.dumps({
            "type": "connected",
            "ts": time.time(),
            "message": "VisionSense telemetry stream active",
        }))

        # Keep the connection alive by listening for any incoming messages
        # (ping/pong or future control commands)
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                # Echo back or handle future commands
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await ws.send_text(json.dumps({"type": "pong", "ts": time.time()}))
                except Exception:
                    pass
            except asyncio.TimeoutError:
                # Send a keepalive ping
                try:
                    await ws.send_text(json.dumps({"type": "ping", "ts": time.time()}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error for {ws.client}: {e}")
    finally:
        await _manager.disconnect(ws)


# ── Expose broadcaster for main.py ────────────────────────────────────────────

def get_broadcast_loop() -> "asyncio.Coroutine":
    return _telemetry_broadcast_loop()
