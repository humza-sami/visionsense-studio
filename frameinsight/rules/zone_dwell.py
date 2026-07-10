"""Zone dwell — how long each track stays inside a drawn area, plus occupancy.

Used for "how long do kids stand at the water cooler", "time spent at a
counter", queue analytics, etc. The zone is a polygon tested against the foot
anchor.

Per-track state machine::

    outside → (foot in zone, sustained sustain_s) → inside
    inside  → (foot out for exit_grace_s, or track lost) → outside, dwell ends

``exit_grace_s`` bridges short occlusions and detector flicker so one visit
doesn't fragment into many. A dwell shorter than ``min_dwell_s`` (someone just
walking through) is dropped from stats and never emitted.

Emits:
- ``dwell_started``   {}                                     when a visit begins
- ``dwell_completed`` {dwell_s}                              when a visit ends
- ``occupancy``       {current, visits, avg_dwell_s, max_dwell_s}
                      every ``summary_every_s``

The running average in ``occupancy`` is over *completed* visits since start
(restored across restarts via snapshot_state).
"""

from __future__ import annotations

from typing import Any

from ..geometry import point_in_polygon
from ..types import Detection
from .base import Rule


class ZoneDwell(Rule):
    KIND = "zone_dwell"

    def configure(
        self,
        *,
        min_dwell_s: float = 3.0,
        exit_grace_s: float = 2.0,
        summary_every_s: float = 60.0,
        **params: Any,
    ) -> None:
        super().configure(**params)
        if self.zone is None or self.zone.type != "polygon":
            raise ValueError(f"rule '{self.name}': zone_dwell needs a polygon zone")
        self.min_dwell_s = float(min_dwell_s)
        self.exit_grace_s = float(exit_grace_s)
        self.summary_every_s = float(summary_every_s)
        # tid -> {"first_in": ts, "entered": ts|None, "last_in": ts}
        self._visits: dict[int, dict[str, float | None]] = {}
        self.completed_visits = 0
        self.total_dwell_s = 0.0
        self.max_dwell_s = 0.0
        self._summary_at: float | None = None

    def on_frame(self, ts: float, detections: list[Detection]) -> None:
        poly = list(self.zone.points)
        for det in detections:
            if not det.is_tracked:
                continue
            inside = point_in_polygon(det.foot, poly)
            v = self._visits.get(det.track_id)
            if inside:
                if v is None:
                    v = {"first_in": ts, "entered": None, "last_in": ts}
                    self._visits[det.track_id] = v
                v["last_in"] = ts
                if v["entered"] is None and ts - v["first_in"] >= self.sustain_s:
                    v["entered"] = v["first_in"]
                    self.emit(ts, "dwell_started", track_id=det.track_id)
            elif v is not None:
                if v["entered"] is None:
                    # Never sustained — a blip, not a visit.
                    del self._visits[det.track_id]
                elif ts - v["last_in"] >= self.exit_grace_s:
                    self._finish_visit(ts, det.track_id, end_ts=v["last_in"])

        if self._summary_at is None:
            self._summary_at = ts + self.summary_every_s
        elif ts >= self._summary_at:
            current = sum(1 for v in self._visits.values() if v["entered"] is not None)
            avg = self.total_dwell_s / self.completed_visits if self.completed_visits else 0.0
            self.emit(ts, "occupancy", {
                "current": current,
                "visits": self.completed_visits,
                "avg_dwell_s": round(avg, 1),
                "max_dwell_s": round(self.max_dwell_s, 1),
            })
            self._summary_at = ts + self.summary_every_s

    def on_track_lost(self, ts: float, track_id: int) -> None:
        v = self._visits.get(track_id)
        if v is not None and v["entered"] is not None:
            self._finish_visit(ts, track_id, end_ts=v["last_in"])
        else:
            self._visits.pop(track_id, None)

    def _finish_visit(self, ts: float, track_id: int, *, end_ts: float) -> None:
        v = self._visits.pop(track_id)
        dwell = end_ts - v["entered"]
        if dwell < self.min_dwell_s:
            return
        self.completed_visits += 1
        self.total_dwell_s += dwell
        self.max_dwell_s = max(self.max_dwell_s, dwell)
        self.emit(ts, "dwell_completed", {"dwell_s": round(dwell, 1)},
                  track_id=track_id)

    def snapshot_state(self) -> dict[str, Any]:
        return {
            "completed_visits": self.completed_visits,
            "total_dwell_s": self.total_dwell_s,
            "max_dwell_s": self.max_dwell_s,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.completed_visits = int(state.get("completed_visits", 0))
        self.total_dwell_s = float(state.get("total_dwell_s", 0.0))
        self.max_dwell_s = float(state.get("max_dwell_s", 0.0))
