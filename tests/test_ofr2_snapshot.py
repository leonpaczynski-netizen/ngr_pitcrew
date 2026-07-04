"""OFR-2 — AI context snapshot discipline field tests.

Covers:
- SetupAISnapshot and PracticeAnalysisSnapshot have discipline="unknown" default
- StrategyAISnapshot has NO discipline field
- Builder derivations: "Race Setup"→"race", "Qualifying"→"qualifying", None→"unknown"
- to_dict() includes discipline
"""
from __future__ import annotations

import pytest

from data.ai_context_snapshot import (
    PracticeAnalysisSnapshot,
    SetupAISnapshot,
    StrategyAISnapshot,
    build_practice_analysis_snapshot,
    build_setup_ai_snapshot,
    build_strategy_ai_snapshot,
)


# ---------------------------------------------------------------------------
# Default discipline value
# ---------------------------------------------------------------------------

class TestDisciplineDefault:
    def test_setup_snapshot_discipline_defaults_unknown(self):
        snap = build_setup_ai_snapshot()
        assert snap.discipline == "unknown"

    def test_practice_snapshot_discipline_defaults_unknown(self):
        snap = build_practice_analysis_snapshot()
        assert snap.discipline == "unknown"

    def test_strategy_snapshot_has_no_discipline_field(self):
        snap = build_strategy_ai_snapshot()
        assert not hasattr(snap, "discipline"), (
            "StrategyAISnapshot must NOT have a discipline field"
        )


# ---------------------------------------------------------------------------
# SetupAISnapshot builder derivations
# ---------------------------------------------------------------------------

class TestSetupSnapshotDisciplineDerivation:
    def _build(self, session_type):
        return build_setup_ai_snapshot(session_type=session_type)

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
# PracticeAnalysisSnapshot builder derivations
# ---------------------------------------------------------------------------

class TestPracticeSnapshotDisciplineDerivation:
    def _build(self, purpose):
        return build_practice_analysis_snapshot(session_purpose=purpose)

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
        snap = build_setup_ai_snapshot(session_type="Race Setup")
        d = snap.to_dict()
        assert "discipline" in d
        assert d["discipline"] == "race"

    def test_practice_snapshot_to_dict_has_discipline(self):
        snap = build_practice_analysis_snapshot(session_purpose="Qualifying")
        d = snap.to_dict()
        assert "discipline" in d
        assert d["discipline"] == "qualifying"

    def test_setup_snapshot_unknown_to_dict(self):
        snap = build_setup_ai_snapshot()
        d = snap.to_dict()
        assert d["discipline"] == "unknown"

    def test_practice_snapshot_unknown_to_dict(self):
        snap = build_practice_analysis_snapshot()
        d = snap.to_dict()
        assert d["discipline"] == "unknown"


# ---------------------------------------------------------------------------
# Frozen dataclass: construction sites still compile
# ---------------------------------------------------------------------------

class TestFrozenDataclassCompat:
    def test_setup_snapshot_without_discipline_kwarg_compiles(self):
        """Existing call sites that don't pass discipline= must still work."""
        snap = build_setup_ai_snapshot()
        assert snap.discipline == "unknown"  # default applied

    def test_practice_snapshot_without_purpose_kwarg_compiles(self):
        snap = build_practice_analysis_snapshot()
        assert snap.discipline == "unknown"

    def test_strategy_snapshot_builds_without_error(self):
        snap = build_strategy_ai_snapshot()
        d = snap.to_dict()
        assert "core" in d
        assert "discipline" not in d  # must NOT bleed into StrategyAISnapshot.to_dict()
