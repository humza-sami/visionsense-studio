"""DeepStream 9.0 capacity benchmark — ALL model sizes (n/s/m/l/x). CRASH-SAFE.

Everything is persisted the moment it exists, so a driver crash, OOM, reboot or
killed session loses nothing:
  * full container output streams line-by-line to artifacts/benchmarks/ds_logs/<rung>.log
  * every rung writes its CSV row even on crash (partial data + failure note)
  * progress state in benchmark_deepstream_state.json after every step
  * rerunning skips rungs that already SUCCEEDED (CSV row with streams_alive>0)
    and retries failed ones
  * GPU health is checked before each rung; a dead driver aborts cleanly with a
    clear message instead of producing junk rows
  * TensorRT engines are pre-built with trtexec (no streams attached) — much
    gentler than building inside a live pipeline (a build under load crashed the
    GSP firmware on 2026-07-08)

Rung pipeline: N× RTSP (704×576 H.265 25fps) → NVDEC → nvstreammux(batch=N) →
nvinfer(FP16, interval=11 ≈ 2 fps/stream) → NvSORT tracker → fakesink. Render off.

  .venv/bin/python scripts/benchmark_deepstream.py all 90
  .venv/bin/python scripts/benchmark_deepstream.py n 90      # one model
  .venv/bin/python scripts/benchmark_deepstream.py n:64 90   # one rung (always runs)
"""
from __future__ import annotations

import csv
import json
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DS_DIR = ROOT / "models" / "deepstream"
CFG_DIR = DS_DIR / "app_configs"
LOG_DIR = ROOT / "artifacts" / "benchmarks" / "ds_logs"
STATE_PATH = ROOT / "benchmark_deepstream_state.json"
IMAGE = "nvcr.io/nvidia/deepstream:9.0-triton-multiarch"
RTSP = "rtsp://127.0.0.1:8554/live"
INTERVAL = 11                      # det fps ≈ 25/(interval+1) ≈ 2.08
STARTUP_ALLOWANCE = 300            # engines are prebuilt; startup should be fast

import os

MODELS = {
    "n": {"ladder": [32, 64, 96, 128, 160, 192, 224], "infer_batch": 32},
    "s": {"ladder": [32, 64, 96, 128, 160, 192],      "infer_batch": 32},
    "m": {"ladder": [32, 48, 64, 96, 128],            "infer_batch": 32},
    "l": {"ladder": [24, 32, 48, 64, 80, 96],         "infer_batch": 16},
    "x": {"ladder": [16, 24, 32, 48, 64],             "infer_batch": 16},
}

# ── Real NVR mode (env NVR=1): 50 live Dahua channels, 1280x720 H.264 ──────────
USE_NVR = os.environ.get("NVR") == "1"
NVR_TMPL = os.environ.get("NVR_TMPL",
    "rtsp://USER:PASS@NVR_HOST:554/cam/realmonitor?channel={ch}&subtype=1")
NVR_CHANNELS = 50
NVR_W, NVR_H = 1280, 720
NVR_LADDER = [8, 16, 32, 50, 64, 80, 96, 112, 128, 150]
if USE_NVR:
    for m in MODELS:
        MODELS[m]["ladder"] = NVR_LADDER
    CSV_PATH = ROOT / "benchmark_deepstream_nvr.csv"
    STATE_PATH = ROOT / "benchmark_deepstream_nvr_state.json"
else:
    CSV_PATH = ROOT / "benchmark_deepstream.csv"
COLUMNS = ["scenario", "model", "total_cameras", "det_interval", "streams_alive",
           "pipeline_fps_per_stream_avg", "pipeline_fps_per_stream_min",
           "gpu_util_avg", "gpu_util_peak", "nvdec_util_avg", "vram_used_MB_peak",
           "cpu_util_avg", "ram_used_MB", "notes"]


# ── tiny persistent state ────────────────────────────────────────────────────
def state_update(**kv) -> None:
    st = {}
    if STATE_PATH.exists():
        try:
            st = json.loads(STATE_PATH.read_text())
        except Exception:
            st = {}
    st.update(kv, updated=datetime.now().isoformat(timespec="seconds"))
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE_PATH)


def succeeded_scenarios() -> set[str]:
    done = set()
    if CSV_PATH.exists():
        for r in csv.DictReader(CSV_PATH.open()):
            try:
                if int(r.get("streams_alive") or 0) > 0:
                    done.add(r["scenario"])
            except ValueError:
                pass
    return done


# ── host sampling ────────────────────────────────────────────────────────────
def nv(q: str) -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"],
            text=True, timeout=10)
        return float(out.split("\n")[0])
    except Exception:
        return -1.0


def gpu_healthy() -> bool:
    return nv("memory.total") > 0


def cpu_pct(iv=0.4) -> float:
    def s():
        v = list(map(int, open("/proc/stat").readline().split()[1:8]))
        return sum(v), v[3] + v[4]
    a, ai = s(); time.sleep(iv); b, bi = s()
    return 0.0 if b == a else round(100 * (1 - (bi - ai) / (b - a)), 1)


def ram_mb() -> int:
    m = {}
    for ln in open("/proc/meminfo"):
        k, v = ln.split(":")
        m[k] = int(v.strip().split()[0])
    return (m["MemTotal"] - m["MemAvailable"]) // 1024


def relay_ok() -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-rtsp_transport", "tcp",
                        "-select_streams", "v", "-show_entries", "stream=codec_name",
                        "-of", "csv", RTSP], capture_output=True, text=True, timeout=15)
    return "hevc" in (r.stdout or "")


# ── config generation ────────────────────────────────────────────────────────
def engine_path(mk: str) -> Path:
    b = MODELS[mk]["infer_batch"]
    return DS_DIR / f"yolo26{mk}" / f"yolo26{mk}.onnx_b{b}_gpu0_fp16.engine"


def write_pgie(mk: str) -> Path:
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    name, b = f"yolo26{mk}", MODELS[mk]["infer_batch"]
    txt = f"""[property]
gpu-id=0
net-scale-factor=0.0039215686274509803
model-color-format=0
onnx-file=/models/{name}/{name}.onnx
model-engine-file=/models/{name}/{name}.onnx_b{b}_gpu0_fp16.engine
labelfile-path=/models/labels.txt
batch-size={b}
network-mode=2
network-type=0
num-detected-classes=80
infer-dims=3;640;640
maintain-aspect-ratio=1
symmetric-padding=1
cluster-mode=4
gie-unique-id=1
parse-bbox-func-name=NvDsInferParseYolo26
custom-lib-path=/models/parser/libnvdsparser_yolo26.so
interval={INTERVAL}

[class-attrs-all]
pre-cluster-threshold=0.25
"""
    p = CFG_DIR / f"pgie_{name}.txt"
    p.write_text(txt)
    return p


def _nvr_sources(n: int) -> str:
    """N individual RTSP source groups, cycling real NVR channels 1..50."""
    blocks = []
    for i in range(n):
        ch = (i % NVR_CHANNELS) + 1
        uri = NVR_TMPL.format(ch=ch)
        blocks.append(f"""[source{i}]
enable=1
type=4
uri={uri}
num-sources=1
gpu-id=0
cudadec-memtype=0
num-extra-surfaces=2
latency=300
select-rtp-protocol=4
rtsp-reconnect-interval-sec=15
""")
    return "\n".join(blocks)


def write_app_config(mk: str, n: int) -> Path:
    name = f"yolo26{mk}"
    if USE_NVR:
        sources = _nvr_sources(n)
        mux_w, mux_h = NVR_W, NVR_H
    else:
        sources = f"""[source0]
enable=1
type=3
uri={RTSP}
num-sources={n}
gpu-id=0
cudadec-memtype=0
num-extra-surfaces=2
latency=200
select-rtp-protocol=4
rtsp-reconnect-interval-sec=15
"""
        mux_w, mux_h = 704, 576
    cfg = f"""[application]
enable-perf-measurement=1
perf-measurement-interval-sec=5

{sources}
[streammux]
gpu-id=0
live-source=1
batch-size={n}
batched-push-timeout=40000
width={mux_w}
height={mux_h}
enable-padding=0
buffer-pool-size=4

[primary-gie]
enable=1
gpu-id=0
config-file=/cfg/pgie_{name}.txt

[tracker]
enable=1
tracker-width=640
tracker-height=384
gpu-id=0
ll-lib-file=/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so
ll-config-file=/opt/nvidia/deepstream/deepstream/samples/configs/deepstream-app/config_tracker_NvSORT.yml

[sink0]
enable=1
type=1
sync=0

[tiled-display]
enable=0

[osd]
enable=0
"""
    p = CFG_DIR / f"ds_app_{name}_{n}.txt"
    p.write_text(cfg)
    return p


# ── container helpers ────────────────────────────────────────────────────────
def docker_run(cname: str, args: list[str], log_path: Path, deadline_s: int,
               on_line=None) -> int:
    """Run a container, streaming output to log_path line-by-line (crash-safe)."""
    subprocess.run(["sudo", "docker", "rm", "-f", cname], capture_output=True)
    # ulimit: 64+ RTSP sources need >1024 fds or GstPoll dies with
    # "gst_poll_write_control: assertion 'set != NULL' failed"
    cmd = ["sudo", "docker", "run", "--rm", "--gpus", "all", "--net=host",
           "--ulimit", "nofile=65536:65536",
           "--name", cname, "-v", f"{DS_DIR}:/models", "-v", f"{CFG_DIR}:/cfg",
           IMAGE] + args
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    end = time.monotonic() + deadline_s
    stop = False
    with log_path.open("w") as lf:
        lf.write(f"# {' '.join(cmd)}\n"); lf.flush()
        for line in proc.stdout:
            lf.write(line); lf.flush()
            if on_line and on_line(line.rstrip()):
                stop = True
                break
            if time.monotonic() > end:
                lf.write("# HARNESS: deadline reached\n")
                break
    subprocess.run(["sudo", "docker", "rm", "-f", cname], capture_output=True)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    return 0 if stop else (proc.returncode if proc.returncode is not None else -9)


def build_parser_lib() -> None:
    so = DS_DIR / "parser" / "libnvdsparser_yolo26.so"
    if so.exists():
        return
    print("[setup] compiling YOLO26 parser in container…")
    rc = docker_run("dsbench_build", ["bash", "-c",
        "g++ -shared -fPIC -o /models/parser/libnvdsparser_yolo26.so "
        "/models/parser/nvdsinfer_yolo26.cpp "
        "-I/opt/nvidia/deepstream/deepstream/sources/includes "
        "-I/usr/local/cuda/include && echo PARSER_BUILD_OK"],
        LOG_DIR / "parser_build.log", 300)
    if not so.exists():
        raise RuntimeError(f"parser build failed (rc={rc}) — see {LOG_DIR}/parser_build.log")
    print("[setup] parser built ✓")


def prebuild_engine(mk: str) -> None:
    """Build the TRT engine with trtexec, NO streams attached (gentle on driver)."""
    eng = engine_path(mk)
    if eng.exists():
        return
    b = MODELS[mk]["infer_batch"]
    name = f"yolo26{mk}"
    print(f"[{mk}] building TRT engine (batch {b}, fp16) with trtexec — one-time…")
    state_update(**{f"engine_{mk}": "building"})
    # The image entrypoint word-splits multi-word args, so `bash -c "<script>"`
    # loses everything after the first word. A script FILE survives splitting.
    script = CFG_DIR / f"build_{name}.sh"
    script.write_text(
        f"trtexec --onnx=/models/{name}/{name}.onnx "
        f"--saveEngine=/models/{name}/{name}.onnx_b{b}_gpu0_fp16.engine "
        f"--fp16 --minShapes=images:1x3x640x640 --optShapes=images:{b}x3x640x640 "
        f"--maxShapes=images:{b}x3x640x640 --memPoolSize=workspace:2048 "
        f"&& echo ENGINE_BUILD_OK\n")
    rc = docker_run(f"dsbench_eng_{mk}", ["bash", f"/cfg/{script.name}"],
        LOG_DIR / f"engine_{name}.log", 3000)
    if not eng.exists():
        state_update(**{f"engine_{mk}": f"FAILED rc={rc}"})
        raise RuntimeError(f"engine build failed for {name} (rc={rc}) — "
                           f"see {LOG_DIR}/engine_{name}.log")
    state_update(**{f"engine_{mk}": "ok"})
    print(f"[{mk}] engine ready ✓")


# ── the measured rung ────────────────────────────────────────────────────────
PERF_RE = re.compile(r"\*\*PERF:\s*(.*)")
FPS_RE = re.compile(r"([\d.]+)\s*\(([\d.]+)\)")


def run_rung(mk: str, n: int, secs: int) -> dict:
    if not gpu_healthy():
        state_update(aborted=f"GPU driver dead before {mk}:{n}")
        raise RuntimeError("GPU driver not responding — reboot/reload driver, then rerun "
                           "(progress is saved; completed rungs will be skipped)")
    scenario = f"ds_{mk}{n}_i{INTERVAL}"
    state_update(current=scenario)
    cfg = write_app_config(mk, n)
    log_path = LOG_DIR / f"{mk}{n}.log"

    gpu, dec, vram, cpu = [], [], [], []
    perf_lines: list[list[float]] = []
    note = ""
    stop_sampling = threading.Event()

    def sampler():
        while not stop_sampling.is_set():
            gpu.append(nv("utilization.gpu")); dec.append(nv("utilization.decoder"))
            vram.append(nv("memory.used")); cpu.append(cpu_pct(0.3))
            time.sleep(1.5)
    th = threading.Thread(target=sampler, daemon=True); th.start()

    t0 = time.monotonic()
    measuring: list[float] = []   # holds start time once first PERF seen

    def on_line(line: str) -> bool:
        nonlocal note
        low = line.lower()
        if ("out of memory" in low or "cuda error" in low or "assert" in low) and not note:
            note = line[:150]
        m = PERF_RE.search(line)
        if m:
            fps = [float(a) for a, _ in FPS_RE.findall(m.group(1))]
            if fps:
                perf_lines.append(fps)
                if not measuring:
                    measuring.append(time.monotonic())
                    print(f"[{mk}:{n}] first PERF after {measuring[0]-t0:.0f}s ({len(fps)} streams)")
        return bool(measuring) and time.monotonic() - measuring[0] > secs

    print(f"[{mk}:{n}] rung starting (interval={INTERVAL}, log={log_path.name})")
    try:
        rc = docker_run(f"dsbench_{mk}{n}", ["deepstream-app", "-c", f"/cfg/{cfg.name}"],
                        log_path, secs + STARTUP_ALLOWANCE, on_line)
        if rc != 0 and not perf_lines and not note:
            note = f"exited early (rc={rc}) — see {log_path.name}"
    except Exception as e:  # never lose the row
        note = f"harness exception: {e}"
    finally:
        stop_sampling.set()
        if not gpu_healthy() and "driver" not in note:
            note = (note + " | GPU DRIVER DIED during rung").strip(" |")

        a = lambda x: round(statistics.mean(x), 1) if x else 0.0
        pk = lambda x: round(max(x), 1) if x else 0.0
        tail = perf_lines[len(perf_lines) // 2:] if perf_lines else []
        per_stream = [statistics.mean(col) for col in zip(*tail)] if tail else []
        row = {"scenario": scenario, "model": f"yolo26{mk}", "total_cameras": n,
               "det_interval": INTERVAL, "streams_alive": len(per_stream),
               "pipeline_fps_per_stream_avg":
                   round(statistics.mean(per_stream), 2) if per_stream else 0,
               "pipeline_fps_per_stream_min":
                   round(min(per_stream), 2) if per_stream else 0,
               "gpu_util_avg": a(gpu), "gpu_util_peak": pk(gpu),
               "nvdec_util_avg": a(dec), "vram_used_MB_peak": pk(vram),
               "cpu_util_avg": a(cpu), "ram_used_MB": ram_mb(), "notes": note}
        new = not CSV_PATH.exists()
        with CSV_PATH.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            if new:
                w.writeheader()
            w.writerow(row)
        state_update(**{scenario: "ok" if per_stream else f"failed: {note[:80]}"})
        print(f"[{mk}:{n}] done: streams {len(per_stream)}/{n} · "
              f"fps/stream {row['pipeline_fps_per_stream_avg']} "
              f"(min {row['pipeline_fps_per_stream_min']}) · GPU {a(gpu)}%/{pk(gpu)} · "
              f"NVDEC {a(dec)}% · VRAM {pk(vram)}MB · CPU {a(cpu)}% {note}")
    return row


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 90

    if USE_NVR:
        r = subprocess.run(["ffprobe", "-v", "error", "-rtsp_transport", "tcp",
                            "-select_streams", "v:0", "-show_entries", "stream=width",
                            "-of", "csv", NVR_TMPL.format(ch=1)],
                           capture_output=True, text=True, timeout=20)
        if "1280" not in (r.stdout or ""):
            print(f"NVR channel 1 not reachable: {r.stdout}{r.stderr[:200]}")
            return 1
        print(f"NVR mode: 50 live channels, {NVR_W}x{NVR_H} H.264 → CSV {CSV_PATH.name}")
    elif not relay_ok():
        print("RTSP relay not serving — start mediamtx + ffmpeg publisher first")
        return 1
    if not gpu_healthy():
        print("GPU driver not responding — reboot/reload driver first")
        return 1
    build_parser_lib()

    done = succeeded_scenarios()
    if done:
        print(f"resume: skipping already-successful rungs: {sorted(done)}")

    if ":" in which:  # explicit single rung always runs
        mk, n = which.split(":")
        write_pgie(mk); prebuild_engine(mk)
        run_rung(mk, int(n), secs)
    else:
        models = list(MODELS) if which == "all" else [which]
        for mk in models:
            write_pgie(mk)
            try:
                prebuild_engine(mk)
            except RuntimeError as e:
                print(f"[{mk}] {e} — skipping model")
                continue
            for n in MODELS[mk]["ladder"]:
                if f"ds_{mk}{n}_i{INTERVAL}" in done:
                    print(f"[{mk}:{n}] already succeeded — skipped")
                    continue
                row = run_rung(mk, n, secs)
                if row["streams_alive"] == 0:
                    print(f"[{mk}] rung {n} failed — stopping ladder for this model")
                    break
                time.sleep(5)
    state_update(current="idle")
    print(f"\nCSV: {CSV_PATH}\nlogs: {LOG_DIR}\nstate: {STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
