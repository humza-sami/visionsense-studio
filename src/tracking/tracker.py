"""Per-camera ByteTrack (§5.7) via the `supervision` library. One tracker instance
per camera so IDs are independent across streams. Converts raw Detections into
tracked Tracks (with stable IDs) that business logic reasons about over time.

Because we detect every Nth frame, the tracker carries IDs across the gaps. On
non-detection frames the orchestrator simply reuses the last tracks for display.
"""
from __future__ import annotations

import numpy as np
import supervision as sv

from src.types import Detection, Track


class CameraTracker:
    def __init__(self) -> None:
        self.bt = sv.ByteTrack()
        self.last: list[Track] = []

    def update(self, detections: list[Detection]) -> list[Track]:
        if detections:
            xyxy = np.array([d.xyxy for d in detections], dtype=float)
            conf = np.array([d.conf for d in detections], dtype=float)
            cls = np.array([d.cls_id for d in detections], dtype=int)
        else:
            xyxy = np.empty((0, 4), dtype=float)
            conf = np.empty((0,), dtype=float)
            cls = np.empty((0,), dtype=int)

        sv_det = sv.Detections(xyxy=xyxy, confidence=conf, class_id=cls)
        tracked = self.bt.update_with_detections(sv_det)

        names = {d.cls_id: d.cls_name for d in detections}
        out: list[Track] = []
        for i in range(len(tracked)):
            tid = tracked.tracker_id[i]
            if tid is None:
                continue
            cid = int(tracked.class_id[i])
            out.append(
                Track(
                    track_id=int(tid),
                    xyxy=tuple(float(v) for v in tracked.xyxy[i]),
                    conf=float(tracked.confidence[i]) if tracked.confidence is not None else 0.0,
                    cls_id=cid,
                    cls_name=names.get(cid, str(cid)),
                )
            )
        self.last = out
        return out
