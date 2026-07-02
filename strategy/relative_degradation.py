"""Deterministic relative-baseline tyre degradation computation.

Computes the 'relative-baseline degradation point' for each compound present
in practice lap sequences. This is the authoritative deterministic result;
the AI call is only used afterwards to supply cliff_lap_practice,
pace_loss_at_cliff_s, total_life_race, and confidence for cliff-detection
compounds.

Public API
----------
compute_relative_degradation(
    lap_sequences: dict[str, list[float]],
    consecutive_laps: int = 2,
) -> dict[str, dict]

Per-compound output dict shape
------------------------------
{
    "optimal_stint_race": int,          # deterministic; 0 if undetermined/not viable
    "harder_baseline_ms": float | None, # mean of the harder compound's laps, or None
    "degradation_method": str,          # "relative_baseline" | "cliff_detection"
    "confidence": str,                  # "high" / "medium" / "low"
    "not_yet_degraded": bool,           # True when softer never crossed baseline
}

Hardness ordering
-----------------
ALL_COMPOUNDS is defined in data/tyres.py with HARDER compounds at LOWER indices
within each category:
  index 0: CH (Comfort Hard)  — hardest of Comfort
  index 1: CM
  index 2: CS (Comfort Soft)  — softest of Comfort
  index 3: SH (Sports Hard)   — hardest of Sports
  ...
  index 6: RH (Racing Hard)   — hardest of Racing
  index 7: RM (Racing Medium)
  index 8: RS (Racing Soft)   — softest of Racing
  index 9: IM (Intermediate)  — wet
  index 10: HW (Heavy Wet)    — wet

So LOWER index = HARDER, HIGHER index = SOFTER.
"Next harder" from a compound at index i means scanning toward LOWER indices.
"""
from __future__ import annotations

import statistics
from typing import Optional

from data.tyres import ALL_COMPOUNDS, get_by_code


# ---------------------------------------------------------------------------
# Compound ordering helpers
# ---------------------------------------------------------------------------

# ALL_COMPOUNDS tuple ordered hardest-first (lower index = harder compound).
# Wet compounds are at the high-index end (IM at 9, HW at 10).
_COMPOUND_LIST: list[str] = [c.code for c in ALL_COMPOUNDS]


def _hardness_index(code: str) -> int:
    """Return the position of a compound code in ALL_COMPOUNDS.

    Lower index = harder compound.  Returns -1 if the code is unknown.
    """
    try:
        return _COMPOUND_LIST.index(code)
    except ValueError:
        return -1


def _is_wet(code: str) -> bool:
    """Return True if the compound is a wet compound (Intermediate or Heavy Wet)."""
    tc = get_by_code(code)
    return tc is not None and tc.wet


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

def compute_relative_degradation(
    lap_sequences: dict[str, list[float]],
    consecutive_laps: int = 2,
) -> dict[str, dict]:
    """Compute relative-baseline degradation for each compound in lap_sequences.

    Parameters
    ----------
    lap_sequences:
        Dict keyed by compound code (e.g. "RS", "RM", "RH") mapping to a
        list of lap times in milliseconds, in recorded order.  These should
        already be filtered / outlier-removed by the caller.
    consecutive_laps:
        Number of consecutive laps that must all be >= the harder compound's
        mean baseline for the degradation point to be triggered.  Default 2.

    Returns
    -------
    Dict keyed by compound code.  Each value is a dict with keys:
        optimal_stint_race  – int
        harder_baseline_ms  – float | None
        degradation_method  – "relative_baseline" | "cliff_detection"
        confidence          – "high" / "medium" / "low"
        not_yet_degraded    – bool
    """
    if not lap_sequences:
        return {}

    # Pre-compute means for every present compound that has at least 1 lap.
    compound_means: dict[str, float] = {}
    for code, laps in lap_sequences.items():
        if laps:
            compound_means[code] = statistics.mean(laps)

    result: dict[str, dict] = {}

    for code, laps in lap_sequences.items():
        result[code] = _analyse_compound(
            code=code,
            laps=laps,
            lap_sequences=lap_sequences,
            compound_means=compound_means,
            consecutive_laps=consecutive_laps,
        )

    return result


def _analyse_compound(
    code: str,
    laps: list[float],
    lap_sequences: dict[str, list[float]],
    compound_means: dict[str, float],
    consecutive_laps: int,
) -> dict:
    """Analyse a single compound and return its degradation result dict."""

    # --- Cliff-detection fallback dict factory ---
    def _cliff_result() -> dict:
        return {
            "optimal_stint_race": 0,
            "harder_baseline_ms": None,
            "degradation_method": "cliff_detection",
            "confidence": _confidence(laps),
            "not_yet_degraded": False,
        }

    # Rule: wet compounds always use cliff_detection.
    if _is_wet(code):
        return _cliff_result()

    # Rule: only one compound present in lap_sequences → cliff_detection.
    if len(lap_sequences) == 1:
        return _cliff_result()

    my_idx = _hardness_index(code)
    if my_idx == -1:
        # Unknown compound — fall back to cliff detection.
        return _cliff_result()

    # Find the next-harder compound that actually has practice data.
    # "Harder" = lower index in _COMPOUND_LIST.
    # Scan from (my_idx - 1) down to 0, looking for a compound in lap_sequences
    # with a valid baseline mean.
    harder_code, harder_baseline_ms = _find_harder_baseline(
        code=code,
        my_idx=my_idx,
        lap_sequences=lap_sequences,
        compound_means=compound_means,
    )

    if harder_code is None:
        # This is either the hardest practised compound, or no harder compound
        # has valid baseline data — use cliff_detection.
        return _cliff_result()

    # --- Relative-baseline path ---
    # Find the FIRST run of `consecutive_laps` consecutive laps all >= harder_baseline_ms.
    degradation_start_idx = _find_consecutive_run(laps, harder_baseline_ms, consecutive_laps)

    if degradation_start_idx is None:
        # Never crosses baseline within recorded laps.
        return {
            "optimal_stint_race": 0,
            "harder_baseline_ms": harder_baseline_ms,
            "degradation_method": "relative_baseline",
            "confidence": "low",  # not_yet_degraded forces "low"
            "not_yet_degraded": True,
        }

    # D = 1-indexed position of the FIRST lap of the degradation run.
    D = degradation_start_idx + 1  # convert 0-indexed to 1-indexed

    # optimal_stint_race = D - 1 (last good lap BEFORE degradation starts).
    # If D - 1 <= 0 (degrades from lap 1), optimal = 0 (not viable).
    optimal = D - 1  # may be 0 — do NOT force a minimum of 1 here

    return {
        "optimal_stint_race": optimal,
        "harder_baseline_ms": harder_baseline_ms,
        "degradation_method": "relative_baseline",
        "confidence": _confidence(laps),
        "not_yet_degraded": False,
    }


def _find_harder_baseline(
    code: str,
    my_idx: int,
    lap_sequences: dict[str, list[float]],
    compound_means: dict[str, float],
) -> tuple[Optional[str], Optional[float]]:
    """Locate the next-harder compound that has a valid baseline.

    Implements the SKIPPED-TIER RULE: skip compounds not present in
    lap_sequences and use the next harder one that does have data.

    In _COMPOUND_LIST, lower index = harder compound.  Scan from
    (my_idx - 1) down to 0.

    Returns (compound_code, mean_ms) or (None, None).
    """
    # Scan toward lower indices (harder compounds).
    for i in range(my_idx - 1, -1, -1):
        harder_code = _COMPOUND_LIST[i]
        if harder_code in lap_sequences and harder_code in compound_means:
            # Valid baseline: compound has data and we computed a mean for it.
            tc = get_by_code(harder_code)
            if tc is not None and tc.wet:
                # Wet compounds cannot act as a baseline for dry compounds.
                continue
            return harder_code, compound_means[harder_code]
    return None, None


def _find_consecutive_run(
    laps: list[float],
    threshold: float,
    consecutive_laps: int,
) -> Optional[int]:
    """Find the 0-indexed position of the FIRST lap in the first consecutive run
    of `consecutive_laps` laps all >= threshold.

    A single outlier lap below the threshold breaks the run.

    Returns None if no such run exists within the recorded laps.
    """
    n = len(laps)
    if n < consecutive_laps:
        return None

    run_start: Optional[int] = None  # 0-indexed start of current candidate run
    run_length = 0

    for i, lap in enumerate(laps):
        if lap >= threshold:
            if run_start is None:
                run_start = i
                run_length = 1
            else:
                run_length += 1
            if run_length >= consecutive_laps:
                return run_start
        else:
            # Reset run on any lap below threshold.
            run_start = None
            run_length = 0

    return None


def _confidence(laps: list[float]) -> str:
    """Compute confidence level based on lap count.

    "high"   if >=8 laps
    "medium" if 4-7 laps
    "low"    if <4 laps
    """
    n = len(laps)
    if n >= 8:
        return "high"
    if n >= 4:
        return "medium"
    return "low"
