"""Desk activity: a person present in a desk zone over a sustained window counts as
'active'. Edge-triggered: emits when activity starts and when it ends.

This is a simplified presence-based heuristic. To make it motion-sensitive, feed
the motion-gate signal for the desk ROI in addition to person presence.
"""
from __future__ import annotations

import time

from src.events.schemas import Event
from src.logic.base import PERSON, LogicHandler
from src.types import Track
from src.zones import in_any


class DeskActivityHandler(LogicHandler):
    name = "desk_activity"

    ACTIVE_AFTER_S = 3.0   # presence must persist this long to be "active"
    IDLE_AFTER_S = 10.0    # absence this long ends the activity

    def __init__(self, cam, zones) -> None:
        super().__init__(cam, zones)
        self._present_since: float | None = None
        self._absent_since: float | None = None
        self._active = False

    def process(self, tracks: list[Track]) -> list[Event]:
        now = time.time()
        persons = [t for t in tracks if t.cls_id == PERSON]
        if self.zones:
            persons = [t for t in persons if in_any(t.bottom_center, self.zones)]
        present = len(persons) > 0
        events: list[Event] = []

        if present:
            self._absent_since = None
            if self._present_since is None:
                self._present_since = now
            if not self._active and (now - self._present_since) >= self.ACTIVE_AFTER_S:
                self._active = True
                events.append(Event(cam=self.cam.id, type="desk_active",
                                    payload={"state": "active", "persons": len(persons)}))
        else:
            self._present_since = None
            if self._absent_since is None:
                self._absent_since = now
            if self._active and (now - self._absent_since) >= self.IDLE_AFTER_S:
                self._active = False
                events.append(Event(cam=self.cam.id, type="desk_active",
                                    payload={"state": "idle"}))
        return events
