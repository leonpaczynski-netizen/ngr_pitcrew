"""Assisted Session Binding (Program 2, Phase 43).

Ranks candidate telemetry sessions against the run plan's context and expected setup, so the user can
explicitly select which session represents the run. It NEVER auto-binds a session, and never binds the
newest merely because it is newest - recency is only a final tie-breaker, and equally-matched sessions
are both surfaced for explicit choice.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Binds NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

SESSION_BINDING_VERSION = "session_binding_v1"
SESSION_BINDING_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return f"{SESSION_BINDING_VERSION}:" + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24]


class BindingConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class SessionCandidate:
    session_id: str
    car: str
    track: str
    layout_id: str
    compound: str
    applied_setup_fingerprint: str
    clean_laps: int
    start: str
    end: str
    match_score: int
    confidence: str
    matches: Tuple[str, ...]
    mismatches: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"session_id": self.session_id, "car": self.car, "track": self.track,
                "layout_id": self.layout_id, "compound": self.compound,
                "applied_setup_fingerprint": self.applied_setup_fingerprint,
                "clean_laps": self.clean_laps, "start": self.start, "end": self.end,
                "match_score": self.match_score, "confidence": self.confidence,
                "matches": list(self.matches), "mismatches": list(self.mismatches)}


@dataclass(frozen=True)
class SessionBindingRanking:
    candidates: Tuple[dict, ...]
    requires_explicit_selection: bool
    auto_bind_forbidden: bool
    ambiguous: bool
    note: str
    content_fingerprint: str
    schema_version: int = SESSION_BINDING_SCHEMA
    eval_version: str = SESSION_BINDING_VERSION

    def to_dict(self) -> dict:
        return {"candidates": [dict(c) for c in self.candidates],
                "requires_explicit_selection": self.requires_explicit_selection,
                "auto_bind_forbidden": self.auto_bind_forbidden, "ambiguous": self.ambiguous,
                "note": self.note, "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def _score(sess: Mapping, ctx: Mapping, expected_fp: str, min_clean: int) -> SessionCandidate:
    matches: List[str] = []
    mismatches: List[str] = []
    score = 0

    def cmp(field, weight, label):
        nonlocal score
        cv, sv = _lc(ctx.get(field)), _lc(sess.get(field))
        if cv and sv:
            if cv == sv:
                matches.append(label)
                score += weight
            else:
                mismatches.append(f"{label} ({sv} vs {cv})")
                score -= weight

    cmp("car", 4, "car")
    cmp("track", 3, "track")
    cmp("layout_id", 2, "layout")
    cmp("compound", 2, "compound")
    fp = _norm(sess.get("applied_setup_fingerprint"))
    if expected_fp and fp:
        if fp == _norm(expected_fp):
            matches.append("setup fingerprint")
            score += 5
        else:
            mismatches.append("setup fingerprint")
            score -= 5
    clean = int(sess.get("clean_laps") or 0)
    if min_clean and clean >= min_clean:
        matches.append(f"{clean} clean laps")
        score += 1
    elif min_clean:
        mismatches.append(f"only {clean} clean laps (min {min_clean})")

    car_diff = any(m.startswith("car ") for m in mismatches)
    track_diff = any(m.startswith("track ") for m in mismatches)
    if car_diff or track_diff:
        conf = BindingConfidence.INCOMPATIBLE
    elif "setup fingerprint" in matches and clean >= (min_clean or 0):
        conf = BindingConfidence.HIGH
    elif score >= 7:
        conf = BindingConfidence.MEDIUM
    else:
        conf = BindingConfidence.LOW
    return SessionCandidate(
        session_id=_norm(sess.get("session_id") or sess.get("id")), car=_norm(sess.get("car")),
        track=_norm(sess.get("track")), layout_id=_norm(sess.get("layout_id")),
        compound=_norm(sess.get("compound")), applied_setup_fingerprint=fp, clean_laps=clean,
        start=_norm(sess.get("start")), end=_norm(sess.get("end")), match_score=score,
        confidence=conf.value, matches=tuple(matches), mismatches=tuple(mismatches))


def rank_candidate_sessions(candidate_sessions: Optional[Sequence[Mapping]],
                            run_plan_context: Optional[Mapping], *, expected_setup_fingerprint: str = "",
                            min_clean_laps: int = 0) -> SessionBindingRanking:
    """Rank candidate sessions by context+setup match. Recency is only a final tie-breaker (never the
    primary). Deterministic; never raises. Binds nothing."""
    try:
        ctx = run_plan_context if isinstance(run_plan_context, Mapping) else {}
        sessions = [s for s in (candidate_sessions or []) if isinstance(s, Mapping)]
        scored = [_score(s, ctx, expected_setup_fingerprint, int(min_clean_laps or 0)) for s in sessions]
        # order: match_score desc, then confidence rank, then session_id (STABLE) - NOT by recency.
        conf_rank = {"high": 0, "medium": 1, "low": 2, "incompatible": 3}
        scored.sort(key=lambda c: (-c.match_score, conf_rank.get(c.confidence, 9), c.session_id))
        top_scores = [c.match_score for c in scored]
        ambiguous = len(scored) >= 2 and top_scores[0] == top_scores[1]
        note = ("multiple sessions match equally well - you must choose explicitly; the newest is NOT "
                "auto-selected." if ambiguous else
                "select and confirm the session; nothing is bound automatically.")
        fp = _fp({"ctx": {k: _lc(ctx.get(k)) for k in ("car", "track", "layout_id", "compound")},
                  "exp": _norm(expected_setup_fingerprint),
                  "cands": [(c.session_id, c.match_score, c.confidence) for c in scored]})
        return SessionBindingRanking(
            candidates=tuple(c.to_dict() for c in scored), requires_explicit_selection=True,
            auto_bind_forbidden=True, ambiguous=ambiguous, note=note, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return SessionBindingRanking(candidates=(), requires_explicit_selection=True,
                                     auto_bind_forbidden=True, ambiguous=False,
                                     note="unavailable.", content_fingerprint=_fp({"e": 1}))


def session_binding_versions() -> dict:
    return {"session_binding": SESSION_BINDING_VERSION, "schema": SESSION_BINDING_SCHEMA}
