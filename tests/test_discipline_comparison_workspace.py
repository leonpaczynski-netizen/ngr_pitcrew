"""Base / Qualifying / Race comparison workspace tests (Engineering-Brain Phase 7).

The workspace is a fuller, self-contained view of the discipline field plan: three
objective header cards, a shared-foundation summary, and the genuinely-differing
fields grouped by subsystem with a per-divergence rationale. The render helper is
module-level and Qt-free (string assertions only); one integration test proves the
richer payload (per-discipline objective cards + why-it-differs) flows through the
real production advisor path.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from ui.setup_builder_ui import (
    _discipline_comparison_workspace_html,
    _discipline_field_plan_html,
    _subsystem_for_field,
    SetupBuilderMixin,
)

# Reuse the Group 64 UAT harness for the integration proof.
from tests.test_group63_setup_brain_uat2 import _uat_history, _CAR
from strategy.setup_ranges import resolve_ranges


def _plan_with_divergence() -> dict:
    """A synthetic discipline plan: some shared fields, some genuinely differing."""
    return {
        "objective": "RACE",
        "disciplines": [
            {"key": "base", "label": "Base", "objective": "balanced platform",
             "confidence": "medium"},
            {"key": "qualifying", "label": "Qualifying",
             "objective": "one-lap outright pace", "confidence": "high"},
            {"key": "race", "label": "Race",
             "objective": "minimum total race time", "confidence": "high"},
        ],
        "rows": [
            # Shared across all three — part of the platform, not a divergence.
            {"field": "arb_rear", "base": 5, "qualifying": 5, "race": 5,
             "differs": False, "disposition": "AUTHORED", "proven": None},
            # Aero diverges: quali runs more front wing than base/race.
            {"field": "aero_front", "base": 450, "qualifying": 480, "race": 450,
             "differs": True, "disposition": "AUTHORED", "proven": None,
             "why_qualifying": "more front downforce for sharper turn-in at max attack"},
            # Ride height diverges: quali lower for one-lap aero.
            {"field": "ride_height_front", "base": 70, "qualifying": 62, "race": 72,
             "differs": True, "disposition": "AUTHORED", "proven": None,
             "why_qualifying": "lower platform for more aero over one lap",
             "why_race": "raised to avoid long-run bottoming over the stint"},
            # Diff diverges and is proven-seeded from history.
            {"field": "lsd_accel", "base": 15, "qualifying": 15, "race": 20,
             "differs": True, "disposition": "PROVEN_HISTORY_SEED", "proven": 20,
             "why_race": "more accel-side lock for repeatable exit traction"},
        ],
        "differing_fields": ["aero_front", "ride_height_front", "lsd_accel"],
        "seeded_from_history": ["lsd_accel"],
    }


# --------------------------------------------------------------- subsystem classifier

def test_subsystem_classifier_groups_known_fields():
    assert _subsystem_for_field("aero_front") == "Aerodynamics"
    assert _subsystem_for_field("ride_height_rear") == "Springs & ride height"
    assert _subsystem_for_field("arb_front") == "Anti-roll bars"
    assert _subsystem_for_field("camber_front") == "Alignment"
    assert _subsystem_for_field("lsd_accel") == "Differential"
    assert _subsystem_for_field("final_drive") == "Gearing"
    assert _subsystem_for_field("brake_bias") == "Brakes"


def test_subsystem_classifier_unknown_field_falls_back():
    assert _subsystem_for_field("some_exotic_knob") == "Other adjustments"
    assert _subsystem_for_field("") == "Other adjustments"


# --------------------------------------------------------------- workspace rendering

def test_workspace_renders_cards_shared_summary_and_groups():
    html = _discipline_comparison_workspace_html(_plan_with_divergence())
    assert "comparison workspace" in html
    # Objective header cards.
    for label in ("Base", "Qualifying", "Race"):
        assert label in html
    assert "one-lap outright pace" in html
    assert "high confidence" in html
    # Shared-foundation summary: 1 of 4 fields shared, 3 diverge.
    assert "<b>1</b> of 4 fields are identical" in html
    # Subsystem group headers for the diverging fields.
    for group in ("Aerodynamics", "Springs &amp; ride height", "Differential"):
        assert group in html
    # Per-divergence rationale surfaced.
    assert "sharper turn-in" in html
    assert "repeatable exit traction" in html
    # Proven-history marker + seeded note.
    assert "proven 20" in html
    assert "Seeded from your proven setup: lsd accel" in html


def test_workspace_highlights_only_the_diverging_discipline():
    """Ride height differs in both quali (62) and race (72); aero only in quali."""
    html = _discipline_comparison_workspace_html(_plan_with_divergence())
    # The diverging values appear as Base -> Q -> R triples.
    assert "Base 450" in html and "Q 480" in html
    assert "Base 70" in html and "Q 62" in html and "R 72" in html


def test_workspace_self_guards_on_empty_and_no_divergence():
    assert _discipline_comparison_workspace_html(None) == ""
    assert _discipline_comparison_workspace_html({}) == ""
    assert _discipline_comparison_workspace_html({"rows": []}) == ""
    # A plan where nothing genuinely differs → the compact table is the better
    # surface, so the workspace declines to render.
    all_same = {
        "rows": [{"field": "arb_rear", "base": 5, "qualifying": 5, "race": 5,
                  "differs": False, "disposition": "AUTHORED", "proven": None}],
        "differing_fields": [],
    }
    assert _discipline_comparison_workspace_html(all_same) == ""


def test_render_surfaces_prefers_workspace_over_compact_table():
    """_render_race_engineer_surfaces uses the workspace when fields diverge."""
    data = {"discipline_field_plan": _plan_with_divergence()}
    html = SetupBuilderMixin._render_race_engineer_surfaces(SetupBuilderMixin, data)
    assert "comparison workspace" in html
    # The compact "side by side" table title must NOT also render (no duplication).
    assert "side by side" not in html


def test_render_surfaces_falls_back_to_compact_when_no_divergence():
    same = _plan_with_divergence()
    for r in same["rows"]:
        r["differs"] = False
        r["qualifying"] = r["base"]
        r["race"] = r["base"]
    same["differing_fields"] = []
    data = {"discipline_field_plan": same}
    html = SetupBuilderMixin._render_race_engineer_surfaces(SetupBuilderMixin, data)
    assert "comparison workspace" not in html
    assert "side by side" in html  # compact table is the fallback


# --------------------------------------------------------------- integration proof

def _baseline_advisor():
    from strategy.driving_advisor import DrivingAdvisor
    rec = SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None,
                          best_lap=lambda: None)
    return DrivingAdvisor(rec, SimpleNamespace(), {})


def test_payload_carries_discipline_cards_and_why_through_real_path():
    adv = _baseline_advisor()
    raw = adv.build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False,
        session_type="Race", duration_mins=45.0,
        track_name="NGR Porsche Cup Rd7", layout_id="full",
        historical_setups=_uat_history(),
    )
    dfp = json.loads(raw).get("discipline_field_plan") or {}
    # Per-discipline objective cards are present with concise objectives.
    discs = {d["key"]: d for d in dfp.get("disciplines") or []}
    assert {"base", "qualifying", "race"} <= set(discs)
    assert "one-lap" in discs["qualifying"]["objective"]
    assert "total race time" in discs["race"]["objective"]
    # At least one genuinely-differing field carries a divergence rationale.
    diff_rows = [r for r in dfp.get("rows") or [] if r.get("differs")]
    assert diff_rows
    assert any(r.get("why_qualifying") or r.get("why_race") for r in diff_rows)
    # The workspace renders end-to-end from the real payload.
    html = _discipline_comparison_workspace_html(dfp)
    assert "comparison workspace" in html
