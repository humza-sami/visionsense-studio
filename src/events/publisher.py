"""Event publisher (§5.11). Publishes to a Redis stream when enabled, and always
keeps a small in-memory ring buffer so the API can show recent events even
without Redis (the macOS dev default).
"""
from __future__ import annotations

import json
import logging
import threading
from collections import deque

from src.config import RedisConfig
from src.events.schemas import Event

log = logging.getLogger("events")


class EventPublisher:
    def __init__(self, cfg: RedisConfig, ring_size: int = 500) -> None:
        self.cfg = cfg
        self._ring: deque[dict] = deque(maxlen=ring_size)
        self._lock = threading.Lock()
        self._redis = None
        if cfg.enabled:
            try:
                import redis

                self._redis = redis.Redis(host=cfg.host, port=cfg.port,
                                          socket_connect_timeout=2)
                self._redis.ping()
                log.info("Redis connected at %s:%s", cfg.host, cfg.port)
            except Exception as e:
                log.warning("Redis unavailable (%s) — using in-memory events only", e)
                self._redis = None

    def emit(self, event: Event) -> None:
        data = event.to_dict()
        with self._lock:
            self._ring.append(data)
        if self._redis is not None:
            try:
                self._redis.xadd(self.cfg.stream, {"data": json.dumps(data)})
            except Exception as e:
                log.warning("Redis xadd failed: %s", e)
        log.info("EVENT %s/%s %s", event.cam, event.type, event.payload)

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._ring)[-limit:][::-1]
