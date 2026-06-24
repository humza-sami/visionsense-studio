"""
Camera Manager — thread-based multi-camera management.

Architecture:
- `camera_manager` is a module-level singleton accessed by API routes.
- Each camera runs as a `CameraWorker` thread that:
    1. Opens cv2.VideoCapture
    2. Reads frames
    3. Applies frame_skip
    4. Runs InferenceEngine
    5. Passes frame through active Solutions
    6. Puts annotated JPEG bytes into a queue for MJPEG streaming
    7. Collects telemetry
- Reconnect on error after 5 s.
- Thread lifecycle: start() / stop() managed by API calls.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections import deque
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.config import settings
from app.models.camera import (
    ApplicationConfig,
    Camera,
    CameraSource,
    PipelineConfig,
)
from .inference_engine import InferenceEngine
from .solutions import BaseSolution, create_solution

logger = logging.getLogger(__name__)


# ── Telemetry collector ───────────────────────────────────────────────────────

class TelemetryCollector:
    """Rolling-window metrics for a single camera."""

    def __init__(self, window: int = 30):
        self._frame_times: deque = deque(maxlen=window)
        self._inference_times: deque = deque(maxlen=window)
        self.counts: Dict[str, int] = {}
        self.application_outputs: Dict[str, Any] = {}
        self.alerts: list = []

    def record_frame(self, inference_ms: float):
        now = time.perf_counter()
        self._frame_times.append(now)
        self._inference_times.append(inference_ms)

    @property
    def fps(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        span = self._frame_times[-1] - self._frame_times[0]
        return round(len(self._frame_times) / span, 1) if span > 0 else 0.0

    @property
    def avg_inference_ms(self) -> float:
        if not self._inference_times:
            return 0.0
        return round(sum(self._inference_times) / len(self._inference_times), 1)

    def snapshot(self) -> Dict[str, Any]:
        alerts = self.alerts[:]
        self.alerts = []
        return {
            "fps": self.fps,
            "inference_ms": self.avg_inference_ms,
            "counts": dict(self.counts),
            "application_outputs": dict(self.application_outputs),
            "alerts": alerts,
        }


# ── Camera worker thread ──────────────────────────────────────────────────────

class CameraWorker(threading.Thread):
    """
    One thread per camera.
    Captures → infers → applies solutions → enqueues JPEG bytes.
    """

    def __init__(self, camera: Camera, device: str = "cpu"):
        super().__init__(daemon=True, name=f"cam-{camera.id}")
        self.camera = camera
        self._device = device
        self._stop_event = threading.Event()
        self._pipeline_lock = threading.Lock()

        # Frame queue for MJPEG consumers (maxsize keeps latency low)
        self.frame_queue: queue.Queue[bytes] = queue.Queue(
            maxsize=settings.frame_queue_maxsize
        )

        self.telemetry = TelemetryCollector()
        self._solutions: Dict[str, BaseSolution] = {}
        self._engine = InferenceEngine(device=device)
        self._frame_counter = 0

        # Rebuild solutions from initial config
        self._rebuild_solutions(camera.pipeline)

    # ── Public API ─────────────────────────────────────────────────────────────

    def stop(self):
        """Signal the thread to exit."""
        self._stop_event.set()

    def update_pipeline(self, pipeline: PipelineConfig):
        """Hot-swap pipeline config (thread-safe)."""
        with self._pipeline_lock:
            self.camera.pipeline = pipeline
            self._rebuild_solutions(pipeline)

    def get_latest_frame(self, timeout: float = 1.0) -> Optional[bytes]:
        """Return the most recent JPEG bytes, blocking up to `timeout` seconds."""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ── Thread main loop ───────────────────────────────────────────────────────

    def run(self):
        logger.info(f"[{self.camera.id}] Worker started")
        while not self._stop_event.is_set():
            try:
                self._stream_loop()
            except Exception as e:
                logger.error(f"[{self.camera.id}] Unexpected error: {e}", exc_info=True)
            if not self._stop_event.is_set():
                self.camera.status = "error"
                self.camera.error_message = "Stream ended, reconnecting..."
                logger.info(f"[{self.camera.id}] Reconnecting in {settings.rtsp_reconnect_delay_s}s")
                time.sleep(settings.rtsp_reconnect_delay_s)

        self.camera.status = "stopped"
        logger.info(f"[{self.camera.id}] Worker stopped")

    def _stream_loop(self):
        """Open capture, read frames, infer, enqueue."""
        cap = self._open_capture()
        if cap is None:
            self.camera.status = "error"
            self.camera.error_message = "Failed to open video source"
            return

        self.camera.status = "live"
        self.camera.error_message = None
        logger.info(f"[{self.camera.id}] Stream opened: {self._source_str()}")

        try:
            while not self._stop_event.is_set():
                ret, raw_frame = cap.read()
                if not ret or raw_frame is None:
                    logger.warning(f"[{self.camera.id}] Frame read failed")
                    break

                self._frame_counter += 1

                # Get current pipeline (lock briefly)
                with self._pipeline_lock:
                    pipeline = self.camera.pipeline
                    solutions = dict(self._solutions)

                # Frame skip
                if self._frame_counter % pipeline.frame_skip != 0:
                    # Still enqueue the raw frame for smooth video
                    jpg = self._encode_jpeg(raw_frame)
                    self._try_enqueue(jpg)
                    continue

                # Inference
                annotated, results, tele = self._engine.infer(raw_frame, pipeline)

                # Solutions layer
                all_alerts = []
                for app_cfg in pipeline.applications:
                    if not app_cfg.enabled:
                        continue
                    sol = solutions.get(app_cfg.type)
                    if sol is None:
                        continue
                    try:
                        annotated, sol_output = sol.process(
                            annotated, results, app_cfg.config
                        )
                        self.telemetry.application_outputs[app_cfg.type] = sol_output
                        all_alerts.extend(sol.pop_alerts())
                    except Exception as e:
                        logger.debug(f"[{self.camera.id}] Solution '{app_cfg.type}' error: {e}")

                # Update telemetry
                self.telemetry.record_frame(tele["inference_ms"])
                self.telemetry.counts = tele["counts"]
                if all_alerts:
                    self.telemetry.alerts.extend(all_alerts)

                # Encode and enqueue
                jpg = self._encode_jpeg(annotated)
                self._try_enqueue(jpg)

        finally:
            cap.release()
            logger.info(f"[{self.camera.id}] Capture released")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Open cv2.VideoCapture with appropriate flags."""
        self.camera.status = "connecting"
        source = self.camera.source
        try:
            if source.type == "rtsp":
                url = source.url
                if not url:
                    logger.error(f"[{self.camera.id}] RTSP url is empty")
                    return None
                # Force TCP transport to avoid UDP packet loss
                os_env_url = url
                if "rtsp_transport" not in url.lower():
                    os_env_url += "?rtsp_transport=tcp" if "?" not in url else "&rtsp_transport=tcp"
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, settings.rtsp_timeout_ms)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, settings.rtsp_timeout_ms)
            elif source.type in ("webcam", "usb"):
                idx = source.device_index if source.device_index is not None else 0
                cap = cv2.VideoCapture(idx)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                logger.error(f"[{self.camera.id}] Unknown source type: {source.type}")
                return None

            if not cap.isOpened():
                cap.release()
                logger.warning(f"[{self.camera.id}] Capture did not open")
                return None

            return cap
        except Exception as e:
            logger.error(f"[{self.camera.id}] Error opening capture: {e}")
            return None

    def _source_str(self) -> str:
        s = self.camera.source
        if s.type == "rtsp":
            # Mask credentials for logging
            url = s.url or ""
            import re
            url = re.sub(r":[^@/]+@", ":***@", url)
            return url
        return f"{s.type}:{s.device_index}"

    @staticmethod
    def _encode_jpeg(frame: np.ndarray, quality: int = None) -> bytes:
        q = quality or settings.mjpeg_quality
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, q])
        if not ret:
            return b""
        return buf.tobytes()

    def _try_enqueue(self, data: bytes):
        """Non-blocking enqueue; drop oldest frame if full."""
        if not data:
            return
        try:
            self.frame_queue.put_nowait(data)
        except queue.Full:
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.frame_queue.put_nowait(data)
            except queue.Full:
                pass

    def _rebuild_solutions(self, pipeline: PipelineConfig):
        """Recreate solution instances based on current application configs."""
        existing_types = set(self._solutions.keys())
        new_types = {app.type for app in pipeline.applications if app.enabled}

        # Remove disabled/removed solutions
        for t in existing_types - new_types:
            del self._solutions[t]

        # Create new solutions
        for app_cfg in pipeline.applications:
            if app_cfg.enabled and app_cfg.type not in self._solutions:
                sol = create_solution(app_cfg.type, app_cfg.config)
                if sol is not None:
                    self._solutions[app_cfg.type] = sol


# ── Camera manager singleton ───────────────────────────────────────────────────

class CameraManager:
    """
    Central registry for all camera workers.
    Accessed by API routes via the module-level `camera_manager` instance.
    """

    def __init__(self):
        self._cameras: Dict[str, Camera] = {}
        self._workers: Dict[str, CameraWorker] = {}
        self._lock = threading.Lock()
        self._device = settings.yolo_device

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, name: str, source: CameraSource,
               pipeline: Optional[PipelineConfig] = None) -> Camera:
        cam_id = f"cam_{uuid.uuid4().hex[:8]}"
        camera = Camera(
            id=cam_id,
            name=name,
            source=source,
            pipeline=pipeline or PipelineConfig(),
        )
        with self._lock:
            self._cameras[cam_id] = camera
        logger.info(f"Camera created: {cam_id} ({name})")
        return camera

    def list(self) -> List[Camera]:
        with self._lock:
            return list(self._cameras.values())

    def get(self, cam_id: str) -> Optional[Camera]:
        return self._cameras.get(cam_id)

    def delete(self, cam_id: str) -> bool:
        self.stop(cam_id)
        with self._lock:
            if cam_id in self._cameras:
                del self._cameras[cam_id]
                logger.info(f"Camera deleted: {cam_id}")
                return True
        return False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self, cam_id: str) -> bool:
        camera = self.get(cam_id)
        if camera is None:
            return False
        with self._lock:
            if cam_id in self._workers:
                w = self._workers[cam_id]
                if w.is_alive():
                    return True  # already running
                del self._workers[cam_id]
            worker = CameraWorker(camera, device=self._device)
            self._workers[cam_id] = worker
        worker.start()
        logger.info(f"Camera started: {cam_id}")
        return True

    def stop(self, cam_id: str) -> bool:
        with self._lock:
            worker = self._workers.pop(cam_id, None)
        if worker:
            worker.stop()
            worker.join(timeout=10)
            logger.info(f"Camera stopped: {cam_id}")
            return True
        return False

    def update_pipeline(self, cam_id: str, pipeline: PipelineConfig) -> bool:
        camera = self.get(cam_id)
        if camera is None:
            return False
        with self._lock:
            camera.pipeline = pipeline
            worker = self._workers.get(cam_id)
        if worker:
            worker.update_pipeline(pipeline)
        return True

    # ── Frame access ──────────────────────────────────────────────────────────

    def get_frame(self, cam_id: str, timeout: float = 1.0) -> Optional[bytes]:
        with self._lock:
            worker = self._workers.get(cam_id)
        if worker is None:
            return None
        return worker.get_latest_frame(timeout=timeout)

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def get_telemetry(self, cam_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            worker = self._workers.get(cam_id)
            camera = self._cameras.get(cam_id)
        if worker is None or camera is None:
            return None
        snap = worker.telemetry.snapshot()
        snap["cam_id"] = cam_id
        snap["status"] = camera.status
        return snap

    def get_all_telemetry(self) -> List[Dict[str, Any]]:
        with self._lock:
            cam_ids = list(self._workers.keys())
        return [t for cid in cam_ids if (t := self.get_telemetry(cid)) is not None]

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def shutdown(self):
        """Stop all workers (called on app shutdown)."""
        with self._lock:
            ids = list(self._workers.keys())
        for cam_id in ids:
            self.stop(cam_id)
        logger.info("CameraManager shut down")


# Module-level singleton
camera_manager = CameraManager()
