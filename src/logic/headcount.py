"""Headcount: count unique active person track IDs (optionally inside zones).
Emits an event only when the count changes, to avoid spamming the stream.
"""
from __future__ import annotations

from src.events.schemas import Event
from src.logic.base import PERSON, LogicHandler
from src.types import Track
from src.zones import in_any


class HeadcountHandler(LogicHandler):
    name = "headcount"

    def __init__(self, cam, zones) -> None:
        super().__init__(cam, zones)
        self._last_count = -1

    def process(self, tracks: list[Track]) -> list[Event]:
        persons = [t for t in tracks if t.cls_id == PERSON]
        if self.zones:
            persons = [t for t in persons if in_any(t.bottom_center, self.zones)]
        count = len({t.track_id for t in persons})

        if count != self._last_count:
            self._last_count = count
            return [Event(cam=self.cam.id, type="headcount",
                          payload={"count": count,
                                   "ids": sorted({t.track_id for t in persons})})]
        return []
