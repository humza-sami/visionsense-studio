"""Annotation for the MJPEG preview — draw tracked boxes + IDs onto a frame."""
from __future__ import annotations

import cv2
import numpy as np

from src.types import Track
from src.zones import Zone

# Deterministic-ish color per class id.
_PALETTE = [
    (66, 135, 245), (52, 199, 89), (255, 149, 0), (255, 59, 48),
    (175, 82, 222), (0, 199, 190), (255, 214, 10), (191, 90, 242),
]


def _color(cls_id: int) -> tuple[int, int, int]:
    return _PALETTE[cls_id % len(_PALETTE)]


def draw(
    frame: np.ndarray,
    tracks: list[Track],
    zones: list[Zone] | None = None,
    label: str | None = None,
) -> np.ndarray:
    img = frame.copy()

    if zones:
        for z in zones:
            pts = np.array(z.polygon, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(img, [pts], isClosed=True, color=(0, 255, 255), thickness=2)
            cv2.putText(img, z.name, tuple(z.polygon[0]), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 255), 2)

    for t in tracks:
        x1, y1, x2, y2 = (int(v) for v in t.xyxy)
        c = _color(t.cls_id)
        cv2.rectangle(img, (x1, y1), (x2, y2), c, 2)
        tag = f"#{t.track_id} {t.cls_name} {t.conf:.2f}"
        cv2.putText(img, tag, (x1, max(0, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, c, 2)

    if label:
        cv2.putText(img, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 2)
    return img
