"""Camera-count scale test — answers "can we run 100 cameras at 2 fps detection each?"

One shared nano detector, N cameras, 2 fps detection per camera, batches CHUNKED to
the engine profile (16) exactly like the production pipeline does. Ladder the camera
count until something breaks; the CSV shows which resource (VRAM / CPU / NVDEC) hit
the wall. Capture stays 25 fps per camera throughout — the point of the test is that
capture fps and detection fps are independent.

  python scripts/benchmark_scale.py [all|N] [seconds] [relay_url] [csv]
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.getcwd())

LADDER = [28, 32, 36, 40]
DET_FPS = 2.0
CHUNK = 16  # engine batch profile — chunk like src/pipeline.py does


def run_scale(n: int, secs: int, url: str, csv_path: str) -> None:
    from benchmark_mixed import COLUMNS, cpu_pct, nv, ram_mb
    from src.capture.frame_buffer import LatestFrameBuffer
    from src.capture.rtsp_worker import CameraWorker
    from src.config import CameraConfig, CaptureConfig, ModelConfig
    from src.inference.engine import Detector

    cap_cfg = CaptureConfig(backend="gstreamer", rtsp_transport="tcp", codec="h265")
    det = Detector(ModelConfig(weights="models/yolo26n.pt", engine="models/yolo26n.engine",
                               imgsz=640, conf=0.25, iou=0.45, device="cuda:0",
                               classes=None, max_batch=CHUNK))
    buf = LatestFrameBuffer()
    workers = []
    cams = []
    for i in range(n):
        cid = f"cam{i:03d}"
        cams.append(cid)
        w = CameraWorker(CameraConfig(id=cid, url=url, enabled=True), buf, cap_cfg)
        w.start()
        workers.append(w)
    print(f"[scale_{n}] warming up 15s")
    time.sleep(15)

    gpu = []; dec = []; vram = []; cpu = []
    ticks = 0; frames_seen = []
    t0 = time.monotonic(); end = t0 + secs; last = 0.0; nextsample = t0
    while time.monotonic() < end:
        now = time.monotonic()
        if now - last >= 1.0 / DET_FPS:
            frames = [f for f in (buf.get(c) for c in cams) if f is not None]
            for i in range(0, len(frames), CHUNK):
                det.detect_batch(frames[i:i + CHUNK])
            last = now; ticks += 1; frames_seen.append(len(frames))
        if now >= nextsample:
            gpu.append(nv("utilization.gpu")); dec.append(nv("utilization.decoder"))
            vram.append(nv("memory.used")); cpu.append(cpu_pct(0.3)); nextsample = now + 1.5
        time.sleep(0.002)
    dur = time.monotonic() - t0
    for w in workers:
        w.stop()

    a = lambda x: round(statistics.mean(x), 1) if x else 0.0
    pk = lambda x: round(max(x), 1) if x else 0.0
    achieved = round(ticks / dur, 2)
    connected = round(statistics.mean(frames_seen), 1) if frames_seen else 0
    row = {"scenario": f"scale_n{n}_2fps", "total_cameras": n,
           "groups": json.dumps([{"label": "nano2fps", "model": "yolo26n", "cams": n,
                                  "target_fps": DET_FPS, "achieved_fps": achieved,
                                  "avg_batch": connected}]),
           "gpu_util_avg": a(gpu), "gpu_util_peak": pk(gpu), "nvdec_util_avg": a(dec),
           "vram_used_MB_peak": pk(vram), "vram_free_MB": round(nv("memory.total") - pk(vram)),
           "cpu_util_avg": a(cpu), "ram_used_MB": ram_mb(),
           "predicted_infer_ms_per_s": round(n * DET_FPS * 3.7), "notes": ""}
    new = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"[scale_{n}] connected {connected}/{n} · det {achieved}/{DET_FPS}fps · GPU {a(gpu)}%/{pk(gpu)}pk "
          f"· NVDEC {a(dec)}% · VRAM {pk(vram)}MB · CPU {a(cpu)}%")


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    url = sys.argv[3] if len(sys.argv) > 3 else "rtsp://127.0.0.1:8554/live"
    csv_path = sys.argv[4] if len(sys.argv) > 4 else "benchmark_scale.csv"

    if which != "all":
        from benchmark_verticals import append_failure_row
        n = int(which)
        try:
            run_scale(n, secs, url, csv_path)
        except Exception as e:
            append_failure_row(csv_path, f"scale_n{n}_2fps", [("nano2fps", n, "n", 25, DET_FPS)],
                               f"{type(e).__name__}: {e}")
            print(f"[scale_{n}] FAILED: {e}")
        sys.stdout.flush()
        os._exit(0)

    if os.path.exists(csv_path):
        os.remove(csv_path)
    for n in LADDER:
        subprocess.run([sys.executable, __file__, str(n), str(secs), url, csv_path],
                       env={**os.environ, "PYTHONPATH": os.getcwd()})
        time.sleep(4)
    print(f"\nscale ladder CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
