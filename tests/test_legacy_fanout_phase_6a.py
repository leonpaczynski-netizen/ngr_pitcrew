"""Legacy Fan-Out Removal Phase 6a — dispatcher SessionTag snapshot.

Retirement-map item 1 (docs/LEGACY_FANOUT_PHASE_5.md §4): the EventDispatcher's
two telemetry-path `config["strategy"]` reads (per-lap DB tagging + the fallback
race-session open) are replaced by a frozen **SessionTag**
(track/car/config_id/event_id):

  * seeded once in `EventDispatcher.__init__` from the config it receives
    (before any thread starts — the single remaining main.py bridge read);
  * re-pushed by `MainWindow._push_session_tag()` (built from EventContext +
    StrategyContext — byte-identical to the old raw reads in sync) at the end of
    `_update_race_config` (Set-as-Active, garage car select, and the
    session-config restore all funnel through it), from `_on_event_save`'s
    active-event re-sync branch, and once at the end of `__init__`;
  * read by `_dispatch` as an immutable attribute — an atomic swap under the
    GIL, so no lock is needed between the UI (writer) and dispatcher (reader)
    threads, and no DB/context work happens per lap event.

These tests exercise the REAL EventDispatcher (plain threading.Thread — no Qt)
without starting its thread.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from data.event_context import build_event_context
from data.session_context import SessionTag, build_session_tag
from data.strategy_context import build_strategy_context

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def main_src():
    return (ROOT / "main.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dash_src():
    return ((ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (ROOT / "ui" / "event_planner_ui.py").read_text(encoding="utf-8"))


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# 1. SessionTag — pure model
# --------------------------------------------------------------------------- #
class TestSessionTag:
    def test_from_strategy_reproduces_legacy_reads(self):
        strat = {"track": "Spa", "car": "Porsche 963",
                 "config_id": "abc123", "event_id": 7}
        tag = SessionTag.from_strategy(strat)
        # OLD (verbatim): strat.get("track","") / ("car","") / ("config_id","")
        # and int(strat.get("event_id", 0)).
        assert tag.track == strat.get("track", "")
        assert tag.car == strat.get("car", "")
        assert tag.config_id == strat.get("config_id", "")
        assert tag.event_id == int(strat.get("event_id", 0))

    def test_from_strategy_defaults(self):
        for empty in ({}, None):
            tag = SessionTag.from_strategy(empty)
            assert tag == SessionTag(track="", car="", config_id="", event_id=0)

    def test_dead_unknown_default_note(self):
        # The old race-start fallback nominally defaulted track to "Unknown",
        # but DEFAULT_CONFIG has always materialised strategy.track = "" — so
        # the real pre-change behaviour for an unset track was "", preserved.
        from config_paths import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["strategy"]["track"] == ""
        assert SessionTag.from_strategy(DEFAULT_CONFIG["strategy"]).track == ""

    def test_build_session_tag_coerces(self):
        tag = build_session_tag(track=None, car=123, config_id=None, event_id="7")
        assert tag.track == "" and tag.car == "123"
        assert tag.config_id == "" and tag.event_id == 7

    def test_immutable(self):
        tag = SessionTag()
        with pytest.raises(Exception):
            tag.track = "X"  # frozen dataclass


class TestContextTagEquivalence:
    def test_context_built_tag_matches_strategy_built_tag_in_sync(self):
        event = {"id": 7, "name": "Race A", "track": "Spa"}
        strategy = {"track": "Spa", "car": "Porsche 963",
                    "config_id": "abc123", "event_id": 7}
        ev_ctx = build_event_context(event=event, strategy=strategy)
        sctx = build_strategy_context(strategy=strategy)
        from_contexts = build_session_tag(
            track=ev_ctx.track, car=ev_ctx.car,
            config_id=sctx.config_id, event_id=int(ev_ctx.event_id or 0))
        assert from_contexts == SessionTag.from_strategy(strategy)

    def test_empty_state_tags_match(self):
        ev_ctx = build_event_context()
        sctx = build_strategy_context()
        from_contexts = build_session_tag(
            track=ev_ctx.track, car=ev_ctx.car,
            config_id=sctx.config_id, event_id=int(ev_ctx.event_id or 0))
        assert from_contexts == SessionTag.from_strategy({})


# --------------------------------------------------------------------------- #
# 2. The REAL dispatcher — seed, swap, and both tagging sites
# --------------------------------------------------------------------------- #
def _make_dispatcher(config=None, db=None, recorder=None):
    import queue as _q
    from main import EventDispatcher
    return EventDispatcher(
        event_queue=_q.PriorityQueue(),
        announcer_handler=MagicMock(),
        logger=MagicMock(),
        bridge=MagicMock(),
        shift_muted_until=[0.0],
        strategy_engine=None,
        recorder=recorder,
        db=db,
        config=config,
        car_id_ref=[42],
        is_racing_ref=[False],
        tracker=None,
    )


class TestDispatcherTag:
    def test_seeded_from_config_at_construction(self):
        cfg = {"strategy": {"track": "Spa", "car": "P963",
                            "config_id": "abc", "event_id": 7}}
        d = _make_dispatcher(config=cfg)
        assert d._session_tag == SessionTag(
            track="Spa", car="P963", config_id="abc", event_id=7)

    def test_seed_with_no_config_is_empty(self):
        d = _make_dispatcher(config=None)
        assert d._session_tag == SessionTag()

    def test_set_session_tag_swaps_and_ignores_none(self):
        d = _make_dispatcher()
        new = SessionTag(track="Monza", car="X", config_id="z", event_id=3)
        d.set_session_tag(new)
        assert d._session_tag is new
        d.set_session_tag(None)          # safe no-op
        assert d._session_tag is new

    def test_race_started_opens_session_from_tag(self):
        from telemetry.state import EventType
        db = MagicMock()
        db.open_session.return_value = 55
        d = _make_dispatcher(db=db)
        d.set_session_tag(SessionTag(track="Spa", car="P963",
                                     config_id="abc", event_id=7))
        event = SimpleNamespace(type=EventType.RACE_STARTED,
                                data={"race_type": "lap"})
        d._dispatch(event)
        db.open_session.assert_called_once_with(
            42, "Spa", "race", "P963", "abc", event_id=7)
        assert d._session_id == 55

    def test_lap_completed_writes_event_id_from_tag(self):
        from telemetry.state import EventType
        db, recorder = MagicMock(), MagicMock()
        recorder.last_lap.return_value = {"x": 1}
        recorder.last_lap_frames.return_value = None
        d = _make_dispatcher(db=db, recorder=recorder)
        d.set_session_id(9)
        d.set_session_tag(SessionTag(event_id=7))
        record = SimpleNamespace(
            lap_num=3, lap_time_ms=90000, fuel_used=2.5,
            fuel_start=60.0, fuel_end=57.5, is_pit_lap=False,
            is_out_lap=False, delta_ms=120, session_type="practice",
        )
        d._dispatch(SimpleNamespace(type=EventType.LAP_COMPLETED,
                                    data={"record": record}))
        assert db.write_lap.call_count == 1
        assert db.write_lap.call_args.kwargs["event_id"] == 7

    def test_updated_tag_used_by_next_event(self):
        from telemetry.state import EventType
        db = MagicMock()
        db.open_session.return_value = 1
        d = _make_dispatcher(db=db)
        d.set_session_tag(SessionTag(track="Old", event_id=1))
        d.set_session_tag(SessionTag(track="New", car="C", config_id="q",
                                     event_id=2))
        d._dispatch(SimpleNamespace(type=EventType.RACE_STARTED,
                                    data={"race_type": "lap"}))
        db.open_session.assert_called_once_with(
            42, "New", "race", "C", "q", event_id=2)


# --------------------------------------------------------------------------- #
# 3. Source-scans — hot path clean, push sites wired
# --------------------------------------------------------------------------- #
class TestSourceScans:
    def test_dispatch_no_longer_reads_config(self, main_src):
        body = _method_body(main_src, "_dispatch")
        assert 'get("strategy"' not in body
        assert "_session_tag" in body

    def test_dispatcher_config_attr_gone(self, main_src):
        # The dispatcher holds no config dict any more — only the seed read in
        # __init__ (allowlisted) and the frozen tag.
        assert "self._config = config or {}" not in main_src

    def test_push_helper_builds_from_contexts(self, dash_src):
        body = _method_body(dash_src, "_push_session_tag")
        assert "build_session_tag(" in body
        assert "self._build_event_context()" in body
        assert "self._active_config_id()" in body
        assert "set_session_tag(" in body
        assert 'config.get("strategy"' not in body

    def test_push_sites_wired(self, dash_src):
        assert "self._push_session_tag()" in _method_body(dash_src, "_update_race_config")
        save = _method_body(dash_src, "_on_event_save")
        # Inside the active-event re-sync branch, after the fan-out write.
        assert "self._push_session_tag()" in save
        assert save.index("self._fanout_event_to_strategy(name)") \
            < save.index("self._push_session_tag()")
        init = _method_body(dash_src, "__init__")
        assert "self._push_session_tag()" in init

    def test_session_tag_model_is_pure(self):
        src = (ROOT / "data" / "session_context.py").read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import PyQt6|from PyQt6)", src, re.M)


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_fanout_writer_and_resync_preserved(self, dash_src):
        helper = _method_body(dash_src, "_fanout_event_to_strategy")
        assert 'strat = self._config.setdefault("strategy", {})' in helper
        assert "self._fanout_event_to_strategy(name)" in _method_body(
            dash_src, "_on_event_save")

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
