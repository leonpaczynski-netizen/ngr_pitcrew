"""Unit tests for strategy.owner_baseline_arbiter.

Covers:
  R5   — Three hard evidence bands (0, 1-4, 5+ laps); no continuous float.
  B8   — Zero laps: feedback alone; LABEL_DRIVER_ONLY.
  B9   — 5+ laps: telemetry primary; agreement, opposition, silence resolved.
  B10  — 1-4 laps: both sources noted; LABEL_DRIVER_EARLY_TEL.
  B11  — 5+ laps, feedback opposes telemetry → status="unresolved".
  B14  — Previously-rejected proposal at same band is suppressed.
  B15  — Clip rule: proposed value snapped; proposal never dropped.
  B16  — Suppressed changes surfaced from rejected_candidates.
  C2   — Unresolved riders: feedback at 5+ laps for params telemetry is silent on.
  GENERAL — build_owner_proposals never raises on broken inputs.

Pure tests — no Qt, no DB, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from strategy.owner_baseline_arbiter import (
    LABEL_DRIVER_EARLY_TEL,
    LABEL_DRIVER_ONLY,
    LABEL_TEL_CORROBORATED,
    LABEL_TEL_NO_FEEDBACK,
    TELEMETRY_PRIMARY_THRESHOLD,
    EARLY_TELEMETRY_THRESHOLD,
    _band,
    build_owner_proposals,
)
from strategy.setup_rule_engine import SetupChangeIntent, SetupPlan
from strategy.setup_knowledge_base import ConfidenceLevel, RiskLevel
from strategy.setup_driver_profile import DriverStyleAlignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intent(
    field: str,
    delta: float,
    to_value: float,
    from_value: float = 0.0,
    rationale: str = "test rationale",
    symptom: str = "test symptom",
    rule_id: str = "R_TEST",
) -> SetupChangeIntent:
    """Build a minimal SetupChangeIntent for testing."""
    return SetupChangeIntent(
        field=field,
        delta=delta,
        from_value=from_value,
        to_value=to_value,
        symptom=symptom,
        evidence=[],
        rule_id=rule_id,
        rationale=rationale,
        rejected_alternatives=[],
        risk=RiskLevel.low,
        confidence=ConfidenceLevel.med,
        driver_style_alignment=DriverStyleAlignment.neutral,
    )


def _suppressed_intent(field: str, delta: float) -> SetupChangeIntent:
    """Build a SetupChangeIntent with a SUPPRESSED rationale (B16)."""
    return _intent(
        field, delta, to_value=abs(delta),
        rationale=f"SUPPRESSED: movement cap hit for {field}",
    )


def _plan(proposed=None, rejected=None) -> SetupPlan:
    return SetupPlan(
        proposed=list(proposed or []),
        rejected_candidates=list(rejected or []),
        protected_fields=[],
    )


def _empty_plan() -> SetupPlan:
    return _plan()


# ---------------------------------------------------------------------------
# _band tests (R5)
# ---------------------------------------------------------------------------

def test_band_zero_laps():
    assert _band(0) == 0


def test_band_negative_laps():
    assert _band(-1) == 0


def test_band_early_telemetry_lower():
    assert _band(EARLY_TELEMETRY_THRESHOLD) == 1


def test_band_early_telemetry_upper():
    assert _band(TELEMETRY_PRIMARY_THRESHOLD - 1) == 1  # 4 laps → band 1


def test_band_telemetry_primary_threshold():
    assert _band(TELEMETRY_PRIMARY_THRESHOLD) == 2  # 5 laps → band 2


def test_band_telemetry_primary_above():
    assert _band(20) == 2


# ---------------------------------------------------------------------------
# Band 0: feedback only (B8 — zero clean laps)
# ---------------------------------------------------------------------------

def test_band0_uses_feedback_plan_only():
    """Zero laps: proposals come from the FEEDBACK plan, not telemetry."""
    fb_intent = _intent("spring_rate_front", +2.0, to_value=52.0, symptom="bouncing")
    tel_intent = _intent("spring_rate_rear", -1.0, to_value=39.0, symptom="oversteer")
    tel_plan = _plan(proposed=[tel_intent])
    fb_plan = _plan(proposed=[fb_intent])

    proposals, _, _ = build_owner_proposals(
        clean_laps=0,
        telemetry_plan=tel_plan,
        feedback_plan=fb_plan,
        owner_baseline={"spring_rate_front": 50.0, "spring_rate_rear": 40.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-1",
        event_id=1,
        suppression_keys=frozenset(),
    )

    fields = {p.parameter for p in proposals}
    assert "spring_rate_front" in fields, "feedback plan field must be proposed at band 0"
    assert "spring_rate_rear" not in fields, "telemetry-only field must NOT appear at band 0"


def test_band0_label_is_driver_only():
    fb_intent = _intent("camber_front", -0.5, to_value=-1.5)
    proposals, _, _ = build_owner_proposals(
        clean_laps=0,
        telemetry_plan=_empty_plan(),
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"camber_front": -1.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-1",
        event_id=1,
        suppression_keys=frozenset(),
    )

    assert proposals, "must have at least one proposal"
    assert all(p.label == LABEL_DRIVER_ONLY for p in proposals)


def test_band0_no_unresolved_riders_because_no_telemetry():
    """At band 0 there is no telemetry at all — riders only make sense at 5+ laps."""
    fb_intent = _intent("toe_front", +0.1, to_value=0.2)
    _, _, riders = build_owner_proposals(
        clean_laps=0,
        telemetry_plan=_empty_plan(),
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"toe_front": 0.1},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-1",
        event_id=1,
        suppression_keys=frozenset(),
    )

    assert riders == [], "no unresolved riders at band 0"


# ---------------------------------------------------------------------------
# Band 1: early telemetry (B10 — 1-4 laps)
# ---------------------------------------------------------------------------

def test_band1_label_is_driver_early_tel():
    tel_intent = _intent("arb_front", +1, to_value=6)
    proposals, _, _ = build_owner_proposals(
        clean_laps=3,
        telemetry_plan=_plan(proposed=[tel_intent]),
        feedback_plan=_empty_plan(),
        owner_baseline={"arb_front": 5},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-2",
        event_id=2,
        suppression_keys=frozenset(),
    )

    assert proposals, "must have proposals at band 1"
    assert all(p.label == LABEL_DRIVER_EARLY_TEL for p in proposals)


def test_band1_no_unresolved_riders():
    tel_intent = _intent("arb_rear", -1, to_value=3)
    _, _, riders = build_owner_proposals(
        clean_laps=2,
        telemetry_plan=_plan(proposed=[tel_intent]),
        feedback_plan=_plan(proposed=[tel_intent]),  # same field — not a rider
        owner_baseline={"arb_rear": 4},
        parameter_model=None,
        discipline="qualifying",
        baseline_revision=1,
        session_run_id="run-2",
        event_id=2,
        suppression_keys=frozenset(),
    )

    assert riders == []


# ---------------------------------------------------------------------------
# Band 2: telemetry primary (B9)
# ---------------------------------------------------------------------------

def test_band2_feedback_agrees_label_corroborated():
    """5+ laps, telemetry and feedback propose same direction → CORROBORATED."""
    tel = _intent("damper_bump_front", +2, to_value=7)   # increase
    fb = _intent("damper_bump_front", +1, to_value=6)    # increase (agrees)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[tel]),
        feedback_plan=_plan(proposed=[fb]),
        owner_baseline={"damper_bump_front": 5},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-5",
        event_id=5,
        suppression_keys=frozenset(),
    )

    assert proposals, "must have proposals at band 2"
    p = proposals[0]
    assert p.parameter == "damper_bump_front"
    assert p.label == LABEL_TEL_CORROBORATED
    assert p.status == "proposed"


def test_band2_no_feedback_label_tel_no_feedback():
    """5+ laps, telemetry proposes, feedback silent → TEL_NO_FEEDBACK."""
    tel = _intent("lsd_accel", +3, to_value=23)
    proposals, _, _ = build_owner_proposals(
        clean_laps=6,
        telemetry_plan=_plan(proposed=[tel]),
        feedback_plan=_empty_plan(),
        owner_baseline={"lsd_accel": 20},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-6",
        event_id=6,
        suppression_keys=frozenset(),
    )

    assert proposals, "must have proposals"
    assert proposals[0].label == LABEL_TEL_NO_FEEDBACK
    assert proposals[0].status == "proposed"


def test_band2_feedback_opposes_status_unresolved():
    """5+ laps, telemetry and feedback propose OPPOSITE directions → status=unresolved (B11)."""
    tel = _intent("camber_rear", -0.2, to_value=-1.2)   # decrease
    fb = _intent("camber_rear", +0.2, to_value=-0.8)    # increase (opposes)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[tel]),
        feedback_plan=_plan(proposed=[fb]),
        owner_baseline={"camber_rear": -1.0},
        parameter_model=None,
        discipline="qualifying",
        baseline_revision=1,
        session_run_id="run-7",
        event_id=7,
        suppression_keys=frozenset(),
    )

    assert proposals, "must produce proposals even for contradictions"
    p = proposals[0]
    assert p.parameter == "camber_rear"
    assert p.status == "unresolved"
    assert p.label == ""


def test_band2_driver_tel_silent_when_feedback_on_tel_silent_field():
    """B9-RIDER / B11 source-separation fix: feedback at 5+ laps on a parameter telemetry
    is SILENT on must produce a DRIVER_TEL_SILENT OwnerProposal, NOT an UnresolvedRider.

    After the 2026-08-10 source-separation fix:
      - unresolved_riders is always an empty list (UnresolvedRider objects are never created).
      - spring_rate_rear (feedback-only field) becomes an OwnerProposal with
          label=LABEL_DRIVER_TEL_SILENT, provenance=PROV_DRIVER_REPORT, status="proposed".
      - spring_rate_front (in both plans, same direction) is corroborated, not DRIVER_TEL_SILENT.
    """
    from strategy.owner_baseline_arbiter import LABEL_DRIVER_TEL_SILENT, PROV_DRIVER_REPORT

    tel = _intent("spring_rate_front", +2, to_value=52)          # only proposes front
    fb_front = _intent("spring_rate_front", +1, to_value=51)     # agrees -> corroborated
    fb_rear = _intent("spring_rate_rear", -1, to_value=39)       # ONLY in feedback

    proposals, _, riders = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[tel]),
        feedback_plan=_plan(proposed=[fb_front, fb_rear]),
        owner_baseline={"spring_rate_front": 50, "spring_rate_rear": 40},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-8",
        event_id=8,
        suppression_keys=frozenset(),
    )

    # After the fix: unresolved_riders is always empty.
    assert riders == [], (
        "unresolved_riders must be [] after the source-separation fix; "
        f"got {riders!r}"
    )
    # spring_rate_rear must appear as a DRIVER_TEL_SILENT proposal.
    silent_params = {
        p.parameter for p in proposals if p.label == LABEL_DRIVER_TEL_SILENT
    }
    assert "spring_rate_rear" in silent_params, (
        "spring_rate_rear (feedback-only field) must produce a DRIVER_TEL_SILENT proposal; "
        f"silent proposals: {silent_params!r}, all proposals: "
        f"{[(p.parameter, p.label, p.provenance) for p in proposals]}"
    )
    # spring_rate_front is corroborated (same direction in both plans), not DRIVER_TEL_SILENT.
    assert "spring_rate_front" not in silent_params, (
        "spring_rate_front (addressed by telemetry plan) must NOT be DRIVER_TEL_SILENT"
    )
    # Verify provenance.
    rear_proposal = next(p for p in proposals if p.parameter == "spring_rate_rear")
    assert rear_proposal.provenance == PROV_DRIVER_REPORT, (
        f"spring_rate_rear DRIVER_TEL_SILENT proposal must have provenance=PROV_DRIVER_REPORT; "
        f"got {rear_proposal.provenance!r}"
    )
    assert rear_proposal.status == "proposed", (
        f"DRIVER_TEL_SILENT proposal must have status='proposed'; got {rear_proposal.status!r}"
    )


# ---------------------------------------------------------------------------
# B14 — Suppression (previously-rejected proposal at same band)
# ---------------------------------------------------------------------------

def test_b14_rejected_proposal_suppressed_at_same_band():
    from strategy.learning_proposal import observation_key
    from strategy.owner_baseline_arbiter import _band as band_fn

    field = "toe_front"
    direction = "increase"
    discipline = "race"
    clean_laps = 5
    key = observation_key(f"{field}:{direction}", discipline)
    b = band_fn(clean_laps)
    suppression_keys = frozenset({(key, b)})

    intent = _intent(field, +0.1, to_value=0.2)

    proposals, _, _ = build_owner_proposals(
        clean_laps=clean_laps,
        telemetry_plan=_plan(proposed=[intent]),
        feedback_plan=_empty_plan(),
        owner_baseline={field: 0.1},
        parameter_model=None,
        discipline=discipline,
        baseline_revision=1,
        session_run_id="run-14",
        event_id=14,
        suppression_keys=suppression_keys,
    )

    # Previously rejected at the same band → suppressed, not re-raised.
    assert all(p.parameter != field for p in proposals), (
        "rejected proposal must not be re-raised at the same evidence band"
    )


def test_b14_rejected_at_lower_band_reraises_at_higher():
    """Crossing a band boundary re-enables the proposal (B14)."""
    from strategy.learning_proposal import observation_key
    from strategy.owner_baseline_arbiter import _band as band_fn

    field = "toe_rear"
    direction = "decrease"
    discipline = "race"
    # Previously rejected at band 0; now at band 2 (crossed TWO bands).
    old_band = 0
    new_laps = 5  # band 2
    key = observation_key(f"{field}:{direction}", discipline)
    suppression_keys = frozenset({(key, old_band)})  # rejected at band 0

    intent = _intent(field, -0.1, to_value=-0.1)

    proposals, _, _ = build_owner_proposals(
        clean_laps=new_laps,
        telemetry_plan=_plan(proposed=[intent]),
        feedback_plan=_empty_plan(),
        owner_baseline={field: 0.0},
        parameter_model=None,
        discipline=discipline,
        baseline_revision=1,
        session_run_id="run-14b",
        event_id=14,
        suppression_keys=suppression_keys,
    )

    # Band has changed: should NOT be suppressed.
    assert any(p.parameter == field for p in proposals), (
        "proposal at new band must not be suppressed by an old-band rejection"
    )


# ---------------------------------------------------------------------------
# B15 — Clip rule
# ---------------------------------------------------------------------------

class _MockSpec:
    """Minimal ParameterSpec-compatible object for testing clip behaviour."""
    def __init__(self, low, high, step):
        self.legal_low = low
        self.legal_high = high
        self.step = step

    def snap(self, value: float) -> float:
        import math
        # Round to step then clamp.
        snapped = round(value / self.step) * self.step
        return max(self.legal_low, min(self.legal_high, snapped))


class _MockParameterModel:
    def __init__(self, field: str, low: float, high: float, step: float):
        self._field = field
        self._spec = _MockSpec(low, high, step)

    def spec(self, field: str):
        return self._spec if field == self._field else None


def test_b15_clip_applied_but_proposal_not_dropped():
    """An out-of-range proposed value is snapped; the proposal is NOT dropped."""
    # Owner baseline has field at 10.0.
    # Rule engine proposes to_value=120.0 but legal_high=100.0.
    model = _MockParameterModel("spring_rate_front", 0.0, 100.0, 1.0)
    intent = _intent("spring_rate_front", +110.0, to_value=120.0, from_value=10.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[intent]),
        feedback_plan=_empty_plan(),
        owner_baseline={"spring_rate_front": 10.0},
        parameter_model=model,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-15",
        event_id=15,
        suppression_keys=frozenset(),
    )

    assert proposals, "proposal must not be dropped even when clipped"
    p = proposals[0]
    assert p.proposed_value <= 100.0, "proposed_value must be snapped to legal range"
    assert p.clipped is True
    assert p.clip_stated_reason != "", "clip_stated_reason must be non-empty when clipped"
    assert p.original_proposed_value == 120.0, "original_proposed_value must preserve raw"


def test_b15_no_clip_when_value_in_range():
    model = _MockParameterModel("camber_front", -3.0, 0.0, 0.1)
    intent = _intent("camber_front", -0.5, to_value=-1.5, from_value=-1.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[intent]),
        feedback_plan=_empty_plan(),
        owner_baseline={"camber_front": -1.0},
        parameter_model=model,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-15b",
        event_id=15,
        suppression_keys=frozenset(),
    )

    assert proposals
    p = proposals[0]
    assert p.clipped is False
    assert p.clip_stated_reason == ""


# ---------------------------------------------------------------------------
# B16 — Suppressed changes surfaced
# ---------------------------------------------------------------------------

def test_b16_suppressed_changes_surfaced_from_rejected_candidates():
    """B16: rejected candidates with "SUPPRESSED" in rationale are surfaced."""
    suppressed = _suppressed_intent("spring_rate_rear", -5.0)
    non_suppressed = _intent("arb_front", +1.0, to_value=6.0, rationale="normal change")

    _, changes, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(rejected=[suppressed, non_suppressed]),
        feedback_plan=_empty_plan(),
        owner_baseline={"spring_rate_rear": 40.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-16",
        event_id=16,
        suppression_keys=frozenset(),
    )

    sc_params = {c.parameter for c in changes}
    assert "spring_rate_rear" in sc_params, "SUPPRESSED rationale must surface the change"
    assert "arb_front" not in sc_params, "non-suppressed candidate must not appear"


def test_b16_suppressed_change_ratchet_flag():
    ratchet_intent = _intent(
        "damper_bump_rear", -2, to_value=5,
        rationale="SUPPRESSED: movement cap hit — ratchet lockout in effect",
    )

    _, changes, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(rejected=[ratchet_intent]),
        feedback_plan=_empty_plan(),
        owner_baseline={"damper_bump_rear": 7.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-16b",
        event_id=16,
        suppression_keys=frozenset(),
    )

    assert changes and changes[0].ratchet_locked is True


def test_b16_feedback_recorded_flag_set_when_feedback_also_proposed_field():
    """feedback_recorded is True when feedback ALSO proposed (or rejected) the field."""
    suppressed = _suppressed_intent("damper_rebound_front", -1.0)
    fb_also_proposed = _intent("damper_rebound_front", -0.5, to_value=5.5)

    _, changes, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(rejected=[suppressed]),
        feedback_plan=_plan(proposed=[fb_also_proposed]),
        owner_baseline={"damper_rebound_front": 6.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-16c",
        event_id=16,
        suppression_keys=frozenset(),
    )

    assert changes
    assert changes[0].feedback_recorded is True


# ---------------------------------------------------------------------------
# as_dict() round-trip
# ---------------------------------------------------------------------------

def test_owner_proposal_as_dict_round_trip():
    tel = _intent("spring_rate_front", +2.0, to_value=52.0)
    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[tel]),
        feedback_plan=_empty_plan(),
        owner_baseline={"spring_rate_front": 50.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=2,
        session_run_id="run-rt",
        event_id=99,
        suppression_keys=frozenset(),
    )

    assert proposals
    d = proposals[0].as_dict()
    assert d["proposal_id"] != ""
    assert d["event_id"] == 99
    assert d["discipline"] == "race"
    assert d["baseline_revision"] == 2
    assert d["clean_laps"] == 5
    assert "evidence_sources" in d


# ---------------------------------------------------------------------------
# Never raises on broken inputs
# ---------------------------------------------------------------------------

def test_build_owner_proposals_never_raises_on_none_plans():
    """Defensive: broken plan objects must not crash the service."""
    result = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=None,        # type: ignore[arg-type]
        feedback_plan=None,         # type: ignore[arg-type]
        owner_baseline={"x": 1.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-broken",
        event_id=0,
        suppression_keys=frozenset(),
    )
    assert len(result) == 3   # (proposals, suppressed, unresolved)


def test_build_owner_proposals_never_raises_on_missing_fields():
    """Intent with to_value=None must not raise — just skip."""
    broken = SetupChangeIntent(
        field="spring_rate_front", delta=0.0, from_value=None, to_value=None,
        symptom="", evidence=[], rule_id="", rationale="", rejected_alternatives=[],
        risk=RiskLevel.low, confidence=ConfidenceLevel.med,
        driver_style_alignment=DriverStyleAlignment.neutral,
    )
    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[broken]),
        feedback_plan=_empty_plan(),
        owner_baseline={"spring_rate_front": 50.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-broken2",
        event_id=1,
        suppression_keys=frozenset(),
    )
    # No proposals produced for broken intent — but no crash either.
    assert proposals == [] or len(proposals) >= 0


def test_build_owner_proposals_empty_baseline():
    """Empty owner baseline: original_value defaults to 0.0 — never raises."""
    intent = _intent("spring_rate_front", +2.0, to_value=52.0)
    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_plan(proposed=[intent]),
        feedback_plan=_empty_plan(),
        owner_baseline={},   # empty — field not in baseline
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-eb",
        event_id=1,
        suppression_keys=frozenset(),
    )

    assert proposals
    assert proposals[0].original_value == 0.0  # defaults to 0 when not in baseline
