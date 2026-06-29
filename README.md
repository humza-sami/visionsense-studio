# VisionSense Studio — Multi-Camera CCTV Detection Backend

Decoupled producer–consumer pipeline for running YOLO across many RTSP cameras on a
single GPU. Built per [PLAN.md](PLAN.md). **Dev on macOS, deploy on Ubuntu/NVIDIA**
with no code changes — only two adapters and the model artifact swap.

```
capture threads → latest-frame buffer → motion gate → batch builder →
ONE batched inference → per-camera ByteTrack → business logic → events + live preview
```

## The macOS ↔ Ubuntu seam

Everything is identical on both OSes except two pluggable layers, chosen
automatically at runtime:

| Layer | macOS dev | Ubuntu prod |
|---|---|---|
| **Compute** ([src/inference/engine.py](src/inference/engine.py)) | `.pt` on CPU/MPS | TensorRT `.engine` on CUDA FP16 |
| **Decode** ([src/capture/capture_source.py](src/capture/capture_source.py)) | `cv2` FFmpeg/webcam | GStreamer NVDEC (or PyNvVideoCodec) |
| GPU telemetry ([metrics.py](src/monitoring/metrics.py)) | unavailable (graceful) | `pynvml` |

`model.device: auto` resolves `cuda > mps > cpu`. If a CUDA device is present and
`models/*.engine` exists, the engine is loaded; otherwise the `.pt` is used.

## Run on macOS (today)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

Open **http://localhost:8000/** for the live detection grid. `config/cameras.yaml`
ships with `cam01` = your webcam so the whole pipeline runs locally. The first run
downloads the YOLO weights.

> **Model name:** the plan targets **YOLO26** (`models/yolo26n.pt`). If that weight
> isn't fetchable from your Ultralytics version yet, set `model.weights` in
> `config/settings.yaml` (or `MODEL_WEIGHTS` env) to a shipping model such as
> `yolo11n.pt` — it's just a string the loader passes to Ultralytics.

## Move to Ubuntu (tomorrow)

```bash
# 1. Install GPU extras (NOT on macOS):
pip install -r requirements.txt
pip install tensorrt onnx onnxruntime-gpu pynvml PyNvVideoCodec

# 2. Build the TensorRT engine ON THIS GPU (engines are GPU/driver-specific):
python scripts/export_model.py models/yolo26n.pt 640 15      # → models/yolo26n.engine

# 3. Point real cameras at the SUBSTREAM, enable them in config/cameras.yaml,
#    set capture.backend + model.device as needed, then:
python -m src.main
# or containerised:
docker compose -f docker/docker-compose.yml up --build
```

Benchmark the box: `python scripts/benchmark.py 15 50` (target: ~8–12 FPS/cam @ 15).

### Prod decode note (important)
The pip `opencv-python` wheel is **not built with GStreamer**, so the NVDEC
GStreamer path won't activate from a pip install — capture falls back to FFmpeg
(CPU decode). For true GPU decode on the server, either install GStreamer + an
OpenCV build with GStreamer support, or wire the `pynvc` backend
(PyNvVideoCodec) in [capture_source.py](src/capture/capture_source.py) (stub
marked there). The pipeline runs correctly either way; only decode placement
(CPU vs NVDEC) differs.

## API

| Endpoint | What |
|---|---|
| `GET /` | Live MJPEG grid dashboard |
| `GET /stream/{cam_id}` | Annotated MJPEG for one camera |
| `GET /status` | Per-cam FPS, loop FPS, GPU/VRAM, worker health |
| `GET /events?limit=100` | Recent business-logic events |
| `GET /health` | Liveness |

## Config

- [config/settings.yaml](config/settings.yaml) — model, pipeline, capture, API, redis.
- [config/cameras.yaml](config/cameras.yaml) — per-camera URL, `det_interval`,
  `motion_gate`, `logic`, `zones_file`, `enabled`.
- [config/zones/](config/zones/) — per-camera ROI polygons (see `cam02.json`).

## Layout

```
src/
  capture/    capture_source (OS seam), frame_buffer (drop-old), rtsp_worker (thread+reconnect)
  inference/  engine (Detector, OS seam), batch_builder, preprocess (ROI crop)
  motion/     motion_gate (MOG2)
  tracking/   tracker (per-camera ByteTrack via supervision)
  logic/      headcount, desk_activity, theft  (+ registry)
  events/     publisher (redis + in-memory ring), schemas
  monitoring/ metrics (pynvml + FPS)
  zones.py viz.py types.py config.py pipeline.py api.py main.py
scripts/      export_model.py (→ TensorRT), benchmark.py
docker/       Dockerfile, docker-compose.yml
```

## What's stubbed / deferred
- **PyNvVideoCodec** zero-copy NVDEC path (returns GPU tensors) — marked TODO; FFmpeg/GStreamer used instead.
- **ByteTrack gap-filling**: between detection frames the last tracks are reused for display (IDs persist via the tracker on detection frames).
- INT8 calibration, DeepStream/Triton — out of scope per plan (revisit at 30+ cams/box).
