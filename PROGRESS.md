# Project Progress Log

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
