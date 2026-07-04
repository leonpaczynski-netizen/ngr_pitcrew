"""OFR-2 Race vs Qualifying Telemetry Disciplines — END-TO-END acceptance tests.

One test class per AC (AC1–AC11), plus edge cases called out in the story.

Conventions (matching the house style in test_ofr1_acceptance.py)
-----------------------------------------------------------------
* Only test files are modified — no production code.
* SessionDB(':memory:') throughout; real config.json is never touched.
* Qt-free; source scans used where a Qt path cannot be driven without Qt.
* Imports are deferred inside helper/test bodies so the module itself is always
  importable even if optional parts of the build fail.
"""
from __future__ import annotations

import ast
import inspect
import re
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]


# ===========================================================================
# Shared helpers
# ===========================================================================

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


def _clean_lap_row(i=0, **overrides):
    """A fully-populated clean lap row."""
    row = {
        "lap_num": i + 1,
        "lap_time_ms": 90_000 + i * 200,
        "fuel_used": 3.1 + i * 0.05,
        "is_pit_lap": 0,
        "is_out_lap": 0,
        "lock_up_count": 1,
        "wheelspin_count": 2,
        "snap_throttle_count": 1,
        "oversteer_count": 2,
        "oversteer_throttle_on": 1,
        "max_lat_g": 2.5,
        "brake_consistency_m": 2.0,
        "tyre_temp_fl_avg": 0.0,
        "tyre_temp_fr_avg": 0.0,
        "tyre_temp_rl_avg": 0.0,
        "tyre_temp_rr_avg": 0.0,
    }
    row.update(overrides)
    return row


def _laps(n=3, **overrides):
    return [_clean_lap_row(i, **overrides) for i in range(n)]


def _laps_with_temps(n=3):
    rows = []
    for i in range(n):
        rows.append(_clean_lap_row(
            i,
            tyre_temp_fl_avg=80.0,
            tyre_temp_fr_avg=85.0,
            tyre_temp_rl_avg=78.0,
            tyre_temp_rr_avg=83.0,
        ))
    return rows


def _make_db():
    from data.session_db import SessionDB
    return SessionDB(":memory:")


def _insert_lap_direct(db, session_id, lap_num, lap_time_ms,
                       snap_throttle=3, brake_con=2.5):
    """Direct SQL insert bypassing LapStats for isolation (mirrors test_ofr2_session_db)."""
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                snap_throttle_count,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, 0, "", lap_num, lap_time_ms, 2.0,
             1, 0, brake_con, snap_throttle, 0.0, 0.0, 0.0),
        )
        db._conn.commit()


def _setup_prompt(session_type, laps=None):
    """Drive _build_setup_from_scratch_prompt with minimal args."""
    from strategy.ai_planner import _build_setup_from_scratch_prompt
    from strategy.setup_ranges import resolve_ranges
    return _build_setup_from_scratch_prompt(
        "Porsche 911", "Suzuka", session_type, 25, 0.0, 0.0,
        ranges=resolve_ranges(""),
        per_lap_telemetry=laps,
    )


def _practice_prompt(laps=None, purpose=None):
    """Drive _build_practice_prompt with minimal args."""
    from strategy.ai_planner import _build_practice_prompt
    return _build_practice_prompt(
        _make_params(),
        {"RM": [90_000, 90_200]},
        {}, {},
        per_lap_telemetry=laps if laps is not None else _laps(),
        session_purpose=purpose,
    )


# ===========================================================================
# AC1 — QUALIFYING setup-build prompt telemetry block
# ===========================================================================

class TestAC1QualifyingSetupBuildBlock:
    """AC1: QUALIFYING discipline block in _build_setup_from_scratch_prompt."""

    def _prompt(self, laps=None):
        return _setup_prompt("Qualifying Setup", laps=laps or _laps(3))

    # ---- required content ---------------------------------------------------

    def test_ac1_best_lap_measured_label(self):
        prompt = self._prompt()
        assert "Best lap" in prompt
        assert "[measured]" in prompt

    def test_ac1_peak_lateral_g_estimated_label(self):
        prompt = self._prompt()
        assert "Peak lateral G" in prompt
        assert "[estimated]" in prompt

    def test_ac1_peak_g_derivation_note_angvel_z(self):
        prompt = self._prompt()
        assert "angvel_z" in prompt

    def test_ac1_peak_g_derivation_note_speed_over_9_81(self):
        prompt = self._prompt()
        assert "speed / 9.81" in prompt

    def test_ac1_lockup_count_calculated_label(self):
        prompt = self._prompt()
        lower = prompt.lower()
        assert "lock-up" in lower or "lock_up" in lower or "lockup" in lower
        assert "[calculated]" in prompt

    def test_ac1_brake_consistency_calculated_label(self):
        prompt = self._prompt()
        assert "brake consistency" in prompt.lower() or "Brake consistency" in prompt
        assert "[calculated]" in prompt

    def test_ac1_rotation_oversteer_total_present(self):
        prompt = self._prompt()
        assert "oversteer" in prompt.lower() or "Oversteer" in prompt

    def test_ac1_rotation_throttle_on_split_present(self):
        prompt = self._prompt()
        assert "throttle-on" in prompt.lower()

    def test_ac1_rotation_entry_split_present(self):
        prompt = self._prompt()
        assert "entry" in prompt.lower()

    def test_ac1_not_measured_disclaimer_steering_corrections(self):
        """The explicit not-measured line for steering corrections must appear."""
        prompt = self._prompt()
        assert "Steering corrections" in prompt
        # "not measured" may appear as "not measured" or "are not measured"
        assert "not measured" in prompt.lower()

    def test_ac1_not_measured_disclaimer_rival_traffic(self):
        """rival traffic/dirty-air appears in the disclaimer."""
        prompt = self._prompt()
        lower = prompt.lower()
        assert "rival" in lower or "traffic" in lower or "dirty-air" in lower or "dirty air" in lower

    def test_ac1_qualifying_header_present(self):
        prompt = self._prompt()
        assert "QUALIFYING" in prompt

    def test_ac1_no_tyre_radius(self):
        prompt = self._prompt()
        assert "tyre_radius" not in prompt
        assert "tyre radius" not in prompt.lower()


# ===========================================================================
# AC2 — RACE setup-build prompt telemetry block
# ===========================================================================

class TestAC2RaceSetupBuildBlock:
    """AC2: RACE discipline block in _build_setup_from_scratch_prompt."""

    def _prompt(self, laps=None):
        return _setup_prompt("Race Setup", laps=laps or _laps(3))

    # ---- required content ---------------------------------------------------

    def test_ac2_fuel_per_lap_measured_label(self):
        prompt = self._prompt()
        assert "[measured]" in prompt
        lower = prompt.lower()
        assert "fuel" in lower

    def test_ac2_lockup_rate_per_lap_calculated(self):
        prompt = self._prompt()
        lower = prompt.lower()
        assert "lock-up rate" in lower
        assert "[calculated]" in prompt

    def test_ac2_wheelspin_rate_per_lap_calculated(self):
        prompt = self._prompt()
        lower = prompt.lower()
        assert "wheelspin" in lower
        assert "[calculated]" in prompt

    def test_ac2_snap_throttle_per_lap_calculated(self):
        prompt = self._prompt()
        lower = prompt.lower()
        assert "snap-throttle" in lower
        assert "[calculated]" in prompt

    def test_ac2_laptime_stddev_calculated(self):
        prompt = self._prompt()
        lower = prompt.lower()
        assert ("std-dev" in lower or "std dev" in lower or "stdev" in lower)
        assert "[calculated]" in prompt

    def test_ac2_single_clean_lap_gives_n_a_1_lap(self):
        """With exactly one clean lap, std-dev must be 'N/A (1 lap)'."""
        prompt = self._prompt(laps=_laps(1))
        assert "N/A (1 lap)" in prompt

    def test_ac2_multi_lap_stddev_is_numeric(self):
        """With multiple laps, a numeric std-dev value is emitted."""
        prompt = self._prompt(laps=_laps(4))
        assert "N/A (1 lap)" not in prompt

    def test_ac2_tyre_temps_fl_fr_rl_rr_measured_label_when_present(self):
        prompt = _setup_prompt("Race Setup", laps=_laps_with_temps(3))
        assert "[measured]" in prompt
        lower = prompt.lower()
        assert "tyre temp" in lower or "fl" in lower

    def test_ac2_tyre_temps_not_recorded_when_all_zero(self):
        """All-zero tyre temps → '— not recorded' sentinel."""
        prompt = self._prompt(laps=_laps(3))
        assert "— not recorded" in prompt

    def test_ac2_partial_temps_render(self):
        """FL non-zero, FR/RL/RR zero → partial temps render (not '— not recorded')."""
        rows = _laps(2)
        for r in rows:
            r["tyre_temp_fl_avg"] = 75.0
        prompt = _setup_prompt("Race Setup", laps=rows)
        assert "— not recorded" not in prompt
        assert "75" in prompt

    def test_ac2_race_header_present(self):
        prompt = self._prompt()
        assert "RACE" in prompt

    def test_ac2_no_tyre_radius(self):
        prompt = self._prompt()
        assert "tyre_radius" not in prompt
        assert "tyre radius" not in prompt.lower()


# ===========================================================================
# AC3 — Practice-analysis discipline from db.get_session_type (RF1)
# ===========================================================================

class TestAC3PracticeOrchestratrorRF1:
    """AC3: practice_orchestrator resolves session_purpose via db.get_session_type;
    dashboard._run_practice_analysis passes NO combo-based session_purpose."""

    # ---- RF1: source-scan confirms orchestrator self-resolves ---------------

    def test_ac3_orchestrator_calls_get_session_type(self):
        """practice_orchestrator.py must contain a call to get_session_type."""
        src = (REPO / "strategy" / "practice_orchestrator.py").read_text(encoding="utf-8")
        assert "get_session_type" in src, (
            "practice_orchestrator must resolve session_purpose via "
            "db.get_session_type (RF1)"
        )

    def test_ac3_orchestrator_resolves_when_empty_purpose(self):
        """The resolution must be conditional on the caller not supplying a purpose
        (line pattern: 'if not session_purpose and session_id > 0')."""
        src = (REPO / "strategy" / "practice_orchestrator.py").read_text(encoding="utf-8")
        assert "not session_purpose" in src and "session_id" in src, (
            "orchestrator must guard: if not session_purpose and session_id > 0 "
            "before resolving from DB"
        )

    def test_ac3_dashboard_run_practice_analysis_passes_no_combo_purpose(self):
        """dashboard._run_practice_analysis must NOT pass a session_purpose kwarg
        to run_practice_analysis (RF1: no UI/combo involvement)."""
        src = (REPO / "ui" / "dashboard.py").read_text(encoding="utf-8")

        # Locate the _run_practice_analysis method body
        m = re.search(
            r"\n    def _run_practice_analysis\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
            src, re.DOTALL,
        )
        assert m, "_run_practice_analysis method not found in dashboard.py"
        body = m.group(0)

        # The call to run_practice_analysis inside this method must NOT pass
        # session_purpose= as a keyword argument
        assert "session_purpose=" not in body, (
            "dashboard._run_practice_analysis must not pass session_purpose= to "
            "run_practice_analysis — the orchestrator owns that resolution (RF1)"
        )

    def test_ac3_db_round_trip_qualifying_via_orchestrator_path(self):
        """End-to-end DB round-trip: open qualifying session → get_session_type returns
        'Qualifying' → orchestrator would resolve to 'Qualifying' discipline."""
        db = _make_db()
        sid = db.open_session(car_id=0, track="Suzuka", session_type="Qualifying")
        result = db.get_session_type(sid)
        assert result == "Qualifying"

        # Verify the orchestrator would pick that up: check the normalise_purpose path
        from data.setup_context import normalise_purpose, SetupPurpose
        disc = normalise_purpose(result)
        assert disc == SetupPurpose.QUALIFYING, (
            "get_session_type('Qualifying') must map to SetupPurpose.QUALIFYING "
            "via normalise_purpose"
        )

    def test_ac3_practice_prompt_with_qualifying_session_purpose_has_qualifying_block(self):
        """When session_purpose='Qualifying' is supplied, the practice prompt
        must contain the QUALIFYING discipline block."""
        prompt = _practice_prompt(laps=_laps(3), purpose="Qualifying")
        assert "QUALIFYING" in prompt

    def test_ac3_practice_prompt_with_race_session_purpose_has_race_block(self):
        """When session_purpose='Race' is supplied, the practice prompt
        must contain the RACE discipline block."""
        prompt = _practice_prompt(laps=_laps(3), purpose="Race")
        assert "RACE" in prompt

    def test_ac3_practice_session_type_in_db_yields_generic_block(self):
        """M3 / C1 guard: a real :memory: session stored with session_type='practice'
        → get_session_type returns 'practice' → normalise_purpose resolves to
        PRACTICE → build_discipline_telemetry_block returns None sentinel
        → the practice prompt embeds the GENERIC _build_per_lap_telemetry_block
        output byte-for-byte (no QUALIFYING or RACE discipline block injected)."""
        from data.session_db import SessionDB
        from data.setup_context import normalise_purpose, SetupPurpose
        from strategy.ai_planner import _build_practice_prompt, _build_per_lap_telemetry_block
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt

        db = SessionDB(":memory:")
        sid = db.open_session(car_id=0, track="Suzuka", session_type="practice")
        session_type = db.get_session_type(sid)
        assert session_type == "practice"

        # normalise_purpose → PRACTICE, not RACE
        disc = normalise_purpose(session_type)
        assert disc == SetupPurpose.PRACTICE

        # discipline block must be None (sentinel → callers keep generic block)
        laps = _laps(3)
        assert bdt(laps, session_type) is None, (
            "PRACTICE session must return None sentinel from "
            "build_discipline_telemetry_block, not a RACE block"
        )

        # End-to-end: practice prompt with PRACTICE purpose must embed the generic
        # block byte-for-byte, identical to passing purpose=None
        params = _make_params()
        lap_data = {"RM": [90_000, 90_200]}
        generic_block = _build_per_lap_telemetry_block(laps)

        prompt_practice = _build_practice_prompt(
            params, lap_data, {}, {},
            per_lap_telemetry=laps,
            session_purpose=session_type,
        )
        prompt_none = _build_practice_prompt(
            params, lap_data, {}, {},
            per_lap_telemetry=laps,
            session_purpose=None,
        )
        assert generic_block in prompt_practice, (
            "Practice-session prompt must contain the generic per-lap block "
            "byte-for-byte when session_type='practice' (AC5 / C1)"
        )
        assert prompt_practice == prompt_none, (
            "practice session_purpose must produce byte-identical output to "
            "session_purpose=None (generic block preserved)"
        )


# ===========================================================================
# AC4 — [measured]/[calculated]/[estimated] labels + estimated derivation notes
# ===========================================================================

class TestAC4Labels:
    """AC4: all three data-quality labels appear in correct contexts with
    derivation notes on estimated signals."""

    def test_ac4_measured_label_in_race_setup_prompt(self):
        prompt = _setup_prompt("Race Setup", laps=_laps_with_temps(2))
        assert "[measured]" in prompt

    def test_ac4_calculated_label_in_race_setup_prompt(self):
        prompt = _setup_prompt("Race Setup", laps=_laps(3))
        assert "[calculated]" in prompt

    def test_ac4_estimated_label_in_qualifying_setup_prompt(self):
        prompt = _setup_prompt("Qualifying Setup", laps=_laps(3))
        assert "[estimated]" in prompt

    def test_ac4_estimated_signals_have_derivation_note_quali_setup(self):
        prompt = _setup_prompt("Qualifying Setup", laps=_laps(3))
        assert "angvel_z" in prompt
        assert "speed / 9.81" in prompt

    def test_ac4_estimated_label_in_qualifying_practice_prompt(self):
        prompt = _practice_prompt(laps=_laps(3), purpose="Qualifying")
        assert "[estimated]" in prompt

    def test_ac4_estimated_signals_have_derivation_note_quali_practice(self):
        prompt = _practice_prompt(laps=_laps(3), purpose="Qualifying")
        assert "angvel_z" in prompt
        assert "speed / 9.81" in prompt

    def test_ac4_build_discipline_block_direct_estimated_label(self):
        """Direct call to build_discipline_telemetry_block for QUALIFYING."""
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Qualifying")
        assert "[estimated]" in block
        assert "angvel_z" in block

    def test_ac4_build_discipline_block_direct_measured_label_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps_with_temps(2), "Race")
        assert "[measured]" in block

    def test_ac4_build_discipline_block_direct_calculated_label_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Race")
        assert "[calculated]" in block


# ===========================================================================
# AC5 — UNKNOWN purpose → byte-identical paths
# ===========================================================================

class TestAC5UnknownByteIdentical:
    """AC5: UNKNOWN purpose → byte-identical output to pre-OFR-2 generic path."""

    def test_ac5_practice_unknown_equals_no_param(self):
        """session_purpose=None must produce identical output to omitting the param."""
        from strategy.ai_planner import _build_practice_prompt
        laps = _laps(3)
        params = _make_params()
        lap_data = {"RM": [90_000, 90_200]}

        prompt_none = _build_practice_prompt(
            params, lap_data, {}, {},
            per_lap_telemetry=laps,
            session_purpose=None,
        )
        prompt_default = _build_practice_prompt(
            params, lap_data, {}, {},
            per_lap_telemetry=laps,
        )
        assert prompt_none == prompt_default, (
            "UNKNOWN purpose practice prompt must be byte-identical to "
            "no-session_purpose call"
        )

    def test_ac5_practice_unknown_contains_generic_per_lap_block(self):
        """UNKNOWN purpose practice prompt must embed the generic block verbatim."""
        from strategy.ai_planner import _build_practice_prompt, _build_per_lap_telemetry_block
        laps = _laps(3)
        params = _make_params()
        lap_data = {"RM": [90_000]}
        generic_block = _build_per_lap_telemetry_block(laps)

        prompt = _build_practice_prompt(
            params, lap_data, {}, {},
            per_lap_telemetry=laps,
            session_purpose=None,
        )
        assert generic_block in prompt

    def test_ac5_setup_unknown_no_laps_equals_no_param_call(self):
        """Setup prompt with UNKNOWN purpose + per_lap_telemetry=None must equal
        a call without the per_lap_telemetry param at all."""
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        from strategy.setup_ranges import resolve_ranges
        args = ("Porsche 911", "Suzuka", "unknown", 25, 0.0, 0.0)
        kwargs_base = dict(ranges=resolve_ranges(""))

        prompt_with_none = _build_setup_from_scratch_prompt(
            *args, **kwargs_base, per_lap_telemetry=None
        )
        prompt_base = _build_setup_from_scratch_prompt(*args, **kwargs_base)
        assert prompt_with_none == prompt_base, (
            "UNKNOWN/no-laps setup prompt must be byte-identical to pre-OFR-2 base call"
        )

    def test_ac5_setup_unknown_with_laps_has_no_discipline_block(self):
        """UNKNOWN purpose + laps → no QUALIFYING or RACE block injected."""
        prompt = _setup_prompt("unknown", laps=_laps(3))
        assert "QUALIFYING" not in prompt
        assert "RACE" not in prompt

    def test_ac5_build_discipline_block_unknown_returns_none_sentinel(self):
        """build_discipline_telemetry_block with UNKNOWN returns None sentinel."""
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_laps(3), "unknown") is None
        assert bdt(_laps(3), None) is None
        assert bdt(_laps(3), "") is None

    def test_ac5_setup_unknown_with_real_laps_equals_none_laps(self):
        """I2: UNKNOWN purpose + 3 real lap dicts must produce byte-identical
        output to UNKNOWN purpose + per_lap_telemetry=None.
        Pins that UNKNOWN + non-empty laps still renders the empty section."""
        laps = _laps(3)
        prompt_with_laps = _setup_prompt("unknown", laps=laps)
        prompt_with_none = _setup_prompt("unknown", laps=None)
        assert prompt_with_laps == prompt_with_none, (
            "UNKNOWN purpose with real laps must be byte-identical to UNKNOWN "
            "purpose with per_lap_telemetry=None — discipline block must not appear"
        )


# ===========================================================================
# AC6 — No tyre_radius in any discipline block path
# ===========================================================================

class TestAC6NoTyreRadius:
    """AC6: tyre_radius must never appear in any discipline-block path."""

    def test_ac6_no_tyre_radius_in_qualifying_setup_prompt(self):
        prompt = _setup_prompt("Qualifying Setup", laps=_laps(3))
        assert "tyre_radius" not in prompt
        assert "tyre radius" not in prompt.lower()

    def test_ac6_no_tyre_radius_in_race_setup_prompt(self):
        prompt = _setup_prompt("Race Setup", laps=_laps(3))
        assert "tyre_radius" not in prompt
        assert "tyre radius" not in prompt.lower()

    def test_ac6_no_tyre_radius_in_qualifying_practice_prompt(self):
        prompt = _practice_prompt(laps=_laps(3), purpose="Qualifying")
        assert "tyre_radius" not in prompt
        assert "tyre radius" not in prompt.lower()

    def test_ac6_no_tyre_radius_in_race_practice_prompt(self):
        prompt = _practice_prompt(laps=_laps(3), purpose="Race")
        assert "tyre_radius" not in prompt
        assert "tyre radius" not in prompt.lower()

    def test_ac6_no_tyre_radius_in_disciplines_module_source(self):
        """The telemetry_disciplines module itself must not mention tyre_radius."""
        src = (REPO / "strategy" / "telemetry_disciplines.py").read_text(encoding="utf-8")
        assert "tyre_radius" not in src
        assert "tyre radius" not in src.lower()

    def test_ac6_no_tyre_radius_in_build_discipline_block_qualifying_output(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Qualifying")
        assert block is not None
        assert "tyre_radius" not in block
        assert "tyre radius" not in block.lower()

    def test_ac6_no_tyre_radius_in_build_discipline_block_race_output(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Race")
        assert block is not None
        assert "tyre_radius" not in block
        assert "tyre radius" not in block.lower()


# ===========================================================================
# AC7 — Objective text, race rules, _build_race_prompt / _build_degradation_prompt
#         byte-identical (no session_purpose / per_lap_telemetry params)
# ===========================================================================

class TestAC7StrategyPromptsUntouched:
    """AC7: strategy prompts are byte-identical; race/degradation signatures unchanged;
    qualifying and race objective strings unchanged."""

    def _src(self):
        return (REPO / "strategy" / "ai_planner.py").read_text(encoding="utf-8")

    # ---- objective / session_desc strings -----------------------------------

    def test_ac7_qualifying_session_desc_unchanged(self):
        src = self._src()
        expected = (
            "1 qualifying lap (maximise single-lap peak pace, tyre warm-up, "
            "maximum rotation, no tyre wear concern)"
        )
        assert expected in src, "qualifying session_desc changed in ai_planner.py"

    def test_ac7_race_session_desc_fragment_1_unchanged(self):
        src = self._src()
        assert "optimise for lowest total race time: minimise tyre degradation" in src

    def test_ac7_race_session_desc_fragment_2_unchanged(self):
        src = self._src()
        assert "maintain consistency; allow sacrificing small qualifying pace" in src

    # ---- _build_race_prompt signature has no new params ---------------------

    def test_ac7_build_race_prompt_no_session_purpose_param(self):
        from strategy.ai_planner import _build_race_prompt
        sig = inspect.signature(_build_race_prompt)
        assert "session_purpose" not in sig.parameters

    def test_ac7_build_race_prompt_no_per_lap_telemetry_param(self):
        from strategy.ai_planner import _build_race_prompt
        sig = inspect.signature(_build_race_prompt)
        assert "per_lap_telemetry" not in sig.parameters

    # ---- _build_degradation_prompt signature --------------------------------

    def test_ac7_build_degradation_prompt_no_session_purpose_param(self):
        from strategy.ai_planner import _build_degradation_prompt
        sig = inspect.signature(_build_degradation_prompt)
        assert "session_purpose" not in sig.parameters

    def test_ac7_build_degradation_prompt_no_per_lap_telemetry_param(self):
        from strategy.ai_planner import _build_degradation_prompt
        sig = inspect.signature(_build_degradation_prompt)
        assert "per_lap_telemetry" not in sig.parameters

    # ---- _build_race_prompt is callable and produces stable output ----------

    def test_ac7_build_race_prompt_renders_without_session_purpose(self):
        """_build_race_prompt must render successfully with no discipline args."""
        from strategy.ai_planner import _build_race_prompt, RaceParams
        params = _make_params()
        lap_data = {"RM": [90_000, 90_200, 90_400]}
        prompt = _build_race_prompt(params, lap_data)
        assert len(prompt) > 100
        # Must NOT contain any discipline block introduced by OFR-2
        assert "QUALIFYING" not in prompt
        assert "[estimated]" not in prompt or "tyre wear" in prompt.lower()

    # ---- _build_degradation_prompt is callable and produces stable output ---

    def test_ac7_build_degradation_prompt_renders_without_session_purpose(self):
        from strategy.ai_planner import _build_degradation_prompt
        prompt = _build_degradation_prompt({"RM": [90_000, 90_200]}, 2.0)
        assert len(prompt) > 50
        # Must NOT have discipline-block markers
        assert "QUALIFYING" not in prompt


# ===========================================================================
# AC8 — SetupAISnapshot + PracticeAnalysisSnapshot gain discipline field;
#        StrategyAISnapshot does NOT
# ===========================================================================

class TestAC8SnapshotDisciplineField:
    """AC8: dataclass field checks + derivations; StrategyAISnapshot negative check."""

    def test_ac8_setup_snapshot_has_discipline_field(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot()
        assert hasattr(snap, "discipline"), "SetupAISnapshot must have discipline field"

    def test_ac8_setup_snapshot_default_unknown(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        assert build_setup_ai_snapshot().discipline == "unknown"

    def test_ac8_setup_snapshot_race_setup_derives_race(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot(session_type="Race Setup")
        assert snap.discipline == "race"

    def test_ac8_setup_snapshot_qualifying_setup_derives_qualifying(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot(session_type="Qualifying Setup")
        assert snap.discipline == "qualifying"

    def test_ac8_setup_snapshot_none_derives_unknown(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot(session_type=None)
        assert snap.discipline == "unknown"

    def test_ac8_practice_snapshot_has_discipline_field(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        snap = build_practice_analysis_snapshot()
        assert hasattr(snap, "discipline")

    def test_ac8_practice_snapshot_default_unknown(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        assert build_practice_analysis_snapshot().discipline == "unknown"

    def test_ac8_practice_snapshot_qualifying_derives_qualifying(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        snap = build_practice_analysis_snapshot(session_purpose="Qualifying")
        assert snap.discipline == "qualifying"

    def test_ac8_practice_snapshot_race_setup_derives_race(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        snap = build_practice_analysis_snapshot(session_purpose="Race Setup")
        assert snap.discipline == "race"

    def test_ac8_strategy_snapshot_has_no_discipline_field(self):
        from data.ai_context_snapshot import build_strategy_ai_snapshot
        snap = build_strategy_ai_snapshot()
        assert not hasattr(snap, "discipline"), (
            "StrategyAISnapshot must NOT have a discipline field (AC8 negative check)"
        )

    def test_ac8_strategy_snapshot_to_dict_no_discipline_key(self):
        from data.ai_context_snapshot import build_strategy_ai_snapshot
        d = build_strategy_ai_snapshot().to_dict()
        assert "discipline" not in d, (
            "StrategyAISnapshot.to_dict() must not carry a discipline key"
        )

    def test_ac8_setup_snapshot_to_dict_has_discipline(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        d = build_setup_ai_snapshot(session_type="Race Setup").to_dict()
        assert "discipline" in d
        assert d["discipline"] == "race"

    def test_ac8_practice_snapshot_to_dict_has_discipline(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        d = build_practice_analysis_snapshot(session_purpose="Qualifying").to_dict()
        assert "discipline" in d
        assert d["discipline"] == "qualifying"

    def test_ac8_normalise_purpose_handles_enum_qualifying(self):
        """normalise_purpose accepts SetupPurpose enum values."""
        from data.setup_context import SetupPurpose, normalise_purpose
        assert normalise_purpose(SetupPurpose.QUALIFYING) == SetupPurpose.QUALIFYING

    def test_ac8_normalise_purpose_handles_enum_unknown(self):
        from data.setup_context import SetupPurpose, normalise_purpose
        assert normalise_purpose(SetupPurpose.UNKNOWN) == SetupPurpose.UNKNOWN


# ===========================================================================
# AC9 — New builder (telemetry_disciplines.py) is pure — AST scan
# ===========================================================================

class TestAC9BuilderPurity:
    """AC9: telemetry_disciplines.py must be pure (no PyQt6, no sqlite3, no IO,
    no config["strategy"] reads); frozen allowlist unchanged."""

    DISCIPLINES_PATH = REPO / "strategy" / "telemetry_disciplines.py"

    def _tree(self):
        src = self.DISCIPLINES_PATH.read_text(encoding="utf-8")
        return ast.parse(src)

    def test_ac9_no_pyqt6_import(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                mod = getattr(node, "module", "") or ""
                assert "PyQt6" not in mod, "PyQt6 module import found"
                assert not any("PyQt6" in n for n in names), "PyQt6 import found"

    def test_ac9_no_sqlite3_import(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                mod = getattr(node, "module", "") or ""
                assert "sqlite3" not in mod
                assert not any("sqlite3" in n for n in names)

    def test_ac9_no_open_builtin_call(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    raise AssertionError("open() call found — violates purity contract")

    def test_ac9_no_config_strategy_access(self):
        """telemetry_disciplines must never read config["strategy"]."""
        src = self.DISCIPLINES_PATH.read_text(encoding="utf-8")
        assert 'config["strategy"]' not in src
        assert "config.get(\"strategy\"" not in src

    def test_ac9_frozen_allowlist_unchanged(self):
        """The frozen allowlist in test_legacy_fanout_phase_5 must be exactly
        as set — telemetry_disciplines must not have added a new consumer."""
        from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
        found = _scan_inventory()
        new = {k: v for k, v in found.items()
               if k not in FROZEN_ALLOWLIST or v > FROZEN_ALLOWLIST[k]}
        gone = {k: v for k, v in FROZEN_ALLOWLIST.items()
                if found.get(k, 0) < v}
        assert not new, (
            f"NEW config['strategy'] consumers introduced: {new}"
        )
        assert not gone, (
            f"config['strategy'] sites removed without updating allowlist: {gone}"
        )


# ===========================================================================
# AC10 — OFR-1 blocks untouched (recommendation_scoring + driving_advisor)
# ===========================================================================

class TestAC10OFR1Untouched:
    """AC10: OFR-1 scored-recommendations block and recommendation_scoring.py untouched."""

    def test_ac10_telemetry_disciplines_not_imported_in_recommendation_scoring(self):
        src = (REPO / "data" / "recommendation_scoring.py").read_text(encoding="utf-8")
        assert "telemetry_disciplines" not in src, (
            "data/recommendation_scoring.py must not import telemetry_disciplines"
        )

    def test_ac10_telemetry_disciplines_not_imported_in_driving_advisor(self):
        src = (REPO / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")
        assert "telemetry_disciplines" not in src, (
            "strategy/driving_advisor.py must not import telemetry_disciplines"
        )

    def test_ac10_format_performance_block_still_present_in_driving_advisor(self):
        """_get_previous_ai_context must still reference format_performance_block
        (OFR-1's §6.4 scored-recommendations block unchanged)."""
        src = (REPO / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")
        assert "format_performance_block" in src, (
            "_get_previous_ai_context must still use format_performance_block (OFR-1 path)"
        )

    def test_ac10_get_previous_ai_context_body_has_scored_recs_call(self):
        """_get_previous_ai_context still calls get_scored_recs_for_prompt."""
        src = (REPO / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")
        assert "get_scored_recs_for_prompt" in src, (
            "_get_previous_ai_context must still call get_scored_recs_for_prompt (OFR-1 AC)"
        )

    def test_ac10_recommendation_scoring_module_importable(self):
        """recommendation_scoring.py must remain importable without error and
        still export its core public functions."""
        import importlib
        mod = importlib.import_module("data.recommendation_scoring")
        # format_performance_block is the OFR-1 §6.4 entry point used by driving_advisor
        assert hasattr(mod, "format_performance_block"), (
            "format_performance_block must still exist in recommendation_scoring"
        )
        # compute_verdict_and_confidence is the core scoring function
        assert hasattr(mod, "compute_verdict_and_confidence"), (
            "compute_verdict_and_confidence must still exist in recommendation_scoring"
        )

    def test_ac10_recommendation_scoring_hash_unchanged(self):
        """Byte-hash guard for recommendation_scoring.py (mirrors test_ofr2_session_db
        which already asserts the hash, but we include it in the acceptance suite for
        complete traceability of AC10)."""
        import hashlib
        path = REPO / "data" / "recommendation_scoring.py"
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()[:16]
        EXPECTED = "0fbd7d07c0dfc23c"
        assert actual == EXPECTED, (
            f"data/recommendation_scoring.py byte-hash changed (OFR-1 non-collision). "
            f"Expected {EXPECTED!r}, got {actual!r}"
        )


# ===========================================================================
# AC11 — Strategy prompts receive zero telemetry changes
# ===========================================================================

class TestAC11StrategyPromptsZeroTelemetry:
    """AC11: strategy analysis prompts receive no telemetry changes from OFR-2."""

    def test_ac11_analyse_strategy_signature_no_per_lap_telemetry(self):
        from strategy.ai_planner import analyse_strategy
        sig = inspect.signature(analyse_strategy)
        assert "per_lap_telemetry" not in sig.parameters

    def test_ac11_analyse_strategy_signature_no_session_purpose(self):
        from strategy.ai_planner import analyse_strategy
        sig = inspect.signature(analyse_strategy)
        assert "session_purpose" not in sig.parameters

    def test_ac11_build_race_prompt_no_discipline_params(self):
        from strategy.ai_planner import _build_race_prompt
        sig = inspect.signature(_build_race_prompt)
        assert "session_purpose" not in sig.parameters
        assert "per_lap_telemetry" not in sig.parameters

    def test_ac11_build_degradation_prompt_no_discipline_params(self):
        from strategy.ai_planner import _build_degradation_prompt
        sig = inspect.signature(_build_degradation_prompt)
        assert "session_purpose" not in sig.parameters
        assert "per_lap_telemetry" not in sig.parameters

    def test_ac11_strategy_ai_snapshot_no_discipline(self):
        from data.ai_context_snapshot import build_strategy_ai_snapshot
        snap = build_strategy_ai_snapshot()
        assert not hasattr(snap, "discipline")

    def test_ac11_race_prompt_output_has_no_qualifying_block(self):
        from strategy.ai_planner import _build_race_prompt
        prompt = _build_race_prompt(_make_params(), {"RM": [90_000, 90_200]})
        assert "Per-Lap Telemetry — QUALIFYING" not in prompt

    def test_ac11_race_prompt_output_has_no_race_discipline_block(self):
        """_build_race_prompt is the strategy prompt, not the setup block;
        it must not contain the OFR-2 RACE discipline block."""
        from strategy.ai_planner import _build_race_prompt
        prompt = _build_race_prompt(_make_params(), {"RM": [90_000, 90_200]})
        # The OFR-2 block header is distinct from any existing "race" mentions
        assert "Per-Lap Telemetry — RACE" not in prompt


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCaseDeclaredPurposeWins:
    """Edge: setup's declared purpose wins over lap-source session type."""

    def test_edge_qualifying_purpose_with_racey_laps_emits_qualifying_block(self):
        """Even if the laps have race-shaped data (fuel, wheelspin, etc.) the
        session_type='Qualifying Setup' must still produce a QUALIFYING block."""
        # Use laps that look like race laps (multiple fuel entries)
        race_like_laps = []
        for i in range(3):
            race_like_laps.append({
                "lap_num": i + 1,
                "lap_time_ms": 92_000 + i * 300,
                "fuel_used": 3.5 + i * 0.1,
                "is_pit_lap": 0,
                "is_out_lap": 0,
                "lock_up_count": 2,
                "wheelspin_count": 4,
                "snap_throttle_count": 3,
                "oversteer_count": 1,
                "oversteer_throttle_on": 0,
                "max_lat_g": 2.1,
                "brake_consistency_m": 3.0,
                "tyre_temp_fl_avg": 80.0,
                "tyre_temp_fr_avg": 82.0,
                "tyre_temp_rl_avg": 79.0,
                "tyre_temp_rr_avg": 81.0,
            })
        prompt = _setup_prompt("Qualifying Setup", laps=race_like_laps)
        assert "QUALIFYING" in prompt, (
            "Declared purpose (Qualifying Setup) must win over lap data shape"
        )
        assert "Per-Lap Telemetry — RACE" not in prompt


class TestEdgeCaseZeroCleanLaps:
    """Edge: zero clean laps → honest line in both disciplines."""

    def test_edge_zero_clean_laps_qualifying_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt([], "Qualifying")
        assert block is not None
        assert "No clean laps available" in block

    def test_edge_zero_clean_laps_race_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt([], "Race")
        assert block is not None
        assert "No clean laps available" in block

    def test_edge_zero_clean_laps_setup_prompt_qualifying_no_crash(self):
        """Empty laps list with qualifying session_type must not raise."""
        prompt = _setup_prompt("Qualifying Setup", laps=[])
        assert len(prompt) > 100


class TestEdgeCasePartialTyreTemps:
    """Edge: partial tyre temps (some non-zero, some zero) → renders what exists."""

    def test_edge_fl_only_renders_fl_not_not_recorded(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _laps(2)
        for r in rows:
            r["tyre_temp_fl_avg"] = 75.0
            r["tyre_temp_fr_avg"] = 0.0
            r["tyre_temp_rl_avg"] = 0.0
            r["tyre_temp_rr_avg"] = 0.0
        block = bdt(rows, "Race")
        assert "— not recorded" not in block
        assert "75" in block

    def test_edge_rr_only_renders_rr_not_not_recorded(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _laps(2)
        for r in rows:
            r["tyre_temp_fl_avg"] = 0.0
            r["tyre_temp_fr_avg"] = 0.0
            r["tyre_temp_rl_avg"] = 0.0
            r["tyre_temp_rr_avg"] = 88.0
        block = bdt(rows, "Race")
        assert "— not recorded" not in block
        assert "88" in block


class TestEdgeCaseNormalisePurposeRouting:
    """Edge: purpose only via normalise_purpose — handles all input types."""

    def test_edge_race_setup_string_routes_to_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(2), "Race Setup")
        assert block is not None
        assert "RACE" in block

    def test_edge_qualifying_setup_string_routes_to_qualifying(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(2), "Qualifying Setup")
        assert block is not None
        assert "QUALIFYING" in block

    def test_edge_enum_qualifying_routes_to_qualifying_block(self):
        from data.setup_context import SetupPurpose
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(2), SetupPurpose.QUALIFYING)
        assert block is not None
        assert "QUALIFYING" in block

    def test_edge_enum_unknown_returns_none(self):
        from data.setup_context import SetupPurpose
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_laps(2), SetupPurpose.UNKNOWN) is None

    def test_edge_none_returns_none(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_laps(2), None) is None


class TestEdgeCaseOneLapStdDev:
    """Edge: 1-lap std-dev → 'N/A (1 lap)'."""

    def test_edge_one_clean_lap_race_block_gives_n_a(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(1), "Race")
        assert "N/A (1 lap)" in block

    def test_edge_one_clean_lap_setup_prompt_gives_n_a(self):
        prompt = _setup_prompt("Race Setup", laps=_laps(1))
        assert "N/A (1 lap)" in prompt

    def test_edge_one_clean_lap_practice_prompt_gives_n_a(self):
        prompt = _practice_prompt(laps=_laps(1), purpose="Race")
        assert "N/A (1 lap)" in prompt


class TestEdgeCaseRF2Wiring:
    """Edge: RF2 wiring — _resolve_recent_laps is on the UI thread; defensive empty."""

    def test_edge_resolve_recent_laps_method_exists_in_source(self):
        src = (REPO / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_resolve_recent_laps" in src, (
            "_resolve_recent_laps helper must exist in setup_builder_ui.py"
        )

    def test_edge_resolve_recent_laps_returns_empty_list_on_no_db(self):
        """When _db is None the helper must return [] defensively."""
        from ui import setup_builder_ui as _sbu_mod

        stub = MagicMock()
        stub._db = None
        stub._resolve_recent_laps = types.MethodType(
            _sbu_mod.SetupBuilderMixin._resolve_recent_laps, stub
        )
        result = stub._resolve_recent_laps(7, "Suzuka")
        assert result == []

    def test_edge_resolve_recent_laps_returns_empty_list_on_zero_car_id(self):
        from ui import setup_builder_ui as _sbu_mod

        stub = MagicMock()
        stub._db = MagicMock()
        stub._resolve_recent_laps = types.MethodType(
            _sbu_mod.SetupBuilderMixin._resolve_recent_laps, stub
        )
        result = stub._resolve_recent_laps(0, "Suzuka")
        assert result == []
        stub._db.get_previous_session_id.assert_not_called()

    def test_edge_resolve_recent_laps_happy_path_returns_laps(self):
        from ui import setup_builder_ui as _sbu_mod

        fake_laps = [{"lap_num": 1, "lap_time_ms": 90_000}]
        stub = MagicMock()
        stub._db = MagicMock()
        stub._db.get_previous_session_id.return_value = 42
        stub._db.get_session_laps.return_value = fake_laps
        stub._resolve_recent_laps = types.MethodType(
            _sbu_mod.SetupBuilderMixin._resolve_recent_laps, stub
        )
        result = stub._resolve_recent_laps(7, "Suzuka")
        assert result == fake_laps
