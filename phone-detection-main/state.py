import json
import os
import threading

STATE_FILE = 'state.json'

MODELS = ['yolo26n.pt', 'yolo26s.pt', 'yolo26m.pt', 'yolo26l.pt', 'yolo26x.pt']


class AppState:
    def __init__(self):
        self._lock = threading.Lock()
        self.camera_source = 0      # int = local device index, str = URL
        self.width = 1280
        self.height = 720
        self.model_name = 'yolo26n.pt'
        self.phone_conf  = 0.5
        self.person_conf = 0.5
        self.main_region = None     # [x1, y1, x2, y2] normalized 0–1, or None
        self.zones = []             # [{'id': int, 'name': str, 'rect': [x1,y1,x2,y2]}]
        self._load()

    def get(self):
        with self._lock:
            return {
                'camera_source': self.camera_source,
                'width': self.width,
                'height': self.height,
                'model_name': self.model_name,
                'phone_conf':  self.phone_conf,
                'person_conf': self.person_conf,
                'main_region': self.main_region,
                'zones': list(self.zones),
            }

    def set_source(self, source, width=1280, height=720):
        with self._lock:
            self.camera_source = source
            self.width = width
            self.height = height
            self._save()

    def set_confidence(self, phone_conf, person_conf):
        with self._lock:
            self.phone_conf  = max(0.01, min(1.0, phone_conf))
            self.person_conf = max(0.01, min(1.0, person_conf))
            self._save()

    def set_model(self, name):
        with self._lock:
            self.model_name = name
            self._save()

    def set_regions(self, main_region, zones):
        with self._lock:
            self.main_region = main_region
            self.zones = zones
            self._save()

    def clear_regions(self):
        with self._lock:
            self.main_region = None
            self.zones = []
            self._save()

    def _save(self):
        data = {
            'camera_source': self.camera_source,
            'width': self.width,
            'height': self.height,
            'model_name': self.model_name,
            'phone_conf':  self.phone_conf,
            'person_conf': self.person_conf,
            'main_region': self.main_region,
            'zones': self.zones,
        }
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            # Backward compat: old state used camera_index (int)
            if 'camera_source' in data:
                src = data['camera_source']
                self.camera_source = int(src) if isinstance(src, (int, float)) else src
            elif 'camera_index' in data:
                self.camera_source = int(data['camera_index'])
            self.width      = data.get('width', 1280)
            self.height     = data.get('height', 720)
            self.model_name  = data.get('model_name', 'yolo26n.pt')
            self.phone_conf  = data.get('phone_conf',  0.5)
            self.person_conf = data.get('person_conf', 0.5)
            self.main_region = data.get('main_region')
            self.zones       = data.get('zones', [])
        except Exception:
            pass


app_state = AppState()
