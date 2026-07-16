"""Enforced registry of LIVE vs EXPERIMENTAL strategy engines.

The 12-sprint determinism rebuild left two engine generations. Several newer
engines are built and *validated by their own tests + the golden UAT* but are NOT
wired into the path a user actually drives — which means a green suite can hide
the fact that they're dormant. This test makes that status explicit and enforced:

  * every EXPERIMENTAL symbol must stay absent from the ``ui/`` runtime — the day
    someone wires one live, this test fails and forces them to consciously move it
    to LIVE below (so "green tests mask dormancy" can't recur);
  * every EXPERIMENTAL module must keep its ``EXPERIMENTAL`` banner;
  * a couple of LIVE engines are asserted present in ``ui/`` as a sanity check.

See docs/ and project memory (codebase audit 2026-07-16, item 6) for the rationale
on why these are marked rather than deleted (they export live dataclasses / are
golden-gated future work).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"

# Dormant engine ENTRY POINTS (functions), keyed to the module carrying the banner.
# NOTE: these modules also export *live* dataclasses — only these callables are dormant.
EXPERIMENTAL_SYMBOLS = {
    "arbitrate_setup_decision": "strategy/setup_decision.py",
    "build_compound_curves":    "strategy/tyre_curves.py",
    "compute_crossovers":       "strategy/tyre_curves.py",
    "compute_feasibility":      "strategy/feasibility.py",
    "check_compound_eligibility": "strategy/feasibility.py",
    "compute_outcome":          "strategy/outcome.py",
    "compare_outcomes":         "strategy/outcome.py",
}

# Modules that must carry the dormancy banner.
EXPERIMENTAL_MODULES = {
    "strategy/setup_decision.py",
    "strategy/tyre_curves.py",
    "strategy/feasibility.py",
    "strategy/outcome.py",
    "strategy/cross_lap_persistence.py",
}

# A few engines that ARE the live path — sanity that the registry reflects reality.
LIVE_SYMBOLS_IN_UI = [
    "recommend_strategy_from_session",   # race_strategy_pipeline
    "build_practice_evidence_bundle",    # practice_evidence_bundle (Sprint 10 piece 4)
    "render_setup_decision",             # setup_advice_render (Sprint 10 piece 3)
]


def _ui_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8", errors="ignore")
            for p in UI_DIR.glob("*.py")}


def test_experimental_symbols_absent_from_ui_runtime():
    ui = _ui_sources()
    offenders = []
    for sym in EXPERIMENTAL_SYMBOLS:
        pat = re.compile(rf"\b{re.escape(sym)}\b")
        for name, src in ui.items():
            if pat.search(src):
                offenders.append(f"{sym} referenced in ui/{name}")
    assert not offenders, (
        "An EXPERIMENTAL strategy engine is now referenced by the UI runtime. "
        "If you intentionally wired it into the live path, move it out of "
        "EXPERIMENTAL_SYMBOLS in this test and update its module banner. "
        f"Offenders: {offenders}")


def test_experimental_modules_keep_banner():
    for rel in sorted(EXPERIMENTAL_MODULES):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "EXPERIMENTAL" in src, (
            f"{rel} lost its EXPERIMENTAL/dormancy banner — either it was wired "
            f"live (update this registry) or the honest marker was dropped.")


def test_live_engines_present_in_ui():
    joined = "\n".join(_ui_sources().values())
    for sym in LIVE_SYMBOLS_IN_UI:
        assert re.search(rf"\b{re.escape(sym)}\b", joined), (
            f"Expected live engine entry point {sym!r} to be referenced by ui/ "
            f"runtime — the live/experimental registry is out of date.")
