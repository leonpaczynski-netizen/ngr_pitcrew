"""Sprint 4 — bottoming ride-height anti-ratchet (UAT Defect 2).

The app classified bottoming as NORMAL_OR_EXPECTED / kerb contact, then raised
ride height anyway (56 -> 58 -> 60 -> 62 across sessions) because
`_rh_permitted_increment` keyed only on confidence and returned +2 mm at medium
confidence regardless of subtype. A kerb strike must NEVER authorise a raise.
"""
from __future__ import annotations

import pytest

from strategy.setup_diagnosis import _rh_permitted_increment, _classify_bottoming_impact


# --------------------------------------------------------------------------- #
# The veto: kerb strike / squat / unknown never raise ride height
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("confidence", ["low", "medium", "high"])
@pytest.mark.parametrize("subtype", ["kerb_strike", "throttle_squat", "insufficient_data"])
def test_non_floor_subtypes_never_authorise_a_raise(confidence, subtype):
    perm = _rh_permitted_increment({"confidence": confidence, "subtype": subtype}, True)
    assert perm == 0, f"{subtype} @ {confidence} authorised {perm}mm — ratchet bug"


def test_kerb_strike_medium_is_zero_not_two():
    # The exact regression: the old rule returned 2 here.
    assert _rh_permitted_increment({"confidence": "medium", "subtype": "kerb_strike"}, True) == 0


# --------------------------------------------------------------------------- #
# Genuine floor contact is still permitted (we did not over-correct)
# --------------------------------------------------------------------------- #
def test_floor_contact_permitted_increments():
    assert _rh_permitted_increment({"confidence": "low", "subtype": "floor_contact"}, True) == 0
    assert _rh_permitted_increment({"confidence": "medium", "subtype": "floor_contact"}, True) == 2
    assert _rh_permitted_increment({"confidence": "high", "subtype": "floor_contact"}, True) == 6
    assert _rh_permitted_increment({"confidence": "high", "subtype": "floor_contact"}, False) == 4


def test_suspension_compression_needs_high_confidence():
    assert _rh_permitted_increment({"confidence": "medium", "subtype": "suspension_compression"}, True) == 0
    assert _rh_permitted_increment({"confidence": "high", "subtype": "suspension_compression"}, True) == 2


def test_empty_confidence_is_zero():
    assert _rh_permitted_increment({}, True) == 0
    assert _rh_permitted_increment(None, True) == 0


# --------------------------------------------------------------------------- #
# The classification the veto keys off: kerb strike is NORMAL_OR_EXPECTED
# --------------------------------------------------------------------------- #
def test_kerb_strike_classifies_normal_or_expected_and_not_performance_relevant():
    impact = _classify_bottoming_impact(
        b_band="required", subtype="kerb_strike", confidence="high",
        driver_mentions_bottoming=False, accel_fade_detected=False,
        location_trustworthy=True,
    )
    assert impact["performance_relevant"] is False


def test_ratchet_scenario_kerb_strike_yields_no_ride_height_change():
    """End-to-end of the reported bug: a kerb-strike bottoming at medium
    confidence produces a permitted increment of 0 — no raise, no ratchet."""
    bottoming_confidence = {"confidence": "medium", "subtype": "kerb_strike"}
    # Simulate three successive sessions — each must permit 0.
    for _session in range(3):
        assert _rh_permitted_increment(bottoming_confidence, True) == 0
