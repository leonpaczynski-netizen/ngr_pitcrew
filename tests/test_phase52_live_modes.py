"""Phase 52 — live Practice/Qualifying/Race mode views (task items 13-15)."""
from __future__ import annotations

import dataclasses

from strategy.live_activity_modes import (
    LiveMode, LiveDensity, build_practice_live_view, build_qualifying_live_view, build_race_live_view,
    QualifyingLiveView,
)


def test_practice_view_is_focused_density():
    v = build_practice_live_view(activity_title="Setup exp 1", objective="rotation", target_laps=8,
                                 valid_laps=3, target_corners=("T1", "T13"), evidence_missing=("consistency",),
                                 stop_condition="return after 8 clean laps")
    assert v.mode == LiveMode.PRACTICE and v.density == LiveDensity.FOCUSED
    assert v.valid_laps == 3 and "T1" in v.target_corners


def test_qualifying_view_is_minimal_and_excludes_experiment_detail():
    v = build_qualifying_live_view(setup_confirmation="Qualifying setup confirmed", tyre_preparation="1 warm-up",
                                   attempt_number=1, target_info="1:29.4")
    assert v.mode == LiveMode.QUALIFYING and v.density == LiveDensity.MINIMAL
    # structurally cannot carry Practice experiment detail (no such fields)
    fields = {f.name for f in dataclasses.fields(QualifyingLiveView)}
    assert "target_corners" not in fields and "evidence_collected" not in fields
    assert "objective" not in fields and "stop_condition" not in fields


def test_race_view_is_safety_focused_and_issues_no_commands():
    v = build_race_live_view(race_setup_match=True, primary_strategy="2-stop", plan_status="on plan",
                             tyre_awareness="MR ~ 18 laps", fuel_awareness="ok", voice_state="disabled",
                             critical_warnings=())
    assert v.mode == LiveMode.RACE and v.density == LiveDensity.SAFETY
    assert v.issues_commands is False  # never issues an unsupported pit/tyre/fuel command
    assert v.voice_state == "disabled"


def test_race_view_surfaces_critical_warnings():
    v = build_race_live_view(race_setup_match=False, critical_warnings=("setup/context mismatch",))
    assert v.race_setup_match is False
    assert "setup/context mismatch" in v.critical_warnings


def test_live_views_are_deterministic():
    a = build_practice_live_view(activity_title="x", objective="y", target_laps=5)
    b = build_practice_live_view(activity_title="x", objective="y", target_laps=5)
    assert a.fingerprint == b.fingerprint
    # live counters / advisory text do not change the stable identity fingerprint
    c = build_practice_live_view(activity_title="x", objective="y", target_laps=5, valid_laps=99,
                                 current_advisory="brake earlier")
    assert c.fingerprint == a.fingerprint


def test_race_command_flag_cannot_be_set_true():
    # the builder hard-codes issues_commands=False; there is no path to enable commands
    v = build_race_live_view(primary_strategy="1-stop")
    assert v.issues_commands is False
