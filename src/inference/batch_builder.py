"""Gather one frame from each camera that should be detected this tick into a
single batch for one inference call (§5.5). cam_order maps results back to cams.
"""
from __future__ import annotations

import numpy as np

from src.capture.frame_buffer import LatestFrameBuffer


def build_batch(
    buffer: LatestFrameBuffer, cam_ids: list[str]
) -> tuple[list[np.ndarray], list[str]]:
    snap = buffer.snapshot()
    frames: list[np.ndarray] = []
    cam_order: list[str] = []
    for cid in cam_ids:
        frame = snap.get(cid)
        if frame is not None:
            frames.append(frame)
            cam_order.append(cid)
    return frames, cam_order
