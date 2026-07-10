from frameinsight.rules.headcount import Headcount

from .util import SQUARE, det_at_foot, make_rule


def frame_of(ts, n, *, fx=0.5, fy=0.5):
    return [det_at_foot(ts, 100 + i, fx + i * 0.001, fy) for i in range(n)]


def test_median_smooths_flicker():
    rule, cap = make_rule(Headcount, None, report_every_s=5.0, window_s=10.0)
    # Mostly 20 people; occasional flicker frames of 12 and 27.
    counts = [20, 20, 12, 20, 20, 27, 20, 20, 20, 12, 20, 20]
    for i, n in enumerate(counts):
        rule.process_frame(i * 1.0, frame_of(i * 1.0, n))
    reports = cap.of_kind("headcount")
    assert reports
    assert reports[-1].data["count"] == 20


def test_zone_limits_counting():
    rule, cap = make_rule(Headcount, SQUARE, report_every_s=2.0)
    for i in range(6):
        ts = float(i)
        dets = frame_of(ts, 3) + [det_at_foot(ts, 900 + j, 0.1, 0.1) for j in range(5)]
        rule.process_frame(ts, dets)
    assert cap.of_kind("headcount")[-1].data["count"] == 3


def test_overcrowded_alert_with_cooldown():
    rule, cap = make_rule(Headcount, None, report_every_s=1.0, window_s=3.0,
                          max_count=10, cooldown_s=60.0)
    for i in range(10):
        rule.process_frame(i * 1.0, frame_of(i * 1.0, 15))
    alerts = cap.of_kind("overcrowded")
    assert len(alerts) == 1          # cooldown suppresses repeats
    assert alerts[0].severity == "alert"
    assert alerts[0].data["count"] == 15
