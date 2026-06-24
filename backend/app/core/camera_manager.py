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
import os
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
from .camera_repository import CameraRepository
from .media_agent_client import (
    list_native_pipelines,
    start_native_pipeline,
    stop_native_pipeline,
)
from .solutions import BaseSolution, create_solution

logger = logging.getLogger(__name__)

# Keep each RTSP decoder lightweight when many cameras are active.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|threads;1",
)


def _pipeline_uses_ai(pipeline: PipelineConfig) -> bool:
    """Return whether this camera currently needs model inference."""
    return (
        any(pipeline.features.model_dump().values())
        or pipeline.tracking.enabled
        or bool(pipeline.open_vocab_prompt)
        or any(app.enabled for app in pipeline.applications)
    )


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
        self._last_output_time = 0.0

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

                # The NVR may send 20–30 fps per channel, but encoding all of
                # those frames for a 16-camera dashboard wastes CPU. Continue
                # reading to keep RTSP buffers fresh and emit at the UI rate.
                now = time.perf_counter()
                output_interval = 1.0 / max(settings.stream_target_fps, 1.0)
                if now - self._last_output_time < output_interval:
                    continue
                self._last_output_time = now

                # Streams start as raw video. Load/run the model only after the
                # user enables an AI feature or application for this camera.
                if not _pipeline_uses_ai(pipeline):
                    self.telemetry.record_frame(0.0)
                    self.telemetry.counts = {}
                    self.telemetry.application_outputs = {}
                    jpg = self._encode_jpeg(raw_frame)
                    self._try_enqueue(jpg)
                    continue

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
        height, width = frame.shape[:2]
        if settings.stream_max_width > 0 and width > settings.stream_max_width:
            scale = settings.stream_max_width / width
            frame = cv2.resize(
                frame,
                (settings.stream_max_width, max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
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
        self._repository = CameraRepository(settings.database_path)
        self._cameras: Dict[str, Camera] = {
            camera.id: camera for camera in self._repository.list()
        }
        self._workers: Dict[str, CameraWorker] = {}
        self._native_ids: set[str] = set()
        self._active_ids: set[str] = set()
        self._native_metrics: Dict[str, Dict[str, Any]] = {}
        self._native_metrics_at = 0.0
        self._native_retry_at: Dict[str, float] = {}
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
        self._repository.save(camera)
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
                self._repository.delete(cam_id)
                logger.info(f"Camera deleted: {cam_id}")
                return True
        return False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self, cam_id: str) -> bool:
        camera = self.get(cam_id)
        if camera is None:
            return False
        with self._lock:
            self._active_ids.add(cam_id)
            known_native = cam_id in self._native_ids
        if known_native:
            if any(
                item.get("id") == cam_id for item in list_native_pipelines()
            ):
                return True
            with self._lock:
                self._native_ids.discard(cam_id)

        if (
            settings.prefer_native_media
            and camera.source.type == "rtsp"
            and camera.source.url
            and not _pipeline_uses_ai(camera.pipeline)
        ):
            camera.status = "connecting"
            camera.error_message = None
            if start_native_pipeline(cam_id, camera.source.url):
                with self._lock:
                    self._native_ids.add(cam_id)
                camera.status = "live"
                logger.info(f"Native camera started: {cam_id}")
                return True
            logger.warning(
                f"Native media agent unavailable for {cam_id}; using OpenCV fallback"
            )

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
            was_native = cam_id in self._native_ids
            self._native_ids.discard(cam_id)
            self._active_ids.discard(cam_id)
        if was_native:
            stop_native_pipeline(cam_id)
            camera = self.get(cam_id)
            if camera is not None:
                camera.status = "stopped"
            logger.info(f"Native camera stopped: {cam_id}")
        if worker:
            worker.stop()
            worker.join(timeout=10)
            logger.info(f"Camera stopped: {cam_id}")
            return True
        return was_native

    def activate_only(self, camera_ids: List[str]) -> List[Camera]:
        """Stop every other worker and start at most two requested cameras."""
        desired = list(dict.fromkeys(camera_ids))[:2]
        desired_set = set(desired)

        with self._lock:
            missing = [cam_id for cam_id in desired if cam_id not in self._cameras]
            if missing:
                raise KeyError(missing[0])
            # Publish desired ownership before stopping anything. Telemetry
            # retries consult this set and therefore cannot resurrect a
            # pipeline that is being removed during a page transition.
            self._active_ids = desired_set.copy()

            stopping = [
                (cam_id, worker)
                for cam_id, worker in self._workers.items()
                if cam_id not in desired_set
            ]
            for cam_id, _ in stopping:
                self._workers.pop(cam_id, None)
                camera = self._cameras.get(cam_id)
                if camera is not None:
                    camera.status = "stopped"
            native_stopping = [
                cam_id for cam_id in self._native_ids if cam_id not in desired_set
            ]
            # The media agent survives backend/container restarts. Reconcile
            # against its actual state so pipelines from an older backend
            # process cannot remain alive and waste decoder resources.
            native_stopping.extend(
                str(item["id"])
                for item in list_native_pipelines()
                if item.get("id") and item.get("id") not in desired_set
            )
            native_stopping = list(dict.fromkeys(native_stopping))
            for cam_id in native_stopping:
                self._native_ids.discard(cam_id)
                camera = self._cameras.get(cam_id)
                if camera is not None:
                    camera.status = "stopped"

        # Signal all old workers first so shutdown happens in parallel.
        for _, worker in stopping:
            worker.stop()
        for cam_id in native_stopping:
            stop_native_pipeline(cam_id)

        deadline = time.monotonic() + 8.0
        for cam_id, worker in stopping:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))
            logger.info(f"Camera deactivated: {cam_id}")

        for cam_id in desired:
            self.start(cam_id)

        return [self.get(cam_id) for cam_id in desired if self.get(cam_id) is not None]

    def update_pipeline(self, cam_id: str, pipeline: PipelineConfig) -> bool:
        camera = self.get(cam_id)
        if camera is None:
            return False
        with self._lock:
            was_native = cam_id in self._native_ids
            worker_was_running = cam_id in self._workers
            camera.pipeline = pipeline
            worker = self._workers.get(cam_id)
        self._repository.save(camera)
        if worker:
            worker.update_pipeline(pipeline)
        needs_ai = _pipeline_uses_ai(pipeline)
        if was_native and needs_ai:
            self.stop(cam_id)
            return self.start(cam_id)
        if worker_was_running and not needs_ai and camera.source.type == "rtsp":
            self.stop(cam_id)
            return self.start(cam_id)
        return True

    def is_native(self, cam_id: str) -> bool:
        with self._lock:
            return cam_id in self._native_ids

    def _native_pipeline(self, cam_id: str) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            refresh = now - self._native_metrics_at >= 0.75
        if refresh:
            snapshots = {
                str(item.get("id")): item for item in list_native_pipelines()
            }
            with self._lock:
                self._native_metrics = snapshots
                self._native_metrics_at = now
        with self._lock:
            return self._native_metrics.get(cam_id)

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
            is_native = cam_id in self._native_ids
            is_active = cam_id in self._active_ids
        if is_native and camera is not None:
            native = self._native_pipeline(cam_id)
            if native is None:
                now = time.monotonic()
                with self._lock:
                    retry_allowed = is_active and (
                        now - self._native_retry_at.get(cam_id, 0.0) >= 5.0
                    )
                    if retry_allowed:
                        self._native_retry_at[cam_id] = now
                restarted = False
                if retry_allowed and camera.source.type == "rtsp" and camera.source.url:
                    # Keep ownership stable across the retry request. If page
                    # activation is waiting, it will run immediately after and
                    # reconcile/stop this pipeline when it is no longer desired.
                    with self._lock:
                        if cam_id in self._active_ids:
                            restarted = start_native_pipeline(
                                cam_id,
                                camera.source.url,
                            )
                if restarted:
                    camera.status = "connecting"
                    with self._lock:
                        self._native_metrics_at = 0.0
                return {
                    "cam_id": cam_id,
                    "status": camera.status,
                    "fps": 0.0,
                    "inference_ms": 0.0,
                    "counts": {},
                    "application_outputs": {},
                    "alerts": [],
                }
            camera.status = (
                "live" if native.get("state") == "live"
                else "error" if native.get("state") == "error"
                else "connecting"
            )
            camera.error_message = native.get("error") or None
            return {
                "cam_id": cam_id,
                "status": camera.status,
                "fps": float(native.get("fps", 0.0)),
                "inference_ms": 0.0,
                "counts": {},
                "application_outputs": {},
                "alerts": [],
            }
        if worker is None or camera is None:
            return None
        snap = worker.telemetry.snapshot()
        snap["cam_id"] = cam_id
        snap["status"] = camera.status
        return snap

    def get_all_telemetry(self) -> List[Dict[str, Any]]:
        with self._lock:
            cam_ids = list(self._workers.keys()) + list(self._native_ids)
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
