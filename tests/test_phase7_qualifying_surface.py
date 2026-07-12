"""Phase 7 — qualifying-discipline output surface.

A qualifying tune is stated for what it is: a one-lap objective, what it buys, what
it trades away, and a plain 'do not race it' warning. Non-qualifying sessions get no
qualifying claims. Nothing is fabricated — only the applied deltas produce claims.
"""
from __future__ import annotations

import json

from strategy.qualifying_discipline import (
    build_qualifying_brief, qualifying_brief_to_json,
)
from strategy.setup_baseline import _SESSION_BIAS_TABLE


# ------------------------------------------------- unit

def test_non_qualifying_session_produces_no_brief():
    for cat in ("race", "sprint", "endurance", "practice", "unknown", ""):
        b = build_qualifying_brief(cat, _SESSION_BIAS_TABLE.get(cat, {}))
        assert b.is_qualifying is False
        assert b.as_note() == ""


def test_qualifying_brief_has_objective_strengths_compromises_warning():
    b = build_qualifying_brief("qualifying", _SESSION_BIAS_TABLE["qualifying"])
    assert b.is_qualifying is True
    assert "one-lap" in b.objective.lower()
    assert b.strengths and b.compromises
    assert "do not race it" in b.one_lap_warning.lower()


def test_qualifying_brief_reflects_camber_and_diff_tradeoffs():
    b = build_qualifying_brief("qualifying", _SESSION_BIAS_TABLE["qualifying"])
    txt = b.as_note().lower()
    assert "camber" in txt                 # camber_front/rear are in the quali table
    assert "rotation" in txt               # freer diffs
    assert "tyre" in txt                   # the durability cost


def test_only_applied_fields_generate_claims():
    # supply just brake_bias -> only the front-bite/lock claim, plus the overarching
    # stint compromise; no camber/diff claims fabricated
    b = build_qualifying_brief("qualifying", {"brake_bias": -1.0})
    joined = " ".join(b.strengths).lower()
    assert "brake bias" in joined
    assert "camber" not in joined
    assert any("stint" in c.lower() for c in b.compromises)


def test_zero_delta_fields_ignored():
    b = build_qualifying_brief("qualifying", {"camber_front": 0.0})
    assert all("camber" not in s.lower() for s in b.strengths)


def test_raw_qual_string_accepted():
    b = build_qualifying_brief("Qualifying (Time Trial)", {"toe_front": -0.05})
    assert b.is_qualifying is True


def test_json_shape():
    b = build_qualifying_brief("qualifying", _SESSION_BIAS_TABLE["qualifying"])
    j = qualifying_brief_to_json(b)
    assert j["is_qualifying"] is True
    assert set(j) == {"is_qualifying", "objective", "strengths",
                      "compromises", "one_lap_warning"}


# ------------------------------------------------- integration (baseline path)

def _make_advisor():
    import tests.test_group41_validation_gate as G
    return G._make_full_advisor({}, [G._make_lap()])


def _baseline(adv, session_type, duration):
    from strategy.setup_ranges import resolve_ranges
    car = "Porsche 911 RSR (991) '17"
    return json.loads(adv.build_baseline_setup_response(
        car, resolve_ranges(car), "RWD", 6, None, False,
        session_type=session_type, duration_mins=duration))


def test_baseline_qualifying_surfaces_brief_and_warning():
    res = _baseline(_make_advisor(), "Qualifying", 0.0)
    assert res["qualifying_brief"]["is_qualifying"] is True
    assert "do not race it" in res["analysis"].lower()


def test_baseline_race_has_no_qualifying_brief():
    res = _baseline(_make_advisor(), "Race", 30.0)
    assert res["qualifying_brief"]["is_qualifying"] is False
    assert "do not race it" not in res["analysis"].lower()
