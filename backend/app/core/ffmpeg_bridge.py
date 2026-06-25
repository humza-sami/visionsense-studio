"""
Two-stage FFmpeg bridge: NVR HEVC → mediamtx H.264 WebRTC.

Stage 1 (stable):
  NVR RTSP (HEVC) ──copy──► mediamtx RTSP  /{cam_id}_raw
  Wall-clock timestamps fix non-monotonic DTS from NVRs.

Stage 2 (retried until it catches an IDR frame):
  mediamtx RTSP /{cam_id}_raw (HEVC) ──transcode──► mediamtx RTSP /{cam_id}
  Retries automatically; within 1-2 GOP periods (~2-4 s) it joins right
  after a keyframe and produces a stable H.264 stream for WebRTC.

The AI worker (OpenCV) reads from rtsp://127.0.0.1:8554/{cam_id} (H.264)
so OpenCV, WebRTC, and the NVR all share a single NVR connection.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MEDIAMTX_RTSP = os.environ.get("VS_MEDIAMTX_RTSP", "rtsp://127.0.0.1:8554")


class _Stage:
    """One FFmpeg subprocess with automatic restart."""

    def __init__(self, name: str, cmd: list[str], restart_delay: float = 2.0):
        self.name = name
        self._cmd = cmd
        self._restart_delay = restart_delay
        self._proc: Optional[subprocess.Popen] = None
        self._stop = threading.Event()
        self.error: Optional[str] = None

    def start(self) -> None:
        self._stop.clear()
        self._launch()
        t = threading.Thread(target=self._monitor, daemon=True, name=self.name)
        t.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _launch(self) -> None:
        self._proc = subprocess.Popen(
            self._cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        self.error = None

    def _monitor(self) -> None:
        while not self._stop.is_set():
            proc = self._proc
            if proc is None:
                break
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                continue
            if self._stop.is_set():
                break
            try:
                self.error = (proc.stderr.read() or b"").decode(errors="replace").strip() or "exited"
            except Exception:
                self.error = "exited"
            logger.debug(f"[{self.name}] restarting in {self._restart_delay}s")
            time.sleep(self._restart_delay)
            if not self._stop.is_set():
                self._launch()


class _Pipeline:
    """Two-stage NVR→mediamtx bridge for one camera."""

    def __init__(self, camera_id: str, rtsp_url: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._stage1: Optional[_Stage] = None
        self._stage2: Optional[_Stage] = None

    def start(self) -> bool:
        if not shutil.which("ffmpeg"):
            logger.error(f"[{self.camera_id}] ffmpeg not found in PATH")
            return False

        raw_path = f"{MEDIAMTX_RTSP}/{self.camera_id}_raw"
        final_path = f"{MEDIAMTX_RTSP}/{self.camera_id}"

        # Stage 1: NVR HEVC → mediamtx (copy, wall-clock timestamps)
        self._stage1 = _Stage(
            name=f"ffb-s1-{self.camera_id}",
            cmd=[
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-use_wallclock_as_timestamps", "1",
                "-i", self.rtsp_url,
                "-c", "copy",
                "-fflags", "+genpts",
                "-avoid_negative_ts", "make_zero",
                "-f", "rtsp", "-rtsp_transport", "tcp",
                raw_path,
            ],
            restart_delay=3.0,
        )
        self._stage1.start()
        logger.info(f"[{self.camera_id}] Stage-1 started (NVR→mediamtx HEVC copy)")

        # Give stage 1 time to publish at least one GOP so stage 2 starts on IDR
        time.sleep(3.0)

        # Stage 2: mediamtx HEVC → H.264 via VideoToolbox (hardware encoder)
        # baseline + bf=0: no B-frames (WebRTC requirement)
        # g=30/keyint_min=30 + force_key_frames: ~1s GOP so browsers join fast
        # realtime=true: low-latency VideoToolbox mode
        self._stage2 = _Stage(
            name=f"ffb-s2-{self.camera_id}",
            cmd=[
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-fflags", "+discardcorrupt",
                "-err_detect", "ignore_err",
                "-i", raw_path,
                "-an",
                "-c:v", "h264_videotoolbox",
                "-pix_fmt", "yuv420p",
                "-profile:v", "baseline",
                "-bf", "0",
                "-g", "30", "-keyint_min", "30",
                "-force_key_frames", "expr:gte(t,n_forced*1)",
                "-b:v", "3000k", "-maxrate", "3000k", "-bufsize", "6000k",
                "-realtime", "true",
                "-fflags", "+genpts",
                "-avoid_negative_ts", "make_zero",
                "-f", "rtsp", "-rtsp_transport", "tcp",
                final_path,
            ],
            restart_delay=1.5,
        )
        self._stage2.start()
        logger.info(f"[{self.camera_id}] Stage-2 started (HEVC→H.264 transcode, retrying for IDR)")
        return True

    def stop(self) -> None:
        if self._stage2:
            self._stage2.stop()
        if self._stage1:
            self._stage1.stop()
        logger.info(f"[{self.camera_id}] Pipeline stopped")

    def is_alive(self) -> bool:
        return bool(self._stage1 and self._stage1.is_alive())

    def stage2_alive(self) -> bool:
        return bool(self._stage2 and self._stage2.is_alive())

    def error(self) -> Optional[str]:
        if self._stage1 and not self._stage1.is_alive():
            return self._stage1.error
        return None


# ── Registry ──────────────────────────────────────────────────────────────────

_pipelines: Dict[str, _Pipeline] = {}
_lock = threading.Lock()


def start(camera_id: str, rtsp_url: str) -> bool:
    with _lock:
        existing = _pipelines.get(camera_id)
        if existing and existing.is_alive():
            return True
        p = _Pipeline(camera_id, rtsp_url)
        if p.start():
            _pipelines[camera_id] = p
            return True
        return False


def stop(camera_id: str) -> None:
    with _lock:
        p = _pipelines.pop(camera_id, None)
    if p:
        p.stop()


def list_all() -> List[Dict[str, Any]]:
    with _lock:
        items = list(_pipelines.items())
    result = []
    for cam_id, p in items:
        alive = p.is_alive()
        result.append({
            "id": cam_id,
            "state": "live" if alive else "error",
            "error": p.error() if not alive else None,
            "transport": "webrtc",
            "whep_url": f"http://localhost:8889/{cam_id}/whep",
            "fps": 0.0,
            "width": 0,
            "height": 0,
            "restarts": 0,
        })
    return result
