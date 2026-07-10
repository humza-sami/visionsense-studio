"""Zone intrusion — alert when someone enters a restricted area.

The reference kernel from the platform architecture doc (§4.1). A track whose
foot anchor stays inside the polygon for ``sustain_s`` raises one alert; the
same track can't re-alert until it leaves and ``cooldown_s`` passes.

Emits:
- ``intrusion``     {confidence}   severity=alert, once per sustained entry
- ``intrusion_end`` {duration_s}   when the intruder leaves / track is lost
"""

from __future__ import annotations

from typing import Any

from ..geometry import point_in_polygon
from ..types import Detection
from .base import Rule


class ZoneIntrusion(Rule):
    KIND = "zone_intrusion"

    def configure(self, **params: Any) -> None:
        super().configure(**params)
        if self.zone is None or self.zone.type != "polygon":
            raise ValueError(f"rule '{self.name}': zone_intrusion needs a polygon zone")
        # tid -> {"first_in": ts, "alerted": ts|None, "last_in": ts}
        self._inside: dict[int, dict[str, float | None]] = {}

    def on_frame(self, ts: float, detections: list[Detection]) -> None:
        poly = list(self.zone.points)
        for det in detections:
            if not det.is_tracked:
                continue
            inside = point_in_polygon(det.foot, poly)
            st = self._inside.get(det.track_id)
            if inside:
                if st is None:
                    st = {"first_in": ts, "alerted": None, "last_in": ts}
                    self._inside[det.track_id] = st
                st["last_in"] = ts
                if (st["alerted"] is None
                        and ts - st["first_in"] >= self.sustain_s
                        and self.cooled_down(ts, key=str(det.track_id))):
                    st["alerted"] = ts
                    self.emit(ts, "intrusion",
                              {"confidence": round(det.confidence, 3)},
                              severity="alert", track_id=det.track_id)
            elif st is not None:
                self._close(ts, det.track_id)

    def on_track_lost(self, ts: float, track_id: int) -> None:
        if track_id in self._inside:
            self._close(ts, track_id)

    def _close(self, ts: float, track_id: int) -> None:
        st = self._inside.pop(track_id)
        if st["alerted"] is not None:
            self.emit(ts, "intrusion_end",
                      {"duration_s": round(st["last_in"] - st["first_in"], 1)},
                      track_id=track_id)
