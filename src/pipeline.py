"""Orchestrator (§5.6) — wires every stage into one GPU consumer loop.

  capture threads → latest-frame buffer → motion gate → batch builder →
  ONE batched inference → per-camera ByteTrack → business logic → events

Detection runs every Nth frame per camera; the tracker carries IDs between, and
non-detection frames just reuse the last tracks for the live preview. Annotated
frames are stored per camera for the MJPEG API.
"""
from __future__ import annotations

import logging
import threading
import time

from src.capture.frame_buffer import LatestFrameBuffer
from src.capture.rtsp_worker import CameraWorker
from src.config import Settings, enabled_cameras
from src.events.publisher import EventPublisher
from src.inference.batch_builder import build_batch
from src.inference.engine import Detector
from src.logic import build_handlers
from src.monitoring.metrics import Metrics
from src.motion.motion_gate import MotionGate
from src.tracking.tracker import CameraTracker
from src.types import Track
from src.viz import draw
from src.zones import load_zones

log = logging.getLogger("pipeline")


class Pipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cams = enabled_cameras(settings)
        self.buffer = LatestFrameBuffer()
        self.metrics = Metrics()
        self.events = EventPublisher(settings.redis)
        self.motion = MotionGate(settings.pipeline.motion_min_area)

        # Lazy: detector loads the (possibly large) model — built in start().
        self.detector: Detector | None = None

        self.workers: dict[str, CameraWorker] = {}
        self.trackers: dict[str, CameraTracker] = {}
        self.handlers = {}
        self.zones = {}
        self._last_tracks: dict[str, list[Track]] = {}

        # Annotated frames for the live preview (cam_id -> BGR ndarray).
        self._annotated: dict[str, "any"] = {}
        self._annot_lock = threading.Lock()

        self.running = False
        self._loop_thread: threading.Thread | None = None
        self._frame_id = 0

        for cam in self.cams:
            self.trackers[cam.id] = CameraTracker()
            self.zones[cam.id] = load_zones(cam.zones_file)
            self.handlers[cam.id] = build_handlers(cam, self.zones[cam.id])

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.running:
            return
        log.info("Loading detector…")
        self.detector = Detector(self.settings.model)

        for cam in self.cams:
            w = CameraWorker(cam, self.buffer, self.settings.capture)
            self.workers[cam.id] = w
            w.start()

        self.running = True
        self._loop_thread = threading.Thread(target=self._run_loop, name="gpu-loop", daemon=True)
        self._loop_thread.start()
        log.info("Pipeline started with %d camera(s)", len(self.cams))

    def stop(self) -> None:
        self.running = False
        for w in self.workers.values():
            w.stop()
        if self._loop_thread:
            self._loop_thread.join(timeout=3)
        log.info("Pipeline stopped")

    # ── main loop ────────────────────────────────────────────────────────────
    def _run_loop(self) -> None:
        target_dt = 1.0 / max(1, self.settings.pipeline.loop_target_fps)
        while self.running:
            t0 = time.monotonic()
            try:
                self._tick()
            except Exception:
                log.exception("tick error")
            self.metrics.mark_loop()
            elapsed = time.monotonic() - t0
            if elapsed < target_dt:
                time.sleep(target_dt - elapsed)

    def _tick(self) -> None:
        fid = self._frame_id
        snap = self.buffer.snapshot()
        if not snap:
            return

        # 1) Motion gate → active cameras.
        active: list[str] = []
        for cam in self.cams:
            frame = snap.get(cam.id)
            if frame is None:
                continue
            if cam.motion_gate and not self.motion.is_active(cam.id, frame):
                continue
            active.append(cam.id)

        # 2) Which active cams are due for detection this frame.
        detect_now = [
            cid for cid in active
            if fid % self._det_interval(cid) == 0
        ]

        if detect_now:
            t = time.monotonic()
            frames, order = build_batch(self.buffer, detect_now)
            if frames:
                results = self.detector.detect_batch(frames)  # ONE batched call
                self.metrics.set_stage_ms("inference", (time.monotonic() - t) * 1000)
                for cid, dets in zip(order, results):
                    tracks = self.trackers[cid].update(dets)
                    self._last_tracks[cid] = tracks
                    self.metrics.mark_detection(cid, len(tracks))
                    for h in self.handlers[cid]:
                        for ev in h.process(tracks):
                            self.events.emit(ev)

        # 3) Update preview for every camera that has a frame (detected or not).
        for cam in self.cams:
            frame = snap.get(cam.id)
            if frame is None:
                continue
            tracks = self._last_tracks.get(cam.id, [])
            label = f"{cam.id}  f{fid}  {len(tracks)} obj"
            annotated = draw(frame, tracks, self.zones.get(cam.id), label)
            with self._annot_lock:
                self._annotated[cam.id] = annotated

        self._frame_id += 1

    def _det_interval(self, cam_id: str) -> int:
        for cam in self.cams:
            if cam.id == cam_id:
                return max(1, cam.det_interval or self.settings.pipeline.default_det_interval)
        return self.settings.pipeline.default_det_interval

    # ── accessors for the API ────────────────────────────────────────────────
    def get_annotated(self, cam_id: str):
        with self._annot_lock:
            return self._annotated.get(cam_id)

    def camera_ids(self) -> list[str]:
        return [c.id for c in self.cams]

    def status(self) -> dict:
        return self.metrics.snapshot(self.workers)
