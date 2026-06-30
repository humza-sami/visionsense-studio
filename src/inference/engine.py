"""Detector: ONE shared model, batched inference. The macOS/Ubuntu seam for compute.

Same Ultralytics interface loads either a `.pt` (dev: CPU/MPS) or a TensorRT
`.engine` (prod: CUDA FP16). Selection is automatic:

  • If model.device resolves to CUDA *and* the .engine file exists → load .engine.
  • Otherwise → load the .pt on the best available device (cuda > mps > cpu).

This is the single most important rule from the plan: one engine instance shared
across all cameras, never one model per camera.
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.config import ModelConfig
from src.types import Detection

log = logging.getLogger("inference")


def select_device(requested: str) -> str:
    """Resolve 'auto' to the best device available on this machine."""
    if requested and requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


class Detector:
    def __init__(self, cfg: ModelConfig) -> None:
        from ultralytics import YOLO

        self.cfg = cfg
        self.device = select_device(cfg.device)
        self.model_path = self._choose_model_path()
        log.info("Loading model '%s' on device '%s'", self.model_path, self.device)
        self.model = YOLO(self.model_path)
        self.names: dict[int, str] = self.model.names  # id -> class name

    def _choose_model_path(self) -> str:
        is_cuda = str(self.device).startswith("cuda")
        engine = Path(self.cfg.engine)
        if is_cuda and engine.exists():
            return str(engine)
        if is_cuda and not engine.exists():
            log.warning(
                "CUDA device but no engine at %s — falling back to %s (.pt). "
                "Run scripts/export_model.py on this box for the fast path.",
                engine, self.cfg.weights,
            )
        return self.cfg.weights

    def detect_batch(self, frames: list) -> list[list[Detection]]:
        """One batched inference call over N frames. Returns per-frame detections."""
        if not frames:
            return []
        results = self.model.predict(
            frames,
            imgsz=self.cfg.imgsz,
            conf=self.cfg.conf,
            iou=self.cfg.iou,
            classes=self.cfg.classes,
            device=self.device,
            verbose=False,
            # Square letterbox (no rectangular inference). The TensorRT engine is
            # built with static H×W (only batch is dynamic), so every frame must be
            # padded to imgsz×imgsz; rect inference would feed e.g. 384×640 and fail
            # the engine's shape check. Harmless (and consistent) for the .pt path too.
            rect=False,
        )
        return [self._parse(r) for r in results]

    def _parse(self, result) -> list[Detection]:
        dets: list[Detection] = []
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return dets
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)
        for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
            dets.append(
                Detection(
                    xyxy=(float(x1), float(y1), float(x2), float(y2)),
                    conf=float(c),
                    cls_id=int(k),
                    cls_name=self.names.get(int(k), str(k)),
                )
            )
        return dets
