"""Engineering Brain Program 2 Phase 12 — vehicle-dynamics knowledge tests.

Property / metamorphic / consistency / determinism / safety for the core knowledge
authority. No migration, no decisions, no mutation.
"""
import inspect

import pytest

from strategy import vehicle_dynamics as VD
from strategy.vehicle_dynamics import (
    CANONICAL_AXES, Component, ComponentGroup, all_components, build_engineering_knowledge,
    build_knowledge_report, explain_change, explain_component,
)
from strategy.setup_synthesis import PARAMETER_INTERACTIONS


# --- property: every component fully explained ------------------------------
def test_every_component_has_full_explanation():
    for c in all_components():
        e = explain_component(c)
        assert e is not None
        assert e.primary_mechanism.strip()
        assert e.secondary_interactions
        assert e.gt7_limitations              # GT7 knowledge is mandatory per component
        assert e.raise_effect and e.lower_effect


def test_group_coverage_matches_ui_spec():
    groups = {e.group for e in (explain_component(c) for c in all_components())}
    for required in (ComponentGroup.SUSPENSION, ComponentGroup.DIFFERENTIAL,
                     ComponentGroup.AERO, ComponentGroup.TYRES, ComponentGroup.BRAKES,
                     ComponentGroup.TRANSMISSION, ComponentGroup.WEIGHT_TRANSFER):
        assert required in groups


# --- consistency: never contradicts / duplicates Program-1 sign graph -------
def test_axis_effects_consistent_with_program1_graph():
    for c in all_components():
        e = explain_component(c)
        graph = PARAMETER_INTERACTIONS.get(c.value)
        if graph:
            for axis, sign in graph.items():
                assert e.axis_effects.get(axis) == sign, (c.value, axis)


def test_all_axes_are_canonical():
    for c in all_components():
        for axis in explain_component(c).axis_effects:
            assert axis in CANONICAL_AXES, (c.value, axis)


# --- metamorphic: raise and lower are opposite ------------------------------
def test_raise_and_lower_flip_axis_signs():
    for c in all_components():
        up = explain_change(c, "raise")
        down = explain_change(c, "lower")
        assert up["ok"] and down["ok"]
        for axis in up["axis_effects"]:
            assert up["axis_effects"][axis] == -down["axis_effects"][axis]


def test_explain_change_carries_mechanism_and_gt7():
    r = explain_change("lsd_accel", "raise")
    assert "traction" in r["primary_mechanism"].lower() or "traction" in r["effect"].lower()
    assert r["gt7_limitations"]


# --- golden knowledge assertions --------------------------------------------
def test_golden_known_relationships():
    # raising front ARB adds understeer (less front grip) → apex_front_support negative
    assert explain_component(Component.ARB_FRONT).axis_effects.get("apex_front_support") == -1
    # raising LSD accel improves exit traction
    assert explain_component(Component.LSD_ACCEL).axis_effects.get("exit_traction") == +1
    # a GT7 ride-height limitation mentions bottoming
    assert any("bottom" in g.lower()
               for g in explain_component(Component.RIDE_HEIGHT_FRONT).gt7_limitations)
    # a GT7 tyre limitation mentions wear
    assert any("wear" in g.lower() for g in explain_component(Component.TYRES).gt7_limitations)


# --- determinism / restart --------------------------------------------------
def test_reports_deterministic():
    assert build_knowledge_report()["content_fingerprint"] == \
        build_knowledge_report()["content_fingerprint"]
    assert build_engineering_knowledge()["content_fingerprint"] == \
        build_engineering_knowledge()["content_fingerprint"]


def test_combined_report_has_all_sections():
    r = build_engineering_knowledge()
    assert r["ok"]
    assert r["component_groups"] and r["load_transfer"] and r["handling_phases"]
    assert r["interactions"] and r["lsd_model"] and r["aero_model"]


# --- safety: read-only knowledge, no decisions/mutation ---------------------
def test_unknown_component_safe():
    assert explain_component("nonexistent") is None
    assert explain_change("nonexistent", "raise")["ok"] is False


def test_module_is_pure_and_makes_no_decisions():
    src = inspect.getsource(VD)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai",
                   "save_setup", "create_setup_experiment", "select_experiment",
                   "recommend"):
        assert banned not in src, banned


def test_no_migration_needed():
    # Program 2 knowledge is static code; the DB schema is untouched.
    from strategy._setup_constants import DB_VERSION
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
