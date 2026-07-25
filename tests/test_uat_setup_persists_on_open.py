"""UAT — the last-applied Race and Qualifying setups load on open, not "standard".

On open the Garage showed a defaults-only ("standard") sheet even when the driver had
applied and recorded a setup for this car/track before. The bridge now seeds the working
sheets from the applied-revision history once per scope. These tests exercise that seed
(``LiveShellBridge._seed_from_last_applied``) against real stores, without Qt.
"""
from __future__ import annotations

from types import SimpleNamespace

from services.setup_service import SetupService, SetupInputs
from services.setup_store import SetupSheetStore
from services.setup_history_store import SetupHistoryStore
from strategy.setup_sheet import sheet_from_dict, empty_sheet
from ui.live_shell_bridge import LiveShellBridge


def _service(tmp_path):
    store = SetupSheetStore(str(tmp_path / "sheets.json"))
    history = SetupHistoryStore(str(tmp_path / "revs.json"))
    inputs = SetupInputs(car="Porsche Cayman GT4", track="Watkins Glen International",
                         layout="long_course")
    svc = SetupService(store=store, inputs_provider=lambda: inputs, history=history)
    return svc, store, history, inputs


def _fake_bridge(svc, store):
    return SimpleNamespace(_setups=svc, _sheets=store, _seeded_history=set())


def test_last_applied_race_and_quali_are_loaded_on_open(tmp_path):
    svc, store, history, inputs = _service(tmp_path)
    # A previous session recorded applied revisions for both disciplines.
    history.record(inputs.scope, "race", revision=3, label="Race · rev 3",
                   fields={"setup_label": "Race", "ride_height_front": 55})
    history.record(inputs.scope, "qualifying", revision=2, label="Quali · rev 2",
                   fields={"setup_label": "Quali", "ride_height_front": 48})
    # On open the working sheets are empty ("standard").
    assert not store.has_setup(inputs.scope, "race")
    assert not store.has_setup(inputs.scope, "qualifying")

    LiveShellBridge._seed_from_last_applied(_fake_bridge(svc, store))

    # Both sheets now carry the last-applied tune, not the default.
    assert store.has_setup(inputs.scope, "race")
    assert store.has_setup(inputs.scope, "qualifying")
    assert store.get(inputs.scope, "race").as_dict()["ride_height_front"] == 55
    assert store.get(inputs.scope, "qualifying").as_dict()["ride_height_front"] == 48


def test_the_newest_revision_is_the_one_loaded(tmp_path):
    svc, store, history, inputs = _service(tmp_path)
    history.record(inputs.scope, "race", revision=1, label="old",
                   fields={"setup_label": "old", "ride_height_front": 70})
    history.record(inputs.scope, "race", revision=4, label="newest",
                   fields={"setup_label": "newest", "ride_height_front": 52})
    LiveShellBridge._seed_from_last_applied(_fake_bridge(svc, store))
    assert store.get(inputs.scope, "race").as_dict()["ride_height_front"] == 52


def test_seed_never_overwrites_an_existing_working_sheet(tmp_path):
    svc, store, history, inputs = _service(tmp_path)
    history.record(inputs.scope, "race", revision=3, label="applied",
                   fields={"setup_label": "applied", "ride_height_front": 55})
    # The driver already has a sheet in progress — history must not clobber it.
    store.set(inputs.scope, "race",
              sheet_from_dict({"setup_label": "current", "ride_height_front": 70}))
    LiveShellBridge._seed_from_last_applied(_fake_bridge(svc, store))
    assert store.get(inputs.scope, "race").as_dict()["ride_height_front"] == 70


def test_no_history_leaves_the_sheet_untouched(tmp_path):
    svc, store, _history, inputs = _service(tmp_path)
    LiveShellBridge._seed_from_last_applied(_fake_bridge(svc, store))
    assert not store.has_setup(inputs.scope, "race")


def test_seed_runs_once_per_scope(tmp_path):
    svc, store, history, inputs = _service(tmp_path)
    history.record(inputs.scope, "race", revision=1, label="r1",
                   fields={"setup_label": "r1", "ride_height_front": 55})
    fake = _fake_bridge(svc, store)
    LiveShellBridge._seed_from_last_applied(fake)
    assert store.has_setup(inputs.scope, "race")
    # The driver deliberately clears the sheet; a later refresh must NOT re-seed it,
    # because the scope was already seeded this session (matches _seed_sheets).
    store.set(inputs.scope, "race", empty_sheet())
    LiveShellBridge._seed_from_last_applied(fake)
    assert not store.has_setup(inputs.scope, "race")
