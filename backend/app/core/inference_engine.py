"""
YOLO inference engine wrapping Ultralytics.

Features:
- Model cache (load once, reuse across frames)
- All YOLO tasks: detect, segment, pose, obb, classify
- Tracking via model.track() with ByteTrack / BoT-SORT
- Feature rendering: boxes, masks, keypoints, trails, OBB
- Open-vocab (YOLO-World / YOLOE) via open_vocab_prompt
- Graceful fallback if model fails to load
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from app.models.camera import PipelineConfig

logger = logging.getLogger(__name__)


# ── Model cache ────────────────────────────────────────────────────────────────

_model_cache: Dict[str, Any] = {}


def _load_model(model_name: str, device: str = "cpu"):
    """Load a YOLO model, returning from cache if already loaded."""
    cache_key = f"{model_name}@{device}"
    if cache_key not in _model_cache:
        try:
            from ultralytics import YOLO
            logger.info(f"Loading model: {model_name} on {device}")
            model = YOLO(model_name)
            model.to(device)
            _model_cache[cache_key] = model
            logger.info(f"Model loaded: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load model '{model_name}': {e}")
            _model_cache[cache_key] = None
    return _model_cache[cache_key]


def clear_model_cache():
    """Release all cached models."""
    _model_cache.clear()


# ── Trail tracker ─────────────────────────────────────────────────────────────

class TrailTracker:
    """Maintains per-track-id position history for motion trail rendering."""

    def __init__(self, max_len: int = 30):
        self._trails: Dict[int, deque] = defaultdict(lambda: deque(maxlen=max_len))

    def update(self, track_id: int, cx: float, cy: float):
        self._trails[track_id].append((int(cx), int(cy)))

    def draw(self, frame: np.ndarray, track_id: int, color=(0, 255, 200)):
        pts = list(self._trails.get(track_id, []))
        for i in range(1, len(pts)):
            alpha = int(200 * i / len(pts))
            cv2.line(frame, pts[i - 1], pts[i], (*color[:2], alpha), 2)

    def prune(self, active_ids: set):
        """Remove stale track ids."""
        for tid in list(self._trails.keys()):
            if tid not in active_ids:
                del self._trails[tid]


# ── Inference engine ──────────────────────────────────────────────────────────

class InferenceEngine:
    """
    Runs YOLO inference on a single frame and returns:
    - annotated_frame (np.ndarray, BGR)
    - results (ultralytics Results or None)
    - telemetry dict
    """

    def __init__(self, device: str = "cpu"):
        self._device = device
        self._trails = TrailTracker(max_len=40)
        self._current_model_key: Optional[str] = None
        self._current_model = None

    # ── Model management ──────────────────────────────────────────────────────

    def _get_model(self, pipeline: PipelineConfig):
        """Return the correct model, reloading if the config changed."""
        key = f"{pipeline.model}@{self._device}"
        if key != self._current_model_key:
            self._current_model = _load_model(pipeline.model, self._device)
            self._current_model_key = key
        return self._current_model

    # ── Main inference call ───────────────────────────────────────────────────

    def infer(
        self,
        frame: np.ndarray,
        pipeline: PipelineConfig,
    ) -> Tuple[np.ndarray, Any, Dict[str, Any]]:
        """
        Run inference on a single BGR frame.

        Returns:
            annotated_frame: BGR ndarray with overlays applied
            results: raw ultralytics Results (or None)
            telemetry: dict with inference_ms, counts, etc.
        """
        t0 = time.perf_counter()
        annotated = frame.copy()
        results = None
        telemetry: Dict[str, Any] = {"inference_ms": 0.0, "counts": {}}

        model = self._get_model(pipeline)
        if model is None:
            # Draw "model unavailable" banner
            cv2.putText(annotated, "Model unavailable", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            return annotated, None, telemetry

        try:
            results = self._run_model(model, frame, pipeline)
        except Exception as e:
            logger.warning(f"Inference error: {e}")
            cv2.putText(annotated, f"Inference error: {e}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            return annotated, None, telemetry

        # Render overlays based on feature flags
        if results is not None:
            annotated = self._render(annotated, results, pipeline)
            telemetry["counts"] = self._count_classes(results)

        t1 = time.perf_counter()
        telemetry["inference_ms"] = round((t1 - t0) * 1000, 1)
        return annotated, results, telemetry

    # ── Model execution ───────────────────────────────────────────────────────

    def _run_model(self, model, frame: np.ndarray, pipeline: PipelineConfig):
        """
        Choose between track() and predict() based on pipeline config.
        Returns first Result object or None.
        """
        task = pipeline.task
        conf = pipeline.thresholds.confidence
        iou = pipeline.thresholds.iou
        verbose = False

        # Set open-vocab classes if prompt is provided
        kwargs: Dict[str, Any] = dict(conf=conf, iou=iou, verbose=verbose)

        if pipeline.open_vocab_prompt:
            try:
                model.set_classes(pipeline.open_vocab_prompt)
            except AttributeError:
                pass  # Not a YOLO-World model

        if pipeline.tracking.enabled:
            tracker_cfg = f"{pipeline.tracking.tracker}.yaml"
            result_list = model.track(
                frame,
                persist=True,
                tracker=tracker_cfg,
                **kwargs,
            )
        else:
            result_list = model.predict(frame, **kwargs)

        return result_list[0] if result_list else None

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, frame: np.ndarray, results, pipeline: PipelineConfig) -> np.ndarray:
        features = pipeline.features

        if features.semantic:
            frame = self._render_semantic(frame, results)
            return frame  # semantic is full-frame, don't stack

        active_ids: set = set()

        # Iterate detections
        try:
            boxes = results.boxes
        except AttributeError:
            boxes = None

        if boxes is not None and len(boxes):
            for i, box in enumerate(boxes):
                try:
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = results.names.get(cls_id, str(cls_id))
                    color = self._class_color(cls_id)

                    track_id = None
                    if boxes.id is not None:
                        try:
                            track_id = int(boxes.id[i])
                            active_ids.add(track_id)
                        except Exception:
                            pass

                    # Trails
                    if features.trails and track_id is not None:
                        cx = (x1 + x2) / 2
                        cy = (y1 + y2) / 2
                        self._trails.update(track_id, cx, cy)
                        self._trails.draw(frame, track_id, color)

                    # Boxes
                    if features.boxes:
                        if features.obb:
                            # OBB rendering handled separately below
                            pass
                        else:
                            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    # Labels
                    if features.labels:
                        label = class_name
                        if track_id is not None:
                            label = f"#{track_id} {label}"
                        label += f" {conf:.2f}"
                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
                        cv2.putText(frame, label, (x1 + 2, y1 - 4),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
                except Exception as e:
                    logger.debug(f"Box render error at index {i}: {e}")

        # Masks (segmentation)
        if features.masks:
            frame = self._render_masks(frame, results)

        # Keypoints (pose)
        if features.keypoints:
            frame = self._render_keypoints(frame, results)

        # OBB
        if features.obb:
            frame = self._render_obb(frame, results)

        # Prune stale trails
        if features.trails:
            self._trails.prune(active_ids)

        # Classify: frame-level label
        if pipeline.task == "classify":
            frame = self._render_classify(frame, results)

        return frame

    def _render_masks(self, frame: np.ndarray, results) -> np.ndarray:
        try:
            if results.masks is None:
                return frame
            h, w = frame.shape[:2]
            overlay = frame.copy()
            for i, mask in enumerate(results.masks.data):
                mask_np = mask.cpu().numpy()
                mask_resized = cv2.resize(mask_np, (w, h))
                binary = (mask_resized > 0.5).astype(np.uint8)
                cls_id = int(results.boxes.cls[i]) if results.boxes is not None else i
                color = self._class_color(cls_id)
                colored_mask = np.zeros_like(frame)
                colored_mask[binary == 1] = color
                overlay = cv2.addWeighted(overlay, 1.0, colored_mask, 0.4, 0)
            return overlay
        except Exception as e:
            logger.debug(f"Mask render error: {e}")
            return frame

    def _render_keypoints(self, frame: np.ndarray, results) -> np.ndarray:
        try:
            if results.keypoints is None:
                return frame
            # COCO skeleton pairs (17-keypoint model)
            SKELETON = [
                (0, 1), (0, 2), (1, 3), (2, 4),
                (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
                (5, 11), (6, 12), (11, 12),
                (11, 13), (13, 15), (12, 14), (14, 16),
            ]
            for person_kps in results.keypoints.data:
                kps = person_kps.cpu().numpy()  # (N, 3): x, y, conf
                valid = [(int(kps[i, 0]), int(kps[i, 1])) for i in range(len(kps))
                         if kps[i, 2] > 0.3]
                for pt in valid:
                    cv2.circle(frame, pt, 4, (0, 255, 0), -1)
                for a, b in SKELETON:
                    if a < len(kps) and b < len(kps) and kps[a, 2] > 0.3 and kps[b, 2] > 0.3:
                        pa = (int(kps[a, 0]), int(kps[a, 1]))
                        pb = (int(kps[b, 0]), int(kps[b, 1]))
                        cv2.line(frame, pa, pb, (0, 200, 255), 2)
            return frame
        except Exception as e:
            logger.debug(f"Keypoint render error: {e}")
            return frame

    def _render_obb(self, frame: np.ndarray, results) -> np.ndarray:
        try:
            if not hasattr(results, "obb") or results.obb is None:
                return frame
            for i, obb in enumerate(results.obb.xywhr):
                x, y, w, h, r = obb.tolist()
                cls_id = int(results.obb.cls[i]) if results.obb.cls is not None else 0
                color = self._class_color(cls_id)
                # Draw rotated rectangle
                rect = ((x, y), (w, h), float(np.degrees(r)))
                box_pts = cv2.boxPoints(rect).astype(np.int32)
                cv2.drawContours(frame, [box_pts], 0, color, 2)
            return frame
        except Exception as e:
            logger.debug(f"OBB render error: {e}")
            return frame

    def _render_semantic(self, frame: np.ndarray, results) -> np.ndarray:
        try:
            if results.masks is None:
                return frame
            h, w = frame.shape[:2]
            # Build per-pixel class map
            seg_map = np.zeros((h, w), dtype=np.int32)
            for i, mask in enumerate(results.masks.data):
                mask_np = cv2.resize(mask.cpu().numpy(), (w, h))
                seg_map[mask_np > 0.5] = i % 256

            # Color map
            color_map = np.random.randint(0, 255, (256, 3), dtype=np.uint8)
            colored = color_map[seg_map]
            frame = cv2.addWeighted(frame, 0.6, colored, 0.4, 0)
            return frame
        except Exception as e:
            logger.debug(f"Semantic render error: {e}")
            return frame

    def _render_classify(self, frame: np.ndarray, results) -> np.ndarray:
        try:
            if results.probs is None:
                return frame
            top1_id = int(results.probs.top1)
            top1_conf = float(results.probs.top1conf)
            label = results.names.get(top1_id, str(top1_id))
            text = f"{label}: {top1_conf:.2f}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
            cv2.rectangle(frame, (10, 10), (20 + tw, 20 + th + 10), (0, 0, 0), -1)
            cv2.putText(frame, text, (15, 15 + th),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 100), 2)
        except Exception as e:
            logger.debug(f"Classify render error: {e}")
        return frame

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _class_color(cls_id: int) -> Tuple[int, int, int]:
        """Deterministic per-class color."""
        palette = [
            (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
            (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
            (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
            (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
            (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 198),
        ]
        return palette[cls_id % len(palette)]

    @staticmethod
    def _count_classes(results) -> Dict[str, int]:
        """Return {class_name: count} from a Results object."""
        counts: Dict[str, int] = {}
        try:
            if results.boxes is None:
                return counts
            for cls_id in results.boxes.cls.tolist():
                cls_id = int(cls_id)
                name = results.names.get(cls_id, str(cls_id))
                counts[name] = counts.get(name, 0) + 1
        except Exception:
            pass
        return counts
