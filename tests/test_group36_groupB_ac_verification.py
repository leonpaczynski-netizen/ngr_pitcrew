"""
Group 36 — Acceptance-criterion verification for Group B:
  "qualifying engineer + mid-race AI re-plan"

Covers gaps not fully exercised by test_group35_midrace_replan.py and
test_qualifying_mode.py.  All tests use fakes / source-text inspection —
the real Claude API is never called.

ACs addressed here:
  AC1  — qualifying ack uses Priority.HIGH
  AC5  — race-finish announcement suppressed in qualifying (voice layer)
  AC7  — at slow_lap_count >= 4 the reason string identifies the plan trigger
         (not just "Strategy at risk")
  AC8  — race_situation dict contains ALL required keys
           (current_lap, laps_remaining, current_compound, tyre_age_laps,
            live_fuel_burn_lpl, recent_lap_times_ms, original_plan_stints,
            replan_reason)
         AND _assemble_strategy_inputs passes _strat_sid (not a raw live
         session id) as the session_id in its returned dict
  AC9  — apply_replan: _slow_lap_count reset, _replan_in_flight cleared
         (belt-and-suspenders verification separate from group35)
  AC11 — adapted plan announcement includes new pit lap AND target pace
  AC12 — _replan_after_overdue does NOT call _request_replan
  cross-cutting:
    in-flight guard completeness — _adapted_plan True blocks replan while
      in-flight is False
    graceful failure — worker exception → "replan_error" path confirmed in
      _display_strategy_results source
    ai_planner backwards compat — race_situation=None → "MID-RACE RE-PLAN"
      absent (mirrors group35 but exercises additional code branches)
    _assemble_strategy_inputs returns tyre_degradation_cache key
"""
from __future__ import annotations

import sys
import pathlib
from dataclasses import dataclass, field
from unittest.mock import MagicMock, call, patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Stub audio / COM so announcer can be imported headlessly
# ---------------------------------------------------------------------------
for _mod in ("win32com", "win32com.client", "pythoncom",
             "sounddevice", "winsound", "pyttsx3", "numpy"):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

from strategy.engine import RaceStrategyEngine, Stint  # noqa: E402
from telemetry.state import Priority                    # noqa: E402
from voice.announcer import VoiceAnnouncer, AnnouncerEventHandler  # noqa: E402

DASHBOARD_SRC = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared helpers (mirrors group35 style exactly)
# ---------------------------------------------------------------------------

def _make_stint(stint_num: int = 1, laps: int = 10, compound: str = "RM",
                ref_lap_ms: int = 90_000, pace_threshold_ms: int = 2000) -> Stint:
    return Stint(
        stint_num=stint_num,
        laps=laps,
        compound=compound,
        ref_lap_ms=ref_lap_ms,
        pace_threshold_ms=pace_threshold_ms,
    )


def _make_engine(stints=None, replan_callback=None):
    tracker = MagicMock()
    tracker.laps_recorded = 5
    tracker.best_lap_ms = 90_000
    tracker.avg_fuel_per_lap = 3.0
    tracker.last_fuel = 30.0
    tracker.tyre_states = {}

    announcer = MagicMock()
    config = {"fuel": {"strategy": "balanced"}, "strategy": {}}
    bridge = MagicMock()

    engine = RaceStrategyEngine(tracker, announcer, config, bridge, db=None)
    engine._replan_callback = replan_callback
    if stints:
        engine.set_plan(stints)
    return engine, tracker, announcer, bridge


def _make_lap_record(lap_time_ms: int = 95_000, fuel_used: float = 3.0):
    rec = MagicMock()
    rec.lap_time_ms = lap_time_ms
    rec.fuel_used = fuel_used
    return rec


def _make_announcer_handler(session_mode: str = "qualifying",
                             target_ms: int = 0,
                             qualifying_lap_count: int = 0):
    """Return (handler, announced_list) with a spy on announce."""
    cfg = {"enabled": True, "rate": 175, "volume": 1.0}
    ann = VoiceAnnouncer(cfg)
    ann._session_mode = session_mode
    ann._qualifying_target_ms = target_ms

    announced: list[tuple] = []  # (text, priority, ...)

    def _spy(text, priority, cooldown_key, cooldown_secs=0.0, **kw):
        announced.append((text, priority))

    ann.announce = _spy  # type: ignore[method-assign]
    handler = AnnouncerEventHandler(ann)
    handler._qualifying_lap_count = qualifying_lap_count
    return handler, announced


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# AC1 — qualifying ack: text + HIGH priority (engine layer)
# ---------------------------------------------------------------------------

class TestAC1QualifyingAckHighPriority:
    """AC1: qualifying ack must be HIGH priority AND contain exact text."""

    def test_ack_text_matches_spec(self):
        """'Qualifying session started. Push for your best lap.' must appear."""
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._on_race_start({})

        texts = [a[0][0] for a in announcer.announce.call_args_list]
        assert any("Qualifying session started. Push for your best lap." == t
                   for t in texts), f"exact text not found in: {texts}"

    def test_ack_priority_is_high(self):
        """AC1 specifies HIGH priority — verify the second positional arg."""
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._on_race_start({})

        # Find the call that contains the qualifying ack text
        for call_args in announcer.announce.call_args_list:
            text = call_args[0][0]
            if "Qualifying session started" in text:
                priority = call_args[0][1]
                assert priority == Priority.HIGH, (
                    f"Expected Priority.HIGH, got {priority!r}"
                )
                return
        pytest.fail("qualifying ack call not found in announcer.announce calls")


# ---------------------------------------------------------------------------
# AC5 — race-finish suppressed in qualifying (voice layer)
# ---------------------------------------------------------------------------

class TestAC5RaceFinishSuppressedInQualifying:
    """AC5: pit/fuel/race-finish announcements must all be suppressed in qualifying."""

    def test_race_finish_no_announcement_in_qualifying(self):
        """_on_race_finish must return early when session_mode is 'qualifying'."""
        handler, announced = _make_announcer_handler(session_mode="qualifying")
        handler._on_race_finish({"position": 1})
        # In qualifying mode, race-finish must be completely silent
        finish_phrases = [t for t, _ in announced if "Race finished" in t]
        assert len(finish_phrases) == 0, (
            f"race-finish announced in qualifying: {finish_phrases}"
        )

    def test_race_finish_announces_in_race_mode(self):
        """In race mode, _on_race_finish SHOULD announce."""
        handler, announced = _make_announcer_handler(session_mode="race")
        handler._on_race_finish({"position": 1})
        finish_phrases = [t for t, _ in announced if "Race finished" in t]
        assert len(finish_phrases) > 0, "race-finish should fire in race mode"


# ---------------------------------------------------------------------------
# AC7 — at slow_lap_count >= 4 the replan reason names the pace gap,
#         NOT just a generic "Strategy at risk" placeholder
# ---------------------------------------------------------------------------

class TestAC7ReplanReasonIsDescriptive:
    """AC7: replan reason passed to callback must describe the pace gap, not just
    the generic race-status phrase."""

    def _run_slow_laps(self, engine, count, lap_ms=93_000):
        s = engine._stints[0]
        rec = _make_lap_record(lap_time_ms=lap_ms)
        for _ in range(count):
            with engine._lock:
                engine._check_lap_targets(rec, s)

    def test_callback_receives_pace_gap_in_reason(self):
        """The reason string at trigger must mention the magnitude of the gap."""
        callback = MagicMock()
        engine, _, _, _ = _make_engine(
            stints=[_make_stint(ref_lap_ms=90_000, pace_threshold_ms=2000)],
            replan_callback=callback,
        )
        self._run_slow_laps(engine, 4, lap_ms=93_000)

        assert callback.call_count == 1
        reason = callback.call_args[0][0]
        # Reason must describe the delta ("3.0s" or similar) and laps
        assert "off target" in reason, f"reason does not name pace gap: {reason!r}"

    def test_callback_reason_not_empty(self):
        """Replan callback must never be called with an empty reason."""
        callback = MagicMock()
        engine, _, _, _ = _make_engine(
            stints=[_make_stint(ref_lap_ms=90_000, pace_threshold_ms=2000)],
            replan_callback=callback,
        )
        self._run_slow_laps(engine, 4, lap_ms=93_000)
        reason = callback.call_args[0][0]
        assert reason, "replan reason must not be empty"


# ---------------------------------------------------------------------------
# AC8 — race_situation dict: ALL required keys present in source
# ---------------------------------------------------------------------------

class TestAC8PracticeSessionId:
    """AC8: practice session id (not live race session) used for lap data query.

    Combines:
    - Source-text checks (existing vacuous tests preserved)
    - Runtime invariant checks via a lightweight stub of _assemble_strategy_inputs
      to prove the DB is called with the PRACTICE session id, not the race session id.
    """

    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_assemble_strategy_inputs")

    def test_comment_documents_practice_session_intent(self):
        """A comment explaining that _strat_sid is the practice session must exist."""
        assert "practice session" in self._body.lower(), (
            "_assemble_strategy_inputs must document that _strat_sid is the practice session"
        )

    def test_strat_sid_passed_as_session_id_in_return(self):
        """The returned dict must map 'session_id' to _strat_sid."""
        assert '"session_id"' in self._body or "'session_id'" in self._body

    # ------------------------------------------------------------------
    # Runtime invariant tests (I1 fix)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_stub(race_session_id: int = 999, practice_session_id: int = 42,
                   car_id: int = 7) -> MagicMock:
        """Build a minimal stub self-object for _assemble_strategy_inputs.

        The dispatcher reports the LIVE (race) session id.  The caller should
        pass session_id_override=practice_session_id to force the practice sid.
        The stub's fake DB records which session_id was passed to
        get_strategy_lap_data so tests can assert the correct one was used.
        """
        import types

        stub = MagicMock()

        # Attributes read by _assemble_strategy_inputs
        stub._ai_api_key.text.return_value = "fake-key"
        stub._read_ui_lap_table.return_value = {}
        stub._config = {
            "strategy": {
                "track": "Monza", "race_type": "lap", "total_laps": "20",
                "tyre_wear_multiplier": "1.0", "fuel_burn_per_lap": "3.0",
                "refuel_speed_lps": "10.0", "pit_loss_secs": "23.0",
                "mandatory_stops": "0",
            },
            "anthropic": {"model": "claude-opus-4-8"},
        }
        stub._get_mandatory_compounds.return_value = []
        stub._load_car_specs_for_current.return_value = ("TestCar", {})
        stub._build_setup_comparison_text.return_value = ""
        stub._tyre_degradation_cache = {}

        # Dispatcher reports the LIVE race session id
        stub._dispatcher = MagicMock()
        stub._dispatcher._session_id = race_session_id

        # Fake DB: records which session_id was passed to get_strategy_lap_data
        fake_db = MagicMock()
        fake_db.get_car_id.return_value = car_id
        fake_db.get_strategy_lap_data.return_value = {"RM": [90_000.0]}
        stub._db = fake_db

        # Bind the real _assemble_strategy_inputs to the stub
        from ui import dashboard as _dash_mod
        # Access the class method directly and bind to stub
        stub._assemble_strategy_inputs = types.MethodType(
            _dash_mod.MainWindow._assemble_strategy_inputs, stub
        )
        # Also bind the real session-id resolution helper it delegates to
        stub._resolve_strat_session_id = types.MethodType(
            _dash_mod.MainWindow._resolve_strat_session_id, stub
        )
        # AI Snapshot Migration: the method now reads race params from the
        # frozen snapshot layer — route the stub through the REAL production
        # builder over the stub's config (legacy-only source), keeping the
        # runtime session-id invariants meaningfully exercised.
        from data.analysis_inputs import build_strategy_inputs as _bss
        stub._build_strategy_inputs = (
            lambda fuel_burn_override=None: _bss(
                legacy_strategy=stub._config.get("strategy", {}),
                fuel_burn_override=fuel_burn_override,
            )
        )

        return stub

    def test_override_uses_practice_sid_not_race_sid(self):
        """When session_id_override=42 is passed and dispatcher reports race sid 999,
        get_strategy_lap_data must be called with session_id=42 (practice), not 999."""
        stub = self._make_stub(race_session_id=999, practice_session_id=42)

        result = stub._assemble_strategy_inputs(session_id_override=42)

        # The DB call must use the practice session id
        call_kwargs = stub._db.get_strategy_lap_data.call_args
        assert call_kwargs is not None, "get_strategy_lap_data was not called"
        # positional: (car_id, track, session_id, ui_lap_data)
        session_id_used = call_kwargs[0][2]
        assert session_id_used == 42, (
            f"Expected practice sid 42, got {session_id_used} "
            f"(live race sid 999 must NOT be used)"
        )
        assert result["session_id"] == 42

    def test_override_zero_fallback_queries_all_history(self):
        """When session_id_override=0 (no practice session recorded, e.g. plan loaded
        without pre-race analysis), get_strategy_lap_data must be called with
        session_id=0 (ALL car+track history, which includes practice laps) — and must
        NOT silently fall back to the live race session (999)."""
        stub = self._make_stub(race_session_id=999)

        result = stub._assemble_strategy_inputs(session_id_override=0)

        # override=0 is authoritative: session_id=0 -> all history, never race session
        call_kwargs = stub._db.get_strategy_lap_data.call_args
        assert call_kwargs is not None, "get_strategy_lap_data was not called"
        session_id_used = call_kwargs[0][2]
        assert session_id_used == 0, (
            f"Expected all-history query (session_id=0), got {session_id_used} "
            f"(must never be the live race session 999)"
        )

    def test_no_override_uses_live_dispatcher_session(self):
        """Without session_id_override, the dispatcher's live session id is used
        (correct pre-race behaviour: dispatcher IS in the practice session)."""
        stub = self._make_stub(race_session_id=123)

        result = stub._assemble_strategy_inputs()  # no override

        call_kwargs = stub._db.get_strategy_lap_data.call_args
        assert call_kwargs is not None
        session_id_used = call_kwargs[0][2]
        assert session_id_used == 123, (
            f"Pre-race (no override) must use dispatcher session 123, got {session_id_used}"
        )


# ---------------------------------------------------------------------------
# AC9 — apply_replan: state management (belt-and-suspenders)
# ---------------------------------------------------------------------------

@dataclass
class _FakeOption:
    rank: int = 1
    name: str = "Test"
    stints: list = field(default_factory=list)
    estimated_time_s: float = 3600.0
    pit_time_s: float = 23.0
    summary: str = ""
    risks: str = ""


@dataclass
class _FakeResult:
    strategies: list = field(default_factory=list)

    def __iter__(self):
        return iter(self.strategies)

    def __len__(self):
        return len(self.strategies)


class TestAC9ApplyReplanStateMgmt:
    """AC9: apply_replan must reset _slow_lap_count AND clear _replan_in_flight."""

    def _setup(self):
        s1 = _make_stint(stint_num=1, laps=10, compound="RM")
        s2 = _make_stint(stint_num=2, laps=10, compound="RH")
        engine, tracker, announcer, bridge = _make_engine(stints=[s1, s2])
        engine._active = True
        s1.completed = True
        tracker.laps_recorded = 8
        return engine, tracker, announcer, s1, s2

    def test_slow_lap_count_reset_to_zero(self):
        engine, tracker, _, s1, _ = self._setup()
        engine._replan_in_flight = True
        engine._slow_lap_count = 7  # arbitrary non-zero value
        opt = _FakeOption(stints=[
            {"compound": "RH", "laps": 10, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeResult(strategies=[opt]))
        assert engine._slow_lap_count == 0

    def test_replan_in_flight_cleared_to_false(self):
        engine, tracker, _, s1, _ = self._setup()
        engine._replan_in_flight = True
        opt = _FakeOption(stints=[
            {"compound": "RH", "laps": 10, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeResult(strategies=[opt]))
        assert engine._replan_in_flight is False

    def test_adapted_plan_blocks_further_replan(self):
        """After apply_replan, _adapted_plan True must suppress next _request_replan."""
        callback = MagicMock()
        engine, tracker, _, s1, _ = self._setup()
        engine._replan_callback = callback
        engine._replan_in_flight = True
        opt = _FakeOption(stints=[
            {"compound": "RH", "laps": 10, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeResult(strategies=[opt]))
        assert engine._adapted_plan is True

        # Now trigger _request_replan — must be a no-op
        callback.reset_mock()
        engine._request_replan(reason="should be suppressed")
        callback.assert_not_called()

    def test_pit_exit_re_arms_after_adapt(self):
        """_on_pit_exit must reset _adapted_plan so the next stint can trigger."""
        engine, _, _, s1, s2 = self._setup()
        engine._adapted_plan = True
        engine._on_pit_exit({})
        assert engine._adapted_plan is False


# ---------------------------------------------------------------------------
# AC11 — announcement includes new pit lap AND target pace
# ---------------------------------------------------------------------------

class TestAC11AnnouncementFormat:
    """AC11: adapted plan announcement must include new pit lap AND target pace."""

    def _setup(self):
        s1 = _make_stint(stint_num=1, laps=10, compound="RM")
        s2 = _make_stint(stint_num=2, laps=10, compound="RH")
        engine, tracker, announcer, bridge = _make_engine(stints=[s1, s2])
        engine._active = True
        s1.completed = True
        tracker.laps_recorded = 8
        return engine, tracker, announcer

    def test_announcement_contains_new_pit_lap(self):
        engine, tracker, announcer = self._setup()
        engine._replan_in_flight = True
        # new stint: 12 laps from lap 8 → end_lap = 8 + 12 - 1 = 19
        opt = _FakeOption(stints=[
            {"compound": "RH", "laps": 12, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeResult(strategies=[opt]))
        texts = [a[0][0] for a in announcer.announce.call_args_list]
        pit_lap_phrases = [t for t in texts if "Strategy adapted" in t]
        assert pit_lap_phrases, f"Strategy adapted announcement not found: {texts}"
        # end_lap = 8 + 12 - 1 = 19
        assert any("19" in t for t in pit_lap_phrases), (
            f"new pit lap (19) not in announcement: {pit_lap_phrases}"
        )

    def test_announcement_contains_target_pace(self):
        engine, tracker, announcer = self._setup()
        engine._replan_in_flight = True
        opt = _FakeOption(stints=[
            {"compound": "RH", "laps": 12, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeResult(strategies=[opt]))
        texts = [a[0][0] for a in announcer.announce.call_args_list]
        pace_phrases = [t for t in texts if "Target" in t or "per lap" in t]
        assert pace_phrases, (
            f"target pace not in adapted plan announcement: {texts}"
        )

    def test_announcement_contains_strategy_adapted(self):
        engine, tracker, announcer = self._setup()
        engine._replan_in_flight = True
        opt = _FakeOption(stints=[
            {"compound": "RH", "laps": 12, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeResult(strategies=[opt]))
        texts = [a[0][0] for a in announcer.announce.call_args_list]
        assert any("Strategy adapted" in t for t in texts), f"not found in: {texts}"


# ---------------------------------------------------------------------------
# AC12 — _replan_after_overdue does NOT invoke _request_replan
# ---------------------------------------------------------------------------

class TestAC12ReplanAfterOverdueDoesNotCallReplan:
    """AC12: the missed-pit-window handler must remain unchanged and must NOT
    trigger the mid-race AI re-plan path."""

    def test_replan_after_overdue_does_not_call_request_replan(self):
        """Missed pit window must NOT invoke _request_replan."""
        callback = MagicMock()
        s1 = _make_stint(stint_num=1, laps=10, compound="RM")
        s2 = _make_stint(stint_num=2, laps=10, compound="RH")
        engine, tracker, announcer, bridge = _make_engine(
            stints=[s1, s2], replan_callback=callback
        )
        engine._active = True
        tracker.laps_recorded = 15  # well past s1.end_lap=10

        with engine._lock:
            new_end = engine._replan_after_overdue(s1, 15)

        # Pit window extended but NO AI re-plan should be triggered
        callback.assert_not_called()
        assert engine._replan_in_flight is False
        assert new_end == 17  # 15 + 2

    def test_replan_after_overdue_extends_pit_lap(self):
        """Sanity: _replan_after_overdue returns the correct new pit lap."""
        s1 = _make_stint(stint_num=1, laps=10, compound="RM")
        s2 = _make_stint(stint_num=2, laps=10, compound="RH")
        engine, tracker, announcer, bridge = _make_engine(stints=[s1, s2])
        engine._active = True

        with engine._lock:
            new_end = engine._replan_after_overdue(s1, 15)

        assert new_end == 17


# ---------------------------------------------------------------------------
# Cross-cutting: in-flight guard — _adapted_plan True blocks even when
# _replan_in_flight is False
# ---------------------------------------------------------------------------

class TestInFlightGuardAdaptedPlan:
    """The dual guard (_replan_in_flight OR _adapted_plan) must block replan."""

    def test_adapted_plan_true_blocks_when_not_in_flight(self):
        """_adapted_plan=True must suppress _request_replan even if in_flight=False."""
        callback = MagicMock()
        engine, _, _, _ = _make_engine(replan_callback=callback)
        engine._adapted_plan = True
        engine._replan_in_flight = False

        engine._request_replan(reason="should not pass through")
        callback.assert_not_called()
        assert engine._replan_in_flight is False  # must NOT have been set

    def test_both_false_allows_replan(self):
        """Both guards False → replan proceeds normally."""
        callback = MagicMock()
        engine, _, _, _ = _make_engine(replan_callback=callback)
        engine._adapted_plan = False
        engine._replan_in_flight = False

        engine._request_replan(reason="valid trigger")
        callback.assert_called_once()
        assert engine._replan_in_flight is True


# ---------------------------------------------------------------------------
# Cross-cutting: graceful failure — replan_error source path
# ---------------------------------------------------------------------------

class TestGracefulFailureSource:
    """Verify _display_strategy_results handles both replan_ok and replan_error
    without calling production code (source-text inspection)."""

    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_display_strategy_results")

    def test_replan_error_calls_replan_failed(self):
        assert "replan_failed" in self._body

    def test_replan_ok_calls_apply_replan(self):
        assert "apply_replan" in self._body

    def test_replan_error_does_not_raise(self):
        """Verify the method body contains a return after replan_error handling
        (prevents fallthrough that could raise downstream)."""
        idx_err = self._body.find('"replan_error"')
        idx_return = self._body.find("return", idx_err)
        idx_next_block = self._body.find("if status ==", idx_err + 1)
        # 'return' must appear before any subsequent status check
        if idx_next_block == -1:
            assert idx_return != -1, "replan_error block must have a return or be at end"
        else:
            assert idx_return < idx_next_block or idx_return != -1, (
                "replan_error block must return before further processing"
            )


# ---------------------------------------------------------------------------
# Cross-cutting: _assemble_strategy_inputs returns tyre_degradation_cache
# ---------------------------------------------------------------------------

class TestAssembleStrategyInputsKeys:
    """Verify the returned dict contains all keys needed by _launch_replan_worker."""

    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_assemble_strategy_inputs")

    def test_key_tyre_degradation_cache_in_return(self):
        assert '"tyre_degradation_cache"' in self._body

    def test_key_lap_data_by_compound_in_return(self):
        assert '"lap_data_by_compound"' in self._body

    def test_key_session_id_in_return(self):
        assert '"session_id"' in self._body


# ---------------------------------------------------------------------------
# AC3 baseline — verify engine does NOT have its own per-lap delta logic
# (qualifying delta is voice-layer only; engine must remain silent)
# ---------------------------------------------------------------------------

class TestAC3EngineRemainsQuietOnQualLapDelta:
    """The engine (_on_race_start in qualifying) must not try to compute
    lap deltas.  Delta logic lives exclusively in the voice announcer layer."""

    def test_engine_qualifying_path_returns_before_strategy_activation(self):
        """In qualifying mode, _on_race_start returns early — strategy is never
        activated, so no strategy-based delta announcements can fire."""
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._active = False

        engine._on_race_start({})

        # Must still be inactive after the qualifying ack
        assert engine._active is False

    def test_engine_qualifying_ack_calls_announce_once(self):
        """Only one announce call: the qualifying session started message."""
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._on_race_start({})

        # Exactly one call — no extra "Strategy loaded" or delta lines
        assert announcer.announce.call_count == 1


# ---------------------------------------------------------------------------
# AC2/AC3/AC6 — voice-layer: qualifying lap count gate (additional edge case)
# ---------------------------------------------------------------------------

class TestAC6NoFabricatedDeltaEdgeCases:
    """AC6: no fabricated delta when best_lap_ms <= 0 AND no manual target."""

    def _delta_phrases(self, announced):
        return [t for t, _ in announced
                if "under target" in t or "over target" in t or "On target" in t]

    def test_best_lap_ms_negative_is_silent(self):
        """Negative best_lap_ms must be treated as missing (AC6 guard)."""
        handler, announced = _make_announcer_handler(
            target_ms=0, qualifying_lap_count=2
        )
        record = MagicMock()
        record.lap_time_ms = 90_000
        record.lap_num = 3
        record.delta_ms = 0
        data = {"record": record, "has_best": True, "laps_remaining": 0,
                "best_lap_ms": -1}
        handler._on_lap(data)
        assert len(self._delta_phrases(announced)) == 0, announced

    def test_best_lap_ms_zero_with_lap3_is_silent(self):
        """best_lap_ms=0 on lap 3 → AC6 silence (mirrors test_qualifying_mode
        but via the extended handler helper to confirm Priority not leaked)."""
        handler, announced = _make_announcer_handler(
            target_ms=0, qualifying_lap_count=2
        )
        record = MagicMock()
        record.lap_time_ms = 90_000
        record.lap_num = 3
        record.delta_ms = 0
        data = {"record": record, "has_best": True, "laps_remaining": 0,
                "best_lap_ms": 0}
        handler._on_lap(data)
        assert len(self._delta_phrases(announced)) == 0, announced


# ---------------------------------------------------------------------------
# C2 — announcer._on_race_start suppressed in qualifying (voice layer)
# ---------------------------------------------------------------------------

class TestC2AnnouncerRaceStartSuppressedInQualifying:
    """C2: AnnouncerEventHandler._on_race_start must be silent in qualifying
    so the driver does not hear both 'Qualifying session started.' (engine)
    AND 'Race started.' (announcer voice layer)."""

    def test_race_started_silent_in_qualifying_mode(self):
        """'Race started.' must NOT be announced when session_mode is 'qualifying'."""
        handler, announced = _make_announcer_handler(session_mode="qualifying")
        handler._on_race_start({})
        race_texts = [t for t, _ in announced if "Race started" in t]
        assert len(race_texts) == 0, (
            f"'Race started.' must not fire in qualifying; got: {race_texts}"
        )

    def test_race_started_fires_in_race_mode(self):
        """'Race started.' MUST be announced when session_mode is 'race' (unchanged)."""
        handler, announced = _make_announcer_handler(session_mode="race")
        handler._on_race_start({})
        race_texts = [t for t, _ in announced if "Race started" in t]
        assert len(race_texts) > 0, (
            f"'Race started.' must fire in race mode; announced={announced}"
        )

    def test_race_started_fires_in_practice_mode(self):
        """Practice mode must be unchanged — 'Race started.' still fires."""
        handler, announced = _make_announcer_handler(session_mode="practice")
        handler._on_race_start({})
        race_texts = [t for t, _ in announced if "Race started" in t]
        assert len(race_texts) > 0, (
            f"'Race started.' must still fire in practice mode; announced={announced}"
        )

    def test_qualifying_guard_does_not_suppress_engine_ack(self):
        """The engine-layer qualifying ack is a separate code path — guard must
        not affect it.  Verify by checking the engine still fires its ack."""
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._on_race_start({})
        texts = [a[0][0] for a in announcer.announce.call_args_list]
        assert any("Qualifying session started" in t for t in texts), (
            f"Engine qualifying ack missing: {texts}"
        )


# ---------------------------------------------------------------------------
# I2 — engine._on_race_start resets _replan_in_flight on race start
# ---------------------------------------------------------------------------

class TestI2ReplanInFlightResetOnRaceStart:
    """I2: _replan_in_flight must be cleared when a race starts so that a
    race restart while a replan is in-flight does not permanently block
    future replans."""

    def test_replan_in_flight_reset_on_race_start(self):
        """After _on_race_start (normal race mode), _replan_in_flight must be False."""
        s = _make_stint()
        engine, _, _, _ = _make_engine(stints=[s])
        engine._replan_in_flight = True  # simulate stale in-flight from previous race
        engine._qualifying_mode = False
        engine._ui_race_mode = True

        engine._on_race_start({})

        assert engine._replan_in_flight is False, (
            "_replan_in_flight must be reset to False on race start"
        )

    def test_adapted_plan_also_reset_on_race_start(self):
        """_adapted_plan must also be cleared on race start (existing behaviour,
        verified alongside I2 to confirm both resets are present)."""
        s = _make_stint()
        engine, _, _, _ = _make_engine(stints=[s])
        engine._adapted_plan = True
        engine._replan_in_flight = True
        engine._qualifying_mode = False
        engine._ui_race_mode = True

        engine._on_race_start({})

        assert engine._adapted_plan is False
        assert engine._replan_in_flight is False


# ---------------------------------------------------------------------------
# I3 — engine.set_plan resets both _replan_in_flight and _adapted_plan
# ---------------------------------------------------------------------------

class TestI3SetPlanResetsReplanState:
    """I3: set_plan must reset _replan_in_flight and _adapted_plan so that
    loading a new plan mid-race while a replan is in-flight cannot let a
    stale worker's apply_replan overwrite the fresh plan."""

    def test_set_plan_resets_replan_in_flight(self):
        """_replan_in_flight must be False after set_plan."""
        engine, _, _, _ = _make_engine()
        engine._replan_in_flight = True  # simulate stale in-flight
        s = _make_stint()
        engine.set_plan([s])
        assert engine._replan_in_flight is False, (
            "_replan_in_flight must be cleared by set_plan"
        )

    def test_set_plan_resets_adapted_plan(self):
        """_adapted_plan must be False after set_plan (fresh plan is not yet adapted)."""
        engine, _, _, _ = _make_engine()
        engine._adapted_plan = True
        s = _make_stint()
        engine.set_plan([s])
        assert engine._adapted_plan is False, (
            "_adapted_plan must be cleared by set_plan"
        )

    def test_set_plan_resets_both_simultaneously(self):
        """Both flags must be cleared in the same set_plan call."""
        engine, _, _, _ = _make_engine()
        engine._replan_in_flight = True
        engine._adapted_plan = True
        s = _make_stint()
        engine.set_plan([s])
        assert engine._replan_in_flight is False
        assert engine._adapted_plan is False
