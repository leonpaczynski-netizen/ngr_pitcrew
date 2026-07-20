"""Phase 37 — driver progression, coaching prioritisation, gear/drive-out, attribution."""
from strategy.driver_development_state import build_driver_development_state, Trend
from strategy.coaching_priority import build_coaching_plan
from tests._race_engineer_helpers import ctx, record, change, residual


def _dev(records):
    return build_driver_development_state("fp", records)


# ---- 10. driver progression ----------------------------------------------------------------- #
def test_trail_brake_progression_across_three_points():
    recs = [
        record("r1", changes=[change("camber_front")], session="s1", at="2026-01-01",
               residuals=[residual("trail_brake", state="present")]),
        record("r2", changes=[change("camber_front")], session="s2", at="2026-01-02",
               residuals=[residual("trail_brake", state="improved_but_present")]),
        record("r3", changes=[change("camber_front")], session="s3", at="2026-01-03",
               residuals=[residual("trail_brake", state="resolved")]),
    ]
    dd = _dev(recs)
    d = {x["dimension"]: x for x in dd.dimensions}["trail_brake_release"]
    assert d["trend"] == Trend.IMPROVING.value
    # improving under a constant setup -> driver technique, not setup.
    assert d["attribution"] == "likely_technique"


def test_latest_good_session_does_not_promote_to_strength():
    recs = [
        record("r1", session="s1", at="2026-01-01", residuals=[residual("understeer", state="present")]),
        record("r2", session="s2", at="2026-01-02", residuals=[residual("understeer", state="present")]),
        record("r3", session="s3", at="2026-01-03", residuals=[residual("understeer", state="resolved")]),
    ]
    dd = _dev(recs)
    d = {x["dimension"]: x for x in dd.dimensions}["turn_in_front_load"]
    assert d["category"] != "strength"


# ---- 11. coaching prioritisation ------------------------------------------------------------ #
def test_persistent_exit_wheelspin_stays_coaching_priority():
    recs = [record(f"w{i}", changes=[change(f)], session=f"s{i}", at=f"2026-01-0{i+1}",
                   residuals=[residual("wheelspin", phase="exit", corner="T2", state="present")])
            for i, f in enumerate(("lsd_initial", "ride_height_rear", "anti_roll_bar_rear"))]
    dd = _dev(recs)
    cp = build_coaching_plan("fp", dd.to_dict())
    dims = {p["dimension"] for p in cp.priorities}
    assert "exit_wheelspin" in dims


# ---- 12. corner-level gear and drive-out evidence ------------------------------------------- #
def test_gear_drive_out_assessment_present():
    recs = [record(f"w{i}", changes=[change(f)], session=f"s{i}", at=f"2026-01-0{i+1}",
                   residuals=[residual("wheelspin", phase="exit", corner="T2", state="present")])
            for i, f in enumerate(("lsd_initial", "ride_height_rear", "anti_roll_bar_rear"))]
    cp = build_coaching_plan("fp", _dev(recs).to_dict())
    p0 = [p for p in cp.priorities if p["dimension"] == "exit_wheelspin"][0]
    assert p0["gear_drive_out"] and "wheelspin_management" in p0["gear_drive_out"]
    assert p0["hold_setup_constant"] is True  # technique/track test isolates the driver


# ---- 13. setup versus driver attribution ---------------------------------------------------- #
def test_problem_across_many_setups_is_technique_or_track():
    # same corner, 3 materially different setups -> track_interaction (one corner).
    recs = [record(f"r{i}", changes=[change(f)], session=f"s{i}", at=f"2026-01-0{i+1}",
                   residuals=[residual("understeer", corner="T1", state="present")])
            for i, f in enumerate(("camber_front", "toe_front", "ride_height_front"))]
    dd = _dev(recs)
    d = {x["dimension"]: x for x in dd.dimensions}["turn_in_front_load"]
    assert d["attribution"] in ("track_interaction", "likely_technique")


def test_problem_after_one_delta_is_setup():
    recs = [
        record("r1", changes=[change("ride_height_rear")], session="s1", at="2026-01-01",
               residuals=[residual("oversteer", phase="exit", corner="T3", state="new", is_new=True)]),
        record("r2", changes=[change("ride_height_rear")], session="s2", at="2026-01-02",
               residuals=[residual("oversteer", phase="exit", corner="T3", state="present")]),
    ]
    dd = _dev(recs)
    d = {x["dimension"]: x for x in dd.dimensions}["rear_stability"]
    assert d["attribution"] == "likely_setup"


def test_setup_only_attribution_is_not_a_coaching_priority():
    recs = [
        record("r1", changes=[change("ride_height_rear")], session="s1", at="2026-01-01",
               residuals=[residual("oversteer", phase="exit", corner="T3", state="new", is_new=True)]),
        record("r2", changes=[change("ride_height_rear")], session="s2", at="2026-01-02",
               residuals=[residual("oversteer", phase="exit", corner="T3", state="present")]),
    ]
    cp = build_coaching_plan("fp", _dev(recs).to_dict())
    assert "rear_stability" not in {p["dimension"] for p in cp.priorities}


# ---- property: shuffle stability + independent evidence never reduces count ------------------ #
def test_driver_state_shuffle_stable():
    recs = [record(f"r{i}", session=f"s{i}", at=f"2026-01-0{i+1}",
                   residuals=[residual("wheelspin", phase="exit", corner="T2", state="present")])
            for i in range(3)]
    a = _dev(recs); b = _dev(list(reversed(recs)))
    assert a.content_fingerprint == b.content_fingerprint


def test_more_evidence_never_reduces_evidence_count():
    base = [record("r1", session="s1", at="2026-01-01",
                   residuals=[residual("wheelspin", phase="exit", corner="T2", state="present")])]
    more = base + [record("r2", session="s2", at="2026-01-02",
                          residuals=[residual("wheelspin", phase="exit", corner="T2", state="present")])]
    c1 = {x["dimension"]: x for x in _dev(base).dimensions}.get("exit_wheelspin", {}).get("evidence_count", 0)
    c2 = {x["dimension"]: x for x in _dev(more).dimensions}["exit_wheelspin"]["evidence_count"]
    assert c2 >= c1
