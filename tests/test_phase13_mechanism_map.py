"""Phase 13 — diagnosis→mechanism MAP + knowledge-consumption tests (Section 23.1, 23.3).

Proves the structural map consumes the Phase-12 authority directly (no copied component /
interaction / LSD / aero / sign authority), maps every required canonical category, and is
deterministic and order-independent.
"""
import inspect

import pytest

from strategy import mechanism_map as MM
from strategy.mechanism_map import (
    MECHANISM_MAP_VERSION, candidates_for, has_mapping, resolve_handling_phase,
)
from strategy.vehicle_dynamics import Component, all_components
from strategy.handling_balance import HandlingPhase
from strategy.load_transfer import TransferMode


# --- knowledge consumption: the map references ONLY real Phase-12 concepts ----
def test_templates_reference_real_phase12_components_phases_modes():
    for issue, tpls in MM._TEMPLATES_BY_ISSUE.items():
        assert tpls, issue
        for t in tpls:
            assert isinstance(t.primary_component, Component)
            assert isinstance(t.handling_phase, HandlingPhase)
            assert isinstance(t.transfer_mode, TransferMode)
            for c in t.secondary_components:
                assert isinstance(c, Component)
            for a, b in t.interaction_pairs:
                assert isinstance(a, Component) and isinstance(b, Component)


def test_map_defines_no_duplicate_sign_or_knowledge():
    """The map holds structural pointers only — no sign graph, no mechanism prose store,
    no component/interaction/LSD/aero tables of its own."""
    src = inspect.getsource(MM)
    for banned in ("PARAMETER_INTERACTIONS", "primary_mechanism =", "axis_effects",
                   "_LSD_MODEL", "_AERO_MODEL", "increased_by"):
        assert banned not in src, banned


# --- required mapping categories (Section 8) ---------------------------------
REQUIRED = [
    "front_lock", "lockup", "rear_loose_under_braking", "braking_instability",
    "entry_understeer", "entry_oversteer", "mid_corner_understeer", "oversteer",
    "wheelspin", "rear_wheelspin", "rear_loose_on_exit", "poor_drive_out",
    "wrong_gear", "gearing_too_long", "kerb", "bottoming", "tyre_deg", "fuel_use_high",
]


@pytest.mark.parametrize("issue", REQUIRED)
def test_required_categories_have_candidates(issue):
    assert has_mapping(issue)
    assert candidates_for(issue)


# --- phase resolution --------------------------------------------------------
def test_phase_resolution_precedence_and_high_speed():
    # explicit phase string wins
    assert resolve_handling_phase("wheelspin", "braking") == HandlingPhase.TRAIL_BRAKING
    # issue-type implied phase when no string
    assert resolve_handling_phase("wheelspin", "") == HandlingPhase.EXIT_TRACTION
    # high-speed context lifts mid/exit understeer to the high-speed phase
    assert resolve_handling_phase("mid_corner_understeer", "apex", "high_speed") \
        == HandlingPhase.HIGH_SPEED_STABILITY
    # a genuine high-speed context alone resolves a phase-less generic symptom
    assert resolve_handling_phase("understeer", "", "high_speed") \
        == HandlingPhase.HIGH_SPEED_STABILITY
    # phase-less generic symptom with no speed context is unresolved (too broad)
    assert resolve_handling_phase("understeer", "") is None


def test_unknown_issue_type_has_no_mapping():
    assert not has_mapping("teleporting")
    assert candidates_for("teleporting") == ()


# --- exit wheelspin must NOT reduce to an automatic LSD explanation ----------
def test_wheelspin_primary_is_traction_demand_not_lsd():
    tpls = candidates_for("wheelspin")
    primaries = [t for t in tpls if t.role_hint == "primary"]
    assert len(primaries) == 1
    assert primaries[0].primary_component == Component.TRANSMISSION   # not an LSD component
    # LSD is present only as a competing interaction, never the sole/primary explanation
    lsd = [t for t in tpls if t.primary_component == Component.LSD_ACCEL]
    assert lsd and all(t.role_hint == "competing" for t in lsd)


def test_poor_drive_out_keeps_competing_causes_incl_technique():
    tpls = candidates_for("poor_drive_out")
    comps = {t.primary_component for t in tpls}
    assert Component.TRANSMISSION in comps           # gear/torque
    assert Component.SPRINGS_REAR in comps or Component.LSD_ACCEL in comps
    assert any(t.is_driver_technique for t in tpls)  # delayed throttle preserved


# --- determinism -------------------------------------------------------------
def test_candidate_order_is_stable():
    assert [t.mechanism_id for t in candidates_for("wheelspin")] == \
           [t.mechanism_id for t in candidates_for("wheelspin")]


def test_version_constant():
    assert MECHANISM_MAP_VERSION == "mechanism_map_v1"
