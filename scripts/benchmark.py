"""Throughput benchmark (§7). Measures batched inference FPS at increasing batch
sizes using the configured model + device. Run on the target box to validate the
8-15 FPS/cam @ 15 cams target.

  python scripts/benchmark.py [max_batch] [iters]
"""
from __future__ import annotations

import sys
import time

import numpy as np

from src.config import load_settings
from src.inference.engine import Detector
from src.monitoring.metrics import gpu_stats


def main() -> None:
    max_batch = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    settings = load_settings()
    det = Detector(settings.model)
    imgsz = settings.model.imgsz
    print(f"device={det.device} model={det.model_path} imgsz={imgsz}\n")

    dummy = (np.random.rand(720, 1280, 3) * 255).astype(np.uint8)

    print(f"{'batch':>6} {'fps_total':>10} {'fps/cam':>9} {'ms/iter':>9} {'vram_mb':>9}")
    for b in sorted({1, 2, 4, 8, max_batch}):
        if b > max_batch:
            continue
        frames = [dummy] * b
        det.detect_batch(frames)  # warmup
        t0 = time.monotonic()
        for _ in range(iters):
            det.detect_batch(frames)
        dt = time.monotonic() - t0
        fps_total = (iters * b) / dt
        gs = gpu_stats()
        vram = gs.get("vram_used_mb", "-")
        print(f"{b:>6} {fps_total:>10.1f} {fps_total / b:>9.1f} "
              f"{dt / iters * 1000:>9.1f} {str(vram):>9}")


if __name__ == "__main__":
    main()
