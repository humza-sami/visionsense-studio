"""Entrypoint: load config → start pipeline → serve API.

  python -m src.main            # uses config/settings.yaml + config/cameras.yaml

Open http://localhost:8000/ for the live detection grid.
"""
from __future__ import annotations

import logging
import signal

import uvicorn

from src.api import create_app
from src.config import load_settings
from src.pipeline import Pipeline


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("main")

    settings = load_settings()
    pipeline = Pipeline(settings)
    pipeline.start()

    app = create_app(
        pipeline,
        jpeg_quality=settings.api.jpeg_quality,
        preview_max_fps=settings.api.preview_max_fps,
    )

    def _shutdown(*_):
        log.info("shutting down…")
        pipeline.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("Serving on http://%s:%d", settings.api.host, settings.api.port)
    uvicorn.run(app, host=settings.api.host, port=settings.api.port, log_level="warning")


if __name__ == "__main__":
    main()
