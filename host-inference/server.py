#!/usr/bin/env python3
"""
VisionSense Host Inference Server
Runs on the Mac host (outside Docker) to access Metal / CoreML.

Usage:  ./start.sh
        # or: python server.py

Listens on http://0.0.0.0:9020
Docker backend calls: POST /infer
"""
from __future__ import annotations

import base64
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import torch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("host-inference")

# ── Device selection ──────────────────────────────────────────────────────────

if torch.backends.mps.is_available():
    DEVICE = "mps"
    logger.info("Device: Metal Performance Shaders (MPS) — M-series GPU ✓")
elif torch.cuda.is_available():
    DEVICE = "cuda"
    logger.info("Device: CUDA GPU")
else:
    DEVICE = "cpu"
    logger.warning("Device: CPU (no GPU found)")

# ── Model cache ───────────────────────────────────────────────────────────────

_model_cache: Dict[str, Any] = {}


def _load_model(name: str):
    from ultralytics import YOLO
    if name not in _model_cache:
        logger.info(f"Loading {name} on {DEVICE} ...")
        m = YOLO(name)
        # Warm-up pass so first real frame isn't slow
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        m.predict(dummy, imgsz=320, verbose=False, device=DEVICE)
        _model_cache[name] = m
        logger.info(f"Ready: {name}")
    return _model_cache[name]


def _resolve_model(base_name: str, features: "InferFeatures") -> str:
    """Build full model filename from bare size + active features."""
    b = re.sub(r"-(pose|seg|obb|cls)(\.pt)?$", "", base_name)
    b = re.sub(r"\.pt$", "", b)
    if features.keypoints:
        return f"{b}-pose.pt"
    if features.masks or features.semantic:
        return f"{b}-seg.pt"
    if features.obb:
        return f"{b}-obb.pt"
    return f"{b}.pt"


# ── Trail tracker (per-stream, keyed by cam_id) ───────────────────────────────

class TrailTracker:
    def __init__(self, max_len: int = 40):
        self._trails: Dict[int, deque] = defaultdict(lambda: deque(maxlen=max_len))

    def update(self, track_id: int, cx: float, cy: float):
        self._trails[track_id].append((cx, cy))

    def snapshot(self, active_ids: set) -> Dict[int, list]:
        # prune stale
        for tid in list(self._trails):
            if tid not in active_ids:
                del self._trails[tid]
        return {
            tid: [[round(x, 4), round(y, 4)] for x, y in pts]
            for tid, pts in self._trails.items()
        }


_trail_trackers: Dict[str, TrailTracker] = defaultdict(TrailTracker)

# ── Startup model preload ─────────────────────────────────────────────────────
# Sizes to preload (X skipped by default — ~135MB each variant)
# Override via env: PRELOAD_SIZES="n,s,m,l,x"
_PRELOAD_SIZES = os.environ.get("PRELOAD_SIZES", "n,s,m,l").lower().split(",")

# All variant suffixes per feature task
_VARIANTS = [".pt", "-seg.pt", "-pose.pt", "-obb.pt"]

# ── Request / Response models ─────────────────────────────────────────────────


class InferFeatures(BaseModel):
    boxes: bool = False
    masks: bool = False
    keypoints: bool = False
    obb: bool = False
    semantic: bool = False
    labels: bool = True
    trails: bool = False


class InferRequest(BaseModel):
    frame_b64: str
    model: str = "yolo26n"
    conf: float = 0.5
    iou: float = 0.45
    imgsz: int = 512
    features: InferFeatures = InferFeatures()
    tracking_enabled: bool = False
    tracker: str = "bytetrack"
    cam_id: str = "default"


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="VisionSense Host Inference", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _preload_all_models():
    """Download + warm-up all model variants in the background at startup."""
    models_to_load = [
        f"yolo26{size}{variant}"
        for size in _PRELOAD_SIZES
        for variant in _VARIANTS
    ]
    logger.info(f"Preloading {len(models_to_load)} models in background: {', '.join(models_to_load)}")
    for name in models_to_load:
        if name not in _model_cache:
            try:
                _load_model(name)
            except Exception as e:
                logger.warning(f"Preload failed for {name}: {e}")
    logger.info("All models preloaded and ready.")


class WarmupRequest(BaseModel):
    model: str = "yolo26n"
    features: InferFeatures = InferFeatures()


@app.on_event("startup")
async def on_startup():
    # Fire preload in a daemon thread so the server starts immediately
    t = threading.Thread(target=_preload_all_models, daemon=True, name="preloader")
    t.start()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "models_loaded": list(_model_cache.keys()),
        "torch_version": torch.__version__,
    }


@app.post("/warmup")
async def warmup(req: WarmupRequest):
    """Pre-load a model into the cache without sending a frame.
    Called by the backend when the pipeline model changes so the model
    is ready before the next inference request arrives."""
    import asyncio
    model_name = _resolve_model(req.model, req.features)
    if model_name in _model_cache:
        return {"status": "already_loaded", "model": model_name, "device": DEVICE}
    # Load in a thread so we don't block the event loop
    loop = asyncio.get_event_loop()
    t0 = time.perf_counter()
    try:
        await loop.run_in_executor(None, _load_model, model_name)
        load_ms = round((time.perf_counter() - t0) * 1000)
        logger.info(f"Warmup complete: {model_name} in {load_ms}ms")
        return {"status": "loaded", "model": model_name, "device": DEVICE, "load_ms": load_ms}
    except Exception as e:
        logger.error(f"Warmup failed for {model_name}: {e}")
        return {"status": "error", "model": model_name, "error": str(e)}


@app.post("/infer")
async def infer(req: InferRequest):
    t0 = time.perf_counter()

    # ── Decode JPEG frame ──────────────────────────────────────────────────
    try:
        img_bytes = base64.b64decode(req.frame_b64)
        arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"error": "bad frame", "inference_ms": 0, "detections": [], "counts": {}}
    except Exception as e:
        return {"error": str(e), "inference_ms": 0, "detections": [], "counts": {}}

    h, w = frame.shape[:2]

    # ── Load model ─────────────────────────────────────────────────────────
    model_name = _resolve_model(req.model, req.features)
    try:
        model = _load_model(model_name)
    except Exception as e:
        logger.error(f"Model load failed: {e}")
        return {"error": str(e), "inference_ms": 0, "detections": [], "counts": {}}

    # ── Run inference ──────────────────────────────────────────────────────
    kwargs: dict = dict(
        conf=req.conf,
        iou=req.iou,
        imgsz=req.imgsz,
        verbose=False,
        device=DEVICE,
    )

    try:
        if req.tracking_enabled:
            result_list = model.track(
                frame, persist=True,
                tracker=f"{req.tracker}.yaml",
                **kwargs,
            )
        else:
            result_list = model.predict(frame, **kwargs)
        results = result_list[0] if result_list else None
    except Exception as e:
        logger.warning(f"Inference error: {e}")
        return {"error": str(e), "inference_ms": 0, "detections": [], "counts": {}}

    inference_ms = round((time.perf_counter() - t0) * 1000, 1)

    if results is None:
        return {"inference_ms": inference_ms, "detections": [], "counts": {}}

    counts = _count_classes(results)
    detections = _extract_detections(results, w, h)

    # ── Update trails ──────────────────────────────────────────────────────
    trails: Dict[str, list] = {}
    if req.features.trails:
        tracker = _trail_trackers[req.cam_id]
        active_ids: set = set()
        for det in detections:
            if det.get("track_id") is not None:
                tid = det["track_id"]
                cx = (det["x1"] + det["x2"]) / 2
                cy = (det["y1"] + det["y2"]) / 2
                tracker.update(tid, cx, cy)
                active_ids.add(tid)
        trails = {str(k): v for k, v in tracker.snapshot(active_ids).items()}

    return {
        "inference_ms": inference_ms,
        "detections": detections,
        "counts": counts,
        "trails": trails,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_classes(results) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    try:
        if results.boxes is None:
            return counts
        for cls_id in results.boxes.cls.tolist():
            name = results.names.get(int(cls_id), str(cls_id))
            counts[name] = counts.get(name, 0) + 1
    except Exception:
        pass
    return counts


def _extract_detections(results, width: int, height: int) -> List[Dict[str, Any]]:
    detections: List[Dict[str, Any]] = []
    try:
        boxes = results.boxes
        if boxes is None:
            return detections

        kp_data = None
        try:
            if hasattr(results, "keypoints") and results.keypoints is not None:
                kp_data = results.keypoints.data
        except Exception:
            pass

        mask_polygons: list = []
        try:
            if hasattr(results, "masks") and results.masks is not None:
                if hasattr(results.masks, "xyn") and results.masks.xyn is not None:
                    mask_polygons = list(results.masks.xyn)
                elif hasattr(results.masks, "xy") and results.masks.xy is not None:
                    mask_polygons = [
                        p / np.array([width, height], dtype=np.float32)
                        for p in results.masks.xy
                    ]
        except Exception:
            pass

        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            cls_id = int(box.cls[0])
            track_id = None
            if boxes.id is not None:
                try:
                    track_id = int(boxes.id[i])
                except Exception:
                    pass

            keypoints = None
            if kp_data is not None and i < len(kp_data):
                try:
                    kp = kp_data[i].cpu().numpy()
                    keypoints = [
                        [
                            round(max(0.0, min(1.0, float(pt[0]) / width)), 4),
                            round(max(0.0, min(1.0, float(pt[1]) / height)), 4),
                            round(float(pt[2]), 3),
                        ]
                        for pt in kp
                    ]
                except Exception:
                    pass

            segments = None
            if mask_polygons and i < len(mask_polygons):
                try:
                    poly = mask_polygons[i]
                    step = max(1, len(poly) // 80)
                    segments = [
                        [round(float(p[0]), 4), round(float(p[1]), 4)]
                        for p in poly[::step]
                    ]
                except Exception:
                    pass

            detections.append({
                "x1": max(0.0, min(1.0, x1 / width)),
                "y1": max(0.0, min(1.0, y1 / height)),
                "x2": max(0.0, min(1.0, x2 / width)),
                "y2": max(0.0, min(1.0, y2 / height)),
                "class_id": cls_id,
                "label": results.names.get(cls_id, str(cls_id)),
                "confidence": round(float(box.conf[0]), 4),
                "track_id": track_id,
                "keypoints": keypoints,
                "segments": segments,
            })
    except Exception as e:
        logger.warning(f"Extraction error: {e}")
    return detections


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting host inference server on :9020 (device={DEVICE})")
    uvicorn.run(app, host="0.0.0.0", port=9020, log_level="warning")
