"""Real-NVR performance-ceiling benchmark — find where FPS drops, per model.

Source bank: channels 1..150 on the Dahua NVR (720p H.264). For camera_count > 150
the list repeats from channel 1 (cam 151 = ch 1 …) and the row is flagged urls_repeated.

Per rung we measure and export the columns the user asked for:
  model, camera_count, min_fps, avg_fps, p50_fps, p95_latency_ms, gpu_util,
  gpu_util_peak, nvdec_util, vram_used_gb, cpu_util, dropped_frames, read_errors,
  urls_repeated, net_rx_mbps_avg, net_rx_mbps_peak, det_interval, streams_alive,
  drop_severity, bottleneck, notes

Latency: deepstream-app is run with NVDS_ENABLE_LATENCY_MEASUREMENT=1, which prints
per-frame "latency = X ms"; we take p50/p95 over the steady window.
Dropped frames: derived — expected(input_fps × window × N) minus delivered(sum avg_fps
× window); explicit QoS/drop log lines are added if present.
Read errors: count of RTSP reconnect/failure lines in the container log.
Bottleneck (one of the user's four cases), decided from measured utilisation:
  1 GPU/server   — gpu_util_peak ≥ 97% and gpu_util_avg high
  2 decoder      — nvdec_util ≥ 88%
  3 RTSP/source  — fps drops while GPU & NVDEC have headroom AND read_errors present,
                   NIC below ~70% of link
  4 network      — fps drops, GPU & NVDEC have headroom, NIC ≥ ~70% of 1 Gbps link

  NVR=1 already implied. Run:  python scripts/benchmark_nvr_ceiling.py all 60
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

import os

ROOT = Path(__file__).resolve().parent.parent
DS_DIR = ROOT / "models" / "deepstream"
CFG_DIR = DS_DIR / "app_configs"
LOG_DIR = ROOT / "artifacts" / "benchmarks" / "ds_logs"
IMAGE = "nvcr.io/nvidia/deepstream:9.0-triton-multiarch"

# SRC=nvr  → real 150-channel Dahua NVR over the routed network (network-path limited)
# SRC=local→ loopback relay looping a real 720p NVR clip (isolates SERVER ceiling)
SRC = os.environ.get("SRC", "nvr")
NVR_TMPL = os.environ.get("NVR_TMPL",
    "rtsp://USER:PASS@NVR_HOST:554/cam/realmonitor?channel={ch}&subtype=1")
LOCAL_URL = "rtsp://127.0.0.1:8554/live"
BANK = 150                 # distinct channels available
if SRC == "local":
    CSV_PATH = ROOT / "benchmark_local720_ceiling.csv"
    STATE_PATH = ROOT / "benchmark_local720_ceiling_state.json"
else:
    CSV_PATH = ROOT / "benchmark_nvr_ceiling.csv"
    STATE_PATH = ROOT / "benchmark_nvr_ceiling_state.json"
INPUT_FPS = 30.0
INTERVAL = 11              # ~2.5 fps detection/cam
LINK_MBPS = 1000.0         # assumed 1 GbE
STARTUP_ALLOWANCE = 360

# per-model ladders — climb until FPS collapses / OOM / errors
MODELS = {
    "n": {"ladder": [64, 96, 128, 160, 200, 240], "infer_batch": 32},
    "s": {"ladder": [64, 96, 128, 160, 200],      "infer_batch": 32},
    "m": {"ladder": [64, 96, 128, 160],           "infer_batch": 32},
    "l": {"ladder": [50, 64, 96, 128],            "infer_batch": 16},
    "x": {"ladder": [32, 50, 64, 96],             "infer_batch": 16},
}
COLUMNS = ["model", "camera_count", "min_fps", "avg_fps", "p50_fps", "p95_latency_ms",
           "gpu_util", "gpu_util_peak", "nvdec_util", "vram_used_gb", "cpu_util",
           "dropped_frames", "read_errors", "urls_repeated", "net_rx_mbps_avg",
           "net_rx_mbps_peak", "det_interval", "streams_alive", "drop_severity",
           "bottleneck", "notes"]


def state_update(**kv):
    st = {}
    if STATE_PATH.exists():
        try: st = json.loads(STATE_PATH.read_text())
        except Exception: st = {}
    st.update(kv, updated=datetime.now().isoformat(timespec="seconds"))
    STATE_PATH.write_text(json.dumps(st, indent=1))


def done_scenarios() -> set:
    d = set()
    if CSV_PATH.exists():
        for r in csv.DictReader(CSV_PATH.open()):
            if int(r.get("streams_alive") or 0) > 0:
                d.add(f"{r['model']}_{r['camera_count']}")
    return d


def nv(q):
    try:
        return float(subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"],
            text=True, timeout=10).split("\n")[0])
    except Exception:
        return -1.0


def gpu_healthy(): return nv("memory.total") > 0


def cpu_pct(iv=0.3):
    def s():
        v = list(map(int, open("/proc/stat").readline().split()[1:8])); return sum(v), v[3]+v[4]
    a, ai = s(); time.sleep(iv); b, bi = s()
    return 0.0 if b == a else round(100*(1-(bi-ai)/(b-a)), 1)


def net_rx_bytes():
    tot = 0
    for ln in open("/proc/net/dev").readlines()[2:]:
        name, rest = ln.split(":", 1)
        if name.strip() == "lo":
            continue
        tot += int(rest.split()[0])
    return tot


def engine_path(mk):
    b = MODELS[mk]["infer_batch"]
    return DS_DIR / f"yolo26{mk}" / f"yolo26{mk}.onnx_b{b}_gpu0_fp16.engine"


def write_pgie(mk):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    name, b = f"yolo26{mk}", MODELS[mk]["infer_batch"]
    (CFG_DIR / f"pgie_{name}.txt").write_text(f"""[property]
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
""")


def write_app_config(mk, n):
    name = f"yolo26{mk}"
    srcs = []
    for i in range(n):
        if SRC == "local":
            uri = f"rtsp://127.0.0.1:8554/live{i % 12}"   # spread across 12 publishers
        else:
            uri = NVR_TMPL.format(ch=(i % BANK) + 1)
        srcs.append(f"""[source{i}]
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
    cfg = f"""[application]
enable-perf-measurement=1
perf-measurement-interval-sec=5

{chr(10).join(srcs)}
[streammux]
gpu-id=0
live-source=1
batch-size={n}
batched-push-timeout=40000
width=1280
height=720
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
    p = CFG_DIR / f"ceil_{name}_{n}.txt"
    p.write_text(cfg)
    return p


PERF_RE = re.compile(r"\*\*PERF:\s*(.*)")
FPS_RE = re.compile(r"([\d.]+)\s*\(([\d.]+)\)")
LAT_RE = re.compile(r"latency[=:\s]+([\d.]+)\s*(?:ms)?", re.I)
ERR_RE = re.compile(r"reset|reconnect|failed to|could not|no more frames|"
                    r"end of stream|rtsp.*error|connection refused", re.I)


def build_engine(mk):
    if engine_path(mk).exists():
        return True
    b = MODELS[mk]["infer_batch"]; name = f"yolo26{mk}"
    script = CFG_DIR / f"build_{name}.sh"
    script.write_text(
        f"trtexec --onnx=/models/{name}/{name}.onnx "
        f"--saveEngine=/models/{name}/{name}.onnx_b{b}_gpu0_fp16.engine "
        f"--fp16 --minShapes=images:1x3x640x640 --optShapes=images:{b}x3x640x640 "
        f"--maxShapes=images:{b}x3x640x640 --memPoolSize=workspace:2048 && echo OK\n")
    subprocess.run(["sudo", "docker", "rm", "-f", f"ceil_eng_{mk}"], capture_output=True)
    subprocess.run(["sudo", "docker", "run", "--rm", "--gpus", "all",
        "--name", f"ceil_eng_{mk}", "-v", f"{DS_DIR}:/models", "-v", f"{CFG_DIR}:/cfg",
        IMAGE, "bash", f"/cfg/{script.name}"],
        stdout=(LOG_DIR / f"engine_{name}.log").open("w"), stderr=subprocess.STDOUT,
        timeout=3000)
    return engine_path(mk).exists()


def classify(min_fps, gpu_avg, gpu_pk, nvdec, read_err, net_pk):
    stable = INPUT_FPS * 0.95
    if min_fps >= stable and read_err == 0:
        sev = "stable"
    elif min_fps >= INPUT_FPS * 0.80:
        sev = "slight FPS drop"
    elif min_fps >= INPUT_FPS * 0.50:
        sev = "major FPS drop"
    else:
        sev = "stream starvation / read errors"

    if sev == "stable":
        return sev, "none"
    if nvdec >= 88:
        return sev, "decoder bottleneck"
    if gpu_pk >= 97 and gpu_avg >= 40:
        return sev, "GPU/server bottleneck"
    # compute & decode both have headroom → source or network
    if net_pk >= LINK_MBPS * 0.70:
        return sev, "network bottleneck"
    if read_err > 0 or min_fps < stable:
        return sev, "RTSP/source starvation"
    return sev, "undetermined"


def run_rung(mk, n, secs):
    if not gpu_healthy():
        state_update(aborted=f"GPU dead before {mk}:{n}")
        raise RuntimeError("GPU driver not responding — reboot then rerun (progress saved)")
    state_update(current=f"{mk}_{n}")
    cfg = write_app_config(mk, n)
    log_path = LOG_DIR / f"ceil_{mk}{n}.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cname = f"ceil_{mk}{n}"
    subprocess.run(["sudo", "docker", "rm", "-f", cname], capture_output=True)

    gpu, dec, vram, cpu = [], [], [], []
    net_samples = []
    stop = threading.Event()

    def sampler():
        last_b, last_t = net_rx_bytes(), time.monotonic()
        while not stop.is_set():
            gpu.append(nv("utilization.gpu")); dec.append(nv("utilization.decoder"))
            vram.append(nv("memory.used")); cpu.append(cpu_pct(0.3))
            b, t = net_rx_bytes(), time.monotonic()
            if t > last_t:
                net_samples.append((b-last_b)*8/1e6/(t-last_t))  # Mbps
            last_b, last_t = b, t
            time.sleep(1.5)
    th = threading.Thread(target=sampler, daemon=True); th.start()

    perf_lines, latencies = [], []
    read_errors = 0
    note = ""
    measuring = []
    cmd = ["sudo", "docker", "run", "--rm", "--gpus", "all", "--net=host",
           "--ulimit", "nofile=1048576:1048576",
           "-e", "NVDS_ENABLE_LATENCY_MEASUREMENT=1",
           "--name", cname, "-v", f"{DS_DIR}:/models", "-v", f"{CFG_DIR}:/cfg",
           IMAGE, "deepstream-app", "-c", f"/cfg/{cfg.name}"]
    print(f"[{mk}:{n}] starting ({'repeat' if n>BANK else 'distinct'} channels, log={log_path.name})")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    t0 = time.monotonic(); deadline = t0 + secs + STARTUP_ALLOWANCE
    with log_path.open("w") as lf:
        try:
            for line in proc.stdout:
                lf.write(line); lf.flush()
                if ERR_RE.search(line): read_errors += 1
                if ("out of memory" in line.lower() or "cuda error" in line.lower()) and not note:
                    note = line.strip()[:120]
                lm = LAT_RE.search(line)
                if lm and measuring:
                    v = float(lm.group(1))
                    if 0 < v < 100000: latencies.append(v)
                pm = PERF_RE.search(line)
                if pm:
                    fps = [float(a) for a, _ in FPS_RE.findall(pm.group(1))]
                    if fps:
                        perf_lines.append(fps)
                        if not measuring:
                            measuring.append(time.monotonic())
                            print(f"[{mk}:{n}] first PERF +{measuring[0]-t0:.0f}s ({len(fps)} streams)")
                if measuring and time.monotonic()-measuring[0] > secs: break
                if time.monotonic() > deadline:
                    note = note or "timeout before steady state"; break
            else:
                if not note: note = f"exited early rc={proc.poll()}"
        except Exception as e:
            note = f"harness exc: {e}"
        finally:
            stop.set()
            subprocess.run(["sudo", "docker", "rm", "-f", cname], capture_output=True)
            try: proc.wait(timeout=30)
            except Exception: proc.kill()

    if not gpu_healthy() and "driver" not in note:
        note = (note + " | GPU DRIVER DIED").strip(" |")

    a = lambda x: round(statistics.mean(x), 1) if x else 0.0
    pk = lambda x: round(max(x), 1) if x else 0.0
    tail = perf_lines[len(perf_lines)//2:] if perf_lines else []
    per_stream = [statistics.mean(c) for c in zip(*tail)] if tail else []
    avg_fps = round(statistics.mean(per_stream), 2) if per_stream else 0
    min_fps = round(min(per_stream), 2) if per_stream else 0
    p50_fps = round(statistics.median(per_stream), 2) if per_stream else 0
    p95_lat = round(sorted(latencies)[int(len(latencies)*0.95)], 1) if len(latencies) > 20 else 0
    net_avg, net_pk = a(net_samples), pk(net_samples)
    # derived dropped frames over the measured window
    win = secs
    delivered = sum(per_stream) * win
    expected = INPUT_FPS * n * win
    dropped = int(max(0, expected - delivered)) if per_stream else 0
    repeated = max(0, n - BANK)
    sev, bottleneck = classify(min_fps, a(gpu), pk(gpu), a(dec), read_errors, net_pk)
    if not per_stream:
        sev, bottleneck = "stream starvation / read errors", (
            "GPU/server bottleneck" if "memory" in note.lower() else
            "RTSP/source starvation" if read_errors else "crash/undetermined")

    row = {"model": f"yolo26{mk}", "camera_count": n, "min_fps": min_fps,
           "avg_fps": avg_fps, "p50_fps": p50_fps, "p95_latency_ms": p95_lat,
           "gpu_util": a(gpu), "gpu_util_peak": pk(gpu), "nvdec_util": a(dec),
           "vram_used_gb": round(pk(vram)/1024, 2), "cpu_util": a(cpu),
           "dropped_frames": dropped, "read_errors": read_errors,
           "urls_repeated": repeated, "net_rx_mbps_avg": net_avg,
           "net_rx_mbps_peak": net_pk, "det_interval": INTERVAL,
           "streams_alive": len(per_stream), "drop_severity": sev,
           "bottleneck": bottleneck, "notes": note}
    new = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new: w.writeheader()
        w.writerow(row)
    state_update(**{f"{mk}_{n}": sev})
    print(f"[{mk}:{n}] {sev} | {bottleneck} | min {min_fps} avg {avg_fps} p95lat {p95_lat}ms | "
          f"GPU {a(gpu)}/{pk(gpu)} NVDEC {a(dec)} VRAM {row['vram_used_gb']}GB "
          f"NET {net_pk}Mbps CPU {a(cpu)} err {read_errors} rep {repeated} {note}")
    return row


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    # reachability
    probe = "rtsp://127.0.0.1:8554/live0" if SRC == "local" else NVR_TMPL.format(ch=1)
    r = subprocess.run(["ffprobe", "-v", "error", "-rtsp_transport", "tcp",
                        "-select_streams", "v:0", "-show_entries", "stream=width",
                        "-of", "csv", probe],
                       capture_output=True, text=True, timeout=20)
    if "1280" not in (r.stdout or ""):
        print(f"source unreachable ({SRC}): {r.stdout}{r.stderr[:150]}"); return 1
    print(f"SRC={SRC} → {'loopback 720p relay' if SRC=='local' else '150-ch NVR'}, CSV {CSV_PATH.name}")
    if not gpu_healthy():
        print("GPU driver down — reboot first"); return 1
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    done = done_scenarios()
    if done: print(f"resume: skipping {sorted(done)}")
    models = list(MODELS) if which == "all" else [which]
    for mk in models:
        write_pgie(mk)
        if not build_engine(mk):
            print(f"[{mk}] engine build failed — skip"); continue
        for n in MODELS[mk]["ladder"]:
            if f"{mk}_{n}" in done:
                print(f"[{mk}:{n}] done — skip"); continue
            row = run_rung(mk, n, secs)
            # stop this model once it's clearly past the ceiling or crashed
            if row["streams_alive"] == 0 or row["drop_severity"] == "major FPS drop" \
               or row["drop_severity"].startswith("stream starvation"):
                print(f"[{mk}] ceiling found at {n} ({row['drop_severity']}) — next model")
                break
            time.sleep(5)
    state_update(current="idle")
    print(f"\nCSV: {CSV_PATH}\nlogs: {LOG_DIR}\nstate: {STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
