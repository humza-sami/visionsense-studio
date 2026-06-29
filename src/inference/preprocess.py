"""Preprocess helpers. Ultralytics letterboxes internally, so the detector path
doesn't need these — they're here for the optional ROI-crop optimisation (§5.9):
crop to a zone before inference when only a small area matters (fewer pixels =
less GPU), then map detections back to full-frame coordinates.
"""
from __future__ import annotations

import numpy as np


def crop_to_bbox(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    return frame[y1:y2, x1:x2]


def offset_detections(dets, dx: int, dy: int):
    """Shift detection boxes from crop-space back to full-frame coordinates."""
    out = []
    for d in dets:
        x1, y1, x2, y2 = d.xyxy
        d.xyxy = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        out.append(d)
    return out


def polygon_bbox(polygon) -> tuple[int, int, int, int]:
    pts = np.array(polygon)
    return int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())
