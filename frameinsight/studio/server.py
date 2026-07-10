"""Zone Studio — local web UI for a FrameInsight site.

Runs on the edge box (or any machine that can reach the cameras):

    frameinsight studio sites/office            # http://<box>:8765

What it does:
- **Zones tab**: grabs a fresh snapshot from a camera, lets you draw desk
  polygons / gate lines with the mouse, and saves them **normalized** to the
  site's ``zones/<cam>.json`` — the same file a developer would write by hand.
  The engine can't tell the difference.
- **Live tab**: plays one camera at a time (MJPEG via ffmpeg) with detection
  boxes, desk zones, occupancy status, and per-desk timers overlaid. The boxes
  come from ``state/live/<cam>.json``, which the running pipeline publishes
  ~5×/s — no video ever flows between the pipeline and this UI.

Security note: binds to LAN with no auth — it can *see cameras* and *edit
zones*. Keep it on the site network / Tailscale only.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from ..siteconfig import SiteConfig, load_site
from ..zones import Zone

log = logging.getLogger("frameinsight.studio")

STATIC_DIR = Path(__file__).parent / "static"
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


class StreamManager:
    """One live MJPEG re-stream at a time (the UI shows a single camera).

    A reaper thread kills any ffmpeg nobody has read from for 10 s — HTTP
    disconnects aren't always delivered to a blocked sync generator, and an
    orphaned ffmpeg would pull a WAN camera stream forever.
    """

    STALE_S = 10.0

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._cam: str | None = None
        self._lock = threading.Lock()
        self._last_read = 0.0
        threading.Thread(target=self._reaper, daemon=True,
                         name="stream-reaper").start()

    def touch(self) -> None:
        self._last_read = time.time()

    def _reaper(self) -> None:
        while True:
            time.sleep(5)
            with self._lock:
                if (self._proc and self._proc.poll() is None
                        and time.time() - self._last_read > self.STALE_S):
                    log.info("stream idle — reaping ffmpeg (%s)", self._cam)
                    self.close()

    def open(self, cam_id: str, url: str, width: int) -> subprocess.Popen:
        with self._lock:
            self.close()
            cmd = [
                FFMPEG, "-nostdin", "-loglevel", "error",
                "-rtsp_transport", "tcp", "-i", url,
                "-vf", f"fps=6,scale={width}:-2",
                "-q:v", "6", "-f", "mpjpeg", "-",
            ]
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL)
            self._cam = cam_id
            self.touch()
            log.info("stream started: %s", cam_id)
            return self._proc

    def close(self, proc: subprocess.Popen | None = None) -> None:
        p = proc or self._proc
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        if proc is None or proc is self._proc:
            self._proc, self._cam = None, None


def snapshot(url: str, out: Path, timeout_s: int = 20) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-nostdin", "-loglevel", "error", "-y",
           "-rtsp_transport", "tcp", "-i", url,
           "-frames:v", "1", "-q:v", "3", str(out)]
    try:
        return (subprocess.run(cmd, timeout=timeout_s).returncode == 0
                and out.is_file())
    except subprocess.TimeoutExpired:
        return False


def create_app(site_path: str | Path) -> FastAPI:
    site: SiteConfig = load_site(site_path)
    app = FastAPI(title=f"FrameInsight Studio — {site.site}")
    streams = StreamManager()
    snap_dir = site.base_dir / site.state_dir / "snapshots"
    live_dir = site.base_dir / site.state_dir / "live"

    def cam_or_404(cam_id: str):
        cam = site.cameras.get(cam_id)
        if cam is None:
            raise HTTPException(404, f"unknown camera '{cam_id}'")
        return cam

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/site")
    def api_site():
        return {
            "site": site.site,
            "streammux": site.streammux,
            "cameras": [
                {
                    "id": c.cam_id,
                    "channel": c.channel,
                    "fps": c.fps,
                    "group": (site.group_for(c.cam_id).name
                              if site.group_for(c.cam_id) else None),
                    "rules": [
                        {"name": r.name, "kernel": r.kernel, "zone": r.zone}
                        for r in site.rules_for_camera(c.cam_id)
                    ],
                }
                for c in site.cameras.values()
            ],
        }

    @app.get("/api/snapshot/{cam_id}")
    def api_snapshot(cam_id: str, fresh: int = 0):
        cam = cam_or_404(cam_id)
        out = snap_dir / f"{cam_id}.jpg"
        if fresh or not out.is_file():
            if not snapshot(cam.resolved_url(), out):
                raise HTTPException(
                    502, f"could not grab a frame from {cam_id} — is the camera reachable?")
        return FileResponse(out, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/zones/{cam_id}")
    def api_zones_get(cam_id: str):
        cam_or_404(cam_id)
        path = site.base_dir / "zones" / f"{cam_id}.json"
        if not path.is_file():
            return {"reference": None, "zones": []}
        return json.loads(path.read_text())

    @app.post("/api/zones/{cam_id}")
    async def api_zones_post(cam_id: str, body: dict):
        cam_or_404(cam_id)
        zones = body.get("zones", [])
        names = set()
        for z in zones:  # same validation the engine runs — bad zones can't be saved
            try:
                Zone(name=z["name"], type=z["type"],
                     points=tuple((float(p[0]), float(p[1])) for p in z["points"]))
            except (KeyError, ValueError, TypeError) as e:
                raise HTTPException(422, f"invalid zone: {e}")
            if z["name"] in names:
                raise HTTPException(422, f"duplicate zone name '{z['name']}'")
            names.add(z["name"])
        path = site.base_dir / "zones" / f"{cam_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "reference": body.get("reference") or {
                "width": site.streammux["width"],
                "height": site.streammux["height"],
                "snapshot": f"{cam_id}_ref.jpg",
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "zones": zones,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=2))
        tmp.replace(path)
        # Keep the snapshot the zones were drawn on as the reference image.
        snap = snap_dir / f"{cam_id}.jpg"
        if snap.is_file():
            shutil.copyfile(snap, path.parent / f"{cam_id}_ref.jpg")
        log.info("zones saved: %s (%d zones)", cam_id, len(zones))
        return {"ok": True, "zones": len(zones),
                "note": "restart the pipeline (or wait for its next start) to apply"}

    @app.get("/api/live/{cam_id}")
    def api_live(cam_id: str):
        cam_or_404(cam_id)
        path = live_dir / f"{cam_id}.json"
        if not path.is_file():
            return JSONResponse({"stale": True, "detections": [], "rules": {}})
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError:  # mid-replace race; next poll gets it
            return JSONResponse({"stale": True, "detections": [], "rules": {}})
        doc["age_s"] = round(time.time() - doc.get("ts", 0), 2)
        doc["stale"] = doc["age_s"] > 3.0
        return doc

    @app.get("/stream/{cam_id}.mjpg")
    def api_stream(cam_id: str, width: int = 1280):
        cam = cam_or_404(cam_id)
        proc = streams.open(cam_id, cam.resolved_url(), min(width, 2560))

        def gen():
            try:
                while True:
                    chunk = proc.stdout.read(65536)
                    if not chunk:
                        break
                    streams.touch()
                    yield chunk
            finally:
                streams.close(proc)

        return StreamingResponse(
            gen(), media_type="multipart/x-mixed-replace; boundary=ffmpeg",
            headers={"Cache-Control": "no-store"})

    @app.get("/api/events/{cam_id}")
    def api_events(cam_id: str, limit: int = 30):
        """Most recent events for this camera from the site's JSONL sink."""
        cam_or_404(cam_id)
        rows: list[dict] = []
        for cfg in site.sinks:
            if cfg.get("type") != "jsonl":
                continue
            path = site.base_dir / cfg["path"]
            if not path.is_file():
                continue
            with open(path, "rb") as fh:  # read only the tail — file can be huge
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 262144))
                lines = fh.read().decode(errors="replace").splitlines()[1:]
            for line in lines:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("cam_id") == cam_id and ev.get("kind") != "heartbeat":
                    rows.append(ev)
        return rows[-limit:][::-1]

    return app


def run(site_path: str, host: str = "0.0.0.0", port: int = 8765) -> None:
    import uvicorn

    app = create_app(site_path)
    print(f"FrameInsight Studio → http://{host}:{port}  (site: {site_path})")
    uvicorn.run(app, host=host, port=port, log_level="warning")
