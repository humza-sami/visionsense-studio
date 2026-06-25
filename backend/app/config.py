"""Application settings — all tuneable via environment variables."""
from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # ── Frontend static build ─────────────────────────────────────────────────
    # FastAPI will serve the compiled React SPA from here if the folder exists.
    frontend_dist: Path = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    # ── YOLO / models ─────────────────────────────────────────────────────────
    default_model: str = "yolo26n.pt"
    models_dir: Path = Path(__file__).resolve().parent / "weights"
    yolo_device: str = "cpu"  # "0" for first GPU, "cpu" for CPU
    ai_image_size: int = 512  # bounded inference resolution; video stays 720p

    # ── Streaming ─────────────────────────────────────────────────────────────
    mjpeg_quality: int = 72          # JPEG encode quality 0–100
    stream_max_width: int = 960      # resize dashboard frames before JPEG encode
    stream_target_fps: float = 10.0  # avoid encoding every source frame
    frame_queue_maxsize: int = 4     # per-camera queue depth (keep latency low)
    telemetry_interval_ms: int = 200 # WS push interval
    media_agent_url: str = "http://host.docker.internal:9010"
    media_agent_timeout_s: float = 2.0
    prefer_native_media: bool = True

    # ── Host inference sidecar ────────────────────────────────────────────────
    # When set, Docker backend delegates YOLO inference to this host-side server
    # so it can use Metal/MPS on Mac instead of CPU inside Docker.
    # Set via VS_REMOTE_INFERENCE_URL=http://host.docker.internal:9020
    remote_inference_url: str = ""

    # ── Persistence ───────────────────────────────────────────────────────────
    data_dir: Path = Path(os.getenv("VS_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
    database_path: Path = Path(
        os.getenv(
            "VS_DATABASE_PATH",
            Path(__file__).resolve().parents[1] / "data" / "visionsense.db",
        )
    )

    # ── RTSP ──────────────────────────────────────────────────────────────────
    rtsp_timeout_ms: int = 5_000
    rtsp_reconnect_delay_s: float = 5.0

    # ── Channel probing ───────────────────────────────────────────────────────
    # Many NVRs throttle simultaneous RTSP handshakes. A small worker pool is
    # both faster and more reliable than opening every channel at once.
    probe_timeout_s: float = 6.0
    probe_max_workers: int = 4

    class Config:
        env_prefix = "VS_"
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure model weights directory exists
settings.models_dir.mkdir(parents=True, exist_ok=True)
