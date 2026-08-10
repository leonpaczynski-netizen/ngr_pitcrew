"""Owner-baseline proposal arbiter (pure, Qt-free, DB-free) — never raises.

The ONLY live arbiter for events that have an owner-authored baseline. After each
recorded practice session, ``build_owner_proposals`` evaluates driver feedback and
telemetry against the owner baseline for one discipline and returns three lists:

  proposals        — parameter changes to present to the driver (advisory only;
                     nothing is applied without an explicit Accept).
  suppressed       — changes the rule engine would have proposed but could not
                     (ratchet-locked, protected, contraindicated). Listed so the
                     driver can see what was considered and why it was withheld.
  unresolved_riders — feedback signals present at 5+ laps for parameters where
                     telemetry is silent. Never discarded; must be explicitly resolved.

Band logic (owner decision R5 — three hard bands, no continuous float):
  ``clean_laps == 0``                  → feedback alone; label LABEL_DRIVER_ONLY.
  ``1 <= clean_laps < 5``              → both sources noted; label LABEL_DRIVER_EARLY_TEL.
  ``clean_laps >= 5``, feedback absent → label LABEL_TEL_NO_FEEDBACK.
  ``clean_laps >= 5``, feedback agrees → label LABEL_TEL_CORROBORATED.
  ``clean_laps >= 5``, feedback opposes → UNRESOLVED; NEITHER direction suppressed,
                                          NEITHER averaged; must be resolved before
                                          accept/reject.

Clip rule (B15): proposed values are passed through ``ParameterSpec.snap()``; if
the snapped value differs from the raw rule-engine value the difference is noted
in ``clip_stated_reason`` and ``clipped=True``.  The proposal is NEVER dropped.

Suppressed changes (B16): the rule engine's ``rejected_candidates`` list already
carries ratchet-locked / contraindicated / protected entries (``_record_suppression``
in ``setup_rule_engine.py``).  This module surfaces them — it adds no new suppression
logic of its own.

Pure: no Qt, no DB, no network, no AI, no wall-clock, no randomness.  Never raises.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Named thresholds (owner decision R5 — hard bands, no continuous float)
# ---------------------------------------------------------------------------

#: Sessions with this many or more clean laps are telemetry-primary.
#: Mirrors ``data.session_db.MIN_EVIDENCE_CLEAN_LAPS`` exactly.
TELEMETRY_PRIMARY_THRESHOLD: int = 5

#: At least one clean lap is required before any telemetry signal is noted.
EARLY_TELEMETRY_THRESHOLD: int = 1

# ---------------------------------------------------------------------------
# Canonical label strings (B8-B11).  The external export embeds these verbatim
# so an LLM consumer can pattern-match without needing the code.
# ---------------------------------------------------------------------------
LABEL_DRIVER_ONLY: str = "driver report only — no telemetry"
LABEL_DRIVER_EARLY_TEL: str = "driver report with early telemetry"
LABEL_TEL_CORROBORATED: str = "telemetry with driver corroboration"
LABEL_TEL_NO_FEEDBACK: str = "telemetry (driver feedback absent or silent)"

# Internal marker for contradicted proposals (B11) — NOT one of the four labels;
# these go into a separate UNRESOLVED bucket with ``status="unresolved"``.
_STATUS_UNRESOLVED: str = "unresolved"
_STATUS_PROPOSED: str = "proposed"

# ---------------------------------------------------------------------------
# Provenance tags (carried on every proposal for the export / external Claude)
# ---------------------------------------------------------------------------
PROV_MEASURED_FACT: str = "MEASURED_FACT"
PROV_DETERMINISTIC_INFERENCE: str = "DETERMINISTIC_INFERENCE"
PROV_DRIVER_REPORT: str = "DRIVER_REPORT"
PROV_UNRESOLVED: str = "UNRESOLVED"


# ---------------------------------------------------------------------------
# Band helper — deterministic, no arithmetic
# ---------------------------------------------------------------------------

def _band(clean_laps: int) -> int:
    """Map a lap count to a 0/1/2 band integer.

    0  → feedback only (no telemetry).
    1  → early telemetry (1-4 clean laps).
    2  → telemetry primary (5+ clean laps).

    Named bands are used for B14 suppression checks: re-raising a rejected
    proposal is allowed only when the evidence has crossed a band boundary
    (``EARLY_TELEMETRY_THRESHOLD`` or ``TELEMETRY_PRIMARY_THRESHOLD``).
    """
    if clean_laps <= 0:
        return 0
    if clean_laps < TELEMETRY_PRIMARY_THRESHOLD:
        return 1
    return 2


# ---------------------------------------------------------------------------
# Direction helper
# ---------------------------------------------------------------------------

def _direction(delta: float) -> str:
    """Return "increase" or "decrease".  Zero delta → "increase" (defensive)."""
    try:
        return "decrease" if float(delta) < 0 else "increase"
    except (TypeError, ValueError):
        return "increase"


# ---------------------------------------------------------------------------
# Clip helper (B15)
# ---------------------------------------------------------------------------

def _clip_to_spec(field: str, raw_value: float, parameter_model) -> Tuple[float, bool, str]:
    """Apply ParameterSpec.snap() and report any clip.

    Returns ``(snapped_value, clipped, reason)``.  ``clipped`` is True when the
    snapped value differs materially from ``raw_value``.  The proposal is never
    dropped (B15 deliberate asymmetry vs A6).

    ``parameter_model`` may be None (e.g. unknown car) — in that case the raw
    value is returned unmodified.
    """
    try:
        if parameter_model is None:
            return raw_value, False, ""
        spec = parameter_model.spec(field) if hasattr(parameter_model, "spec") else None
        if spec is None:
            return raw_value, False, ""
        snapped = spec.snap(raw_value)
        if abs(snapped - raw_value) > 1e-9:
            reason = (
                f"raw computed value {raw_value:.4g} snapped to nearest legal "
                f"grid position {snapped:.4g} "
                f"(step={spec.step:.4g}, legal=[{spec.legal_low:.4g},{spec.legal_high:.4g}])"
            )
            return snapped, True, reason
        return snapped, False, ""
    except Exception:
        return raw_value, False, ""


# ---------------------------------------------------------------------------
# Public return types
# ---------------------------------------------------------------------------

@dataclass
class OwnerProposal:
    """One proposed parameter change for the driver to accept, reject or edit.

    The external-export schema keys are intentionally identical to the field
    names here so ``as_dict()`` round-trips without a mapping table.
    """
    proposal_id: str              # uuid — stable across DB round-trips
    event_id: int
    session_run_id: str
    discipline: str
    parameter: str                # canonical field name ("camber_front", etc.)
    direction: str                # "increase" | "decrease"
    proposed_value: float         # clipped / snapped if needed
    original_value: float         # owner baseline value at time of proposal
    clipped: bool
    clip_stated_reason: str       # non-empty when clipped==True
    label: str                    # one of LABEL_* or "" for unresolved
    status: str                   # "proposed" | "unresolved"
    original_proposed_value: float  # raw value before clip; preserved when EDITED
    evidence_sources: List[str]   # free-text from rule engine rationale/symptom
    baseline_revision: int
    provenance: str               # PROV_* constant
    clean_laps: int               # laps in the originating session (for B14)

    def as_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "event_id": self.event_id,
            "session_run_id": self.session_run_id,
            "discipline": self.discipline,
            "parameter": self.parameter,
            "direction": self.direction,
            "proposed_value": self.proposed_value,
            "original_value": self.original_value,
            "clipped": self.clipped,
            "clip_stated_reason": self.clip_stated_reason,
            "label": self.label,
            "status": self.status,
            "original_proposed_value": self.original_proposed_value,
            "evidence_sources": list(self.evidence_sources),
            "baseline_revision": self.baseline_revision,
            "provenance": self.provenance,
            "clean_laps": self.clean_laps,
        }


@dataclass
class UnresolvedRider:
    """Feedback present for a parameter that telemetry is SILENT on (B9/Correction 2).

    Never discarded. Carried through to the export and the UI so the driver can
    acknowledge or dismiss it explicitly.
    """
    parameter: str
    feedback_direction: str       # "increase" | "decrease" (from the feedback plan)
    discipline: str
    session_run_id: str
    baseline_revision: int
    note: str                     # human-readable explanation (e.g. rule rationale)
    evidence_sources: List[str]
    event_id: int

    def as_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "feedback_direction": self.feedback_direction,
            "discipline": self.discipline,
            "session_run_id": self.session_run_id,
            "baseline_revision": self.baseline_revision,
            "note": self.note,
            "evidence_sources": list(self.evidence_sources),
            "event_id": self.event_id,
        }


@dataclass
class SuppressedChange:
    """A change the rule engine evaluated but could not propose (B16).

    Ratchet-locked, protected-field, contraindicated or movement-capped entries
    in ``SetupPlan.rejected_candidates`` are surfaced here verbatim — no new
    suppression logic is added.
    """
    parameter: str
    reason: str                  # rationale text from the rule engine
    ratchet_locked: bool         # True when the movement cap / lockout blocked it
    feedback_recorded: bool      # True when the feedback plan ALSO proposed this field

    def as_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "reason": self.reason,
            "ratchet_locked": self.ratchet_locked,
            "feedback_recorded": self.feedback_recorded,
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_owner_proposals(
    *,
    clean_laps: int,
    telemetry_plan,            # SetupPlan — from run_rule_engine with full diagnosis
    feedback_plan,             # SetupPlan — from run_rule_engine with feedback-only diagnosis
    owner_baseline: dict,
    parameter_model=None,      # CarParameterModel or None
    discipline: str,
    baseline_revision: int,
    session_run_id: str,
    event_id: int,
    suppression_keys: FrozenSet[str] = frozenset(),
) -> Tuple[List[OwnerProposal], List[SuppressedChange], List[UnresolvedRider]]:
    """Build proposals, suppressed changes and unresolved riders for one session.

    Parameters
    ----------
    clean_laps
        Number of clean (non-out, non-pit, non-spin) laps in this session.
        Used to determine the evidence band (R5 — three hard bands).
    telemetry_plan
        ``SetupPlan`` from ``run_rule_engine`` called with the FULL diagnosis
        (real laps + feedback) and the OWNER BASELINE as ``setup=``.  At
        ``clean_laps == 0`` this and ``feedback_plan`` are identical (both built
        from feedback-only diagnosis).
    feedback_plan
        ``SetupPlan`` from ``run_rule_engine`` called with a feedback-ONLY
        diagnosis (``laps=[]``) and the same owner baseline.  Represents what
        driver feedback alone implies.
    owner_baseline
        The current owner-entered setup values ``{field: value}``.
    parameter_model
        ``CarParameterModel`` for snap/clip (B15), or ``None`` when unknown.
    discipline
        "race" or "qualifying".
    baseline_revision
        Current revision counter for the owner baseline (A5).
    session_run_id
        UUID of the session run that generated this evidence.
    event_id
        Integer event id.
    suppression_keys
        A frozenset of ``observation_key(parameter + ":" + direction, discipline)``
        strings that were previously REJECTED in this event, paired with their
        band.  Passed as ``frozenset({(obs_key, band_int), ...})``.  A rejected
        proposal at the same band is suppressed; crossing a band boundary allows
        re-raise (B14 "materially different evidence").

    Returns
    -------
    (proposals, suppressed, unresolved_riders) — all lists, never None.
    Never raises.
    """
    try:
        return _build_proposals_inner(
            clean_laps=clean_laps,
            telemetry_plan=telemetry_plan,
            feedback_plan=feedback_plan,
            owner_baseline=owner_baseline,
            parameter_model=parameter_model,
            discipline=str(discipline or ""),
            baseline_revision=int(baseline_revision or 0),
            session_run_id=str(session_run_id or ""),
            event_id=int(event_id or 0),
            suppression_keys=suppression_keys or frozenset(),
        )
    except Exception:
        return [], [], []


def _build_proposals_inner(
    *,
    clean_laps: int,
    telemetry_plan,
    feedback_plan,
    owner_baseline: dict,
    parameter_model,
    discipline: str,
    baseline_revision: int,
    session_run_id: str,
    event_id: int,
    suppression_keys: FrozenSet,
) -> Tuple[List[OwnerProposal], List[SuppressedChange], List[UnresolvedRider]]:
    """Inner implementation — may raise; always wrapped by build_owner_proposals."""
    try:
        from strategy.learning_proposal import observation_key as _obs_key
    except Exception:
        def _obs_key(obs: str, scope: str = "") -> str:  # type: ignore[misc]
            return f"{obs}|{scope}".lower().strip()

    current_band = _band(clean_laps)

    # Build per-field direction maps from each plan.
    # Only the first proposal per field is kept (highest-confidence rule wins
    # inside the rule engine already).
    tel_dirs: Dict[str, Tuple[str, object]] = {}   # field -> (direction, intent)
    fb_dirs: Dict[str, Tuple[str, object]] = {}    # field -> (direction, intent)

    for intent in (getattr(telemetry_plan, "proposed", None) or []):
        f = getattr(intent, "field", None)
        if f and f not in tel_dirs:
            tel_dirs[f] = (_direction(getattr(intent, "delta", 0)), intent)

    for intent in (getattr(feedback_plan, "proposed", None) or []):
        f = getattr(intent, "field", None)
        if f and f not in fb_dirs:
            fb_dirs[f] = (_direction(getattr(intent, "delta", 0)), intent)

    # Suppressed set: {(obs_key, band)} pairs that block re-raise at the same band.
    # Format accepted: frozenset of 2-tuples.
    _rejected_pairs: set = set()
    for item in suppression_keys:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            _rejected_pairs.add((str(item[0]), int(item[1])))

    def _is_suppressed(param: str, direction: str) -> bool:
        key = _obs_key(f"{param}:{direction}", discipline)
        return any(k == key and b == current_band for k, b in _rejected_pairs)

    proposals: List[OwnerProposal] = []
    suppressed: List[SuppressedChange] = []
    unresolved_riders: List[UnresolvedRider] = []

    # ----------------------------------------------------------------
    # Determine the SOURCE intents based on band logic (R5, hard bands)
    # ----------------------------------------------------------------
    if current_band == 0:
        # B8: zero clean laps — feedback alone; no telemetry signal implied.
        source_items = list(fb_dirs.items())
        default_label = LABEL_DRIVER_ONLY
        default_prov = PROV_DRIVER_REPORT
    elif current_band == 1:
        # B10: 1-4 laps — both sources noted; feedback is primary carrier of direction.
        # Use the TELEMETRY plan (which already merged feedback into the diagnosis).
        source_items = list(tel_dirs.items())
        default_label = LABEL_DRIVER_EARLY_TEL
        default_prov = PROV_DETERMINISTIC_INFERENCE
    else:
        # B9: 5+ laps — telemetry primary.
        source_items = list(tel_dirs.items())
        default_label = ""   # determined per-proposal below
        default_prov = PROV_MEASURED_FACT

    for field_name, (tel_dir, intent) in source_items:
        try:
            # ---- Clip proposed value (B15) ----
            raw_to = getattr(intent, "to_value", None)
            if raw_to is None:
                continue
            try:
                raw_float = float(raw_to)
            except (TypeError, ValueError):
                continue
            original_val = float(owner_baseline.get(field_name, 0.0) or 0.0)
            snapped, clipped, clip_reason = _clip_to_spec(field_name, raw_float, parameter_model)

            # ---- Band-specific label + provenance ----
            if current_band == 0:
                label = LABEL_DRIVER_ONLY
                prov = PROV_DRIVER_REPORT
                status = _STATUS_PROPOSED
            elif current_band == 1:
                label = LABEL_DRIVER_EARLY_TEL
                prov = PROV_DETERMINISTIC_INFERENCE
                status = _STATUS_PROPOSED
            else:
                # 5+ laps: check feedback agreement (B9)
                fb_entry = fb_dirs.get(field_name)
                if fb_entry is None:
                    # Telemetry proposed, feedback silent → TEL_NO_FEEDBACK
                    label = LABEL_TEL_NO_FEEDBACK
                    prov = PROV_MEASURED_FACT
                    status = _STATUS_PROPOSED
                elif fb_entry[0] == tel_dir:
                    # Telemetry AND feedback agree → CORROBORATED
                    label = LABEL_TEL_CORROBORATED
                    prov = PROV_MEASURED_FACT
                    status = _STATUS_PROPOSED
                else:
                    # B11: feedback OPPOSES telemetry → UNRESOLVED, no label, no average
                    label = ""
                    prov = PROV_UNRESOLVED
                    status = _STATUS_UNRESOLVED

            # ---- B14: suppression check ----
            if _is_suppressed(field_name, tel_dir) and status != _STATUS_UNRESOLVED:
                # Previously rejected at the same band — do not re-raise.
                continue

            # ---- Evidence sources ----
            evidence: List[str] = []
            rationale = str(getattr(intent, "rationale", "") or "")
            symptom = str(getattr(intent, "symptom", "") or "")
            rule_id = str(getattr(intent, "rule_id", "") or "")
            if symptom:
                evidence.append(symptom)
            if rationale and rationale != symptom:
                evidence.append(rationale)
            if rule_id:
                evidence.append(f"rule:{rule_id}")

            proposals.append(OwnerProposal(
                proposal_id=str(uuid.uuid4()),
                event_id=event_id,
                session_run_id=session_run_id,
                discipline=discipline,
                parameter=field_name,
                direction=tel_dir,
                proposed_value=snapped,
                original_value=original_val,
                clipped=clipped,
                clip_stated_reason=clip_reason,
                label=label,
                status=status,
                original_proposed_value=raw_float,
                evidence_sources=evidence,
                baseline_revision=baseline_revision,
                provenance=prov,
                clean_laps=clean_laps,
            ))
        except Exception:
            continue  # never raise; degrade silently per-proposal

    # ----------------------------------------------------------------
    # Unresolved riders (B9/Correction 2): feedback at 5+ laps for
    # parameters telemetry is SILENT on.
    # ----------------------------------------------------------------
    if current_band >= 2:
        tel_fields = set(tel_dirs)
        for field_name, (fb_dir, fb_intent) in fb_dirs.items():
            if field_name in tel_fields:
                continue   # telemetry addressed it → handled above
            try:
                note = str(getattr(fb_intent, "symptom", "") or "")
                rationale = str(getattr(fb_intent, "rationale", "") or "")
                rule_id = str(getattr(fb_intent, "rule_id", "") or "")
                evidence: List[str] = [s for s in (note, rationale) if s]
                if rule_id:
                    evidence.append(f"rule:{rule_id}")
                unresolved_riders.append(UnresolvedRider(
                    parameter=field_name,
                    feedback_direction=fb_dir,
                    discipline=discipline,
                    session_run_id=session_run_id,
                    baseline_revision=baseline_revision,
                    note=(
                        f"Feedback implies {fb_dir} {field_name} but telemetry "
                        f"produced no finding for this parameter at "
                        f"{clean_laps} clean laps. Never discarded."
                    ),
                    evidence_sources=evidence,
                    event_id=event_id,
                ))
            except Exception:
                continue

    # ----------------------------------------------------------------
    # Suppressed changes (B16): surface what the rule engine withheld.
    # ----------------------------------------------------------------
    # The feedback_plan's rejected set is also useful for determining
    # feedback_recorded on each suppressed entry.
    fb_rejected_fields = {
        getattr(i, "field", "") for i in (getattr(feedback_plan, "rejected_candidates", None) or [])
    }
    fb_proposed_fields = set(fb_dirs)

    for intent in (getattr(telemetry_plan, "rejected_candidates", None) or []):
        try:
            rationale = str(getattr(intent, "rationale", "") or "")
            if "SUPPRESSED" not in rationale:
                continue
            f = str(getattr(intent, "field", "") or "")
            if not f:
                continue
            ratchet = any(kw in rationale.lower() for kw in
                          ("ratchet", "movement cap", "already at the limit",
                           "locked out", "lockout", "closed-loop"))
            feedback_rec = f in fb_proposed_fields or f in fb_rejected_fields
            suppressed.append(SuppressedChange(
                parameter=f,
                reason=rationale,
                ratchet_locked=ratchet,
                feedback_recorded=feedback_rec,
            ))
        except Exception:
            continue

    return proposals, suppressed, unresolved_riders
