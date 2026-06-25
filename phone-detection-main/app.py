import threading
import time

import cv2
from flask import Flask, Response, jsonify, render_template, request

from camera import Camera, camera
from detector import detect, switch_model
from state import MODELS, app_state
from tracker import ZoneTracker

app = Flask(__name__)

_trackers = {}          # zone_id (int) -> ZoneTracker
_trackers_lock = threading.Lock()
_latest_frame = None
_frame_lock = threading.Lock()


def _sync_trackers():
    with _trackers_lock:
        zone_ids = {z['id'] for z in app_state.zones}
        for zid in list(_trackers.keys()):
            if zid not in zone_ids:
                del _trackers[zid]
        for zid in zone_ids:
            if zid not in _trackers:
                _trackers[zid] = ZoneTracker()


def _inference_loop():
    global _latest_frame
    while True:
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.01)
            continue
        state = app_state.get()
        annotated, zone_hits = detect(frame, state['main_region'], state['zones'],
                                      state['phone_conf'], state['person_conf'])
        with _trackers_lock:
            for zid, hit in zone_hits.items():
                if zid in _trackers:
                    _trackers[zid].update(hit)
        with _frame_lock:
            _latest_frame = annotated


def _generate_stream():
    while True:
        with _frame_lock:
            frame = _latest_frame
        if frame is None:
            time.sleep(0.01)
            continue
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
               + buf.tobytes() + b'\r\n')
        time.sleep(0.033)  # ~30 fps cap on stream output


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    s = app_state.get()
    initial = {
        'camera_source': s['camera_source'],
        'width':         s['width'],
        'height':        s['height'],
        'model_name':    s['model_name'],
        'phone_conf':    s['phone_conf'],
        'person_conf':   s['person_conf'],
    }
    return render_template('index.html', initial_state=initial)


@app.route('/stream')
def stream():
    return Response(_generate_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/cameras')
def api_cameras():
    return jsonify(Camera.list_cameras())


@app.route('/api/camera', methods=['POST'])
def api_camera():
    data   = request.get_json(force=True, silent=True) or {}
    source = data.get('source', 0)
    # Coerce numeric-looking values to int (JSON may send an int already)
    if isinstance(source, float):
        source = int(source)
    w = int(data.get('width')  or 1280)
    h = int(data.get('height') or 720)
    app_state.set_source(source, w, h)
    result = camera.start(source, w, h)
    if result is None:
        return jsonify({'ok': False, 'error': f'Could not open source: {source}'}), 400
    actual_w, actual_h = result
    return jsonify({'ok': True, 'actual_width': actual_w, 'actual_height': actual_h})


@app.route('/api/models')
def api_models():
    return jsonify({'models': MODELS, 'active': app_state.get()['model_name']})


@app.route('/api/model', methods=['POST'])
def api_model():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get('model', '').strip()
    if name not in MODELS:
        return jsonify({'ok': False, 'error': f'Unknown model: {name}'}), 400
    switch_model(name)
    app_state.set_model(name)
    return jsonify({'ok': True, 'model': name})


@app.route('/api/regions', methods=['GET'])
def api_get_regions():
    s = app_state.get()
    return jsonify({'main_region': s['main_region'], 'zones': s['zones']})


@app.route('/api/regions', methods=['POST'])
def api_set_regions():
    data = request.get_json()
    app_state.set_regions(data.get('main_region'), data.get('zones', []))
    _sync_trackers()
    return jsonify({'ok': True})


@app.route('/api/regions', methods=['DELETE'])
def api_clear_regions():
    app_state.clear_regions()
    with _trackers_lock:
        _trackers.clear()
    return jsonify({'ok': True})


@app.route('/api/stats')
def api_stats():
    zones = app_state.get()['zones']
    result = []
    with _trackers_lock:
        for zone in zones:
            zid = zone['id']
            stats = (_trackers[zid].get_stats() if zid in _trackers
                     else {'total_seconds': 0, 'is_active': False, 'sessions': 0})
            result.append({'id': zid, 'name': zone['name'], **stats})
    return jsonify(result)


@app.route('/api/confidence', methods=['POST'])
def api_confidence():
    data        = request.get_json(force=True, silent=True) or {}
    phone_conf  = float(data.get('phone_conf',  0.5))
    person_conf = float(data.get('person_conf', 0.5))
    app_state.set_confidence(phone_conf, person_conf)
    return jsonify({'ok': True, 'phone_conf': phone_conf, 'person_conf': person_conf})


@app.route('/api/stats/reset', methods=['POST'])
def api_reset_stats():
    with _trackers_lock:
        for t in _trackers.values():
            t.reset()
    return jsonify({'ok': True})


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    s = app_state.get()
    switch_model(s['model_name'])
    camera.start(s['camera_source'], s['width'], s['height'])
    _sync_trackers()
    threading.Thread(target=_inference_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=8000, threaded=True)
