"""FastAPI surface: health, status/metrics, recent events, per-camera MJPEG preview,
and a minimal dashboard grid so you can SEE detections without a separate frontend.
"""
from __future__ import annotations

import time

import cv2
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from src.pipeline import Pipeline


def create_app(pipeline: Pipeline, jpeg_quality: int = 70, preview_max_fps: int = 15) -> FastAPI:
    app = FastAPI(title="VisionSense Studio — CCTV Detection")
    frame_interval = 1.0 / max(1, preview_max_fps)
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]

    @app.get("/health")
    def health():
        return {"status": "ok", "running": pipeline.running,
                "cameras": pipeline.camera_ids()}

    @app.get("/status")
    def status():
        return JSONResponse(pipeline.status())

    @app.get("/events")
    def events(limit: int = 100):
        return JSONResponse(pipeline.events.recent(limit))

    def _mjpeg(cam_id: str):
        while True:
            frame = pipeline.get_annotated(cam_id)
            if frame is not None:
                ok, buf = cv2.imencode(".jpg", frame, encode_params)
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + buf.tobytes() + b"\r\n")
            time.sleep(frame_interval)

    @app.get("/stream/{cam_id}")
    def stream(cam_id: str):
        return StreamingResponse(
            _mjpeg(cam_id),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.get("/", response_class=HTMLResponse)
    def index():
        cams = pipeline.camera_ids()
        tiles = "".join(
            f'<div class="tile"><div class="cap">{c}</div>'
            f'<img src="/stream/{c}" alt="{c}"/></div>'
            for c in cams
        )
        return f"""<!doctype html><html><head><meta charset="utf-8"/>
<title>VisionSense Studio</title>
<style>
  body{{margin:0;background:#0b0e14;color:#e6e6e6;font-family:system-ui,sans-serif}}
  header{{padding:14px 20px;font-size:18px;font-weight:600;border-bottom:1px solid #1d2330;
          display:flex;justify-content:space-between;align-items:center}}
  #stats{{font-size:12px;color:#9aa4b2;font-weight:400}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px;padding:16px}}
  .tile{{background:#121722;border:1px solid #1d2330;border-radius:10px;overflow:hidden}}
  .tile img{{width:100%;display:block;background:#000;aspect-ratio:16/9;object-fit:contain}}
  .cap{{padding:8px 10px;font-size:13px;color:#9aa4b2}}
</style></head><body>
<header><span>VisionSense Studio — live detections</span><span id="stats">loading…</span></header>
<div class="grid">{tiles or '<p style="padding:20px">No enabled cameras. Edit config/cameras.yaml.</p>'}</div>
<script>
async function poll(){{
  try{{
    const r = await fetch('/status'); const s = await r.json();
    const g = s.gpu && s.gpu.available ? `GPU ${{s.gpu.gpu_util}}% · VRAM ${{s.gpu.vram_used_mb}}/${{s.gpu.vram_total_mb}}MB` : 'GPU n/a (dev)';
    document.getElementById('stats').textContent = `loop ${{s.loop_fps}} fps · ${{g}}`;
  }}catch(e){{}}
  setTimeout(poll, 1500);
}}
poll();
</script>
</body></html>"""

    return app
