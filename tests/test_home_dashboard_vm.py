"""Home Dashboard Build sprint — tests for ui/home_dashboard_vm.py and the
Home tab wiring.

Two kinds of tests, both following the project's no-Qt convention:
  1. Pure unit tests of ui.home_dashboard_vm (imported directly — no PyQt6),
     driving it with REAL contexts built by the data/*_context builders.
  2. Source-scan tests that the dashboard/setup-builder/track-modelling wiring
     is additive and display-only (no QApplication required).
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from ui import home_dashboard_vm as hd
from ui import product_flow as pf
from data.event_context import build_event_context, empty_event_context
from data.strategy_context import (
    build_strategy_context, build_strategy_prompt_snapshot,
    empty_strategy_context,
)
from data.setup_context import build_setup_context, empty_setup_context
from data.track_context import build_track_context, empty_track_context
from data.ai_context_snapshot import build_strategy_ai_snapshot


ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sb_src():
    return (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tm_src():
    return (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    """Extract a method body (until the next def at the same indent)."""
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# Context fixtures (real builders, plain dict inputs)
# --------------------------------------------------------------------------- #
def _event_ctx(**over):
    ev = {
        "name": "Test GP", "track": "Fuji Speedway", "race_type": "lap",
        "laps": 20, "tyre_wear": 2.0, "fuel_mult": 1.0, "refuel_rate_lps": 10.0,
        "bop": True, "tuning": False, "avail_tyres": ["RM", "RH"],
        "req_tyres": ["RM"], "mandatory_stops": 1,
    }
    ev.update(over)
    return build_event_context(event=ev, strategy={"car": "Porsche RSR '17"})


def _strategy_ctx(event_ctx, **over):
    strat = {
        "stops": [
            {"laps": 10, "compound": "RM"},
            {"laps": 10, "compound": "RH"},
        ],
        "fuel_burn_per_lap": 2.1,
        "pit_loss_secs": 23.0,
        "config_id": "abc123def0",
    }
    strat.update(over)
    return build_strategy_context(strategy=strat, event_context=event_ctx)


def _setup_ctx(event_ctx, strategy_snapshot=None, **over):
    setup = {
        "setup_label": "R Test GP 1", "setup_type": "Race Setup",
        "car": "Porsche RSR '17", "track": "Fuji Speedway",
        "ride_height_f": 90,
    }
    setup.update(over)
    return build_setup_context(
        setup=setup,
        recommendation={
            "analysis": "Front-limited in slow corners.",
            "changes": [{"setting": "Ride height (front)", "from": "90",
                         "to": "85", "why": "reduce understeer"}],
            "setup_fields": {"ride_height_f": 85},
            "primary_issue": "understeer",
            "confidence": "medium",
        },
        event_context=event_ctx,
        strategy_snapshot=strategy_snapshot,
    )


def _track_ctx(event_ctx=None, **kw):
    defaults = dict(
        selected_location_id="fuji_speedway",
        selected_layout_id="fuji_speedway__gp",
        event_context=event_ctx,
        seed_audit=SimpleNamespace(
            has_metadata=True, has_lap_length=True, has_corner_windows=True,
            has_sector_definitions=True, has_corner_complexes=False,
            has_seed_centreline=True, seed_source="track_library",
            corner_count=16,
        ),
        file_audit=SimpleNamespace(
            ref_path_exists=True, ref_path_point_count=200,
            calibration_laps_exists=True, reviewed_exists=True,
            offset_exists=True,
        ),
        station_map_exists=True,
    )
    defaults.update(kw)
    return build_track_context(**defaults)


# --------------------------------------------------------------------------- #
# 1. Empty state
# --------------------------------------------------------------------------- #
class TestEmptyState:
    def test_empty_state_all_cards_missing(self):
        s = hd.empty_home_dashboard_state()
        assert s.schema == hd.HOME_DASHBOARD_SCHEMA
        assert [c.key for c in s.cards] == list(hd.CARD_ORDER)
        for c in s.cards:
            assert c.status == hd.HomeDashboardStatus.MISSING

    def test_empty_state_next_action_is_create_event(self):
        s = hd.empty_home_dashboard_state()
        assert "event" in s.next_action.action.lower()
        assert s.next_action.tab == "Event Planner"
        assert s.next_action.complete is False

    def test_empty_contexts_behave_like_none(self):
        s = hd.build_home_dashboard_state(
            event_context=empty_event_context(),
            strategy_context=empty_strategy_context(),
            setup_context=empty_setup_context(),
            track_context=empty_track_context(),
        )
        for c in s.cards:
            assert c.status == hd.HomeDashboardStatus.MISSING


# --------------------------------------------------------------------------- #
# 2. Event selected but nothing else
# --------------------------------------------------------------------------- #
class TestEventOnly:
    def test_event_card_populates(self):
        ev = _event_ctx()
        s = hd.build_home_dashboard_state(event_context=ev)
        card = s.card(hd.CARD_RACE_SETUP)
        assert card.status == hd.HomeDashboardStatus.READY
        text = " ".join(card.lines)
        assert "Test GP" in text
        assert "Porsche RSR '17" in text
        assert "Fuji Speedway" in text
        assert "Lap race, 20 laps" in text
        assert "Tuning: Locked" in text
        assert "BoP: On" in text

    def test_other_cards_still_missing(self):
        s = hd.build_home_dashboard_state(event_context=_event_ctx())
        assert s.card(hd.CARD_SETUP).status == hd.HomeDashboardStatus.MISSING
        assert s.card(hd.CARD_STRATEGY).status == hd.HomeDashboardStatus.MISSING

    def test_incomplete_event_gets_warnings(self):
        ev = build_event_context(event={"name": "Bare", "race_type": "lap"})
        s = hd.build_home_dashboard_state(event_context=ev)
        card = s.card(hd.CARD_RACE_SETUP)
        assert card.status == hd.HomeDashboardStatus.ATTENTION
        assert card.warnings


# --------------------------------------------------------------------------- #
# 3./4. Strategy — fresh and stale against the event
# --------------------------------------------------------------------------- #
class TestStrategyCard:
    def test_fresh_strategy_is_ready(self):
        ev = _event_ctx()
        sc = _strategy_ctx(ev)
        s = hd.build_home_dashboard_state(event_context=ev, strategy_context=sc)
        card = s.card(hd.CARD_STRATEGY)
        assert card.status == hd.HomeDashboardStatus.READY
        text = " ".join(card.lines)
        assert "2 stints" in text and "1 pit stop" in text
        assert "RM" in text and "RH" in text
        assert "Pit on lap: 10" in text
        assert "2.1 L per lap" in text

    def test_stale_strategy_against_changed_event(self):
        old_event = _event_ctx()
        sc = _strategy_ctx(old_event)          # built against the old event
        new_event = _event_ctx(laps=30)        # event edited afterwards
        s = hd.build_home_dashboard_state(event_context=new_event,
                                          strategy_context=sc)
        card = s.card(hd.CARD_STRATEGY)
        assert card.status == hd.HomeDashboardStatus.ATTENTION
        msgs = [w.message for w in card.warnings]
        assert any("before the current event settings changed" in m for m in msgs)
        assert any(w.kind == "stale" for w in card.warnings)

    def test_no_plan_is_missing_not_stale(self):
        ev = _event_ctx()
        sc = build_strategy_context(strategy={"config_id": "x"}, event_context=ev)
        s = hd.build_home_dashboard_state(event_context=ev, strategy_context=sc)
        assert s.card(hd.CARD_STRATEGY).status == hd.HomeDashboardStatus.MISSING

    def test_plan_without_fuel_calibration_warns(self):
        ev = _event_ctx()
        sc = _strategy_ctx(ev, fuel_burn_per_lap=0)
        s = hd.build_home_dashboard_state(event_context=ev, strategy_context=sc)
        card = s.card(hd.CARD_STRATEGY)
        msgs = " ".join(w.message for w in card.warnings)
        assert "not calibrated" in msgs


# --------------------------------------------------------------------------- #
# 5./6./7. Setup — fresh, stale vs event, stale vs strategy snapshot
# --------------------------------------------------------------------------- #
class TestSetupCard:
    def test_fresh_setup_is_ready_and_matches_event(self):
        ev = _event_ctx()
        sc = _strategy_ctx(ev)
        snap = build_strategy_prompt_snapshot(sc, ev)
        setup = _setup_ctx(ev, snap)
        s = hd.build_home_dashboard_state(
            event_context=ev, strategy_context=sc, setup_context=setup)
        card = s.card(hd.CARD_SETUP)
        assert card.status == hd.HomeDashboardStatus.READY
        text = " ".join(card.lines)
        assert "R Test GP 1" in text
        assert "For: Race" in text
        assert "Built for the current event settings." in text
        assert "understeer" in text

    def test_stale_setup_against_changed_event(self):
        old_event = _event_ctx()
        setup = _setup_ctx(old_event)
        new_event = _event_ctx(tyre_wear=5.0)
        s = hd.build_home_dashboard_state(event_context=new_event,
                                          setup_context=setup)
        card = s.card(hd.CARD_SETUP)
        assert card.status == hd.HomeDashboardStatus.ATTENTION
        msgs = [w.message for w in card.warnings]
        assert any("older event version" in m for m in msgs)

    def test_stale_setup_against_changed_strategy_snapshot(self):
        ev = _event_ctx()
        sc_old = _strategy_ctx(ev)
        snap_old = build_strategy_prompt_snapshot(sc_old, ev)
        setup = _setup_ctx(ev, snap_old)
        # The strategy plan changes after the setup was built.
        sc_new = _strategy_ctx(ev, stops=[{"laps": 20, "compound": "RM"}])
        s = hd.build_home_dashboard_state(
            event_context=ev, strategy_context=sc_new, setup_context=setup)
        card = s.card(hd.CARD_SETUP)
        msgs = [w.message for w in card.warnings]
        assert any("before the strategy plan changed" in m for m in msgs)

    def test_setup_missing_identity_warns(self):
        setup = build_setup_context(setup={"setup_label": "Mystery",
                                           "setup_type": "Race Setup"})
        s = hd.build_home_dashboard_state(setup_context=setup)
        card = s.card(hd.CARD_SETUP)
        msgs = " ".join(w.message for w in card.warnings)
        assert "no car or track identity" in msgs


# --------------------------------------------------------------------------- #
# 8.–11. Track Intelligence
# --------------------------------------------------------------------------- #
class TestTrackCard:
    def test_full_track_data_is_ready(self):
        ev = _event_ctx(track="Fuji Speedway")
        tc = _track_ctx(ev)
        s = hd.build_home_dashboard_state(event_context=ev, track_context=tc)
        card = s.card(hd.CARD_TRACK)
        assert card.status == hd.HomeDashboardStatus.READY
        text = " ".join(card.lines)
        assert "Live corner mapping: ready to attempt" in text

    def test_missing_track_identity(self):
        # Display name only (from the legacy strategy dict) — ids are missing.
        tc = build_track_context(strategy={"track": "Fuji Speedway"})
        s = hd.build_home_dashboard_state(track_context=tc)
        card = s.card(hd.CARD_TRACK)
        msgs = " ".join(w.message for w in card.warnings)
        assert "identity is missing" in msgs

    def test_seed_metadata_present_geometry_missing(self):
        tc = _track_ctx(
            seed_audit=SimpleNamespace(
                has_metadata=True, has_lap_length=True,
                has_corner_windows=True, has_sector_definitions=False,
                has_corner_complexes=False, has_seed_centreline=False,
                seed_source="track_library", corner_count=16,
            ),
        )
        s = hd.build_home_dashboard_state(track_context=tc)
        text = " ".join(s.card(hd.CARD_TRACK).lines)
        assert "Track info (seed): available" in text
        assert "Track shape (geometry): not available" in text

    def test_station_map_unavailable_blocks_live_mapping(self):
        tc = _track_ctx(station_map_exists=False)
        s = hd.build_home_dashboard_state(track_context=tc)
        card = s.card(hd.CARD_TRACK)
        text = " ".join(card.lines)
        assert "Live corner mapping: not available" in text
        msgs = " ".join(w.message for w in card.warnings)
        assert "Live mapping is blocked" in msgs
        assert card.status == hd.HomeDashboardStatus.BLOCKED

    def test_track_mismatch_against_event(self):
        ev = _event_ctx(track="Daytona")
        # Track Modelling selection (Fuji) differs from the event's track.
        tc = build_track_context(
            selected_location_id="fuji_speedway",
            selected_layout_id="fuji_speedway__gp",
            location_seed=SimpleNamespace(
                track_location_id="fuji_speedway",
                display_name="Fuji Speedway"),
            station_map_exists=True,
        )
        s = hd.build_home_dashboard_state(event_context=ev, track_context=tc)
        card = s.card(hd.CARD_TRACK)
        msgs = " ".join(w.message for w in card.warnings)
        assert "does not match the active event" in msgs

    def test_no_track_at_all_is_missing(self):
        s = hd.build_home_dashboard_state(track_context=empty_track_context())
        assert s.card(hd.CARD_TRACK).status == hd.HomeDashboardStatus.MISSING


# --------------------------------------------------------------------------- #
# 12./13. AI Input Safety
# --------------------------------------------------------------------------- #
class TestAISafetyCard:
    def test_clean_snapshot_is_ready(self):
        ev = _event_ctx()
        sc = _strategy_ctx(ev)
        snap = build_strategy_ai_snapshot(
            event_context=ev, strategy_context=sc,
            legacy_strategy={"track": "Fuji Speedway"})
        s = hd.build_home_dashboard_state(
            event_context=ev, strategy_context=sc, ai_snapshot=snap)
        card = s.card(hd.CARD_AI_SAFETY)
        assert card.status == hd.HomeDashboardStatus.READY
        assert "frozen snapshot" in " ".join(card.lines)

    def test_legacy_fallback_snapshot_warns(self):
        snap = build_strategy_ai_snapshot(
            legacy_strategy={"track": "Fuji Speedway", "total_laps": 20})
        s = hd.build_home_dashboard_state(ai_snapshot=snap)
        card = s.card(hd.CARD_AI_SAFETY)
        assert card.status == hd.HomeDashboardStatus.ATTENTION
        msgs = " ".join(w.message for w in card.warnings)
        assert "legacy fallback" in msgs

    def test_stale_snapshot_state_is_surfaced(self):
        old_event = _event_ctx()
        sc = _strategy_ctx(old_event)          # strategy keyed to old event
        new_event = _event_ctx(laps=30)
        snap = build_strategy_ai_snapshot(
            event_context=new_event, strategy_context=sc,
            legacy_strategy={"track": "Fuji Speedway"})
        s = hd.build_home_dashboard_state(
            event_context=new_event, strategy_context=sc, ai_snapshot=snap)
        card = s.card(hd.CARD_AI_SAFETY)
        assert card.status == hd.HomeDashboardStatus.ATTENTION
        assert any(w.kind == "stale" for w in card.warnings)

    def test_bare_core_object_accepted(self):
        ev = _event_ctx()
        snap = build_strategy_ai_snapshot(
            event_context=ev, legacy_strategy={"track": "Fuji Speedway"})
        s = hd.build_home_dashboard_state(event_context=ev,
                                          ai_snapshot=snap.core)
        assert s.card(hd.CARD_AI_SAFETY).status == hd.HomeDashboardStatus.READY

    def test_no_snapshot_is_missing(self):
        s = hd.build_home_dashboard_state()
        assert s.card(hd.CARD_AI_SAFETY).status == hd.HomeDashboardStatus.MISSING


# --------------------------------------------------------------------------- #
# 14. Next-best-action ordering
# --------------------------------------------------------------------------- #
class TestNextBestAction:
    def test_no_event_suggests_event(self):
        s = hd.build_home_dashboard_state()
        assert s.next_action.tab == "Event Planner"

    def test_event_without_laps_suggests_practice(self):
        ev = _event_ctx()
        s = hd.build_home_dashboard_state(event_context=ev)
        assert "practice" in s.next_action.action.lower()
        assert s.next_action.tab == "Live Race Engineer"

    def test_laps_without_setup_suggests_setup(self):
        ev = _event_ctx()
        s = hd.build_home_dashboard_state(
            event_context=ev, has_practice_laps=True, has_valid_laps=True)
        assert "setup" in s.next_action.action.lower()
        assert s.next_action.tab == "Setup Builder"

    def test_setup_without_strategy_suggests_strategy(self):
        ev = _event_ctx()
        setup = _setup_ctx(ev)
        s = hd.build_home_dashboard_state(
            event_context=ev, setup_context=setup,
            has_practice_laps=True, has_valid_laps=True)
        assert "strategy" in s.next_action.action.lower()
        assert s.next_action.tab == "Strategy Builder"

    def test_everything_ready_suggests_race(self):
        ev = _event_ctx()
        sc = _strategy_ctx(ev)
        setup = _setup_ctx(ev)
        s = hd.build_home_dashboard_state(
            event_context=ev, strategy_context=sc, setup_context=setup,
            has_practice_laps=True, has_valid_laps=True)
        assert "race" in s.next_action.action.lower()
        assert s.next_action.tab == "Live Race Engineer"

    def test_live_active_completes_flow(self):
        ev = _event_ctx()
        sc = _strategy_ctx(ev)
        setup = _setup_ctx(ev)
        s = hd.build_home_dashboard_state(
            event_context=ev, strategy_context=sc, setup_context=setup,
            has_practice_laps=True, has_valid_laps=True, live_active=True)
        assert s.next_action.complete is True
        assert s.next_action.tab == "History"

    def test_progress_counts_partition_gates(self):
        ev = _event_ctx()
        s = hd.build_home_dashboard_state(event_context=ev)
        na = s.next_action
        assert na.ready_count + na.pending_count == 8
        assert na.progress_text == f"{na.ready_count} of 8 steps done"

    def test_strategy_gate_needs_a_plan_not_just_config(self):
        # A strategy context without a stint plan must NOT satisfy the gate.
        ev = _event_ctx()
        sc = build_strategy_context(strategy={"config_id": "x",
                                              "fuel_burn_per_lap": 2.0},
                                    event_context=ev)
        s = hd.build_home_dashboard_state(
            event_context=ev, strategy_context=sc, setup_context=_setup_ctx(ev),
            has_practice_laps=True, has_valid_laps=True)
        assert "strategy" in s.next_action.action.lower()


# --------------------------------------------------------------------------- #
# 15. Display labels are user-friendly
# --------------------------------------------------------------------------- #
class TestFriendlyLabels:
    _FORBIDDEN = (
        "config_id", "change_hash", "snapshot_id", "event_change_hash",
        "SSOT", "resolver", "legacy_strategy", "LEGACY_STRATEGY",
        "EMPTY", "ctx", "fan-out", "station_map", "seed_audit",
        "TrackContext", "EventContext", "StrategyContext", "SetupContext",
    )

    def _full_state(self):
        ev = _event_ctx()
        sc = _strategy_ctx(ev)
        snap = build_strategy_prompt_snapshot(sc, ev)
        setup = _setup_ctx(ev, snap)
        tc = _track_ctx(ev)
        ai = build_strategy_ai_snapshot(
            event_context=ev, strategy_context=sc,
            legacy_strategy={"track": "Fuji Speedway"})
        return hd.build_home_dashboard_state(
            event_context=ev, strategy_context=sc, setup_context=setup,
            track_context=tc, ai_snapshot=ai,
            has_practice_laps=True, has_valid_laps=True)

    def test_no_jargon_in_any_display_string(self):
        s = self._full_state()
        blobs = []
        for c in s.cards:
            blobs.extend([c.title, c.headline, c.status_text])
            blobs.extend(c.lines)
            blobs.extend(w.message for w in c.warnings)
        blobs.extend([s.next_action.action, s.next_action.tab])
        for blob in blobs:
            for bad in self._FORBIDDEN:
                assert bad not in blob, f"jargon {bad!r} leaked into {blob!r}"

    def test_status_labels_are_words_not_enums(self):
        for st in hd.HomeDashboardStatus:
            label = hd.status_label(st)
            assert label and label[0].isupper()
            assert "_" not in label

    def test_setup_source_shown_in_plain_english(self):
        s = self._full_state()
        text = " ".join(s.card(hd.CARD_SETUP).lines)
        assert "AI recommendation" in text
        assert "saved_db" not in text and "legacy_config" not in text

    def test_stale_wording_matches_spec_examples(self):
        old_event = _event_ctx()
        setup = _setup_ctx(old_event)
        sc = _strategy_ctx(old_event)
        new_event = _event_ctx(laps=30)
        s = hd.build_home_dashboard_state(
            event_context=new_event, strategy_context=sc, setup_context=setup)
        msgs = [w.message for w in s.warnings]
        assert any("Setup was generated for an older event version" in m
                   for m in msgs)
        assert any("Strategy plan was built before the current event settings "
                   "changed" in m for m in msgs)


# --------------------------------------------------------------------------- #
# 16. Never raises on malformed / missing data
# --------------------------------------------------------------------------- #
class TestNeverRaises:
    GARBAGE = (None, "a string", 42, 3.14, [], [1, 2], {}, {"x": 1},
               object(), SimpleNamespace(), SimpleNamespace(source=object()),
               lambda: None)

    def test_garbage_in_every_slot(self):
        for g in self.GARBAGE:
            s = hd.build_home_dashboard_state(
                event_context=g, strategy_context=g, setup_context=g,
                track_context=g, ai_snapshot=g, strategy_snapshot=g)
            assert len(s.cards) == 5
            assert s.next_action.action

    def test_garbage_mixed_with_real_contexts(self):
        ev = _event_ctx()
        s = hd.build_home_dashboard_state(
            event_context=ev, strategy_context="garbage",
            setup_context=123, track_context=[1], ai_snapshot={})
        assert s.card(hd.CARD_RACE_SETUP).status == hd.HomeDashboardStatus.READY

    def test_raising_attribute_object_is_contained(self):
        class Evil:
            def __getattr__(self, name):
                raise RuntimeError("boom")
        s = hd.build_home_dashboard_state(
            event_context=Evil(), strategy_context=Evil(),
            setup_context=Evil(), track_context=Evil(), ai_snapshot=Evil())
        assert len(s.cards) == 5

    def test_flow_flags_never_raise(self):
        flags = hd.build_flow_flags(event_context="x", strategy_context=1,
                                    setup_context=[], track_context={})
        assert set(flags) >= {"has_event", "has_setup", "has_strategy"}

    def test_formatters_never_raise_and_escape_html(self):
        card = hd.HomeDashboardCard(
            key="k", title="<b>T</b>", status=hd.HomeDashboardStatus.READY,
            headline="<script>x</script>",
            lines=("<i>line</i>",),
            warnings=(hd.HomeDashboardWarning("k", "<u>w</u>"),),
        )
        html = hd.format_card_html(card)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        na = hd.HomeDashboardNextAction(
            action="<a>", tab="<t>", complete=False,
            ready_count=1, pending_count=2)
        html2 = hd.format_next_action_html(na)
        assert "<a>" not in html2


# --------------------------------------------------------------------------- #
# Source-scan: Home tab wiring is additive and display-only
# --------------------------------------------------------------------------- #
class TestHomeTabWiring:
    def test_home_tab_leads_before_track_modelling(self, dash_src):
        # Home Dashboard Promotion (2026-07-03): Home now LEADS the tab bar.
        home = dash_src.index('self._build_home_tab(),             "Home")             # 0')
        tm = dash_src.index('self._build_track_modelling_tab(), "Track Modelling")  # 13')
        assert home < tm, "Home tab must lead, before the other tabs"

    def test_tab_indices_after_home_promotion(self, dash_src):
        # The addTab lines after Home led the bar (every non-Home tab +1).
        for needle in (
            'self._build_home_tab(),             "Home")             # 0',
            '"Live Race Engineer") # 1',
            '"Event Planner")   # 2',
            '"Telemetry")        # 7',
            '"Diagnostics")      # 8',
            '"AI Log")           # 12',
            'self._build_track_modelling_tab(), "Track Modelling")  # 13',
        ):
            assert needle in dash_src, f"tab wiring changed: {needle}"

    def test_diagnostic_tabs_still_present(self, dash_src):
        for builder in ("_build_telemetry_tab", "_build_debug_tab",
                        "_build_ai_log_tab", "_build_track_modelling_tab"):
            assert f"self.{builder}()" in dash_src

    def test_on_tab_changed_handles_home(self, dash_src):
        # Tab Navigation Refactor (2026-07-03): dispatch is by stable tab key.
        body = _method_body(dash_src, "_on_tab_changed")
        assert "_home_refresh" in body and "TAB_HOME" in body
        # Existing dispatches untouched (key-based since the refactor).
        for frag in ("_refresh_history", "_sync_setup_builder_from_event",
                     "_sync_strategy_from_event", "_sync_practice_from_event",
                     "_refresh_telemetry_context", "_flush_ai_log_pending_select",
                     "_tm_on_tab_shown"):
            assert frag in body

    def test_home_reads_from_canonical_contexts(self, dash_src):
        body = _method_body(dash_src, "_build_home_dashboard_state")
        assert "_build_event_context" in body
        assert "_build_strategy_context" in body
        assert "_build_track_context" in body
        assert "_last_setup_context" in body
        assert "_build_strategy_ai_snapshot" in body
        assert "build_home_dashboard_state" in body

    def test_home_methods_do_not_write_state(self, dash_src):
        for name in ("_build_home_tab", "_build_home_dashboard_state",
                     "_home_has_practice_laps", "_home_refresh",
                     "_home_refresh_if_visible"):
            body = _method_body(dash_src, name)
            assert 'setdefault("strategy"' not in body, f"{name} writes strategy"
            assert re.search(r'config\[.strategy.\]\s*\[', body) is None, (
                f"{name} writes into config['strategy']")
            assert "_persist_config" not in body, f"{name} persists config"
            assert "upsert" not in body and "save_" not in body, (
                f"{name} writes to the DB or files")

    def test_home_tab_is_a_workflow_tab_in_product_flow(self):
        assert pf.TAB_ROLES.get("Home") == pf.ROLE_WORKFLOW
        assert pf.decorate_tab_title("Home") == "Home"
        # The diagnostic tool set is unchanged.
        assert set(pf.diagnostic_tabs()) == {
            "Telemetry", "Diagnostics", "AI Log", "Track Modelling",
        }

    def test_refresh_hooks_are_guarded_and_display_only(self, dash_src, sb_src, tm_src):
        # dashboard hooks
        assert "_home_refresh_if_visible" in _method_body(dash_src, "_on_event_set_active")
        assert "_home_refresh_if_visible" in _method_body(dash_src, "_update_race_config")
        # mixin hooks must be hasattr-guarded (the mixins can be used standalone)
        for src, method in ((sb_src, "_display_setup_result"),
                            (tm_src, "_tm_refresh_track_truth_panel")):
            body = _method_body(src, method)
            assert '_home_refresh_if_visible' in body
            assert 'hasattr(self, "_home_refresh_if_visible")' in body

    def test_no_polling_or_background_workers_added(self, dash_src):
        for name in ("_build_home_tab", "_home_refresh",
                     "_home_refresh_if_visible", "_build_home_dashboard_state"):
            body = _method_body(dash_src, name)
            assert "QTimer" not in body
            assert "QThread" not in body
            assert "Worker" not in body

    def test_vm_module_is_pure(self):
        src = (ROOT / "ui" / "home_dashboard_vm.py").read_text(encoding="utf-8")
        # No Qt / DB / network / AI imports, and no file I/O.
        for bad in ("PyQt6", "QtWidgets", "sqlite3", "requests", "urllib",
                    "anthropic", "session_db"):
            assert re.search(rf"^\s*(import {bad}|from {bad})", src, re.M) is None, (
                f"home_dashboard_vm must not import {bad}")
        assert "open(" not in src, "home_dashboard_vm must not do file I/O"
