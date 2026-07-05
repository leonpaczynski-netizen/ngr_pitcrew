"""Setup rule engine — Group 42: Rule-First Setup Brain.

Evaluates the rule catalogue against a diagnosis dict and produces a SetupPlan
of proposed and rejected candidates.

Public API
----------
run_rule_engine(diagnosis, setup, ranges, profile, allowed_tuning, rule_outcome_store)
    -> SetupPlan

RuleOutcomeStore  — in-memory outcome tracking for confidence-downgrade gate.
SetupChangeIntent — single proposed or rejected change with full explainability.
SetupPlan         — result container.

Design notes
------------
- NEVER raises — wraps everything in try/except returning an empty SetupPlan.
- Pack A rules create protected_fields / rejected_candidates; never proposed.
- Pack B rules use DriverProfile to set driver_style_alignment.
- Delta resolvers are looked up by name from setup_knowledge_base._DELTA_RESOLVERS.
- Confidence is downgraded one step (high→med→low) when the RuleOutcomeStore
  reports success_rate < LOW_SUCCESS_RATE with sufficient samples (AC21).
- Conflicting candidates (same field, opposite deltas): keep higher confidence;
  both go to rejected_candidates with reason "conflict:<other_rule_id>".
- No-op changes (delta==0 or clamped to_value==from_value) are excluded.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

from strategy._setup_constants import MIN_OUTCOME_SAMPLES, LOW_SUCCESS_RATE
from strategy.setup_knowledge_base import (
    ConfidenceLevel,
    RiskLevel,
    RulePhase,
    SetupRule,
    get_all_rules,
    resolve_delta,
)
from strategy.setup_driver_profile import DriverProfile, DriverStyleAlignment

log = logging.getLogger(__name__)

# Canonical gearbox fields (for gear-count gating)
_GEAR_FIELDS = ("gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6")
_REAL_GEARBOX_FIELDS = frozenset({"final_drive"} | set(_GEAR_FIELDS))


# ---------------------------------------------------------------------------
# Confidence downgrade helper
# ---------------------------------------------------------------------------

def _downgrade_confidence(c: ConfidenceLevel) -> ConfidenceLevel:
    if c == ConfidenceLevel.high:
        return ConfidenceLevel.med
    return ConfidenceLevel.low


# ---------------------------------------------------------------------------
# NamedTuples
# ---------------------------------------------------------------------------

class SetupChangeIntent(NamedTuple):
    """A single proposed or rejected setup change with full explainability."""
    field: str
    delta: float
    from_value: object          # float or None
    to_value: object            # float or None
    symptom: str
    evidence: list              # list[str] — telemetry / feel keys that fired
    rule_id: str
    rationale: str
    rejected_alternatives: list  # list[str] — alternative rule_ids considered
    risk: RiskLevel
    confidence: ConfidenceLevel
    driver_style_alignment: DriverStyleAlignment


class SetupPlan(NamedTuple):
    """Result of the rule engine evaluation."""
    proposed: list               # list[SetupChangeIntent]
    rejected_candidates: list    # list[SetupChangeIntent] with .rationale carrying reason
    protected_fields: list       # list[str]


# ---------------------------------------------------------------------------
# RuleOutcomeStore
# ---------------------------------------------------------------------------

class RuleOutcomeStore:
    """In-memory outcome store for rule success-rate confidence-downgrade gate.

    Keyed by (rule_id, car, track, driver_profile_version).
    JSON-serialisable internal dict — no DB this sprint.

    Deferred: live wiring into build_combined_setup_response and persistence
    of RuleOutcomeStore across calls/sessions is deferred to a future sprint.
    A fresh empty store has no samples so the confidence-downgrade hook (AC21)
    would never fire anyway — the hook is implemented and unit-tested in
    isolation, ready to activate once persistence is in place.
    """

    def __init__(self) -> None:
        # {(rule_id, car, track, profile_version): {"fire_count": int, "success_count": int}}
        self._store: dict = {}

    def _key(self, rule_id: str, car: str, track: str, profile_version: str) -> tuple:
        return (rule_id, car, track, profile_version)

    def record_fire(
        self,
        rule_id: str,
        car: str = "",
        track: str = "",
        profile_version: str = "",
    ) -> None:
        k = self._key(rule_id, car, track, profile_version)
        entry = self._store.setdefault(k, {"fire_count": 0, "success_count": 0})
        entry["fire_count"] += 1

    def record_success(
        self,
        rule_id: str,
        car: str = "",
        track: str = "",
        profile_version: str = "",
    ) -> None:
        k = self._key(rule_id, car, track, profile_version)
        entry = self._store.setdefault(k, {"fire_count": 0, "success_count": 0})
        entry["success_count"] += 1

    def fire_count(
        self,
        rule_id: str,
        car: str = "",
        track: str = "",
        profile_version: str = "",
    ) -> int:
        k = self._key(rule_id, car, track, profile_version)
        return self._store.get(k, {}).get("fire_count", 0)

    def get_success_rate(
        self,
        rule_id: str,
        car: str = "",
        track: str = "",
        profile_version: str = "",
    ) -> "float | None":
        """Return success_rate, or None when fewer than MIN_OUTCOME_SAMPLES fires."""
        k = self._key(rule_id, car, track, profile_version)
        entry = self._store.get(k)
        if entry is None:
            return None
        fc = entry.get("fire_count", 0)
        if fc < MIN_OUTCOME_SAMPLES:
            return None
        sc = entry.get("success_count", 0)
        return sc / fc

    def to_dict(self) -> dict:
        """Return a JSON-serialisable copy of the internal store."""
        return {str(k): v for k, v in self._store.items()}


# ---------------------------------------------------------------------------
# Precondition / contraindication evaluator
# ---------------------------------------------------------------------------

def _get_nested(diagnosis: dict, key: str):
    """Resolve dotted key paths like 'driver_feel_flags.floaty_front'."""
    parts = key.split(".")
    obj = diagnosis
    for part in parts:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _matches_value(actual, expected) -> bool:
    """Check whether *actual* matches the *expected* precondition specification.

    Special expected values
    -----------------------
    "__not_low__"             — actual != "low"
    "__gt_zero__"             — actual is numeric and > 0
    "__is_traction__"         — actual not in {"snap_throttle_induced", "insufficient_data"}
    "__NOT_high_speed_instability__"  — actual != "high_speed_instability"
    "__contains_understeer__" — "understeer" in str(actual)
    "__in_consider_required__" — actual in {"consider", "required"}
    True / False              — truthiness check
    string                    — exact equality
    """
    if expected == "__not_low__":
        return actual != "low"
    if expected == "__gt_zero__":
        try:
            return float(actual) > 0
        except (TypeError, ValueError):
            return False
    if expected == "__is_traction__":
        return actual not in {"snap_throttle_induced", "insufficient_data"}
    if expected == "__NOT_high_speed_instability__":
        return actual != "high_speed_instability"
    if expected == "__contains_understeer__":
        return "understeer" in str(actual).lower()
    if expected == "__in_consider_required__":
        return actual in {"consider", "required"}
    if isinstance(expected, bool):
        return bool(actual) == expected
    return actual == expected


def _eval_preconditions(preconditions: dict, diagnosis: dict) -> bool:
    """Return True if ALL preconditions match the diagnosis.

    Special key "__any__" accepts a list of diagnosis keys whose presence/truth
    means ANY one of them is sufficient to satisfy the check.
    """
    for key, expected in preconditions.items():
        if key == "__any__":
            # expected is a list of evidence-key names; pass if ANY is truthy
            if not isinstance(expected, list):
                return False
            if not any(_get_nested(diagnosis, ek) for ek in expected):
                return False
        else:
            actual = _get_nested(diagnosis, key)
            if not _matches_value(actual, expected):
                return False
    return True


def _eval_contraindications(contraindications: dict, diagnosis: dict) -> bool:
    """Return True if ANY contraindication matches (blocking the rule from firing)."""
    for key, expected in contraindications.items():
        if key == "__any__":
            if not isinstance(expected, list):
                continue
            if any(_get_nested(diagnosis, ek) for ek in expected):
                return True  # blocked
        else:
            actual = _get_nested(diagnosis, key)
            if _matches_value(actual, expected):
                return True  # blocked
    return False


# ---------------------------------------------------------------------------
# Driver-style alignment
# ---------------------------------------------------------------------------

def _compute_driver_style_alignment(
    rule: SetupRule, profile: DriverProfile
) -> DriverStyleAlignment:
    """Return alignment based on driver style tags overlap."""
    if not rule.driver_style_tags:
        return DriverStyleAlignment.neutral
    overlap = [t for t in rule.driver_style_tags if t in profile.style_tags]
    if len(overlap) == len(rule.driver_style_tags):
        return DriverStyleAlignment.aligned
    if overlap:
        return DriverStyleAlignment.neutral
    # Check for explicit caution signals
    if "dislikes_snap_exit" in rule.driver_style_tags and profile.dislikes_snap_exit:
        return DriverStyleAlignment.aligned
    if "dislikes_floaty_front" in rule.driver_style_tags and profile.dislikes_floaty_front:
        return DriverStyleAlignment.aligned
    return DriverStyleAlignment.caution


# ---------------------------------------------------------------------------
# Gear count gating
# ---------------------------------------------------------------------------

def _max_gear_from_setup(setup: dict) -> int:
    """Return the highest gear index present in the setup (1-based), or 6."""
    for i in range(6, 0, -1):
        if f"gear_{i}" in setup and setup[f"gear_{i}"] is not None:
            try:
                float(setup[f"gear_{i}"])
                return i
            except (TypeError, ValueError):
                continue
    return 6


def _gear_index(field: str) -> int:
    """Return the gear index (1-6) for a gear_N field, or 0 for non-gear fields."""
    if field.startswith("gear_"):
        try:
            return int(field[5:])
        except ValueError:
            pass
    return 0


# ---------------------------------------------------------------------------
# Pack A special handling
# ---------------------------------------------------------------------------

_PACK_A_FIELD_PROTECTED_UNCONDITIONALLY = frozenset({
    "transmission_max_speed_kmh",  # A6 — display-only always
})

_PACK_A_VIRTUAL_FIELDS = frozenset({
    "__gearbox_fake__",  # A7
    "__gear_inversion__",  # A8
})

# Pack A rule_ids that unconditionally protect their field
_PACK_A_UNCONDITIONAL_PROTECT = {"A6"}

# Pack A rule_ids that only protect when preconditions match
_PACK_A_CONDITIONAL_PROTECT = {"A3", "A4"}


def _is_pack_a_rule(rule: SetupRule) -> bool:
    return rule.pack == "A"


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def run_rule_engine(
    diagnosis: dict,
    setup: dict,
    ranges: dict,
    profile: DriverProfile,
    allowed_tuning: "list[str] | None" = None,
    rule_outcome_store: "RuleOutcomeStore | None" = None,
) -> SetupPlan:
    """Evaluate all registered rules against diagnosis and return a SetupPlan.

    Parameters
    ----------
    diagnosis     : Output of build_setup_diagnosis.
    setup         : Current car setup dict (canonical keys).
    ranges        : Resolved per-car ranges from resolve_ranges().
    profile       : DriverProfile from build_driver_profile().
    allowed_tuning: Optional list of allowed tuning categories; None = no restriction.
    rule_outcome_store: Optional outcome store for AC21 confidence downgrade.

    Returns
    -------
    SetupPlan with proposed / rejected_candidates / protected_fields.
    Never raises — returns empty SetupPlan on any error.
    """
    try:
        return _run_rule_engine_inner(
            diagnosis, setup, ranges, profile, allowed_tuning, rule_outcome_store
        )
    except Exception as exc:
        log.warning("run_rule_engine failed: %s", exc, exc_info=True)
        return SetupPlan(proposed=[], rejected_candidates=[], protected_fields=[])


def _run_rule_engine_inner(
    diagnosis: dict,
    setup: dict,
    ranges: dict,
    profile: DriverProfile,
    allowed_tuning: "list[str] | None",
    rule_outcome_store: "RuleOutcomeStore | None",
) -> SetupPlan:
    proposed: list[SetupChangeIntent] = []
    rejected: list[SetupChangeIntent] = []
    protected_fields: list[str] = []

    # Fields protected unconditionally (Pack A A6 etc.)
    for uf in _PACK_A_FIELD_PROTECTED_UNCONDITIONALLY:
        if uf not in protected_fields:
            protected_fields.append(uf)

    # Allowed fields derived from allowed_tuning categories
    allowed_fields: "set[str] | None" = None
    if allowed_tuning is not None:
        try:
            from strategy.driving_advisor import _derive_locked_fields
            locked = _derive_locked_fields(allowed_tuning)
            # We need the inverse — derive allowed from canonical minus locked
            from strategy.driving_advisor import _CANONICAL_SETUP_PARAMS
            allowed_fields = {f for f in _CANONICAL_SETUP_PARAMS if f not in locked}
        except Exception:
            allowed_fields = None  # fail open

    max_gear = _max_gear_from_setup(setup)

    # Indexed by field → best (highest-confidence) candidate so far
    # {field: SetupChangeIntent}
    proposed_by_field: dict[str, SetupChangeIntent] = {}

    all_rules = get_all_rules()

    for rule in all_rules:
        try:
            _process_rule(
                rule=rule,
                diagnosis=diagnosis,
                setup=setup,
                ranges=ranges,
                profile=profile,
                allowed_fields=allowed_fields,
                rule_outcome_store=rule_outcome_store,
                protected_fields=protected_fields,
                proposed_by_field=proposed_by_field,
                rejected=rejected,
                max_gear=max_gear,
            )
        except Exception as exc:
            log.debug("Rule %s failed: %s", rule.rule_id, exc)
            continue  # one bad rule must not abort the whole engine

    # Build final proposed list from proposed_by_field
    proposed = list(proposed_by_field.values())

    return SetupPlan(
        proposed=proposed,
        rejected_candidates=rejected,
        protected_fields=protected_fields,
    )


def _process_rule(
    rule: SetupRule,
    diagnosis: dict,
    setup: dict,
    ranges: dict,
    profile: DriverProfile,
    allowed_fields: "set[str] | None",
    rule_outcome_store: "RuleOutcomeStore | None",
    protected_fields: list,
    proposed_by_field: dict,
    rejected: list,
    max_gear: int,
) -> None:
    """Process a single rule — updates proposed_by_field, rejected, protected_fields."""

    # --- Pack A: unconditional field protection ---
    if rule.rule_id in _PACK_A_UNCONDITIONAL_PROTECT:
        if rule.field not in protected_fields and rule.field not in _PACK_A_VIRTUAL_FIELDS:
            protected_fields.append(rule.field)
        return

    # --- Skip virtual (meta) Pack A rules that have no real field ---
    if rule.field in _PACK_A_VIRTUAL_FIELDS:
        return

    # --- Evaluate preconditions ---
    if not _eval_preconditions(rule.preconditions, diagnosis):
        return  # rule does not fire

    # --- Evaluate contraindications ---
    if _eval_contraindications(rule.contraindications, diagnosis):
        return  # rule suppressed

    # --- Pack A conditional protection rules (A3, A4): block the field ---
    if rule.pack == "A" and rule.rule_id in _PACK_A_CONDITIONAL_PROTECT:
        # The rule fired = the guard condition is active → protect the field
        if rule.field not in protected_fields:
            protected_fields.append(rule.field)
        return

    # --- General Pack A: any firing Pack A rule → rejected_candidate ---
    if _is_pack_a_rule(rule):
        reason = f"pack_a_safety: {rule.title}"
        intent = SetupChangeIntent(
            field=rule.field,
            delta=0.0,
            from_value=None,
            to_value=None,
            symptom=rule.symptom,
            evidence=[],
            rule_id=rule.rule_id,
            rationale=f"BLOCKED — {rule.rationale}",
            rejected_alternatives=[],
            risk=rule.risk,
            confidence=rule.base_confidence,
            driver_style_alignment=DriverStyleAlignment.caution,
        )
        rejected.append(intent)
        return

    # --- Skip if field is protected ---
    if rule.field in protected_fields:
        return

    # --- Allowed-tuning gate ---
    if allowed_fields is not None and rule.field not in allowed_fields:
        return

    # --- Gear count gating ---
    gear_idx = _gear_index(rule.field)
    if gear_idx > 0 and gear_idx > max_gear:
        # Gear beyond what the car has — skip (would be a no-op or invalid)
        return

    # --- Resolve delta ---
    delta = resolve_delta(rule.delta_fn, setup, ranges, diagnosis)
    if delta == 0.0:
        return  # no-op

    # --- Compute from/to values ---
    from_value: "float | None" = None
    to_value: "float | None" = None
    cur_raw = setup.get(rule.field)
    if cur_raw is not None:
        try:
            from_value = float(cur_raw)
            to_value = from_value + delta
        except (TypeError, ValueError):
            pass

    # --- Skip when field is absent from setup (cannot compute a valid to_value) ---
    # A change with to_value=None produces an incomplete change entry that fails
    # the setup_fields/changes consistency validator.
    if from_value is None:
        return

    # --- Clamp to ranges ---
    if to_value is not None and rule.field in ranges:
        lo, hi = ranges[rule.field]
        try:
            to_value = max(float(lo), min(float(hi), to_value))
        except (TypeError, ValueError):
            pass

    # --- No-op after clamp ---
    if from_value is not None and to_value is not None:
        if abs(to_value - from_value) < 1e-9:
            return

    # --- Gear inversion check ---
    if gear_idx > 1 and from_value is not None and to_value is not None:
        prev_key = f"gear_{gear_idx - 1}"
        prev_val = setup.get(prev_key)
        if prev_val is not None:
            try:
                prev_float = float(prev_val)
                if to_value >= prev_float:
                    # Would create inversion — reject
                    intent = SetupChangeIntent(
                        field=rule.field,
                        delta=delta,
                        from_value=from_value,
                        to_value=to_value,
                        symptom=rule.symptom,
                        evidence=[],
                        rule_id=rule.rule_id,
                        rationale=f"BLOCKED — gear ratio inversion: {rule.field} to_value={to_value:.3f} >= gear_{gear_idx-1}={prev_float:.3f}",
                        rejected_alternatives=[],
                        risk=RiskLevel.high,
                        confidence=ConfidenceLevel.high,
                        driver_style_alignment=DriverStyleAlignment.caution,
                    )
                    rejected.append(intent)
                    return
            except (TypeError, ValueError):
                pass

    # --- Compute confidence (with outcome-store downgrade) ---
    confidence = rule.base_confidence
    if rule_outcome_store is not None:
        rate = rule_outcome_store.get_success_rate(rule.rule_id)
        fc = rule_outcome_store.fire_count(rule.rule_id)
        if rate is not None and rate < LOW_SUCCESS_RATE and fc >= MIN_OUTCOME_SAMPLES:
            confidence = _downgrade_confidence(confidence)

    # --- Driver-style alignment ---
    alignment = _compute_driver_style_alignment(rule, profile)

    # --- Apply driver-style caution from profile ---
    # If profile dislikes_snap_exit and rule would increase LSD accel → caution
    if profile.dislikes_snap_exit and rule.field == "lsd_accel" and delta > 0:
        if diagnosis.get("driver_feel_flags", {}).get("snap_oversteer_exit"):
            return  # blocked by driver-style contraindication

    # --- Build evidence list from diagnosis ---
    evidence: list[str] = []
    for key in ("wheelspin_band", "bottoming_band", "dominant_problem",
                "wheelspin_subtype", "compliance_priority", "gearbox_flag"):
        val = diagnosis.get(key)
        if val and val not in ("low", "minor", "unknown", "insufficient_data", False, None):
            evidence.append(f"{key}={val}")
    feel_flags = diagnosis.get("driver_feel_flags") or {}
    for fk, fv in feel_flags.items():
        if fv:
            evidence.append(f"feel:{fk}")

    # --- Build candidate intent ---
    intent = SetupChangeIntent(
        field=rule.field,
        delta=delta,
        from_value=from_value,
        to_value=to_value,
        symptom=rule.symptom,
        evidence=evidence,
        rule_id=rule.rule_id,
        rationale=rule.rationale,
        rejected_alternatives=[],
        risk=rule.risk,
        confidence=confidence,
        driver_style_alignment=alignment,
    )

    # --- Conflict resolution: same field, check existing candidate ---
    existing = proposed_by_field.get(rule.field)
    if existing is not None:
        # Same field already has a candidate
        existing_delta = existing.delta
        if (delta > 0) == (existing_delta > 0):
            # Same direction — keep higher confidence candidate
            _conf_rank = {ConfidenceLevel.low: 0, ConfidenceLevel.med: 1, ConfidenceLevel.high: 2}
            if _conf_rank[confidence] > _conf_rank[existing.confidence]:
                # New candidate wins — move existing to rejected with conflict reason
                rej_existing = existing._replace(
                    rationale=f"conflict:{rule.rule_id} — lower confidence",
                )
                rejected.append(rej_existing)
                proposed_by_field[rule.field] = intent
            else:
                # Existing wins — reject new with conflict reason
                rejected.append(intent._replace(
                    rationale=f"conflict:{existing.rule_id} — lower confidence",
                ))
        else:
            # Opposite directions — conflict; keep higher confidence, reject both or lower
            _conf_rank = {ConfidenceLevel.low: 0, ConfidenceLevel.med: 1, ConfidenceLevel.high: 2}
            if _conf_rank[confidence] >= _conf_rank[existing.confidence]:
                rej_existing = existing._replace(
                    rationale=f"conflict:{rule.rule_id} — opposite direction, lower or equal confidence",
                )
                rejected.append(rej_existing)
                proposed_by_field[rule.field] = intent
            else:
                rejected.append(intent._replace(
                    rationale=f"conflict:{existing.rule_id} — opposite direction, lower confidence",
                ))
    else:
        proposed_by_field[rule.field] = intent
