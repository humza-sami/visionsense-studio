"""Directional line crossing — entry/exit counting at a gate or doorway.

The zone is a **directed line** (2 points, a→b). A track "crosses" when its
foot anchor moves from one side of the line to the other between two processed
frames *and* the segment it travelled actually intersects the gate segment
(so walking around the end of the line doesn't count).

Direction naming: crossing to the **left** of travel direction a→b emits
``label_left`` (default "in"); to the right, ``label_right`` (default "out").
Draw the line so that "in" means what the client thinks it means, and check it
against the reference snapshot — see the example's zone files.

Emits:
- ``line_crossed``  {direction, totals}         per crossing, per track
- ``count_summary`` {in, out, window_s}          every ``summary_every_s``
"""

from __future__ import annotations

from typing import Any

from ..geometry import segments_intersect, side_of_line
from ..types import Detection
from .base import Rule


class LineCrossing(Rule):
    KIND = "line_crossing"

    def configure(
        self,
        *,
        label_left: str = "in",
        label_right: str = "out",
        recross_cooldown_s: float = 2.0,
        summary_every_s: float = 60.0,
        **params: Any,
    ) -> None:
        super().configure(**params)
        if self.zone is None or self.zone.type != "line":
            raise ValueError(f"rule '{self.name}': line_crossing needs a line zone")
        self.label_left = label_left
        self.label_right = label_right
        self.recross_cooldown_s = float(recross_cooldown_s)
        self.summary_every_s = float(summary_every_s)
        self.counts: dict[str, int] = {label_left: 0, label_right: 0}
        self._side: dict[int, tuple[int, tuple[float, float]]] = {}  # tid -> (side, foot)
        self._last_cross: dict[int, float] = {}
        self._summary_at: float | None = None

    def on_frame(self, ts: float, detections: list[Detection]) -> None:
        a, b = self.zone.points
        for det in detections:
            if not det.is_tracked:
                continue
            foot = det.foot
            side = side_of_line(a, b, foot)
            prev = self._side.get(det.track_id)
            if side != 0:
                self._side[det.track_id] = (side, foot)
            if prev is None or side == 0:
                continue
            prev_side, prev_foot = prev
            if side == prev_side:
                continue
            # Side flipped — require the actual path to cut the gate segment.
            if not segments_intersect(prev_foot, foot, a, b):
                continue
            last = self._last_cross.get(det.track_id)
            if last is not None and ts - last < self.recross_cooldown_s:
                continue
            self._last_cross[det.track_id] = ts
            direction = self.label_left if side > 0 else self.label_right
            self.counts[direction] += 1
            self.emit(ts, "line_crossed", {
                "direction": direction,
                "totals": dict(self.counts),
            }, track_id=det.track_id)

        if self._summary_at is None:
            self._summary_at = ts + self.summary_every_s
        elif ts >= self._summary_at:
            self.emit(ts, "count_summary", {
                **{k: v for k, v in self.counts.items()},
                "window_s": self.summary_every_s,
            })
            self._summary_at = ts + self.summary_every_s

    def on_track_lost(self, ts: float, track_id: int) -> None:
        self._side.pop(track_id, None)
        self._last_cross.pop(track_id, None)

    def snapshot_state(self) -> dict[str, Any]:
        return {"counts": dict(self.counts)}

    def restore_state(self, state: dict[str, Any]) -> None:
        self.counts.update(state.get("counts", {}))
