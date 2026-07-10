"""Event sinks — where kernel events go.

Sinks are deliberately dumb: they serialize :class:`~frameinsight.types.Event`
and move on. Business logic lives in kernels; aggregation lives in the cloud
(Supabase). Configure them in site.yaml::

    sinks:
      - {type: console}
      - {type: jsonl,  path: events/events.jsonl}
      - {type: sqlite, path: events/events.db}
      - {type: supabase, table: events, url_env: SUPABASE_URL,
         key_env: SUPABASE_SERVICE_KEY, batch: 50, flush_s: 5}

The Supabase sink batches and never blocks the pipeline: a failed POST logs
and requeues (bounded), because losing the pipeline over a flaky uplink is the
one unforgivable failure (architecture doc §7 — alerts go out immediately, raw
detections never leave the box).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from .types import Event

log = logging.getLogger("frameinsight.sinks")


class EventSink:
    def write(self, event: Event) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class ConsoleSink(EventSink):
    def write(self, event: Event) -> None:
        print(event.to_json(), flush=True)


class JsonlSink(EventSink):
    """Append-only JSONL — the crash-safe local source of truth."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", buffering=1)  # line-buffered

    def write(self, event: Event) -> None:
        self._fh.write(event.to_json() + "\n")

    def close(self) -> None:
        self._fh.close()


class SqliteSink(EventSink):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts REAL NOT NULL, site TEXT, cam_id TEXT, rule TEXT,"
            " kind TEXT, severity TEXT, track_id INTEGER, data TEXT)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
        self._db.commit()

    def write(self, event: Event) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO events (ts, site, cam_id, rule, kind, severity, track_id, data)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (event.ts, event.site, event.cam_id, event.rule, event.kind,
                 event.severity, event.track_id, json.dumps(event.data)))
            self._db.commit()

    def close(self) -> None:
        self._db.close()


class SupabaseSink(EventSink):
    """Batched inserts to a Supabase (PostgREST) table via the REST API."""

    MAX_QUEUE = 5000  # bounded — a dead uplink must not eat RAM forever

    def __init__(self, *, table: str = "events",
                 url_env: str = "SUPABASE_URL",
                 key_env: str = "SUPABASE_SERVICE_KEY",
                 batch: int = 50, flush_s: float = 5.0) -> None:
        import os
        base = os.environ.get(url_env)
        key = os.environ.get(key_env)
        if not base or not key:
            raise ValueError(f"supabase sink: set {url_env} and {key_env} in the environment")
        self._endpoint = base.rstrip("/") + f"/rest/v1/{table}"
        self._key = key
        self._batch = int(batch)
        self._flush_s = float(flush_s)
        self._queue: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True,
                                        name="supabase-sink")
        self._thread.start()

    def write(self, event: Event) -> None:
        row = event.to_dict()
        # Postgres wants ISO timestamps; keep the raw epoch in the row too.
        row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(event.ts)) + "Z"
        row["ts_epoch"] = round(event.ts, 3)
        with self._lock:
            if len(self._queue) >= self.MAX_QUEUE:
                self._queue.pop(0)
                log.warning("supabase queue full — dropping oldest event")
            self._queue.append(row)

    def _pump(self) -> None:
        while not self._stop.wait(self._flush_s):
            self._flush()
        self._flush()

    def _flush(self) -> None:
        with self._lock:
            rows, self._queue = self._queue[:self._batch * 4], self._queue[self._batch * 4:]
        if not rows:
            return
        try:
            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps(rows).encode(),
                headers={"Content-Type": "application/json",
                         "apikey": self._key,
                         "Authorization": f"Bearer {self._key}",
                         "Prefer": "return=minimal"},
                method="POST")
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:  # network is allowed to fail; the pipeline is not
            log.warning("supabase flush failed (%s) — requeueing %d events", e, len(rows))
            with self._lock:
                self._queue = rows + self._queue
                del self._queue[self.MAX_QUEUE:]

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=15)


class CompositeSink(EventSink):
    def __init__(self, sinks: list[EventSink]) -> None:
        self.sinks = sinks

    def write(self, event: Event) -> None:
        for s in self.sinks:
            try:
                s.write(event)
            except Exception:
                log.exception("sink %s failed on event %s", type(s).__name__, event.kind)

    def close(self) -> None:
        for s in self.sinks:
            s.close()


_TYPES = {"console": ConsoleSink, "jsonl": JsonlSink,
          "sqlite": SqliteSink, "supabase": SupabaseSink}


def build_sinks(configs: list[dict[str, Any]], base_dir: str | Path = ".") -> CompositeSink:
    """Instantiate the site.yaml ``sinks:`` list. Relative paths resolve
    against the site directory."""
    sinks: list[EventSink] = []
    for cfg in configs:
        cfg = dict(cfg)
        kind = cfg.pop("type")
        if kind not in _TYPES:
            raise ValueError(f"unknown sink type '{kind}' (have: {', '.join(_TYPES)})")
        if "path" in cfg and not Path(cfg["path"]).is_absolute():
            cfg["path"] = str(Path(base_dir) / cfg["path"])
        sinks.append(_TYPES[kind](**cfg))
    return CompositeSink(sinks)
