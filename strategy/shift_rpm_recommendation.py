"""Shift-beep RPM recommendation — pure domain (UAT enhancement ENH-073-001).

WHY IT EXISTS
  The Setup Builder let the driver type a shift-beep RPM for Race and Qualifying by hand. This recommends
  one from the car's REAL data instead of a guess: GT7 broadcasts a per-car upshift-indicator band
  (``rpm_alert_max``) in telemetry — the game's own "shift here" point — and the car spec carries a
  peak-power RPM (``power_rpm``). We NEVER fabricate a curve: with none of these inputs the recommendation is
  explicitly "unknown".

DOCTRINE
  Deterministic, offline, pure; never raises. The optimal upshift point for acceleration is a property of the
  power curve, so it is essentially the SAME for Race and Qualifying — the honest race/qual difference is
  strategy (qualifying = max attack at the indicator; race = optionally a touch conservative for engine/fuel),
  NOT a different optimum. Confidence is labelled by the evidence used. No AI, no network, no DB, no Qt.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

SHIFT_RPM_RECOMMENDATION_VERSION = "shift_rpm_recommendation_v1"

# race is shifted a touch below the qualifying/optimal point — a strategy choice for engine + fuel, not a
# different optimum. Kept small and explicit.
_RACE_CONSERVATISM = 0.02


class ShiftRpmConfidence(str, Enum):
    HIGH = "high"        # GT7's own per-car rpm-alert band (measured from telemetry)
    MEDIUM = "medium"    # derived from the rev limit
    LOW = "low"          # derived from peak-power RPM only (a proxy)
    NONE = "none"        # no usable car data — no recommendation (never fabricated)


@dataclass(frozen=True)
class ShiftRpmRecommendation:
    qualifying_rpm: Optional[int]
    race_rpm: Optional[int]
    confidence: ShiftRpmConfidence
    source: str
    rationale: str

    def to_dict(self) -> dict:
        return {"qualifying_rpm": self.qualifying_rpm, "race_rpm": self.race_rpm,
                "confidence": self.confidence.value, "source": self.source, "rationale": self.rationale}


def _pos_int(x) -> Optional[int]:
    try:
        v = int(round(float(x)))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def recommend_shift_rpm(*, rpm_alert_max=None, power_rpm=None, rev_limit_rpm=None) -> ShiftRpmRecommendation:
    """Recommend the shift-beep RPM for Qualifying and Race from whatever REAL car data is available. Never
    raises. Never fabricates: with no usable input it returns an explicit 'unknown' recommendation.

    Priority of evidence:
      1. ``rpm_alert_max`` — GT7's own per-car upshift indicator (telemetry). HIGH confidence.
      2. ``rev_limit_rpm`` — shift just before the limiter. MEDIUM confidence.
      3. ``power_rpm`` — peak-power RPM; the optimal shift sits just past it. LOW confidence (a proxy).
    """
    try:
        alert = _pos_int(rpm_alert_max)
        rev = _pos_int(rev_limit_rpm)
        power = _pos_int(power_rpm)

        if alert is not None:
            qual = alert
            source = "gt7_rpm_alert"
            rationale = (f"GT7 signals the upshift for this car at {alert} rpm (its own indicator). "
                         "Qualifying shifts right at it; race is a touch below for engine/fuel margin.")
            conf = ShiftRpmConfidence.HIGH
        elif rev is not None:
            qual = int(round(rev * 0.97))
            source = "rev_limit"
            rationale = (f"No live rpm-alert yet; shifting just below the ~{rev} rpm limiter "
                         f"({qual} rpm). Drive the car so GT7 broadcasts its exact indicator to refine this.")
            conf = ShiftRpmConfidence.MEDIUM
        elif power is not None:
            qual = int(round(power * 1.05))
            source = "peak_power_proxy"
            rationale = (f"Estimated from peak power (~{power} rpm) — the optimal upshift sits just past it "
                         f"(~{qual} rpm). This is a proxy; a live rpm-alert reading will refine it.")
            conf = ShiftRpmConfidence.LOW
        else:
            return ShiftRpmRecommendation(None, None, ShiftRpmConfidence.NONE, "none",
                                          "No usable car data — drive the car so GT7 broadcasts its rpm-alert "
                                          "band, or add peak-power / rev-limit data. No value is guessed.")

        # clamp below the limiter if we know it
        if rev is not None:
            qual = min(qual, rev)
        race = int(round(qual * (1.0 - _RACE_CONSERVATISM)))
        return ShiftRpmRecommendation(qualifying_rpm=qual, race_rpm=race, confidence=conf,
                                      source=source, rationale=rationale)
    except Exception:  # pragma: no cover - defensive
        return ShiftRpmRecommendation(None, None, ShiftRpmConfidence.NONE, "error",
                                      "recommendation unavailable")


def shift_rpm_recommendation_versions() -> dict:
    return {"shift_rpm_recommendation": SHIFT_RPM_RECOMMENDATION_VERSION}
