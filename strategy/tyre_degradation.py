"""Deterministic tyre-degradation analysis.

Computes per-compound degradation using the deterministic relative-baseline
method (``strategy.relative_degradation``) and enforces the life-ordering
invariant (a softer compound's usable race stint must not exceed a
harder compound's). No AI, network, or Qt dependencies.

Extracted from the former ``strategy.ai_planner.analyse_tyre_degradation``
during the determinism rebuild (Sprint 1). The AI cliff-detection pass that
previously enriched cliff_lap_practice / pace_loss_at_cliff_s / total_life_race
has been removed; Sprint 7 restores those fields via a deterministic
crossover/cliff calculator.
"""
from __future__ import annotations


def analyse_tyre_degradation(
    lap_sequences: dict[str, list[float]],
    wear_multiplier: float = 1.0,
    consecutive_laps: int = 2,
) -> dict:
    """Return per-compound degradation, deterministic-only.

    For each compound the result carries at least ``optimal_stint_race`` (the
    usable race stint length), ``degradation_method`` and, where the relative
    baseline method applied, ``harder_baseline_ms`` and ``not_yet_degraded``.

    The life-ordering invariant is enforced last: walking present compounds
    hardest-first, a softer compound's positive ``optimal_stint_race`` is
    clamped so it never exceeds a harder compound's.
    """
    from strategy.relative_degradation import compute_relative_degradation
    from data.tyres import ALL_COMPOUNDS

    det_result = compute_relative_degradation(
        lap_sequences, consecutive_laps=consecutive_laps
    )

    merged: dict = {}
    for compound in lap_sequences:
        det_entry = dict(det_result.get(compound, {}))
        method = det_entry.get("degradation_method", "cliff_detection")
        det_entry.setdefault("degradation_method", method)
        if method == "relative_baseline":
            det_entry.setdefault("harder_baseline_ms", det_entry.get("harder_baseline_ms"))
            det_entry.setdefault("not_yet_degraded", det_entry.get("not_yet_degraded", False))
            if det_entry.get("not_yet_degraded"):
                det_entry["confidence"] = "low"
        else:
            det_entry["harder_baseline_ms"] = None
            det_entry.setdefault("not_yet_degraded", False)
        merged[compound] = det_entry

    # Life-ordering enforcement. ALL_COMPOUNDS is ordered HARDEST-FIRST
    # (lower index = harder). Invariant: optimal(softer) <= optimal(harder).
    _code_order = [c.code for c in ALL_COMPOUNDS]
    present_codes = sorted(
        list(merged),
        key=lambda c: _code_order.index(c) if c in _code_order else 9999,
    )
    running_cap: int | None = None
    for code in present_codes:
        opt = merged[code].get("optimal_stint_race", 0) or 0
        if opt > 0:
            if running_cap is not None and opt > running_cap:
                merged[code]["optimal_stint_race"] = running_cap
                opt = running_cap
            if running_cap is None or opt < running_cap:
                running_cap = opt

    return merged
