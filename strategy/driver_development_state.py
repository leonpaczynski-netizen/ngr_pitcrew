"""Driver-Development State — Layer 5 of the Race-Engineer Activation (Program 2, Phase 37).

A deterministic, read-only view of how the driver is developing, built from REPEATED evidence (the
per-corner residual states recorded across the exact-context development history) rather than one-off
laps. It represents strengths and development areas across driving dimensions, a confidence and a
trend per dimension, and - critically - it distinguishes the likely CAUSE of each recurring problem:

  * ``likely_technique``  - the problem persists across materially different setups (or is driver-
                            keyed) so it is most likely a driver-technique limitation;
  * ``likely_setup``      - the problem appeared/worsened only after a specific setup delta;
  * ``combined``          - evidence points to a driver/setup interaction;
  * ``track_interaction`` - the problem is bound to one corner across many setups (a circuit constraint);
  * ``insufficient``      - not enough repeated evidence to attribute.

Doctrine:
  * A strong setup is not blamed for a driver inconsistency without evidence, and a repeated car
    behaviour is not dismissed as driver error.
  * Progression is a TREND across ordered evidence - the latest session is never assumed to be
    automatically better; a single good session does not promote a development area to a strength.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Coaches NOTHING here (Layer 6 selects priorities); authors no setup value.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

DRIVER_DEVELOPMENT_STATE_VERSION = "driver_development_state_v1"
DRIVER_DEVELOPMENT_STATE_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{DRIVER_DEVELOPMENT_STATE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class DimensionCategory(str, Enum):
    STRENGTH = "strength"
    DEVELOPMENT_AREA = "development_area"
    EMERGING = "emerging"            # some progress but not yet a strength
    INSUFFICIENT = "insufficient"


class Attribution(str, Enum):
    LIKELY_TECHNIQUE = "likely_technique"
    LIKELY_SETUP = "likely_setup"
    COMBINED = "combined"
    TRACK_INTERACTION = "track_interaction"
    INSUFFICIENT = "insufficient"


class Trend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    REGRESSING = "regressing"
    INSUFFICIENT = "insufficient"


# canonical driving dimensions (subset materially observable from recorded residual evidence).
# key = (issue-family/type token, phase token) -> dimension.  '*' = any phase.
_DIMENSION_MAP = {
    ("lockup", "braking"): "threshold_braking", ("lock", "braking"): "threshold_braking",
    ("lockup", "*"): "threshold_braking",
    ("trail", "entry"): "trail_brake_release", ("trail_brake", "*"): "trail_brake_release",
    ("understeer", "entry"): "turn_in_front_load", ("understeer", "turn_in"): "turn_in_front_load",
    ("understeer", "mid"): "minimum_corner_speed", ("understeer", "*"): "turn_in_front_load",
    ("oversteer", "entry"): "trail_brake_release", ("oversteer", "mid"): "rear_stability",
    ("oversteer", "exit"): "rear_stability", ("instability", "exit"): "rear_stability",
    ("instability", "*"): "rear_stability", ("stability", "exit"): "rear_stability",
    ("wheelspin", "exit"): "exit_wheelspin", ("wheelspin", "*"): "exit_wheelspin",
    ("traction", "exit"): "drive_out", ("traction", "*"): "drive_out",
    ("drive_out", "*"): "drive_out", ("gearing", "*"): "gear_selection", ("gear", "*"): "gear_selection",
    ("apex", "*"): "apex_connection", ("throttle", "exit"): "throttle_progression",
    ("throttle", "*"): "throttle_timing", ("steering", "*"): "steering_correction",
    ("width", "*"): "use_of_track_width",
}

# residual_state -> a progress score (higher = better).
_STATE_SCORE = {"resolved": 2, "improved_but_present": 1, "present": 0, "new": 0, "": 0,
                "still_present": 0, "regressed": -1}


def _dimension_for(issue_type: str, family: str, phase: str) -> str:
    it, fam, ph = _lc(issue_type), _lc(family), _lc(phase)
    for token in (it, fam):
        if not token:
            continue
        for key in (token, token.split("_")[0]):
            if (key, ph) in _DIMENSION_MAP:
                return _DIMENSION_MAP[(key, ph)]
            if (key, "*") in _DIMENSION_MAP:
                return _DIMENSION_MAP[(key, "*")]
    return ""


@dataclass(frozen=True)
class DriverDimension:
    dimension: str
    category: str
    attribution: str
    trend: str
    confidence: str
    evidence_count: int
    session_count: int
    distinct_setup_count: int
    corners: Tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        return {"dimension": self.dimension, "category": self.category,
                "attribution": self.attribution, "trend": self.trend, "confidence": self.confidence,
                "evidence_count": self.evidence_count, "session_count": self.session_count,
                "distinct_setup_count": self.distinct_setup_count, "corners": list(self.corners),
                "reason": self.reason}


@dataclass(frozen=True)
class DriverDevelopmentState:
    scope_fingerprint: str
    dimensions: Tuple[dict, ...]
    strengths: Tuple[str, ...]
    development_areas: Tuple[str, ...]
    empty_state: str
    doctrine: str
    content_fingerprint: str
    schema_version: int = DRIVER_DEVELOPMENT_STATE_SCHEMA
    eval_version: str = DRIVER_DEVELOPMENT_STATE_VERSION

    def to_dict(self) -> dict:
        return {"scope_fingerprint": self.scope_fingerprint,
                "dimensions": [dict(d) for d in self.dimensions], "strengths": list(self.strengths),
                "development_areas": list(self.development_areas), "empty_state": self.empty_state,
                "doctrine": self.doctrine, "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_DOCTRINE = ("Built from repeated evidence, not one-off laps. Progression is a trend across ordered "
             "evidence; the latest session is never assumed better. A problem across materially "
             "different setups points to technique or track; a problem only after one delta points to "
             "setup. A strong setup is not blamed for driver inconsistency without evidence.")


def _order_key(rec: Mapping):
    return (_norm(rec.get("recorded_at")), _norm(rec.get("record_key")))


def _setup_signature(rec: Mapping) -> str:
    return "|".join(sorted(_norm(c.get("field")) for c in (rec.get("changes") or [])
                           if _norm(c.get("field")))) or "no_change"


def build_driver_development_state(scope_fingerprint: str,
                                   exact_records: Optional[Sequence[Mapping]]
                                   ) -> DriverDevelopmentState:
    """Build the driver-development state from ordered EXACT-CONTEXT records. Deterministic;
    order-independent input (re-sorted internally); never raises."""
    try:
        return _build(_norm(scope_fingerprint),
                      sorted([r for r in (exact_records or []) if isinstance(r, Mapping)],
                             key=_order_key))
    except Exception:  # pragma: no cover - defensive
        return DriverDevelopmentState(scope_fingerprint=_norm(scope_fingerprint), dimensions=(),
                                      strengths=(), development_areas=(),
                                      empty_state="Driver-development state unavailable.",
                                      doctrine=_DOCTRINE, content_fingerprint=_fp({"error": True}))


def _build(scope_fp: str, ordered: List[Mapping]) -> DriverDevelopmentState:
    # per dimension: ordered observations
    obs: "Dict[str, List[dict]]" = {}
    for rec in ordered:
        sig = _setup_signature(rec)
        session = _norm(rec.get("test_session_id")) or _norm(rec.get("session_date")) \
            or _norm(rec.get("record_key"))
        for r in (rec.get("residual_states") or []):
            dim = _dimension_for(_norm(r.get("issue_type")), _norm(r.get("family")),
                                 _norm(r.get("phase")))
            if not dim:
                continue
            state = _lc(r.get("residual_state"))
            score = _STATE_SCORE.get(state, 0)
            if r.get("is_regression"):
                score = min(score, -1)
            obs.setdefault(dim, []).append({
                "score": score, "session": session, "setup_sig": sig,
                "corner": _norm(r.get("corner_name")) or _norm(r.get("segment_id")),
                "recorded_at": _norm(rec.get("recorded_at")),
                "confidence": _lc(r.get("confidence")) or _lc(rec.get("confidence_level")),
                "appeared": bool(r.get("is_new")) or bool(r.get("is_regression")),
                "protected_good": bool(r.get("protected_good"))})

    dims: List[DriverDimension] = []
    for dim in sorted(obs):
        points = obs[dim]
        n = len(points)
        sessions = {p["session"] for p in points}
        setups = {p["setup_sig"] for p in points}
        corners = tuple(sorted({p["corner"] for p in points if p["corner"]}))
        conf = _dominant_conf(points)

        trend = _trend(points)
        appeared = any(p.get("appeared") for p in points)   # a NEW / regressed observation
        # attribution:
        #  * persists across >=2 materially different setups -> the setup is not the cause: it is a
        #    driver-technique limitation, or a circuit constraint when bound to one corner;
        #  * one setup, the problem APPEARED (new/regressed) and is not improving -> setup-attributable;
        #  * one setup, improving/present under a CONSTANT setup -> the variation is the driver.
        if n < 2:
            attribution = Attribution.INSUFFICIENT
        elif len(setups) >= 2:
            attribution = (Attribution.TRACK_INTERACTION if len(corners) == 1
                           else Attribution.LIKELY_TECHNIQUE)
        elif appeared and trend is not Trend.IMPROVING:
            attribution = Attribution.LIKELY_SETUP
        elif trend is Trend.IMPROVING:
            attribution = Attribution.LIKELY_TECHNIQUE
        else:
            attribution = Attribution.COMBINED

        # category: strong = mostly resolved/high scores and improving/stable over >=3 points; a lone
        # good latest point does not promote.
        avg = sum(p["score"] for p in points) / max(n, 1)
        latest_good = points[-1]["score"] >= 2
        if n < 2:
            category = DimensionCategory.INSUFFICIENT
        elif avg >= 1.5 and trend is not Trend.REGRESSING:
            category = DimensionCategory.STRENGTH
        elif trend is Trend.IMPROVING and n >= 3:
            category = DimensionCategory.EMERGING
        elif avg <= 0.5 or trend is Trend.REGRESSING:
            category = DimensionCategory.DEVELOPMENT_AREA
        else:
            category = DimensionCategory.EMERGING if latest_good else DimensionCategory.DEVELOPMENT_AREA

        reason = _reason(dim, category, attribution, trend, n, len(sessions), len(setups))
        dims.append(DriverDimension(
            dimension=dim, category=category.value, attribution=attribution.value, trend=trend.value,
            confidence=conf, evidence_count=n, session_count=len(sessions),
            distinct_setup_count=len(setups), corners=corners, reason=reason))

    strengths = tuple(d.dimension for d in dims if d.category == DimensionCategory.STRENGTH.value)
    dev_areas = tuple(d.dimension for d in dims
                      if d.category in (DimensionCategory.DEVELOPMENT_AREA.value,
                                        DimensionCategory.EMERGING.value))
    empty = "" if dims else ("No repeated driver-development evidence yet - not enough recorded "
                             "per-corner observations to characterise the driver.")
    fp = _fp({"scope": scope_fp,
              "dims": [(d.dimension, d.category, d.attribution, d.trend, d.evidence_count)
                       for d in dims]})
    return DriverDevelopmentState(scope_fingerprint=scope_fp,
                                  dimensions=tuple(d.to_dict() for d in dims), strengths=strengths,
                                  development_areas=dev_areas, empty_state=empty, doctrine=_DOCTRINE,
                                  content_fingerprint=fp)


def _dominant_conf(points: Sequence[Mapping]) -> str:
    rank = {"": 0, "low": 1, "medium": 2, "high": 3, "very_high": 4}
    best = ""
    for p in points:
        if rank.get(p["confidence"], 0) > rank.get(best, 0):
            best = p["confidence"]
    return best


def _trend(points: Sequence[Mapping]) -> Trend:
    if len(points) < 3:
        return Trend.INSUFFICIENT if len(points) < 2 else Trend.STABLE
    k = max(1, len(points) // 3)
    first = sum(p["score"] for p in points[:k]) / k
    last = sum(p["score"] for p in points[-k:]) / k
    if last - first >= 0.75:
        return Trend.IMPROVING
    if first - last >= 0.75:
        return Trend.REGRESSING
    return Trend.STABLE


def _reason(dim, category, attribution, trend, n, sessions, setups) -> str:
    return (f"{dim.replace('_', ' ')}: {category.value.replace('_', ' ')} from {n} observation(s) "
            f"across {sessions} session(s) and {setups} setup(s); attribution {attribution.value}; "
            f"trend {trend.value}.")


def driver_development_versions() -> dict:
    return {"driver_development_state": DRIVER_DEVELOPMENT_STATE_VERSION,
            "schema": DRIVER_DEVELOPMENT_STATE_SCHEMA}
