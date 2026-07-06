"""Live N-camera benchmark for capacity/pricing decisions.

Runs the REAL pipeline against N identical RTSP feeds (via the local relay), then
samples steady-state metrics for a window and prints a per-feed + aggregate report:
per-camera capture FPS and detection FPS, GPU util, NVDEC decoder util, VRAM, CPU,
inference ms, and a rough end-to-end capacity verdict.

  python scripts/benchmark_live.py [n_cameras] [seconds] [rtsp_url]

Defaults: 15 cameras, 60s, rtsp://127.0.0.1:8554/live
"""
from __future__ import annotations

import statistics
import subprocess
import sys
import time

from src.config import (ApiConfig, CameraConfig, CaptureConfig, ModelConfig,
                        PipelineConfig, RedisConfig, Settings)
from src.pipeline import Pipeline


def nv(query: str) -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            text=True).strip().splitlines()[0]
        return float(out.replace("%", "").strip())
    except Exception:
        return -1.0


def cpu_percent(interval: float = 0.5) -> float:
    def snap():
        with open("/proc/stat") as f:
            p = f.readline().split()[1:8]
        v = list(map(int, p))
        idle = v[3] + v[4]
        return sum(v), idle
    t1, i1 = snap(); time.sleep(interval); t2, i2 = snap()
    dt, di = t2 - t1, i2 - i1
    return 0.0 if dt == 0 else round(100.0 * (1 - di / dt), 1)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    url = sys.argv[3] if len(sys.argv) > 3 else "rtsp://127.0.0.1:8554/live"

    cams = [CameraConfig(id=f"cam{i:02d}", url=url, det_interval=3,
                         motion_gate=False, logic=["headcount"], enabled=True)
            for i in range(1, n + 1)]
    settings = Settings(
        model=ModelConfig(weights="models/yolo26n.pt", engine="models/yolo26n.engine",
                          imgsz=640, conf=0.35, classes=[0, 24, 26, 28, 63, 67], device="cuda:0"),
        pipeline=PipelineConfig(default_det_interval=3, loop_target_fps=30),
        capture=CaptureConfig(backend="gstreamer", rtsp_transport="tcp"),
        api=ApiConfig(), redis=RedisConfig(enabled=False), cameras=cams)

    print(f"Starting {n} feeds from {url} … (warmup 15s, sample {secs}s)")
    p = Pipeline(settings)
    p.start()
    time.sleep(15)  # let all cameras connect + engine warm up

    # snapshot frames_read per camera at start/end → capture fps per feed
    def frames_map():
        st = p.status()["cameras"]
        return {c: st.get(c, {}).get("frames_read", 0) for c in p.camera_ids()}

    f0 = frames_map(); t0 = time.monotonic()
    gpu, dec, vram, infer, loop, cpu = [], [], [], [], [], []
    end = time.monotonic() + secs
    while time.monotonic() < end:
        s = p.status()
        gpu.append(nv("utilization.gpu"))
        dec.append(nv("utilization.decoder"))
        vram.append(nv("memory.used"))
        loop.append(s.get("loop_fps", 0))
        if s["stage_ms"].get("inference"):
            infer.append(s["stage_ms"]["inference"])
        cpu.append(cpu_percent(0.4))
        time.sleep(2)
    dt = time.monotonic() - t0
    f1 = frames_map()

    st = p.status()["cameras"]
    connected = [c for c in p.camera_ids() if st.get(c, {}).get("connected")]
    cap_fps = {c: round((f1[c] - f0[c]) / dt, 1) for c in p.camera_ids()}
    det_fps = {c: st.get(c, {}).get("detect_fps", 0) for c in p.camera_ids()}
    p.stop()

    def avg(x): return round(statistics.mean(x), 1) if x else 0.0
    def pk(x): return round(max(x), 1) if x else 0.0
    conn_cap = [cap_fps[c] for c in connected] or [0]
    conn_det = [det_fps[c] for c in connected] or [0]

    print("\n" + "=" * 66)
    print(f"  {n}-CAMERA LIVE BENCHMARK  ({len(connected)}/{n} connected)")
    print("=" * 66)
    print(f"  {'camera':<8} {'capture_fps':>12} {'detect_fps':>11} {'connected':>10}")
    for c in p.camera_ids():
        print(f"  {c:<8} {cap_fps[c]:>12} {det_fps[c]:>11} {str(st.get(c,{}).get('connected', False)):>10}")
    print("-" * 66)
    print(f"  per-feed capture fps : avg {avg(conn_cap):>6}  min {round(min(conn_cap),1):>6}  max {pk(conn_cap):>6}")
    print(f"  per-feed detect  fps : avg {avg(conn_det):>6}  min {round(min(conn_det),1):>6}  max {pk(conn_det):>6}")
    print(f"  GPU util  %          : avg {avg(gpu):>6}  peak {pk(gpu):>6}")
    print(f"  NVDEC decoder util % : avg {avg(dec):>6}  peak {pk(dec):>6}")
    print(f"  VRAM used MB         : avg {avg(vram):>6}  peak {pk(vram):>6}  / 8192")
    print(f"  inference ms (batch) : avg {avg(infer):>6}  peak {pk(infer):>6}")
    print(f"  loop fps             : avg {avg(loop):>6}")
    print(f"  CPU util %           : avg {avg(cpu):>6}  peak {pk(cpu):>6}")
    print("=" * 66)
    # crude capacity projection for pricing
    if avg(gpu) > 0 and len(connected):
        head_gpu = 95.0 / max(avg(gpu), 1) * len(connected)
        head_vram = 7000.0 / max(avg(vram), 1) * len(connected)
        print(f"  capacity projection  : ~{int(min(head_gpu, head_vram))} cameras/GPU "
              f"at this fps (limited by {'GPU' if head_gpu<head_vram else 'VRAM'})")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
