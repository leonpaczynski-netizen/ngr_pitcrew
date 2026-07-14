"""Live per-corner telemetry aggregation + wheel-slip classification tests.

Covers the pure per-axle slip classifier, the per-corner aggregator + telemetry->
diagnosis converter, and the live consumer (fed synthetic packets with the segment
resolver monkeypatched). All pure — no Qt, no DB, no live game.
"""
from __future__ import annotations

from types import SimpleNamespace

from strategy.wheel_slip import (
    classify_wheel_slip, driven_axle, SlipSample, _TWO_PI,
    SPIN_SPEED_RATIO, LOCK_SPEED_RATIO,
)
from strategy.live_corner_aggregator import (
    LiveCornerAggregator, CornerTelemetryAggregate, observed_symptom,
    diagnoses_from_telemetry, phase_from_segment_type, merge_corner_slip_rows,
)


# ------------------------------------------------------------- helpers

def _rps_for_axle_speed(speed_ms, radius=0.33):
    """rad/s that yields a given linear speed at a wheel radius."""
    return speed_ms / (radius * _TWO_PI)


def _wheels(front_ms, rear_ms, radius=0.33):
    fr = _rps_for_axle_speed(front_ms, radius)
    rr = _rps_for_axle_speed(rear_ms, radius)
    return (fr, fr, rr, rr), (radius, radius, radius, radius)


# ------------------------------------------------------------- wheel_slip

def test_driven_axle_by_drivetrain():
    assert driven_axle("FF") == "front"
    assert driven_axle("AWD") == "all"
    assert driven_axle("FR") == "rear"
    assert driven_axle("") == "rear"       # unknown → rear


def test_below_min_speed_is_clean():
    rps, rad = _wheels(0.5, 5.0)
    assert classify_wheel_slip(rps, rad, 1.0, 1.0, 0.0, "FR").kind == "clean"


def test_rwd_rear_wheelspin_detected_front_ignored():
    # Rear axle spinning 60% faster than ground; front tracking ground speed.
    rps, rad = _wheels(front_ms=30.0, rear_ms=30.0 * 1.6)
    s = classify_wheel_slip(rps, rad, 30.0, throttle=1.0, brake=0.0, drivetrain="FR")
    assert s.kind == "wheelspin" and s.axle == "rear"
    assert s.slip_ratio > SPIN_SPEED_RATIO
    # The same fronts-spinning frame must NOT read as wheelspin on a RWD car.
    rps2, rad2 = _wheels(front_ms=30.0 * 1.6, rear_ms=30.0)
    assert classify_wheel_slip(rps2, rad2, 30.0, 1.0, 0.0, "FR").kind == "clean"


def test_fwd_front_wheelspin_detected():
    rps, rad = _wheels(front_ms=30.0 * 1.6, rear_ms=30.0)
    s = classify_wheel_slip(rps, rad, 30.0, 1.0, 0.0, "FF")
    assert s.kind == "wheelspin" and s.axle == "front"


def test_front_lockup_under_braking():
    # Front wheels well below ground speed under braking.
    rps, rad = _wheels(front_ms=30.0 * 0.3, rear_ms=30.0)
    s = classify_wheel_slip(rps, rad, 30.0, throttle=0.0, brake=1.0, drivetrain="FR")
    assert s.kind == "lockup" and s.axle == "front"
    assert s.slip_ratio < LOCK_SPEED_RATIO


def test_no_slip_when_throttle_and_brake_low():
    rps, rad = _wheels(30.0, 30.0)
    assert classify_wheel_slip(rps, rad, 30.0, 0.1, 0.1, "FR").kind == "clean"


def test_malformed_input_is_clean():
    assert classify_wheel_slip(None, None, "x", 1.0, 0.0, "FR").kind == "clean"
    assert classify_wheel_slip((1,), (0.3,), 30.0, 1.0, 0.0, "FR").kind == "clean"


# ------------------------------------------------------------- aggregator

def test_segment_phase_mapping():
    assert phase_from_segment_type("braking_zone") == "braking"
    assert phase_from_segment_type("apex_zone") == "apex"
    assert phase_from_segment_type("corner_exit") == "exit"
    assert phase_from_segment_type("traction_zone") == "exit"
    assert phase_from_segment_type("straight") == ""


def test_events_are_edge_triggered():
    agg = LiveCornerAggregator()
    spin = SlipSample("wheelspin", "rear", 1.5)
    clean = SlipSample("clean", "", 0.0)
    # A continuous slide of 4 frames = ONE event; a gap then slip = a second event.
    for s in (spin, spin, spin, clean, spin):
        agg.add_sample(segment_id="s_t3", turn=3, phase="exit", slip=s, throttle=1.0)
    out = {a.segment_id: a for a in agg.finalize()}["s_t3"]
    assert out.wheelspin_events == 2
    assert out.wheelspin_by_phase.get("exit") == 2
    assert out.spin_axle_counts.get("rear") == 2
    assert out.samples == 5


def test_finalize_and_exit_gear_modal():
    agg = LiveCornerAggregator()
    clean = SlipSample("clean", "", 0.0)
    for g in (2, 2, 3):
        agg.add_sample(segment_id="s_t1", turn=1, phase="exit", slip=clean,
                       throttle=0.8, gear=g, rpm=6000)
    a = agg.finalize()[0]
    assert a.exit_gear == 2 and a.exit_rpm_avg == 6000
    assert abs(a.avg_throttle - 0.8) < 1e-6


def test_observed_symptom_thresholds():
    # Too few samples → None.
    thin = CornerTelemetryAggregate("s", 3, "T3", "left", samples=3, wheelspin_events=3,
                                    lockup_events=0, wheelspin_by_phase={"exit": 3},
                                    lockup_by_phase={}, spin_axle_counts={"rear": 3},
                                    lock_axle_counts={}, avg_throttle=0.9, avg_brake=0.0,
                                    exit_gear=2, exit_rpm_avg=6000)
    assert observed_symptom(thin) is None
    # Enough samples + events → a loose/exit symptom from wheelspin.
    strong = CornerTelemetryAggregate("s", 3, "T3", "left", samples=40, wheelspin_events=6,
                                      lockup_events=0, wheelspin_by_phase={"exit": 6},
                                      lockup_by_phase={}, spin_axle_counts={"rear": 6},
                                      lock_axle_counts={}, avg_throttle=0.9, avg_brake=0.0,
                                      exit_gear=2, exit_rpm_avg=6500)
    phase, symptom, severity, ev = observed_symptom(strong)
    assert (phase, symptom) == ("exit", "loose")
    assert severity == "high" and "wheelspin" in ev


def _segments():
    return [{"segment_type": "apex_zone", "turn_number": 3,
             "reviewed_display_name": "Turn 3", "lap_progress_mid": 0.42,
             "direction": "left"}]


def test_diagnoses_from_telemetry_flips_telemetry_available():
    agg = CornerTelemetryAggregate("s_t3", 3, "Turn 3", "left", samples=40,
                                   wheelspin_events=6, lockup_events=0,
                                   wheelspin_by_phase={"exit": 6}, lockup_by_phase={},
                                   spin_axle_counts={"rear": 6}, lock_axle_counts={},
                                   avg_throttle=0.9, avg_brake=0.0, exit_gear=2,
                                   exit_rpm_avg=6500)
    out = diagnoses_from_telemetry([agg], _segments())
    assert len(out) == 1
    d = out[0]
    assert d["source"] == "live_telemetry"
    assert d["corner"]["turn"] == 3 and d["corner"]["resolved"] is True
    assert d["phase"] == "exit" and d["symptom"] == "loose"
    # telemetry_available=True + resolved corner → confidence lifted above "low".
    assert d["confidence"] in ("medium", "high")
    assert "measured live" in d["telemetry_evidence"]
    assert d["causes"]                        # exit/loose causes present


def test_diagnoses_skips_thin_corners():
    thin = CornerTelemetryAggregate("s", 5, "T5", "", samples=2, wheelspin_events=1,
                                    lockup_events=0, wheelspin_by_phase={}, lockup_by_phase={},
                                    spin_axle_counts={}, lock_axle_counts={}, avg_throttle=0.0,
                                    avg_brake=0.0, exit_gear=None, exit_rpm_avg=None)
    assert diagnoses_from_telemetry([thin], _segments()) == []


# ------------------------------------------------------------- live consumer

def _packet(front_ms, rear_ms, speed_ms, throttle, brake, gear=2, rpm=6000,
            on_track=True, radius=0.33):
    (fr_fl, fr_fr, rr_rl, rr_rr), rad = _wheels(front_ms, rear_ms, radius)
    return SimpleNamespace(
        wheel_rps=(fr_fl, fr_fr, rr_rl, rr_rr), tyre_radius=rad, speed_ms=speed_ms,
        throttle=throttle, brake=brake, current_gear=gear, engine_rpm=rpm,
        car_on_track=on_track)


def test_consumer_accumulates_via_resolver(monkeypatch):
    import telemetry.live_corner_telemetry as lct

    match = SimpleNamespace(segment_id="s_t3", segment_type="corner_exit",
                            turn_number=3, display_name="Turn 3", direction="left")
    monkeypatch.setattr(lct, "packet_to_live_position", lambda p: object())
    monkeypatch.setattr(lct, "resolve_live_segment",
                        lambda *a, **k: SimpleNamespace(match=match))

    tel = lct.LiveCornerTelemetry("fuji", "full", drivetrain="FR", sample_every=1)
    # 6 frames of rear wheelspin on exit → 1 edge-triggered event.
    for _ in range(6):
        tel.add_packet(_packet(front_ms=30.0, rear_ms=48.0, speed_ms=30.0,
                               throttle=1.0, brake=0.0))
    aggs = tel.aggregates()
    assert len(aggs) == 1 and aggs[0].turn == 3
    assert aggs[0].wheelspin_events == 1 and aggs[0].samples == 6
    # And it produces a telemetry-grounded diagnosis once evidence is enough.
    for _ in range(40):
        tel.add_packet(_packet(30.0, 30.0, 30.0, 0.9, 0.0))   # clean exit samples
    # Re-trigger a couple more discrete spins to clear the event bar.
    for pair in ((48.0,), (48.0,), (48.0,)):
        tel.add_packet(_packet(30.0, 30.0, 30.0, 0.5, 0.0))   # reset latch
        tel.add_packet(_packet(30.0, pair[0], 30.0, 1.0, 0.0))
    diags = tel.diagnoses(_segments())
    assert diags and diags[0]["corner"]["turn"] == 3
    assert diags[0]["source"] == "live_telemetry"


def test_consumer_skips_off_track_and_straights(monkeypatch):
    import telemetry.live_corner_telemetry as lct
    # Straight segment → no phase → not attributed.
    straight = SimpleNamespace(segment_id="s_str", segment_type="straight",
                               turn_number=None, display_name="Back straight",
                               direction="")
    monkeypatch.setattr(lct, "packet_to_live_position", lambda p: object())
    monkeypatch.setattr(lct, "resolve_live_segment",
                        lambda *a, **k: SimpleNamespace(match=straight))
    tel = lct.LiveCornerTelemetry("fuji", "full", drivetrain="FR", sample_every=1)
    for _ in range(10):
        tel.add_packet(_packet(30.0, 48.0, 30.0, 1.0, 0.0))
    assert tel.aggregates() == []
    # Off-track frames are dropped entirely.
    tel2 = lct.LiveCornerTelemetry("fuji", "full", drivetrain="FR", sample_every=1)
    monkeypatch.setattr(lct, "resolve_live_segment",
                        lambda *a, **k: SimpleNamespace(
                            match=SimpleNamespace(segment_id="s_t3",
                                                  segment_type="corner_exit",
                                                  turn_number=3, display_name="T3",
                                                  direction="left")))
    tel2.add_packet(_packet(30.0, 48.0, 30.0, 1.0, 0.0, on_track=False))
    assert tel2.aggregates() == []


# ------------------------------------------------------------- advisor plumbing

def test_advisor_surfaces_corner_telemetry_diagnoses(monkeypatch):
    import json
    import strategy.driving_advisor as da
    from tests.test_group63_setup_brain_uat2 import (
        _uat_advisor, _uat_history, _UAT_FEELING, _CAR,
    )
    monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
        "status": "APPROVED", "warnings": [], "contradictions": [],
        "missing_evidence": [], "explanation_notes": "audit ok"}))
    agg = CornerTelemetryAggregate("s_t2", 2, "Turn 2", "left", samples=40,
                                   wheelspin_events=6, lockup_events=0,
                                   wheelspin_by_phase={"exit": 6}, lockup_by_phase={},
                                   spin_axle_counts={"rear": 6}, lock_axle_counts={},
                                   avg_throttle=0.9, avg_brake=0.0, exit_gear=2,
                                   exit_rpm_avg=6500)
    adv = _uat_advisor()
    raw = adv.build_combined_setup_response(
        setup_dict={"final_drive": 4.25, "num_gears": 6, "aero_front": 450,
                    "aero_rear": 590, "lsd_initial": 10, "lsd_accel": 15, "lsd_decel": 10,
                    "arb_front": 6, "arb_rear": 5},
        car_name=_CAR, feeling=_UAT_FEELING, purpose="Race", drivetrain="RR",
        historical_setups=_uat_history(), track_name="NGR Porsche Cup Rd7",
        fuel_multiplier=3.0, refuel_rate_lps=1.0,
        live_corner_aggregates=[agg])
    d = json.loads(raw)
    tel = d.get("corner_telemetry_diagnoses") or []
    assert tel and tel[0]["source"] == "live_telemetry"
    assert tel[0]["phase"] == "exit" and tel[0]["symptom"] == "loose"
    assert "measured live" in tel[0]["telemetry_evidence"]


def test_advisor_omits_surface_without_aggregates(monkeypatch):
    import json
    import strategy.driving_advisor as da
    from tests.test_group63_setup_brain_uat2 import (
        _uat_advisor, _uat_history, _UAT_FEELING, _CAR,
    )
    monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
        "status": "APPROVED", "warnings": [], "contradictions": [],
        "missing_evidence": [], "explanation_notes": "ok"}))
    raw = _uat_advisor().build_combined_setup_response(
        setup_dict={"final_drive": 4.25, "num_gears": 6, "arb_front": 6},
        car_name=_CAR, feeling=_UAT_FEELING, purpose="Race", drivetrain="RR",
        historical_setups=_uat_history(), track_name="NGR Porsche Cup Rd7",
        fuel_multiplier=3.0, refuel_rate_lps=1.0)
    assert "corner_telemetry_diagnoses" not in json.loads(raw)


# ------------------------------------------------------------- cross-session persistence

def _agg(seg="s_t3", turn=3, samples=40, spin=4, gear=2, rpm=6500):
    return CornerTelemetryAggregate(
        seg, turn, "Turn 3", "left", samples=samples, wheelspin_events=spin,
        lockup_events=0, wheelspin_by_phase={"exit": spin}, lockup_by_phase={},
        spin_axle_counts={"rear": spin}, lock_axle_counts={}, avg_throttle=0.9,
        avg_brake=0.0, exit_gear=gear, exit_rpm_avg=rpm)


def test_db_v17_schema_and_table():
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 17
    cols = [r[1] for r in db._conn.execute(
        "PRAGMA table_info(corner_slip_telemetry)").fetchall()]
    assert {"segment_id", "run_id", "wheelspin_events", "throttle_sum"} <= set(cols)


def test_save_get_and_upsert_idempotent():
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    db.save_corner_slip_aggregates(7, "Fuji", "full", run_id=100, aggregates=[_agg(spin=4)])
    rows = db.get_corner_slip_rows(7, "Fuji", "full")
    assert len(rows) == 1
    assert rows[0]["wheelspin_events"] == 4
    assert abs(rows[0]["throttle_sum"] - 0.9 * 40) < 1e-6   # avg_throttle * samples
    # Re-saving the SAME run replaces the row (idempotent) — not a second row.
    db.save_corner_slip_aggregates(7, "Fuji", "full", run_id=100, aggregates=[_agg(spin=6)])
    rows = db.get_corner_slip_rows(7, "Fuji", "full")
    assert len(rows) == 1 and rows[0]["wheelspin_events"] == 6
    # A different run adds a second row.
    db.save_corner_slip_aggregates(7, "Fuji", "full", run_id=200, aggregates=[_agg(spin=3)])
    assert len(db.get_corner_slip_rows(7, "Fuji", "full")) == 2


def test_merge_accumulates_across_runs():
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    db.save_corner_slip_aggregates(7, "Fuji", "full", 100, [_agg(spin=4, samples=40)])
    db.save_corner_slip_aggregates(7, "Fuji", "full", 200, [_agg(spin=3, samples=20)])
    merged = merge_corner_slip_rows(db.get_corner_slip_rows(7, "Fuji", "full"))
    assert len(merged) == 1
    m = merged[0]
    assert m.wheelspin_events == 7          # 4 + 3 across the two runs
    assert m.samples == 60
    assert m.sessions == 2                  # two distinct runs
    assert m.wheelspin_by_phase.get("exit") == 7
    assert abs(m.avg_throttle - 0.9) < 1e-6


def test_merge_filters_car_and_track():
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    db.save_corner_slip_aggregates(7, "Fuji", "full", 100, [_agg()])
    db.save_corner_slip_aggregates(9, "Fuji", "full", 100, [_agg()])   # other car
    db.save_corner_slip_aggregates(7, "Suzuka", "full", 100, [_agg()])  # other track
    assert len(db.get_corner_slip_rows(7, "Fuji", "full")) == 1


def test_diagnoses_report_session_count():
    merged = merge_corner_slip_rows([
        {"segment_id": "s_t3", "turn": 3, "display_name": "Turn 3", "direction": "left",
         "run_id": r, "samples": 40, "wheelspin_events": 4, "lockup_events": 0,
         "wheelspin_by_phase": '{"exit": 4}', "lockup_by_phase": "{}",
         "spin_axle_counts": '{"rear": 4}', "lock_axle_counts": "{}",
         "throttle_sum": 36.0, "brake_sum": 0.0, "exit_gear": 2, "exit_rpm_avg": 6500}
        for r in (100, 200, 300)])
    out = diagnoses_from_telemetry(merged, _segments())
    assert out and out[0]["sessions"] == 3
    assert "across 3 sessions" in out[0]["telemetry_evidence"]
