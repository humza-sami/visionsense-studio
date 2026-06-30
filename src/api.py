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
            f'<div class="tile" data-cam="{c}">'
            f'  <div class="bar"><span class="dot" data-dot></span>'
            f'    <span class="name">{c}</span>'
            f'    <span class="badge" data-fps>– fps</span>'
            f'    <span class="badge" data-obj>– obj</span></div>'
            f'  <img src="/stream/{c}" alt="{c}"/>'
            f'  <div class="err" data-err></div>'
            f'</div>'
            for c in cams
        )
        empty = '<p style="padding:20px;color:#9aa4b2">No enabled cameras. Edit config/cameras.yaml.</p>'
        return f"""<!doctype html><html><head><meta charset="utf-8"/>
<title>VisionSense Studio</title>
<style>
  :root{{--bg:#0b0e14;--panel:#121722;--line:#1d2330;--muted:#9aa4b2;--fg:#e6e6e6}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,sans-serif}}
  header{{padding:12px 18px;border-bottom:1px solid var(--line);display:flex;
          justify-content:space-between;align-items:center;gap:16px;position:sticky;top:0;
          background:var(--bg);z-index:5}}
  header .title{{font-size:17px;font-weight:600}}
  header .title small{{color:var(--muted);font-weight:400;margin-left:8px}}
  #stats{{font-size:12px;color:var(--muted);display:flex;gap:14px;flex-wrap:wrap}}
  #stats b{{color:var(--fg);font-weight:600}}
  .wrap{{display:grid;grid-template-columns:1fr 320px;gap:14px;padding:14px;align-items:start}}
  @media(max-width:900px){{.wrap{{grid-template-columns:1fr}}}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}}
  .tile{{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
  .tile img{{width:100%;display:block;background:#000;aspect-ratio:16/9;object-fit:contain}}
  .bar{{display:flex;align-items:center;gap:8px;padding:8px 10px;font-size:12px}}
  .bar .name{{font-weight:600;margin-right:auto}}
  .dot{{width:9px;height:9px;border-radius:50%;background:#6b7280;flex:0 0 auto}}
  .dot.on{{background:#34c759;box-shadow:0 0 6px #34c75988}}
  .dot.off{{background:#ff453a}}
  .badge{{background:#0b0e14;border:1px solid var(--line);border-radius:6px;
          padding:2px 7px;color:var(--muted);font-variant-numeric:tabular-nums}}
  .err{{color:#ff6b6b;font-size:11px;padding:0 10px 8px;min-height:0}}
  aside{{background:var(--panel);border:1px solid var(--line);border-radius:10px;
         position:sticky;top:64px;max-height:calc(100vh - 88px);display:flex;flex-direction:column}}
  aside h2{{margin:0;padding:12px 14px;font-size:13px;border-bottom:1px solid var(--line);
            color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
  #events{{overflow:auto;padding:8px;display:flex;flex-direction:column;gap:6px}}
  .ev{{border:1px solid var(--line);border-left-width:3px;border-radius:6px;padding:7px 9px;font-size:12px}}
  .ev .row{{display:flex;justify-content:space-between;gap:8px}}
  .ev .typ{{font-weight:600}}
  .ev .meta{{color:var(--muted);font-size:11px;margin-top:2px;word-break:break-word}}
  .ev.headcount{{border-left-color:#4f8ef5}}
  .ev.theft_suspected{{border-left-color:#ff453a}}
  .ev.desk_active{{border-left-color:#34c759}}
  .ev .cam{{color:var(--muted)}}
  .empty{{color:var(--muted);font-size:12px;padding:14px}}
</style></head><body>
<header>
  <div class="title">VisionSense Studio<small>live detections</small></div>
  <div id="stats"><span>connecting…</span></div>
</header>
<div class="wrap">
  <div class="grid">{tiles or empty}</div>
  <aside><h2>Events</h2><div id="events"><div class="empty">No events yet.</div></div></aside>
</div>
<script>
const fmtTime = ts => new Date(ts*1000).toLocaleTimeString();
async function pollStatus(){{
  try{{
    const s = await (await fetch('/status')).json();
    const g = s.gpu && s.gpu.available
      ? `GPU <b>${{s.gpu.gpu_util}}%</b> · VRAM <b>${{s.gpu.vram_used_mb}}/${{s.gpu.vram_total_mb}}</b>MB`
      : 'GPU <b>n/a</b> (dev/CPU)';
    const inf = (s.stage_ms && s.stage_ms.inference) ? `infer <b>${{s.stage_ms.inference}}</b>ms` : '';
    let conn = 0, total = 0;
    document.querySelectorAll('.tile').forEach(t=>{{
      const cam = t.dataset.cam, c = (s.cameras||{{}})[cam] || {{}};
      total++;
      const dot = t.querySelector('[data-dot]');
      const live = c.connected !== false;  // file/loop sources may flap; treat undefined as on
      if(c.connected===true){{dot.className='dot on'; conn++;}}
      else if(c.connected===false){{dot.className='dot off';}}
      else {{dot.className='dot'; conn++;}}
      t.querySelector('[data-fps]').textContent = (c.detect_fps??'–')+' fps';
      t.querySelector('[data-obj]').textContent = (c.objects??'–')+' obj';
      t.querySelector('[data-err]').textContent = (c.connected===false && c.last_error) ? c.last_error : '';
    }});
    document.getElementById('stats').innerHTML =
      `loop <b>${{s.loop_fps}}</b> fps · ${{inf}} · cams <b>${{conn}}/${{total}}</b> · ${{g}}`;
  }}catch(e){{ document.getElementById('stats').textContent='status unavailable'; }}
  setTimeout(pollStatus, 1500);
}}
async function pollEvents(){{
  try{{
    const evs = await (await fetch('/events?limit=40')).json();
    const el = document.getElementById('events');
    if(!evs.length){{ el.innerHTML='<div class="empty">No events yet.</div>'; }}
    else el.innerHTML = evs.map(e=>{{
      const meta = Object.entries(e.payload||{{}}).map(([k,v])=>`${{k}}: ${{Array.isArray(v)?'['+v.join(', ')+']':v}}`).join(' · ');
      return `<div class="ev ${{e.type}}"><div class="row"><span class="typ">${{e.type}}</span>`
           + `<span class="cam">${{e.cam}} · ${{fmtTime(e.ts)}}</span></div>`
           + (meta?`<div class="meta">${{meta}}</div>`:'')+`</div>`;
    }}).join('');
  }}catch(e){{}}
  setTimeout(pollEvents, 1500);
}}
pollStatus(); pollEvents();
</script>
</body></html>"""

    return app
