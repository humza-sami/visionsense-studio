# Project Progress Log

## [2026-06-30] - GPU LIVE: driver+CUDA+TensorRT, engine, Redis, NVDEC verified
**Agent:** claude-opus-4-8

### What Changed (this box is now a working GPU deployment)
* **NVIDIA stack installed & active**: driver 595.71.05 (nvidia-driver-595-open, DKMS),
  rebooted to swap nouveau→nvidia. `nvidia-smi` sees the RTX 3070 Ti. Passwordless sudo
  was granted by the user to do this.
* **CUDA PyTorch + TensorRT** in the venv: `torch 2.6.0+cu124`, `tensorrt-cu12 11.1.0.106`.
* **TensorRT engine built**: `models/yolo26n.engine`. Ultralytics' native export wanted a
  ~4 GB `nvidia-modelopt[onnx]` tree (and would clobber torch), so we build the engine
  directly from the ONNX via the TRT Python API — `scripts/build_engine_from_onnx.py`.
  This TRT-11 binding dropped the global FP16 BuilderFlag (strongly-typed networks); we
  enable TF32 (Ampere tensor cores). Engine bench: **batch-15 = 23.5 fps/cam, 3.1 GB VRAM**
  — beats the plan's 8–12 fps/cam target. Inference dropped 32 ms (.pt) → 11 ms (engine).
* **Detector fix**: pass `rect=False` so square 640×640 letterbox matches the engine's
  static H×W (only batch is dynamic); rect inference fed 384×640 and failed the shape check.
* **Redis live**: `redis-server` installed + enabled (systemd); `redis.enabled: true`.
  Verified events publish to the `cctv:events` stream (XADD/XREVRANGE).
* **NVDEC verified**: installed GStreamer + nvcodec; `nvh264dec` hardware-decodes H.264
  (decoder util confirmed on nvidia-smi). Fixed the capture pipeline to insert
  `cudadownload` before `videoconvert` (nvcodec outputs CUDA memory).
* **Config**: all 15 real cameras (Dahua NVR, substream subtype=1) + an always-on `cam-demo`
  (local H.264 clip) so the dashboard shows live detection regardless of camera reachability.
* **Autostart**: `deploy/visionsense.service` + `deploy/install_service.sh` (systemd, runs
  on boot, restarts on failure, auto-reconnects cameras).

### Blocker (external, not code)
* **The 15 RTSP cameras are unreachable from this box.** The NVR's public IP
  103.83.89.187 is dead on every port (554/80/37777/8000) from here, and outbound :554 to
  the public internet is firewalled. The cameras come online automatically (worker reconnect)
  the moment a path is opened: open outbound TCP 554, OR use the NVR's LAN IP if this server
  is on the same network, OR VPN. Nothing in software can bypass a blocked network path.

## [2026-06-30] - Verified end-to-end on the Ubuntu/RTX box + UI + GPU bootstrap
**Agent:** claude-opus-4-8

### What Changed
* **Stood up a runnable env on the bare RTX box** with `uv` (no sudo): Python 3.12 venv,
  CPU torch 2.12, ultralytics 8.4.83, supervision 0.29, opencv-headless, fastapi.
* **Ran the WHOLE pipeline end-to-end** (capture→buffer→motion→batch→detect→ByteTrack→
  logic→events→MJPEG) against a synthetic people clip. Verified: 1000 frames read,
  batched inference (~93ms/CPU), IDs tracked, headcount event emitted, annotated frames,
  and all API endpoints (`/health /status /events /stream /`) serving. **Smoke test PASSES.**
* **Confirmed `yolo26n.pt` is real** and downloads from ultralytics assets v8.4.0 — the
  configured weight name was correct; no fallback needed. Cached to `models/`.
* **Improved the dashboard UI** (PLAN.md "Frontend UI" task): per-tile live status dot +
  detect-fps + object-count badges, a live **Events feed** panel, richer header stats.
* **New scripts:** `scripts/setup_gpu.sh` (idempotent driver/CUDA-torch/TensorRT/redis/
  engine bootstrap — the sudo step), `scripts/make_test_video.py`, `scripts/smoke_test.py`.
* **requirements.txt:** pinned `supervision<0.30` (sv.ByteTrack is removed in 0.30) and
  switched to `opencv-python-headless` (no libGL on a headless server).

### Decisions & Tradeoffs
* GPU stack (driver/CUDA/TensorRT/.engine) is **not installed here — this box has no sudo
  and no NVIDIA driver yet.** The CPU `.pt` path is fully verified; the `.engine` path is
  unchanged and auto-selects once `setup_gpu.sh` is run with sudo + a reboot.

### Handoff Notes (read this first, next agent)
* To finish the GPU path: `bash scripts/setup_gpu.sh` (needs sudo; reboots once for the
  driver, then re-run). It builds `models/yolo26n.engine` for this exact 3070 Ti.
* Activate env: `export PATH="$HOME/.local/bin:$PATH"` then use `.venv/bin/python`.
* Re-verify anytime: `.venv/bin/python scripts/smoke_test.py` (no camera/GPU needed).
* Real cameras: set substream URLs + `enabled: true` in `config/cameras.yaml`.

## [2026-06-30] - CCTV detection backend scaffold (full pipeline)
**Agent:** claude-opus-4-8

### What Changed
* Built entire backend per PLAN.md under `src/` (capture→buffer→motion→batch→infer→ByteTrack→logic→events→FastAPI MJPEG dashboard); scripts/, docker/, README, config/.
* macOS↔Ubuntu seam: `inference/engine.py` (.pt CPU/MPS ↔ TensorRT .engine CUDA) + `capture/capture_source.py` (cv2/FFmpeg ↔ GStreamer NVDEC), auto-selected at runtime.
* All files `py_compile`-clean. Deps NOT installed locally yet (no venv).

### Decisions & Tradeoffs
* One shared Detector via Ultralytics (loads .pt or .engine). Per-camera ByteTrack via `supervision`. Redis optional (in-memory ring fallback).

### Handoff Notes (read this first, next agent)
* Not yet run end-to-end — only compiled. Next: `pip install -r requirements.txt`, `python -m src.main`, open http://localhost:8000/.
* YOLO26 weight name unverified; if download fails set `model.weights` to `yolo11n.pt`.
* On Ubuntu: `scripts/export_model.py` to build the .engine (GPU-specific); pip opencv has NO GStreamer → NVDEC path needs system OpenCV or PyNvVideoCodec (stub in capture_source.py).
