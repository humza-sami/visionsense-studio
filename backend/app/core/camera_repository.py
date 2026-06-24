"""SQLite persistence for camera definitions and pipeline configuration."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import List

from app.models.camera import Camera


class CameraRepository:
    def __init__(self, database_path: Path):
        self._path = database_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cameras (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def list(self) -> List[Camera]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM cameras ORDER BY rowid"
            ).fetchall()
        cameras: List[Camera] = []
        for (payload,) in rows:
            camera = Camera.model_validate_json(payload)
            # Runtime state is never restored as live after a process restart.
            camera.status = "idle"
            camera.error_message = None
            cameras.append(camera)
        return cameras

    def save(self, camera: Camera) -> None:
        persisted = camera.model_copy(
            update={"status": "idle", "error_message": None}
        )
        payload = persisted.model_dump_json()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cameras(id, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (camera.id, payload),
            )

    def delete(self, camera_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
