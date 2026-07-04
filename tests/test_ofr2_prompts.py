"""OFR-2 — prompt-level integration tests.

Covers:
- QUALIFYING practice prompt contains peak-G [estimated] + derivation note + disclaimer
- RACE practice prompt contains std-dev [calculated] line
- UNKNOWN purpose practice prompt byte-identical to pre-change generic path
- Setup-build prompt with quali/race + laps contains the right discipline block
- Setup-build prompt with UNKNOWN/no-laps is byte-identical to a no-laps call
- Objective/session_desc strings unchanged (literal asserts)
- _build_race_prompt + _build_degradation_prompt signatures unchanged; no
  telemetry_disciplines import reaches them
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(**kw):
    from strategy.ai_planner import RaceParams
    defaults = dict(
        track="Suzuka",
        total_laps=25,
        tyre_wear_multiplier=2.0,
        fuel_burn_per_lap=3.0,
        refuel_speed_lps=10.0,
        pit_loss_secs=23.0,
    )
    defaults.update(kw)
    return RaceParams(**defaults)


def _clean_lap_row(i=0):
    return {
        "lap_num": i + 1,
        "lap_time_ms": 90_000 + i * 200,
        "fuel_used": 3.1 + i * 0.05,
        "is_pit_lap": 0,
        "is_out_lap": 0,
        "lock_up_count": 1,
        "wheelspin_count": 2,
        "snap_throttle_count": 1,
        "oversteer_count": 1,
        "oversteer_throttle_on": 0,
        "max_lat_g": 2.5,
        "brake_consistency_m": 2.0,
        "tyre_temp_fl_avg": 0.0,
        "tyre_temp_fr_avg": 0.0,
        "tyre_temp_rl_avg": 0.0,
        "tyre_temp_rr_avg": 0.0,
    }


def _laps(n=3):
    return [_clean_lap_row(i) for i in range(n)]


# ---------------------------------------------------------------------------
# QUALIFYING purpose injects discipline block in practice prompt
# ---------------------------------------------------------------------------

class TestQualifyingPracticePrompt:
    def _prompt(self, laps=None, purpose="Qualifying"):
        from strategy.ai_planner import _build_practice_prompt
        return _build_practice_prompt(
            _make_params(),
            {"RM": [90_000, 90_200]},
            {}, {},
            per_lap_telemetry=laps or _laps(),
            session_purpose=purpose,
        )

    def test_peak_g_estimated_line_present(self):
        prompt = self._prompt()
        assert "Peak lateral G" in prompt
        assert "[estimated]" in prompt

    def test_derivation_note_present(self):
        prompt = self._prompt()
        assert "angvel_z" in prompt
        assert "speed / 9.81" in prompt

    def test_disclaimer_line_present(self):
        prompt = self._prompt()
        assert "Steering corrections" in prompt
        assert "not measured" in prompt.lower()

    def test_qualifying_header_in_prompt(self):
        prompt = self._prompt()
        assert "QUALIFYING" in prompt

    def test_generic_per_lap_header_not_in_prompt(self):
        # Discipline block replaces the generic one; generic is not also included
        prompt = self._prompt()
        assert "Per-Lap Telemetry (last clean laps)" not in prompt


# ---------------------------------------------------------------------------
# RACE purpose injects discipline block in practice prompt
# ---------------------------------------------------------------------------

class TestRacePracticePrompt:
    def _prompt(self, laps=None, purpose="Race"):
        from strategy.ai_planner import _build_practice_prompt
        return _build_practice_prompt(
            _make_params(),
            {"RM": [90_000, 90_200]},
            {}, {},
            per_lap_telemetry=laps or _laps(),
            session_purpose=purpose,
        )

    def test_stddev_calculated_line_present(self):
        prompt = self._prompt()
        assert "std-dev" in prompt.lower() or "std dev" in prompt.lower()
        assert "[calculated]" in prompt

    def test_race_header_in_prompt(self):
        prompt = self._prompt()
        assert "RACE" in prompt

    def test_generic_per_lap_header_not_in_prompt(self):
        prompt = self._prompt()
        assert "Per-Lap Telemetry (last clean laps)" not in prompt


# ---------------------------------------------------------------------------
# UNKNOWN purpose → byte-identical to generic per-lap path
# ---------------------------------------------------------------------------

class TestUnknownPracticePromptByteIdentical:
    """When session_purpose is None/unknown, the prompt must be byte-identical
    to the pre-OFR-2 path (_build_per_lap_telemetry_block embedded verbatim)."""

    def test_unknown_prompt_equals_generic_prompt(self):
        from strategy.ai_planner import _build_practice_prompt, _build_per_lap_telemetry_block
        laps = _laps(3)
        params = _make_params()
        lap_data = {"RM": [90_000, 90_200]}

        # The "pre-change" reference: call without session_purpose (defaults to None)
        # but confirm the generic block would produce the same text
        generic_block = _build_per_lap_telemetry_block(laps)

        # OFR-2 path with UNKNOWN
        prompt_with_unknown = _build_practice_prompt(
            params, lap_data, {}, {},
            per_lap_telemetry=laps,
            session_purpose=None,
        )
        # Pre-change reference (no session_purpose param at all — same default)
        prompt_without_param = _build_practice_prompt(
            params, lap_data, {}, {},
            per_lap_telemetry=laps,
        )

        # Both must be identical
        assert prompt_with_unknown == prompt_without_param, (
            "UNKNOWN purpose prompt must be byte-identical to default (no-param) path"
        )
        # And both must contain the generic block
        assert generic_block in prompt_with_unknown

    def test_unknown_prompt_contains_generic_per_lap_header(self):
        from strategy.ai_planner import _build_practice_prompt
        laps = _laps(2)
        prompt = _build_practice_prompt(
            _make_params(), {"RM": [90_000]}, {}, {},
            per_lap_telemetry=laps,
            session_purpose=None,
        )
        assert "Per-Lap Telemetry (last clean laps)" in prompt

    def test_empty_laps_unknown_purpose_matches_generic_empty(self):
        from strategy.ai_planner import _build_practice_prompt, _build_per_lap_telemetry_block
        # Empty laps, UNKNOWN → generic block = "" → neither section added
        prompt_unknown = _build_practice_prompt(
            _make_params(), {}, {}, {},
            per_lap_telemetry=[],
            session_purpose=None,
        )
        prompt_default = _build_practice_prompt(
            _make_params(), {}, {}, {},
            per_lap_telemetry=[],
        )
        assert prompt_unknown == prompt_default
        assert _build_per_lap_telemetry_block([]) == ""  # confirms generic is empty


# ---------------------------------------------------------------------------
# Setup-build prompt discipline injection
# ---------------------------------------------------------------------------

class TestSetupBuildPromptDiscipline:
    def _prompt(self, session_type="qualifying", laps=None):
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        from strategy.setup_ranges import resolve_ranges
        return _build_setup_from_scratch_prompt(
            "Porsche 911", "Suzuka", session_type, 25, 0.0, 0.0,
            ranges=resolve_ranges(""),
            per_lap_telemetry=laps,
        )

    def test_qualifying_with_laps_contains_qualifying_block(self):
        prompt = self._prompt("qualifying", laps=_laps(3))
        assert "QUALIFYING" in prompt

    def test_race_with_laps_contains_race_block(self):
        prompt = self._prompt("race", laps=_laps(3))
        assert "RACE" in prompt

    def test_unknown_with_laps_no_discipline_block(self):
        # session_type="unknown" → UNKNOWN → _telem_section="" → no discipline header
        prompt = self._prompt("unknown", laps=_laps(3))
        assert "QUALIFYING" not in prompt
        assert "RACE" not in prompt
        # But prompt itself still renders (no crash)
        assert len(prompt) > 100

    def test_unknown_with_no_laps_byte_identical_to_no_param_call(self):
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        from strategy.setup_ranges import resolve_ranges
        # Call with unknown purpose + no laps
        prompt_unknown = _build_setup_from_scratch_prompt(
            "Porsche 911", "Suzuka", "unknown", 25, 0.0, 0.0,
            ranges=resolve_ranges(""),
            per_lap_telemetry=None,
        )
        # Call as if OFR-2 didn't exist (no per_lap_telemetry param)
        prompt_base = _build_setup_from_scratch_prompt(
            "Porsche 911", "Suzuka", "unknown", 25, 0.0, 0.0,
            ranges=resolve_ranges(""),
        )
        assert prompt_unknown == prompt_base, (
            "UNKNOWN/no-laps setup prompt must be byte-identical to pre-OFR-2 call"
        )

    def test_qualifying_with_no_laps_byte_identical_to_no_param_call(self):
        # If laps=[] and purpose=qualifying, no clean laps → block is just the
        # "No clean laps available" header. The per_lap_telemetry=None path
        # (pre-change) produces "" for _telem_section. Confirm per_lap_telemetry=None
        # with qualifying session_type == call without the param.
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        from strategy.setup_ranges import resolve_ranges
        prompt_with_none = _build_setup_from_scratch_prompt(
            "Porsche 911", "Suzuka", "qualifying", 25, 0.0, 0.0,
            ranges=resolve_ranges(""),
            per_lap_telemetry=None,
        )
        prompt_base = _build_setup_from_scratch_prompt(
            "Porsche 911", "Suzuka", "qualifying", 25, 0.0, 0.0,
            ranges=resolve_ranges(""),
        )
        assert prompt_with_none == prompt_base, (
            "per_lap_telemetry=None with qualifying session must equal pre-OFR-2 base"
        )


# ---------------------------------------------------------------------------
# Objective / session_desc strings unchanged
# ---------------------------------------------------------------------------

class TestObjectiveStringsUnchanged:
    """These are literal guard asserts — they pin the text that must NOT change."""

    def _src(self):
        return (ROOT / "strategy" / "ai_planner.py").read_text(encoding="utf-8")

    def test_qualifying_session_desc_unchanged(self):
        src = self._src()
        expected = (
            "1 qualifying lap (maximise single-lap peak pace, tyre warm-up, "
            "maximum rotation, no tyre wear concern)"
        )
        assert expected in src, f"qualifying session_desc changed: not found in ai_planner.py"

    def test_race_session_desc_unchanged(self):
        src = self._src()
        # Each fragment is on a single source line — check the key identifying phrases
        assert "optimise for lowest total race time: minimise tyre degradation" in src, (
            "race session_desc fragment changed: not found in ai_planner.py"
        )
        assert "maintain consistency; allow sacrificing small qualifying pace" in src, (
            "race session_desc consistency clause changed: not found in ai_planner.py"
        )


# ---------------------------------------------------------------------------
# _build_race_prompt and _build_degradation_prompt untouched
# ---------------------------------------------------------------------------

class TestUntouchedPromptFunctions:
    def test_build_race_prompt_has_no_session_purpose_param(self):
        from strategy.ai_planner import _build_race_prompt
        sig = inspect.signature(_build_race_prompt)
        assert "session_purpose" not in sig.parameters

    def test_build_race_prompt_has_no_per_lap_telemetry_param(self):
        from strategy.ai_planner import _build_race_prompt
        sig = inspect.signature(_build_race_prompt)
        assert "per_lap_telemetry" not in sig.parameters

    def test_build_degradation_prompt_has_no_session_purpose_param(self):
        from strategy.ai_planner import _build_degradation_prompt
        sig = inspect.signature(_build_degradation_prompt)
        assert "session_purpose" not in sig.parameters

    def test_build_degradation_prompt_has_no_per_lap_telemetry_param(self):
        from strategy.ai_planner import _build_degradation_prompt
        sig = inspect.signature(_build_degradation_prompt)
        assert "per_lap_telemetry" not in sig.parameters

    def test_build_per_lap_telemetry_block_unchanged(self):
        """The generic block function must still exist and work exactly as before."""
        from strategy.ai_planner import _build_per_lap_telemetry_block
        rows = [_clean_lap_row(0)]
        block = _build_per_lap_telemetry_block(rows)
        assert "Per-Lap Telemetry (last clean laps)" in block
        assert "Outlap" in block

    def test_telemetry_disciplines_not_imported_at_module_level(self):
        """The import is deferred inside the function bodies — it must NOT appear
        at the module level of ai_planner (no stray top-level import)."""
        src = (ROOT / "strategy" / "ai_planner.py").read_text(encoding="utf-8")
        import ast
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                mod = getattr(node, "module", "") or ""
                assert "telemetry_disciplines" not in mod
                assert not any("telemetry_disciplines" in n for n in names)
