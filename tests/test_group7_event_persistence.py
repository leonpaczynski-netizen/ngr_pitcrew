"""Tests for Remediation Group 7: Event Persistence (DEF-P1-009).

Root cause: _evt_tyre_wear, _evt_fuel_mult, _evt_refuel_rate are QSpinBox (int-only
widgets), but the DB schema stores tyre_wear, fuel_mult, refuel_rate_lps as REAL
columns. SQLite returns REAL as Python float; PyQt6's QSpinBox.setValue() rejects
floats with TypeError. The broad except-Exception-pass in _on_event_selected()
silently caught this, leaving those spinboxes at their default value (1) and
preventing all subsequent field population (avail_tyres, req_tyres, tuning cats,
notes) from running.

Fix applied in _on_event_selected():
  - int(round(...)) wraps every REAL->QSpinBox assignment
  - except clause now prints the traceback instead of silently swallowing it
  - Tuning-perms group visibility uses _tun_on only (not _bop_on and _tun_on)
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# DB round-trip tests
# ---------------------------------------------------------------------------

class TestEventDBRoundTrip(unittest.TestCase):

    def setUp(self):
        from data.session_db import SessionDB
        self.db = SessionDB(":memory:")

    def tearDown(self):
        self.db.close()

    def test_db_returns_float_for_tyre_wear(self):
        """tyre_wear DB column is REAL — documents why int cast is required."""
        self.db.upsert_event({"name": "TW", "tyre_wear": 3})
        evt = self.db.get_all_events()[0]
        self.assertIsInstance(evt["tyre_wear"], float,
                              "DB REAL column must return float; callers must cast for QSpinBox")
        self.assertEqual(evt["tyre_wear"], 3.0)

    def test_db_returns_float_for_fuel_mult(self):
        """fuel_mult DB column is REAL — documents why int cast is required."""
        self.db.upsert_event({"name": "FM", "fuel_mult": 4})
        evt = self.db.get_all_events()[0]
        self.assertIsInstance(evt["fuel_mult"], float,
                              "DB REAL column must return float; callers must cast for QSpinBox")
        self.assertEqual(evt["fuel_mult"], 4.0)

    def test_upsert_event_saves_non_default_tyre_wear(self):
        """DEF-P1-009 req 1: tyre_wear=2 round-trips through DB correctly."""
        self.db.upsert_event({"name": "Evt1", "tyre_wear": 2})
        evt = self.db.get_all_events()[0]
        self.assertEqual(evt["tyre_wear"], 2.0,
                         "tyre_wear 2 must survive upsert + get_all_events round-trip")

    def test_upsert_event_tyre_wear_update(self):
        """Second upsert with new tyre_wear overwrites the stored value."""
        self.db.upsert_event({"name": "Evt1", "tyre_wear": 1})
        self.db.upsert_event({"name": "Evt1", "tyre_wear": 5})
        evt = self.db.get_all_events()[0]
        self.assertEqual(evt["tyre_wear"], 5.0,
                         "upsert_event UPDATE path must overwrite tyre_wear")

    def test_upsert_event_saves_non_default_fuel_mult(self):
        """DEF-P1-009 req 2: fuel_mult=3 round-trips through DB correctly."""
        self.db.upsert_event({"name": "Evt2", "fuel_mult": 3})
        evt = self.db.get_all_events()[0]
        self.assertEqual(evt["fuel_mult"], 3.0,
                         "fuel_mult 3 must survive upsert + get_all_events round-trip")

    def test_upsert_event_saves_avail_tyres(self):
        """DEF-P1-009 req 3: avail_tyres list round-trips through JSON storage."""
        codes = ["RM", "RH", "RS"]
        self.db.upsert_event({"name": "Evt3", "avail_tyres": codes})
        evt = self.db.get_all_events()[0]
        self.assertIsInstance(evt["avail_tyres"], list,
                              "avail_tyres must be returned as a Python list")
        self.assertEqual(sorted(evt["avail_tyres"]), sorted(codes))

    def test_upsert_event_avail_tyres_empty_list(self):
        """Empty avail_tyres round-trips as an empty list, not null."""
        self.db.upsert_event({"name": "Evt3e", "avail_tyres": []})
        evt = self.db.get_all_events()[0]
        self.assertEqual(evt["avail_tyres"], [])

    def test_upsert_event_saves_req_tyres(self):
        """DEF-P1-009 req 4: req_tyres list round-trips through JSON storage."""
        self.db.upsert_event({"name": "Evt4", "req_tyres": ["RM"]})
        evt = self.db.get_all_events()[0]
        self.assertEqual(evt["req_tyres"], ["RM"],
                         "req_tyres must survive JSON serialisation round-trip")

    def test_upsert_event_req_tyres_multiple(self):
        """Multiple required tyres survive the round-trip."""
        self.db.upsert_event({"name": "Evt4m", "req_tyres": ["RM", "RH"]})
        evt = self.db.get_all_events()[0]
        self.assertEqual(sorted(evt["req_tyres"]), ["RH", "RM"])

    def test_upsert_event_saves_bop_true(self):
        """DEF-P1-009 req 5a: bop=True stored as truthy."""
        self.db.upsert_event({"name": "Bop1", "bop": True})
        evt = self.db.get_all_events()[0]
        self.assertTrue(bool(evt["bop"]),
                        "bop=True must be stored and returned as truthy")

    def test_upsert_event_saves_bop_false(self):
        """bop=False stored as falsy."""
        self.db.upsert_event({"name": "Bop0", "bop": False})
        evt = self.db.get_all_events()[0]
        self.assertFalse(bool(evt["bop"]))

    def test_upsert_event_saves_tuning_false(self):
        """DEF-P1-009 req 5b: tuning=False persists."""
        self.db.upsert_event({"name": "Tun0", "tuning": False})
        evt = self.db.get_all_events()[0]
        self.assertFalse(bool(evt["tuning"]))

    def test_upsert_event_saves_tuning_true(self):
        """tuning=True persists."""
        self.db.upsert_event({"name": "Tun1", "tuning": True})
        evt = self.db.get_all_events()[0]
        self.assertTrue(bool(evt["tuning"]))

    def test_upsert_event_saves_allowed_tuning_categories(self):
        """allowed_tuning_categories serialised via JSON and returned correctly."""
        cats = ["suspension", "brake_balance", "aero"]
        self.db.upsert_event({"name": "Cats", "allowed_tuning_categories": cats})
        evt = self.db.get_all_events()[0]
        self.assertIn("allowed_tuning_categories", evt,
                      "get_all_events must return allowed_tuning_categories key")
        self.assertEqual(sorted(evt["allowed_tuning_categories"]), sorted(cats))

    def test_allowed_tuning_categories_empty_default(self):
        """Event with no allowed_tuning_categories returns empty list."""
        self.db.upsert_event({"name": "NoCats"})
        evt = self.db.get_all_events()[0]
        self.assertEqual(evt.get("allowed_tuning_categories", "MISSING"), [],
                         "allowed_tuning_categories default must be empty list")

    def test_complete_event_round_trip_all_fields(self):
        """Full round-trip: all Group 7 required fields saved and loaded correctly."""
        saved = {
            "name":                      "Suzuka 25L",
            "track":                     "Suzuka Circuit",
            "race_type":                 "Lap Race",
            "laps":                      25,
            "duration_mins":             60,
            "tyre_wear":                 3,
            "fuel_mult":                 2,
            "refuel_rate_lps":           10.0,
            "mandatory_stops":           1,
            "bop":                       True,
            "tuning":                    False,
            "weather":                   "Fixed Dry",
            "damage":                    "Light",
            "avail_tyres":               ["RM", "RH"],
            "req_tyres":                 ["RH"],
            "allowed_tuning_categories": ["brake_balance"],
            "notes":                     "Test event",
        }
        self.db.upsert_event(saved)
        evts = self.db.get_all_events()
        self.assertEqual(len(evts), 1)
        e = evts[0]
        self.assertEqual(e["tyre_wear"], 3.0)
        self.assertEqual(e["fuel_mult"], 2.0)
        self.assertTrue(bool(e["bop"]))
        self.assertFalse(bool(e["tuning"]))
        self.assertEqual(sorted(e["avail_tyres"]), ["RH", "RM"])
        self.assertEqual(e["req_tyres"], ["RH"])
        self.assertEqual(e["allowed_tuning_categories"], ["brake_balance"])
        self.assertEqual(e["notes"], "Test event")

    def test_get_event_matches_get_all_events(self):
        """get_event() by name returns the same field values as get_all_events()[0]."""
        self.db.upsert_event({
            "name": "Nurburgring",
            "tyre_wear": 2,
            "fuel_mult": 3,
            "avail_tyres": ["RM"],
            "req_tyres": [],
            "bop": False,
            "tuning": True,
        })
        by_name = self.db.get_event("Nurburgring")
        by_list = self.db.get_all_events()[0]
        self.assertIsNotNone(by_name)
        self.assertEqual(by_name["tyre_wear"], by_list["tyre_wear"])
        self.assertEqual(by_name["fuel_mult"], by_list["fuel_mult"])
        self.assertEqual(by_name["avail_tyres"], by_list["avail_tyres"])
        self.assertEqual(by_name["allowed_tuning_categories"],
                         by_list["allowed_tuning_categories"])


# ---------------------------------------------------------------------------
# Source-scan tests — _on_event_selected fix applied
# ---------------------------------------------------------------------------

class TestEventSelectedFixApplied(unittest.TestCase):

    def _body(self, method: str) -> str:
        return _method_body(_dashboard_text(), method)

    def test_tyre_wear_cast_to_int(self):
        """DEF-P1-009: tyre_wear must be wrapped in int(round(...)) before setValue."""
        body = self._body("_on_event_selected")
        self.assertIn('int(round(evt.get("tyre_wear"', body,
                      '_on_event_selected must cast tyre_wear to int(round(...))')

    def test_fuel_mult_cast_to_int(self):
        """DEF-P1-009: fuel_mult must be wrapped in int(round(...)) before setValue."""
        body = self._body("_on_event_selected")
        self.assertIn('int(round(evt.get("fuel_mult"', body,
                      '_on_event_selected must cast fuel_mult to int(round(...))')

    def test_refuel_rate_cast_to_int(self):
        """refuel_rate_lps must be wrapped in int(round(...)) before setValue."""
        body = self._body("_on_event_selected")
        self.assertIn('int(round(evt.get("refuel_rate_lps"', body,
                      '_on_event_selected must cast refuel_rate_lps to int(round(...))')

    def test_exception_not_silently_swallowed(self):
        """except Exception must print traceback, not silently pass."""
        body = self._body("_on_event_selected")
        self.assertNotIn("except Exception:\n            pass", body,
                         "Silent exception pass must be removed from _on_event_selected")
        self.assertIn("traceback", body,
                      "_on_event_selected exception handler must call traceback.print_exc()")

    def test_tuning_perms_uses_tun_only_not_bop_and_tun(self):
        """Tuning perms group must show when tuning=True regardless of BoP state."""
        body = self._body("_on_event_selected")
        self.assertNotIn("_bop_on and _tun_on", body,
                         "_on_event_selected must not gate tuning perms on BoP")
        self.assertIn("bool(_tun_on)", body,
                      "_on_event_selected must use bool(_tun_on) for group visibility")

    def test_avail_tyre_checks_populated_after_tyre_wear(self):
        """avail_tyres checkboxes are set in the same try block after the int-cast fix."""
        body = self._body("_on_event_selected")
        tw_pos = body.find('int(round(evt.get("tyre_wear"')
        at_pos = body.find("_avail_tyre_checks")
        self.assertGreater(tw_pos, -1, "int(round(evt.get('tyre_wear'...)) must be present")
        self.assertGreater(at_pos, tw_pos,
                           "_avail_tyre_checks must appear after tyre_wear setValue")

    def test_req_tyre_checks_populated(self):
        """req_tyres checkboxes are populated in _on_event_selected."""
        body = self._body("_on_event_selected")
        self.assertIn("_req_tyre_checks", body)
        self.assertIn('evt.get("req_tyres"', body)


# ---------------------------------------------------------------------------
# Source-scan tests — _on_event_set_active writes correct strategy keys
# ---------------------------------------------------------------------------

class TestEventSetActiveStratKeys(unittest.TestCase):
    # Legacy Fan-Out Removal Phase 4 (2026-07-03): the strat-write block moved
    # verbatim from _on_event_set_active into _fanout_event_to_strategy (so the
    # save path can re-sync it). Same invariants, new home; Set-as-Active must
    # still invoke the helper after _on_event_save().

    def _body(self) -> str:
        return _method_body(_dashboard_text(), "_fanout_event_to_strategy")

    def test_writes_tyre_wear_multiplier(self):
        self.assertIn('strat["tyre_wear_multiplier"]', self._body())

    def test_writes_fuel_mult(self):
        self.assertIn('strat["fuel_mult"]', self._body())

    def test_writes_bop(self):
        self.assertIn('strat["bop"]', self._body())

    def test_writes_tuning(self):
        self.assertIn('strat["tuning"]', self._body())

    def test_writes_allowed_tuning_categories(self):
        self.assertIn('strat["allowed_tuning_categories"]', self._body())

    def test_writes_required_tyres(self):
        self.assertIn('strat["required_tyres"]', self._body())

    def test_on_event_save_called_before_strat_writes(self):
        """_on_event_save() must flush form to DB before the fan-out reads the
        form values into strat (via _fanout_event_to_strategy)."""
        body = _method_body(_dashboard_text(), "_on_event_set_active")
        save_pos = body.find("_on_event_save()")
        fanout_pos = body.find("self._fanout_event_to_strategy(evt_name)")
        self.assertGreater(save_pos, -1, "_on_event_set_active must call _on_event_save()")
        self.assertGreater(fanout_pos, save_pos,
                           "_on_event_save() must precede the fan-out write")


# ---------------------------------------------------------------------------
# DEF-P1-005 auto-resolution: practice analysis passes BoP context to AI
# ---------------------------------------------------------------------------

class TestPracticeAnalysisBoPContext(unittest.TestCase):

    def _body(self) -> str:
        return _method_body(_dashboard_text(), "_run_practice_analysis")

    # AI Snapshot Migration: the derivations moved into
    # build_practice_analysis_snapshot (data/ai_context_snapshot.py); the
    # method now routes race_params through the frozen snapshot. Same
    # DEF-P1-005 invariants, verified at the new home.

    def test_passes_tuning_locked_to_race_params(self):
        """tuning_locked derived from strategy config and forwarded to AI planner."""
        body = self._body()
        self.assertIn("_build_practice_ai_snapshot", body,
                      '_run_practice_analysis must build race_params via the frozen snapshot')
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        rp = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T", "tuning": False},
            fuel_burn_override=2.5).race_params_dict()
        self.assertTrue(rp["tuning_locked"],
                        'tuning_locked must be derived from config["strategy"]["tuning"]')

    def test_passes_allowed_tuning_to_race_params(self):
        """allowed_tuning derived from strategy config and forwarded to AI planner."""
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        rp = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T", "allowed_tuning_categories": ["brake_balance"]},
            fuel_burn_override=2.5).race_params_dict()
        self.assertEqual(rp["allowed_tuning"], ["brake_balance"],
                         'allowed_tuning must reference allowed_tuning_categories')


if __name__ == "__main__":
    unittest.main()
