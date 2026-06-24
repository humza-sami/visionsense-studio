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
    default_model: str = "yolov8n.pt"
    models_dir: Path = Path(__file__).resolve().parent / "weights"
    yolo_device: str = "cpu"  # "0" for first GPU, "cpu" for CPU

    # ── Streaming ─────────────────────────────────────────────────────────────
    mjpeg_quality: int = 80          # JPEG encode quality 0–100
    frame_queue_maxsize: int = 4     # per-camera queue depth (keep latency low)
    telemetry_interval_ms: int = 200 # WS push interval

    # ── RTSP ──────────────────────────────────────────────────────────────────
    rtsp_timeout_ms: int = 5_000
    rtsp_reconnect_delay_s: float = 5.0

    # ── Channel probing ───────────────────────────────────────────────────────
    probe_timeout_s: float = 3.0
    probe_max_workers: int = 16

    class Config:
        env_prefix = "VS_"
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure model weights directory exists
settings.models_dir.mkdir(parents=True, exist_ok=True)
