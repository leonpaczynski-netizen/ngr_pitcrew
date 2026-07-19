"""Canonical Engineering-Context Scope — Layer 1 of the Race-Engineer Activation (Program 2, Phase 36).

ONE immutable object that names *exactly* which engineering programme is being evaluated: the driver,
the car (and variant), the track, the layout, the event/programme identity, the setup discipline
(Base / Qualifying / Race), the tyre compound (or compound policy), the BoP / tuning-permitted /
power-weight restriction state, and the GT7 / rule-engine / data-schema versions plus the event
race-distance objective and tyre/fuel multipliers where materially relevant.

Every downstream activation layer (context-safe knowledge retrieval, setup-outcome learning,
driver-development, coaching, the crew brief) reasons from this ONE object so no component builds its
own partial interpretation of the facts.

Doctrine:
  * Missing context is EXPLICIT. A genuinely-unknown identity component is represented by an internal
    ``_UNKNOWN`` sentinel, NOT by an empty string that compares equal to another empty string - a
    known value and an unknown value are DIFFERENT scopes and never merge (identical semantics to the
    Phase-8 ``MemoryContextKey``).
  * The context fingerprint covers the SEMANTIC engineering identity only. Runtime / object / machine
    identity (``id()``, addresses, hostnames, usernames, filesystem paths, wall-clock, random ids) and
    accidental source-row order NEVER enter it. A different driver, car, track, layout or discipline
    can never produce the same fingerprint.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value and decides NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Tuple

ENGINEERING_CONTEXT_SCOPE_VERSION = "engineering_context_scope_v1"
ENGINEERING_CONTEXT_SCOPE_SCHEMA = 1

# a KNOWN value and an UNKNOWN value are different scopes - they must never collapse to "".
_UNKNOWN = "\x00unknown"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


class SetupDiscipline(str, Enum):
    """The engineering purpose of a setup - Base, Qualifying and Race are DIFFERENT programmes and
    their knowledge is never silently shared (Layer 4 keeps their working windows separate)."""
    BASE = "base"
    QUALIFYING = "qualifying"
    RACE = "race"
    UNKNOWN = "unknown"


# accepted spellings that normalise onto a canonical discipline.
_DISCIPLINE_ALIASES = {
    "base": SetupDiscipline.BASE, "baseline": SetupDiscipline.BASE, "practice": SetupDiscipline.BASE,
    "qualifying": SetupDiscipline.QUALIFYING, "quali": SetupDiscipline.QUALIFYING,
    "qualify": SetupDiscipline.QUALIFYING, "one_lap": SetupDiscipline.QUALIFYING,
    "race": SetupDiscipline.RACE, "stint": SetupDiscipline.RACE, "endurance": SetupDiscipline.RACE,
}


def normalise_discipline(v) -> SetupDiscipline:
    return _DISCIPLINE_ALIASES.get(_lc(v), SetupDiscipline.UNKNOWN)


class ContextCompleteness(str, Enum):
    """How completely the current context is known - drives how much a plan may lean on it."""
    COMPLETE = "complete"          # full identity + discipline + versions + compound + tuning state
    SUFFICIENT = "sufficient"      # full core identity (enough to scope a programme)
    PARTIAL = "partial"            # car+track known but core identity incomplete
    INSUFFICIENT = "insufficient"  # car or track unknown - cannot scope a programme


# Tri-state permission flags. "unknown" is preserved and is NOT the same as "permitted"/"locked".
class TriState(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


def _tri(v) -> TriState:
    if v is None or _norm(v) == "":
        return TriState.UNKNOWN
    if isinstance(v, bool):
        return TriState.YES if v else TriState.NO
    s = _lc(v)
    if s in ("yes", "true", "1", "permitted", "allowed", "on", "open"):
        return TriState.YES
    if s in ("no", "false", "0", "locked", "forbidden", "off", "fixed"):
        return TriState.NO
    return TriState.UNKNOWN


# --------------------------------------------------------------------------- #
# The canonical scope object
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EngineeringContextScope:
    """Immutable canonical statement of exactly which programme is being evaluated. Empty component =
    genuinely unknown (kept distinct from any known value in every comparison and fingerprint)."""

    # identity (semantic, fingerprint-material)
    driver: str = ""
    car: str = ""
    car_variant: str = ""
    track: str = ""
    layout_id: str = ""
    event_id: str = ""
    discipline: SetupDiscipline = SetupDiscipline.UNKNOWN
    compound: str = ""
    compound_policy: str = ""
    # regulation / restriction state
    bop_state: str = ""
    tuning_permitted: TriState = TriState.UNKNOWN
    power_restriction: str = ""
    weight_restriction: str = ""
    # versions (fingerprint-material - knowledge is version-scoped)
    gt7_version: str = ""
    rule_engine_version: str = ""
    data_schema_version: str = ""
    # event objective (materially relevant to Race gearing / strategy)
    race_objective: str = ""       # e.g. "laps:12" or "minutes:30" - free text, normalised only
    tyre_multiplier: str = ""
    fuel_multiplier: str = ""

    # the CORE identity that must be present to scope a programme at all.
    _CORE = ("driver", "car", "track", "layout_id", "discipline", "gt7_version")
    # the FULL identity considered for a "complete" grade.
    _FULL = _CORE + ("compound", "event_id", "rule_engine_version")

    def _val(self, field_name: str) -> str:
        v = getattr(self, field_name)
        if isinstance(v, SetupDiscipline):
            return v.value if v is not SetupDiscipline.UNKNOWN else ""
        return _norm(v)

    def is_known(self, field_name: str) -> bool:
        return bool(self._val(field_name))

    def missing_core(self) -> Tuple[str, ...]:
        return tuple(f for f in self._CORE if not self.is_known(f))

    def missing_fields(self) -> Tuple[str, ...]:
        return tuple(f for f in self._FULL if not self.is_known(f))

    def completeness(self) -> ContextCompleteness:
        if not self.is_known("car") or not self.is_known("track"):
            return ContextCompleteness.INSUFFICIENT
        if self.missing_core():
            return ContextCompleteness.PARTIAL
        # all core known - is the fuller identity known too?
        if not self.missing_fields():
            return ContextCompleteness.COMPLETE
        return ContextCompleteness.SUFFICIENT

    def identity_line(self) -> str:
        """Canonical identity line: every component lower-cased, unknowns kept DISTINCT via the
        sentinel so a known value never collides with an unknown one."""
        parts = []
        for f in ("driver", "car", "car_variant", "track", "layout_id", "event_id"):
            v = _lc(getattr(self, f))
            parts.append(v if v else _UNKNOWN)
        parts.append(self.discipline.value)
        for f in ("compound", "compound_policy", "bop_state"):
            v = _lc(getattr(self, f))
            parts.append(v if v else _UNKNOWN)
        parts.append(self.tuning_permitted.value)
        for f in ("power_restriction", "weight_restriction", "gt7_version",
                  "rule_engine_version", "data_schema_version", "race_objective",
                  "tyre_multiplier", "fuel_multiplier"):
            v = _lc(getattr(self, f))
            parts.append(v if v else _UNKNOWN)
        return "|".join(parts)

    def context_fingerprint(self) -> str:
        digest = hashlib.sha256(self.identity_line().encode("utf-8")).hexdigest()[:24]
        return f"{ENGINEERING_CONTEXT_SCOPE_VERSION}:ctx:{digest}"

    def label(self) -> str:
        bits = [b for b in (self.car, self.car_variant, self.track, self.layout_id,
                            self.discipline.value if self.discipline is not SetupDiscipline.UNKNOWN
                            else "", self.compound) if b]
        return " / ".join(bits) if bits else "unknown context"

    def compatibility_key(self) -> dict:
        """The Phase-22/23 compatibility identity subset (car + discipline + gt7_version + driver +
        compound) used to compare against evidence groups."""
        return {"car": _lc(self.car), "discipline": self.discipline.value,
                "gt7_version": _lc(self.gt7_version), "driver": _lc(self.driver),
                "compound": _lc(self.compound)}

    def to_dict(self) -> dict:
        return {
            "driver": self.driver, "car": self.car, "car_variant": self.car_variant,
            "track": self.track, "layout_id": self.layout_id, "event_id": self.event_id,
            "discipline": self.discipline.value, "compound": self.compound,
            "compound_policy": self.compound_policy, "bop_state": self.bop_state,
            "tuning_permitted": self.tuning_permitted.value,
            "power_restriction": self.power_restriction,
            "weight_restriction": self.weight_restriction, "gt7_version": self.gt7_version,
            "rule_engine_version": self.rule_engine_version,
            "data_schema_version": self.data_schema_version, "race_objective": self.race_objective,
            "tyre_multiplier": self.tyre_multiplier, "fuel_multiplier": self.fuel_multiplier,
            "label": self.label(), "compatibility_key": self.compatibility_key(),
            "completeness": self.completeness().value,
            "missing_core": list(self.missing_core()), "missing_fields": list(self.missing_fields()),
            "context_fingerprint": self.context_fingerprint(),
            "schema_version": ENGINEERING_CONTEXT_SCOPE_SCHEMA,
            "eval_version": ENGINEERING_CONTEXT_SCOPE_VERSION}


def build_engineering_context_scope(context: Optional[Mapping]) -> EngineeringContextScope:
    """Build the canonical scope from a loosely-shaped context mapping (as assembled by SessionDB from
    the Phase-22 programme primary key + session identity). Deterministic; never raises. Unknown
    components stay unknown - they are never invented."""
    try:
        c = context if isinstance(context, Mapping) else {}
        prog = c.get("programme") if isinstance(c.get("programme"), Mapping) else {}

        def pick(*keys) -> str:
            for k in keys:
                for src in (c, prog):
                    if isinstance(src, Mapping) and _norm(src.get(k)):
                        return _norm(src.get(k))
            return ""

        return EngineeringContextScope(
            driver=pick("driver"), car=pick("car"), car_variant=pick("car_variant", "variant"),
            track=pick("track"), layout_id=pick("layout_id", "layout"),
            event_id=pick("event_id", "event", "programme_id"),
            discipline=normalise_discipline(pick("discipline", "purpose")),
            compound=pick("compound"), compound_policy=pick("compound_policy", "tyre_policy"),
            bop_state=pick("bop_state", "bop"),
            tuning_permitted=_tri(c.get("tuning_permitted", prog.get("tuning_permitted"))),
            power_restriction=pick("power_restriction", "power"),
            weight_restriction=pick("weight_restriction", "weight"),
            gt7_version=pick("gt7_version"), rule_engine_version=pick("rule_engine_version"),
            data_schema_version=pick("data_schema_version", "db_schema_version"),
            race_objective=pick("race_objective", "race_distance", "duration"),
            tyre_multiplier=pick("tyre_multiplier", "tyre_wear_multiplier"),
            fuel_multiplier=pick("fuel_multiplier", "fuel_consumption_multiplier"))
    except Exception:  # pragma: no cover - defensive; never raise into the caller
        return EngineeringContextScope()


# --------------------------------------------------------------------------- #
# Compatibility between the current scope and an evidence context
# --------------------------------------------------------------------------- #
class ContextRelation(str, Enum):
    EXACT = "exact"                      # same driver+car+track+layout+discipline+compound+version
    SAME_PROGRAMME_OTHER_DISCIPLINE = "same_programme_other_discipline"
    SAME_CAR_OTHER_TRACK = "same_car_other_track"
    SAME_DRIVER_OTHER_CAR = "same_driver_other_car"
    DIFFERENT_VERSION = "different_version"
    UNRELATED = "unrelated"
    UNVERIFIABLE = "unverifiable"        # not enough identity on one side to compare


def _eq_known(a: str, b: str) -> bool:
    """Two components are equal ONLY when both are known and identical. Unknown never matches."""
    a, b = _lc(a), _lc(b)
    return bool(a) and bool(b) and a == b


def relate_context(scope: EngineeringContextScope, evidence_ctx: Optional[Mapping]) -> ContextRelation:
    """Classify how an evidence context relates to the current scope. Same driver OR same car ALONE is
    never EXACT - exact requires the full identity to match. Deterministic; never raises."""
    e = evidence_ctx if isinstance(evidence_ctx, Mapping) else {}
    car = _norm(e.get("car"))
    track = _norm(e.get("track"))
    if not (scope.is_known("car") and car) and not (scope.is_known("track") and track):
        return ContextRelation.UNVERIFIABLE
    same_car = _eq_known(scope.car, car)
    same_track = _eq_known(scope.track, track)
    same_layout = _eq_known(scope.layout_id, e.get("layout_id"))
    same_driver = _eq_known(scope.driver, e.get("driver"))
    same_disc = _eq_known(scope.discipline.value, e.get("discipline"))
    same_ver = _eq_known(scope.gt7_version, e.get("gt7_version"))
    same_compound = _eq_known(scope.compound, e.get("compound"))

    if (same_car and same_track and same_layout and same_driver and same_disc
            and same_ver and same_compound):
        return ContextRelation.EXACT
    if same_car and same_track and same_layout and same_driver and same_ver and not same_disc:
        return ContextRelation.SAME_PROGRAMME_OTHER_DISCIPLINE
    if same_car and same_ver and not same_track:
        return ContextRelation.SAME_CAR_OTHER_TRACK
    if same_car and same_track and not same_ver and scope.is_known("gt7_version") \
            and _norm(e.get("gt7_version")):
        return ContextRelation.DIFFERENT_VERSION
    if same_driver and not same_car:
        return ContextRelation.SAME_DRIVER_OTHER_CAR
    return ContextRelation.UNRELATED


def scope_versions() -> dict:
    return {"engineering_context_scope": ENGINEERING_CONTEXT_SCOPE_VERSION,
            "schema": ENGINEERING_CONTEXT_SCOPE_SCHEMA}
