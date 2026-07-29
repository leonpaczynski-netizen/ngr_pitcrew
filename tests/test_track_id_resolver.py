"""The layout_id fix: resolve a track name to canonical ids, write them on event
activation, and keep existing setup sheets findable when the id corrects.

Root bug this guards against: the canonical track_location_id / layout_id were only
ever written by the Track Modelling tab, so activating a different event left them
frozen (every setup was built + saved with a stale layout_id — Watkins Glen for a
Monza event). That mis-directed track shaping AND blocked personal-history recall.
"""
from __future__ import annotations

from data.track_intelligence import resolve_ids_for_track_name
from services.event_setup import EventSetupService, EventDraft
from services.setup_store import SetupSheetStore, scope_key
from strategy.setup_sheet import sheet_from_dict


class _DB:
    def __init__(self):
        self.events, self.cycles, self.next_id = [], {}, 7

    def get_event_id(self, name):
        return 7

    def upsert_event(self, row):
        row = dict(row); row["id"] = self.next_id; self.events.append(row); return self.next_id

    def get_preparation_cycle(self, cycle_id):
        return dict(self.cycles[cycle_id]) if cycle_id in self.cycles else None

    def upsert_preparation_cycle(self, cycle):
        self.cycles[cycle["cycle_id"]] = dict(cycle); return cycle["cycle_id"]


# ---------------------------------------------------------------------------
# resolve_ids_for_track_name
# ---------------------------------------------------------------------------

class TestResolver:
    def test_exact_and_layout_default(self):
        assert resolve_ids_for_track_name("Autodromo Nazionale Monza") == (
            "autodromo_nazionale_monza", "autodromo_nazionale_monza__full_course")

    def test_name_embedding_a_layout_and_endash(self):
        # en-dash + "Grand Prix" → the location's primary (long course) layout.
        assert resolve_ids_for_track_name("Watkins Glen International – Grand Prix") == (
            "watkins_glen_international", "watkins_glen_international__long_course")

    def test_short_app_name_resolves_via_tokens(self):
        # The app says "Fuji Speedway"; the seed says "Fuji International Speedway".
        assert resolve_ids_for_track_name("Fuji Speedway") == (
            "fuji_international_speedway", "fuji_international_speedway__full_course")

    def test_layout_letter_is_disambiguated(self):
        # "Circuit B" must resolve the seed's "Layout B", not the first layout.
        assert resolve_ids_for_track_name("Sainte-Croix – Circuit B") == (
            "circuit_de_sainte_croix", "circuit_de_sainte_croix__layout_b")
        assert resolve_ids_for_track_name("Sainte-Croix – Circuit A")[1] == (
            "circuit_de_sainte_croix__layout_a")

    def test_no_false_match_between_different_circuits(self):
        # Sainte-Croix must never resolve to Spa (both start "Circuit de …").
        loc, _ = resolve_ids_for_track_name("Circuit de Sainte-Croix")
        assert loc == "circuit_de_sainte_croix"

    def test_unknown_returns_empty(self):
        assert resolve_ids_for_track_name("Totally Made Up Track") == ("", "")
        assert resolve_ids_for_track_name("") == ("", "")


# ---------------------------------------------------------------------------
# Fan-out writes the ids on activation
# ---------------------------------------------------------------------------

class TestFanoutWritesIds:
    def _activate(self, track):
        cfg: dict = {}
        svc = EventSetupService(db=_DB(), config=cfg, persist=None)
        draft = EventDraft(name="Rd8", car="Porsche 911 RSR '17",
                           track=track, race_type="lap", laps=10)
        assert svc.save_and_activate(draft).ok
        return cfg["strategy"]

    def test_activation_rewrites_the_real_layout_id(self):
        strat = self._activate("Autodromo Nazionale Monza")
        assert strat["track_location_id"] == "autodromo_nazionale_monza"
        assert strat["layout_id"] == "autodromo_nazionale_monza__full_course"

    def test_switching_events_never_keeps_the_previous_track_id(self):
        # Activate Monza, then Watkins on the SAME config — the Monza id must not linger.
        cfg: dict = {}
        svc = EventSetupService(db=_DB(), config=cfg, persist=None)
        svc.save_and_activate(EventDraft(name="A", car="Porsche 911 RSR '17",
                                         track="Autodromo Nazionale Monza",
                                         race_type="lap", laps=10))
        svc.save_and_activate(EventDraft(name="B", car="Porsche 911 RSR '17",
                                         track="Fuji Speedway", race_type="lap", laps=10))
        assert cfg["strategy"]["layout_id"] == "fuji_international_speedway__full_course"


# ---------------------------------------------------------------------------
# Setup-sheet continuity when the layout id corrects
# ---------------------------------------------------------------------------

class TestSheetContinuityFallback:
    def test_sheet_saved_under_stale_layout_is_still_found(self):
        store = SetupSheetStore(path=None)
        # A sheet stored under the OLD (stale) layout id.
        stale = scope_key("Porsche 911 RSR '17", "Autodromo Nazionale Monza",
                          "watkins_glen_international__long_course")
        store.set(stale, "race", sheet_from_dict({"aero_front": 409}), persist=False)
        # Looked up under the CORRECTED layout id → still found via the car|track prefix.
        fixed = scope_key("Porsche 911 RSR '17", "Autodromo Nazionale Monza",
                          "autodromo_nazionale_monza__full_course")
        assert store.get(fixed, "race").as_dict().get("aero_front") == 409

    def test_fallback_never_crosses_a_different_track(self):
        store = SetupSheetStore(path=None)
        store.set(scope_key("RSR", "Monza", "lay_x"), "race",
                  sheet_from_dict({"aero_front": 1}), persist=False)
        # A different track with no stored sheet must NOT borrow Monza's.
        assert store.get(scope_key("RSR", "Spa", "lay_y"), "race").as_dict().get("aero_front") in (None, 0)
