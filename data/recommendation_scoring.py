"""OFR-1 Between-Race Learning Loop — pure scoring logic.

WHY IT EXISTS
  After a setup recommendation has been applied and at least one session
  driven with the new setup, this module self-scores the AI's suggestion
  against measured before/after lap telemetry.  The result is persisted by
  SessionDB.persist_score() (write-once) and later formatted as a §6.4
  'Performance of Previous Recommendations' block that feeds back into the
  next setup-advice prompt.

PURITY CONTRACT
  • No PyQt6, no sqlite3, no file I/O.
  • Never raises — every public function wraps its internals in try/except
    and returns a safe fallback value.
  • No tyre-radius fields.

HONESTY GATES
  • Fewer than 3 clean laps on either side → 'insufficient_data', confidence 0.0.
  • Missing/empty/unparsable before_metrics AND no before-session lap rows
    → 'insufficient_data', confidence 0.0.
  Fabrication of verdicts is explicitly forbidden.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from statistics import mean as _mean
from typing import Any


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LapWindow:
    """Aggregated view of a set of lap-record rows from one session side."""

    laps: list          # raw row dicts (all laps, including pit/out)
    clean_count: int    # laps where is_pit_lap=0 AND is_out_lap=0
    compound: str       # majority compound among clean laps ('' if mixed/absent)
    best_clean_ms: int  # best clean lap time in ms (0 when clean_count == 0)
    avg_lock_up: float  # mean lock_up_count per clean lap
    avg_wheelspin: float
    avg_oversteer: float        # oversteer_count per clean lap
    avg_oversteer_throttle: float  # oversteer_throttle_on per clean lap
    avg_bottoming: float
    avg_brake_consistency: float  # brake_consistency_m per clean lap (lower=better)


@dataclass(frozen=True)
class ScoringResult:
    """Outcome of scoring one recommendation against before/after telemetry."""

    rec_id: int
    verdict: str    # 'improved' | 'worsened' | 'neutral' | 'insufficient_data'
    confidence: float   # 0.0–1.0
    details: dict   # JSON-serialisable: lap-time delta, per-event rate deltas,
                    # clean-lap counts, compounds, target classification,
                    # assumptions note.


# ---------------------------------------------------------------------------
# Helper: aggregate a set of lap rows into a LapWindow
# ---------------------------------------------------------------------------

def aggregate_lap_window(
    lap_rows: list[dict],
    *,
    exclude_pit: bool = True,
    exclude_out: bool = True,
) -> LapWindow:
    """Build a LapWindow from raw lap_record dicts.

    Defensive on missing keys — any absent field is treated as 0 / empty.
    Never raises.
    """
    try:
        def _int(row: dict, key: str) -> int:
            try:
                return int(row.get(key) or 0)
            except (TypeError, ValueError):
                return 0

        def _float(row: dict, key: str) -> float:
            try:
                v = row.get(key)
                return float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        clean: list[dict] = []
        for row in (lap_rows or []):
            pit = _int(row, "is_pit_lap")
            out = _int(row, "is_out_lap")
            if exclude_pit and pit:
                continue
            if exclude_out and out:
                continue
            clean.append(row)

        clean_count = len(clean)

        # Best clean lap time
        times = [_int(r, "lap_time_ms") for r in clean if _int(r, "lap_time_ms") > 0]
        best_clean_ms = min(times) if times else 0

        # Majority compound
        compound_votes: dict[str, int] = {}
        for r in clean:
            c = (r.get("compound") or "").strip()
            if c:
                compound_votes[c] = compound_votes.get(c, 0) + 1
        if compound_votes:
            top = max(compound_votes, key=lambda k: compound_votes[k])
            majority = compound_votes[top]
            total_with_compound = sum(compound_votes.values())
            compound = top if (majority / total_with_compound) >= 0.6 else ""
        else:
            compound = ""

        # Per-lap event rates
        def _avg_field(field_name: str) -> float:
            if not clean:
                return 0.0
            vals = [_float(r, field_name) for r in clean]
            return _mean(vals) if vals else 0.0

        avg_lock_up             = _avg_field("lock_up_count")
        avg_wheelspin           = _avg_field("wheelspin_count")
        avg_oversteer           = _avg_field("oversteer_count")
        avg_oversteer_throttle  = _avg_field("oversteer_throttle_on")
        avg_bottoming           = _avg_field("bottoming_count")
        avg_brake_consistency   = _avg_field("brake_consistency_m")

        return LapWindow(
            laps=list(lap_rows or []),
            clean_count=clean_count,
            compound=compound,
            best_clean_ms=best_clean_ms,
            avg_lock_up=avg_lock_up,
            avg_wheelspin=avg_wheelspin,
            avg_oversteer=avg_oversteer,
            avg_oversteer_throttle=avg_oversteer_throttle,
            avg_bottoming=avg_bottoming,
            avg_brake_consistency=avg_brake_consistency,
        )
    except Exception:
        return LapWindow(
            laps=[],
            clean_count=0,
            compound="",
            best_clean_ms=0,
            avg_lock_up=0.0,
            avg_wheelspin=0.0,
            avg_oversteer=0.0,
            avg_oversteer_throttle=0.0,
            avg_bottoming=0.0,
            avg_brake_consistency=0.0,
        )


# ---------------------------------------------------------------------------
# Helper: classify what a recommendation targets
# ---------------------------------------------------------------------------

_HANDLING_KEYWORDS = frozenset([
    "understeer", "oversteer", "wheelspin", "traction", "stability",
    "lock-up", "lockup", "locking", "snap", "bottoming", "rotation", "grip",
])


def classify_why_text(why: str) -> str:
    """Return 'handling' if *why* mentions any handling keyword, else 'laptime'.

    Case-insensitive; None-safe; never raises.
    """
    try:
        if not why:
            return "laptime"
        text = why.lower()
        for kw in _HANDLING_KEYWORDS:
            if kw in text:
                return "handling"
        return "laptime"
    except Exception:
        return "laptime"


def _classify_rec(rec: dict) -> str:
    """Derive target type from the recommendation's changes list.

    Parses recommendation_text as AI JSON expecting
    {"changes": [{"field": ..., "why": ...}, ...]}.
    Any unparsable content is treated as 'laptime'.
    """
    try:
        text = rec.get("recommendation_text") or ""
        data = json.loads(text)
        changes = data.get("changes", [])
        if not isinstance(changes, list) or not changes:
            return "laptime"
        # Any handling keyword in any why-text → 'handling'
        for change in changes:
            why = change.get("why") or ""
            if classify_why_text(str(why)) == "handling":
                return "handling"
        return "laptime"
    except Exception:
        return "laptime"


# ---------------------------------------------------------------------------
# Core: compute verdict and confidence
# ---------------------------------------------------------------------------

def compute_verdict_and_confidence(
    rec: dict,
    before_window: LapWindow,
    after_window: LapWindow,
    *,
    multi_rec_count: int = 1,
    has_driver_feedback: bool = False,
) -> ScoringResult:
    """Score one recommendation against before/after lap windows.

    HONESTY GATES (returns insufficient_data, confidence 0.0):
      1. before_metrics missing / '{}' / unparsable AND before_window has 0
         clean laps.
      2. clean_count < 3 on either window.

    VERDICT RULES:
      improved  — laptime target AND Δt < −200 ms
                  OR handling target AND agreement ≥ 0.6 AND Δt ≤ +100 ms
      worsened  — Δt > +300 ms
                  OR (handling target AND agreement < 0.3 AND Δt > 0)
      neutral   — all other cases incl. mixed signal (Δt < −200 but handling
                  clearly worsened: agreement < 0.3)

    CONFIDENCE:
      Starts at 1.0.
      −0.1 per clean lap below 6 on EACH side (floor 0 per side deduction).
      −0.15 if lap-time direction and handling direction disagree.
      +0.1 if has_driver_feedback.
      × (1 / multi_rec_count) attribution split.
      Clamped [0.0, 1.0].
      insufficient_data always → 0.0.

    Never raises — returns ScoringResult with 'insufficient_data' on any error.
    """
    rec_id = int(rec.get("id") or 0)

    try:
        # ------------------------------------------------------------------
        # Gate 1: before-window data availability
        # ------------------------------------------------------------------
        before_metrics_raw = rec.get("before_metrics") or "{}"
        try:
            before_metrics: dict = json.loads(before_metrics_raw)
            if not isinstance(before_metrics, dict):
                before_metrics = {}
        except Exception:
            before_metrics = {}

        before_has_rows = before_window.clean_count > 0
        before_metrics_missing = not before_metrics or before_metrics == {}

        if before_metrics_missing and not before_has_rows:
            return ScoringResult(
                rec_id=rec_id,
                verdict="insufficient_data",
                confidence=0.0,
                details={
                    "reason": "no before_metrics and no before-session laps",
                    "before_source": "creation_session",
                },
            )

        # ------------------------------------------------------------------
        # Gate 2: minimum 3 clean laps on each side
        # ------------------------------------------------------------------
        if before_window.clean_count < 3 or after_window.clean_count < 3:
            return ScoringResult(
                rec_id=rec_id,
                verdict="insufficient_data",
                confidence=0.0,
                details={
                    "reason": "insufficient clean laps",
                    "before_clean_laps": before_window.clean_count,
                    "after_clean_laps": after_window.clean_count,
                    "before_source": "creation_session",
                },
            )

        # ------------------------------------------------------------------
        # Best lap delta
        # ------------------------------------------------------------------
        # Prefer real before lap rows; fall back to before_metrics.best_lap_ms
        if before_window.best_clean_ms > 0:
            before_best_ms = before_window.best_clean_ms
            before_best_source = "lap_rows"
        else:
            before_best_ms = int(before_metrics.get("best_lap_ms") or 0)
            before_best_source = "before_metrics"

        after_best_ms = after_window.best_clean_ms

        delta_ms: int = 0
        if before_best_ms > 0 and after_best_ms > 0:
            delta_ms = after_best_ms - before_best_ms
        elif after_best_ms > 0 and before_best_ms == 0:
            # Can't compute delta without a before reference
            delta_ms = 0

        # ------------------------------------------------------------------
        # Target classification
        # ------------------------------------------------------------------
        target = _classify_rec(rec)

        # ------------------------------------------------------------------
        # Handling metric deltas (handling targets only)
        # ------------------------------------------------------------------
        # Each metric: (before_rate, after_rate, lower_is_better)
        handling_metrics = [
            ("lock_up",             before_window.avg_lock_up,            after_window.avg_lock_up,            True),
            ("wheelspin",           before_window.avg_wheelspin,          after_window.avg_wheelspin,          True),
            ("oversteer",           before_window.avg_oversteer,          after_window.avg_oversteer,          True),
            ("oversteer_throttle",  before_window.avg_oversteer_throttle, after_window.avg_oversteer_throttle, True),
            ("bottoming",           before_window.avg_bottoming,          after_window.avg_bottoming,          True),
            ("brake_consistency",   before_window.avg_brake_consistency,  after_window.avg_brake_consistency,  True),
        ]

        # Directional agreement: only count metrics where either side is nonzero
        relevant_count = 0
        improved_count = 0
        metric_deltas: dict[str, float] = {}

        for name, b_val, a_val, lower_better in handling_metrics:
            delta = a_val - b_val
            metric_deltas[f"{name}_before"] = round(b_val, 3)
            metric_deltas[f"{name}_after"]  = round(a_val, 3)
            metric_deltas[f"{name}_delta"]  = round(delta, 3)
            if b_val > 0 or a_val > 0:
                relevant_count += 1
                # lower_better=True: negative delta is good
                if lower_better and delta < 0:
                    improved_count += 1
                elif not lower_better and delta > 0:
                    improved_count += 1

        handling_agreement = (
            improved_count / relevant_count if relevant_count > 0 else 0.5
        )

        # ------------------------------------------------------------------
        # Verdict
        # ------------------------------------------------------------------
        lt_improved  = delta_ms < -200
        lt_worsened  = delta_ms > 300
        lt_neutral_ok = delta_ms <= 100   # used in handling improved check

        if target == "laptime":
            if lt_improved:
                verdict = "improved"
            elif lt_worsened:
                verdict = "worsened"
            else:
                verdict = "neutral"
        else:  # handling target
            handling_improved = handling_agreement >= 0.6 and lt_neutral_ok
            handling_worsened = handling_agreement < 0.3 and delta_ms > 0

            if handling_improved:
                # Mixed-signal override: laptime clearly improved but handling
                # clearly worsened → neutral (mixed)
                if lt_improved and handling_agreement < 0.3:
                    verdict = "neutral"
                else:
                    verdict = "improved"
            elif handling_worsened or lt_worsened:
                verdict = "worsened"
            else:
                verdict = "neutral"

        # ------------------------------------------------------------------
        # Confidence
        # ------------------------------------------------------------------
        conf = 1.0

        # Deduct for thin lap counts (per side, floor 0 per side)
        for clean_laps in (before_window.clean_count, after_window.clean_count):
            shortfall = max(0, 6 - clean_laps)
            conf -= 0.1 * shortfall

        # Deduct if lap-time direction and handling direction disagree
        laptime_direction = (
            "improved" if lt_improved else ("worsened" if lt_worsened else "neutral")
        )
        handling_direction = (
            "improved" if handling_agreement >= 0.6
            else ("worsened" if handling_agreement < 0.3 else "neutral")
        )
        if laptime_direction != handling_direction and "neutral" not in (
            laptime_direction, handling_direction
        ):
            conf -= 0.15

        # Feedback bonus
        if has_driver_feedback:
            conf += 0.1

        # Attribution split
        safe_multi = max(1, int(multi_rec_count))
        conf = conf / safe_multi

        # Clamp
        conf = max(0.0, min(1.0, conf))

        # ------------------------------------------------------------------
        # Build details dict (JSON-serialisable)
        # ------------------------------------------------------------------
        details: dict[str, Any] = {
            "before_source":         "creation_session",
            "assumptions_note":      (
                "before_session = rec creation session (may pre-date application by design)"
            ),
            "target":                target,
            "delta_ms":              delta_ms,
            "before_best_ms":        before_best_ms,
            "after_best_ms":         after_best_ms,
            "before_best_source":    before_best_source,
            "before_clean_laps":     before_window.clean_count,
            "after_clean_laps":      after_window.clean_count,
            "before_compound":       before_window.compound,
            "after_compound":        after_window.compound,
            "handling_agreement":    round(handling_agreement, 3),
            "relevant_metrics":      relevant_count,
            "improved_metrics":      improved_count,
        }
        details.update(metric_deltas)

        return ScoringResult(
            rec_id=rec_id,
            verdict=verdict,
            confidence=round(conf, 4),
            details=details,
        )

    except Exception as exc:
        return ScoringResult(
            rec_id=rec_id,
            verdict="insufficient_data",
            confidence=0.0,
            details={"reason": f"scoring error: {exc}", "before_source": "creation_session"},
        )


# ---------------------------------------------------------------------------
# Formatter: §6.4 plain-English performance block
# ---------------------------------------------------------------------------

def format_performance_block(
    scored_recs: list[dict],
    *,
    confidence_threshold: float = 0.5,
) -> str:
    """Format a §6.4 'Performance of Previous Recommendations' block.

    One entry per qualifying rec: score_verdict present, not 'insufficient_data',
    confidence ≥ confidence_threshold.  Returns '' when none qualify.

    Reads score_details JSON for lap-delta and per-event rates.
    Never raises on malformed rows.
    """
    try:
        qualifying: list[dict] = []
        for rec in (scored_recs or []):
            try:
                verdict = rec.get("score_verdict") or ""
                if not verdict or verdict == "insufficient_data":
                    continue
                conf = float(rec.get("score_confidence") or -1.0)
                if conf < confidence_threshold:
                    continue
                qualifying.append(rec)
            except Exception:
                continue

        if not qualifying:
            return ""

        lines: list[str] = [
            "## Performance of Previous Recommendations (this car + track)"
        ]

        for rec in qualifying:
            try:
                # Parse details
                details_raw = rec.get("score_details") or "{}"
                try:
                    details: dict = json.loads(details_raw)
                    if not isinstance(details, dict):
                        details = {}
                except Exception:
                    details = {}

                verdict = rec.get("score_verdict") or ""
                conf    = float(rec.get("score_confidence") or 0.0)

                # Describe the change from recommendation_text
                rec_text = rec.get("recommendation_text") or ""
                change_desc = ""
                try:
                    data = json.loads(rec_text)
                    changes = data.get("changes", [])
                    if isinstance(changes, list) and changes:
                        parts = []
                        for ch in changes[:3]:  # limit verbosity
                            f_ = ch.get("field", "?")
                            fr_ = ch.get("from", "?")
                            to_ = ch.get("to", "?")
                            why_ = ch.get("why", "")
                            desc = f"{f_} {fr_} → {to_}"
                            if why_:
                                desc += f" (expected: {why_})"
                            parts.append(desc)
                        change_desc = "; ".join(parts)
                except Exception:
                    # Fallback: use truncated raw text
                    change_desc = rec_text[:120].replace("\n", " ")

                lines.append(f"Setup change: {change_desc}")

                # Measured outcomes
                delta_ms   = details.get("delta_ms")
                measured_parts: list[str] = []

                if delta_ms is not None:
                    delta_s = delta_ms / 1000.0
                    measured_parts.append(f"best lap {delta_s:+.2f}s")

                # Handling rate pairs (before→after/lap)
                for metric_key, label in [
                    ("lock_up",            "lock-ups"),
                    ("wheelspin",          "wheelspin"),
                    ("oversteer",          "oversteer"),
                    ("bottoming",          "bottoming"),
                    ("brake_consistency",  "brake consistency (m)"),
                ]:
                    b_val = details.get(f"{metric_key}_before")
                    a_val = details.get(f"{metric_key}_after")
                    if b_val is None or a_val is None:
                        continue
                    delta_v = a_val - b_val
                    if abs(delta_v) < 0.01 and abs(b_val) < 0.01:
                        measured_parts.append(f"{label} unchanged")
                    else:
                        measured_parts.append(
                            f"{label} {b_val:.1f}→{a_val:.1f}/lap"
                        )

                measured_str = "; ".join(measured_parts) if measured_parts else "no metrics"
                lines.append(f"  Measured: {measured_str}")
                lines.append(f"  Verdict: {verdict} (confidence {conf:.2f})")

            except Exception:
                continue  # skip malformed rows silently

        if len(lines) <= 1:
            # Only header, no valid entries rendered
            return ""

        return "\n".join(lines) + "\n"

    except Exception:
        return ""
