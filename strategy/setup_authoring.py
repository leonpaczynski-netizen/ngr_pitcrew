"""Group 64 — canonical deterministic setup-authoring architecture (pure, Qt-free).

The failed UAT showed Base, Qualifying and Race collapsing to the same output and a
lone rule change being presented as a finished setup. The root cause was that the
setup *objective* (base / qualifying / race) was carried only as a display label on
the incremental analyse path, and no single place authored a COMPLETE, objective-
specific, full-field setup with an explicit disposition for every adjustable field.

This module is that single place. It:

* carries the objective as a first-class :class:`SetupObjective` (never a label);
* takes one immutable :class:`SetupAuthoringContext` (the evidence needed to author);
* authors a full-field plan by composing the existing deterministic generator
  (``build_baseline_setup``: neutral physics + car-range placement + driver-profile
  bias + objective/session bias + proven-history seeding + track shaping + gearbox);
* assigns EVERY adjustable field one explicit :class:`FieldDisposition`, so no field
  disappears silently; and
* attaches an objective-specific justification per field, so Base/Qualifying/Race
  differences are evidence-supported, not visual theatre.

Authority boundary (unchanged): this module is DETERMINISTIC and authors values only
through the existing generator + range/legality clamps. It calls no AI, writes no
files, touches no DB, issues no pit command, and never auto-applies. The AI audit
stays advisory-only and the Apply gate is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from enum import Enum
from typing import Optional


class SetupObjective(Enum):
    """What a setup is being optimised for. Carried through the whole authoring
    path — never reduced to a display label."""
    BASE = "base"            # first intelligent track platform for practice
    QUALIFYING = "qualifying"  # maximum one-lap outright pace (fresh tyres, min fuel)
    RACE = "race"            # minimum TOTAL race time + repeatability over a stint


class FieldDisposition(Enum):
    """Why each adjustable field holds the value it holds. Every field the car
    exposes receives exactly one of these — nothing is left unexplained."""
    AUTHORED = "AUTHORED"                          # deterministically engineered for the objective
    PRESERVED = "PRESERVED"                        # kept at the current/known-good value on purpose
    PROVEN_HISTORY_SEED = "PROVEN_HISTORY_SEED"    # seeded from the driver's proven same-car value
    TRACK_MODEL_SEED = "TRACK_MODEL_SEED"          # shaped by an approved track model
    DRIVER_PROFILE_SEED = "DRIVER_PROFILE_SEED"    # nudged by the driver profile
    EVENT_CONSTRAINT = "EVENT_CONSTRAINT"          # locked by event tuning permissions
    CONTROLLED_TEST_REQUIRED = "CONTROLLED_TEST_REQUIRED"  # direction unknown → A/B test
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"        # conservative default, not diagnosed
    NOT_ADJUSTABLE = "NOT_ADJUSTABLE"              # car has no range / part for this field
    NOT_RELEVANT = "NOT_RELEVANT"                  # field exists but not relevant to this car/drivetrain
    REJECTED_FOR_SAFETY = "REJECTED_FOR_SAFETY"    # a candidate value was blocked by safety/legality


# Deterministic evidence precedence (documented; higher wins). A lower-confidence
# source must never silently overwrite a higher-confidence one. History informs a
# starting window; track/discipline demands then adjust it.
EVIDENCE_PRECEDENCE: tuple[str, ...] = (
    "1. Safety and legal constraints",
    "2. Car-adjustment ranges and installed-part availability",
    "3. Event restrictions (tuning permissions / BoP)",
    "4. Validated current telemetry",
    "5. Proven same-car, same-track/layout, same-driver history",
    "6. Proven same-car history from another track (reduced confidence)",
    "7. Approved track-model requirements",
    "8. Driver profile",
    "9. Car-characteristic defaults",
    "10. Generic conservative fallback",
)


@dataclass(frozen=True)
class SetupAuthoringContext:
    """The evidence required to author a complete objective-specific setup.

    One controlled context object — not a different dict per Base/Quali/Race path.
    Only ``car``, ``objective`` and ``ranges`` are required; everything else has an
    honest empty/neutral default so a fresh profile authors deterministically
    without inventing evidence.
    """
    car: str
    objective: SetupObjective
    ranges: dict
    drivetrain: str = ""
    num_gears: int = 6
    profile: object = None
    allowed_tuning: Optional[list] = None
    tuning_locked: bool = False
    track_profile: object = None
    history_prior: Optional[dict] = None       # field -> {value, tier, source, confidence}
    current_setup: Optional[dict] = None
    duration_mins: float = 0.0
    tyre_wear_multiplier: Optional[float] = None
    fuel_multiplier: Optional[float] = None
    refuel_rate: Optional[float] = None
    required_compounds: tuple = ()
    car_class: str = ""

    def session_type_str(self) -> str:
        """Map the objective to the ``session_type`` string the deterministic
        generator classifies for its bias table."""
        if self.objective is SetupObjective.QUALIFYING:
            return "Qualifying"
        if self.objective is SetupObjective.RACE:
            return "Race"
        return "Practice"  # BASE — an intelligent platform, no discipline bias


@dataclass(frozen=True)
class FieldPlanEntry:
    field: str
    value: object
    disposition: FieldDisposition
    source: str                     # provenance label from the generator
    objective_contribution: str     # WHY this value for THIS objective
    confidence: str
    proven_value: Optional[float]   # the driver's proven same-car value, if any
    reason: str

    def as_json(self) -> dict:
        return {
            "field": self.field,
            "value": self.value,
            "disposition": self.disposition.value,
            "source": self.source,
            "objective_contribution": self.objective_contribution,
            "confidence": self.confidence,
            "proven_value": self.proven_value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FullFieldPlan:
    objective: SetupObjective
    session_type: str
    setup_fields: dict
    entries: list                   # list[FieldPlanEntry]
    analysis: str
    confidence: str
    seeded_from_history: list       # field names seeded from proven history

    def dispositions(self) -> dict:
        return {e.field: e.disposition.value for e in self.entries}

    def as_json(self) -> dict:
        return {
            "objective": self.objective.value,
            "session_type": self.session_type,
            "setup_fields": dict(self.setup_fields),
            "entries": [e.as_json() for e in self.entries],
            "dispositions": self.dispositions(),
            "analysis": self.analysis,
            "confidence": self.confidence,
            "seeded_from_history": list(self.seeded_from_history),
        }


def objective_from_session_type(session_type: str) -> SetupObjective:
    """Classify a UI session-type string into a canonical objective."""
    st = (session_type or "").strip().lower()
    if "qual" in st:
        return SetupObjective.QUALIFYING
    if "race" in st or "sprint" in st or "endurance" in st:
        return SetupObjective.RACE
    return SetupObjective.BASE


# ---------------------------------------------------------------------------
# Objective-specific per-field justification
# ---------------------------------------------------------------------------
# Keyed (objective, field) → short reason a value leans the way it does for this
# discipline. Only fields the discipline actually biases carry a specific line;
# others get a generic objective statement. Grounded in _SESSION_BIAS_TABLE.
_OBJECTIVE_FIELD_REASON: dict = {
    SetupObjective.QUALIFYING: {
        "camber_front": "more front camber for peak one-lap cornering grip (tyre life is irrelevant over one lap)",
        "camber_rear": "more rear camber for peak one-lap grip",
        "toe_front": "more front toe-out for sharper turn-in on a single flying lap",
        "aero_front": "more front downforce for sharper turn-in / mid-corner bite at maximum attack",
        "brake_bias": "brake bias forward for entry bite and trail-braking rotation",
        "lsd_decel": "freer braking-side diff for more corner-entry rotation for one lap",
        "lsd_accel": "freer accel-side diff for more exit rotation (accept slight slip for one lap)",
        "ride_height_front": "lower platform for more aero — no long-run bottoming worry over one lap",
        "ride_height_rear": "lower platform for more aero — no long-run bottoming worry over one lap",
    },
    SetupObjective.RACE: {
        "lsd_accel": "more accel-side lock for repeatable exit traction over the stint",
        "lsd_decel": "a touch more braking-side stability for predictable entry over many laps",
        "aero_rear": "more rear downforce for high-speed stability under fuel load",
        "ride_height_front": "platform margin over fuel burn and bumps across the stint",
        "ride_height_rear": "platform margin over fuel burn and bumps across the stint",
    },
    SetupObjective.BASE: {},
}

_OBJECTIVE_GENERIC_REASON: dict = {
    SetupObjective.BASE: "balanced, track-suitable starting platform for practice",
    SetupObjective.QUALIFYING: "one-lap outright pace on fresh tyres and minimum fuel",
    SetupObjective.RACE: "minimum total race time — repeatable pace, stable over fuel and tyre wear",
}


# Provenance-label → disposition. Labels come from strategy.setup_baseline.
def _disposition_for_change(change: dict, objective: SetupObjective) -> FieldDisposition:
    src = str(change.get("source_label") or change.get("rationale") or "")
    sess = str(change.get("session_influence") or "")
    # History-seeded values win the provenance.
    if "proven setup" in src or "seeded from your proven" in src:
        return FieldDisposition.PROVEN_HISTORY_SEED
    # Objective/session bias actually moved the value → engineered for the objective.
    if "session bias applied" in sess:
        return FieldDisposition.AUTHORED
    if "driver-profile biased" in src:
        return FieldDisposition.DRIVER_PROFILE_SEED
    if "conservative default" in src:
        return FieldDisposition.INSUFFICIENT_EVIDENCE
    # Track shaping is folded into aero via bias; a car-range adaptation or a plain
    # neutral seed is a deterministic authored starting value.
    return FieldDisposition.AUTHORED


def author_full_field_plan(ctx: SetupAuthoringContext) -> FullFieldPlan:
    """Author a complete, objective-specific, full-field setup with a disposition
    for EVERY adjustable field the selected car exposes.

    Deterministic: composes ``build_baseline_setup`` (the single value-authoring
    funnel) and then classifies each field. Authors no value the generator/validator
    would not, invents nothing, and calls no AI.
    """
    # Function-local imports avoid any module-level cycle (setup_baseline is imported
    # lazily by driving_advisor; setup_authoring sits above both).
    from strategy.setup_baseline import build_baseline_setup, NEUTRAL_SEEDS
    from strategy.driving_advisor import (
        _CANONICAL_SETUP_PARAMS, _DISPLAY_ONLY_FIELDS, _derive_locked_fields,
    )
    from strategy.setup_history_intelligence import build_baseline_seed_overrides

    objective = ctx.objective
    session_type = ctx.session_type_str()

    # Proven-history seed overrides (geometry + LSD triplet, strong scope only).
    seed_overrides: dict = {}
    if ctx.history_prior:
        try:
            seed_overrides = build_baseline_seed_overrides(ctx.history_prior)
        except Exception:
            seed_overrides = {}

    raw = build_baseline_setup(
        ctx.car, ctx.ranges, ctx.drivetrain, ctx.num_gears,
        ctx.profile, ctx.allowed_tuning, ctx.tuning_locked,
        session_type=session_type,
        tyre_wear_multiplier=ctx.tyre_wear_multiplier,
        car_class=ctx.car_class,
        duration_mins=ctx.duration_mins,
        track_profile=ctx.track_profile,
        historical_seed_overrides=seed_overrides or None,
    )

    changes_by_field = {c.get("field"): c for c in (raw.get("changes") or []) if c.get("field")}
    setup_fields = dict(raw.get("setup_fields") or {})

    # Which fields are locked by event permissions, and which the drivetrain hides.
    locked_fields = _derive_locked_fields(ctx.allowed_tuning) if ctx.allowed_tuning else set()
    _is_awd = (ctx.drivetrain or "").upper() in {"AWD", "4WD", "4X4"}
    _front_diff = {"lsd_front_initial", "lsd_front_accel", "lsd_front_decel"}

    prior = ctx.history_prior or {}

    entries: list[FieldPlanEntry] = []
    seeded: list[str] = []
    # Author a disposition for EVERY canonical actionable field (display-only excluded).
    for f in sorted(_CANONICAL_SETUP_PARAMS - _DISPLAY_ONLY_FIELDS):
        proven = None
        pd = prior.get(f)
        if isinstance(pd, dict):
            try:
                proven = float(pd.get("value"))
            except (TypeError, ValueError):
                proven = None

        # Not adjustable: no car range AND not a computed gearbox field.
        _is_gearbox = f == "final_drive" or (f.startswith("gear_") and f != "gear_ratios")
        if f in _front_diff and not _is_awd:
            entries.append(FieldPlanEntry(
                f, None, FieldDisposition.NOT_RELEVANT, "front differential",
                "front diff only exists on AWD/4WD cars", "n/a", proven,
                "car drivetrain has no front differential"))
            continue
        if f not in ctx.ranges and not _is_gearbox and f not in NEUTRAL_SEEDS:
            entries.append(FieldPlanEntry(
                f, None, FieldDisposition.NOT_ADJUSTABLE, "car model",
                "the selected car exposes no adjustable range for this field", "n/a",
                proven, "no tuning range on this car"))
            continue
        if f in locked_fields:
            entries.append(FieldPlanEntry(
                f, ctx.current_setup.get(f) if ctx.current_setup else None,
                FieldDisposition.EVENT_CONSTRAINT, "event rules",
                "locked by event tuning permissions", "n/a", proven,
                "event does not allow tuning this field"))
            continue

        ch = changes_by_field.get(f)
        if ch is None:
            # Field is adjustable and unlocked but the generator produced no value
            # (e.g. absent from NEUTRAL_SEEDS) — honest insufficient-evidence marker.
            entries.append(FieldPlanEntry(
                f, setup_fields.get(f), FieldDisposition.INSUFFICIENT_EVIDENCE,
                "generator", _OBJECTIVE_GENERIC_REASON.get(objective, ""),
                "low", proven, "no deterministic value authored for this field"))
            continue

        disp = _disposition_for_change(ch, objective)
        if disp is FieldDisposition.PROVEN_HISTORY_SEED:
            seeded.append(f)
        # Objective contribution: a field-specific line when the discipline biases it,
        # otherwise the generic objective statement.
        obj_reason = _OBJECTIVE_FIELD_REASON.get(objective, {}).get(
            f, _OBJECTIVE_GENERIC_REASON.get(objective, ""))
        entries.append(FieldPlanEntry(
            field=f,
            value=ch.get("to_clamped", setup_fields.get(f)),
            disposition=disp,
            source=str(ch.get("source_label") or ch.get("rationale") or ""),
            objective_contribution=obj_reason,
            confidence=str(ch.get("confidence_level") or "low"),
            proven_value=proven,
            reason=str(ch.get("why") or ch.get("rationale") or ""),
        ))

    analysis = (
        f"{objective.value.title()} setup authored deterministically for "
        f"{_OBJECTIVE_GENERIC_REASON.get(objective, '')}. "
        + str(raw.get("analysis", ""))
    ).strip()

    return FullFieldPlan(
        objective=objective,
        session_type=session_type,
        setup_fields=setup_fields,
        entries=entries,
        analysis=analysis,
        confidence=str((raw.get("confidence") or {}).get("overall", "low")),
        seeded_from_history=seeded,
    )


def author_discipline_setups(
    make_context,
) -> dict:
    """Author Base, Qualifying and Race full-field plans from a context factory.

    ``make_context(objective) -> SetupAuthoringContext`` supplies a context per
    objective (the caller injects the right ``duration_mins`` etc.). Returns
    ``{objective_value: FullFieldPlan}`` for the three disciplines so a caller can
    prove — and render — where they genuinely differ.
    """
    out: dict = {}
    for obj in (SetupObjective.BASE, SetupObjective.QUALIFYING, SetupObjective.RACE):
        try:
            out[obj.value] = author_full_field_plan(make_context(obj))
        except Exception:
            out[obj.value] = None
    return out
