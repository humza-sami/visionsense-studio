"""Comprehensive capacity/perf benchmark → CSV (for GPU/model comparison & pricing).

Runs the REAL pipeline against N identical RTSP feeds (via the local relay), samples
steady-state metrics, and appends one fully-detailed row to a CSV. A separate process
is used per camera count (clean VRAM measurement each time).

  # one run:
  python scripts/benchmark_csv.py run  N SECS DET_INTERVAL IMGSZ CONF URL CSV [WEIGHTS] [ENGINE] [MODEL_NAME]
  # sweep (spawns a clean process per count):
  python scripts/benchmark_csv.py sweep "5,10,15,20,25,30" SECS DET_INTERVAL IMGSZ CONF URL CSV [WEIGHTS] [ENGINE] [MODEL_NAME]

Fair-test defaults: uncapped loop fps, all 80 classes, no camera cap.
"""
from __future__ import annotations

import csv
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime

CSV_DEFAULT = "benchmark_results.csv"
COLUMNS = [
    "test_id", "datetime", "gpu", "vram_total_MB",
    "model", "precision", "runtime", "weights_MB", "engine_MB",
    "imgsz", "classes", "conf", "det_interval",
    "src_resolution", "src_codec", "src_fps",
    "cameras_requested", "cameras_connected",
    "capture_fps_per_feed", "detect_fps_per_feed", "tracking_fps_per_feed",
    "loop_fps", "inference_ms_avg", "inference_ms_peak",
    "gpu_util_avg", "gpu_util_peak", "nvdec_util_avg", "nvdec_util_peak",
    "vram_used_MB_avg", "vram_used_MB_peak", "vram_free_MB",
    "cpu_util_avg", "cpu_util_peak", "ram_used_MB",
    "detection_accuracy_manual", "notes",
]


def nv(query: str) -> float:
    try:
        return float(subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            text=True).strip().splitlines()[0].replace("%", "").strip())
    except Exception:
        return -1.0


def nv_str(query: str) -> str:
    try:
        return subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"],
            text=True).strip().splitlines()[0].strip()
    except Exception:
        return "?"


def cpu_percent(interval: float = 0.4) -> float:
    def snap():
        v = list(map(int, open("/proc/stat").readline().split()[1:8]))
        return sum(v), v[3] + v[4]
    t1, i1 = snap(); time.sleep(interval); t2, i2 = snap()
    dt, di = t2 - t1, i2 - i1
    return 0.0 if dt == 0 else round(100.0 * (1 - di / dt), 1)


def ram_used_mb() -> int:
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":"); m[k] = int(v.strip().split()[0])
    return (m["MemTotal"] - m["MemAvailable"]) // 1024


def one_run(n, secs, det_interval, imgsz, conf, url, csv_path,
            weights="models/yolo26n.pt", engine="models/yolo26n.engine",
            model_name=None):
    from src.config import (ApiConfig, CameraConfig, CaptureConfig, ModelConfig,
                            PipelineConfig, RedisConfig, Settings)
    from src.pipeline import Pipeline

    cams = [CameraConfig(id=f"cam{i:02d}", url=url, det_interval=det_interval,
                         motion_gate=False, logic=[], enabled=True)
            for i in range(1, n + 1)]
    settings = Settings(
        model=ModelConfig(weights=weights, engine=engine,
                          imgsz=imgsz, conf=conf, iou=0.45, max_batch=n, device="cuda:0",
                          classes=None),  # ALL classes, no filter
        pipeline=PipelineConfig(default_det_interval=det_interval, loop_target_fps=120),  # uncapped
        capture=CaptureConfig(backend="gstreamer", rtsp_transport="tcp", codec="h265"),
        api=ApiConfig(), redis=RedisConfig(enabled=False), cameras=cams)

    model_name = model_name or os.path.splitext(os.path.basename(weights))[0]
    runtime = "TensorRT" if os.path.exists(engine) else "PyTorch"
    precision = "FP16/TF32 (TensorRT)" if os.path.exists(engine) else "PyTorch"
    print(f"[run] {n} cams · model={model_name} · det_interval={det_interval} · imgsz={imgsz} · conf={conf}")
    p = Pipeline(settings)
    p.start()
    time.sleep(15)  # warmup + connect

    def frames():
        st = p.status()["cameras"]
        return {c: st.get(c, {}).get("frames_read", 0) for c in p.camera_ids()}

    f0 = frames(); t0 = time.monotonic()
    gpu, dec, vram, infer, loop, cpu = [], [], [], [], [], []
    end = time.monotonic() + secs
    while time.monotonic() < end:
        s = p.status()
        gpu.append(nv("utilization.gpu")); dec.append(nv("utilization.decoder"))
        vram.append(nv("memory.used")); loop.append(s.get("loop_fps", 0))
        if s["stage_ms"].get("inference"):
            infer.append(s["stage_ms"]["inference"])
        cpu.append(cpu_percent(0.4)); time.sleep(1.5)
    dt = time.monotonic() - t0
    f1 = frames()
    st = p.status()["cameras"]
    conn = [c for c in p.camera_ids() if st.get(c, {}).get("connected")]
    cap = [round((f1[c] - f0[c]) / dt, 1) for c in conn] or [0]
    det = [st.get(c, {}).get("detect_fps", 0) for c in conn] or [0]
    ram = ram_used_mb()
    p.stop()

    a = lambda x: round(statistics.mean(x), 1) if x else 0.0
    pk = lambda x: round(max(x), 1) if x else 0.0
    vram_total = int(nv("memory.total"))
    row = {
        "test_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "datetime": datetime.now().isoformat(timespec="seconds"),
        "gpu": nv_str("name"), "vram_total_MB": vram_total,
        "model": model_name, "precision": precision, "runtime": runtime,
        "weights_MB": round(os.path.getsize(weights) / 1e6, 1) if os.path.exists(weights) else "",
        "engine_MB": round(os.path.getsize(engine) / 1e6, 1) if os.path.exists(engine) else "",
        "imgsz": imgsz, "classes": "all(80)", "conf": conf, "det_interval": det_interval,
        "src_resolution": "704x576", "src_codec": "H265", "src_fps": 25,
        "cameras_requested": n, "cameras_connected": len(conn),
        "capture_fps_per_feed": a(cap), "detect_fps_per_feed": a(det),
        "tracking_fps_per_feed": a(cap),  # ByteTrack fills to capture rate
        "loop_fps": a(loop), "inference_ms_avg": a(infer), "inference_ms_peak": pk(infer),
        "gpu_util_avg": a(gpu), "gpu_util_peak": pk(gpu),
        "nvdec_util_avg": a(dec), "nvdec_util_peak": pk(dec),
        "vram_used_MB_avg": a(vram), "vram_used_MB_peak": pk(vram),
        "vram_free_MB": round(vram_total - pk(vram)),
        "cpu_util_avg": a(cpu), "cpu_util_peak": pk(cpu), "ram_used_MB": ram,
        "detection_accuracy_manual": "", "notes": "",
    }
    new = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"[run] connected {len(conn)}/{n} · cap {a(cap)}fps · det {a(det)}fps · "
          f"GPU {a(gpu)}% · NVDEC {a(dec)}% · VRAM {pk(vram)}MB · CPU {a(cpu)}% → row appended")
    return len(conn), pk(vram), vram_total


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "sweep"
    if mode == "run":
        n = int(sys.argv[2]); secs = int(sys.argv[3]); di = int(sys.argv[4])
        imgsz = int(sys.argv[5]); conf = float(sys.argv[6])
        url = sys.argv[7]; csv_path = sys.argv[8] if len(sys.argv) > 8 else CSV_DEFAULT
        weights = sys.argv[9] if len(sys.argv) > 9 else "models/yolo26n.pt"
        engine = sys.argv[10] if len(sys.argv) > 10 else "models/yolo26n.engine"
        model_name = sys.argv[11] if len(sys.argv) > 11 else None
        one_run(n, secs, di, imgsz, conf, url, csv_path, weights, engine, model_name)
        sys.stdout.flush()
        # GStreamer/OpenCV abort noisily at interpreter exit ("terminate called…").
        # The CSV row is already written, so exit hard-cleanly to avoid a false failure.
        os._exit(0)

    # sweep: one clean subprocess per count
    counts = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "5,10,15,20,25,30").split(",")]
    secs = sys.argv[3] if len(sys.argv) > 3 else "30"
    di = sys.argv[4] if len(sys.argv) > 4 else "1"
    imgsz = sys.argv[5] if len(sys.argv) > 5 else "640"
    conf = sys.argv[6] if len(sys.argv) > 6 else "0.25"
    url = sys.argv[7] if len(sys.argv) > 7 else "rtsp://127.0.0.1:8554/live"
    csv_path = sys.argv[8] if len(sys.argv) > 8 else CSV_DEFAULT
    weights = sys.argv[9] if len(sys.argv) > 9 else "models/yolo26n.pt"
    engine = sys.argv[10] if len(sys.argv) > 10 else "models/yolo26n.engine"
    model_name = sys.argv[11] if len(sys.argv) > 11 else None
    for n in counts:
        print(f"\n===== SWEEP: {n} cameras =====")
        args = [sys.executable, __file__, "run", str(n), secs, di, imgsz, conf, url, csv_path,
                weights, engine]
        if model_name:
            args.append(model_name)
        r = subprocess.run(args,
                           env={**os.environ, "PYTHONPATH": os.getcwd()})
        if r.returncode != 0:
            print(f"[sweep] {n} cams failed (rc={r.returncode}) — stopping sweep")
            break
        time.sleep(4)  # let VRAM/pipelines fully release between runs
    print(f"\nCSV written: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
