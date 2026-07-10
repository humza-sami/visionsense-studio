"""Core data types shared by the GPU runtime, rule kernels, and sinks.

Everything downstream of the pipeline speaks these two types only. Kernels never
see GStreamer/DeepStream objects, which is what keeps them testable off-GPU.

Coordinate convention: bounding boxes are **normalized to [0, 1]** in the
streammux (pipeline) frame — ``(x, y, w, h)`` with the origin at the top-left.
Zones are stored normalized too, so rules are resolution-independent.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

# DeepStream reports this object_id when the tracker has not (yet) assigned one.
UNTRACKED_ID = 0xFFFFFFFFFFFFFFFF


@dataclass(frozen=True)
class Detection:
    """One tracked object in one frame of one camera."""

    cam_id: str
    ts: float                      # wall-clock epoch seconds
    track_id: int                  # persistent per-camera tracker ID
    class_name: str                # e.g. "person"
    confidence: float
    bbox: tuple[float, float, float, float]  # (x, y, w, h), normalized 0..1

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return (x + w / 2.0, y + h / 2.0)

    @property
    def foot(self) -> tuple[float, float]:
        """Bottom-center anchor — where the object touches the floor plane.

        Floor zones must test this point, not the box center: a person's box
        center crosses a painted floor line long before they do.
        """
        x, y, w, h = self.bbox
        return (x + w / 2.0, y + h)

    @property
    def is_tracked(self) -> bool:
        return self.track_id != UNTRACKED_ID


@dataclass
class Event:
    """One business fact produced by a rule kernel.

    ``kind`` is the machine name ("line_crossed", "dwell_completed", ...);
    ``data`` carries the kind-specific payload. Sinks serialize this as-is, so
    keep ``data`` JSON-safe.
    """

    site: str
    cam_id: str
    rule: str                      # rule instance name from site.yaml
    kind: str
    severity: str = "info"         # info | alert
    ts: float = field(default_factory=time.time)
    track_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": round(self.ts, 3),
            "site": self.site,
            "cam_id": self.cam_id,
            "rule": self.rule,
            "kind": self.kind,
            "severity": self.severity,
            "track_id": self.track_id,
            "data": self.data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))
