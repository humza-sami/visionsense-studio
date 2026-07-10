from frameinsight.rules.zone_dwell import ZoneDwell

from .util import SQUARE, det_at_foot, make_rule


def feed(rule, frames):
    """frames: list of (ts, [(tid, fx, fy), ...])"""
    for ts, tracks in frames:
        rule.process_frame(ts, [det_at_foot(ts, tid, fx, fy)
                                for tid, fx, fy in tracks])


def test_visit_measures_dwell():
    rule, cap = make_rule(ZoneDwell, SQUARE, sustain_s=1.0, min_dwell_s=3.0,
                          exit_grace_s=1.0)
    frames = [(t / 2, [(1, 0.5, 0.5)]) for t in range(0, 41)]      # inside 0..20s
    frames += [(20.5 + t / 2, [(1, 0.1, 0.5)]) for t in range(0, 6)]  # outside
    feed(rule, frames)
    assert cap.kinds().count("dwell_started") == 1
    done = cap.of_kind("dwell_completed")
    assert len(done) == 1
    assert abs(done[0].data["dwell_s"] - 20.0) < 1.0
    assert done[0].track_id == 1


def test_walkthrough_below_min_dwell_is_dropped():
    rule, cap = make_rule(ZoneDwell, SQUARE, sustain_s=0.5, min_dwell_s=3.0,
                          exit_grace_s=0.5)
    frames = [(t / 10, [(2, 0.5, 0.5)]) for t in range(0, 11)]     # inside 1s only
    frames += [(1.1 + t / 10, [(2, 0.1, 0.5)]) for t in range(0, 10)]
    feed(rule, frames)
    assert cap.of_kind("dwell_completed") == []


def test_short_exit_bridged_by_grace():
    rule, cap = make_rule(ZoneDwell, SQUARE, sustain_s=0.5, min_dwell_s=3.0,
                          exit_grace_s=2.0)
    frames = [(t / 2, [(3, 0.5, 0.5)]) for t in range(0, 11)]       # in 0..5s
    frames += [(5.5, [(3, 0.1, 0.5)]), (6.0, [(3, 0.1, 0.5)])]      # out 1s < grace
    frames += [(6.5 + t / 2, [(3, 0.5, 0.5)]) for t in range(0, 8)]  # back in
    frames += [(11 + t, [(3, 0.1, 0.5)]) for t in range(0, 4)]      # out for good
    feed(rule, frames)
    assert len(cap.of_kind("dwell_completed")) == 1  # one visit, not two


def test_track_lost_inside_closes_visit():
    rule, cap = make_rule(ZoneDwell, SQUARE, sustain_s=0.5, min_dwell_s=3.0,
                          lost_timeout_s=1.0)
    frames = [(t / 2, [(4, 0.5, 0.5)]) for t in range(0, 21)]       # inside 0..10s
    frames += [(10.5 + t, []) for t in range(0, 4)]                 # track vanishes
    feed(rule, frames)
    done = cap.of_kind("dwell_completed")
    assert len(done) == 1
    assert abs(done[0].data["dwell_s"] - 10.0) < 1.0


def test_occupancy_summary_and_average():
    rule, cap = make_rule(ZoneDwell, SQUARE, sustain_s=0.5, min_dwell_s=1.0,
                          exit_grace_s=0.5, summary_every_s=5.0)
    # Two sequential visits: 4s and 8s → avg 6s.
    frames = [(t / 2, [(5, 0.5, 0.5)]) for t in range(0, 9)]
    frames += [(4.5 + t / 2, [(5, 0.1, 0.5)]) for t in range(0, 4)]
    frames += [(7 + t / 2, [(6, 0.5, 0.5)]) for t in range(0, 17)]
    frames += [(15.5 + t / 2, [(6, 0.1, 0.5)]) for t in range(0, 4)]
    frames += [(18 + t, []) for t in range(0, 3)]
    feed(rule, frames)
    occ = cap.of_kind("occupancy")
    assert occ
    last = occ[-1].data
    assert last["visits"] == 2
    assert 5.0 <= last["avg_dwell_s"] <= 7.0
    assert last["max_dwell_s"] >= 7.5
