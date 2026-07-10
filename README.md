# FrameInsight

Multi-camera CCTV analytics backend on NVIDIA DeepStream. One GPU pipeline
decodes, detects (YOLO26 / TensorRT), and tracks across all cameras; business
applications — footfall, dwell time, headcount, intrusion — are **~30-line rule
kernels** running on the detection metadata, configured per client in a
`site.yaml`. Detection runs once; rules are nearly free.

Measured on an RTX 3070 Ti 8 GB: **50 real 720p RTSP cameras through
YOLO26-xlarge at 30 fps**. The ceiling is the video **decoder** (NVDEC,
~64×720p30 per Ampere decoder), not the AI — full numbers in
[docs/deepstream-benchmark-report.md](docs/deepstream-benchmark-report.md).

```
RTSP cameras ──► NVDEC decode ──► batch ──► YOLO26 (TensorRT) ──► tracker ─┐
                (all GPU-resident, zero copy)                              │ metadata only
                                                                           ▼
                site.yaml + zones/*.json ──► rule kernels ──► events ──► sinks
                (per-client, no code)        (per-frame,      JSONL / SQLite /
                                             testable off-GPU) console / Supabase
```

Design rationale and production practices:
[docs/frameinsight-platform-architecture.md](docs/frameinsight-platform-architecture.md).

## Repository layout

```
frameinsight/                the backend package
  types.py                   Detection / Event — the only vocabulary kernels speak
  geometry.py, zones.py      normalized [0,1] zones (polygons + directed lines)
  rules/                     kernel protocol + built-ins:
                             line_crossing, zone_dwell, headcount, zone_intrusion
  siteconfig.py              site.yaml loading + validation
  dispatch.py                camera → rules routing, crash-safe rule state
  sinks.py                   console / JSONL / SQLite / Supabase event sinks
  runtime.py                 DeepStream pipeline per group (pyservicemaker; GPU side)
                             + live-state publisher (state/live/<cam>.json, ~5 Hz)
  replay.py                  run recorded detections through rules — no GPU
  studio/                    Zone Studio: local web UI — draw zones on camera
                             snapshots, single-camera live view with boxes/timers
  cli.py                     frameinsight validate | replay | run | studio | kernels

examples/school/             worked example site: gate counting, water-cooler
                             dwell, classroom headcounts, one custom kernel
sites/office/                real deployment: 16×4MP cams, yolo26x @ 5 det/s,
                             room headcount + per-desk occupancy/working timers
tests/                       kernel + config test suite (runs anywhere, no GPU)

models/deepstream/           YOLO26 model packs: custom NMS-free bbox parser,
                             nvinfer configs (n/s/m/l/x), labels; ONNX/engines git-ignored
dashboard/                   FrameInsight Analytics Cloud — the online dashboard
                             (Next.js + shadcn/ui; per-vertical skins, fleet health,
                             alerts, reports, AI insights; own README, split-ready)
docker/Dockerfile            the one edge image every site runs
scripts/                     engine building, edge launcher, benchmark harnesses
docs/                        architecture, benchmark report, DeepStream guides
frameinsight_estimator.html  server-spec calculator calibrated on the benchmarks
```

## Install

**Rules-only development (any machine, no GPU)** — kernels, zones, replay,
tests all work on a laptop:

```bash
git clone https://github.com/humza-sami/visionsense-studio
cd visionsense-studio
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # 27 tests, < 1 s
frameinsight kernels                     # list built-in rule kernels
```

**Live runtime (the edge server)** needs:

1. **NVIDIA driver 590+**, Docker, and the
   [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
   (`scripts/setup_gpu.sh` documents our host setup).
2. **The DeepStream 9.0 container** — pulled automatically by the Docker build:
   `nvcr.io/nvidia/deepstream:9.0-triton-multiarch`.
3. **Model packs.** Export ONNX weights and prebuild TensorRT engines **once,
   offline** (never while streams are live — engine builds under decode load
   have crashed the GPU driver):

   ```bash
   python scripts/export_model.py               # Ultralytics → models/deepstream/yolo26*/…onnx
   # then per model, inside the container (exact commands in models/deepstream/README.md):
   #   g++  … nvdsinfer_yolo26.cpp → libnvdsparser_yolo26.so     (bbox parser, once)
   #   trtexec --onnx=… --fp16 → yolo26s.onnx_b32_gpu0_fp16.engine
   ```
4. **The edge image** — built on first use by the launcher, or manually:

   ```bash
   docker build -t frameinsight/edge:0.1.0 -f docker/Dockerfile .
   ```

## Usage

A deployment is a **site directory** — config, not code:

```
sites/<client>/
  site.yaml        cameras, pipeline groups, rule bindings, sinks
  zones/*.json     drawn areas/lines, normalized to a reference snapshot
  apps/*.py        optional custom kernels (only if built-ins don't cover it)
```

The engine is identical for every client. Day-to-day:

```bash
# 1. Check a site before touching the server (no GPU needed)
frameinsight validate examples/school

# 2. Develop/regression-test rules against recorded detections (no GPU needed)
frameinsight replay examples/school examples/school/sample_data/school_day.jsonl --console

# 3. Run live on the edge box: one DeepStream pipeline per site.yaml group,
#    supervised (a crashed group restarts alone)
export SCHOOL_NVR_TMPL='rtsp://USER:PASS@NVR_HOST:554/cam/realmonitor?channel={ch}&subtype=1'
bash scripts/run_edge.sh examples/school

# …or a single group, without the supervisor:
bash scripts/run_edge.sh examples/school entrances

# 4. Zone Studio — draw zones with the mouse + watch a camera live with boxes
#    and rule timers overlaid (needs ffmpeg; pip install 'frameinsight[studio]')
frameinsight studio sites/office            # → http://<edge-box>:8765
```

Events stream to the sinks listed in site.yaml (console, append-only JSONL,
SQLite, batched Supabase). The runtime also emits `heartbeat` events with
per-camera frame ages and a `camera_stalled` alert when a feed goes quiet —
that's the health feed for the online dashboard.

**Start from the worked example:** [examples/school/](examples/school/) counts
kids entering/exiting the gate, measures water-cooler dwell times, and reports
per-classroom headcounts — including a custom plugin kernel and a synthetic
recording you can replay in seconds.

## The rules model (why this scales to many clients)

- **One detection pass, many apps.** Kernels consume `(class, confidence, box,
  track_id)` per frame — never pixels. Adding an app adds microseconds, not GPU load.
- **Per-camera detection rates = pipeline groups.** nvinfer's `interval` skips
  whole batches, so "gate at 10 det/s, classrooms at 1 det/s" is done with two
  pipelines (site.yaml `groups:`), which the benchmarks showed share the GPU
  additively and cheaply.
- **Zones are normalized** to [0,1] against a per-camera reference snapshot —
  they survive stream-resolution changes, and every floor rule tests the
  **feet** (bottom-center) anchor, not the box center.
- **Every kernel takes the standard guards** — `classes`, `min_conf`,
  `sustain_s`, `cooldown_s`, `lost_timeout_s` — because flickery boxes and
  track-ID churn are facts of CCTV life ([architecture doc](docs/frameinsight-platform-architecture.md) §4.3).
- **Crash-safe by construction:** rule state snapshots to `state/*.json` and
  restores on start; JSONL sinks are append-only; a buggy kernel logs and is
  skipped, never kills the pipeline.

Writing a custom kernel:

```python
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule

@register_kernel
class AfterHoursPresence(Rule):
    KIND = "after_hours"                      # referenced from site.yaml

    def on_frame(self, ts, detections):       # detections pre-filtered by
        for d in detections:                  # classes + min_conf
            if self.cooled_down(ts, str(d.track_id)):
                self.emit(ts, "after_hours_person", severity="alert",
                          track_id=d.track_id)
```

Save it as `sites/<client>/apps/after_hours.py`, bind it in site.yaml, test it
with `frameinsight replay`. Done.

## Key measured facts (RTX 3070 Ti 8 GB · 720p H.264 · FP16)

- **NVDEC decoder is the wall** — ~64× 720p30 streams saturate one Ampere
  decoder (~1.8 Gpx/s). Substreams (704×576) roughly double camera capacity.
- **Compute rarely binds** at alert-grade rates: 15×xlarge + 25×small = 40 cams
  at full 30 fps used 14 % GPU, 65 % NVDEC, 4.3 GB VRAM.
- **VRAM** ≈ 1.5 GB base + one FP16 engine per distinct model + ~30 MB/camera.

These calibrate [frameinsight_estimator.html](frameinsight_estimator.html) —
the quick server-quoting calculator.

## Security

- Camera credentials and API keys live in **environment variables only**
  (`.env.example`); site.yaml references them as `${VAR}` and the loader
  refuses to run with them missing. Never commit a URL with a password in it.
- `*.key` / `*.pem` / engines / videos are git-ignored.
