"""EngineeringContextKey — the canonical engineering identity spine (Phase 1).

Why this module exists
----------------------
NGR Pit Crew is a deterministic, offline, evidence-gated GT7 race-engineering
system. Its core engineering context is::

    this driver + this car + this track + this layout + this event
    + this discipline + this GT7 version + this applied setup
    + this setup lineage + this telemetry session and run

Historically the app grew several *incompatible* identity systems: sessions and
strategy records key on ``config_id`` (a 10-char match key), engineering/track
records key on ``layout_id`` / ``track_location_id``, and some track fields are
free text. Applied setups, setup lineage, lap records, driver feedback and
per-corner evidence do **not** all share one joinable engineering context, which
blocks reliable cross-session learning and honest before/after setup comparison.

This module is the **single owner of canonical engineering identity**. It is a
PURE, typed, deterministic value object plus resolvers — no PyQt, no DB, no
network, no generative AI, and it never raises out of a resolver.

Honesty contract
----------------
Unknown identity information stays explicitly unknown (a field is ``None``, never
a manufactured placeholder that looks authoritative). Two records are NEVER
joined merely because two free-text names look similar. Ambiguity is reported,
not resolved by guessing.

Two identifiers
---------------
* :meth:`EngineeringContextKey.fingerprint` — the FULL identity fingerprint over
  every component (driver…run). Enriching a partial context, or changing any
  material component, produces a different full fingerprint.
* :meth:`EngineeringContextKey.scope_fingerprint` — the STABLE physical-scope
  join key over ``(driver, car, track_location, layout, gt7_version)`` only. All
  records for the same driver/car/track/layout/physics share it regardless of
  which session, run, setup or discipline they belong to. This is the key future
  setup experiments and outcomes join on for before/after comparison.

Both are versioned by :data:`FINGERPRINT_VERSION` so the algorithm can evolve
without silently re-keying stored joins.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping, Optional, Tuple


# --------------------------------------------------------------------------- #
# Versioning
# --------------------------------------------------------------------------- #
# Bump ONLY when the canonical serialization or field set changes. Stored
# fingerprints carry this prefix so old joins are never silently re-keyed.
FINGERPRINT_VERSION = "eck_v1"

# Canonical order of the FULL identity fingerprint. Fixed forever for v1.
_FULL_FIELDS: Tuple[str, ...] = (
    "driver_id",
    "car_id",
    "track_location_id",
    "layout_id",
    "event_id",
    "discipline",
    "gt7_version",
    "config_id",
    "setup_id",
    "applied_checkpoint_id",
    "lineage_id",
    "session_id",
    "run_id",
)

# The stable physical-scope join key: who + what + where + which physics.
# Deliberately EXCLUDES event/discipline/config/setup/session/run so that a
# telemetry session, an applied-setup checkpoint and a driver-feedback record
# taken on the same car/track/layout resolve to the SAME scope even though their
# volatile components differ.
_SCOPE_FIELDS: Tuple[str, ...] = (
    "driver_id",
    "car_id",
    "track_location_id",
    "layout_id",
    "gt7_version",
)

# Serialization sentinels. A KNOWN empty string ("") and an UNKNOWN field (None)
# MUST serialize differently, else "known-but-blank" would collide with
# "genuinely unknown". "\x00" cannot appear in the normal string inputs.
_UNKNOWN_TOKEN = "\x00∅"      # field is genuinely unresolved / unavailable
_KNOWN_PREFIX = "§"           # marks a known value (even if it is "")


# --------------------------------------------------------------------------- #
# Resolution status + provenance
# --------------------------------------------------------------------------- #
class ResolutionStatus(str, Enum):
    """How well a source record resolved to a canonical engineering context."""

    COMPLETE = "complete"        # every scope component resolved from evidence
    PARTIAL = "partial"          # some scope components genuinely unknown
    AMBIGUOUS = "ambiguous"      # a component had >1 candidate; NOT guessed
    UNRESOLVED = "unresolved"    # no usable identity evidence at all
    INVALID = "invalid"          # the source record was malformed / unusable


class ProvenanceSource(str, Enum):
    """Where a resolved component's value came from (recorded per field)."""

    SESSION_ROW = "session_row"
    APPLIED_CHECKPOINT = "applied_checkpoint"
    SETUP_LINEAGE = "setup_lineage"
    DRIVER_FEEDBACK = "driver_feedback"
    RECOMMENDATION = "recommendation"
    WORKING_CONFIG = "working_config"
    EVENT_CONTEXT = "event_context"
    TRACK_LIBRARY = "track_library"
    CALLER = "caller"            # supplied explicitly by the integration caller
    DERIVED = "derived"          # deterministically derived from another field


# --------------------------------------------------------------------------- #
# The canonical identity value object
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EngineeringContextKey:
    """Immutable canonical engineering identity.

    Every component is ``Optional[str]``: ``None`` means *genuinely unknown /
    unavailable* (never guessed), a string means *known* (normalised). IDs that
    are naturally integers (car_id, session_id, …) are stored as their decimal
    string so the whole key is one uniform, hashable, JSON-safe shape.
    """

    driver_id: Optional[str] = None
    car_id: Optional[str] = None
    track_location_id: Optional[str] = None
    layout_id: Optional[str] = None
    event_id: Optional[str] = None
    discipline: Optional[str] = None          # session objective (race/quali/practice/base…)
    gt7_version: Optional[str] = None          # physics / game version identity
    config_id: Optional[str] = None            # COMPATIBILITY match key (never recalculated here)
    setup_id: Optional[str] = None
    applied_checkpoint_id: Optional[str] = None
    lineage_id: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None

    # -- serialization ----------------------------------------------------- #
    def _canonical_line(self, fields: Tuple[str, ...]) -> str:
        parts = []
        for name in fields:
            value = getattr(self, name)
            if value is None:
                parts.append(f"{name}={_UNKNOWN_TOKEN}")
            else:
                parts.append(f"{name}={_KNOWN_PREFIX}{value}")
        return "\n".join(parts)

    def _digest(self, fields: Tuple[str, ...]) -> str:
        raw = self._canonical_line(fields).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def fingerprint(self) -> str:
        """The FULL identity fingerprint (all components), versioned.

        Deterministic: the same known/unknown component set always yields the
        same value. Any material change (or enrichment of a previously-unknown
        field) yields a different value.
        """
        return f"{FINGERPRINT_VERSION}:{self._digest(_FULL_FIELDS)}"

    def scope_fingerprint(self) -> str:
        """The STABLE physical-scope join key, versioned.

        Over (driver, car, track_location, layout, gt7_version) only — invariant
        to session/run/setup/discipline. Future joins for before/after setup
        comparison key on this.
        """
        return f"{FINGERPRINT_VERSION}:scope:{self._digest(_SCOPE_FIELDS)}"

    # -- introspection ----------------------------------------------------- #
    @property
    def known_fields(self) -> Tuple[str, ...]:
        return tuple(n for n in _FULL_FIELDS if getattr(self, n) is not None)

    @property
    def unknown_fields(self) -> Tuple[str, ...]:
        return tuple(n for n in _FULL_FIELDS if getattr(self, n) is None)

    @property
    def scope_complete(self) -> bool:
        """True when every physical-scope component is known."""
        return all(getattr(self, n) is not None for n in _SCOPE_FIELDS)

    def to_dict(self) -> dict:
        return {n: getattr(self, n) for n in _FULL_FIELDS}

    # -- enrichment (requirement 11: enrich without contradictory duplicate) - #
    def enrich(
        self, other: "EngineeringContextKey"
    ) -> Tuple["EngineeringContextKey", Tuple[str, ...]]:
        """Return (enriched_key, conflicting_fields).

        Fills THIS key's unknown fields from ``other`` where ``other`` knows
        them. A field known in BOTH with DIFFERENT values is a *conflict*: it is
        left unchanged (this key wins) and its name is reported — the caller
        decides. Fields never silently overwrite an existing known value, so
        enrichment can only ever ADD identity, never invent a contradictory
        duplicate.
        """
        updates = {}
        conflicts = []
        for name in _FULL_FIELDS:
            mine = getattr(self, name)
            theirs = getattr(other, name)
            if theirs is None:
                continue
            if mine is None:
                updates[name] = theirs
            elif mine != theirs:
                conflicts.append(name)
        enriched = replace(self, **updates) if updates else self
        return enriched, tuple(conflicts)


# --------------------------------------------------------------------------- #
# Structured resolution result
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EngineeringContextResolution:
    """The full, structured outcome of resolving a source record.

    Carries far more than an id: the canonical context, a completeness verdict,
    per-field provenance, the fields that stayed unknown or were ambiguous, any
    compatibility warnings, and the fingerprint-algorithm version used.
    """

    context: EngineeringContextKey
    status: ResolutionStatus
    provenance: Mapping[str, str] = field(default_factory=dict)
    unresolved: Tuple[str, ...] = ()
    ambiguous: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    fingerprint_version: str = FINGERPRINT_VERSION

    @property
    def fingerprint(self) -> str:
        return self.context.fingerprint()

    @property
    def scope_fingerprint(self) -> str:
        return self.context.scope_fingerprint()

    def to_dict(self) -> dict:
        return {
            "context": self.context.to_dict(),
            "fingerprint": self.fingerprint,
            "scope_fingerprint": self.scope_fingerprint,
            "status": self.status.value,
            "provenance": dict(self.provenance),
            "unresolved": list(self.unresolved),
            "ambiguous": list(self.ambiguous),
            "warnings": list(self.warnings),
            "fingerprint_version": self.fingerprint_version,
        }


# --------------------------------------------------------------------------- #
# Normalisation helpers (pure)
# --------------------------------------------------------------------------- #
def _norm(value) -> Optional[str]:
    """Normalise a component value to a known string or None (unknown).

    None / "" / whitespace-only / a zero-ish sentinel is treated as UNKNOWN so a
    default 0 id or blank string never masquerades as authoritative identity.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    # numeric ids: 0 is the app's "unset" sentinel across the schema.
    try:
        if isinstance(value, bool):  # guard bool-is-int
            return None
        n = int(value)
        return str(n) if n != 0 else None
    except (TypeError, ValueError):
        s = str(value).strip()
        return s if s else None


def _status_for(
    ctx: EngineeringContextKey,
    *,
    ambiguous: Tuple[str, ...],
    had_any_evidence: bool,
) -> ResolutionStatus:
    if not had_any_evidence:
        return ResolutionStatus.UNRESOLVED
    if ambiguous:
        return ResolutionStatus.AMBIGUOUS
    if ctx.scope_complete:
        return ResolutionStatus.COMPLETE
    if ctx.known_fields:
        return ResolutionStatus.PARTIAL
    return ResolutionStatus.UNRESOLVED


def _resolve_layout(
    track_location_id,
    layout_id,
    free_text_track,
    layout_candidates: Optional[Tuple[str, ...]],
    provenance: dict,
    warnings: list,
    ambiguous: list,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve track/layout identity honestly.

    * An explicit ``layout_id`` / ``track_location_id`` is authoritative.
    * A free-text track alone NEVER invents a layout id. If ``layout_candidates``
      is supplied and contains exactly one entry, that single unambiguous match
      resolves the layout; >1 candidates marks the field AMBIGUOUS (never
      guessed); 0 candidates leaves it unknown with a compatibility warning.
    """
    loc = _norm(track_location_id)
    lay = _norm(layout_id)
    if loc is not None:
        provenance["track_location_id"] = ProvenanceSource.CALLER.value
    if lay is not None:
        provenance["layout_id"] = ProvenanceSource.CALLER.value

    ft = _norm(free_text_track)
    if lay is None and ft is not None:
        cands = tuple(c for c in (layout_candidates or ()) if _norm(c))
        if len(cands) == 1:
            lay = _norm(cands[0])
            provenance["layout_id"] = ProvenanceSource.TRACK_LIBRARY.value
            warnings.append(
                f"layout_id resolved from free-text track {ft!r} via a single "
                "track-library candidate")
        elif len(cands) > 1:
            ambiguous.append("layout_id")
            warnings.append(
                f"free-text track {ft!r} matched {len(cands)} candidate layouts "
                "— left unresolved (never guessed)")
        else:
            warnings.append(
                f"free-text track {ft!r} present but layout_id unresolved "
                "(no track-library match) — physical scope stays partial")
    return loc, lay


# --------------------------------------------------------------------------- #
# Resolvers — pure functions over plain records (no DB / Qt / AI)
# --------------------------------------------------------------------------- #
def build_engineering_context(
    *,
    driver_id=None,
    car_id=None,
    track_location_id=None,
    layout_id=None,
    free_text_track=None,
    event_id=None,
    discipline=None,
    gt7_version=None,
    config_id=None,
    setup_id=None,
    applied_checkpoint_id=None,
    lineage_id=None,
    session_id=None,
    run_id=None,
    layout_candidates: Optional[Tuple[str, ...]] = None,
    provenance: Optional[Mapping[str, str]] = None,
) -> EngineeringContextResolution:
    """General deterministic builder. All inputs optional; unknowns stay unknown.

    ``provenance`` optionally seeds per-field source labels (component name ->
    :class:`ProvenanceSource` value); the resolver fills in the rest it can prove.
    """
    prov: dict = dict(provenance or {})
    warnings: list = []
    ambiguous: list = []

    loc, lay = _resolve_layout(
        track_location_id, layout_id, free_text_track,
        layout_candidates, prov, warnings, ambiguous)

    fields = {
        "driver_id": _norm(driver_id),
        "car_id": _norm(car_id),
        "track_location_id": loc,
        "layout_id": lay,
        "event_id": _norm(event_id),
        "discipline": _norm(discipline),
        "gt7_version": _norm(gt7_version),
        "config_id": _norm(config_id),
        "setup_id": _norm(setup_id),
        "applied_checkpoint_id": _norm(applied_checkpoint_id),
        "lineage_id": _norm(lineage_id),
        "session_id": _norm(session_id),
        "run_id": _norm(run_id),
    }
    ctx = EngineeringContextKey(**fields)

    # Default provenance = CALLER for any known field the caller didn't label
    # (layout/track already labelled inside _resolve_layout).
    for name, value in fields.items():
        if value is not None and name not in prov:
            prov[name] = ProvenanceSource.CALLER.value

    unresolved = ctx.unknown_fields
    had_any = bool(ctx.known_fields) or bool(ambiguous)
    status = _status_for(ctx, ambiguous=tuple(ambiguous), had_any_evidence=had_any)

    return EngineeringContextResolution(
        context=ctx,
        status=status,
        provenance=prov,
        unresolved=unresolved,
        ambiguous=tuple(ambiguous),
        warnings=tuple(warnings),
    )


def resolve_from_session_row(
    row: Mapping,
    *,
    driver_id=None,
    layout_id=None,
    gt7_version=None,
    layout_candidates: Optional[Tuple[str, ...]] = None,
) -> EngineeringContextResolution:
    """Resolve a ``sessions`` table row (dict-like) to a canonical context.

    The sessions row carries car_id, free-text track, config_id, event_id and
    session_type (the discipline). track_location_id/layout_id are NOT stored on
    sessions, so they stay unknown unless the caller supplies them (or an
    unambiguous track-library candidate resolves the layout).
    """
    if not isinstance(row, Mapping):
        return _invalid("session row is not a mapping")
    prov = {
        "car_id": ProvenanceSource.SESSION_ROW.value,
        "config_id": ProvenanceSource.SESSION_ROW.value,
        "event_id": ProvenanceSource.SESSION_ROW.value,
        "discipline": ProvenanceSource.SESSION_ROW.value,
        "session_id": ProvenanceSource.SESSION_ROW.value,
    }
    return build_engineering_context(
        driver_id=driver_id,
        car_id=row.get("car_id"),
        free_text_track=row.get("track"),
        layout_id=layout_id,
        event_id=row.get("event_id"),
        discipline=row.get("session_type"),
        gt7_version=gt7_version,
        config_id=row.get("config_id"),
        session_id=row.get("id"),
        layout_candidates=layout_candidates,
        provenance=prov,
    )


def resolve_from_applied_checkpoint(
    row: Mapping,
    *,
    driver_id=None,
    gt7_version=None,
    session_id=None,
    config_id=None,
) -> EngineeringContextResolution:
    """Resolve an ``applied_setup_checkpoints`` row to a canonical context.

    Checkpoints DO carry car_id + free-text track + layout_id + purpose (the
    discipline) + setup_id + checkpoint_id, so their physical scope is usually
    complete when a layout_id was recorded.
    """
    if not isinstance(row, Mapping):
        return _invalid("applied-checkpoint row is not a mapping")
    prov = {
        "car_id": ProvenanceSource.APPLIED_CHECKPOINT.value,
        "discipline": ProvenanceSource.APPLIED_CHECKPOINT.value,
        "setup_id": ProvenanceSource.APPLIED_CHECKPOINT.value,
        "applied_checkpoint_id": ProvenanceSource.APPLIED_CHECKPOINT.value,
    }
    return build_engineering_context(
        driver_id=driver_id,
        car_id=row.get("car_id"),
        free_text_track=row.get("track"),
        layout_id=row.get("layout_id"),
        discipline=row.get("purpose"),
        gt7_version=gt7_version,
        config_id=config_id,
        setup_id=row.get("setup_id"),
        applied_checkpoint_id=row.get("checkpoint_id") or row.get("id"),
        session_id=session_id,
        provenance=prov,
    )


def resolve_from_lineage(
    row: Mapping,
    *,
    driver_id=None,
    gt7_version=None,
    config_id=None,
) -> EngineeringContextResolution:
    """Resolve a ``setup_lineage`` row to a canonical context."""
    if not isinstance(row, Mapping):
        return _invalid("lineage row is not a mapping")
    prov = {
        "car_id": ProvenanceSource.SETUP_LINEAGE.value,
        "discipline": ProvenanceSource.SETUP_LINEAGE.value,
        "lineage_id": ProvenanceSource.SETUP_LINEAGE.value,
        "session_id": ProvenanceSource.SETUP_LINEAGE.value,
    }
    return build_engineering_context(
        driver_id=driver_id,
        car_id=row.get("car_id"),
        free_text_track=row.get("track"),
        layout_id=row.get("layout_id"),
        discipline=row.get("objective"),
        gt7_version=gt7_version,
        config_id=config_id,
        lineage_id=row.get("id"),
        session_id=row.get("session_id"),
        provenance=prov,
    )


def resolve_from_driver_feedback(
    row: Mapping,
    *,
    session_row: Optional[Mapping] = None,
    driver_id=None,
    layout_id=None,
    gt7_version=None,
    layout_candidates: Optional[Tuple[str, ...]] = None,
) -> EngineeringContextResolution:
    """Resolve a ``driver_feedback`` row to a canonical context.

    Feedback rows store session_id, config_id and setup_id but NOT car/track;
    those come from the joined ``session_row`` when provided, so the feedback
    resolves to the SAME session/setup scope without any free-text coincidence.
    """
    if not isinstance(row, Mapping):
        return _invalid("driver-feedback row is not a mapping")
    sess = session_row if isinstance(session_row, Mapping) else {}
    prov = {
        "config_id": ProvenanceSource.DRIVER_FEEDBACK.value,
        "setup_id": ProvenanceSource.DRIVER_FEEDBACK.value,
        "session_id": ProvenanceSource.DRIVER_FEEDBACK.value,
        "car_id": ProvenanceSource.SESSION_ROW.value,
        "discipline": ProvenanceSource.SESSION_ROW.value,
    }
    return build_engineering_context(
        driver_id=driver_id,
        car_id=sess.get("car_id"),
        free_text_track=sess.get("track"),
        layout_id=layout_id,
        event_id=sess.get("event_id"),
        discipline=sess.get("session_type"),
        gt7_version=gt7_version,
        config_id=row.get("config_id") or sess.get("config_id"),
        setup_id=row.get("setup_id"),
        session_id=row.get("session_id") or sess.get("id"),
        layout_candidates=layout_candidates,
        provenance=prov,
    )


def engineering_context_from_stored_row(row: Mapping) -> EngineeringContextKey:
    """Rebuild an :class:`EngineeringContextKey` from a stored ``engineering_context``
    row (dict-like). Missing/blank component columns become ``None`` (unknown), so a
    round-trip preserves the known/unknown distinction. Never raises."""
    if not isinstance(row, Mapping):
        return EngineeringContextKey()
    kwargs = {}
    for name in _FULL_FIELDS:
        v = row.get(name)
        kwargs[name] = v if (v is not None and v != "") else None
    return EngineeringContextKey(**kwargs)


def resolve_feedback_against_session_context(
    session_ctx: EngineeringContextKey,
    *,
    config_id=None,
    setup_id=None,
) -> EngineeringContextResolution:
    """Resolve a driver-feedback record to the SAME context as its session.

    The feedback inherits the session's already-resolved identity (so it shares
    the session's stable ``scope_fingerprint`` — test 14), enriched with the
    feedback's own ``config_id`` / ``setup_id`` where the session left them
    unknown. Enrichment never overwrites a known session value; a contradiction
    is reported as a warning, not silently applied.
    """
    add = build_engineering_context(
        config_id=config_id, setup_id=setup_id,
        provenance={
            "config_id": ProvenanceSource.DRIVER_FEEDBACK.value,
            "setup_id": ProvenanceSource.DRIVER_FEEDBACK.value,
        },
    ).context
    enriched, conflicts = session_ctx.enrich(add)
    warnings = []
    if conflicts:
        warnings.append(
            "feedback identity conflicts with the session context on "
            f"{', '.join(conflicts)} — session value kept")
    prov = {}
    for name in _FULL_FIELDS:
        if getattr(session_ctx, name) is not None:
            prov[name] = ProvenanceSource.SESSION_ROW.value
    if config_id is not None and getattr(session_ctx, "config_id") is None:
        prov["config_id"] = ProvenanceSource.DRIVER_FEEDBACK.value
    if setup_id is not None and getattr(session_ctx, "setup_id") is None:
        prov["setup_id"] = ProvenanceSource.DRIVER_FEEDBACK.value
    status = _status_for(
        enriched, ambiguous=(),
        had_any_evidence=bool(enriched.known_fields))
    return EngineeringContextResolution(
        context=enriched, status=status, provenance=prov,
        unresolved=enriched.unknown_fields, ambiguous=(),
        warnings=tuple(warnings))


def _invalid(reason: str) -> EngineeringContextResolution:
    return EngineeringContextResolution(
        context=EngineeringContextKey(),
        status=ResolutionStatus.INVALID,
        warnings=(reason,),
    )
