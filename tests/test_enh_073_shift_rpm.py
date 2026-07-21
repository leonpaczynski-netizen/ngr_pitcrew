"""ENH-073-001 — principled shift-RPM recommendation (never fabricated)."""
from __future__ import annotations

from strategy.shift_rpm_recommendation import recommend_shift_rpm, ShiftRpmConfidence


def test_gt7_rpm_alert_is_high_confidence_and_authoritative():
    r = recommend_shift_rpm(rpm_alert_max=7500)
    assert r.qualifying_rpm == 7500
    assert r.race_rpm < 7500                     # race a touch conservative
    assert r.confidence == ShiftRpmConfidence.HIGH
    assert r.source == "gt7_rpm_alert"


def test_rpm_alert_outranks_other_evidence():
    r = recommend_shift_rpm(rpm_alert_max=7800, power_rpm=6000, rev_limit_rpm=8200)
    assert r.source == "gt7_rpm_alert" and r.qualifying_rpm == 7800


def test_rev_limit_is_medium_confidence_below_limiter():
    r = recommend_shift_rpm(rev_limit_rpm=8000)
    assert r.confidence == ShiftRpmConfidence.MEDIUM
    assert r.qualifying_rpm < 8000               # just below the limiter


def test_power_rpm_only_is_low_confidence_proxy():
    r = recommend_shift_rpm(power_rpm=7000)
    assert r.confidence == ShiftRpmConfidence.LOW
    assert r.qualifying_rpm > 7000               # optimal sits just past peak power
    assert r.source == "peak_power_proxy"


def test_power_is_clamped_below_known_rev_limit():
    # rev_limit outranks power for the base, but the clamp still protects the value
    r = recommend_shift_rpm(power_rpm=9000, rev_limit_rpm=7400)
    assert r.qualifying_rpm <= 7400


def test_no_data_is_unknown_never_fabricated():
    r = recommend_shift_rpm()
    assert r.qualifying_rpm is None and r.race_rpm is None
    assert r.confidence == ShiftRpmConfidence.NONE
    assert "guess" in r.rationale.lower() or "no usable" in r.rationale.lower()


def test_race_is_not_above_qualifying():
    for kw in ({"rpm_alert_max": 7500}, {"rev_limit_rpm": 8000}, {"power_rpm": 7000}):
        r = recommend_shift_rpm(**kw)
        assert r.race_rpm <= r.qualifying_rpm


def test_never_raises_on_garbage():
    r = recommend_shift_rpm(rpm_alert_max="nonsense", power_rpm=None, rev_limit_rpm=-5)
    assert r.confidence == ShiftRpmConfidence.NONE
