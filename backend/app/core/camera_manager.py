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

# Callback registered by the WebSocket broadcaster to receive per-inference pushes.
# Set via set_detection_push_cb(); called from CameraWorker inference thread.
_detection_push_cb: Optional[Any] = None


def set_detection_push_cb(cb: Any) -> None:
    global _detection_push_cb
    _detection_push_cb = cb


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
        self.detections: List[Dict[str, Any]] = []
        self.trails: Dict[int, list] = {}
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
        return round((len(self._frame_times) - 1) / span, 1) if span > 0 else 0.0

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
            "detections": list(self.detections),
            "trails": {str(k): v for k, v in self.trails.items()},
            "application_outputs": dict(self.application_outputs),
            "alerts": alerts,
        }


# ── Camera worker thread ──────────────────────────────────────────────────────

class CameraWorker(threading.Thread):
    """
    One thread per camera.
    Captures → infers → applies solutions → enqueues JPEG bytes.
    """

    def __init__(self, camera: Camera, device: str = "cpu",
                 source_url_override: Optional[str] = None):
        super().__init__(daemon=True, name=f"cam-{camera.id}")
        self.camera = camera
        self._device = device
        self._stop_event = threading.Event()
        self._pipeline_lock = threading.Lock()
        # When set, AI capture reads from this URL instead of camera.source.url.
        # Used so the FFmpeg bridge owns the single NVR connection and OpenCV
        # reads locally from mediamtx (rtsp://127.0.0.1:8554/{id}).
        self._source_url_override = source_url_override

        # Frame queue for MJPEG consumers (maxsize keeps latency low)
        self.frame_queue: queue.Queue[bytes] = queue.Queue(
            maxsize=settings.frame_queue_maxsize
        )

        self.telemetry = TelemetryCollector()
        self._solutions: Dict[str, BaseSolution] = {}
        self._engine = InferenceEngine(device=device)
        self._frame_counter = 0
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_sequence = 0
        self._frame_condition = threading.Condition()

        # Rebuild solutions from initial config
        self._rebuild_solutions(camera.pipeline)

    # ── Public API ─────────────────────────────────────────────────────────────

    def stop(self):
        """Signal the thread to exit."""
        self._stop_event.set()
        with self._frame_condition:
            self._frame_condition.notify_all()

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
        logger.info(f"[{self.camera.id}] AI sidecar started")
        while not self._stop_event.is_set():
            try:
                self._capture_and_infer()
            except Exception as e:
                logger.error(f"[{self.camera.id}] Unexpected error: {e}", exc_info=True)
            if not self._stop_event.is_set():
                logger.info(
                    f"[{self.camera.id}] AI source reconnecting in "
                    f"{settings.rtsp_reconnect_delay_s}s"
                )
                time.sleep(settings.rtsp_reconnect_delay_s)

        logger.info(f"[{self.camera.id}] AI sidecar stopped")

    def _capture_and_infer(self):
        """Continuously drain RTSP while inference consumes only the newest frame."""
        cap = self._open_capture()
        if cap is None:
            return

        logger.info(f"[{self.camera.id}] AI source opened: {self._source_str()}")
        capture_done = threading.Event()
        inference_thread = threading.Thread(
            target=self._inference_loop,
            args=(capture_done,),
            daemon=True,
            name=f"ai-infer-{self.camera.id}",
        )
        inference_thread.start()

        try:
            while not self._stop_event.is_set():
                ret, raw_frame = cap.read()
                if not ret or raw_frame is None:
                    logger.warning(f"[{self.camera.id}] AI frame read failed")
                    break
                with self._frame_condition:
                    self._latest_frame = raw_frame
                    self._latest_sequence += 1
                    self._frame_condition.notify()

        finally:
            capture_done.set()
            with self._frame_condition:
                self._frame_condition.notify_all()
            inference_thread.join(timeout=5)
            cap.release()
            logger.info(f"[{self.camera.id}] AI capture released")

    def _inference_loop(self, capture_done: threading.Event):
        """Infer sequentially; skip directly to the latest captured frame."""
        consumed_sequence = 0
        while not self._stop_event.is_set() and not capture_done.is_set():
            with self._frame_condition:
                self._frame_condition.wait_for(
                    lambda: (
                        self._stop_event.is_set()
                        or capture_done.is_set()
                        or self._latest_sequence > consumed_sequence
                    ),
                    timeout=1.0,
                )
                if self._stop_event.is_set() or capture_done.is_set():
                    return
                frame = self._latest_frame
                consumed_sequence = self._latest_sequence
            if frame is None:
                continue

            self._frame_counter += 1
            with self._pipeline_lock:
                pipeline = self.camera.pipeline
                solutions = dict(self._solutions)
            if not _pipeline_uses_ai(pipeline):
                continue
            if self._frame_counter % pipeline.frame_skip != 0:
                continue

            annotated, results, tele = self._engine.infer(
                frame,
                pipeline,
                render=False,
                cam_id=self.camera.id,
            )
            all_alerts = []
            for app_cfg in pipeline.applications:
                if not app_cfg.enabled:
                    continue
                solution = solutions.get(app_cfg.type)
                if solution is None:
                    continue
                try:
                    annotated, output = solution.process(
                        annotated,
                        results,
                        app_cfg.config,
                    )
                    self.telemetry.application_outputs[app_cfg.type] = output
                    all_alerts.extend(solution.pop_alerts())
                except Exception as exc:
                    logger.debug(
                        f"[{self.camera.id}] Solution '{app_cfg.type}' error: {exc}"
                    )

            self.telemetry.record_frame(tele["inference_ms"])
            self.telemetry.counts = tele["counts"]
            self.telemetry.detections = tele.get("detections", [])
            if pipeline.features.trails and frame is not None:
                if tele.get("remote_trails"):
                    self.telemetry.trails = tele["remote_trails"]
                else:
                    h, w = frame.shape[:2]
                    self.telemetry.trails = self._engine.get_trails(w, h)
            if all_alerts:
                self.telemetry.alerts.extend(all_alerts)

            # Push detection result immediately to WebSocket (bypasses 200ms timer)
            if _detection_push_cb is not None:
                try:
                    _detection_push_cb({
                        "cam_id": self.camera.id,
                        "ai_enabled": True,
                        "ai_fps": round(self.telemetry.fps, 1),
                        "inference_ms": round(self.telemetry.avg_inference_ms, 1),
                        "counts": dict(self.telemetry.counts),
                        "detections": list(self.telemetry.detections),
                        "trails": {str(k): v for k, v in self.telemetry.trails.items()},
                    })
                except Exception:
                    pass

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Open cv2.VideoCapture with appropriate flags."""
        source = self.camera.source
        try:
            if source.type == "rtsp":
                # Prefer the local mediamtx URL when the FFmpeg bridge owns the
                # NVR connection — avoids competing for the NVR's single RTSP slot.
                url = self._source_url_override or source.url
                if not url:
                    logger.error(f"[{self.camera.id}] RTSP url is empty")
                    return None
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
        self._ai_camera_id: Optional[str] = None
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
        started = False
        actual_native = (
            camera.source.type == "rtsp"
            and any(
                item.get("id") == cam_id for item in list_native_pipelines()
            )
        )
        if actual_native:
            with self._lock:
                self._native_ids.add(cam_id)
            camera.status = "live"
            started = True
        elif known_native:
            with self._lock:
                self._native_ids.discard(cam_id)

        if (
            not started
            and
            settings.prefer_native_media
            and camera.source.type == "rtsp"
            and camera.source.url
        ):
            camera.status = "connecting"
            camera.error_message = None
            if start_native_pipeline(cam_id, camera.source.url):
                with self._lock:
                    self._native_ids.add(cam_id)
                camera.status = "live"
                logger.info(f"Native camera started: {cam_id}")
                started = True
            else:
                logger.warning(f"Native media agent unavailable for {cam_id}")

        if _pipeline_uses_ai(camera.pipeline):
            started = self._start_ai_worker(camera, force=True) or started
        elif camera.source.type != "rtsp" and not started:
            # Webcam/USB still depends on the Python worker for capture.
            started = self._start_ai_worker(camera, force=True)
        return started

    def _start_ai_worker(self, camera: Camera, force: bool) -> bool:
        """Start the single bounded AI sidecar without touching native video."""
        workers_to_stop: List[CameraWorker] = []
        with self._lock:
            if (
                not force
                and self._ai_camera_id is not None
                and self._ai_camera_id != camera.id
            ):
                return False
            existing = self._workers.get(camera.id)
            if existing is not None and existing.is_alive():
                existing.update_pipeline(camera.pipeline)
                self._ai_camera_id = camera.id
                return True
            if existing is not None:
                self._workers.pop(camera.id, None)

            # This product currently allocates one AI slot. Starting AI on a
            # different camera releases the previous sidecar, while all native
            # WebRTC video pipelines continue independently.
            for other_id, worker in list(self._workers.items()):
                if other_id != camera.id:
                    workers_to_stop.append(worker)
                    self._workers.pop(other_id, None)

            # If FFmpeg bridge owns the NVR connection, read AI frames from the
            # local mediamtx restream instead of connecting to the NVR directly.
            source_override: Optional[str] = None
            if camera.id in self._native_ids and camera.source.type == "rtsp":
                source_override = f"rtsp://127.0.0.1:8554/{camera.id}"
                logger.info(
                    f"[{camera.id}] AI worker reading from local mediamtx restream"
                )

            worker = CameraWorker(camera, device=self._device,
                                  source_url_override=source_override)
            self._workers[camera.id] = worker
            self._ai_camera_id = camera.id

        for old_worker in workers_to_stop:
            old_worker.stop()
        for old_worker in workers_to_stop:
            old_worker.join(timeout=5)
        worker.start()
        logger.info(f"AI assigned to camera: {camera.id}")
        return True

    def _stop_ai_worker(self, cam_id: str) -> bool:
        with self._lock:
            worker = self._workers.pop(cam_id, None)
            if self._ai_camera_id == cam_id:
                self._ai_camera_id = None
        if worker is None:
            return False
        worker.stop()
        worker.join(timeout=5)
        logger.info(f"AI released from camera: {cam_id}")
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
            logger.info(f"AI stopped: {cam_id}")
        return was_native or worker is not None

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
                if self._ai_camera_id == cam_id:
                    self._ai_camera_id = None
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
        with self._lock:
            is_active = cam_id in self._active_ids
        if is_active and camera.source.type == "rtsp" and not was_native:
            if not self.start(cam_id):
                return False
        if needs_ai and is_active:
            return self._start_ai_worker(camera, force=True)
        if worker_was_running and not needs_ai:
            self._stop_ai_worker(cam_id)
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
        ai_snapshot = worker.telemetry.snapshot() if worker is not None else None
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
                    "video_fps": 0.0,
                    "ai_fps": ai_snapshot["fps"] if ai_snapshot else 0.0,
                    "ai_enabled": ai_snapshot is not None,
                    "inference_ms": 0.0,
                    "counts": {},
                    "detections": [],
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
                "video_fps": float(native.get("fps", 0.0)),
                "ai_fps": ai_snapshot["fps"] if ai_snapshot else 0.0,
                "ai_enabled": ai_snapshot is not None,
                "inference_ms": (
                    ai_snapshot["inference_ms"] if ai_snapshot else 0.0
                ),
                "counts": ai_snapshot["counts"] if ai_snapshot else {},
                "detections": ai_snapshot["detections"] if ai_snapshot else [],
                "trails": ai_snapshot["trails"] if ai_snapshot else {},
                "application_outputs": (
                    ai_snapshot["application_outputs"] if ai_snapshot else {}
                ),
                "alerts": ai_snapshot["alerts"] if ai_snapshot else [],
            }
        if worker is None or camera is None:
            return None
        snap = ai_snapshot or worker.telemetry.snapshot()
        snap["cam_id"] = cam_id
        snap["status"] = camera.status
        snap["video_fps"] = snap["fps"]
        snap["ai_fps"] = snap["fps"]
        snap["ai_enabled"] = True
        return snap

    def get_all_telemetry(self) -> List[Dict[str, Any]]:
        with self._lock:
            cam_ids = list(dict.fromkeys([
                *self._native_ids,
                *self._workers.keys(),
            ]))
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
