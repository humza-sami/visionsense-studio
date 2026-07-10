from frameinsight.rules.line_crossing import LineCrossing

from .util import GATE, det_at_foot, make_rule


def walk(rule, tid, ys, *, x=0.5, t0=0.0, dt=0.1, **kw):
    for i, y in enumerate(ys):
        rule.process_frame(t0 + i * dt, [det_at_foot(t0 + i * dt, tid, x, y, **kw)])


def test_downward_crossing_counts_in():
    rule, cap = make_rule(LineCrossing, GATE,
                          label_left="enter", label_right="exit")
    walk(rule, tid=1, ys=[0.30, 0.40, 0.45, 0.55, 0.65])
    crossings = cap.of_kind("line_crossed")
    assert len(crossings) == 1
    assert crossings[0].data["direction"] == "enter"
    assert crossings[0].data["totals"] == {"enter": 1, "exit": 0}
    assert crossings[0].track_id == 1


def test_upward_crossing_counts_out():
    rule, cap = make_rule(LineCrossing, GATE,
                          label_left="enter", label_right="exit")
    walk(rule, tid=2, ys=[0.70, 0.60, 0.45, 0.35])
    assert [e.data["direction"] for e in cap.of_kind("line_crossed")] == ["exit"]


def test_walking_around_line_end_does_not_count():
    rule, cap = make_rule(LineCrossing, GATE)
    walk(rule, tid=3, ys=[0.30, 0.45, 0.55, 0.70], x=0.95)  # beyond x=0.9 endpoint
    assert cap.of_kind("line_crossed") == []


def test_jitter_on_line_does_not_double_count():
    rule, cap = make_rule(LineCrossing, GATE, recross_cooldown_s=2.0)
    # Crosses, then jitters back and forth within the cooldown window.
    walk(rule, tid=4, ys=[0.45, 0.55, 0.48, 0.53, 0.47, 0.56], dt=0.1)
    assert len(cap.of_kind("line_crossed")) == 1


def test_two_tracks_counted_independently():
    rule, cap = make_rule(LineCrossing, GATE)
    for i, (y1, y2) in enumerate(zip([0.3, 0.45, 0.6], [0.7, 0.55, 0.4])):
        ts = i * 0.1
        rule.process_frame(ts, [det_at_foot(ts, 10, 0.4, y1),
                                det_at_foot(ts, 11, 0.6, y2)])
    dirs = sorted(e.data["direction"] for e in cap.of_kind("line_crossed"))
    assert dirs == ["in", "out"]


def test_low_confidence_ignored():
    rule, cap = make_rule(LineCrossing, GATE, min_conf=0.5)
    walk(rule, tid=5, ys=[0.3, 0.45, 0.55, 0.7], conf=0.3)
    assert cap.of_kind("line_crossed") == []


def test_summary_and_state_roundtrip():
    rule, cap = make_rule(LineCrossing, GATE, summary_every_s=1.0)
    walk(rule, tid=6, ys=[0.3, 0.55], dt=0.1)
    # Advance time past the summary interval with empty frames.
    rule.process_frame(2.0, [])
    summaries = cap.of_kind("count_summary")
    assert summaries and summaries[-1].data["in"] == 1

    fresh, _ = make_rule(LineCrossing, GATE)
    fresh.restore_state(rule.snapshot_state())
    assert fresh.counts["in"] == 1
