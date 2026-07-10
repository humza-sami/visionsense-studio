"""Shared test helpers: a capturing sink and detection factories."""

from __future__ import annotations

from frameinsight.sinks import EventSink
from frameinsight.types import Detection, Event
from frameinsight.zones import Zone


class Capture(EventSink):
    def __init__(self) -> None:
        self.events: list[Event] = []

    def write(self, event: Event) -> None:
        self.events.append(event)

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]

    def of_kind(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]


def det(ts: float, tid: int, x: float, y: float, *, w: float = 0.05,
        h: float = 0.2, cls: str = "person", conf: float = 0.9,
        cam: str = "cam1") -> Detection:
    """Detection whose FOOT anchor lands at (x + w/2, y + h)."""
    return Detection(cam_id=cam, ts=ts, track_id=tid, class_name=cls,
                     confidence=conf, bbox=(x, y, w, h))


def det_at_foot(ts: float, tid: int, fx: float, fy: float, **kw) -> Detection:
    """Detection placed so its foot anchor is exactly (fx, fy)."""
    w = kw.pop("w", 0.05)
    h = kw.pop("h", 0.2)
    return det(ts, tid, fx - w / 2, fy - h, w=w, h=h, **kw)


def make_rule(cls, zone: Zone | None = None, *, capture: Capture | None = None, **params):
    cap = capture or Capture()
    rule = cls(site="test-site", cam_id="cam1", name=f"test_{cls.KIND}",
               emit=cap.write, zone=zone, **params)
    return rule, cap


SQUARE = Zone(name="square", type="polygon",
              points=((0.3, 0.3), (0.7, 0.3), (0.7, 0.7), (0.3, 0.7)))

# Horizontal gate line at y=0.5, directed left→right: crossing downward
# (increasing y) lands on the +1 side → label_left.
GATE = Zone(name="gate", type="line", points=((0.1, 0.5), (0.9, 0.5)))
