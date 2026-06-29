# Multi-Camera CCTV Detection Backend — Full Build Plan

**Target hardware:** Ubuntu 24.04 · RTX 3070 Ti (8 GB VRAM) · 16 GB RAM · 15 RTSP cameras · YOLO26
**Audience:** Python developer building the production backend from scratch.

---

## 0. Read this first — your hardware reality check

Everything below is sized for **your exact box**. Do not skip this section; it decides every later choice.

### What your parts actually are

| Part | Spec | What it means for you |
|---|---|---|
| GPU | RTX 3070 Ti, Ampere (GA104) | Has **3rd-gen tensor cores** → full **FP16 and INT8** acceleration. Good. This is *not* a GTX; the FP16 speedup is real. |
| VRAM | **8 GB** | **This is your hard limit.** Holds the model engine + activations + decoded frames + CUDA context. Everything in the plan is designed to fit here. |
| NVDEC | 1× 5th-gen decoder | The dedicated video-decode chip. One Ampere NVDEC handles **~20+ 1080p30 H.264 streams**, so 15 cameras decode fine on the GPU — *if* you actually use NVDEC and not the CPU. |
| System RAM | 16 GB | Tight but workable. Run the server **headless (no desktop GUI)** and keep CPU-side frame buffers tiny. |
| CPU | (yours) | Used only for orchestration, business logic, networking, Redis. **Never** for video decode in production. |

### The honest capacity verdict

You **can** run all 15 cameras on this single 3070 Ti. You **cannot** run 15 cameras at 30 FPS, every-frame, full-frame, 1280px detection — that will not fit in 8 GB and will not keep real-time. The achievable design target is:

> **15 cameras × ~8–12 FPS detection each, at 640px, YOLO26n/s FP16, with cross-camera batching + detect-every-3rd-frame + ByteTrack + motion gating.**

That is more than enough for person / phone / bag / head-count / desk-activity / theft logic, because those events do not need 30 detections per second.

### VRAM budget (why 8 GB is enough if you behave)

| Consumer | Approx VRAM |
|---|---|
| CUDA context (headless) | ~0.4–0.6 GB |
| TensorRT YOLO26**n** engine + workspace (batch 15, 640, FP16) | ~1.0–1.8 GB |
| YOLO26**s** instead (if you need accuracy) | ~1.8–2.8 GB |
| NVDEC decoded surfaces (15 cams × few buffers, NV12 ~3 MB) | ~0.2–0.4 GB |
| Preprocessed batch tensor (15×3×640×640 FP16 = 37 MB) | negligible |
| **Safety headroom (keep free!)** | **~1.5–2 GB** |

**Rules this forces on you:**
- Use **YOLO26n** first; move to **YOLO26s** only if accuracy demands it. Do **not** use m/l/x on 8 GB with 15 cams.
- One single model engine for all cameras. **Never load 15 model copies** — that is the #1 way people crash an 8 GB card.
- Stick to **imgsz=640** (drop to 512 if VRAM/throughput gets tight). Never 1280 across 15 streams here.
- Pull the camera **sub-stream** (usually 1080p or lower) for the AI. Use the main/4K stream only if you also record. 4K decode + inference across 15 cams will not fit.

---

## 1. Architecture

A decoupled producer–consumer pipeline. Each stage is a separate worker so the GPU and CPU stay busy at the same time instead of taking turns.

```
 15× RTSP cameras
        │
        ▼
 (1) CAPTURE+DECODE   ── one worker per camera, NVDEC on GPU
        │              frame decoded → stays in GPU memory
        ▼
 (2) LATEST-FRAME BUFFER  ── size 1 per camera, DROP old frames
        │
        ▼
 (3) MOTION GATE      ── cheap bg-subtraction; static frame? skip inference
        │ (only active frames pass)
        ▼
 (4) BATCH BUILDER    ── grab 1 frame from each active camera (short timeout)
        │              → one tensor [B,3,640,640]
        ▼
 (5) INFERENCE        ── ONE TensorRT FP16 YOLO26 engine, dynamic batch
        │              run only every Nth frame per camera
        ▼
 (6) TRACKER (per cam) ── ByteTrack fills frames between detections, gives IDs
        │
        ▼
 (7) BUSINESS LOGIC   ── theft / headcount / desk-activity, per camera + zones
        │
        ▼
 (8) EVENTS → Redis/MQTT → alerts / dashboard / DB
        │
        ▼
 (9) MONITORING       ── per-cam FPS, latency, queue depth, GPU/VRAM/CPU/RAM, drops
```

### Why this layout (given Python's GIL)
- **Decode workers** spend their time inside NVDEC / native code, which releases the GIL — so threads work here.
- **Inference** is one native TensorRT call on a batch — also releases the GIL.
- The **batch builder + inference loop** runs in one place (a single GPU consumer) so you never fight over the GPU.
- **Business logic** is pure Python; if it gets heavy, push it to separate **processes** (multiprocessing) so it doesn't stall the GPU loop.

---

## 2. Tech stack decision (for your box specifically)

| Concern | Choice | Why / alternative |
|---|---|---|
| Video decode | **GStreamer + NVIDIA NVDEC**, or **PyNvVideoCodec** | Gets decode off the CPU. PyNvVideoCodec is pip-installable and decodes straight to a GPU tensor (zero-copy). GStreamer is great but desktop element names are fiddly (see §5.3). |
| Inference engine | **TensorRT FP16**, YOLO26 | 2–5× over PyTorch; FP16 uses your tensor cores. This is the single biggest win. |
| Model loader | **Ultralytics loads the `.engine`** for speed of development | Lets you call batched inference + tracking with minimal code. Drop to the raw TensorRT API later only if you need more control. |
| Tracker | **ByteTrack** | Fastest mainstream tracker, no ReID network. Use BoT-SORT only if you must re-identify a person across cameras. |
| Motion gate | **OpenCV MOG2 / frame-diff** | Pure CPU, dirt cheap, runs before the GPU. |
| Events/alerts | **Redis** (pub/sub or streams) | Lightweight, on-prem, simple. MQTT if cameras/devices already speak it. Kafka is overkill. |
| Packaging | **Docker with `--gpus all`** | Reproducible on-prem deploy. |
| **Skip for now** | DeepStream, Triton, Kubernetes | DeepStream = phase 3 (max density, steep curve). Triton = pointless for one local GPU. K8s = pointless on one on-prem box. |

---

## 3. Project structure

```
cctv-backend/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── config/
│   ├── settings.yaml          # global tunables (imgsz, det_interval, batch, thresholds)
│   ├── cameras.yaml           # 15 camera URLs + per-camera options
│   └── zones/                 # per-camera ROI/zone polygons (json)
├── models/
│   ├── yolo26n.pt             # training/dev format
│   ├── yolo26n.onnx           # intermediate
│   └── yolo26n.engine         # TensorRT — what production runs
├── src/
│   ├── capture/
│   │   ├── rtsp_worker.py      # per-camera decode thread + reconnection
│   │   └── frame_buffer.py     # latest-frame holder (drop-old)
│   ├── inference/
│   │   ├── engine.py           # TensorRT/Ultralytics wrapper
│   │   ├── batch_builder.py    # gather frames across cameras
│   │   └── preprocess.py       # letterbox/resize (GPU if possible)
│   ├── motion/
│   │   └── motion_gate.py
│   ├── tracking/
│   │   └── tracker.py          # ByteTrack per camera
│   ├── logic/
│   │   ├── base.py
│   │   ├── headcount.py
│   │   ├── desk_activity.py
│   │   └── theft.py
│   ├── events/
│   │   ├── publisher.py        # Redis
│   │   └── schemas.py
│   ├── monitoring/
│   │   └── metrics.py          # pynvml + per-stage timings
│   ├── pipeline.py             # orchestrator — wires everything
│   └── main.py
├── scripts/
│   ├── export_model.py
│   └── benchmark.py
├── requirements.txt
└── README.md
```

---

## 4. Build order (phases)

Build in this order so you always have a *working* system and can benchmark each gain.

- **Phase 0 — Environment.** Drivers, CUDA, TensorRT, libraries, headless server.
- **Phase 1 — Single camera, TensorRT.** Export YOLO26 → engine. One RTSP → NVDEC decode → engine → draw boxes. Prove the fast path works.
- **Phase 2 — Multi-camera + batching + queues.** All 15 cameras into threaded decoders → latest-frame buffers → one batched inference. This is where the big jump happens.
- **Phase 3 — Tracking + frame skip.** Detect every Nth frame, ByteTrack between.
- **Phase 4 — Motion gating + ROI.** Skip static frames; restrict to zones.
- **Phase 5 — Business logic + events.** Headcount, desk activity, theft rules → Redis.
- **Phase 6 — Monitoring, Docker, resilience.** Metrics, reconnection, autostart.

---

## 5. Component-by-component implementation

> Code below is skeleton-grade — correct in shape, adapt names/paths. Comments mark the production gotchas.

### 5.1 Environment setup (Phase 0)

```bash
# NVIDIA driver (matching CUDA 12.x for Ampere) + verify
nvidia-smi

# Headless: do NOT install a desktop environment on the server. Saves RAM + VRAM.

# Python env
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip

# Core libs
pip install ultralytics            # YOLO26 + export + ByteTrack built in
pip install onnx onnxruntime-gpu
pip install opencv-python           # use opencv-python (not headless) only if you need GUI; on a
                                    # headless server prefer opencv-python-headless
pip install redis pyyaml pynvml
# GPU decode (recommended, pip-installable):
pip install PyNvVideoCodec          # NVDEC straight to GPU tensors (zero-copy via DLPack)
# TensorRT: install matching your CUDA (via pip 'tensorrt' wheel or NVIDIA repo)
pip install tensorrt
```

Sanity-check NVDEC and TensorRT exist:
```bash
python -c "import tensorrt as trt; print(trt.__version__)"
python -c "import PyNvVideoCodec as nvc; print('nvdec ok')"
```

### 5.2 Model export: `.pt` → ONNX → TensorRT engine (Phase 1)

`scripts/export_model.py`:
```python
from ultralytics import YOLO

model = YOLO("models/yolo26n.pt")

# Export straight to a TensorRT engine with dynamic batch (up to 15) and FP16.
model.export(
    format="engine",     # TensorRT
    half=True,           # FP16 — uses your tensor cores
    dynamic=True,        # allow variable batch size
    batch=15,            # max batch = number of cameras
    imgsz=640,
    device=0,
    workspace=4,         # GB of scratch TRT may use while building (cap it for 8GB card)
)
# Produces models/yolo26n.engine
```

Notes:
- The engine is **built for THIS GPU**. Rebuild it on every machine model you ship to (a 3070 Ti engine won't run optimally — or at all — on a different card).
- Build once, cache the `.engine`. Building takes minutes; loading is fast.
- INT8 later (§9) gives more speed but needs a calibration set and accuracy validation. Start FP16.

### 5.3 Camera capture worker — NVDEC, threaded, drop-old (Phase 1→2)

You have two solid GPU-decode paths. Pick one.

**Option A — GStreamer via OpenCV (quick to wire, element names vary).**
```python
import cv2

def gst_pipeline(rtsp_url):
    # IMPORTANT: element names differ by platform.
    #  - Desktop dGPU with NVIDIA gst plugins: nvh264dec / nvh265dec (or 'nvdec')
    #  - Jetson / DeepStream installs: nvv4l2decoder
    # Test `gst-inspect-1.0 | grep nv` to see what you actually have.
    return (
        f"rtspsrc location={rtsp_url} latency=100 protocols=tcp ! "
        "rtph264depay ! h264parse ! nvh264dec ! "      # GPU decode
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink drop=true max-buffers=1 sync=false"    # <-- drop-old, no buffering
    )

cap = cv2.VideoCapture(gst_pipeline(url), cv2.CAP_GSTREAMER)
```
The `drop=true max-buffers=1` is the key line — it throws away stale frames so you always read the *current* scene.

**Option B — PyNvVideoCodec (cleanest GPU-native, recommended).** Decodes directly to GPU; hand frames to the model without a CPU round-trip.

Either way, wrap each camera in a **thread** that pushes the latest frame into a size-1 buffer:

`src/capture/rtsp_worker.py`:
```python
import threading, time, cv2

class CameraWorker(threading.Thread):
    def __init__(self, cam_id, url, buffer):
        super().__init__(daemon=True)
        self.cam_id, self.url, self.buffer = cam_id, url, buffer
        self.running = True

    def run(self):
        while self.running:
            cap = cv2.VideoCapture(gst_pipeline(self.url), cv2.CAP_GSTREAMER)
            if not cap.isOpened():
                time.sleep(2)               # reconnection backoff
                continue
            fail = 0
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    fail += 1
                    if fail > 30:           # camera died → reconnect
                        break
                    continue
                fail = 0
                self.buffer.put(self.cam_id, frame)   # overwrites old frame
            cap.release()
            time.sleep(1)                   # then loop → reconnect
```

### 5.4 Latest-frame buffer (drop-old)

`src/capture/frame_buffer.py`:
```python
import threading

class LatestFrameBuffer:
    """One slot per camera. New frame overwrites the old one. Never queues stale frames."""
    def __init__(self):
        self._frames = {}
        self._lock = threading.Lock()

    def put(self, cam_id, frame):
        with self._lock:
            self._frames[cam_id] = (frame, time.monotonic())

    def snapshot(self):
        # Return current frame for every camera that has one
        with self._lock:
            return {cid: f for cid, (f, _) in self._frames.items()}
```

### 5.5 Batch builder (Phase 2)

`src/inference/batch_builder.py`:
```python
def build_batch(buffer, active_cam_ids):
    frames, cam_order = [], []
    snap = buffer.snapshot()
    for cid in active_cam_ids:
        if cid in snap:
            frames.append(snap[cid])
            cam_order.append(cid)
    return frames, cam_order   # frames -> one inference call; cam_order maps results back
```

### 5.6 Inference worker — one engine, dynamic batch (Phase 2)

`src/inference/engine.py` (Ultralytics-loads-engine path — fastest to build):
```python
from ultralytics import YOLO

class Detector:
    def __init__(self, engine_path, imgsz=640, conf=0.35):
        self.model = YOLO(engine_path)     # loads the TensorRT .engine
        self.imgsz, self.conf = imgsz, conf

    def detect_batch(self, frames):
        # frames: list of images (1..15). ONE batched call.
        results = self.model.predict(frames, imgsz=self.imgsz,
                                     conf=self.conf, verbose=False, device=0)
        return results                     # list aligned to input order
```

The orchestrator loop (in `pipeline.py`) ties it together:
```python
frame_id = 0
while running:
    active = motion_gate.active_cameras()          # §5.8
    detect_now = [c for c in active if frame_id % DET_INTERVAL[c] == 0]
    if detect_now:
        frames, order = build_batch(buffer, detect_now)
        if frames:
            results = detector.detect_batch(frames)
            for cid, res in zip(order, results):
                dets = parse(res)
                tracks = trackers[cid].update(dets)   # §5.7
                logic[cid].process(tracks)            # §5.10
    else:
        # no detection this frame → trackers predict only
        for cid in active:
            trackers[cid].predict_only()
    frame_id += 1
```

### 5.7 Tracking — ByteTrack, detect-every-N (Phase 3)

Easiest: let Ultralytics run ByteTrack with `model.track(..., tracker="bytetrack.yaml")`. For per-camera control, use the standalone tracker (e.g. the `supervision` library's ByteTrack) so you keep one tracker instance **per camera**:

```python
# src/tracking/tracker.py
from supervision import ByteTrack   # or ultralytics' built-in
class CameraTracker:
    def __init__(self):
        self.bt = ByteTrack()
    def update(self, detections):
        return self.bt.update_with_detections(detections)
```

**Detection interval** (`DET_INTERVAL`) per camera, in `settings.yaml`:
- Busy entry/exit / theft zones: every **2nd** frame.
- Quiet desks: every **5th** frame.
- The tracker carries IDs between detections, so you run YOLO 5–15× less often.

### 5.8 Motion gating (Phase 4)

`src/motion/motion_gate.py`:
```python
import cv2
class MotionGate:
    def __init__(self):
        self.bg = {}   # one subtractor per camera
    def is_active(self, cam_id, frame, min_area=500):
        if cam_id not in self.bg:
            self.bg[cam_id] = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        small = cv2.resize(frame, (320, 180))      # cheap: run on a downscaled gray frame
        mask = self.bg[cam_id].apply(small)
        return int((mask > 0).sum()) > min_area    # enough motion?
```
**Caveat:** do not motion-gate theft / small-hand-movement zones — subtle activity can be missed. Use it for empty rooms, corridors, inactive desks. Make it per-zone in config.

### 5.9 ROI / zones (Phase 4)

Per camera, store zone polygons in `config/zones/<cam_id>.json`. Two uses:
- **Crop** to a zone before inference when only a small area matters (fewer pixels = less GPU).
- **Filter** detections by zone for logic ("person in restricted area", "object left desk zone").

```python
import numpy as np, cv2
def in_zone(point, polygon):
    return cv2.pointPolygonTest(np.array(polygon, np.int32), point, False) >= 0
```

### 5.10 Business logic (Phase 5)

`src/logic/base.py` — one handler per camera, stateful (uses track IDs over time):
```python
class LogicHandler:
    def __init__(self, cam_cfg): self.cfg = cam_cfg
    def process(self, tracks):  raise NotImplementedError
```
Examples:
- **Headcount:** count unique active track IDs of class `person` in a zone.
- **Desk activity:** person present + hand/object motion inside desk ROI over a time window.
- **Theft:** object (phone/bag/laptop) track disappears near a person track / crosses an exit zone → raise event. This is where track IDs matter — you reason about objects *over time*, not single frames.

### 5.11 Events / alerts (Phase 5)

`src/events/publisher.py`:
```python
import redis, json, time
class EventPublisher:
    def __init__(self, host="localhost"):
        self.r = redis.Redis(host=host)
    def emit(self, cam_id, event_type, payload):
        msg = {"cam": cam_id, "type": event_type, "ts": time.time(), **payload}
        self.r.xadd("cctv:events", {"data": json.dumps(msg)})   # Redis stream
```
Dashboards / DB writers / notifiers subscribe to `cctv:events` independently. This decouples detection from delivery.

### 5.12 Config (15 cameras)

`config/cameras.yaml`:
```yaml
cameras:
  - id: cam01
    url: "rtsp://user:pass@192.168.1.11:554/substream"   # use SUBSTREAM for AI
    det_interval: 3
    motion_gate: true
    logic: [headcount, desk_activity]
    zones_file: zones/cam01.json
  - id: cam02
    url: "rtsp://user:pass@192.168.1.12:554/substream"
    det_interval: 2
    motion_gate: false          # theft zone → never gate
    logic: [theft, headcount]
    zones_file: zones/cam02.json
  # ... cam03 .. cam15
```
`config/settings.yaml`:
```yaml
model:
  engine: models/yolo26n.engine
  imgsz: 640
  conf: 0.35
  max_batch: 15
pipeline:
  default_det_interval: 3
redis:
  host: localhost
```

### 5.13 Monitoring (Phase 6)

`src/monitoring/metrics.py` — track per-stage timings and GPU state. Use `pynvml` for GPU/VRAM/decoder utilisation:
```python
import pynvml
pynvml.nvmlInit()
h = pynvml.nvmlDeviceGetHandleByIndex(0)
def gpu_stats():
    util = pynvml.nvmlDeviceGetUtilizationRates(h)
    mem = pynvml.nvmlDeviceGetMemoryInfo(h)
    return {"gpu_util": util.gpu, "vram_used_mb": mem.used // 1024**2}
```
Log per camera: effective FPS, end-to-end latency, queue/drops. Watch the **decoder** column in `nvidia-smi dmon -s u` separately — it can saturate before compute does.

### 5.14 RTSP resilience

15 real cameras *will* drop. Built into §5.3: reconnect with backoff, per-camera failure counter, daemon threads so one dead camera never kills the pipeline. Add a watchdog that flags a camera as "down" in metrics if no frame arrives for N seconds.

---

## 6. VRAM & RAM management strategy (critical for 8 GB / 16 GB)

- **One engine, shared.** Single `Detector` instance for all 15 cameras.
- **YOLO26n at 640.** Upgrade to `s` only if accuracy fails; re-check VRAM headroom after.
- **Cap TensorRT workspace** at build time (`workspace=4`) so the build doesn't over-allocate.
- **Keep frames on the GPU** (PyNvVideoCodec / GStreamer NVMM) to avoid CPU↔GPU copies and to spare your 16 GB system RAM.
- **Headless server.** No desktop = more free VRAM and RAM.
- **Sub-stream for AI.** 1080p (or lower) sub-stream, not the 4K main stream.
- **Bounded everything.** Size-1 frame buffers; drop-old. No unbounded Python queues (they eat RAM and process stale video).
- Keep **~1.5–2 GB VRAM free** as headroom; if `nvmlDeviceGetMemoryInfo` shows < 1 GB free, reduce batch or imgsz.

---

## 7. Benchmark plan (with target numbers for your box)

Run `scripts/benchmark.py` at **1 → 2 → 4 → 8 → 15** cameras, same model / resolution / source. Log per config:

- FPS per camera **and** end-to-end latency (capture → event). Watch both — high FPS on stale frames is a failure.
- GPU util, **decoder util**, VRAM used.
- CPU util, system RAM.
- Stage timings: decode, preprocess, inference, postprocess, tracking, logic.
- Dropped/stale frames, queue depths.
- Accuracy delta: FP32 vs FP16 (and later INT8); detect-every-frame vs every-3rd.

**Targets you should be able to hit on the 3070 Ti** (YOLO26n FP16, 640, det-interval 3, motion gating on quiet cams):

| Cameras | Detection FPS/cam | GPU util | VRAM | Verdict |
|---|---|---|---|---|
| 1 | 30 (easily) | low | ~1.5 GB | trivial |
| 4 | 15–30 | moderate | ~2 GB | comfortable |
| 8 | 12–20 | higher | ~2.5 GB | comfortable |
| **15** | **8–12** | high, not pinned | **~3–4 GB** | **the goal — works with headroom** |

If at 15 cams GPU util pins ~100% *with* batching + frame-skip + motion-gating already on, only then consider INT8 (§9) or a second GPU.

---

## 8. Deployment

- **Docker** with the NVIDIA Container Toolkit; run `--gpus all`. Base image: an NVIDIA CUDA/TensorRT runtime image matching your driver.
- **docker-compose**: one service for the pipeline, one for Redis.
- **Autostart**: `systemd` unit (or `restart: unless-stopped` in compose) so it survives reboots.
- **Build the `.engine` inside the target machine's environment** (or a matching one) — engines are GPU/driver-specific.
- Logs + metrics to a volume; expose a small health endpoint.

---

## 9. Risks & tradeoffs (specific to this hardware)

- **8 GB ceiling.** Biggest risk. Adding heavy per-camera secondary models (pose, segmentation, ReID) will blow the budget. Add them only behind triggers, on cropped ROIs, not full-time on 15 streams.
- **INT8 accuracy.** INT8 buys speed but can hurt small-object detection (distant phones, small bags). Calibrate on real footage and validate before shipping. FP16 is the safe default.
- **Single NVDEC.** Fine for 15×1080p H.264. If cameras are 4K or you also decode main streams for recording, the decoder can saturate before compute — use sub-streams and prefer **H.265** (roughly half the decode load of H.264).
- **Frame-skip misses brief events.** Lower `det_interval` on theft/critical zones.
- **Motion-gating misses subtle activity.** Never gate theft/hand zones; combine with periodic forced detection.
- **GStreamer element naming.** Desktop NVDEC element names differ from Jetson docs — verify with `gst-inspect-1.0`. PyNvVideoCodec sidesteps this.
- **16 GB RAM.** Stay headless, keep buffers tiny; if you add many CPU-side logic processes, watch RAM.

---

## 10. Timeline / milestones

| Milestone | Deliverable | Rough effort |
|---|---|---|
| M0 | Env ready, `nvidia-smi`/TRT/NVDEC verified | 0.5 day |
| M1 | YOLO26n `.engine`; 1 camera NVDEC→engine→boxes | 1–2 days |
| M2 | 15 cameras, threaded decode, drop-old buffers, **batched** inference | 3–5 days |
| M3 | ByteTrack + detect-every-N | 2–3 days |
| M4 | Motion gating + ROI/zones | 2–3 days |
| M5 | Business logic (headcount/desk/theft) + Redis events | 4–7 days |
| M6 | Monitoring, Docker, reconnection, autostart, benchmark report | 3–5 days |

Each milestone is shippable and benchmarkable.

---

## 11. Cheat sheet

**Do immediately:**
1. Export YOLO26n → **TensorRT FP16 engine**, dynamic batch 15.
2. One **shared** engine, **batched** inference across cameras.
3. **NVDEC** decode in **threaded** workers with **drop-old** size-1 buffers.
4. **Detect every 3rd frame + ByteTrack.**
5. **Motion-gate** quiet cameras; **ROI** the rest.
6. Use camera **sub-streams** for the AI.
7. Profile decode / preprocess / inference / postprocess / tracking **separately**.

**Stop immediately:**
- One `model(frame)` call per camera / one model copy per camera.
- CPU decoding via plain `cv2.VideoCapture(rtsp)`.
- Unbounded queues / processing stale frames.
- Full-frame detection when a zone is enough.
- Running `.pt` PyTorch in production.
- Segmentation when detection is enough.
- 1280px or 4K inference across 15 streams on this 8 GB card.

**The one-line mindset shift:** *not* "one camera = one YOLO loop," but "**15 cameras feed one optimized GPU pipeline.**"

**Skip (for your scale):** DeepStream (revisit only if you push toward 30+ cams/box), Triton, Kubernetes.