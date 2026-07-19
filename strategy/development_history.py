"""Immutable cross-session engineering development history (Engineering Brain Phase 8).

One completed engineering review (a persisted, canonical Phase-3 outcome) becomes ONE
immutable ``DevelopmentRecord``. A ``DevelopmentHistory`` is the chronological,
never-rewritten sequence of those records for a single engineering context. This is the
permanent record the higher layers (`engineering_memory`, `progress_metrics`) fold over.

Doctrine (identical to the rest of the Engineering Brain):
  * Phase 8 sits ABOVE Phases 1-7. It makes NO engineering decision, authors no setup
    value, evaluates no lap, and never re-runs an outcome. It only re-projects
    already-authoritative engineering evidence into a durable, comparable shape.
  * Memory is keyed by the FULL engineering context (driver, car, track, layout,
    discipline, gt7 version, tyre compound) — incompatible contexts NEVER mix.
  * History is immutable and append-only: a record is never rewritten or deleted, and
    the same review re-recorded yields the SAME ``record_key`` (idempotent).
  * Identity never depends on display text (reuses Phase 6 issue identity semantics).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock (timestamps are passed in as data, never read from the clock).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

DEVELOPMENT_HISTORY_VERSION = "development_history_v1"

_UNKNOWN = "\x00unknown"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


# --------------------------------------------------------------------------- #
# Memory context key — the permanent-memory scope. Never mixes incompatible ctx.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MemoryContextKey:
    """The full engineering-memory scope. Empty component = genuinely unknown (a
    known value and an unknown value are DIFFERENT scopes — they never merge)."""

    driver: str = ""
    car: str = ""
    track: str = ""
    layout_id: str = ""
    discipline: str = ""
    gt7_version: str = ""
    compound: str = ""

    def _line(self) -> str:
        return "|".join(
            (v if v else _UNKNOWN) for v in (
                _lc(self.driver), _lc(self.car), _lc(self.track), _lc(self.layout_id),
                _lc(self.discipline), _lc(self.gt7_version), _lc(self.compound)))

    def key(self) -> str:
        digest = hashlib.sha256(self._line().encode("utf-8")).hexdigest()[:20]
        return f"{DEVELOPMENT_HISTORY_VERSION}:ctx:{digest}"

    def label(self) -> str:
        parts = [p for p in (self.car, self.track, self.layout_id, self.discipline,
                             self.compound) if p]
        return " · ".join(parts) if parts else "unknown context"

    def to_dict(self) -> dict:
        return {"driver": self.driver, "car": self.car, "track": self.track,
                "layout_id": self.layout_id, "discipline": self.discipline,
                "gt7_version": self.gt7_version, "compound": self.compound,
                "key": self.key(), "label": self.label()}

    @classmethod
    def from_dict(cls, d: Mapping) -> "MemoryContextKey":
        d = d or {}
        return cls(driver=_norm(d.get("driver")), car=_norm(d.get("car")),
                   track=_norm(d.get("track")), layout_id=_norm(d.get("layout_id")),
                   discipline=_norm(d.get("discipline")),
                   gt7_version=_norm(d.get("gt7_version")),
                   compound=_norm(d.get("compound")))


# --------------------------------------------------------------------------- #
# Protected-knowledge constraint types (things that must never be forgotten)
# --------------------------------------------------------------------------- #
class ConstraintKind(str, Enum):
    NEVER_MOVE_DIRECTION = "never_move_direction"   # a failed direction (Phase 3 lockout)
    NEVER_BELOW = "never_below"                     # learned working-window minimum
    NEVER_ABOVE = "never_above"                     # learned working-window maximum
    PREFERRED_RANGE = "preferred_range"            # learned working window (converged)
    KNOWN_UNSTABLE = "known_unstable"              # a change that produced a regression
    PROTECTED_BEHAVIOUR = "protected_behaviour"    # a confirmed-good behaviour to keep


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


# --------------------------------------------------------------------------- #
# Immutable development record
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DevelopmentRecord:
    """ONE completed engineering review, captured immutably WITH its full memory
    context. All collection fields are tuples of plain dicts (already normalised)."""

    record_key: str                       # deterministic idempotency key
    memory_context_key: str               # MemoryContextKey.key()
    context: MemoryContextKey
    scope_fingerprint: str
    experiment_id: str
    outcome_id: str
    outcome_status: str
    confidence_level: str
    recorded_at: str                      # ISO string, supplied by the caller
    session_date: str
    test_session_id: str
    changes: Tuple[dict, ...]
    residual_states: Tuple[dict, ...]
    confirmed_improvements: Tuple[dict, ...]
    new_regressions: Tuple[dict, ...]
    protected_behaviours: Tuple[dict, ...]
    working_window_snapshot: Tuple[dict, ...]
    protected_knowledge: Tuple[dict, ...]
    content_fingerprint: str
    eval_version: str = DEVELOPMENT_HISTORY_VERSION

    @property
    def improved(self) -> bool:
        return self.outcome_status in ("confirmed_improvement", "partial_improvement")

    @property
    def regressed(self) -> bool:
        return self.outcome_status == "regression" or bool(self.new_regressions)

    @property
    def conclusive(self) -> bool:
        return self.outcome_status not in ("insufficient_evidence", "confounded", "")

    def to_dict(self) -> dict:
        return {
            "record_key": self.record_key,
            "memory_context_key": self.memory_context_key,
            "context": self.context.to_dict(),
            "scope_fingerprint": self.scope_fingerprint,
            "experiment_id": self.experiment_id, "outcome_id": self.outcome_id,
            "outcome_status": self.outcome_status,
            "confidence_level": self.confidence_level,
            "recorded_at": self.recorded_at, "session_date": self.session_date,
            "test_session_id": self.test_session_id,
            "changes": [dict(c) for c in self.changes],
            "residual_states": [dict(r) for r in self.residual_states],
            "confirmed_improvements": [dict(i) for i in self.confirmed_improvements],
            "new_regressions": [dict(r) for r in self.new_regressions],
            "protected_behaviours": [dict(p) for p in self.protected_behaviours],
            "working_window_snapshot": [dict(w) for w in self.working_window_snapshot],
            "protected_knowledge": [dict(k) for k in self.protected_knowledge],
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "DevelopmentRecord":
        d = d or {}
        ctx = MemoryContextKey.from_dict(d.get("context") or {})
        def _t(k):
            return tuple(dict(x) for x in (d.get(k) or ()))
        return cls(
            record_key=_norm(d.get("record_key")),
            memory_context_key=_norm(d.get("memory_context_key") or ctx.key()),
            context=ctx, scope_fingerprint=_norm(d.get("scope_fingerprint")),
            experiment_id=_norm(d.get("experiment_id")),
            outcome_id=_norm(d.get("outcome_id")),
            outcome_status=_norm(d.get("outcome_status")),
            confidence_level=_norm(d.get("confidence_level")),
            recorded_at=_norm(d.get("recorded_at")),
            session_date=_norm(d.get("session_date")),
            test_session_id=_norm(d.get("test_session_id")),
            changes=_t("changes"), residual_states=_t("residual_states"),
            confirmed_improvements=_t("confirmed_improvements"),
            new_regressions=_t("new_regressions"),
            protected_behaviours=_t("protected_behaviours"),
            working_window_snapshot=_t("working_window_snapshot"),
            protected_knowledge=_t("protected_knowledge"),
            content_fingerprint=_norm(d.get("content_fingerprint")),
            eval_version=_norm(d.get("eval_version")) or DEVELOPMENT_HISTORY_VERSION)


def _record_content(context_key: str, scope_fp: str, experiment_id: str,
                    outcome_id: str, outcome_status: str, changes, residuals,
                    improvements, regressions, protected, windows, knowledge) -> str:
    payload = {
        "ctx": context_key, "scope": scope_fp, "exp": experiment_id,
        "out": outcome_id, "status": outcome_status,
        "changes": list(changes), "residuals": list(residuals),
        "improvements": list(improvements), "regressions": list(regressions),
        "protected": list(protected), "windows": list(windows),
        "knowledge": list(knowledge),
    }
    return _dumps(payload)


def _residual_summary(res) -> dict:
    """Normalise a Phase-6 ResidualIssue (or dict) into a stable record shape."""
    if hasattr(res, "identity"):
        ident = res.identity
        return {
            "issue_key": res.identity.key(),
            "family": ident.issue_family.value, "issue_type": ident.issue_type,
            "axle": ident.axle, "phase": ident.phase,
            "segment_id": ident.segment_id, "corner_name": ident.corner_name,
            "residual_state": res.residual_state.value,
            "is_new": bool(res.is_new), "is_regression": bool(res.is_regression),
            "still_present": bool(res.still_present),
            "protected_good": bool(res.protected_good),
            "confidence": _norm(res.confidence),
        }
    d = res or {}
    return {
        "issue_key": _norm(d.get("issue_key")),
        "family": _norm(d.get("family")), "issue_type": _norm(d.get("issue_type")),
        "axle": _norm(d.get("axle")), "phase": _norm(d.get("phase")),
        "segment_id": _norm(d.get("segment_id")),
        "corner_name": _norm(d.get("corner_name")),
        "residual_state": _norm(d.get("residual_state")),
        "is_new": bool(d.get("is_new")), "is_regression": bool(d.get("is_regression")),
        "still_present": bool(d.get("still_present")),
        "protected_good": bool(d.get("protected_good")),
        "confidence": _norm(d.get("confidence")),
    }


def _change_summary(c: Mapping) -> dict:
    return {"field": _norm(c.get("field")), "subsystem": _norm(c.get("subsystem")),
            "from_value": _norm(c.get("from_value")),
            "to_value": _norm(c.get("to_value") or c.get("to_clamped")),
            "direction": _norm(c.get("delta_direction") or c.get("direction")),
            "symptom": _norm(c.get("symptom") or c.get("rationale"))}


def _derive_protected_knowledge(outcome: Mapping, windows, improved: bool,
                                changes: Sequence[dict]) -> Tuple[dict, ...]:
    """Turn canonical evidence into durable constraints (never authored guesses):
      * Phase-3 failed directions  → NEVER_MOVE_DIRECTION.
      * A regression outcome       → KNOWN_UNSTABLE (this change hurt).
      * Learned working windows     → NEVER_BELOW / NEVER_ABOVE / PREFERRED_RANGE.
    """
    out = []
    for fd in (outcome.get("failed_directions") or ()):
        fld = _norm(fd.get("field"))
        if not fld:
            continue
        out.append({"kind": ConstraintKind.NEVER_MOVE_DIRECTION.value, "field": fld,
                    "direction": _norm(fd.get("direction")),
                    "value": _norm(fd.get("magnitude")),
                    "confidence": _norm(fd.get("severity") or fd.get("confidence")),
                    "source": "phase3_failed_direction"})
    status = _norm(outcome.get("status"))
    if status == "regression":
        for c in changes:
            fld = _norm(c.get("field"))
            if fld:
                out.append({"kind": ConstraintKind.KNOWN_UNSTABLE.value, "field": fld,
                            "direction": _norm(c.get("direction")),
                            "value": _norm(c.get("to_value")),
                            "confidence": _norm(outcome.get("confidence_level")),
                            "source": "regression_outcome"})
    for w in (windows or ()):
        fld = _norm(w.get("field"))
        if not fld:
            continue
        lo, hi = w.get("min"), w.get("max")
        conf = _norm(w.get("confidence"))
        if lo is not None:
            out.append({"kind": ConstraintKind.NEVER_BELOW.value, "field": fld,
                        "direction": "", "value": _norm(lo), "confidence": conf,
                        "source": "learned_working_window"})
        if hi is not None:
            out.append({"kind": ConstraintKind.NEVER_ABOVE.value, "field": fld,
                        "direction": "", "value": _norm(hi), "confidence": conf,
                        "source": "learned_working_window"})
        if lo is not None and hi is not None and conf in ("high", "medium"):
            out.append({"kind": ConstraintKind.PREFERRED_RANGE.value, "field": fld,
                        "direction": "", "value": f"{_norm(lo)}..{_norm(hi)}",
                        "confidence": conf, "source": "converged_working_window"})
    # stable de-dup + order
    seen = {}
    for k in out:
        seen[(k["kind"], k["field"], k["direction"], k["value"])] = k
    return tuple(seen[q] for q in sorted(seen))


def _window_snapshot(windows) -> Tuple[dict, ...]:
    out = []
    for w in (windows or ()):
        fld = _norm(w.get("field"))
        if not fld:
            continue
        out.append({"field": fld, "min": w.get("min"), "max": w.get("max"),
                    "confidence": _norm(w.get("confidence")),
                    "valid_experiment_count": int(w.get("valid_experiment_count") or 0),
                    "improvement_count": int(w.get("improvement_count") or 0),
                    "regression_count": int(w.get("regression_count") or 0)})
    return tuple(sorted(out, key=lambda d: d["field"]))


def build_development_record(
    outcome: Mapping,
    experiment: Mapping,
    *,
    context: MemoryContextKey,
    scope_fingerprint: str = "",
    working_windows: Optional[Sequence[Mapping]] = None,
    residuals: Sequence = (),
    recorded_at: str = "",
    session_date: str = "",
) -> Optional[DevelopmentRecord]:
    """Build ONE immutable development record from canonical, already-authoritative
    inputs. Pure; deterministic; never reads the clock (``recorded_at`` is supplied).
    Returns None only when the outcome is unusable (no id/status)."""
    if not isinstance(outcome, Mapping) or not isinstance(experiment, Mapping):
        return None
    outcome_id = _norm(outcome.get("id") or outcome.get("outcome_id"))
    status = _norm(outcome.get("status"))
    if not status:
        return None
    experiment_id = _norm(experiment.get("id") or outcome.get("experiment_id"))
    scope_fp = _norm(scope_fingerprint or outcome.get("scope_fingerprint")
                     or experiment.get("scope_fingerprint"))
    changes = tuple(_change_summary(c) for c in (experiment.get("changes") or ()))
    res_summ = tuple(_residual_summary(r) for r in (residuals or ()))
    improvements = tuple(r for r in res_summ
                         if r["residual_state"] in ("resolved", "improved_but_present"))
    regressions = tuple(r for r in res_summ if r["is_new"] or r["is_regression"])
    protected = tuple(
        {"behaviour": _norm(p.get("behaviour")), "field": _norm(p.get("field")),
         "verdict": _norm(p.get("verdict")), "confidence": _norm(p.get("confidence"))}
        for p in (outcome.get("protected") or ()))
    windows = _window_snapshot(working_windows)
    knowledge = _derive_protected_knowledge(
        outcome, working_windows,
        improved=(status in ("confirmed_improvement", "partial_improvement")),
        changes=changes)
    content = _record_content(
        context.key(), scope_fp, experiment_id, outcome_id, status, changes,
        res_summ, improvements, regressions, protected, windows, knowledge)
    content_fp = f"{DEVELOPMENT_HISTORY_VERSION}:{hashlib.sha256(content.encode()).hexdigest()[:24]}"
    record_key = (f"{DEVELOPMENT_HISTORY_VERSION}:rec:"
                  + hashlib.sha256(
                      "|".join((context.key(), experiment_id, outcome_id)).encode()
                  ).hexdigest()[:24])
    return DevelopmentRecord(
        record_key=record_key, memory_context_key=context.key(), context=context,
        scope_fingerprint=scope_fp, experiment_id=experiment_id, outcome_id=outcome_id,
        outcome_status=status, confidence_level=_norm(outcome.get("confidence_level")),
        recorded_at=_norm(recorded_at), session_date=_norm(session_date),
        test_session_id=_norm(outcome.get("test_session_id")),
        changes=changes, residual_states=res_summ,
        confirmed_improvements=improvements, new_regressions=regressions,
        protected_behaviours=protected, working_window_snapshot=windows,
        protected_knowledge=knowledge, content_fingerprint=content_fp)


# --------------------------------------------------------------------------- #
# Development history (chronological, immutable)
# --------------------------------------------------------------------------- #
def _order_key(rec: DevelopmentRecord) -> Tuple[str, str, str]:
    # deterministic chronological order: recorded_at, then outcome id, then record key
    return (rec.recorded_at, rec.outcome_id.rjust(12, "0"), rec.record_key)


@dataclass(frozen=True)
class DevelopmentHistory:
    """The immutable, chronological development history for ONE memory context."""

    context: MemoryContextKey
    records: Tuple[DevelopmentRecord, ...]
    content_fingerprint: str
    eval_version: str = DEVELOPMENT_HISTORY_VERSION

    @property
    def session_count(self) -> int:
        return len({r.test_session_id for r in self.records if r.test_session_id})

    @property
    def review_count(self) -> int:
        return len(self.records)

    @property
    def latest(self) -> Optional[DevelopmentRecord]:
        return self.records[-1] if self.records else None

    def records_for_experiment(self, experiment_id: str) -> Tuple[DevelopmentRecord, ...]:
        return tuple(r for r in self.records if r.experiment_id == str(experiment_id))

    def to_dict(self) -> dict:
        return {"context": self.context.to_dict(),
                "records": [r.to_dict() for r in self.records],
                "review_count": self.review_count,
                "session_count": self.session_count,
                "content_fingerprint": self.content_fingerprint,
                "eval_version": self.eval_version}


def build_history(records: Sequence, *,
                  context: Optional[MemoryContextKey] = None) -> DevelopmentHistory:
    """Assemble an immutable, chronological ``DevelopmentHistory`` from records
    (``DevelopmentRecord`` instances or dicts). De-duplicates by ``record_key``
    (append-only: the same review can never appear twice). Deterministic order."""
    parsed = []
    for r in (records or ()):
        rec = r if isinstance(r, DevelopmentRecord) else DevelopmentRecord.from_dict(r)
        parsed.append(rec)
    by_key = {}
    for rec in parsed:
        by_key.setdefault(rec.record_key, rec)     # first wins; identical by construction
    ordered = tuple(sorted(by_key.values(), key=_order_key))
    ctx = context
    if ctx is None:
        ctx = ordered[0].context if ordered else MemoryContextKey()
    raw = _dumps([r.content_fingerprint for r in ordered] + [ctx.key()])
    fp = f"{DEVELOPMENT_HISTORY_VERSION}:hist:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
    return DevelopmentHistory(context=ctx, records=ordered, content_fingerprint=fp)


# --------------------------------------------------------------------------- #
# Long-term engineering timeline
# --------------------------------------------------------------------------- #
class TimelineEventKind(str, Enum):
    SESSION = "session"
    EXPERIMENT = "experiment"
    IMPROVEMENT = "improvement"
    REGRESSION = "regression"
    RESOLUTION = "resolution"
    PROTECTED_KEPT = "protected_kept"
    PROTECTED_DAMAGED = "protected_damaged"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class TimelineEvent:
    sequence_no: int
    recorded_at: str
    session_date: str
    kind: TimelineEventKind
    experiment_id: str
    outcome_status: str
    detail: str

    def to_dict(self) -> dict:
        return {"sequence_no": self.sequence_no, "recorded_at": self.recorded_at,
                "session_date": self.session_date, "kind": self.kind.value,
                "experiment_id": self.experiment_id,
                "outcome_status": self.outcome_status, "detail": self.detail}


def build_timeline(history: DevelopmentHistory) -> Tuple[TimelineEvent, ...]:
    """Deterministic chronological engineering timeline: session → experiment →
    improvement / regression / resolution / protected-behaviour, in record order."""
    out = []
    seq = 0
    last_session = None

    def _emit(kind, rec, detail):
        nonlocal seq
        out.append(TimelineEvent(
            sequence_no=seq, recorded_at=rec.recorded_at,
            session_date=rec.session_date, kind=kind,
            experiment_id=rec.experiment_id, outcome_status=rec.outcome_status,
            detail=detail))
        seq += 1

    for rec in history.records:
        if rec.test_session_id and rec.test_session_id != last_session:
            last_session = rec.test_session_id
            _emit(TimelineEventKind.SESSION, rec, f"session {rec.test_session_id}")
        _emit(TimelineEventKind.EXPERIMENT, rec,
              ", ".join(c["field"] for c in rec.changes) or "review")
        resolved = [r for r in rec.residual_states
                    if r["residual_state"] == "resolved"]
        for r in resolved:
            _emit(TimelineEventKind.RESOLUTION, rec,
                  f"{r['issue_type']} @ {r['corner_name'] or r['segment_id'] or '—'}")
        if rec.improved and not resolved:
            _emit(TimelineEventKind.IMPROVEMENT, rec, rec.outcome_status)
        for r in rec.new_regressions:
            _emit(TimelineEventKind.REGRESSION, rec,
                  f"{r['issue_type']} @ {r['corner_name'] or r['segment_id'] or '—'}")
        for p in rec.protected_behaviours:
            kind = (TimelineEventKind.PROTECTED_DAMAGED
                    if p["verdict"] in ("material_regression", "minor_regression")
                    else TimelineEventKind.PROTECTED_KEPT)
            _emit(kind, rec, p["behaviour"])
        if not rec.conclusive:
            _emit(TimelineEventKind.INCONCLUSIVE, rec, rec.outcome_status)
    return tuple(out)
