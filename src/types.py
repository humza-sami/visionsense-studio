"""Shared lightweight data types passed between pipeline stages.

Keeping these framework-agnostic means business logic never imports ultralytics
or supervision directly — only the inference/tracking layers do.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Detection:
    xyxy: tuple[float, float, float, float]
    conf: float
    cls_id: int
    cls_name: str


@dataclass
class Track:
    track_id: int
    xyxy: tuple[float, float, float, float]
    conf: float
    cls_id: int
    cls_name: str

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def bottom_center(self) -> tuple[float, float]:
        """Feet/base point — better than centroid for ground-plane logic."""
        x1, _, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, y2)
