"""Generate a synthetic test video (people + motion) for headless verification.

A real CCTV box has RTSP cameras and a real GPU; a fresh dev/CI box often has
neither a webcam nor cameras configured. This writes a short looping clip with
people in it so the full pipeline (decode → detect → ByteTrack → logic → events)
can be exercised end-to-end without any camera hardware.

  python scripts/make_test_video.py [out_path] [n_frames]

Then point a camera at it in config/cameras.yaml:
  - id: cam01
    url: test_assets/people.mp4
    enabled: true
"""
from __future__ import annotations

import os
import sys
import urllib.request

import cv2
import numpy as np

SAMPLE_URL = "https://ultralytics.com/images/bus.jpg"  # has several people


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "test_assets/people.mp4"
    n_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    cache = "/tmp/_vss_people.jpg"
    if not os.path.exists(cache):
        print(f"Downloading sample image → {cache}")
        urllib.request.urlretrieve(SAMPLE_URL, cache)
    img = cv2.resize(cv2.imread(cache), (1280, 720))
    h, w = img.shape[:2]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(out_path, fourcc, 25.0, (w, h))
    if not vw.isOpened():  # mp4 codec unavailable → fall back to MJPG/AVI
        out_path = os.path.splitext(out_path)[0] + ".avi"
        vw = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (w, h))

    # Gentle horizontal pan so there is motion for the tracker / motion gate.
    for i in range(n_frames):
        dx = int(30 * np.sin(i / 15.0))
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        vw.write(cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT))
    vw.release()
    print(f"Wrote {out_path}  ({os.path.getsize(out_path)} bytes, {n_frames} frames)")


if __name__ == "__main__":
    main()
