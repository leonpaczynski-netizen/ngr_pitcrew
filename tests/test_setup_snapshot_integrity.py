"""Phase 2 — setup-snapshot / aero-position integrity.

Regression guard for the UAT defect where a car running MAXIMUM front aero was
classified `aero_front_near_min=True` (then cascaded into a nonsensical "increase
front downforce" diagnosis). Root causes: (a) car-name mismatch -> generic
(0,1000) placeholder range; (b) a value at range max must never be near-min.
"""
from __future__ import annotations

from strategy.setup_diagnosis import _aero_near_min, build_setup_diagnosis
from strategy.setup_ranges import (
    resolve_ranges, car_has_range_overrides, _normalise_car_key,
)

RSR = "Porsche 911 RSR (991) '17"
RSR_VARIANT = "Porsche 911 RSR '17"   # the name stored in setup history (no chassis code)


# ----------------------------------------------------- _aero_near_min invariant

def test_max_aero_is_never_near_min():
    assert _aero_near_min(450, 350, 450) is False
    assert _aero_near_min(1000, 0, 1000) is False


def test_above_max_is_never_near_min():
    assert _aero_near_min(500, 350, 450) is False


def test_genuine_min_is_near_min():
    assert _aero_near_min(350, 350, 450) is True
    assert _aero_near_min(360, 350, 450) is True   # within bottom 10%


def test_mid_range_is_not_near_min():
    assert _aero_near_min(400, 350, 450) is False


def test_reversed_or_degenerate_range_fails_safe():
    assert _aero_near_min(100, 450, 350) is False   # hi < lo
    assert _aero_near_min(100, 100, 100) is False   # span 0


# ----------------------------------------------------- car-name normalisation

def test_name_variant_resolves_real_range():
    assert _normalise_car_key(RSR_VARIANT) == _normalise_car_key(RSR)
    # The variant must resolve the RSR's real aero range, not the (0,1000) placeholder.
    assert resolve_ranges(RSR_VARIANT).get("aero_front") == (350, 450)


def test_car_has_range_overrides():
    assert car_has_range_overrides(RSR) is True
    assert car_has_range_overrides(RSR_VARIANT) is True
    assert car_has_range_overrides("Totally Unlisted Car ZZZ") is False
    assert car_has_range_overrides("") is False


# ----------------------------------------------------- end-to-end diagnosis

def _diag(setup, car=RSR):
    return build_setup_diagnosis(laps=[], setup=setup, car_name=car,
                                 event_ctx={}, feeling=None, location_confidence="low")


def test_diagnosis_max_front_aero_not_near_min():
    d = _diag({"aero_front": 450, "aero_rear": 690})  # both near max
    assert d["aero_front_near_min"] is False
    assert d["aero_rear_near_min"] is False


def test_diagnosis_name_variant_max_aero_not_near_min():
    # The exact UAT trigger: history stores the variant name; max aero must still
    # not be flagged near-min (variant now resolves the real range).
    d = _diag({"aero_front": 450, "aero_rear": 690}, car=RSR_VARIANT)
    assert d["aero_front_near_min"] is False


def test_diagnosis_unlisted_car_at_generic_max_not_near_min():
    # Even against the generic (0,1000) fallback for an unlisted car, a value at
    # the range max can never be near-min (the hard invariant).
    d = _diag({"aero_front": 1000, "aero_rear": 1000}, car="Totally Unlisted Car ZZZ")
    assert d["aero_front_near_min"] is False
    assert d["aero_rear_near_min"] is False


def test_diagnosis_genuine_low_aero_is_near_min():
    # With a real per-car range, a genuinely low front aero IS near-min.
    d = _diag({"aero_front": 355, "aero_rear": 690})
    assert d["aero_front_near_min"] is True
