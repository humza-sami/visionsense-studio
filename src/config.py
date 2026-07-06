"""Load YAML config into typed dataclasses. Single source of truth for tunables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


@dataclass
class ModelConfig:
    weights: str = "models/yolo26n.pt"
    engine: str = "models/yolo26n.engine"
    imgsz: int = 640
    conf: float = 0.35
    iou: float = 0.45
    max_batch: int = 15
    device: str = "auto"
    classes: Optional[list[int]] = None


@dataclass
class PipelineConfig:
    default_det_interval: int = 3
    loop_target_fps: int = 30
    motion_min_area: int = 500


@dataclass
class CaptureConfig:
    backend: str = "auto"
    rtsp_transport: str = "tcp"
    codec: str = "h264"          # h264 | h265 — picks nvh264dec / nvh265dec for NVDEC
    reconnect_backoff_s: float = 2.0
    read_fail_limit: int = 30


@dataclass
class ApiConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    jpeg_quality: int = 70
    preview_max_fps: int = 15


@dataclass
class RedisConfig:
    enabled: bool = False
    host: str = "localhost"
    port: int = 6379
    stream: str = "cctv:events"


@dataclass
class CameraConfig:
    id: str
    url: Any                      # int (webcam), path, or rtsp url
    det_interval: int = 3
    motion_gate: bool = False
    logic: list[str] = field(default_factory=list)
    zones_file: Optional[str] = None
    enabled: bool = True


@dataclass
class Settings:
    model: ModelConfig
    pipeline: PipelineConfig
    capture: CaptureConfig
    api: ApiConfig
    redis: RedisConfig
    cameras: list[CameraConfig]


def _env_override(settings: Settings) -> None:
    """Allow a few high-value overrides via env vars (handy in Docker)."""
    if v := os.getenv("MODEL_WEIGHTS"):
        settings.model.weights = v
    if v := os.getenv("MODEL_ENGINE"):
        settings.model.engine = v
    if v := os.getenv("MODEL_IMGSZ"):
        settings.model.imgsz = int(v)
    if v := os.getenv("MODEL_MAX_BATCH"):
        settings.model.max_batch = int(v)
    if v := os.getenv("MODEL_DEVICE"):
        settings.model.device = v
    if v := os.getenv("REDIS_ENABLED"):
        settings.redis.enabled = v.lower() in ("1", "true", "yes")
    if v := os.getenv("REDIS_HOST"):
        settings.redis.host = v
    if v := os.getenv("API_PORT"):
        settings.api.port = int(v)


def load_settings(
    settings_path: str | Path = ROOT / "config" / "settings.yaml",
    cameras_path: str | Path = ROOT / "config" / "cameras.yaml",
) -> Settings:
    s = _load_yaml(Path(settings_path))
    c = _load_yaml(Path(cameras_path))

    cams = [CameraConfig(**cam) for cam in c.get("cameras", [])]

    settings = Settings(
        model=ModelConfig(**s.get("model", {})),
        pipeline=PipelineConfig(**s.get("pipeline", {})),
        capture=CaptureConfig(**s.get("capture", {})),
        api=ApiConfig(**s.get("api", {})),
        redis=RedisConfig(**s.get("redis", {})),
        cameras=cams,
    )
    _env_override(settings)
    return settings


def enabled_cameras(settings: Settings) -> list[CameraConfig]:
    return [c for c in settings.cameras if c.enabled]
