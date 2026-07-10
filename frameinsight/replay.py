"""Replay recorded detections through the kernels — no GPU, no cameras.

This is how kernels are developed and regression-tested (architecture doc §9,
Testing): record detection metadata once, then replay it through rule code on
any laptop. The replay file is JSONL, one **frame** per line::

    {"cam": "gate", "ts": 12.5, "objects": [
        {"id": 3, "cls": "person", "conf": 0.82, "bbox": [0.40, 0.30, 0.05, 0.20]}
    ]}

``ts`` may be relative seconds (replay rebases to now) or epoch seconds.
``bbox`` is (x, y, w, h) normalized to [0,1] — same convention as live.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator

from .dispatch import Dispatcher
from .siteconfig import SiteConfig
from .sinks import EventSink
from .types import Detection


def read_frames(path: str | Path) -> Iterator[tuple[str, float, list[dict]]]:
    with open(path) as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rec = json.loads(line)
                yield rec["cam"], float(rec["ts"]), rec.get("objects", [])
            except (json.JSONDecodeError, KeyError) as e:
                raise ValueError(f"{path}:{lineno}: bad frame record ({e})") from e


def replay(
    site: SiteConfig,
    sink: EventSink,
    events_path: str | Path,
    *,
    speed: float = 0.0,
) -> int:
    """Feed a recording through the site's rules. ``speed=0`` runs as fast as
    possible (tests/CI); ``speed=1`` paces in real time, ``2`` twice as fast.
    Returns the number of frames replayed."""
    dispatcher = Dispatcher(site, sink, snapshot_every_s=float("inf"))
    frames = 0
    t0: float | None = None
    base = time.time()
    wall0 = time.monotonic()
    for cam, ts, objects in read_frames(events_path):
        if t0 is None:
            t0 = ts
        rel = ts - t0
        if speed > 0:
            lag = rel / speed - (time.monotonic() - wall0)
            if lag > 0:
                time.sleep(lag)
        # Rebase relative timestamps onto the wall clock so sink rows are sane.
        abs_ts = ts if ts > 1e9 else base + rel
        dets = [
            Detection(
                cam_id=cam,
                ts=abs_ts,
                track_id=int(o["id"]),
                class_name=str(o.get("cls", "person")),
                confidence=float(o.get("conf", 1.0)),
                bbox=tuple(float(v) for v in o["bbox"]),
            )
            for o in objects
        ]
        dispatcher.process_frame(cam, abs_ts, dets)
        frames += 1
    dispatcher.close()
    return frames
