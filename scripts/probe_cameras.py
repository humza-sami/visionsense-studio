"""Probe every camera in config/cameras.yaml: connect, grab a frame, report
resolution + which subtype works. Run this on the box that can actually reach the
NVR before launching the full pipeline.

  python scripts/probe_cameras.py            # probe enabled cameras as configured
  python scripts/probe_cameras.py --all      # also try the other subtype per camera

Exit code is non-zero if any enabled camera fails to deliver a frame.
"""
from __future__ import annotations

import os
import re
import sys
import time

import cv2

from src.config import enabled_cameras, load_settings

# TCP + sane timeouts so a dead camera fails fast instead of hanging forever.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;6000000"
)
TIMEOUT_S = 8


def _redact(url: str) -> str:
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:****@", url)


def _try(url: str) -> tuple[bool, object]:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    t0 = time.time()
    ok, frame = False, None
    while time.time() - t0 < TIMEOUT_S:
        ok, frame = cap.read()
        if ok and frame is not None:
            break
    shape = None if frame is None else frame.shape
    cap.release()
    return (ok and frame is not None), shape


def main() -> int:
    also_all = "--all" in sys.argv
    cams = enabled_cameras(load_settings())
    print(f"Probing {len(cams)} enabled camera(s)  (timeout {TIMEOUT_S}s each)\n")
    failures = 0
    for c in cams:
        ok, shape = _try(str(c.url))
        status = f"OK   {shape[1]}x{shape[0]}" if ok else "FAIL (no frame / unreachable)"
        print(f"  {c.id:>6}  {status:36}  {_redact(str(c.url))}")
        if not ok:
            failures += 1
            if also_all and "subtype=" in str(c.url):
                alt = re.sub(r"subtype=\d", lambda m: "subtype=0" if m.group(0).endswith("1") else "subtype=1", str(c.url))
                ok2, shape2 = _try(alt)
                if ok2:
                    print(f"         ↳ alt works: {shape2[1]}x{shape2[0]}  {_redact(alt)}")

    print(f"\n{len(cams) - failures}/{len(cams)} cameras delivered a frame.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
