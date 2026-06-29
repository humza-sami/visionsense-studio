"""Metrics (§5.13). Per-camera FPS + GPU/VRAM telemetry. pynvml is NVIDIA-only and
optional — on macOS it's simply absent and GPU stats report as unavailable.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_NVML = None
try:  # pragma: no cover - platform dependent
    import pynvml

    pynvml.nvmlInit()
    _NVML = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    pynvml = None
    _NVML = None


def gpu_stats() -> dict:
    if _NVML is None:
        return {"available": False}
    try:
        util = pynvml.nvmlDeviceGetUtilizationRates(_NVML)
        mem = pynvml.nvmlDeviceGetMemoryInfo(_NVML)
        return {
            "available": True,
            "gpu_util": util.gpu,
            "mem_util": util.memory,
            "vram_used_mb": mem.used // 1024 ** 2,
            "vram_total_mb": mem.total // 1024 ** 2,
        }
    except Exception:
        return {"available": False}


class Metrics:
    """Thread-safe rolling metrics keyed by camera."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._det_ticks: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=60))
        self._counts: dict[str, int] = defaultdict(int)
        self._loop_ticks: deque[float] = deque(maxlen=120)
        self._stage_ms: dict[str, float] = {}

    def mark_detection(self, cam_id: str, n_objects: int) -> None:
        with self._lock:
            self._det_ticks[cam_id].append(time.monotonic())
            self._counts[cam_id] = n_objects

    def mark_loop(self) -> None:
        with self._lock:
            self._loop_ticks.append(time.monotonic())

    def set_stage_ms(self, stage: str, ms: float) -> None:
        with self._lock:
            self._stage_ms[stage] = round(ms, 2)

    @staticmethod
    def _fps(ticks: deque[float]) -> float:
        if len(ticks) < 2:
            return 0.0
        span = ticks[-1] - ticks[0]
        return round((len(ticks) - 1) / span, 1) if span > 0 else 0.0

    def snapshot(self, workers: dict | None = None) -> dict:
        with self._lock:
            cams = {}
            for cid, ticks in self._det_ticks.items():
                cams[cid] = {
                    "detect_fps": self._fps(ticks),
                    "objects": self._counts.get(cid, 0),
                }
            loop_fps = self._fps(self._loop_ticks)
            stages = dict(self._stage_ms)

        if workers:
            for cid, w in workers.items():
                cams.setdefault(cid, {})
                cams[cid].update({
                    "connected": getattr(w, "connected", False),
                    "frames_read": getattr(w, "frames_read", 0),
                    "last_error": getattr(w, "last_error", None),
                })

        return {
            "loop_fps": loop_fps,
            "stage_ms": stages,
            "gpu": gpu_stats(),
            "cameras": cams,
        }
