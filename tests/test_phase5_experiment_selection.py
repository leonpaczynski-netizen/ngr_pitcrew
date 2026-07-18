"""Engineering-Brain Phase 5 — candidate generation + deterministic selection."""
from __future__ import annotations

from pathlib import Path

import pytest

from strategy.experiment_selection import (
    SelectionContext, CandidateExperiment, Eligibility, NoSelectionReason,
    generate_candidates, select_experiment, build_test_protocol, legal_step,
    B_FAILED_DIRECTION, B_ILLEGAL_VALUE, B_EQUALS_CURRENT, B_INEFFECTIVE,
    B_NO_MEASURABLE_DELTA,
)

ROOT = Path(__file__).resolve().parents[1]


def _ctx(**over):
    base = dict(
        scope_fingerprint="eck_v1:scope:x", car="RSR", track="Fuji",
        layout_id="full", discipline="Race", dominant_issue="mid_corner_understeer",
        target_phase="apex", target_corners=("T3",), recurrence_class="recurring",
        valid_lap_count=5,
        current_setup={"arb_front": 5, "arb_rear": 4, "aero_front": 300, "toe_front": 0.10},
        ranges={"arb_front": (1, 7), "arb_rear": (1, 7), "aero_front": (0, 500),
                "toe_front": (-1, 1)},
        working_windows={}, failed_directions=(), ineffective_directions=(),
        protected_behaviours=())
    base.update(over)
    return SelectionContext(**base)


# --- 12.3 candidate generation ---------------------------------------------
def test_uses_current_setup_and_legal_increments():
    cands = generate_candidates(_ctx())
    assert cands
    for c in cands:
        assert c.current_value is not None
        assert c.legal_increment == legal_step(c.field)
        assert c.reversible


def test_rejects_illegal_value_at_boundary():
    c = _ctx(current_setup={"arb_front": 1}, ranges={"arb_front": (1, 7)})
    cands = generate_candidates(c)
    af = [x for x in cands if x.field == "arb_front"]
    # to improve apex_front_support, arb_front must DECREASE from 1 -> 0 (illegal)
    assert af and B_ILLEGAL_VALUE in af[0].hard_blockers


def test_avoids_failed_direction():
    # aero_front increase improves apex support; block it as a failed direction
    c = _ctx(failed_directions=(("aero_front", "increase"),))
    cands = generate_candidates(c)
    af = [x for x in cands if x.field == "aero_front"][0]
    assert B_FAILED_DIRECTION in af.hard_blockers
    assert af.eligibility == Eligibility.BLOCKED


def test_avoids_ineffective_direction():
    c = _ctx(ineffective_directions=(("aero_front", "increase"),))
    af = [x for x in generate_candidates(c) if x.field == "aero_front"][0]
    assert B_INEFFECTIVE in af.hard_blockers


def test_no_generic_universal_values():
    # candidates propose a DELTA from current, never a fixed universal value
    cands = generate_candidates(_ctx())
    for c in cands:
        assert c.proposed_value != c.current_value
        assert c.delta is not None and abs(c.delta) > 0


def test_produces_structured_effects_and_protocol():
    cands = generate_candidates(_ctx())
    sel = select_experiment(cands, recurrence_class="recurring", valid_lap_count=5)
    assert sel.selected is not None
    assert sel.selected.expected_positive_effect
    tp = build_test_protocol(sel.selected, parent_setup_id="base1", rollback_target="Base")
    assert tp["rollback_target"] and tp["success_criteria"] and tp["min_valid_laps"] >= 1
    assert tp["field"] == sel.selected.field


def test_unknown_issue_generates_nothing():
    assert generate_candidates(_ctx(dominant_issue="not_a_known_symptom")) == ()


# --- 12.4 selector ---------------------------------------------------------
def test_hard_gates_before_scoring():
    # a blocked candidate (failed direction) is never selected even if best-isolated
    c = _ctx(failed_directions=(("aero_front", "increase"),))
    sel = select_experiment(generate_candidates(c), recurrence_class="recurring",
                            valid_lap_count=5)
    assert sel.selected is None or sel.selected.field != "aero_front"


def test_minimum_effective_single_field_wins():
    sel = select_experiment(generate_candidates(_ctx()), recurrence_class="recurring",
                            valid_lap_count=5)
    assert sel.selected.isolation_score == 1


def test_no_safe_candidate_returns_no_selection():
    # all fields blocked (at legal floor, illegal to move)
    c = _ctx(current_setup={"arb_front": 1}, ranges={"arb_front": (1, 1)})
    sel = select_experiment(generate_candidates(c), recurrence_class="recurring",
                            valid_lap_count=5)
    assert sel.selected is None
    assert sel.no_selection_reason is not None


def test_decision_authority_blocks_selection():
    sel = select_experiment(generate_candidates(_ctx()), decision_blocks=True)
    assert sel.selected is None
    assert sel.no_selection_reason == NoSelectionReason.DECISION_AUTHORITY_BLOCKS


def test_insufficient_recurrence_defers():
    sel = select_experiment(generate_candidates(_ctx()), recurrence_class="isolated",
                            valid_lap_count=5)
    assert sel.selected is None
    assert sel.no_selection_reason == NoSelectionReason.TRACK_OR_CORNER_EVIDENCE_INSUFFICIENT


def test_insufficient_valid_laps_defers():
    sel = select_experiment(generate_candidates(_ctx()), recurrence_class="recurring",
                            valid_lap_count=1)
    assert sel.selected is None


# --- property / metamorphic ------------------------------------------------
def test_candidate_order_independent():
    cands = list(generate_candidates(_ctx()))
    a = select_experiment(cands, recurrence_class="recurring", valid_lap_count=5)
    b = select_experiment(list(reversed(cands)), recurrence_class="recurring", valid_lap_count=5)
    assert a.selected.candidate_id == b.selected.candidate_id


def test_candidate_equal_to_current_never_selected():
    for c in generate_candidates(_ctx()):
        if c.eligibility == Eligibility.ELIGIBLE:
            assert c.proposed_value != c.current_value


def test_all_blocked_becomes_no_selection():
    cands = generate_candidates(_ctx())
    blocked = tuple(c.__class__(**{**c.to_dict(),
                    "eligibility": Eligibility.BLOCKED,
                    "hard_blockers": ("forced",), "direction": c.direction})
                    for c in cands) if False else None
    # simpler: block via failed directions on every generated field
    fields = {c.field for c in cands}
    c2 = _ctx(failed_directions=tuple((f, d) for f in fields
                                      for d in ("increase", "decrease")))
    sel = select_experiment(generate_candidates(c2), recurrence_class="recurring",
                            valid_lap_count=5)
    assert sel.selected is None


def test_no_random_or_wallclock():
    src = (ROOT / "strategy" / "experiment_selection.py").read_text(encoding="utf-8")
    assert "import random" not in src and "random." not in src
    assert "datetime.now" not in src and "time.time" not in src


def test_module_pure():
    src = (ROOT / "strategy" / "experiment_selection.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "from ui.", "import sqlite3", "from data.session_db",
                   "requests", "anthropic", "openai"):
        assert banned not in src, banned
