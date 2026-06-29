# Project Progress Log

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
