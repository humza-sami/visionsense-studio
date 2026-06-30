"""End-to-end smoke test — no camera hardware, no GPU required.

Runs the REAL pipeline (capture → buffer → motion gate → batch → detect →
ByteTrack → logic → events) against a synthetic video for a few seconds and
asserts that frames were read, detections happened, IDs were tracked, and at
least one annotated preview frame was produced. Exits non-zero on failure so it
is usable in CI or as a post-deploy check.

  python scripts/make_test_video.py        # once, to create the clip
  python scripts/smoke_test.py             # then run this

Works on the dev box (CPU/.pt) and on the prod box (CUDA/.engine) unchanged — it
just uses whatever device select_device() resolves to.
"""
from __future__ import annotations

import os
import sys
import time

from src.config import (ApiConfig, CameraConfig, CaptureConfig, ModelConfig,
                        PipelineConfig, RedisConfig, Settings)
from src.pipeline import Pipeline

VIDEO = os.environ.get("SMOKE_VIDEO", "test_assets/people.mp4")
RUN_SECONDS = float(os.environ.get("SMOKE_SECONDS", "9"))


def main() -> int:
    if not os.path.exists(VIDEO):
        print(f"FAIL: {VIDEO} missing — run: python scripts/make_test_video.py")
        return 2

    settings = Settings(
        model=ModelConfig(weights="models/yolo26n.pt", imgsz=640, conf=0.35,
                          classes=[0, 24, 26, 28, 63, 67], device="auto"),
        pipeline=PipelineConfig(default_det_interval=2, loop_target_fps=15),
        capture=CaptureConfig(backend="opencv"),
        api=ApiConfig(),
        redis=RedisConfig(enabled=False),
        cameras=[CameraConfig(id="cam01", url=VIDEO, det_interval=2,
                              motion_gate=False, logic=["headcount", "theft"],
                              enabled=True)],
    )

    p = Pipeline(settings)
    p.start()
    time.sleep(RUN_SECONDS)
    st = p.status()
    annotated = p.get_annotated("cam01")
    events = p.events.recent(50)
    p.stop()

    cam = st["cameras"].get("cam01", {})
    frames = cam.get("frames_read", 0)
    detect_fps = cam.get("detect_fps", 0)
    objects = cam.get("objects", 0)

    print(f"device      : {p.detector.device}")
    print(f"frames_read : {frames}")
    print(f"detect_fps  : {detect_fps}")
    print(f"objects     : {objects}")
    print(f"inference_ms: {st['stage_ms'].get('inference')}")
    print(f"annotated   : {None if annotated is None else annotated.shape}")
    print(f"events      : {len(events)}  e.g. {events[0] if events else None}")
    print(f"gpu         : {st['gpu']}")

    checks = {
        "frames were read": frames > 0,
        "detection ran": detect_fps > 0,
        "objects detected": objects > 0,
        "annotated frame produced": annotated is not None,
        "at least one event emitted": len(events) > 0,
    }
    ok = True
    print("\n--- checks ---")
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed

    print("\nSMOKE TEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
