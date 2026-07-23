"""Who owns the setup values (single-system stage 2).

Until now the answer was "a QDoubleSpinBox on the classic form", which is the reason the
old UI cannot be deleted. This store is the file that replaces it.
"""

import json
import os

from strategy.setup_sheet import sheet_from_dict
from services.setup_store import (
    SetupSheetStore, default_store_path, scope_key,
)


def _path(tmp_path):
    return str(tmp_path / "setup_sheets.json")


class TestScopeKey:
    def test_car_track_and_layout_all_matter(self):
        a = scope_key("Porsche Cayman GT4", "Watkins Glen", "long")
        assert a != scope_key("Porsche Cayman GT4", "Watkins Glen", "short")
        assert a != scope_key("Mazda MX-5", "Watkins Glen", "long")

    def test_case_and_whitespace_do_not_create_a_second_scope(self):
        assert scope_key(" Porsche Cayman GT4 ", "Watkins Glen", "Long") == \
               scope_key("porsche cayman gt4", "watkins glen", "long")


class TestEmptyState:
    def test_a_missing_file_reads_as_empty_defaults(self, tmp_path):
        store = SetupSheetStore(_path(tmp_path))
        sheet = store.get(scope_key("c", "t", "l"), "race")
        assert sheet.is_authored is False
        assert store.scopes() == ()

    def test_an_unknown_scope_is_empty_not_an_error(self, tmp_path):
        store = SetupSheetStore(_path(tmp_path))
        assert store.has_setup("nope", "race") is False

    def test_a_corrupt_file_degrades_to_empty_rather_than_crashing(self, tmp_path):
        p = _path(tmp_path)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{not json at all")
        store = SetupSheetStore(p).load()
        assert store.scopes() == ()
        assert store.get("any", "race").is_authored is False

    def test_a_file_with_the_wrong_shape_is_ignored(self, tmp_path):
        p = _path(tmp_path)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"scopes": "not a mapping"}, fh)
        assert SetupSheetStore(p).load().scopes() == ()


class TestRoundTrip:
    def test_a_sheet_survives_a_restart(self, tmp_path):
        p, scope = _path(tmp_path), scope_key("c", "t", "l")
        SetupSheetStore(p).set(scope, "race", {"arb_front": 7, "springs_front": 3.2})
        again = SetupSheetStore(p).load()
        sheet = again.get(scope, "race")
        assert sheet.get("arb_front") == 7.0
        assert sheet.get("springs_front") == 3.2
        assert again.has_setup(scope, "race") is True

    def test_the_two_disciplines_are_stored_separately(self, tmp_path):
        p, scope = _path(tmp_path), scope_key("c", "t", "l")
        store = SetupSheetStore(p)
        store.set(scope, "race", {"arb_front": 7})
        store.set(scope, "qualifying", {"arb_front": 3})
        assert store.get(scope, "race").get("arb_front") == 7.0
        assert store.get(scope, "qualifying").get("arb_front") == 3.0

    def test_scopes_never_leak_into_each_other(self, tmp_path):
        p = _path(tmp_path)
        store = SetupSheetStore(p)
        store.set(scope_key("car a", "t", "l"), "race", {"arb_front": 7})
        assert store.get(scope_key("car b", "t", "l"), "race").is_authored is False

    def test_a_setup_sheet_object_is_accepted_as_well_as_a_dict(self, tmp_path):
        p, scope = _path(tmp_path), scope_key("c", "t", "l")
        store = SetupSheetStore(p)
        store.set(scope, "race", sheet_from_dict({"arb_front": 9}))
        assert store.get(scope, "race").get("arb_front") == 9.0

    def test_unknown_disciplines_fall_back_to_race(self, tmp_path):
        p, scope = _path(tmp_path), scope_key("c", "t", "l")
        store = SetupSheetStore(p)
        store.set(scope, "base", {"arb_front": 5})
        assert store.get(scope, "race").get("arb_front") == 5.0


class TestMerge:
    def test_merging_changes_only_the_named_fields(self, tmp_path):
        p, scope = _path(tmp_path), scope_key("c", "t", "l")
        store = SetupSheetStore(p)
        store.set(scope, "race", {"arb_front": 7, "arb_rear": 6})
        store.merge(scope, "race", {"arb_front": 4})
        sheet = store.get(scope, "race")
        assert sheet.get("arb_front") == 4.0
        assert sheet.get("arb_rear") == 6.0

    def test_merging_persists(self, tmp_path):
        p, scope = _path(tmp_path), scope_key("c", "t", "l")
        SetupSheetStore(p).set(scope, "race", {"arb_front": 7})
        SetupSheetStore(p).load().merge(scope, "race", {"arb_front": 4})
        assert SetupSheetStore(p).load().get(scope, "race").get("arb_front") == 4.0


class TestBothSheetsWrittenTogether:
    def test_set_many_persists_once(self, tmp_path):
        """The initial-setup build authors BOTH sheets; saving twice would leave a
        window where the file mixes this build's Race sheet with the last build's
        Qualifying sheet."""
        p, scope = _path(tmp_path), scope_key("c", "t", "l")
        store = SetupSheetStore(p)
        writes = []
        real_save = store.save
        store.save = lambda: writes.append(True) or real_save()
        store.set_many(scope, {"race": {"arb_front": 7}, "qualifying": {"arb_front": 3}})
        assert len(writes) == 1
        reloaded = SetupSheetStore(p).load()
        assert reloaded.get(scope, "race").get("arb_front") == 7.0
        assert reloaded.get(scope, "qualifying").get("arb_front") == 3.0


class TestClear:
    def test_clearing_one_scope_leaves_the_others(self, tmp_path):
        p = _path(tmp_path)
        store = SetupSheetStore(p)
        a, b = scope_key("a", "t", "l"), scope_key("b", "t", "l")
        store.set(a, "race", {"arb_front": 7})
        store.set(b, "race", {"arb_front": 8})
        store.clear(a)
        assert store.get(a, "race").is_authored is False
        assert store.get(b, "race").get("arb_front") == 8.0

    def test_clearing_everything(self, tmp_path):
        p = _path(tmp_path)
        store = SetupSheetStore(p)
        store.set(scope_key("a", "t", "l"), "race", {"arb_front": 7})
        store.clear()
        assert store.scopes() == ()


class TestNoPath:
    def test_a_store_with_no_path_still_works_in_memory(self):
        store = SetupSheetStore("")
        scope = scope_key("c", "t", "l")
        store.set(scope, "race", {"arb_front": 7})
        assert store.get(scope, "race").get("arb_front") == 7.0
        assert store.save() is False


class TestPathHelper:
    def test_the_sheets_live_beside_the_config(self, tmp_path):
        cfg = str(tmp_path / "config.json")
        assert default_store_path(cfg) == os.path.join(str(tmp_path), "setup_sheets.json")

    def test_no_config_path_means_no_file(self):
        assert default_store_path("") == ""
