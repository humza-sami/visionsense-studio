"""Latest-frame buffer (drop-old). One slot per camera; new frame overwrites old.

This is the backpressure strategy from the plan: never queue stale video. The GPU
loop always reads the *current* scene, so it can't fall behind real time.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np


class LatestFrameBuffer:
    def __init__(self) -> None:
        self._frames: dict[str, tuple[np.ndarray, float]] = {}
        self._lock = threading.Lock()

    def put(self, cam_id: str, frame: np.ndarray) -> None:
        with self._lock:
            self._frames[cam_id] = (frame, time.monotonic())

    def get(self, cam_id: str) -> Optional[np.ndarray]:
        with self._lock:
            entry = self._frames.get(cam_id)
            return entry[0] if entry else None

    def snapshot(self) -> dict[str, np.ndarray]:
        """Current frame for every camera that has one (shallow copy of dict)."""
        with self._lock:
            return {cid: f for cid, (f, _) in self._frames.items()}

    def age(self, cam_id: str) -> Optional[float]:
        """Seconds since the last frame for a camera (None if never seen)."""
        with self._lock:
            entry = self._frames.get(cam_id)
            return (time.monotonic() - entry[1]) if entry else None
