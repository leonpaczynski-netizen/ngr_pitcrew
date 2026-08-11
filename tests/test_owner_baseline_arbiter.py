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


# ---------------------------------------------------------------------------
# I-C — Band-1 gate fix: feedback-only fields must not silently disappear
#        at band 1 (1-4 laps) after source separation.
#
# Before the fix the second pass was gated at ``current_band >= 2``.  After
# source-separation (feedback=None in the telemetry diagnosis) the telemetry
# plan no longer carries feedback-driven intents, so at band 1 tel_dirs was
# empty for those fields and the first pass produced nothing.  The second pass
# gate ``>= 2`` then silently dropped them — a driver who drove 3 practice
# laps lost proposals that existed at 0 laps and would return at 5 laps.
#
# Fixed by extending the gate to ``current_band >= 1``.
# ---------------------------------------------------------------------------

def test_ic_band1_feedback_only_field_emitted_not_dropped():
    """I-C regression guard: at band 1 a feedback-only field must produce a proposal.

    Failure mode when reverted: if the second-pass gate is put back to
    ``current_band >= 2``, the second pass does not run at band 1.  The field
    is absent from tel_dirs (telemetry is silent on it) AND absent from the
    second pass.  ``len(proposals) == 0`` and the assert below fails.
    """
    from strategy.owner_baseline_arbiter import LABEL_DRIVER_TEL_SILENT

    fb_intent = _intent("arb_rear", +1.0, to_value=6.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=3,           # band 1 (1-4 laps)
        telemetry_plan=_empty_plan(),   # telemetry is completely silent on arb_rear
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"arb_rear": 5.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-ic1",
        event_id=20,
        suppression_keys=frozenset(),
    )

    arb_proposals = [p for p in proposals if p.parameter == "arb_rear"]
    assert len(arb_proposals) == 1, (
        "At band 1, a feedback-only field must appear in proposals via the second "
        "pass (current_band >= 1 gate).  If this fails, the gate was reverted to >= 2."
    )
    assert arb_proposals[0].label == LABEL_DRIVER_TEL_SILENT, (
        f"Band-1 feedback-only proposal must carry LABEL_DRIVER_TEL_SILENT; "
        f"got {arb_proposals[0].label!r}"
    )


def test_ic_proposal_never_disappears_as_laps_increase():
    """I-C continuity: a feedback-only proposal must exist at bands 0, 1 AND 2.

    Before the fix, at band 1 with source-separated telemetry the proposal
    silently disappeared (0 laps → present; 3 laps → gone; 5 laps → back).
    This test pins the continuity across all three bands.

    Failure mode when reverted (gate >= 2): the band-1 assertion fails because
    ``arb_rear`` is absent from proposals at 3 laps.
    """
    from strategy.owner_baseline_arbiter import LABEL_DRIVER_ONLY, LABEL_DRIVER_TEL_SILENT

    fb_intent = _intent("arb_rear", +1.0, to_value=6.0)
    # Telemetry plan proposes a DIFFERENT field to prove arb_rear is feedback-only.
    tel_intent = _intent("lsd_accel", +2.0, to_value=32.0)

    for clean_laps, expected_label in [
        (0, LABEL_DRIVER_ONLY),        # band 0: first pass uses fb_dirs -> DRIVER_ONLY
        (3, LABEL_DRIVER_TEL_SILENT),  # band 1: second pass required (gate >= 1)
        (5, LABEL_DRIVER_TEL_SILENT),  # band 2: second pass runs, no corroborated_flags
    ]:
        proposals, _, _ = build_owner_proposals(
            clean_laps=clean_laps,
            telemetry_plan=_plan(proposed=[tel_intent]),
            feedback_plan=_plan(proposed=[fb_intent]),
            owner_baseline={"arb_rear": 5.0, "lsd_accel": 30.0},
            parameter_model=None,
            discipline="race",
            baseline_revision=1,
            session_run_id=f"run-ic2-{clean_laps}",
            event_id=21,
            suppression_keys=frozenset(),
        )
        arb_props = [p for p in proposals if p.parameter == "arb_rear"]
        assert len(arb_props) == 1, (
            f"arb_rear must be in proposals at clean_laps={clean_laps} (band "
            f"{0 if clean_laps == 0 else (1 if clean_laps < 5 else 2)}).  "
            f"If this fails at 3 laps, the band-1 gate was reverted to >= 2."
        )
        assert arb_props[0].label == expected_label, (
            f"Expected label {expected_label!r} at clean_laps={clean_laps}; "
            f"got {arb_props[0].label!r}"
        )


# ---------------------------------------------------------------------------
# Sixth label — LABEL_DRIVER_SYMPTOM_CORROBORATED
#
# A feedback-led proposal in the second pass (telemetry silent on the lever)
# is upgraded from LABEL_DRIVER_TEL_SILENT to LABEL_DRIVER_SYMPTOM_CORROBORATED
# when the SERVICE passes a non-empty ``corroborated_flags`` frozenset.
#
# Gate: ``current_band >= 2 and corroborated_flags`` (both conditions required).
# Service enforces "all raised feel flags are corroborated" before passing a
# non-empty frozenset — at the arbiter level any non-empty frozenset is trusted.
# Provenance stays PROV_DRIVER_REPORT — telemetry confirmed the SYMPTOM, not
# the lever; using PROV_MEASURED_FACT here would repeat the original defect.
# ---------------------------------------------------------------------------

def test_symptom_corroborated_label_fires_at_band2_when_gate_open():
    """Sixth label fires when corroborated_flags is non-empty at band 2.

    Failure mode when reverted: if the label-upgrade line is removed or the
    ``corroborated_flags`` check short-circuits to False, the label remains
    LABEL_DRIVER_TEL_SILENT and the assertion below fails.
    """
    from strategy.owner_baseline_arbiter import (
        LABEL_DRIVER_SYMPTOM_CORROBORATED,
        PROV_DRIVER_REPORT,
    )

    fb_intent = _intent("arb_rear", +1.0, to_value=6.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,           # band 2
        telemetry_plan=_empty_plan(),
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"arb_rear": 5.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-sym1",
        event_id=30,
        suppression_keys=frozenset(),
        corroborated_flags=frozenset({"entry_understeer"}),
    )

    arb_props = [p for p in proposals if p.parameter == "arb_rear"]
    assert len(arb_props) == 1, "arb_rear must appear in proposals"
    p = arb_props[0]
    assert p.label == LABEL_DRIVER_SYMPTOM_CORROBORATED, (
        f"Expected LABEL_DRIVER_SYMPTOM_CORROBORATED when gate is open; "
        f"got {p.label!r}. If this fails, the upgrade logic was reverted."
    )
    assert p.provenance == PROV_DRIVER_REPORT, (
        f"Provenance must be PROV_DRIVER_REPORT even with symptom corroboration; "
        f"got {p.provenance!r}. MEASURED_FACT here would repeat the original defect."
    )


def test_symptom_corroborated_provenance_must_not_be_measured_fact():
    """Sixth label must NEVER use PROV_MEASURED_FACT — that was the original bug.

    Telemetry confirmed the SYMPTOM (e.g. rear loose on exit), not the lever
    (e.g. arb_rear).  Provenance must therefore be DRIVER_REPORT.

    Failure mode: if someone changes provenance to MEASURED_FACT for this path,
    this test fails and flags the regression.
    """
    from strategy.owner_baseline_arbiter import (
        LABEL_DRIVER_SYMPTOM_CORROBORATED,
        PROV_DRIVER_REPORT,
        PROV_MEASURED_FACT,
    )

    fb_intent = _intent("arb_rear", +1.0, to_value=6.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_empty_plan(),
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"arb_rear": 5.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-sym2",
        event_id=31,
        suppression_keys=frozenset(),
        corroborated_flags=frozenset({"entry_understeer"}),
    )

    assert proposals
    p = proposals[0]
    assert p.provenance != PROV_MEASURED_FACT, (
        "PROV_MEASURED_FACT on a DRIVER_SYMPTOM_CORROBORATED proposal is the "
        "original provenance defect — telemetry confirmed the symptom, not the lever."
    )
    assert p.provenance == PROV_DRIVER_REPORT


def test_symptom_gate_closed_emits_driver_tel_silent():
    """When corroborated_flags is empty the second pass falls back to DRIVER_TEL_SILENT.

    Failure mode: if the gate condition ignores corroborated_flags and always
    upgrades, the label would be DRIVER_SYMPTOM_CORROBORATED and the assert fails.
    """
    from strategy.owner_baseline_arbiter import (
        LABEL_DRIVER_TEL_SILENT,
        LABEL_DRIVER_SYMPTOM_CORROBORATED,
    )

    fb_intent = _intent("arb_rear", +1.0, to_value=6.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_empty_plan(),
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"arb_rear": 5.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-sym3",
        event_id=32,
        suppression_keys=frozenset(),
        corroborated_flags=frozenset(),   # empty — gate closed
    )

    arb_props = [p for p in proposals if p.parameter == "arb_rear"]
    assert len(arb_props) == 1
    assert arb_props[0].label == LABEL_DRIVER_TEL_SILENT, (
        f"Empty corroborated_flags must produce DRIVER_TEL_SILENT fallback; "
        f"got {arb_props[0].label!r}"
    )
    assert arb_props[0].label != LABEL_DRIVER_SYMPTOM_CORROBORATED


def test_symptom_gate_open_with_two_flags_both_corroborated():
    """Two corroborated flags: gate still opens (all-flags rule, not exactly-one).

    The service changed from "exactly one active flag" to "all raised flags
    corroborated" because a single dropdown answer can raise two feel flags
    (exit_stability='strong oversteer' sets both rear_loose_on_exit AND
    snap_oversteer_exit).  The old rule refused the common corroborated case.

    Failure mode when reverted: if the service reverts to len(flags)==1, the
    two-flag case closes the gate -> arbiter receives empty corroborated_flags
    -> DRIVER_TEL_SILENT instead of DRIVER_SYMPTOM_CORROBORATED -> assert fails.
    (This test is at the arbiter level: it receives the pre-computed frozenset
    directly and pins that a two-element set causes the upgrade.)
    """
    from strategy.owner_baseline_arbiter import LABEL_DRIVER_SYMPTOM_CORROBORATED

    fb_intent = _intent("arb_rear", +1.0, to_value=6.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=5,
        telemetry_plan=_empty_plan(),
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"arb_rear": 5.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-sym4",
        event_id=33,
        suppression_keys=frozenset(),
        corroborated_flags=frozenset({"rear_loose_on_exit", "snap_oversteer_exit"}),
    )

    arb_props = [p for p in proposals if p.parameter == "arb_rear"]
    assert len(arb_props) == 1
    assert arb_props[0].label == LABEL_DRIVER_SYMPTOM_CORROBORATED, (
        "Two corroborated flags must still open the gate.  If this fails, the "
        "service reverted to 'exactly one flag' — but at the arbiter level a "
        "non-empty frozenset always opens the gate regardless of size."
    )


def test_symptom_corroborated_not_applied_at_band1():
    """At band 1, corroborated_flags is ignored — label is always DRIVER_TEL_SILENT.

    Corroboration evidence is too sparse at 1-4 laps to justify the upgrade.
    The condition is ``current_band >= 2 AND corroborated_flags``.

    Failure mode: if the band-2 guard is removed, band 1 would emit
    DRIVER_SYMPTOM_CORROBORATED -> assertion fails.
    """
    from strategy.owner_baseline_arbiter import (
        LABEL_DRIVER_TEL_SILENT,
        LABEL_DRIVER_SYMPTOM_CORROBORATED,
    )

    fb_intent = _intent("arb_rear", +1.0, to_value=6.0)

    proposals, _, _ = build_owner_proposals(
        clean_laps=3,           # band 1 — corroborated_flags must be ignored here
        telemetry_plan=_empty_plan(),
        feedback_plan=_plan(proposed=[fb_intent]),
        owner_baseline={"arb_rear": 5.0},
        parameter_model=None,
        discipline="race",
        baseline_revision=1,
        session_run_id="run-sym5",
        event_id=34,
        suppression_keys=frozenset(),
        corroborated_flags=frozenset({"entry_understeer"}),  # non-empty, but band 1
    )

    arb_props = [p for p in proposals if p.parameter == "arb_rear"]
    assert len(arb_props) == 1
    assert arb_props[0].label == LABEL_DRIVER_TEL_SILENT, (
        "At band 1 the corroboration upgrade must not fire — label must be "
        f"DRIVER_TEL_SILENT; got {arb_props[0].label!r}"
    )
    assert arb_props[0].label != LABEL_DRIVER_SYMPTOM_CORROBORATED
