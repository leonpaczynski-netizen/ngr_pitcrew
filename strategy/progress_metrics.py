"""Deterministic long-term engineering progress intelligence (Engineering Brain Phase 8).

Turns an immutable ``DevelopmentHistory`` + ``EngineeringMemory`` into deterministic
long-term metrics, an engineering scorecard, and session-to-session comparison. It
calculates progress; it never decides, authors, or evaluates a lap.

All trends use the same philosophy as Phase 7: a minimum number of points, a window
comparison, and hysteresis — a single session can never flip a long-term trend.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from strategy.development_history import DevelopmentHistory, DevelopmentRecord
from strategy.engineering_memory import EngineeringMemory

PROGRESS_METRICS_VERSION = "progress_metrics_v1"

MIN_TREND_POINTS = 3
TREND_DELTA = 0.15


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class MetricTrend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    WORSENING = "worsening"
    INSUFFICIENT = "insufficient"


def numeric_trend(series: Sequence[Optional[float]], *,
                  higher_is_better: bool = True,
                  min_points: int = MIN_TREND_POINTS,
                  delta: float = TREND_DELTA) -> MetricTrend:
    """Deterministic long-term trend over an ordered numeric series (None = a gap,
    skipped). Compares the early-window mean to the recent-window mean with a minimum
    point count + a delta band, so ONE session can never flip the trend."""
    pts = [float(v) for v in series if v is not None]
    if len(pts) < min_points:
        return MetricTrend.INSUFFICIENT
    half = len(pts) // 2
    early = pts[:half] or pts[:1]
    recent = pts[half:] or pts[-1:]
    em = sum(early) / len(early)
    rm = sum(recent) / len(recent)
    move = rm - em
    if abs(move) < delta:
        return MetricTrend.STABLE
    up = move > 0
    good = up if higher_is_better else (not up)
    return MetricTrend.IMPROVING if good else MetricTrend.WORSENING


# --------------------------------------------------------------------------- #
# Progress metrics
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProgressMetrics:
    review_count: int
    session_count: int
    conclusive_reviews: int
    experiment_success_rate: float       # improved / conclusive
    issue_resolution_rate: float         # resolved issues / issues ever seen
    recurring_issues_reduced: int        # issues that stopped recurring
    issues_solved: int
    issues_remaining: int
    working_window_convergence: float    # converged fields / fields with a window
    driver_consistency_trend: str        # MetricTrend value
    engineering_confidence_trend: str
    entry_stability_trend: str
    exit_traction_trend: str
    brake_consistency_trend: str
    development_velocity: float          # net issues resolved per session
    experiment_efficiency: float         # net improvement per experiment
    content_fingerprint: str
    eval_version: str = PROGRESS_METRICS_VERSION

    def to_dict(self) -> dict:
        return {
            "review_count": self.review_count, "session_count": self.session_count,
            "conclusive_reviews": self.conclusive_reviews,
            "experiment_success_rate": self.experiment_success_rate,
            "issue_resolution_rate": self.issue_resolution_rate,
            "recurring_issues_reduced": self.recurring_issues_reduced,
            "issues_solved": self.issues_solved,
            "issues_remaining": self.issues_remaining,
            "working_window_convergence": self.working_window_convergence,
            "driver_consistency_trend": self.driver_consistency_trend,
            "engineering_confidence_trend": self.engineering_confidence_trend,
            "entry_stability_trend": self.entry_stability_trend,
            "exit_traction_trend": self.exit_traction_trend,
            "brake_consistency_trend": self.brake_consistency_trend,
            "development_velocity": self.development_velocity,
            "experiment_efficiency": self.experiment_efficiency,
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version,
        }


_CONF = {"high": 1.0, "medium": 0.6, "low": 0.3, "provisional": 0.3, "": 0.0}
# how many still-present affected corners of a given phase/issue appear per record →
# a lower count over time = an improving stability/traction/brake trend.
_ENTRY_ISSUES = {"understeer", "entry_understeer", "mid_corner_understeer",
                 "oversteer", "snap_oversteer", "entry_rotation", "front_push"}
_EXIT_ISSUES = {"wheelspin", "rear_wheelspin", "exit_wheelspin", "poor_traction",
                "rear_loose_on_exit", "poor_drive_out"}
_BRAKE_ISSUES = {"front_lock", "lockup", "rear_loose_under_braking",
                 "braking_instability"}


def _phase_load(rec: DevelopmentRecord, issue_set) -> Optional[float]:
    """Count of still-present issues of a category in this record (lower = better).
    None when the record is inconclusive (not comparable)."""
    if not rec.conclusive:
        return None
    n = 0
    for r in rec.residual_states:
        if r.get("still_present") and (r.get("issue_type") in issue_set
                                       or r.get("family") in issue_set):
            n += 1
    return float(n)


def _driver_consistency_series(history: DevelopmentHistory) -> List[Optional[float]]:
    """A proxy for lap-to-lap consistency from validity evidence already captured on
    the outcome (valid-lap ratio). Higher = more consistent. Engineering measurement,
    not a driver rating."""
    out: List[Optional[float]] = []
    for rec in history.records:
        # residual confidence is a coarse proxy already available on the record;
        # fall back to conclusiveness.
        if not rec.conclusive:
            out.append(None)
            continue
        confs = [_CONF.get(str(r.get("confidence") or "").lower(), 0.0)
                 for r in rec.residual_states]
        out.append(sum(confs) / len(confs) if confs else 0.0)
    return out


def build_progress_metrics(history: DevelopmentHistory,
                           memory: EngineeringMemory) -> ProgressMetrics:
    """Deterministic long-term metrics over the history + folded memory."""
    records = history.records
    review_count = len(records)
    conclusive = [r for r in records if r.conclusive]
    improved = [r for r in conclusive if r.improved]
    success_rate = round(len(improved) / len(conclusive), 4) if conclusive else 0.0

    issues = memory.issues
    ever = len(issues)
    solved = sum(1 for i in issues if i.currently_resolved)
    remaining = sum(1 for i in issues if not i.currently_resolved)
    resolution_rate = round(solved / ever, 4) if ever else 0.0
    # recurring issues reduced: recurred at some point but now resolved
    reduced = sum(1 for i in issues if i.times_regressed and i.currently_resolved)

    fields_with_window = memory.window_evolution
    converged = sum(1 for w in fields_with_window if w.converged)
    convergence = round(converged / len(fields_with_window), 4) \
        if fields_with_window else 0.0

    entry = numeric_trend([_phase_load(r, _ENTRY_ISSUES) for r in records],
                          higher_is_better=False)
    exit_ = numeric_trend([_phase_load(r, _EXIT_ISSUES) for r in records],
                          higher_is_better=False)
    brake = numeric_trend([_phase_load(r, _BRAKE_ISSUES) for r in records],
                          higher_is_better=False)
    driver = numeric_trend(_driver_consistency_series(history),
                           higher_is_better=True)
    conf_series = [_CONF.get(str(r.confidence_level or "").lower(), 0.0)
                   if r.conclusive else None for r in records]
    confidence = numeric_trend(conf_series, higher_is_better=True)

    sessions = history.session_count or 1
    velocity = round(solved / sessions, 4)
    experiments = len(conclusive) or 1
    net = len(improved) - sum(1 for r in conclusive if r.regressed)
    efficiency = round(net / experiments, 4)

    payload = {
        "reviews": review_count, "sessions": history.session_count,
        "conclusive": len(conclusive), "success": success_rate,
        "resolution": resolution_rate, "reduced": reduced, "solved": solved,
        "remaining": remaining, "convergence": convergence,
        "driver": driver.value, "confidence": confidence.value,
        "entry": entry.value, "exit": exit_.value, "brake": brake.value,
        "velocity": velocity, "efficiency": efficiency,
        "ctx": history.context.key(),
    }
    fp = (f"{PROGRESS_METRICS_VERSION}:"
          + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24])
    return ProgressMetrics(
        review_count=review_count, session_count=history.session_count,
        conclusive_reviews=len(conclusive), experiment_success_rate=success_rate,
        issue_resolution_rate=resolution_rate, recurring_issues_reduced=reduced,
        issues_solved=solved, issues_remaining=remaining,
        working_window_convergence=convergence,
        driver_consistency_trend=driver.value,
        engineering_confidence_trend=confidence.value,
        entry_stability_trend=entry.value, exit_traction_trend=exit_.value,
        brake_consistency_trend=brake.value, development_velocity=velocity,
        experiment_efficiency=efficiency, content_fingerprint=fp)


# --------------------------------------------------------------------------- #
# Engineering scorecard
# --------------------------------------------------------------------------- #
class ScorecardBand(str, Enum):
    STRONG = "strong"                   # solving more than breaking, protected intact
    PROGRESSING = "progressing"
    STALLED = "stalled"                 # little net progress
    REGRESSING = "regressing"           # breaking more than solving / protection lost
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class EngineeringScorecard:
    issues_solved: int
    issues_remaining: int
    protected_retained: int
    protected_damaged: int
    engineering_confidence: str          # MetricTrend value
    development_velocity: float
    experiment_efficiency: float
    experiment_success_rate: float
    band: ScorecardBand
    content_fingerprint: str
    eval_version: str = PROGRESS_METRICS_VERSION

    def to_dict(self) -> dict:
        return {"issues_solved": self.issues_solved,
                "issues_remaining": self.issues_remaining,
                "protected_retained": self.protected_retained,
                "protected_damaged": self.protected_damaged,
                "engineering_confidence": self.engineering_confidence,
                "development_velocity": self.development_velocity,
                "experiment_efficiency": self.experiment_efficiency,
                "experiment_success_rate": self.experiment_success_rate,
                "band": self.band.value,
                "content_fingerprint": self.content_fingerprint,
                "eval_version": self.eval_version}


def build_scorecard(history: DevelopmentHistory, memory: EngineeringMemory,
                    metrics: ProgressMetrics) -> EngineeringScorecard:
    """A deterministic development summary. Read-only; recommends nothing."""
    retained = sum(1 for p in memory.protected_behaviours
                   if p.get("verdict") == "preserved")
    damaged = sum(1 for p in memory.protected_behaviours
                  if p.get("verdict") in ("material_regression", "minor_regression"))
    solved, remaining = metrics.issues_solved, metrics.issues_remaining

    if metrics.conclusive_reviews < MIN_TREND_POINTS:
        band = ScorecardBand.INSUFFICIENT
    elif damaged > retained or metrics.experiment_efficiency < 0:
        band = ScorecardBand.REGRESSING
    elif metrics.development_velocity <= 0 and solved == 0:
        band = ScorecardBand.STALLED
    elif solved > remaining and metrics.experiment_success_rate >= 0.5:
        band = ScorecardBand.STRONG
    else:
        band = ScorecardBand.PROGRESSING

    payload = {"solved": solved, "remaining": remaining, "retained": retained,
               "damaged": damaged, "conf": metrics.engineering_confidence_trend,
               "vel": metrics.development_velocity,
               "eff": metrics.experiment_efficiency,
               "succ": metrics.experiment_success_rate, "band": band.value,
               "ctx": history.context.key()}
    fp = (f"{PROGRESS_METRICS_VERSION}:score:"
          + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:20])
    return EngineeringScorecard(
        issues_solved=solved, issues_remaining=remaining,
        protected_retained=retained, protected_damaged=damaged,
        engineering_confidence=metrics.engineering_confidence_trend,
        development_velocity=metrics.development_velocity,
        experiment_efficiency=metrics.experiment_efficiency,
        experiment_success_rate=metrics.experiment_success_rate,
        band=band, content_fingerprint=fp)


# --------------------------------------------------------------------------- #
# Session-to-session comparison
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SessionComparison:
    earlier_label: str
    later_label: str
    earlier_session_id: str
    later_session_id: str
    issues_resolved_delta: int
    regressions_delta: int
    improvements_delta: int
    confidence_delta: float
    protected_damaged_delta: int
    verdict: str                        # improved / mixed / regressed / inconclusive
    content_fingerprint: str
    eval_version: str = PROGRESS_METRICS_VERSION

    def to_dict(self) -> dict:
        return {"earlier_label": self.earlier_label, "later_label": self.later_label,
                "earlier_session_id": self.earlier_session_id,
                "later_session_id": self.later_session_id,
                "issues_resolved_delta": self.issues_resolved_delta,
                "regressions_delta": self.regressions_delta,
                "improvements_delta": self.improvements_delta,
                "confidence_delta": self.confidence_delta,
                "protected_damaged_delta": self.protected_damaged_delta,
                "verdict": self.verdict,
                "content_fingerprint": self.content_fingerprint,
                "eval_version": self.eval_version}


def _record_signature(rec: DevelopmentRecord) -> dict:
    resolved = sum(1 for r in rec.residual_states
                   if r.get("residual_state") == "resolved")
    regressions = len(rec.new_regressions)
    improvements = len(rec.confirmed_improvements)
    conf = _CONF.get(str(rec.confidence_level or "").lower(), 0.0)
    damaged = sum(1 for p in rec.protected_behaviours
                  if p.get("verdict") in ("material_regression", "minor_regression"))
    return {"resolved": resolved, "regressions": regressions,
            "improvements": improvements, "confidence": conf, "damaged": damaged}


def compare_records(earlier: DevelopmentRecord,
                    later: DevelopmentRecord) -> SessionComparison:
    """Deterministic comparison of two development records (e.g. this Fuji session vs
    the last, or this Porsche RSR vs the previous). Read-only; decides nothing."""
    a = _record_signature(earlier)
    b = _record_signature(later)
    resolved_d = b["resolved"] - a["resolved"]
    reg_d = b["regressions"] - a["regressions"]
    imp_d = b["improvements"] - a["improvements"]
    conf_d = round(b["confidence"] - a["confidence"], 4)
    dmg_d = b["damaged"] - a["damaged"]

    score = resolved_d + imp_d - reg_d - dmg_d
    if b == a:
        verdict = "inconclusive"
    elif score > 0 and reg_d <= 0 and dmg_d <= 0:
        verdict = "improved"
    elif score < 0 or dmg_d > 0:
        verdict = "regressed"
    else:
        verdict = "mixed"

    payload = {"a": a, "b": b, "ea": earlier.record_key, "la": later.record_key,
               "verdict": verdict}
    fp = (f"{PROGRESS_METRICS_VERSION}:cmp:"
          + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:20])
    return SessionComparison(
        earlier_label=earlier.context.label(), later_label=later.context.label(),
        earlier_session_id=earlier.test_session_id,
        later_session_id=later.test_session_id,
        issues_resolved_delta=resolved_d, regressions_delta=reg_d,
        improvements_delta=imp_d, confidence_delta=conf_d,
        protected_damaged_delta=dmg_d, verdict=verdict, content_fingerprint=fp)


def compare_latest_sessions(history: DevelopmentHistory) -> Optional[SessionComparison]:
    """Compare the two most recent DISTINCT-session records in the history."""
    seen: List[DevelopmentRecord] = []
    seen_sessions: List[str] = []
    for rec in reversed(history.records):
        sid = rec.test_session_id or rec.record_key
        if sid not in seen_sessions:
            seen_sessions.append(sid)
            seen.append(rec)
        if len(seen) == 2:
            break
    if len(seen) < 2:
        return None
    later, earlier = seen[0], seen[1]
    return compare_records(earlier, later)
