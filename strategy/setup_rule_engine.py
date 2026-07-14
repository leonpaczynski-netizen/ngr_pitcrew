"""Setup rule engine — Group 45: Setup Brain Intelligence Expansion.

Group 45 changes
----------------
- run_rule_engine / _run_rule_engine_inner: new optional keyword params
  session_type, car_class, drivetrain, tyre_wear_multiplier (all default None).
  Existing Group 42/43/44 callers work unchanged (defaults cover them).
- _scope_matches: new filter applied AFTER Pack A unconditional checks.
  Pack A rules are always evaluated (safety invariants); scope only gates B/C/D/P+.
- SetupChangeIntent: four new tail fields with "" defaults:
    source_label, session_influence, car_drivetrain_influence, pack.
- _process_rule: new session_type / drivetrain params; profile rank bonus
  (+1/0/-1) used as a tiebreaker tuple (confidence_rank, profile_rank_bonus).
- Session confidence upgrade: quali → prefers_front_bite/trail_braker tags
  upgrade one step; race → safety-phase or race_values_consistency tags upgrade.
- Monotonic gear inversion check: changed from `>=` to `>` so equal adjacent
  ratios are ALLOWED; reject-reason starts with "monotonic ordering violation".

Previously "Setup rule engine — Group 42: Rule-First Setup Brain."

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

from strategy._setup_constants import (
    MIN_OUTCOME_SAMPLES, LOW_SUCCESS_RATE, HIGH_SUCCESS_RATE,
    HIGH_FUEL_MULTIPLIER_THRESHOLD,
)
from strategy.setup_knowledge_base import (
    CarClass,
    ConfidenceLevel,
    DrivetrainType,
    RiskLevel,
    RulePhase,
    SessionType,
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
# Arbitration (Phase 10): when two rules contend for the same field, the winner
# records what it beat so "Considered alternatives" is real, not "none".
# ---------------------------------------------------------------------------

def _arbitration_note(loser: "SetupChangeIntent", reason: str) -> str:
    """One-line record of a rule that lost a same-field contest, for the winner's
    rejected_alternatives. Names the beaten rule, its symptom and direction."""
    try:
        direction = "raise" if float(loser.delta) > 0 else "lower"
    except (TypeError, ValueError):
        direction = "change"
    sym = (loser.symptom or "").strip()
    sym_txt = f" for {sym}" if sym else ""
    rid = loser.rule_id or "rule"
    return f"{rid}: {direction} {loser.field}{sym_txt} — not taken ({reason})"


def _record_alternative(winner: "SetupChangeIntent", loser: "SetupChangeIntent",
                        reason: str) -> "SetupChangeIntent":
    """Return the winner with the beaten candidate appended to rejected_alternatives."""
    note = _arbitration_note(loser, reason)
    return winner._replace(
        rejected_alternatives=list(winner.rejected_alternatives) + [note]
    )


# ---------------------------------------------------------------------------
# NamedTuples
# ---------------------------------------------------------------------------

class SetupChangeIntent(NamedTuple):
    """A single proposed or rejected setup change with full explainability.

    Group 45 tail fields (all default ""):
      source_label          — "Porsche-specific rule" if pack=="P", else "generic rule".
      session_influence     — verbatim session-bias text; "" when session unknown.
      car_drivetrain_influence — drivetrain-specific modifier text; "" when generic.
      pack                  — rule pack letter (e.g. "A", "B", "P").
    """
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
    # Group 45 explainability fields — at tail with defaults so existing code is unaffected
    source_label: str = ""
    session_influence: str = ""
    car_drivetrain_influence: str = ""
    pack: str = ""
    # Group 46 explainability fields — learning and fuel context
    learning_influence: str = ""
    fuel_influence: str = ""


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
# Scope filter (Group 45)
# ---------------------------------------------------------------------------

def _scope_matches(
    rule: SetupRule,
    session_type: "SessionType | None",
    car_class: "CarClass | None",
    drivetrain: "DrivetrainType | None",
) -> bool:
    """Return True when the rule applies to the given context.

    None context value = wildcard-permissive (never filters that axis).
    Rules with applies_* == 'any' always pass.
    Pack A rules are NOT filtered by this function — they are called
    only for non-Pack-A rules (safety invariants are always evaluated).
    """
    if (
        rule.applies_session != SessionType.any
        and session_type is not None
        and rule.applies_session != session_type
    ):
        return False
    if (
        rule.applies_drivetrain != DrivetrainType.any
        and drivetrain is not None
        and rule.applies_drivetrain != drivetrain
    ):
        return False
    if (
        rule.applies_car_class != CarClass.any
        and car_class is not None
        and rule.applies_car_class != car_class
    ):
        return False
    return True


def _upgrade_confidence(c: ConfidenceLevel) -> ConfidenceLevel:
    """Upgrade confidence one step (low→med→high); cap at high."""
    if c == ConfidenceLevel.low:
        return ConfidenceLevel.med
    return ConfidenceLevel.high


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
    *,
    session_type: "SessionType | None" = None,
    car_class: "CarClass | None" = None,
    drivetrain: "DrivetrainType | None" = None,
    tyre_wear_multiplier: "float | None" = None,
    car: str = "",
    track: str = "",
    profile_version: str = "",
    blocked_rule_ids: "dict | None" = None,
) -> SetupPlan:
    """Evaluate all registered rules against diagnosis and return a SetupPlan.

    Parameters
    ----------
    diagnosis          : Output of build_setup_diagnosis.
    setup              : Current car setup dict (canonical keys).
    ranges             : Resolved per-car ranges from resolve_ranges().
    profile            : DriverProfile from build_driver_profile().
    allowed_tuning     : Optional list of allowed tuning categories; None = no restriction.
    rule_outcome_store : Optional outcome store for AC21 confidence downgrade.
    session_type       : SessionType enum or None (None = wildcard-permissive).
    car_class          : CarClass enum or None (None = wildcard-permissive).
    drivetrain         : DrivetrainType enum or None (None = wildcard-permissive).
    tyre_wear_multiplier: float or None — for tyre/fuel weighting; not directly used by
                          the engine (the diagnosis dict already carries tyre_wear_high);
                          accepted here for forward-compatibility.
    car                : Car identifier string for keyed outcome-store lookup (Group 46).
    track              : Track identifier string for keyed outcome-store lookup (Group 46).
    profile_version    : Driver profile version string for keyed lookup (Group 46).

    Returns
    -------
    SetupPlan with proposed / rejected_candidates / protected_fields.
    Never raises — returns empty SetupPlan on any error.
    """
    try:
        return _run_rule_engine_inner(
            diagnosis, setup, ranges, profile, allowed_tuning, rule_outcome_store,
            session_type=session_type,
            car_class=car_class,
            drivetrain=drivetrain,
            car=car,
            track=track,
            profile_version=profile_version,
            blocked_rule_ids=blocked_rule_ids,
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
    *,
    session_type: "SessionType | None" = None,
    car_class: "CarClass | None" = None,
    drivetrain: "DrivetrainType | None" = None,
    car: str = "",
    track: str = "",
    profile_version: str = "",
    blocked_rule_ids: "dict | None" = None,
) -> SetupPlan:
    proposed: list[SetupChangeIntent] = []
    rejected: list[SetupChangeIntent] = []
    _blocked_rules = blocked_rule_ids or {}
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
                session_type=session_type,
                car_class=car_class,
                drivetrain=drivetrain,
                car=car,
                track=track,
                profile_version=profile_version,
                blocked_rule_ids=_blocked_rules,
            )
        except Exception as exc:
            log.debug("Rule %s failed: %s", rule.rule_id, exc)
            continue  # one bad rule must not abort the whole engine

    # Group 46: per-gear rule emission (AFTER main rule loop)
    _emit_per_gear_changes(
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
        gearbox_flag=diagnosis.get("gearbox_flag", "preserve"),
        gearing_diagnosis_category=diagnosis.get("gearing_diagnosis_category", "insufficient_data"),
        car=car,
        track=track,
        profile_version=profile_version,
    )

    # Build final proposed list from proposed_by_field
    proposed = list(proposed_by_field.values())

    # Build per_gear_explanation and attach to diagnosis (mutable dict)
    _gear_explanation = _build_per_gear_explanation(
        diagnosis=diagnosis,
        setup=setup,
        max_gear=max_gear,
        proposed_by_field=proposed_by_field,
        rejected=rejected,
    )
    if isinstance(diagnosis, dict):
        diagnosis["per_gear_explanation"] = _gear_explanation

    return SetupPlan(
        proposed=proposed,
        rejected_candidates=rejected,
        protected_fields=protected_fields,
    )


# ---------------------------------------------------------------------------
# Anti-ratchet movement cap
# ---------------------------------------------------------------------------
# Automated rule proposals apply a FIXED increment to the current value and clamp
# only to the static per-car range. Across successive Analyse/Apply cycles a
# persistent symptom therefore walks a field toward its mechanical limit in fixed
# steps, bounded only by the range wall. The movement cap reserves the outer
# fraction of every range: proposals may move a field freely in the interior but
# cannot push it INTO (or deeper into) the reserve at either end. Movement AWAY
# from a boundary is never restricted. Gearbox fields are naturally exempt — they
# are not range-managed (absent from `ranges`), so their monotonicity logic is
# untouched. This generalises the pre-existing `aero_rear_healthy` soft ceiling
# (which caps rear-aero increases at ~80%) to every range-managed field.
_MOVEMENT_CAP_RESERVE_FRAC = 0.10


def _apply_movement_cap(
    field: str, from_value: float, to_value: float, ranges: dict
) -> "tuple[float, bool, str]":
    """Hold an automated proposal out of the outer operating-band reserve.

    Returns (capped_to_value, cap_hit, reason).

    - Movement away from the nearer boundary is never restricted (cap_hit False).
    - Movement toward a boundary is capped at the reserve edge. A field already
      inside the reserve cannot be pushed further toward that limit — the value is
      held at the current value (a no-op the caller surfaces as a 'near-limit'
      rejection). cap_hit is True whenever the reserve altered the proposal.
    """
    try:
        lo, hi = float(ranges[field][0]), float(ranges[field][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return to_value, False, ""
    span = hi - lo
    if span <= 0:
        return to_value, False, ""
    reserve = _MOVEMENT_CAP_RESERVE_FRAC * span
    hi_guard = hi - reserve
    lo_guard = lo + reserve
    if to_value > from_value and to_value > hi_guard:
        capped = max(from_value, hi_guard)
        if capped < to_value:
            return capped, True, f"near its upper limit ({hi:g}); held at the operating-band edge ({hi_guard:g})"
    elif to_value < from_value and to_value < lo_guard:
        capped = min(from_value, lo_guard)
        if capped > to_value:
            return capped, True, f"near its lower limit ({lo:g}); held at the operating-band edge ({lo_guard:g})"
    return to_value, False, ""


def _movement_cap_rejection(
    rule: "SetupRule", from_value: float, delta: float, reason: str
) -> "SetupChangeIntent":
    """Rejected candidate explaining a field is already at its operating-band edge."""
    return SetupChangeIntent(
        field=rule.field,
        delta=0.0,
        from_value=from_value,
        to_value=from_value,
        symptom=rule.symptom,
        evidence=[],
        rule_id=rule.rule_id,
        rationale=(
            f"movement_cap: {rule.field} is already {reason} — automated tuning "
            "will not drive it further toward its limit; a persisting symptom "
            "likely has another root cause."
        ),
        rejected_alternatives=[],
        risk=rule.risk,
        confidence=rule.base_confidence,
        driver_style_alignment=DriverStyleAlignment.caution,
        source_label="Porsche-specific rule" if rule.pack == "P" else "generic rule",
        session_influence="",
        car_drivetrain_influence="",
        pack=rule.pack,
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
    session_type: "SessionType | None" = None,
    car_class: "CarClass | None" = None,
    drivetrain: "DrivetrainType | None" = None,
    car: str = "",
    track: str = "",
    profile_version: str = "",
    blocked_rule_ids: "dict | None" = None,
) -> None:
    """Process a single rule — updates proposed_by_field, rejected, protected_fields.

    Group 45 additions:
    - Scope filter (_scope_matches) applied after Pack A unconditional checks.
      Pack A rules are EXEMPT from scope filtering (safety invariants).
    - Session confidence upgrade: qualifying → prefers_front_bite/trail_braker tags
      upgrade confidence one step; race → safety-phase or race_values_consistency
      tags upgrade one step.
    - Profile rank bonus (+1/0/-1) used as tiebreaker tuple when confidence is equal.
    - Monotonic gear inversion check: strict > (not >=) — equal ratios are allowed.
      Reject-reason starts with "monotonic ordering violation".
    - New explainability fields on SetupChangeIntent: source_label, session_influence,
      car_drivetrain_influence, pack.
    """

    # --- Pack A: unconditional field protection ---
    if rule.rule_id in _PACK_A_UNCONDITIONAL_PROTECT:
        if rule.field not in protected_fields and rule.field not in _PACK_A_VIRTUAL_FIELDS:
            protected_fields.append(rule.field)
        return

    # --- Closed-loop lockout (Phase 1) ---
    # A rule whose recorded outcomes at this scope are decisively negative (worsened,
    # never improved) is LOCKED OUT — surfaced as a rejected candidate with the reason,
    # never proposed — so the app stops re-recommending a change that made the car
    # worse. Pack A safety protection above still runs first; this only blocks
    # NON-safety proposals. Lifted automatically once a later 'improved' outcome exists.
    _lockout_reason = (blocked_rule_ids or {}).get(rule.rule_id)
    if _lockout_reason:
        rejected.append(SetupChangeIntent(
            field=rule.field, delta=0.0, from_value=setup.get(rule.field),
            to_value=setup.get(rule.field), symptom=rule.symptom, evidence=[],
            rule_id=rule.rule_id, rationale=str(_lockout_reason),
            rejected_alternatives=[], risk=RiskLevel.high, confidence=ConfidenceLevel.low,
            driver_style_alignment=DriverStyleAlignment.caution,
            source_label="closed-loop lockout", session_influence="",
            car_drivetrain_influence="", pack=rule.pack))
        return

    # --- Skip virtual (meta) Pack A rules that have no real field ---
    if rule.field in _PACK_A_VIRTUAL_FIELDS:
        return

    # --- Pack A safety checks: preconditions + contraindications BEFORE scope filter ---
    # Pack A rules are unconditionally evaluated (safety invariants are not scope-filtered).
    if _is_pack_a_rule(rule):
        # Evaluate preconditions
        if not _eval_preconditions(rule.preconditions, diagnosis):
            return  # rule does not fire
        # Evaluate contraindications
        if _eval_contraindications(rule.contraindications, diagnosis):
            return  # rule suppressed
        # Conditional protect (A3, A4)
        if rule.rule_id in _PACK_A_CONDITIONAL_PROTECT:
            if rule.field not in protected_fields:
                protected_fields.append(rule.field)
            return
        # General Pack A: any firing Pack A rule → rejected_candidate
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
            source_label="generic rule",
            session_influence="",
            car_drivetrain_influence="",
            pack=rule.pack,
        )
        rejected.append(intent)
        return

    # --- Scope filter (Group 45): non-Pack-A rules only ---
    if not _scope_matches(rule, session_type, car_class, drivetrain):
        return  # rule does not apply in this session/car context

    # --- Evaluate preconditions ---
    if not _eval_preconditions(rule.preconditions, diagnosis):
        return  # rule does not fire

    # --- Evaluate contraindications ---
    if _eval_contraindications(rule.contraindications, diagnosis):
        return  # rule suppressed

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

    # --- Movement cap (anti-ratchet) ---
    # Hold automated proposals out of the outer operating-band reserve so repeated
    # fixed-increment changes cannot walk a field to its mechanical limit across
    # successive Analyse/Apply cycles. Gearbox fields are exempt (not in `ranges`).
    _cap_hit = False
    _cap_reason = ""
    if to_value is not None and from_value is not None and rule.field in ranges:
        to_value, _cap_hit, _cap_reason = _apply_movement_cap(
            rule.field, from_value, to_value, ranges
        )

    # --- No-op after clamp / cap ---
    if from_value is not None and to_value is not None:
        if abs(to_value - from_value) < 1e-9:
            if _cap_hit:
                # The reserve fully absorbed the proposal: the field is already at
                # the edge of its safe operating band. Surface a rejected candidate
                # so the driver learns the field is near its limit rather than the
                # recommendation vanishing silently.
                rejected.append(
                    _movement_cap_rejection(rule, from_value, delta, _cap_reason)
                )
            return

    # If the reserve reduced (but did not zero) the movement, keep the change but
    # make delta reflect the capped magnitude so the intent stays self-consistent.
    if _cap_hit and from_value is not None and to_value is not None:
        delta = to_value - from_value

    # --- Gear inversion check (Group 45: strict > to allow equal adjacent ratios) ---
    # Reject reason MUST start with "monotonic ordering violation" (brief contract).
    if gear_idx > 1 and from_value is not None and to_value is not None:
        prev_key = f"gear_{gear_idx - 1}"
        prev_val = setup.get(prev_key)
        if prev_val is not None:
            try:
                prev_float = float(prev_val)
                if to_value > prev_float:
                    # Would create strict inversion — reject
                    # (equal values are ALLOWED: gear_N == gear_{N-1} is not an inversion)
                    intent = SetupChangeIntent(
                        field=rule.field,
                        delta=delta,
                        from_value=from_value,
                        to_value=to_value,
                        symptom=rule.symptom,
                        evidence=[],
                        rule_id=rule.rule_id,
                        rationale=(
                            f"monotonic ordering violation: {rule.field} to_value={to_value:.3f} "
                            f"> gear_{gear_idx-1}={prev_float:.3f}"
                        ),
                        rejected_alternatives=[],
                        risk=RiskLevel.high,
                        confidence=ConfidenceLevel.high,
                        driver_style_alignment=DriverStyleAlignment.caution,
                        source_label="generic rule" if rule.pack != "P" else "Porsche-specific rule",
                        session_influence="",
                        car_drivetrain_influence="",
                        pack=rule.pack,
                    )
                    rejected.append(intent)
                    return
            except (TypeError, ValueError):
                pass

    # --- Compute confidence (with outcome-store downgrade/upgrade — Group 46) ---
    # Key-aware lookup with fallback to empty-key for backward compatibility.
    # Group 46: also upgrade when success_rate >= HIGH_SUCCESS_RATE with enough samples.
    confidence = rule.base_confidence
    _learning_influence = ""
    if rule_outcome_store is not None:
        # Specific-key lookup first (car+track+profile_version scoped)
        rate = rule_outcome_store.get_success_rate(rule.rule_id, car, track, profile_version)
        fc = rule_outcome_store.fire_count(rule.rule_id, car, track, profile_version)
        # Fall back to empty-key aggregate if no specific-key data
        if rate is None:
            rate = rule_outcome_store.get_success_rate(rule.rule_id)
            fc = rule_outcome_store.fire_count(rule.rule_id)
        if rate is not None and fc >= MIN_OUTCOME_SAMPLES:
            if rate >= HIGH_SUCCESS_RATE:
                confidence = _upgrade_confidence(confidence)
                _learning_influence = (
                    f"learning: {fc} samples, {rate:.0%} success — confidence upgraded"
                )
            elif rate < LOW_SUCCESS_RATE:
                confidence = _downgrade_confidence(confidence)
                _learning_influence = (
                    f"learning: {fc} samples, {rate:.0%} success — confidence downgraded"
                )
            # else: between thresholds — no learning claim

    # --- Session confidence upgrade (Group 45) ---
    # qualifying → rules with prefers_front_bite or trail_braker tags get +1 confidence
    # race → safety-phase rules or race_values_consistency-tagged rules get +1 confidence
    # Downgrade must NEVER be reversed here — only upgrade after the downgrade.
    _session_influence = ""
    if session_type == SessionType.quali:
        if rule.driver_style_tags and (
            "prefers_front_bite" in rule.driver_style_tags
            or "trail_braker" in rule.driver_style_tags
        ):
            confidence = _upgrade_confidence(confidence)
            _session_influence = "qualifying bias applied — front response/bite prioritised"
        else:
            # A qualifying rule that lacks front-bite/trail-braker tags gets no positive
            # quali claim — session is known but no special bias applies for this rule.
            _session_influence = ""
    elif session_type == SessionType.race:
        if (
            rule.phase == RulePhase.safety
            or (rule.driver_style_tags and "race_values_consistency" in rule.driver_style_tags)
        ):
            confidence = _upgrade_confidence(confidence)
            # Endurance flag comes from the diagnosis (injected by driving_advisor)
            _duration_mins = diagnosis.get("duration_mins", 0) or 0
            if _duration_mins >= 60:
                _session_influence = "endurance bias applied"
            else:
                _session_influence = "race consistency bias applied"
    else:
        if session_type is None:
            _session_influence = "neutral weighting — session type not available"

    # --- Fuel load layer (Group 46) ---
    # High fuel load: traction/stability fields with delta>0 are upgraded;
    # rotation/aero-cut fields are noted (NOT downgraded) when delta<0.
    # Fuel influence is only claimed when fuel_high is genuinely True.
    _fuel_influence = ""
    _FUEL_TRACTION_STABILITY_FIELDS = frozenset({
        "lsd_accel", "lsd_initial", "arb_rear", "aero_rear", "ride_height_rear",
    })
    _FUEL_ROTATION_FIELDS = frozenset({
        "aero_front", "aero_rear", "lsd_decel", "brake_bias",
    })
    if diagnosis.get("fuel_high"):
        if rule.field in _FUEL_TRACTION_STABILITY_FIELDS and delta > 0:
            confidence = _upgrade_confidence(confidence)
            _fuel_influence = "high fuel load: traction/stability prioritised"
        elif rule.field in _FUEL_ROTATION_FIELDS and delta < 0:
            # Note only — do NOT downgrade, do NOT upgrade
            _fuel_influence = "high fuel load: rotation/aero-cut de-prioritised (note only)"

    # --- Driver-style alignment ---
    alignment = _compute_driver_style_alignment(rule, profile)

    # --- Apply driver-style caution from profile ---
    # If profile dislikes_snap_exit and rule would increase LSD accel → caution
    # Also record this in driver_style_influence context (the blocked case exits here).
    if profile.dislikes_snap_exit and rule.field == "lsd_accel" and delta > 0:
        if diagnosis.get("driver_feel_flags", {}).get("snap_oversteer_exit"):
            return  # blocked by driver-style contraindication

    # --- Profile rank bonus (Group 45): tiebreaker (+1/0/-1) ---
    # +1 if ALL rule.driver_style_tags ⊆ profile.style_tags
    # 0 if partial/none overlap
    # -1 if profile.dislikes_snap_exit and rule increases lsd_accel (already blocked above
    #    when snap_oversteer_exit is in the diagnosis; this covers the ranking reduction
    #    when snap is not in the diagnosis but profile still dislikes it)
    _profile_rank_bonus = 0
    if rule.driver_style_tags:
        _all_match = all(t in profile.style_tags for t in rule.driver_style_tags)
        if _all_match:
            _profile_rank_bonus = 1
    if profile.dislikes_snap_exit and rule.field == "lsd_accel" and delta > 0:
        _profile_rank_bonus = -1  # override — profile penalty for snap-risk LSD increase

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

    # --- Explainability fields (Group 45) ---
    _source_label = "Porsche-specific rule" if rule.pack == "P" else "generic rule"
    _car_drivetrain_influence = ""
    if drivetrain == DrivetrainType.rr and rule.applies_drivetrain == DrivetrainType.rr:
        _car_drivetrain_influence = "RR drivetrain: rear-exit-stability modifiers applied"
    elif drivetrain is None:
        _car_drivetrain_influence = "drivetrain unknown — generic logic applied"

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
        source_label=_source_label,
        session_influence=_session_influence,
        car_drivetrain_influence=_car_drivetrain_influence,
        pack=rule.pack,
        learning_influence=_learning_influence,
        fuel_influence=_fuel_influence,
    )

    # If the reserve trimmed the proposal to the operating-band edge, disclose it.
    if _cap_hit:
        intent = intent._replace(
            rationale=f"{intent.rationale} (movement capped — {_cap_reason})"
        )

    # --- Conflict resolution: same field, check existing candidate ---
    # Group 45: tiebreaker is a tuple (confidence_rank, profile_rank_bonus)
    _conf_rank = {ConfidenceLevel.low: 0, ConfidenceLevel.med: 1, ConfidenceLevel.high: 2}
    existing = proposed_by_field.get(rule.field)
    if existing is not None:
        # Reconstruct existing profile rank bonus
        _existing_bonus = 0
        if hasattr(existing, "driver_style_alignment"):
            if existing.driver_style_alignment == DriverStyleAlignment.aligned:
                _existing_bonus = 1
            elif existing.driver_style_alignment == DriverStyleAlignment.caution:
                _existing_bonus = -1
        _new_tuple = (_conf_rank[confidence], _profile_rank_bonus)
        _existing_tuple = (_conf_rank[existing.confidence], _existing_bonus)

        # Same field already has a candidate
        existing_delta = existing.delta
        if (delta > 0) == (existing_delta > 0):
            # Same direction — keep higher (confidence, profile_bonus) tuple
            if _new_tuple > _existing_tuple:
                # New candidate wins — move existing to rejected with conflict reason
                rej_existing = existing._replace(
                    rationale=f"conflict:{rule.rule_id} — lower confidence",
                )
                rejected.append(rej_existing)
                proposed_by_field[rule.field] = _record_alternative(
                    intent, existing, "same direction, lower confidence")
            else:
                # Existing wins — reject new with conflict reason
                rejected.append(intent._replace(
                    rationale=f"conflict:{existing.rule_id} — lower confidence",
                ))
                proposed_by_field[rule.field] = _record_alternative(
                    existing, intent, "same direction, lower confidence")
        else:
            # Opposite directions — conflict; keep higher (confidence, bonus) tuple
            if _new_tuple >= _existing_tuple:
                rej_existing = existing._replace(
                    rationale=f"conflict:{rule.rule_id} — opposite direction, lower or equal confidence",
                )
                rejected.append(rej_existing)
                proposed_by_field[rule.field] = _record_alternative(
                    intent, existing, "opposite direction, lower or equal confidence")
            else:
                rejected.append(intent._replace(
                    rationale=f"conflict:{existing.rule_id} — opposite direction, lower confidence",
                ))
                proposed_by_field[rule.field] = _record_alternative(
                    existing, intent, "opposite direction, lower confidence")
    else:
        proposed_by_field[rule.field] = intent


# ---------------------------------------------------------------------------
# Per-gear rule emission (Group 46)
# ---------------------------------------------------------------------------

# Thresholds for per-gear signal detection
# _PER_GEAR_WHEELSPIN_THRESHOLD is a PER-LAP average rate (float).
# wheelspin_by_gear values are now normalised by len(laps) in setup_diagnosis.py,
# mirroring exactly how rev_limiter_by_gear is averaged.  A value of 2.0 means
# the gear averaged 2 wheelspin-frames per lap — a meaningful and repeatable signal.
# This matches the per-lap scale of _PER_GEAR_LIMITER_THRESHOLD (>0 avg hits/lap)
# and is consistent with the evidence_reason text which already says "avg hits/lap".
# At 10 Hz telemetry, 2 wheelspin frames/lap ≈ 0.2 s of wheelspin per lap in that
# gear — a level that warrants investigation without triggering on noise.
_PER_GEAR_WHEELSPIN_THRESHOLD = 2.0   # wheelspin frames per lap in a gear to trigger a proposal
_PER_GEAR_LIMITER_THRESHOLD   = 0   # >0 hits is sufficient (brief: > 0)
_PER_GEAR_DELTA               = 0.03  # conservative, smaller than final_drive ±0.05


def _emit_per_gear_changes(
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
    gearbox_flag: str,
    gearing_diagnosis_category: str,
    car: str = "",
    track: str = "",
    profile_version: str = "",
) -> None:
    """Emit per-gear changes for gears 1..max_gear based on indexed telemetry signals.

    Called from _run_rule_engine_inner AFTER the main rule loop.  Only proposes
    a gear_N change when a REAL indexed signal exists for that gear:
      - limiter evidence: per_gear_limiter_evidence[N] > 0 AND gearing_diagnosis_category
        == 'gear_too_short' → lengthen (lower ratio by _PER_GEAR_DELTA)
      - wheelspin evidence: wheelspin_by_gear[N] > _PER_GEAR_WHEELSPIN_THRESHOLD (esp.
        low gears / snap-throttle context) → lengthen that gear for traction
      - bog evidence: bog_by_gear[N] if genuinely detected (shortens: +delta)

    Gated on gearbox_flag=='may_change'; emits a 'gearbox locked' note otherwise.
    Routes through the SAME clamp + strict-'>' monotonic check + conflict machinery.
    Uses rule_id="PG_{N}".
    """
    if gearbox_flag != "may_change":
        # Gearbox is locked — emit per-gear notes (no proposed changes)
        return

    per_gear_limiter: dict = diagnosis.get("per_gear_limiter_evidence") or {}
    wheelspin_by_gear: dict = diagnosis.get("wheelspin_by_gear") or {}
    bog_by_gear: dict = diagnosis.get("bog_by_gear") or {}

    for gear_n in range(1, max_gear + 1):
        gear_key = f"gear_{gear_n}"

        # Skip if field is not in setup (cannot compute from_value)
        cur_raw = setup.get(gear_key)
        if cur_raw is None:
            continue
        try:
            from_value = float(cur_raw)
        except (TypeError, ValueError):
            continue

        # Skip protected / locked fields
        if gear_key in protected_fields:
            continue
        if allowed_fields is not None and gear_key not in allowed_fields:
            continue

        # Skip if already has a proposed change from the main rule loop
        if gear_key in proposed_by_field:
            continue

        # Determine evidence and delta direction for this gear
        delta: float = 0.0
        evidence_reason: str = ""

        # 1. Limiter + gear_too_short → lengthen (lower ratio = negative delta)
        limiter_hits = float(per_gear_limiter.get(gear_n, 0) or 0)
        if limiter_hits > _PER_GEAR_LIMITER_THRESHOLD and gearing_diagnosis_category == "gear_too_short":
            delta = -_PER_GEAR_DELTA
            evidence_reason = (
                f"rev limiter in gear {gear_n} ({limiter_hits:.1f} avg hits/lap) + "
                f"gear_too_short diagnosis: lengthening ratio for traction/shift comfort"
            )

        # 2. Per-gear wheelspin → lengthen that gear for traction (negative delta = lower ratio)
        # ws_hits is a per-lap float average (normalised in setup_diagnosis.py);
        # compare as float against the per-lap threshold.
        ws_hits = float(wheelspin_by_gear.get(gear_n, 0) or 0)
        if ws_hits > _PER_GEAR_WHEELSPIN_THRESHOLD and delta == 0.0:
            delta = -_PER_GEAR_DELTA
            evidence_reason = (
                f"wheelspin in gear {gear_n} ({ws_hits:.1f} avg frames/lap): "
                f"lengthening ratio to ease traction demands"
            )

        # 3. Per-gear bog → shorten (higher ratio = positive delta), if genuine signal
        bog_hits = int(bog_by_gear.get(gear_n, 0) or 0)
        if bog_hits > 0 and delta == 0.0:
            delta = +_PER_GEAR_DELTA
            evidence_reason = (
                f"bog detected in gear {gear_n} ({bog_hits} events): "
                f"shortening ratio to reduce bog (stay above power band)"
            )

        if delta == 0.0:
            continue  # no indexed evidence for this gear

        # Compute to_value
        to_value = from_value + delta

        # Clamp to ranges
        if gear_key in ranges:
            lo, hi = ranges[gear_key]
            try:
                to_value = max(float(lo), min(float(hi), to_value))
            except (TypeError, ValueError):
                pass

        # No-op after clamp
        if abs(to_value - from_value) < 1e-9:
            continue

        # Strict monotonic check: gear_N must be <= gear_{N-1}
        if gear_n > 1:
            prev_key = f"gear_{gear_n - 1}"
            # Check proposed_by_field first (may have been modified by main loop or earlier PG)
            prev_intent = proposed_by_field.get(prev_key)
            prev_raw = (
                prev_intent.to_value
                if prev_intent is not None and prev_intent.to_value is not None
                else setup.get(prev_key)
            )
            if prev_raw is not None:
                try:
                    prev_float = float(prev_raw)
                    if to_value > prev_float:
                        # Monotonic violation — reject
                        _rej = SetupChangeIntent(
                            field=gear_key,
                            delta=delta,
                            from_value=from_value,
                            to_value=to_value,
                            symptom=f"per-gear: {evidence_reason}",
                            evidence=[evidence_reason],
                            rule_id=f"PG_{gear_n}",
                            rationale=(
                                f"monotonic ordering violation: {gear_key} to_value={to_value:.3f} "
                                f"> gear_{gear_n - 1}={prev_float:.3f}"
                            ),
                            rejected_alternatives=[],
                            risk=RiskLevel.high,
                            confidence=ConfidenceLevel.med,
                            driver_style_alignment=DriverStyleAlignment.neutral,
                            source_label="per-gear rule",
                            session_influence="",
                            car_drivetrain_influence="",
                            pack="",
                            learning_influence="",
                            fuel_influence="",
                        )
                        rejected.append(_rej)
                        continue
                except (TypeError, ValueError):
                    pass

        # Monotonic check: gear_N must be >= gear_{N+1} (check next gear too)
        if gear_n < max_gear:
            next_key = f"gear_{gear_n + 1}"
            next_intent = proposed_by_field.get(next_key)
            next_raw = (
                next_intent.to_value
                if next_intent is not None and next_intent.to_value is not None
                else setup.get(next_key)
            )
            if next_raw is not None:
                try:
                    next_float = float(next_raw)
                    if to_value < next_float:
                        # Would create inversion with next gear — reject
                        _rej = SetupChangeIntent(
                            field=gear_key,
                            delta=delta,
                            from_value=from_value,
                            to_value=to_value,
                            symptom=f"per-gear: {evidence_reason}",
                            evidence=[evidence_reason],
                            rule_id=f"PG_{gear_n}",
                            rationale=(
                                f"monotonic ordering violation: {gear_key} to_value={to_value:.3f} "
                                f"< gear_{gear_n + 1}={next_float:.3f}"
                            ),
                            rejected_alternatives=[],
                            risk=RiskLevel.high,
                            confidence=ConfidenceLevel.med,
                            driver_style_alignment=DriverStyleAlignment.neutral,
                            source_label="per-gear rule",
                            session_influence="",
                            car_drivetrain_influence="",
                            pack="",
                            learning_influence="",
                            fuel_influence="",
                        )
                        rejected.append(_rej)
                        continue
                except (TypeError, ValueError):
                    pass

        # Propose the change
        _pg_intent = SetupChangeIntent(
            field=gear_key,
            delta=delta,
            from_value=from_value,
            to_value=to_value,
            symptom=f"per-gear: {evidence_reason}",
            evidence=[evidence_reason],
            rule_id=f"PG_{gear_n}",
            rationale=evidence_reason,
            rejected_alternatives=[],
            risk=RiskLevel.low,
            confidence=ConfidenceLevel.med,
            driver_style_alignment=DriverStyleAlignment.neutral,
            source_label="per-gear rule",
            session_influence="",
            car_drivetrain_influence="",
            pack="",
            learning_influence="",
            fuel_influence="",
        )

        # Conflict with existing candidate for same field
        existing = proposed_by_field.get(gear_key)
        if existing is not None:
            _conf_rank = {ConfidenceLevel.low: 0, ConfidenceLevel.med: 1, ConfidenceLevel.high: 2}
            if _conf_rank[_pg_intent.confidence] > _conf_rank[existing.confidence]:
                rejected.append(existing._replace(
                    rationale=f"conflict:PG_{gear_n} — lower confidence",
                ))
                proposed_by_field[gear_key] = _record_alternative(
                    _pg_intent, existing, "lower confidence")
            else:
                rejected.append(_pg_intent._replace(
                    rationale=f"conflict:{existing.rule_id} — lower confidence",
                ))
                proposed_by_field[gear_key] = _record_alternative(
                    existing, _pg_intent, "lower confidence")
        else:
            proposed_by_field[gear_key] = _pg_intent


def _build_per_gear_explanation(
    diagnosis: dict,
    setup: dict,
    max_gear: int,
    proposed_by_field: dict,
    rejected: list,
) -> dict:
    """Build per_gear_explanation dict for all gears 1..max_gear.

    Returns {gear_N: "proposed: <reason>" | "not proposed: <reason>"} for every
    gear that exists in the setup, so the UI can display an honest per-gear note.
    """
    explanation: dict = {}
    per_gear_limiter: dict = diagnosis.get("per_gear_limiter_evidence") or {}
    wheelspin_by_gear: dict = diagnosis.get("wheelspin_by_gear") or {}
    bog_by_gear: dict = diagnosis.get("bog_by_gear") or {}
    gearbox_flag = diagnosis.get("gearbox_flag", "preserve")
    gearing_category = diagnosis.get("gearing_diagnosis_category", "insufficient_data")

    for gear_n in range(1, max_gear + 1):
        gear_key = f"gear_{gear_n}"
        if setup.get(gear_key) is None:
            continue

        if gearbox_flag != "may_change":
            explanation[gear_key] = "not proposed: gearbox locked (preserve flag)"
            continue

        pg_intent = proposed_by_field.get(gear_key)
        if pg_intent is not None and pg_intent.rule_id == f"PG_{gear_n}":
            explanation[gear_key] = f"proposed: {pg_intent.rationale}"
            continue

        # Check if rejected due to monotonic violation
        pg_rejected = [r for r in rejected if r.rule_id == f"PG_{gear_n}" and r.field == gear_key]
        if pg_rejected:
            explanation[gear_key] = f"not proposed: {pg_rejected[0].rationale}"
            continue

        # No indexed evidence
        limiter_hits = float(per_gear_limiter.get(gear_n, 0) or 0)
        ws_hits = int(wheelspin_by_gear.get(gear_n, 0) or 0)
        bog_hits = int(bog_by_gear.get(gear_n, 0) or 0)

        if limiter_hits == 0 and ws_hits <= _PER_GEAR_WHEELSPIN_THRESHOLD and bog_hits == 0:
            if gearing_category == "gear_too_short":
                explanation[gear_key] = (
                    f"not proposed: gearing_diagnosis_category=gear_too_short but no indexed "
                    f"evidence for gear {gear_n} specifically (no limiter hits, no wheelspin events)"
                )
            else:
                explanation[gear_key] = (
                    f"not proposed: no indexed evidence for gear {gear_n} "
                    f"(limiter=0, wheelspin={ws_hits}, bog=0)"
                )
        else:
            explanation[gear_key] = (
                f"not proposed: evidence present (limiter={limiter_hits:.1f}, "
                f"wheelspin={ws_hits}, bog={bog_hits}) but change was blocked or conflicted"
            )

    return explanation
