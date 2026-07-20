"""Cross-session setup verdict (pure, deterministic).

Holistic brain, Phase 3. Compares a setup revision against the previous one using
everything the app now collects — lap-time deltas, per-corner apex-speed deltas
(from the Phase 1 extraction), slip counts, the actual changes made, and the
driver's own vs-previous feedback — into ONE honest engineer summary:

  "Softer rear ARB, +2 front wing → best lap −0.31s. T4 exit +6 km/h (rear
   wheelspin −0.8/lap) and T7 +4 km/h; T1 entry −3 km/h (more understeer).
   You reported it felt 'better' — telemetry agrees. Net: improved."

Correlation, not proof: the engine pairs the biggest corner deltas with the
changes and feedback and says so plainly. Pure — no Qt, no DB; the caller
assembles the two SetupRunSummary objects from the DB + extraction pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


# Thresholds
LAP_IMPROVE_MS = 100          # best/avg lap delta to count as a real move
APEX_DELTA_KMH = 1.5          # per-corner apex speed delta to call better/worse
MIN_LAPS = 3                  # per setup, before drawing a verdict


class SetupOverall(str, Enum):
    IMPROVED = "improved"
    WORSENED = "worsened"
    MIXED = "mixed"
    INSUFFICIENT = "insufficient"


class FeedbackAgreement(str, Enum):
    NONE = "none"
    AGREES = "agrees"
    CONTRADICTS = "contradicts"


@dataclass(frozen=True)
class SetupRunSummary:
    label: str
    laps: int
    best_ms: int
    avg_ms: int
    per_corner_apex_kmh: Mapping[str, float] = field(default_factory=dict)
    avg_wheelspin: float = 0.0
    avg_lockup: float = 0.0


@dataclass(frozen=True)
class CornerDelta:
    corner_name: str
    apex_speed_delta_kmh: float   # cur - prev (positive = faster)
    verdict: str                  # better | worse | similar


@dataclass(frozen=True)
class SetupVerdict:
    prev_label: str
    cur_label: str
    overall: SetupOverall
    best_lap_delta_ms: int        # cur - prev (negative = improvement)
    avg_lap_delta_ms: int
    corner_deltas: Tuple[CornerDelta, ...]
    reasons: Tuple[str, ...]
    feedback_agreement: FeedbackAgreement

    @property
    def better_corners(self) -> Tuple[CornerDelta, ...]:
        return tuple(c for c in self.corner_deltas if c.verdict == "better")

    @property
    def worse_corners(self) -> Tuple[CornerDelta, ...]:
        return tuple(c for c in self.corner_deltas if c.verdict == "worse")

    def headline(self) -> str:
        d = self.best_lap_delta_ms
        sign = "-" if d < 0 else "+"
        return (f"{self.cur_label} vs {self.prev_label}: best lap "
                f"{sign}{abs(d)/1000:.2f}s → {self.overall.value}.")


def _fmt_changes(changes: Sequence) -> str:
    parts = []
    for ch in (changes or []):
        if isinstance(ch, dict):
            field_name = ch.get("setting") or ch.get("field") or "?"
            frm, to = ch.get("from"), ch.get("to")
            parts.append(f"{field_name} {frm}→{to}" if frm is not None else str(field_name))
        else:
            parts.append(str(ch))
    return ", ".join(parts)


def compare_setups(
    prev: SetupRunSummary,
    cur: SetupRunSummary,
    *,
    changes: Sequence = (),
    feedback_vs_previous: str = "",
) -> SetupVerdict:
    """Compare the current setup run against the previous one."""
    reasons: List[str] = []

    if prev.laps < MIN_LAPS or cur.laps < MIN_LAPS:
        return SetupVerdict(
            prev_label=prev.label, cur_label=cur.label,
            overall=SetupOverall.INSUFFICIENT,
            best_lap_delta_ms=(cur.best_ms - prev.best_ms) if (prev.best_ms and cur.best_ms) else 0,
            avg_lap_delta_ms=0, corner_deltas=(),
            reasons=(f"Not enough laps to judge ({prev.laps} vs {cur.laps}; "
                     f"need {MIN_LAPS} each).",),
            feedback_agreement=FeedbackAgreement.NONE)

    best_delta = int(cur.best_ms - prev.best_ms) if (prev.best_ms and cur.best_ms) else 0
    avg_delta = int(cur.avg_ms - prev.avg_ms) if (prev.avg_ms and cur.avg_ms) else 0

    # Per-corner apex deltas.
    corner_deltas: List[CornerDelta] = []
    for name, cur_apex in cur.per_corner_apex_kmh.items():
        if name not in prev.per_corner_apex_kmh:
            continue
        delta = round(cur_apex - prev.per_corner_apex_kmh[name], 1)
        verdict = ("better" if delta >= APEX_DELTA_KMH
                   else "worse" if delta <= -APEX_DELTA_KMH else "similar")
        corner_deltas.append(CornerDelta(name, delta, verdict))
    corner_deltas.sort(key=lambda c: c.apex_speed_delta_kmh, reverse=True)

    # Overall verdict from lap-time movement.
    best_improved = best_delta <= -LAP_IMPROVE_MS
    best_worsened = best_delta >= LAP_IMPROVE_MS
    avg_improved = avg_delta <= -LAP_IMPROVE_MS
    avg_worsened = avg_delta >= LAP_IMPROVE_MS
    if best_improved and not avg_worsened:
        overall = SetupOverall.IMPROVED
    elif best_worsened and not avg_improved:
        overall = SetupOverall.WORSENED
    else:
        overall = SetupOverall.MIXED

    # Reasons.
    if changes:
        reasons.append(f"Changes: {_fmt_changes(changes)}.")
    if best_delta:
        reasons.append(f"Best lap {'-' if best_delta < 0 else '+'}"
                       f"{abs(best_delta)/1000:.2f}s, "
                       f"average {'-' if avg_delta < 0 else '+'}{abs(avg_delta)/1000:.2f}s.")
    better = [c for c in corner_deltas if c.verdict == "better"][:3]
    worse = [c for c in corner_deltas if c.verdict == "worse"][:3]
    if better:
        reasons.append("Gained: " + ", ".join(
            f"{c.corner_name} +{c.apex_speed_delta_kmh:.0f} km/h" for c in better) + ".")
    if worse:
        reasons.append("Lost: " + ", ".join(
            f"{c.corner_name} {c.apex_speed_delta_kmh:.0f} km/h" for c in worse) + ".")
    spin_delta = round(cur.avg_wheelspin - prev.avg_wheelspin, 1)
    if abs(spin_delta) >= 0.5:
        reasons.append(
            f"Rear wheelspin {'down' if spin_delta < 0 else 'up'} "
            f"{abs(spin_delta):.1f}/lap.")
    lock_delta = round(cur.avg_lockup - prev.avg_lockup, 1)
    if abs(lock_delta) >= 0.5:
        reasons.append(
            f"Lock-ups {'down' if lock_delta < 0 else 'up'} {abs(lock_delta):.1f}/lap.")

    # Feedback agreement vs telemetry.
    fb = (feedback_vs_previous or "").strip().lower()
    agreement = FeedbackAgreement.NONE
    if fb in ("better", "worse"):
        telem_better = overall is SetupOverall.IMPROVED
        telem_worse = overall is SetupOverall.WORSENED
        if (fb == "better" and telem_better) or (fb == "worse" and telem_worse):
            agreement = FeedbackAgreement.AGREES
            reasons.append(f"You reported it felt '{fb}' — telemetry agrees.")
        elif (fb == "better" and telem_worse) or (fb == "worse" and telem_better):
            agreement = FeedbackAgreement.CONTRADICTS
            reasons.append(
                f"You reported '{fb}', but the telemetry says the opposite — "
                "worth another back-to-back run.")

    return SetupVerdict(
        prev_label=prev.label, cur_label=cur.label, overall=overall,
        best_lap_delta_ms=best_delta, avg_lap_delta_ms=avg_delta,
        corner_deltas=tuple(corner_deltas), reasons=tuple(reasons),
        feedback_agreement=agreement)
