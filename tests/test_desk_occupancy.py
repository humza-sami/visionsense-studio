"""Tests for the office site's desk_occupancy kernel (loaded as a plugin)."""

import importlib.util
from pathlib import Path

from frameinsight.zones import Zone

from .util import Capture, det

KERNEL_PATH = (Path(__file__).parent.parent
               / "sites/office/apps/desk_occupancy.py")
spec = importlib.util.spec_from_file_location("office_desk_occupancy", KERNEL_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
DeskOccupancy = mod.DeskOccupancy

DESK1 = Zone(name="desk1", type="polygon",
             points=((0.1, 0.1), (0.3, 0.1), (0.3, 0.4), (0.1, 0.4)))
DESK2 = Zone(name="desk2", type="polygon",
             points=((0.6, 0.1), (0.8, 0.1), (0.8, 0.4), (0.6, 0.4)))


def make(**over):
    cap = Capture()
    params = dict(site="office", cam_id="cam01", name="desks", emit=cap.write,
                  zones=[DESK1, DESK2], classes=["person"], min_conf=0.4,
                  sustain_s=2.0, empty_grace_s=5.0, working_after_s=30.0,
                  summary_every_s=3600.0)
    params.update(over)
    return DeskOccupancy(**params), cap


def seated(ts, tid=1, cx=0.2, cy=0.25):
    """Detection whose box-CENTER is at (cx, cy) — desk anchor is the center."""
    w, h = 0.06, 0.18
    return det(ts, tid, cx - w / 2, cy - h / 2, w=w, h=h)


def test_sustained_sitting_opens_session_and_vacate_closes_it():
    rule, cap = make()
    for t in range(0, 60):            # seated at desk1 for 60 s
        rule.process_frame(float(t), [seated(float(t))])
    assert cap.kinds().count("desk_occupied") == 1
    for t in range(60, 70):           # walks away; grace is 5 s
        rule.process_frame(float(t), [])
    vac = cap.of_kind("desk_vacated")
    assert len(vac) == 1
    assert vac[0].data["desk"] == "desk1"
    assert abs(vac[0].data["session_s"] - 59.0) < 2.0


def test_short_occlusion_does_not_split_session():
    rule, cap = make()
    frames = [seated(float(t)) for t in range(0, 20)]
    for t in range(0, 20):
        rule.process_frame(float(t), [frames[t]])
    for t in range(20, 23):           # 3 s occlusion < 5 s grace
        rule.process_frame(float(t), [])
    for t in range(23, 40):
        rule.process_frame(float(t), [seated(float(t))])
    assert cap.kinds().count("desk_occupied") == 1
    assert cap.of_kind("desk_vacated") == []


def test_walkby_below_sustain_ignored():
    rule, cap = make()
    rule.process_frame(0.0, [seated(0.0)])
    rule.process_frame(1.0, [seated(1.0)])   # only 1 s < sustain 2 s
    for t in range(2, 10):
        rule.process_frame(float(t), [])
    assert cap.of_kind("desk_occupied") == []
    assert cap.of_kind("desk_vacated") == []


def test_working_flag_and_live_state():
    rule, _ = make()
    for t in range(0, 45):            # 45 s > working_after 30 s
        rule.process_frame(float(t), [seated(float(t)),
                                      seated(float(t), tid=2, cx=0.7, cy=0.3)])
    s = rule._summary(45.0)
    assert s["occupied"] == 2
    assert s["working"] == 2
    assert s["present"] == 2
    assert s["per_desk"]["desk1"]["session_s"] > 40
    live = rule.live_state()
    assert live["desks"] == 2


def test_id_switch_keeps_timer_running():
    rule, cap = make()
    # Same chair, but the tracker re-assigns the ID halfway through.
    for t in range(0, 20):
        rule.process_frame(float(t), [seated(float(t), tid=7)])
    for t in range(20, 40):
        rule.process_frame(float(t), [seated(float(t), tid=99)])
    for t in range(40, 50):
        rule.process_frame(float(t), [])
    vac = cap.of_kind("desk_vacated")
    assert len(vac) == 1
    assert vac[0].data["session_s"] > 35     # one continuous session, not two


def test_state_roundtrip_preserves_today_totals():
    rule, cap = make()
    for t in range(0, 20):
        rule.process_frame(float(t), [seated(float(t))])
    for t in range(20, 30):
        rule.process_frame(float(t), [])
    snap = rule.snapshot_state()
    fresh, _ = make()
    fresh.restore_state(snap)
    assert fresh._st["desk1"]["today_s"] > 15
