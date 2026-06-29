"""Cheap CPU motion gate (§5.8). Runs before the GPU; skips inference on static
frames. One MOG2 background subtractor per camera, applied to a downscaled gray
frame so it costs almost nothing.

CAVEAT: never gate theft / subtle-hand zones — set `motion_gate: false` for those
cameras in cameras.yaml. Use it for empty rooms, corridors, idle desks.
"""
from __future__ import annotations

import cv2
import numpy as np


class MotionGate:
    def __init__(self, min_area: int = 500) -> None:
        self.min_area = min_area
        self._bg: dict[str, cv2.BackgroundSubtractorMOG2] = {}

    def is_active(self, cam_id: str, frame: np.ndarray) -> bool:
        sub = self._bg.get(cam_id)
        if sub is None:
            sub = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
            self._bg[cam_id] = sub
        small = cv2.resize(frame, (320, 180))
        mask = sub.apply(small)
        return int((mask > 0).sum()) > self.min_area
