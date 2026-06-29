"""
Group 29 — Tyre wear multiplier applies equally to practice and race (no scaling)

Background
----------
The strategy/degradation engine assumed practice telemetry was gathered at 1×
wear and the race ran at N×, so it instructed the AI to divide practice tyre
life by the multiplier to get "race-equivalent" laps and described the race as
"N× faster than practice". Drivers who set the SAME wear in practice and race
were double-counted: their practice data already reflects race wear.

Decision: remove practice→race scaling globally. The one configured multiplier
is the wear rate for BOTH sessions; practice laps ARE race laps.

These tests are behavioural (prompt-builder output) and source-scan only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy import ai_planner as ap

AP_SOURCE = (ROOT / "strategy" / "ai_planner.py").read_text(encoding="utf-8")


class TestDegradationPromptNoScaling:
    def _prompt(self, mult: float) -> str:
        seqs = {"RM": [60000, 60100, 60250, 61400, 61600]}
        return ap._build_degradation_prompt(seqs, mult)

    def test_no_division_by_multiplier(self):
        p = self._prompt(3.0)
        # The old formulas "/ 3.0" and "× 0.33" must be gone.
        assert "/ 3.0" not in p
        assert "practice laps × multiplier" not in p

    def test_states_multiplier_applies_equally(self):
        p = self._prompt(3.0)
        assert "applies EQUALLY to practice and race" in p

    def test_optimal_stint_is_unscaled_cliff(self):
        p = self._prompt(3.0)
        assert "cliff_lap_practice - 1" in p
        assert "no scaling" in p.lower()

    def test_total_life_equals_practice_total(self):
        p = self._prompt(3.0)
        assert "EQUALS the total practice laps" in p

    def test_multiplier_value_still_shown_for_context(self):
        p = self._prompt(2.5)
        assert "2.5" in p


class TestWearNoteReframed:
    def test_source_has_no_faster_than_practice(self):
        assert "faster than practice" not in AP_SOURCE

    def test_wear_note_unit_multiplier_mentions_shared_rate(self):
        params = _make_params(tyre_wear_multiplier=1.0)
        note = ap._wear_note(params)
        assert "practice and race" in note.lower()

    def test_wear_note_high_multiplier_says_do_not_scale(self):
        params = _make_params(tyre_wear_multiplier=3.0)
        note = ap._wear_note(params)
        assert "3.0" in note
        assert "do not scale" in note.lower()
        assert "applies equally" in note.lower()


class TestBuildPathWearContext:
    def test_no_race_faster_phrasing_in_source(self):
        # The from-scratch build prompt's wear line must not claim race is
        # faster than practice.
        assert "race wears tyres" not in AP_SOURCE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_params(**overrides):
    """Construct a minimal RaceParams, tolerant of the dataclass's required fields."""
    import dataclasses
    RaceParams = ap.RaceParams
    kwargs = {}
    for f in dataclasses.fields(RaceParams):
        if f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING:  # type: ignore[attr-defined]
            continue
        # Provide a sane placeholder for required fields by type annotation.
        ann = str(f.type)
        if "int" in ann:
            kwargs[f.name] = 0
        elif "float" in ann:
            kwargs[f.name] = 0.0
        elif "str" in ann:
            kwargs[f.name] = ""
        elif "bool" in ann:
            kwargs[f.name] = False
        else:
            kwargs[f.name] = None
    kwargs.update(overrides)
    return RaceParams(**kwargs)
