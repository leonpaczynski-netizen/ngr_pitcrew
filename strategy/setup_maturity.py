"""Data-maturity → cold-start aggression (pure, deterministic, offline).

While a setup has little recorded data, the driver's feedback is the best signal we
have, so corrective changes should be BOLD — fix a poor setup decisively rather than
nudge it one timid step at a time. As real runs accumulate, telemetry becomes the
dominant driver and the changes taper back to the measured, single-step behaviour.

Policy (locked with Leon, 2026-07-29):
  * A "qualifying run" is a recorded run with at least MIN_CLEAN_LAPS (5) clean laps.
    A 2-lap bail-out (the setup was so bad the driver came straight in) does NOT count.
  * Full maturity is FULL_AT (3) qualifying runs. At 0 runs the corrective step is
    scaled by MAX_AGGRESSION (3x); it decays linearly to 1x at 3 runs.

The movement cap / range clamp still bound every result, so "aggressive" never means
"pinned to the mechanical limit" — bold, not reckless.
"""
from __future__ import annotations

MIN_CLEAN_LAPS: int = 5
FULL_AT: int = 3
MAX_AGGRESSION: float = 3.0


def count_qualifying_runs(clean_lap_counts, *, min_clean_laps: int = MIN_CLEAN_LAPS) -> int:
    """Number of runs that reached the clean-lap threshold.

    ``clean_lap_counts`` is an iterable of per-run clean-lap counts (ints). A run with
    fewer than ``min_clean_laps`` clean laps is ignored — a too-short run carries no
    reliable read of the setup. Pure; never raises."""
    n = 0
    for c in (clean_lap_counts or ()):
        try:
            if int(c) >= int(min_clean_laps):
                n += 1
        except (TypeError, ValueError):
            continue
    return n


def data_maturity(qualifying_runs: int, *, full_at: int = FULL_AT) -> float:
    """Maturity in [0.0, 1.0]: 0 at blank, 1.0 once ``full_at`` qualifying runs exist."""
    try:
        qr = max(0, int(qualifying_runs))
    except (TypeError, ValueError):
        qr = 0
    if full_at <= 0:
        return 1.0
    return min(qr, full_at) / float(full_at)


def cold_start_aggression(maturity: float, *, max_factor: float = MAX_AGGRESSION) -> float:
    """Corrective-step multiplier for the given maturity: ``max_factor`` at maturity 0,
    decaying linearly to 1.0 at maturity 1.0. Clamped to [1.0, max_factor]."""
    try:
        m = float(maturity)
    except (TypeError, ValueError):
        m = 1.0
    m = max(0.0, min(1.0, m))
    factor = max_factor - (max_factor - 1.0) * m
    return max(1.0, min(max_factor, factor))


def aggression_for_runs(clean_lap_counts) -> float:
    """Convenience: per-run clean-lap counts → cold-start aggression factor.

    aggression_for_runs([]) == 3.0 (blank); [6,7,8] == 1.0 (mature); [6,2,7] == ~2.33
    (the 2-lap run doesn't count, so it reads as one qualifying run)."""
    qr = count_qualifying_runs(clean_lap_counts)
    return cold_start_aggression(data_maturity(qr))
