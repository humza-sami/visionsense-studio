"""End-to-end off-GPU: site.yaml → dispatcher → kernels → sinks, via replay."""

import json

import pytest

from frameinsight.replay import replay
from frameinsight.siteconfig import load_site

from .util import Capture

SITE_YAML = """
site: test-school
streammux: {width: 1280, height: 720}
url_template: ${TEST_NVR}/ch{ch}

cameras:
  gate:   {channel: 1, fps: 30}
  cooler: {channel: 2, fps: 30}

groups:
  - name: fast
    model: yolo26s
    detect_fps: 10
    cameras: [gate, cooler]

rules:
  - name: gate_counter
    camera: gate
    kernel: line_crossing
    zone: zones/gate.json#entry_line
    params: {label_left: enter, label_right: exit, summary_every_s: 3600}
  - name: cooler_dwell
    camera: cooler
    kernel: zone_dwell
    zone: zones/cooler.json#cooler_area
    params: {sustain_s: 1.0, min_dwell_s: 3.0, exit_grace_s: 1.0, summary_every_s: 3600}
  - name: custom_wave
    camera: gate
    kernel: wave_detector
    params: {classes: [person], min_conf: 0.1}

sinks:
  - {type: jsonl, path: events/out.jsonl}
"""

GATE_ZONES = {"reference": {"width": 1280, "height": 720},
              "zones": [{"name": "entry_line", "type": "line",
                         "points": [[0.1, 0.5], [0.9, 0.5]]}]}
COOLER_ZONES = {"reference": {"width": 1280, "height": 720},
                "zones": [{"name": "cooler_area", "type": "polygon",
                           "points": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]]}]}

# A trivially custom kernel proving the plugin protocol end-to-end.
PLUGIN = '''
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule

@register_kernel
class WaveDetector(Rule):
    KIND = "wave_detector"
    def on_frame(self, ts, detections):
        for d in detections:
            if d.track_id == 777 and self.cooled_down(ts, str(d.track_id)):
                self.emit(ts, "wave", track_id=d.track_id)
'''


def obj(tid, fx, fy, cls="person", conf=0.9, w=0.05, h=0.2):
    return {"id": tid, "cls": cls, "conf": conf, "bbox": [fx - w / 2, fy - h, w, h]}


def make_site(tmp_path):
    (tmp_path / "zones").mkdir()
    (tmp_path / "apps").mkdir()
    (tmp_path / "site.yaml").write_text(SITE_YAML)
    (tmp_path / "zones/gate.json").write_text(json.dumps(GATE_ZONES))
    (tmp_path / "zones/cooler.json").write_text(json.dumps(COOLER_ZONES))
    (tmp_path / "apps/wave.py").write_text(PLUGIN)
    return tmp_path


def make_recording(tmp_path):
    frames = []
    # gate: track 1 walks down across the line; track 777 waves nearby.
    for i, y in enumerate([0.30, 0.40, 0.45, 0.55, 0.65]):
        frames.append({"cam": "gate", "ts": i * 0.2,
                       "objects": [obj(1, 0.5, y), obj(777, 0.8, 0.3)]})
    # cooler: track 2 dwells inside the polygon for ~8s then leaves.
    for i in range(17):
        frames.append({"cam": "cooler", "ts": i * 0.5,
                       "objects": [obj(2, 0.5, 0.5)]})
    for i in range(4):
        frames.append({"cam": "cooler", "ts": 8.5 + i * 0.5,
                       "objects": [obj(2, 0.1, 0.5)]})
    path = tmp_path / "recording.jsonl"
    path.write_text("\n".join(json.dumps(f) for f in frames) + "\n")
    return path


def test_full_replay_pipeline(tmp_path):
    site = load_site(make_site(tmp_path))
    cap = Capture()
    n = replay(site, cap, make_recording(tmp_path))
    assert n == 26

    crossings = [e for e in cap.of_kind("line_crossed")]
    assert len(crossings) == 1 and crossings[0].data["direction"] == "enter"

    dwells = cap.of_kind("dwell_completed")
    assert len(dwells) == 1 and abs(dwells[0].data["dwell_s"] - 8.0) < 1.0

    assert len(cap.of_kind("wave")) == 1          # custom plugin kernel ran

    # Dispatcher persisted rule state on close (crash-safety).
    state = json.loads((tmp_path / "state/all.json").read_text())
    assert state["gate_counter"]["counts"]["enter"] == 1


def test_validation_catches_config_mistakes(tmp_path):
    make_site(tmp_path)
    bad = SITE_YAML.replace("cameras: [gate, cooler]",
                            "cameras: [gate, cooler, ghost]")
    (tmp_path / "site.yaml").write_text(bad)
    with pytest.raises(ValueError, match="unknown camera 'ghost'"):
        load_site(tmp_path)


def test_camera_in_two_groups_rejected(tmp_path):
    make_site(tmp_path)
    second_group = """  - name: slow
    model: yolo26m
    detect_fps: 1
    cameras: [gate]

rules:"""
    (tmp_path / "site.yaml").write_text(SITE_YAML.replace("rules:", second_group, 1))
    with pytest.raises(ValueError, match="exactly one group"):
        load_site(tmp_path)


def test_zone_reference_must_exist(tmp_path):
    make_site(tmp_path)
    (tmp_path / "site.yaml").write_text(
        SITE_YAML.replace("zones/gate.json#entry_line",
                          "zones/gate.json#no_such_zone"))
    from frameinsight.dispatch import Dispatcher
    site = load_site(tmp_path)
    with pytest.raises(ValueError, match="no zone named 'no_such_zone'"):
        Dispatcher(site, Capture())


def test_resolved_url_expands_env_before_channel(tmp_path, monkeypatch):
    make_site(tmp_path)
    monkeypatch.setenv("TEST_NVR", "rtsp://u:p@1.2.3.4:554/cam?channel={ch}")
    site = load_site(tmp_path)
    # site.yaml template is "${TEST_NVR}/ch{ch}" — both placeholder styles work
    assert site.cameras["cooler"].resolved_url() == \
        "rtsp://u:p@1.2.3.4:554/cam?channel=2/ch2"
