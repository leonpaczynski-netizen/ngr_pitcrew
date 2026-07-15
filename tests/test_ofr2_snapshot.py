"""OFR-2 — AI context snapshot discipline field tests.

Covers:
- SetupInputs and PracticeInputs have discipline="unknown" default
- StrategyInputs has NO discipline field
- Builder derivations: "Race Setup"→"race", "Qualifying"→"qualifying", None→"unknown"
- to_dict() includes discipline
"""
from __future__ import annotations

import pytest

from data.analysis_inputs import (
    PracticeInputs,
    SetupInputs,
    StrategyInputs,
    build_practice_inputs,
    build_setup_inputs,
    build_strategy_inputs,
)


# ---------------------------------------------------------------------------
# Default discipline value
# ---------------------------------------------------------------------------

class TestDisciplineDefault:
    def test_setup_snapshot_discipline_defaults_unknown(self):
        snap = build_setup_inputs()
        assert snap.discipline == "unknown"

    def test_practice_snapshot_discipline_defaults_unknown(self):
        snap = build_practice_inputs()
        assert snap.discipline == "unknown"

    def test_strategy_snapshot_has_no_discipline_field(self):
        snap = build_strategy_inputs()
        assert not hasattr(snap, "discipline"), (
            "StrategyInputs must NOT have a discipline field"
        )


# ---------------------------------------------------------------------------
# SetupInputs builder derivations
# ---------------------------------------------------------------------------

class TestSetupSnapshotDisciplineDerivation:
    def _build(self, session_type):
        return build_setup_inputs(session_type=session_type)

    def test_race_setup_maps_to_race(self):
        snap = self._build("Race Setup")
        assert snap.discipline == "race"

    def test_qualifying_setup_maps_to_qualifying(self):
        snap = self._build("Qualifying Setup")
        assert snap.discipline == "qualifying"

    def test_qualifying_string_maps_to_qualifying(self):
        snap = self._build("Qualifying")
        assert snap.discipline == "qualifying"

    def test_race_string_maps_to_race(self):
        snap = self._build("race")
        assert snap.discipline == "race"

    def test_none_maps_to_unknown(self):
        snap = self._build(None)
        assert snap.discipline == "unknown"

    def test_empty_string_maps_to_unknown(self):
        snap = self._build("")
        assert snap.discipline == "unknown"

    def test_practice_maps_to_practice(self):
        snap = self._build("practice")
        assert snap.discipline == "practice"

    def test_unknown_string_maps_to_unknown(self):
        snap = self._build("unknown")
        assert snap.discipline == "unknown"

    def test_junk_string_maps_to_unknown(self):
        snap = self._build("foobar_xyz")
        assert snap.discipline == "unknown"


# ---------------------------------------------------------------------------
# PracticeInputs builder derivations
# ---------------------------------------------------------------------------

class TestPracticeSnapshotDisciplineDerivation:
    def _build(self, purpose):
        return build_practice_inputs(session_purpose=purpose)

    def test_race_setup_maps_to_race(self):
        snap = self._build("Race Setup")
        assert snap.discipline == "race"

    def test_qualifying_maps_to_qualifying(self):
        snap = self._build("Qualifying")
        assert snap.discipline == "qualifying"

    def test_qualifying_setup_maps_to_qualifying(self):
        snap = self._build("Qualifying Setup")
        assert snap.discipline == "qualifying"

    def test_none_maps_to_unknown(self):
        snap = self._build(None)
        assert snap.discipline == "unknown"

    def test_empty_string_maps_to_unknown(self):
        snap = self._build("")
        assert snap.discipline == "unknown"

    def test_practice_maps_to_practice(self):
        snap = self._build("practice")
        assert snap.discipline == "practice"

    def test_unknown_maps_to_unknown(self):
        snap = self._build("unknown")
        assert snap.discipline == "unknown"


# ---------------------------------------------------------------------------
# to_dict() carries discipline
# ---------------------------------------------------------------------------

class TestToDictCarriesDiscipline:
    def test_setup_snapshot_to_dict_has_discipline(self):
        snap = build_setup_inputs(session_type="Race Setup")
        d = snap.to_dict()
        assert "discipline" in d
        assert d["discipline"] == "race"

    def test_practice_snapshot_to_dict_has_discipline(self):
        snap = build_practice_inputs(session_purpose="Qualifying")
        d = snap.to_dict()
        assert "discipline" in d
        assert d["discipline"] == "qualifying"

    def test_setup_snapshot_unknown_to_dict(self):
        snap = build_setup_inputs()
        d = snap.to_dict()
        assert d["discipline"] == "unknown"

    def test_practice_snapshot_unknown_to_dict(self):
        snap = build_practice_inputs()
        d = snap.to_dict()
        assert d["discipline"] == "unknown"


# ---------------------------------------------------------------------------
# Frozen dataclass: construction sites still compile
# ---------------------------------------------------------------------------

class TestFrozenDataclassCompat:
    def test_setup_snapshot_without_discipline_kwarg_compiles(self):
        """Existing call sites that don't pass discipline= must still work."""
        snap = build_setup_inputs()
        assert snap.discipline == "unknown"  # default applied

    def test_practice_snapshot_without_purpose_kwarg_compiles(self):
        snap = build_practice_inputs()
        assert snap.discipline == "unknown"

    def test_strategy_snapshot_builds_without_error(self):
        snap = build_strategy_inputs()
        d = snap.to_dict()
        assert "core" in d
        assert "discipline" not in d  # must NOT bleed into StrategyInputs.to_dict()
