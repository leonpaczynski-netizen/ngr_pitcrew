"""Engineering Brain Program 2 Phase 12 — load-transfer / handling / interaction tests."""
import inspect

import pytest

from strategy import load_transfer as LT
from strategy import handling_balance as HB
from strategy import setup_interactions as SI
from strategy.load_transfer import TransferMode, all_modes, explain_transfer, build_load_transfer_report
from strategy.handling_balance import (
    HandlingPhase, all_phases, explain_phase, phase_components, build_handling_report,
)
from strategy.setup_interactions import (
    Component, all_interactions, aero_model, build_interactions_report,
    explain_interaction, interactions_for, lsd_model,
)


# --- load transfer ----------------------------------------------------------
def test_all_transfer_modes_explained():
    assert len(all_modes()) == 7
    for m in all_modes():
        e = explain_transfer(m)
        assert e.mechanism.strip() and e.gt7_note.strip()
        assert e.increased_by and e.decreased_by


def test_transfer_lookup_safe_and_deterministic():
    assert explain_transfer("nope") is None
    assert build_load_transfer_report()["content_fingerprint"] == \
        build_load_transfer_report()["content_fingerprint"]


def test_lateral_transfer_mentions_roll_stiffness_split():
    e = explain_transfer(TransferMode.LATERAL)
    assert "roll" in e.mechanism.lower() or "roll" in e.balance_effect.lower()


# --- handling balance -------------------------------------------------------
def test_all_phases_explained_with_components_and_modes():
    assert len(all_phases()) == 8
    for p in all_phases():
        e = explain_phase(p)
        assert e.dominant_mechanism.strip() and e.gt7_note.strip()
        assert e.key_components and e.load_transfer_modes
        assert e.understeer_if and e.oversteer_if


def test_phase_key_components_are_valid_and_resolve():
    for p in all_phases():
        e = explain_phase(p)
        for c in e.key_components:
            assert isinstance(c, Component)
        assert len(phase_components(p)) == len(e.key_components)


def test_phase_modes_are_valid_transfer_modes():
    for p in all_phases():
        for m in explain_phase(p).load_transfer_modes:
            assert isinstance(m, TransferMode)


def test_exit_traction_phase_is_lsd_led():
    e = explain_phase(HandlingPhase.EXIT_TRACTION)
    assert Component.LSD_ACCEL in e.key_components


def test_handling_report_deterministic():
    assert build_handling_report()["content_fingerprint"] == \
        build_handling_report()["content_fingerprint"]


# --- setup interactions -----------------------------------------------------
def test_interactions_present_and_valid():
    assert len(all_interactions()) >= 10
    for i in all_interactions():
        assert isinstance(i.a, Component) and isinstance(i.b, Component)
        assert i.a != i.b
        assert i.mechanism.strip() and i.gt7_note.strip()


def test_interaction_lookup_is_order_independent():
    a = explain_interaction("springs_front", "damper_bump_front")
    b = explain_interaction("damper_bump_front", "springs_front")
    assert a is not None and a is b


def test_interactions_for_component():
    hits = interactions_for("lsd_accel")
    assert hits and all(Component.LSD_ACCEL in (i.a, i.b) for i in hits)


def test_lsd_and_aero_models():
    lsd = lsd_model()
    assert {m["parameter"] for m in lsd} == {"initial_torque", "acceleration_locking",
                                             "deceleration_locking"}
    aero = aero_model()
    aspects = {a["aspect"] for a in aero}
    assert {"front_balance", "rear_balance", "ride_height_sensitivity"} <= aspects


def test_interactions_report_deterministic():
    assert build_interactions_report()["content_fingerprint"] == \
        build_interactions_report()["content_fingerprint"]


# --- purity -----------------------------------------------------------------
def test_modules_are_pure():
    for mod in (LT, HB, SI):
        src = inspect.getsource(mod)
        for banned in ("import random", "random.", "time.time", "datetime.now",
                       "import sqlite3", "PyQt", "requests", "urllib", "openai",
                       "save_setup", "select_experiment"):
            assert banned not in src, f"{mod.__name__}:{banned}"
