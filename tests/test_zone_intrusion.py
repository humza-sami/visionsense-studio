from frameinsight.rules.zone_intrusion import ZoneIntrusion

from .util import SQUARE, det_at_foot, make_rule


def test_sustained_entry_alerts_once():
    rule, cap = make_rule(ZoneIntrusion, SQUARE, sustain_s=2.0, cooldown_s=30.0)
    for t in range(0, 12):
        ts = t * 0.5
        rule.process_frame(ts, [det_at_foot(ts, 1, 0.5, 0.5)])
    alerts = cap.of_kind("intrusion")
    assert len(alerts) == 1
    assert alerts[0].severity == "alert"


def test_blip_below_sustain_never_alerts():
    rule, cap = make_rule(ZoneIntrusion, SQUARE, sustain_s=2.0)
    rule.process_frame(0.0, [det_at_foot(0.0, 2, 0.5, 0.5)])
    rule.process_frame(0.5, [det_at_foot(0.5, 2, 0.5, 0.5)])
    rule.process_frame(1.0, [det_at_foot(1.0, 2, 0.1, 0.5)])  # left before 2s
    assert cap.of_kind("intrusion") == []


def test_intrusion_end_reports_duration():
    rule, cap = make_rule(ZoneIntrusion, SQUARE, sustain_s=1.0)
    for t in range(0, 11):
        ts = t * 1.0
        rule.process_frame(ts, [det_at_foot(ts, 3, 0.5, 0.5)])
    rule.process_frame(11.0, [det_at_foot(11.0, 3, 0.1, 0.5)])
    ends = cap.of_kind("intrusion_end")
    assert len(ends) == 1
    assert abs(ends[0].data["duration_s"] - 10.0) < 0.5
