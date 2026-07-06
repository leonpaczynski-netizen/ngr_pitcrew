"""Group 47 — Setup Brain Outcome Verification & Learning Loop 2.

WHY IT EXISTS
  After an approved setup change has been applied and the driver has run another
  practice/race session, we want to verify *whether the change actually helped*:
  did the targeted telemetry issue improve, stay the same, get worse, or trade one
  problem for another?  The classification then feeds — through the existing
  Group 46 validated learning path — a one-step confidence/ranking nudge and an
  honest human-readable explanation.

WHAT THIS MODULE IS NOT
  • It is NOT an AI tuner.  It authors no setup values and touches no setup dict.
  • It cannot unblock a rejected recommendation, create fields, or alter the Apply
    gate.  Its only outputs are a verdict, a confidence, and explanation text.
  • Driver feedback is *evidence*, never an authority: it can never override a
    telemetry safety regression, and positive feedback alone (with flat/absent
    telemetry) never manufactures an "improved" verdict.

PURITY CONTRACT (mirrors data/recommendation_scoring.py)
  • No PyQt6, no sqlite3, no file I/O, no network, no AI.
  • Never raises — every public function wraps its internals and returns a safe
    fallback (INSUFFICIENT_EVIDENCE / empty string).
  • Invents no telemetry: if a required signal is unavailable, the result is
    INSUFFICIENT_EVIDENCE.  Steering-angle / rival-driver metrics are NOT used
    because no such signal exists (honest deferral).

VERDICT VOCABULARY BRIDGE
  The persisted Group 46 learning verdict vocabulary is
  {improved, worsened, neutral, insufficient_data}.  outcome_to_learning_verdict()
  maps this module's richer OutcomeVerdict onto it so MIXED never boosts confidence
  (→ neutral) and INSUFFICIENT_EVIDENCE is skipped by the feed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enums / target-issue identifiers
# ---------------------------------------------------------------------------

class OutcomeVerdict(str, Enum):
    """Classification of whether an applied change helped the targeted issue."""

    IMPROVED = "IMPROVED"
    UNCHANGED = "UNCHANGED"
    WORSE = "WORSE"
    MIXED = "MIXED"                          # improved one issue, worsened another / conflicting
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# Target issue identifiers (the issue a setup change was intended to fix).
TARGET_EXIT_TRACTION = "exit_traction"
TARGET_BOTTOMING = "bottoming"
TARGET_BRAKE_STABILITY = "brake_stability"
TARGET_ROTATION = "rotation"
TARGET_UNKNOWN = "unknown"

# Issues for which the Setup Brain has NO reliable telemetry signal.  Verifying
# these deterministically would require inventing steering-angle metrics, so we
# honestly return INSUFFICIENT_EVIDENCE instead (see module docstring).
_UNSUPPORTED_TARGETS = frozenset({
    "understeer", "front_bite", "rotation_feel", TARGET_UNKNOWN, "",
})

# Minimum clean laps required on EACH side to trust a before/after comparison.
# Matches data/recommendation_scoring.py's honesty gate.
MIN_CLEAN_LAPS: int = 3

# A metric value of this sentinel means "not measured / signal unavailable".
METRIC_ABSENT: float = -1.0

# Unchanged band: a per-lap event-rate delta smaller than max(_BAND_ABS,
# _BAND_REL * before) is treated as no meaningful movement.
_BAND_ABS: float = 0.5
_BAND_REL: float = 0.15


# ---------------------------------------------------------------------------
# Typed metric containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricSnapshot:
    """Per-lap-average telemetry snapshot for one session side.

    All event-rate fields default to METRIC_ABSENT (-1.0) meaning "not measured".
    clean_laps carries the clean-lap count backing the averages.  Only signals
    the Setup Brain already derives are represented here — no invented metrics.
    """

    wheelspin: float = METRIC_ABSENT            # exit-traction primary
    oversteer_throttle: float = METRIC_ABSENT   # exit instability (on-throttle) — traction secondary
    bottoming: float = METRIC_ABSENT            # ride-height / platform
    lock_up: float = METRIC_ABSENT              # brake-stability primary
    brake_consistency: float = METRIC_ABSENT    # brake-stability secondary (metres, lower=better)
    oversteer: float = METRIC_ABSENT            # rotation proxy
    clean_laps: int = 0

    @classmethod
    def from_window(cls, window) -> "MetricSnapshot":
        """Build a snapshot from a recommendation_scoring.LapWindow (duck-typed).

        LapWindow always yields floats (0.0 when a rate is genuinely absent), so
        insufficiency is governed by clean_laps, not the METRIC_ABSENT sentinel.
        Never raises — missing attributes fall back to METRIC_ABSENT / 0.
        """
        def _g(name: str) -> float:
            try:
                v = getattr(window, name, METRIC_ABSENT)
                return float(v) if v is not None else METRIC_ABSENT
            except (TypeError, ValueError):
                return METRIC_ABSENT

        try:
            clean = int(getattr(window, "clean_count", 0) or 0)
        except (TypeError, ValueError):
            clean = 0

        return cls(
            wheelspin=_g("avg_wheelspin"),
            oversteer_throttle=_g("avg_oversteer_throttle"),
            bottoming=_g("avg_bottoming"),
            lock_up=_g("avg_lock_up"),
            brake_consistency=_g("avg_brake_consistency"),
            oversteer=_g("avg_oversteer"),
            clean_laps=clean,
        )


@dataclass(frozen=True)
class OutcomeVerificationResult:
    """Result of verifying whether an applied change fixed its targeted issue."""

    rule_id: str
    car_id: int
    track: str
    layout_id: str
    target_issue: str
    before_metric: float          # targeted primary metric before (METRIC_ABSENT if unmeasured)
    after_metric: float           # targeted primary metric after
    driver_feedback: str          # raw feedback string echoed back as evidence
    outcome: OutcomeVerdict
    confidence: float             # 0.0–1.0
    evidence_summary: str
    safety_notes: str


# ---------------------------------------------------------------------------
# Driver feedback classification (deterministic keyword matcher)
# ---------------------------------------------------------------------------

# Multi-word phrases are checked before single tokens.  Kept intentionally small
# and literal — no NLP, no negation handling (a documented deferral).
_FEEDBACK_POSITIVE = (
    "fixed", "fix ", "more stable", "more grip", "much better", "feels better",
    "better", "improved", "improve", "solved", "gone", "no more", "great", "good",
    "planted", "sorted",
)
_FEEDBACK_NEGATIVE = (
    "worse", "still loose", "still spinning", "still", "rear loose", "loose",
    "unstable", "snappy", "snap", "spinning", "no grip", "more understeer",
    "understeer", "bad", "terrible", "nervous",
)
_FEEDBACK_NEUTRAL = (
    "no change", "no difference", "unchanged", "same as before", "about the same",
    "the same", "no real change",
)


def classify_driver_feedback(text: str) -> str:
    """Classify free-text driver feedback into a deterministic bucket.

    Returns one of: 'better' | 'worse' | 'no_change' | 'mixed' | 'unknown'.

    'mixed'   — both positive and negative sentiment present (e.g. "exit better
                but braking worse").
    'unknown' — empty or no recognised sentiment (vague feedback → weak learning).

    Case-insensitive; None-safe; never raises.
    """
    try:
        if not text:
            return "unknown"
        t = str(text).lower()

        has_pos = any(kw in t for kw in _FEEDBACK_POSITIVE)
        has_neg = any(kw in t for kw in _FEEDBACK_NEGATIVE)
        has_neutral = any(kw in t for kw in _FEEDBACK_NEUTRAL)

        if has_pos and has_neg:
            return "mixed"
        if has_pos:
            return "better"
        if has_neg:
            return "worse"
        if has_neutral:
            return "no_change"
        return "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Target-issue inference from changed setup fields
# ---------------------------------------------------------------------------

_FIELD_TO_TARGET = {
    # exit traction / wheelspin
    "lsd_accel": TARGET_EXIT_TRACTION,
    "lsd_initial": TARGET_EXIT_TRACTION,
    "aero_rear": TARGET_EXIT_TRACTION,
    "arb_rear": TARGET_EXIT_TRACTION,
    "torque_distribution_rear": TARGET_EXIT_TRACTION,
    # bottoming / ride height / platform
    "ride_height_front": TARGET_BOTTOMING,
    "ride_height_rear": TARGET_BOTTOMING,
    "springs_front": TARGET_BOTTOMING,
    "springs_rear": TARGET_BOTTOMING,
    "damper_compression_front": TARGET_BOTTOMING,
    "damper_compression_rear": TARGET_BOTTOMING,
    # brake stability
    "brake_bias": TARGET_BRAKE_STABILITY,
    "brake_balance": TARGET_BRAKE_STABILITY,
    # rotation
    "aero_front": TARGET_ROTATION,
    "arb_front": TARGET_ROTATION,
    "lsd_decel": TARGET_ROTATION,
}


def infer_target_issue_from_fields(fields) -> str:
    """Infer the primary issue a set of changed fields was intended to address.

    Returns a TARGET_* identifier.  When the fields map to more than one issue
    the traction/stability issue wins (it is the highest-priority safety concern
    for the Setup Brain).  Unknown fields → TARGET_UNKNOWN.  Never raises.
    """
    try:
        found = {
            _FIELD_TO_TARGET[f]
            for f in (fields or [])
            if f in _FIELD_TO_TARGET
        }
        if not found:
            return TARGET_UNKNOWN
        # Priority order: traction/stability first, then platform, brakes, rotation.
        for target in (TARGET_EXIT_TRACTION, TARGET_BOTTOMING,
                       TARGET_BRAKE_STABILITY, TARGET_ROTATION):
            if target in found:
                return target
        return TARGET_UNKNOWN
    except Exception:
        return TARGET_UNKNOWN


# ---------------------------------------------------------------------------
# Core telemetry verdict per lower-is-better metric
# ---------------------------------------------------------------------------

def _metric_present(value: float) -> bool:
    try:
        return value is not None and float(value) > METRIC_ABSENT / 2  # > -0.5
    except (TypeError, ValueError):
        return False


def _metric_direction(before: float, after: float) -> "str | None":
    """Classify a lower-is-better metric movement.

    Returns 'improved' | 'worse' | 'unchanged', or None when either side is
    unmeasured (METRIC_ABSENT).  Never raises.
    """
    if not (_metric_present(before) and _metric_present(after)):
        return None
    try:
        b = float(before)
        a = float(after)
    except (TypeError, ValueError):
        return None
    band = max(_BAND_ABS, _BAND_REL * b)
    delta = a - b
    if delta < -band:
        return "improved"
    if delta > band:
        return "worse"
    return "unchanged"


# (primary attr, secondary attr | None) per target
_TARGET_METRICS = {
    TARGET_EXIT_TRACTION: ("wheelspin", "oversteer_throttle"),
    TARGET_BOTTOMING: ("bottoming", None),
    TARGET_BRAKE_STABILITY: ("lock_up", "brake_consistency"),
    TARGET_ROTATION: ("oversteer", None),
}

# Safety monitors: metrics whose regression counts as "introduced a new problem"
# even when they are not the targeted issue.
_SAFETY_MONITORS = ("wheelspin", "lock_up", "bottoming")


def _telemetry_outcome(
    target_issue: str,
    before: MetricSnapshot,
    after: MetricSnapshot,
) -> "tuple[OutcomeVerdict, float, float, str, bool]":
    """Return (verdict, before_metric, after_metric, evidence, safety_regression).

    Pure telemetry classification, before driver feedback is folded in.
    safety_regression is True when a safety-monitor metric worsened.
    """
    metrics = _TARGET_METRICS.get(target_issue)
    if metrics is None:
        return (OutcomeVerdict.INSUFFICIENT_EVIDENCE, METRIC_ABSENT, METRIC_ABSENT,
                "no telemetry signal exists for this issue", False)

    primary_attr, secondary_attr = metrics
    b_primary = getattr(before, primary_attr)
    a_primary = getattr(after, primary_attr)

    primary_dir = _metric_direction(b_primary, a_primary)
    if primary_dir is None:
        return (OutcomeVerdict.INSUFFICIENT_EVIDENCE, b_primary, a_primary,
                f"{primary_attr} not measured on both sides", False)

    # Secondary metric (optional) — used for MIXED detection within the same issue.
    secondary_dir = None
    if secondary_attr is not None:
        secondary_dir = _metric_direction(
            getattr(before, secondary_attr), getattr(after, secondary_attr)
        )

    # Cross-issue "new problem" detection: any OTHER safety monitor worsening.
    new_problem_attr = None
    for mon in _SAFETY_MONITORS:
        if mon == primary_attr:
            continue
        d = _metric_direction(getattr(before, mon), getattr(after, mon))
        if d == "worse":
            new_problem_attr = mon
            break

    safety_regression = (primary_dir == "worse") or (new_problem_attr is not None)

    # Assemble evidence text.
    ev = f"{primary_attr} {_fmt(b_primary)}→{_fmt(a_primary)}/lap ({primary_dir})"
    if secondary_attr is not None and secondary_dir is not None:
        ev += (f"; {secondary_attr} "
               f"{_fmt(getattr(before, secondary_attr))}→"
               f"{_fmt(getattr(after, secondary_attr))}/lap ({secondary_dir})")
    if new_problem_attr is not None:
        ev += (f"; new problem: {new_problem_attr} worsened "
               f"{_fmt(getattr(before, new_problem_attr))}→"
               f"{_fmt(getattr(after, new_problem_attr))}/lap")

    # Decide verdict.
    if primary_dir == "improved":
        if secondary_dir == "worse" or new_problem_attr is not None:
            verdict = OutcomeVerdict.MIXED
        else:
            verdict = OutcomeVerdict.IMPROVED
    elif primary_dir == "worse":
        if secondary_dir == "improved":
            verdict = OutcomeVerdict.MIXED
        else:
            verdict = OutcomeVerdict.WORSE
    else:  # primary unchanged
        if new_problem_attr is not None:
            verdict = OutcomeVerdict.MIXED
        elif secondary_dir == "improved":
            verdict = OutcomeVerdict.IMPROVED
        elif secondary_dir == "worse":
            verdict = OutcomeVerdict.WORSE
        else:
            verdict = OutcomeVerdict.UNCHANGED

    return (verdict, b_primary, a_primary, ev, safety_regression)


def _fmt(v: float) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "?"


# ---------------------------------------------------------------------------
# Public: verify_outcome
# ---------------------------------------------------------------------------

def verify_outcome(
    *,
    rule_id: str,
    car_id: int,
    track: str,
    layout_id: str,
    target_issue: str,
    before: MetricSnapshot,
    after: MetricSnapshot,
    driver_feedback: str = "",
) -> OutcomeVerificationResult:
    """Classify whether an applied change fixed its targeted issue.

    Telemetry is primary and safety-first; driver feedback is folded in as
    supporting evidence that can never override a telemetry safety regression and
    never manufactures an "improved" verdict on its own.  Returns
    INSUFFICIENT_EVIDENCE whenever the required signal is unavailable.

    Never raises.
    """
    fb_raw = driver_feedback or ""

    def _result(outcome: OutcomeVerdict, before_m: float, after_m: float,
                confidence: float, evidence: str, safety: str) -> OutcomeVerificationResult:
        return OutcomeVerificationResult(
            rule_id=rule_id or "",
            car_id=int(car_id or 0),
            track=track or "",
            layout_id=layout_id or "",
            target_issue=target_issue or TARGET_UNKNOWN,
            before_metric=before_m,
            after_metric=after_m,
            driver_feedback=fb_raw,
            outcome=outcome,
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            evidence_summary=evidence,
            safety_notes=safety,
        )

    try:
        fb = classify_driver_feedback(fb_raw)

        # Gate: unsupported target (no telemetry signal → honest INSUFFICIENT).
        if target_issue in _UNSUPPORTED_TARGETS:
            return _result(
                OutcomeVerdict.INSUFFICIENT_EVIDENCE, METRIC_ABSENT, METRIC_ABSENT, 0.0,
                "no deterministic telemetry signal exists for this issue "
                "(steering-angle / front-bite metrics are not measured)",
                "verdict withheld — invents no metric",
            )

        # Gate: minimum clean laps on each side.
        if before.clean_laps < MIN_CLEAN_LAPS or after.clean_laps < MIN_CLEAN_LAPS:
            return _result(
                OutcomeVerdict.INSUFFICIENT_EVIDENCE, METRIC_ABSENT, METRIC_ABSENT, 0.0,
                f"insufficient clean laps (before={before.clean_laps}, "
                f"after={after.clean_laps}, need ≥{MIN_CLEAN_LAPS} each)",
                "verdict withheld — thin sample",
            )

        base, before_m, after_m, evidence, safety_regression = _telemetry_outcome(
            target_issue, before, after
        )

        if base == OutcomeVerdict.INSUFFICIENT_EVIDENCE:
            # Telemetry absent for the target metric.  Feedback alone must NOT
            # author a verdict — learning stays put.
            note = "verdict withheld — required telemetry metric unavailable"
            if fb in ("better", "worse", "mixed"):
                evidence = f"{evidence}; driver feedback '{fb_raw}' recorded as evidence only"
            return _result(OutcomeVerdict.INSUFFICIENT_EVIDENCE, before_m, after_m,
                           0.0, evidence, note)

        # ---- confidence base from telemetry ----
        thin = min(before.clean_laps, after.clean_laps)
        conf = 0.6 if base in (OutcomeVerdict.IMPROVED, OutcomeVerdict.WORSE) else 0.4
        if base == OutcomeVerdict.MIXED:
            conf = 0.35
        if thin >= 6:
            conf += 0.1
        elif thin <= MIN_CLEAN_LAPS:
            conf -= 0.1

        safety_notes = ""
        outcome = base

        # ---- fold in driver feedback (evidence, never authority) ----
        if fb == "mixed":
            # Contradictory feedback → never a clean improvement.
            if outcome == OutcomeVerdict.IMPROVED:
                outcome = OutcomeVerdict.MIXED
            safety_notes = "driver feedback contradictory — treated as mixed evidence"
            conf = min(conf, 0.45)
        elif fb == "better":
            if outcome == OutcomeVerdict.IMPROVED:
                conf += 0.15  # telemetry + feedback agree → stronger (bounded) upgrade
            elif outcome == OutcomeVerdict.WORSE or safety_regression:
                # Positive feedback CANNOT override a telemetry safety regression.
                safety_notes = ("positive driver feedback NOT applied — telemetry shows a "
                                "safety regression (telemetry wins)")
                conf = max(conf, 0.5)
            # UNCHANGED + better → stays UNCHANGED (feedback alone never upgrades).
        elif fb == "worse":
            if outcome == OutcomeVerdict.IMPROVED:
                # Telemetry improved but driver unhappy → conflicting → mixed.
                outcome = OutcomeVerdict.MIXED
                safety_notes = "telemetry improved but driver reports worse — conflicting"
                conf = min(conf, 0.45)
            elif outcome == OutcomeVerdict.UNCHANGED:
                # Negative feedback with flat telemetry → downgrade (feedback-driven).
                outcome = OutcomeVerdict.WORSE
                safety_notes = "flat telemetry, driver reports worse — feedback-driven downgrade"
                conf = min(conf, 0.5)
            elif outcome == OutcomeVerdict.WORSE:
                conf += 0.15  # telemetry + feedback agree it got worse
        # fb == 'no_change' or 'unknown' → no adjustment (vague ⇒ weak learning).

        if safety_regression and not safety_notes:
            safety_notes = "telemetry safety-monitor regression detected"

        return _result(outcome, before_m, after_m, conf, evidence, safety_notes)

    except Exception as exc:
        return _result(
            OutcomeVerdict.INSUFFICIENT_EVIDENCE, METRIC_ABSENT, METRIC_ABSENT, 0.0,
            f"verification error: {exc}", "verdict withheld — internal error",
        )


# ---------------------------------------------------------------------------
# Verdict bridge to the Group 46 learning vocabulary
# ---------------------------------------------------------------------------

_OUTCOME_TO_VERDICT = {
    OutcomeVerdict.IMPROVED: "improved",
    OutcomeVerdict.WORSE: "worsened",
    OutcomeVerdict.UNCHANGED: "neutral",
    OutcomeVerdict.MIXED: "neutral",                       # never boosts confidence
    OutcomeVerdict.INSUFFICIENT_EVIDENCE: "insufficient_data",  # skipped by the feed
}


def outcome_to_learning_verdict(outcome: OutcomeVerdict) -> str:
    """Map an OutcomeVerdict onto the persisted learning verdict vocabulary.

    Bridge invariants that keep learning safe:
      • MIXED → 'neutral' (fire-only): never upgrades confidence.
      • INSUFFICIENT_EVIDENCE → 'insufficient_data': the feed skips it entirely.
      • Only IMPROVED → 'improved' can drive an upgrade; only WORSE → 'worsened'
        lowers the success rate (a downgrade), both capped ±1 step by the engine.
    """
    return _OUTCOME_TO_VERDICT.get(outcome, "insufficient_data")


# ---------------------------------------------------------------------------
# Explainability formatter (pure)
# ---------------------------------------------------------------------------

def format_learning_outcome_explanation(
    outcomes: list,
    *,
    min_samples: int = 1,
) -> str:
    """Render a short, honest 'Learning outcome' explanation from stored rows.

    *outcomes* is a list of learning_outcomes row dicts (as returned by
    SessionDB.get_learning_outcomes).  Groups by rule_id, counts improved vs
    total scored samples, and states the confidence effect — always with the
    disclaimer that learning affects confidence/ranking only.

    Returns '' when there is nothing meaningful to say.  Never raises.
    """
    try:
        if not outcomes:
            return ""

        # Aggregate per rule_id, skipping insufficient_data (no signal).
        agg: dict = {}
        for row in outcomes:
            try:
                rid = (row.get("rule_id") or "").strip()
                verdict = (row.get("verdict") or "").strip()
                if not rid or verdict == "insufficient_data" or not verdict:
                    continue
                entry = agg.setdefault(rid, {
                    "improved": 0, "worsened": 0, "neutral": 0, "total": 0,
                    "target_issue": (row.get("target_issue") or "").strip(),
                })
                if verdict == "improved":
                    entry["improved"] += 1
                elif verdict == "worsened":
                    entry["worsened"] += 1
                else:
                    entry["neutral"] += 1
                entry["total"] += 1
                if not entry["target_issue"]:
                    entry["target_issue"] = (row.get("target_issue") or "").strip()
            except Exception:
                continue

        lines: list[str] = []
        for rid, e in agg.items():
            if e["total"] < min_samples:
                continue
            issue = e["target_issue"] or "the targeted issue"
            issue_h = issue.replace("_", " ")
            if e["improved"] > e["worsened"] and e["improved"] >= 1:
                effect = "Confidence may be upgraded one step."
                verb = "improved"
                n = e["improved"]
            elif e["worsened"] > e["improved"] and e["worsened"] >= 1:
                effect = "Confidence may be downgraded one step; risky changes stay gated."
                verb = "worsened"
                n = e["worsened"]
            else:
                effect = "Confidence unchanged (no clear trend)."
                verb = "showed no clear change to"
                n = e["total"]
            lines.append(
                f"Rule {rid}: previous changes {verb} {issue_h} in "
                f"{n} of {e['total']} scored sample(s). {effect}"
            )

        if not lines:
            return ""

        header = "Learning outcome:"
        disclaimer = ("This adjusts confidence/ranking and explanation only — it "
                      "does not author setup values or bypass validation.")
        return header + "\n" + "\n".join(lines) + "\n" + disclaimer
    except Exception:
        return ""
