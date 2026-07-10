"""Desk / chair occupancy with per-desk timers — the office client's kernel.

One polygon per desk (drawn in Zone Studio, named desk1, desk2, …). A desk is
OCCUPIED while any person's box-center sits inside its polygon (box-center,
not feet: a seated person's feet are hidden under the desk). The timer belongs
to the DESK, not to a tracker ID — seated people get occluded and IDs churn,
but "somebody is in this chair area" is stable across ID swaps.

State machine per desk (same guard philosophy as the built-ins)::

    empty → person present sustained sustain_s        → occupied (session starts)
    occupied → zone empty for empty_grace_s           → vacated  (session ends)
    occupied ≥ working_after_s                        → counted as "working"

Emits:
- ``desk_occupied`` / ``desk_vacated`` {desk, session_s}     per session
- ``desk_summary`` {present, occupied, working, per_desk}    every summary_every_s

live_state() feeds the Studio live view: per-desk occupied/working flags,
current session seconds, and accumulated seconds today (resets at midnight).
"""

from __future__ import annotations

import time
from typing import Any

from frameinsight.geometry import point_in_polygon
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule
from frameinsight.types import Detection


@register_kernel
class DeskOccupancy(Rule):
    KIND = "desk_occupancy"

    def configure(
        self,
        *,
        zones: list | None = None,
        desk_prefix: str = "desk",
        working_after_s: float = 120.0,
        empty_grace_s: float = 20.0,
        summary_every_s: float = 60.0,
        **params: Any,
    ) -> None:
        super().configure(**params)
        self.desks = {
            z.name: list(z.points)
            for z in (zones or [])
            if z.type == "polygon" and z.name.startswith(desk_prefix)
        }
        if not self.desks:
            # Zones not drawn yet — stay inert so the site runs before setup
            # is finished. Studio will populate the zone file.
            import logging
            logging.getLogger("frameinsight.rules").warning(
                "rule '%s' (%s): no '%s*' polygons yet — draw desks in Zone Studio",
                self.name, self.cam_id, desk_prefix)
        self.working_after_s = float(working_after_s)
        self.empty_grace_s = float(empty_grace_s)
        self.summary_every_s = float(summary_every_s)
        # per desk: first (pre-sustain), since (session start), last_seen,
        # today_s (closed sessions), sessions
        self._st: dict[str, dict[str, Any]] = {
            name: {"first": None, "since": None, "last_seen": 0.0,
                   "today_s": 0.0, "sessions": 0}
            for name in self.desks
        }
        self._present_now = 0
        self._day = None
        self._summary_at: float | None = None

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _anchor(det: Detection) -> tuple[float, float]:
        return det.center  # seated people: feet are under the desk

    def _roll_day(self, ts: float) -> None:
        day = time.localtime(ts).tm_yday
        if self._day is None:
            self._day = day
        elif day != self._day:
            self._day = day
            for st in self._st.values():
                st["today_s"] = 0.0
                st["sessions"] = 0

    def _session_s(self, st: dict[str, Any], ts: float) -> float:
        if st["since"] is None:
            return 0.0
        return max(0.0, min(st["last_seen"], ts) - st["since"])

    # -- frame processing --------------------------------------------------------

    def on_frame(self, ts: float, detections: list[Detection]) -> None:
        self._roll_day(ts)
        self._present_now = len(detections)
        anchors = [self._anchor(d) for d in detections]

        for name, poly in self.desks.items():
            st = self._st[name]
            occupied_now = any(point_in_polygon(a, poly) for a in anchors)
            if occupied_now:
                st["last_seen"] = ts
                if st["first"] is None:
                    st["first"] = ts
                if st["since"] is None and ts - st["first"] >= self.sustain_s:
                    st["since"] = st["first"]
                    self.emit(ts, "desk_occupied", {"desk": name})
            else:
                if st["since"] is not None:
                    if ts - st["last_seen"] >= self.empty_grace_s:
                        self._close_session(name, ts)
                elif st["first"] is not None:
                    st["first"] = None  # blip below sustain

        if self._summary_at is None:
            self._summary_at = ts + self.summary_every_s
        elif ts >= self._summary_at:
            self.emit(ts, "desk_summary", self._summary(ts))
            self._summary_at = ts + self.summary_every_s

    def _close_session(self, name: str, ts: float) -> None:
        st = self._st[name]
        dur = st["last_seen"] - st["since"]
        st["today_s"] += dur
        st["sessions"] += 1
        st["first"] = st["since"] = None
        self.emit(ts, "desk_vacated", {"desk": name, "session_s": round(dur, 1)})

    # -- reporting ---------------------------------------------------------------

    def _summary(self, ts: float) -> dict[str, Any]:
        per_desk = {}
        occupied = working = 0
        for name, st in self._st.items():
            sess = self._session_s(st, ts)
            occ = st["since"] is not None
            work = occ and sess >= self.working_after_s
            occupied += occ
            working += work
            per_desk[name] = {
                "occupied": occ,
                "working": work,
                "session_s": round(sess, 1),
                "today_s": round(st["today_s"] + sess, 1),
                "sessions": st["sessions"] + (1 if occ else 0),
            }
        return {
            "present": self._present_now,
            "desks": len(self.desks),
            "occupied": occupied,
            "working": working,
            "per_desk": per_desk,
        }

    def live_state(self) -> dict[str, Any]:
        if not self.desks:
            return {}
        return self._summary(time.time())

    # -- persistence ---------------------------------------------------------------

    def snapshot_state(self) -> dict[str, Any]:
        return {
            "day": self._day,
            "desks": {n: {"today_s": st["today_s"], "sessions": st["sessions"]}
                      for n, st in self._st.items()},
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self._day = state.get("day", self._day)
        for name, saved in state.get("desks", {}).items():
            if name in self._st:
                self._st[name]["today_s"] = float(saved.get("today_s", 0.0))
                self._st[name]["sessions"] = int(saved.get("sessions", 0))
