"""Headcount — smoothed periodic count of people in a zone (or whole frame).

Used for classroom occupancy, room utilization, crowd level. Raw per-frame
counts flicker (missed detections, partial occlusion), so we report the
**median** of the counts sampled over ``window_s`` — one flickery frame can't
move the median.

Track IDs are not required; counting is frame-level. The zone is optional:
omit it to count the whole camera view.

Emits:
- ``headcount``  {count, min, max, samples}   every ``report_every_s``
- ``overcrowded`` {count, limit}              when the smoothed count exceeds
                                              ``max_count`` (0 disables),
                                              rate-limited by ``cooldown_s``
"""

from __future__ import annotations

from statistics import median
from typing import Any

from ..geometry import point_in_polygon
from ..types import Detection
from .base import Rule


class Headcount(Rule):
    KIND = "headcount"

    def configure(
        self,
        *,
        report_every_s: float = 30.0,
        window_s: float = 10.0,
        max_count: int = 0,
        **params: Any,
    ) -> None:
        super().configure(**params)
        if self.zone is not None and self.zone.type != "polygon":
            raise ValueError(f"rule '{self.name}': headcount zone must be a polygon")
        self.report_every_s = float(report_every_s)
        self.window_s = float(window_s)
        self.max_count = int(max_count)
        self._samples: list[tuple[float, int]] = []
        self._report_at: float | None = None

    def on_frame(self, ts: float, detections: list[Detection]) -> None:
        if self.zone is not None:
            poly = list(self.zone.points)
            count = sum(1 for d in detections if point_in_polygon(d.foot, poly))
        else:
            count = len(detections)
        self._samples.append((ts, count))
        cutoff = ts - self.window_s
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

        if self._report_at is None:
            self._report_at = ts + self.report_every_s
        elif ts >= self._report_at:
            counts = [c for _, c in self._samples]
            smoothed = int(median(counts)) if counts else 0
            self.emit(ts, "headcount", {
                "count": smoothed,
                "min": min(counts) if counts else 0,
                "max": max(counts) if counts else 0,
                "samples": len(counts),
            })
            if self.max_count and smoothed > self.max_count and self.cooled_down(ts):
                self.emit(ts, "overcrowded",
                          {"count": smoothed, "limit": self.max_count},
                          severity="alert")
            self._report_at = ts + self.report_every_s
