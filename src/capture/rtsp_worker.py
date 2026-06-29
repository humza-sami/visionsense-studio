"""Per-camera capture thread: decode → push latest frame → reconnect on failure.

One daemon thread per camera. Threads are the right tool here because the time is
spent inside native decode (cv2/FFmpeg/NVDEC), which releases the GIL. A dead
camera reconnects with backoff and never takes down the pipeline.
"""
from __future__ import annotations

import logging
import threading
import time

from src.capture.capture_source import open_capture
from src.capture.frame_buffer import LatestFrameBuffer
from src.config import CameraConfig, CaptureConfig

log = logging.getLogger("capture")


class CameraWorker(threading.Thread):
    def __init__(
        self,
        cam: CameraConfig,
        buffer: LatestFrameBuffer,
        capture_cfg: CaptureConfig,
    ) -> None:
        super().__init__(daemon=True, name=f"capture-{cam.id}")
        self.cam = cam
        self.buffer = buffer
        self.cfg = capture_cfg
        self.running = True
        self.connected = False
        self.frames_read = 0
        self.last_error: str | None = None

    def stop(self) -> None:
        self.running = False

    def run(self) -> None:
        while self.running:
            cap = open_capture(self.cam.url, self.cfg)
            if not cap or not cap.isOpened():
                self.connected = False
                self.last_error = "open failed"
                log.warning("[%s] open failed, retrying in %ss", self.cam.id, self.cfg.reconnect_backoff_s)
                time.sleep(self.cfg.reconnect_backoff_s)
                continue

            self.connected = True
            self.last_error = None
            log.info("[%s] connected", self.cam.id)
            fail = 0
            while self.running:
                ok, frame = cap.read()
                if not ok or frame is None:
                    fail += 1
                    if fail > self.cfg.read_fail_limit:
                        self.last_error = "read failures, reconnecting"
                        log.warning("[%s] %s", self.cam.id, self.last_error)
                        break
                    time.sleep(0.01)
                    continue
                fail = 0
                self.frames_read += 1
                self.buffer.put(self.cam.id, frame)

            cap.release()
            self.connected = False
            if self.running:
                time.sleep(self.cfg.reconnect_backoff_s)

        log.info("[%s] worker stopped", self.cam.id)
