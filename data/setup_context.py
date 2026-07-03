"""SetupContext — canonical read model for the active setup recommendation.

Added by the **State Consolidation 3 — SetupContext** sprint (2026-07-03) as the
third concrete step of the target architecture proposed in
`docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§7). It follows
`data/event_context.py` (State Consolidation 1) and
`data/strategy_context.py` (State Consolidation 2) and depends on both.

Why this exists
---------------
Setup state is scattered across several stores that mix different kinds of truth:

* the manual/current setup dict (`_current_setup_dict()` in `setup_builder_ui.py`),
* saved setups in the DB (`setups` table) and legacy `config["car_setup"]["setups"]`,
* the AI setup-advice response (`build_setup_advice_response` /
  `build_combined_setup_response` — `analysis` / `changes` / `setup_fields` /
  `validation_errors` / `primary_issue` / `confidence`),
* the deterministic diagnosis (`strategy/setup_diagnosis.py`).

None of these records *which event and strategy assumptions a setup recommendation
was generated against*, so a setup can silently go stale when the event or
strategy changes underneath it. ``SetupContext`` is an immutable read model that
owns *only* setup-recommendation truth and is **keyed** to
``EventContext.change_hash`` and ``StrategyPromptSnapshot.snapshot_id``, so stale
setups become detectable.

Ownership boundary
------------------
SetupContext owns: setup id / config id, setup purpose (qualifying/race/practice/
test/unknown), setup source, the recommendation payload (analysis + adjustments +
target setup), baseline/target setup references, changed fields, reason/diagnosis
summary, confidence/validation state, applied/not-applied state, a setup change
marker, and the ``event_change_hash`` / ``strategy_snapshot_id`` /
``telemetry_diagnosis_hash`` it was built against.

It must **not** own: selected event, race type, race duration/lap count, tyre/fuel
multipliers, BoP/tuning legality, allowed setup changes (all EventContext); the
active strategy plan, stint plan, fuel burn per lap (StrategyContext); raw
telemetry packets, lap validity (Telemetry/Session context); track/corner map
geometry (a later TrackContext); AI logs; driver learning history (a later
LearningContext).

Purity
------
No PyQt6, no DB, no I/O, no network/AI — builders take plain dicts (a setup dict,
an AI recommendation dict, a diagnosis dict) plus an ``EventContext`` and a
``StrategyPromptSnapshot``. This keeps the module unit-testable without a
QApplication (the project's test convention) and free of import cycles. The
legacy setup config/DB stores are intentionally *not* deleted this sprint; they
remain as legacy compatibility.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from data.event_context import EventContext
    from data.strategy_context import StrategyPromptSnapshot


SETUP_CONTEXT_SCHEMA = "setup_context_v1"
SETUP_PROMPT_SNAPSHOT_SCHEMA = "setup_prompt_snapshot_v1"


class SetupContextSource(str, Enum):
    """Where a SetupContext was resolved from."""
    EMPTY = "empty"                  # no setup state at all
    AI = "ai"                        # AI setup-advice response (telemetry fix)
    GENERATED = "generated"          # AI from-scratch build
    MANUAL = "manual"                # user-entered manual setup
    SAVED_DB = "saved_db"            # loaded from the setups DB table
    LEGACY_CONFIG = "legacy_config"  # from config["car_setup"]["setups"]


class SetupPurpose(str, Enum):
    """What the setup is for."""
    QUALIFYING = "qualifying"
    RACE = "race"
    PRACTICE = "practice"
    TEST = "test"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Safe coercion helpers (never raise) — mirror data/event_context.py
# --------------------------------------------------------------------------- #
def _as_str(v, default: str = "") -> str:
    if v is None:
        return default
    try:
        return str(v)
    except Exception:  # pragma: no cover - defensive
        return default


def _as_int(v, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _as_opt_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _as_opt_bool(v) -> Optional[bool]:
    if v is None or v == "":
        return None
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "applied")
    try:
        return bool(v)
    except Exception:  # pragma: no cover - defensive
        return None


def normalise_purpose(v) -> SetupPurpose:
    """Map any setup-type/purpose token to a SetupPurpose.

    Accepts the UI's "Race Setup"/"Qualifying Setup", the diagnosis "practice"/
    "test", a SetupPurpose, or free text. Unknown → UNKNOWN.
    """
    if isinstance(v, SetupPurpose):
        return v
    s = _as_str(v).strip().lower()
    if not s:
        return SetupPurpose.UNKNOWN
    if "qual" in s:
        return SetupPurpose.QUALIFYING
    if "race" in s:
        return SetupPurpose.RACE
    if "practice" in s:
        return SetupPurpose.PRACTICE
    if "test" in s:
        return SetupPurpose.TEST
    return SetupPurpose.UNKNOWN


# --------------------------------------------------------------------------- #
# Freezing helpers — copy mutable setup dicts into immutable structures so a
# snapshot stays stable even if the source config/DB dict mutates later.
# --------------------------------------------------------------------------- #
def _freeze_value(v) -> Any:
    if isinstance(v, dict):
        return tuple(sorted((str(k), _freeze_value(val)) for k, val in v.items()))
    if isinstance(v, (list, tuple)):
        return tuple(_freeze_value(x) for x in v)
    return v


def _freeze_mapping(d) -> Tuple[Tuple[str, Any], ...]:
    """Deep-copy a dict into a sorted tuple of (key, frozen-value) pairs."""
    if not isinstance(d, dict):
        return ()
    return tuple(sorted((str(k), _freeze_value(v)) for k, v in d.items()))


def _thaw_value(v) -> Any:
    if isinstance(v, tuple):
        # A frozen mapping is a tuple of 2-tuples with str keys.
        if v and all(isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], str) for x in v):
            return {k: _thaw_value(val) for k, val in v}
        return [_thaw_value(x) for x in v]
    return v


def _thaw_mapping(frozen: Tuple[Tuple[str, Any], ...]) -> dict:
    """Reconstruct a plain dict from a frozen mapping."""
    return {k: _thaw_value(v) for k, v in (frozen or ())}


# --------------------------------------------------------------------------- #
# Setup adjustment entry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SetupChangeEntry:
    """One recommended setup adjustment. Mirrors the AI ``changes`` shape
    (``{setting|field, from, to, why}``)."""
    field: str
    from_value: str
    to_value: str
    why: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "from": self.from_value,
            "to": self.to_value,
            "why": self.why,
        }


def _parse_adjustments(raw) -> Tuple[SetupChangeEntry, ...]:
    """Parse an AI ``changes`` list into typed entries. Never raises."""
    if not isinstance(raw, (list, tuple)):
        return ()
    out = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        field = _as_str(d.get("field") or d.get("setting") or d.get("name"))
        if not field:
            continue
        out.append(
            SetupChangeEntry(
                field=field,
                from_value=_as_str(d.get("from", d.get("from_value", ""))),
                to_value=_as_str(d.get("to", d.get("to_value", ""))),
                why=_as_str(d.get("why", d.get("reason", ""))),
            )
        )
    return tuple(out)


# --------------------------------------------------------------------------- #
# The read model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SetupContext:
    """Immutable, normalised snapshot of the active setup recommendation."""

    # Identity
    setup_id: Optional[int]
    config_id: str
    setup_label: str

    # Classification
    purpose: SetupPurpose
    source: SetupContextSource

    # Car / track identity (the setup is FOR a car+track; it does not OWN the
    # event selection — those live in EventContext).
    car: str
    track: str
    track_location_id: str
    layout_id: str

    # Recommendation payload
    adjustments: Tuple[SetupChangeEntry, ...]
    changed_fields: Tuple[str, ...]
    baseline_setup: Tuple[Tuple[str, Any], ...]
    target_setup: Tuple[Tuple[str, Any], ...]
    reason_summary: str
    primary_issue: str
    confidence: str
    validation_warnings: Tuple[str, ...]
    applied: Optional[bool]

    # Keys / freshness markers
    change_hash: str = ""
    event_change_hash: str = ""
    strategy_snapshot_id: str = ""
    telemetry_diagnosis_hash: str = ""

    has_recommendation: bool = False
    has_setup: bool = False

    # -- convenience ------------------------------------------------------- #
    @property
    def has_active_setup(self) -> bool:
        return self.source != SetupContextSource.EMPTY

    @property
    def is_ai_generated(self) -> bool:
        return self.source in (SetupContextSource.AI, SetupContextSource.GENERATED)

    def baseline_setup_dict(self) -> dict:
        return _thaw_mapping(self.baseline_setup)

    def target_setup_dict(self) -> dict:
        return _thaw_mapping(self.target_setup)

    # -- keying / staleness ------------------------------------------------ #
    def matches_event(self, event_context: "EventContext") -> bool:
        """True when this setup was built against the given event."""
        return self.event_change_hash == _as_str(getattr(event_context, "change_hash", ""))

    def is_stale_for_event(self, event_context: "EventContext") -> bool:
        """True when a recommendation exists but the event changed under it."""
        if not self.has_active_setup:
            return False
        cur = _as_str(getattr(event_context, "change_hash", ""))
        return bool(self.event_change_hash) and bool(cur) and self.event_change_hash != cur

    def is_stale_for_strategy(self, strategy_snapshot) -> bool:
        """True when a recommendation exists but the strategy snapshot changed."""
        if not self.has_active_setup:
            return False
        cur = _as_str(getattr(strategy_snapshot, "snapshot_id", ""))
        return bool(self.strategy_snapshot_id) and bool(cur) and self.strategy_snapshot_id != cur

    def is_missing_identity(self) -> bool:
        """True when the setup lacks car or track identity."""
        return not self.car or not self.track

    def matches_purpose(self, requested) -> bool:
        """True when the setup's purpose matches a requested purpose."""
        return self.purpose == normalise_purpose(requested)

    # -- display ----------------------------------------------------------- #
    def summary_line(self) -> str:
        if not self.has_active_setup:
            return "No setup recommendation"
        label = self.setup_label or "(unnamed)"
        car = self.car or "—"
        n = len(self.adjustments)
        chg = f"{n} change{'' if n == 1 else 's'}" if self.has_recommendation else "baseline"
        return (
            f"Setup: {label} ({self.purpose.value})  |  Car: {car}  |  "
            f"Source: {self.source.value}  |  {chg}"
        )

    def to_summary_lines(self) -> list:
        lines = [
            f"Setup: {self.setup_label or '(unnamed)'}",
            f"Purpose: {self.purpose.value}   Source: {self.source.value}",
            f"Car: {self.car or '—'}   Track: {self.track or '—'}",
        ]
        if self.has_recommendation:
            lines.append(f"Adjustments: {len(self.adjustments)}")
            if self.primary_issue:
                lines.append(f"Primary issue: {self.primary_issue}")
            if self.confidence:
                lines.append(f"Confidence: {self.confidence}")
        if self.validation_warnings:
            lines.append(f"Validation: {len(self.validation_warnings)} warning(s)")
        return lines

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        d["purpose"] = self.purpose.value
        d["adjustments"] = [a.to_dict() for a in self.adjustments]
        d["changed_fields"] = list(self.changed_fields)
        d["validation_warnings"] = list(self.validation_warnings)
        d["baseline_setup"] = self.baseline_setup_dict()
        d["target_setup"] = self.target_setup_dict()
        d["schema"] = SETUP_CONTEXT_SCHEMA
        return d


@dataclass(frozen=True)
class SetupContextValidationResult:
    """Validation result keeping setup-input problems separate from staleness
    (event/strategy drift) problems."""
    ok: bool
    setup_warnings: Tuple[str, ...] = ()
    setup_missing: Tuple[str, ...] = ()
    staleness_warnings: Tuple[str, ...] = ()

    @property
    def warnings(self) -> Tuple[str, ...]:
        return tuple(self.setup_warnings) + tuple(self.staleness_warnings)


# --------------------------------------------------------------------------- #
# Builder / adapter
# --------------------------------------------------------------------------- #
def _canonical_change_fields(**kw) -> dict:
    """The subset of fields that define whether the *setup recommendation*
    changed. Excludes provenance (source) and the hash itself; excludes event and
    strategy hashes (those are tracked separately)."""
    return {
        "setup_id": kw["setup_id"],
        "config_id": kw["config_id"],
        "setup_label": kw["setup_label"],
        "purpose": kw["purpose"].value,
        "car": kw["car"],
        "track": kw["track"],
        "track_location_id": kw["track_location_id"],
        "layout_id": kw["layout_id"],
        "adjustments": [a.to_dict() for a in kw["adjustments"]],
        "changed_fields": list(kw["changed_fields"]),
        "target_setup": list(kw["target_setup"]),
        "baseline_setup": list(kw["baseline_setup"]),
        "reason_summary": kw["reason_summary"],
        "primary_issue": kw["primary_issue"],
        "confidence": kw["confidence"],
        "validation_warnings": list(kw["validation_warnings"]),
        "applied": kw["applied"],
    }


def compute_change_hash(fields: dict) -> str:
    """Stable 12-char hash over the canonical setup fields — a change marker so
    consumers can cheaply detect that the setup recommendation changed and
    invalidate any derived snapshot. Deterministic (no time / randomness)."""
    blob = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _diagnosis_hash(diagnosis) -> str:
    if not isinstance(diagnosis, dict) or not diagnosis:
        return ""
    try:
        blob = json.dumps(diagnosis, sort_keys=True, default=str)
    except Exception:  # pragma: no cover - defensive
        return ""
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def build_setup_context(
    *,
    setup: Optional[dict] = None,
    recommendation: Optional[dict] = None,
    event_context: Optional["EventContext"] = None,
    strategy_snapshot: Optional["StrategyPromptSnapshot"] = None,
    diagnosis: Optional[dict] = None,
    purpose=None,
    source: Optional[SetupContextSource] = None,
    applied: Optional[bool] = None,
) -> SetupContext:
    """Build the canonical SetupContext from the current app state.

    Parameters
    ----------
    setup : dict | None
        The baseline / current setup dict (as produced by
        ``_current_setup_dict()`` or a DB ``setup_dict``). Supplies setup id,
        ``config_id``, label, ``setup_type`` (purpose), and the baseline fields.
    recommendation : dict | None
        An AI setup-advice response (``analysis`` / ``changes`` / ``setup_fields``
        / ``validation_errors`` / ``primary_issue`` / ``confidence``). Supplies
        the adjustment list and the target setup.
    event_context : EventContext | None
        The canonical event/race read model. Only its ``change_hash`` (and, as a
        fallback, ``car`` / ``track`` / track ids) is read — event fields are
        never copied as owned state.
    strategy_snapshot : StrategyPromptSnapshot | None
        The frozen strategy snapshot; only its ``snapshot_id`` (and, as a
        fallback, ``config_id``) is read.
    diagnosis : dict | None
        The deterministic ``setup_diagnosis`` dict; hashed into
        ``telemetry_diagnosis_hash`` and mined for optional summary / primary
        issue / confidence when the recommendation omits them.
    purpose / source / applied
        Explicit overrides.

    Never raises. Returns an EMPTY-source context when nothing is available.
    """
    setup = setup if isinstance(setup, dict) else {}
    recommendation = recommendation if isinstance(recommendation, dict) else {}
    diagnosis = diagnosis if isinstance(diagnosis, dict) else {}

    has_setup = bool(setup)
    has_recommendation = bool(recommendation.get("changes") or recommendation.get("setup_fields")
                              or recommendation.get("analysis") or recommendation.get("primary_issue"))

    # Identity
    setup_id = _as_opt_int(setup.get("setup_id") or setup.get("id"))
    config_id = _as_str(setup.get("config_id")) or _as_str(getattr(strategy_snapshot, "config_id", ""))
    setup_label = _as_str(setup.get("setup_label") or setup.get("name"))

    # Classification
    resolved_purpose = (
        normalise_purpose(purpose) if purpose is not None
        else normalise_purpose(setup.get("setup_type") or setup.get("purpose")
                               or setup.get("session"))
    )

    # Car / track identity — from the setup dict, falling back to EventContext.
    car = _as_str(setup.get("car") or setup.get("name")) or _as_str(getattr(event_context, "car", ""))
    track = _as_str(setup.get("track")) or _as_str(getattr(event_context, "track", ""))
    track_location_id = _as_str(setup.get("track_location_id")) or _as_str(getattr(event_context, "track_location_id", ""))
    layout_id = _as_str(setup.get("layout_id")) or _as_str(getattr(event_context, "layout_id", ""))

    # Recommendation payload
    adjustments = _parse_adjustments(recommendation.get("changes"))
    target_setup_dict = recommendation.get("setup_fields")
    target_setup = _freeze_mapping(target_setup_dict if isinstance(target_setup_dict, dict) else {})
    baseline_setup = _freeze_mapping(setup)

    changed = list(dict.fromkeys(  # preserve order, dedupe
        [a.field for a in adjustments]
        + ([str(k) for k in target_setup_dict.keys()] if isinstance(target_setup_dict, dict) else [])
    ))
    changed_fields = tuple(changed)

    reason_summary = (
        _as_str(recommendation.get("analysis"))
        or _as_str(diagnosis.get("summary"))
        or _as_str(diagnosis.get("dominant_problem"))
    )
    primary_issue = (
        _as_str(recommendation.get("primary_issue"))
        or _as_str(diagnosis.get("dominant_problem"))
    )
    confidence = _as_str(recommendation.get("confidence")) or _as_str(diagnosis.get("location_confidence"))

    validation_warnings = tuple(
        _as_str(w) for w in (recommendation.get("validation_errors") or []) if _as_str(w)
    )

    # Source resolution
    if source is not None:
        resolved_source = source
    elif has_recommendation:
        # A from-scratch build has no telemetry-fix baseline changes; treat an
        # explicit source override for that. Default AI-with-changes → AI.
        resolved_source = SetupContextSource.AI
    elif has_setup:
        resolved_source = (
            SetupContextSource.SAVED_DB if setup_id is not None
            else SetupContextSource.MANUAL
        )
    else:
        resolved_source = SetupContextSource.EMPTY

    event_change_hash = _as_str(getattr(event_context, "change_hash", "")) if event_context else ""
    strategy_snapshot_id = _as_str(getattr(strategy_snapshot, "snapshot_id", "")) if strategy_snapshot else ""
    telemetry_diagnosis_hash = _diagnosis_hash(diagnosis)

    canonical = _canonical_change_fields(
        setup_id=setup_id, config_id=config_id, setup_label=setup_label,
        purpose=resolved_purpose, car=car, track=track,
        track_location_id=track_location_id, layout_id=layout_id,
        adjustments=adjustments, changed_fields=changed_fields,
        target_setup=target_setup, baseline_setup=baseline_setup,
        reason_summary=reason_summary, primary_issue=primary_issue,
        confidence=confidence, validation_warnings=validation_warnings,
        applied=applied,
    )
    change_hash = "" if resolved_source == SetupContextSource.EMPTY else compute_change_hash(canonical)

    return SetupContext(
        setup_id=setup_id,
        config_id=config_id,
        setup_label=setup_label,
        purpose=resolved_purpose,
        source=resolved_source,
        car=car,
        track=track,
        track_location_id=track_location_id,
        layout_id=layout_id,
        adjustments=adjustments,
        changed_fields=changed_fields,
        baseline_setup=baseline_setup,
        target_setup=target_setup,
        reason_summary=reason_summary,
        primary_issue=primary_issue,
        confidence=confidence,
        validation_warnings=validation_warnings,
        applied=applied,
        change_hash=change_hash,
        event_change_hash=event_change_hash,
        strategy_snapshot_id=strategy_snapshot_id,
        telemetry_diagnosis_hash=telemetry_diagnosis_hash,
        has_recommendation=has_recommendation,
        has_setup=has_setup,
    )


def empty_setup_context() -> SetupContext:
    """A well-formed EMPTY context (no active setup)."""
    return build_setup_context()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_setup_context(
    ctx: SetupContext,
    event_context: Optional["EventContext"] = None,
    strategy_snapshot: Optional["StrategyPromptSnapshot"] = None,
    requested_purpose=None,
) -> SetupContextValidationResult:
    """Return non-crashing validation warnings, keeping setup-input problems
    separate from staleness (event/strategy drift) problems.

    Missing optional fields produce warnings, never exceptions. When
    ``event_context`` / ``strategy_snapshot`` are supplied, drift is reported in
    ``staleness_warnings``. When ``requested_purpose`` is supplied, a
    purpose mismatch is reported.
    """
    setup_warnings = []
    setup_missing = []
    staleness_warnings = []

    if ctx.source == SetupContextSource.EMPTY:
        setup_warnings.append("No setup — build or load one in Setup Builder.")
        setup_missing.append("setup")
    else:
        if ctx.is_missing_identity():
            if not ctx.car:
                setup_warnings.append("Setup has no car identity.")
                setup_missing.append("car")
            if not ctx.track:
                setup_warnings.append("Setup has no track identity.")
                setup_missing.append("track")
        if ctx.purpose == SetupPurpose.UNKNOWN:
            setup_warnings.append("Setup purpose is unknown (qualifying/race not set).")
            setup_missing.append("purpose")

    if requested_purpose is not None and ctx.has_active_setup:
        if not ctx.matches_purpose(requested_purpose):
            staleness_warnings.append(
                f"Setup was built for {ctx.purpose.value}, but a "
                f"{normalise_purpose(requested_purpose).value} setup was requested."
            )

    if event_context is not None and ctx.is_stale_for_event(event_context):
        staleness_warnings.append(
            "Setup is stale — the event configuration changed after it was built."
        )
    if strategy_snapshot is not None and ctx.is_stale_for_strategy(strategy_snapshot):
        staleness_warnings.append(
            "Setup is stale — the strategy plan changed after it was built."
        )

    ok = not setup_warnings and not staleness_warnings
    return SetupContextValidationResult(
        ok=ok,
        setup_warnings=tuple(setup_warnings),
        setup_missing=tuple(setup_missing),
        staleness_warnings=tuple(staleness_warnings),
    )


# --------------------------------------------------------------------------- #
# Frozen prompt snapshot (EventContext + StrategyPromptSnapshot + SetupContext)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SetupPromptSnapshot:
    """An immutable, value-copied snapshot combining the setup recommendation
    (from SetupContext) with the event + strategy keys it was built against, for
    AI setup-prompt construction.

    Every field is a copied primitive or a frozen tuple, so the snapshot stays
    stable even if the source setup dict / config is mutated after it is built —
    the whole point is to stop a prompt from mixing stale and fresh state. This
    type exists so a *future* AI-setup-prompt migration can freeze a consistent
    context; the high-risk prompt paths are **not** migrated this sprint.
    """
    schema: str

    # Identity — combined marker so equal event+strategy+setup state → equal id.
    snapshot_id: str
    event_change_hash: str
    strategy_snapshot_id: str
    setup_change_hash: str
    telemetry_diagnosis_hash: str

    # Setup recommendation (copied from SetupContext)
    setup_id: Optional[int]
    config_id: str
    setup_label: str
    purpose: str
    source: str
    car: str
    track: str
    track_location_id: str
    layout_id: str
    adjustments: Tuple[SetupChangeEntry, ...]
    changed_fields: Tuple[str, ...]
    baseline_setup: Tuple[Tuple[str, Any], ...]
    target_setup: Tuple[Tuple[str, Any], ...]
    reason_summary: str
    primary_issue: str
    confidence: str
    validation_warnings: Tuple[str, ...]
    applied: Optional[bool]

    def baseline_setup_dict(self) -> dict:
        return _thaw_mapping(self.baseline_setup)

    def target_setup_dict(self) -> dict:
        return _thaw_mapping(self.target_setup)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["adjustments"] = [a.to_dict() for a in self.adjustments]
        d["changed_fields"] = list(self.changed_fields)
        d["validation_warnings"] = list(self.validation_warnings)
        d["baseline_setup"] = self.baseline_setup_dict()
        d["target_setup"] = self.target_setup_dict()
        return d


def build_setup_prompt_snapshot(setup_context: SetupContext) -> SetupPromptSnapshot:
    """Freeze a SetupContext (with its event/strategy keys) into one snapshot.

    ``snapshot_id`` is a stable hash of the event + strategy + setup change
    markers, so equal state yields an equal id and any drift changes it.
    """
    snapshot_id = compute_change_hash({
        "event": setup_context.event_change_hash,
        "strategy": setup_context.strategy_snapshot_id,
        "setup": setup_context.change_hash,
        "diagnosis": setup_context.telemetry_diagnosis_hash,
    })
    return SetupPromptSnapshot(
        schema=SETUP_PROMPT_SNAPSHOT_SCHEMA,
        snapshot_id=snapshot_id,
        event_change_hash=setup_context.event_change_hash,
        strategy_snapshot_id=setup_context.strategy_snapshot_id,
        setup_change_hash=setup_context.change_hash,
        telemetry_diagnosis_hash=setup_context.telemetry_diagnosis_hash,
        setup_id=setup_context.setup_id,
        config_id=setup_context.config_id,
        setup_label=setup_context.setup_label,
        purpose=setup_context.purpose.value,
        source=setup_context.source.value,
        car=setup_context.car,
        track=setup_context.track,
        track_location_id=setup_context.track_location_id,
        layout_id=setup_context.layout_id,
        adjustments=setup_context.adjustments,
        changed_fields=setup_context.changed_fields,
        baseline_setup=setup_context.baseline_setup,
        target_setup=setup_context.target_setup,
        reason_summary=setup_context.reason_summary,
        primary_issue=setup_context.primary_issue,
        confidence=setup_context.confidence,
        validation_warnings=setup_context.validation_warnings,
        applied=setup_context.applied,
    )
