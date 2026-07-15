"""Sprint 2 — runtime stability: the exact `_sc` NameError regression.

UAT Defect 7: Race Strategy Analysis crashed with
    NameError: name '_sc' is not defined
at ui/dashboard.py, inside `_run_ai_analysis`, in the `race_type == "timed"`
branch (`_duration_secs = float(_sc.get("race_duration_minutes", 60)) * 60.0`).
`_sc` was an orphan left by the AI-snapshot migration — it only fired for
TIMED races, which is why lap-race tests never hit it.

Sprint 1 removed `_run_ai_analysis` entirely (the AI path is gone), which
deletes the crash site. These tests lock that in and prove the deterministic
replacement — computing race laps for a timed event — works without the
orphan.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_DASHBOARD_SRC = (_REPO / "ui" / "dashboard.py").read_text(encoding="utf-8")


def test_run_ai_analysis_method_is_gone():
    """The crashing AI-analysis handler must not exist on the window class."""
    from ui.dashboard import MainWindow
    assert not hasattr(MainWindow, "_run_ai_analysis"), (
        "_run_ai_analysis reintroduced — it carried the _sc NameError crash"
    )


def test_exact_sc_crash_pattern_absent_from_source():
    """The exact orphaned expression that raised NameError must not reappear."""
    assert '_sc.get("race_duration_minutes"' not in _DASHBOARD_SRC
    assert "_sc.get('race_duration_minutes'" not in _DASHBOARD_SRC


def test_no_orphan_sc_reads_in_dashboard():
    """Every function that READS a bare `_sc` must also DEFINE `_sc` locally.

    Guards against any future reintroduction of an undefined `_sc` (the exact
    class of bug behind Defect 7), not just the one crash line.
    """
    # Split source into top-level `def`/`async def` blocks (methods included).
    lines = _DASHBOARD_SRC.splitlines()
    func_ranges: list[tuple[int, int]] = []
    starts = [i for i, ln in enumerate(lines) if re.match(r"\s*(async\s+)?def\s+\w+", ln)]
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        func_ranges.append((s, e))

    offenders: list[str] = []
    for s, e in func_ranges:
        body = "\n".join(lines[s:e])
        reads = re.search(r"\b_sc\b\s*\.", body) or re.search(r"\b_sc\b\s*\[", body)
        if not reads:
            continue
        # `_sc` must be assigned somewhere in the same function body.
        if not re.search(r"\b_sc\b\s*=", body):
            offenders.append(lines[s].strip()[:80])
    assert not offenders, f"functions read an undefined `_sc`: {offenders}"


def test_timed_race_lap_estimate_is_deterministic():
    """The deterministic replacement for the crash intent works and repeats.

    The crash line was computing the timed-race duration in seconds to feed
    lap estimation. That is now `strategy.feasibility.estimate_race_laps`.
    """
    from strategy.race_params import RaceParams
    from strategy.feasibility import estimate_race_laps

    params = RaceParams(
        track="Fuji", total_laps=0, tyre_wear_multiplier=1.0,
        fuel_burn_per_lap=3.0, refuel_speed_lps=5.0, pit_loss_secs=22.0,
        race_type="timed", duration_mins=60,
    )
    duration_s = float(params.duration_mins) * 60.0
    representative_lap_s = 100.0  # 1:40 laps

    laps_a = estimate_race_laps(duration_s, representative_lap_s)
    laps_b = estimate_race_laps(duration_s, representative_lap_s)
    assert laps_a == laps_b == 36  # ceil(3600 / 100)


def test_estimate_race_laps_guards_zero_lap_time():
    """No division-by-zero / crash when representative lap time is unknown."""
    from strategy.feasibility import estimate_race_laps
    assert estimate_race_laps(3600.0, 0.0) == 0
