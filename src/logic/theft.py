"""Theft heuristic: a carryable object (phone/bag/laptop/suitcase) that was being
tracked near a person disappears, or crosses an exit zone → raise a suspicion
event. This is where track IDs matter: we reason about objects OVER TIME.

Deliberately conservative/explainable rather than ML-magical — tune thresholds
against real footage. Never motion-gate cameras running this handler.
"""
from __future__ import annotations

import time

from src.events.schemas import Event
from src.logic.base import CARRY_ITEMS, PERSON, LogicHandler
from src.types import Track
from src.zones import in_any


class TheftHandler(LogicHandler):
    name = "theft"

    NEAR_PX = 150          # object considered "held" if within this of a person
    VANISH_AFTER_S = 2.0   # object gone this long after being near a person → alert
    COOLDOWN_S = 30.0      # don't re-alert on the same object id

    def __init__(self, cam, zones) -> None:
        super().__init__(cam, zones)
        # object_id -> {last_seen, was_near_person, last_xyxy}
        self._objects: dict[int, dict] = {}
        self._alerted: dict[int, float] = {}

    def process(self, tracks: list[Track]) -> list[Event]:
        now = time.time()
        events: list[Event] = []
        persons = [t for t in tracks if t.cls_id == PERSON]
        items = [t for t in tracks if t.cls_id in CARRY_ITEMS]
        seen_ids = set()

        for obj in items:
            seen_ids.add(obj.track_id)
            near = self._near_person(obj, persons)
            rec = self._objects.setdefault(
                obj.track_id, {"was_near_person": False})
            rec["last_seen"] = now
            rec["last_xyxy"] = obj.xyxy
            rec["cls_name"] = obj.cls_name
            rec["was_near_person"] = rec["was_near_person"] or near

            # Crossed into an exit zone → immediate suspicion.
            if self.zones and in_any(obj.bottom_center, self.zones, zone_type="exit"):
                if self._can_alert(obj.track_id, now):
                    events.append(self._alert(obj.track_id, obj.cls_name,
                                              "object_in_exit_zone", now))

        # Objects that were near a person and have now vanished.
        for oid, rec in list(self._objects.items()):
            if oid in seen_ids:
                continue
            gone_for = now - rec.get("last_seen", now)
            if rec.get("was_near_person") and gone_for >= self.VANISH_AFTER_S:
                if self._can_alert(oid, now):
                    events.append(self._alert(oid, rec.get("cls_name", "item"),
                                              "object_vanished_near_person", now))
            if gone_for > 60:
                self._objects.pop(oid, None)

        return events

    def _near_person(self, obj: Track, persons: list[Track]) -> bool:
        ox, oy = obj.center
        for p in persons:
            px, py = p.center
            if ((ox - px) ** 2 + (oy - py) ** 2) ** 0.5 <= self.NEAR_PX:
                return True
        return False

    def _can_alert(self, oid: int, now: float) -> bool:
        return (now - self._alerted.get(oid, 0)) >= self.COOLDOWN_S

    def _alert(self, oid: int, cls_name: str, reason: str, now: float) -> Event:
        self._alerted[oid] = now
        return Event(cam=self.cam.id, type="theft_suspected",
                     payload={"object_id": oid, "object": cls_name, "reason": reason})
