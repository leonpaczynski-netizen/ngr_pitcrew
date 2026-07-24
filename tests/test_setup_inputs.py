"""Gathering the setup generators' inputs without a window (stage 2b groundwork).

Replaces ``_build_setup_inputs``, ``_load_car_specs_for_current`` and
``_build_track_tune_profile_for_current`` on SetupBuilderMixin. Everything except two
combo-box reads was already headless — it just lived on the mixin, so reaching it meant
reaching through MainWindow.
"""

from services.setup_inputs import build_setup_inputs
from services.setup_service import SetupInputs


class _DB:
    def __init__(self, event=None, setups=None, feedback=None, car_id=3):
        self._event = event
        self._setups = setups or []
        self._feedback = feedback or []
        self._car_id = car_id

    def get_event(self, name):
        return dict(self._event) if self._event and self._event.get("name") == name else None

    def get_setups_for_car_track(self, car, track):
        return list(self._setups)

    def get_car_id(self, car):
        return self._car_id

    def get_recent_feedback(self, car_id, track, limit=100):
        return list(self._feedback)


def _config(**strategy):
    base = {"car": "Porsche Cayman GT4", "track": "Watkins Glen International"}
    base.update(strategy)
    return {"strategy": base}


class TestIdentity:
    def test_car_and_track_come_from_the_config_when_there_is_no_event(self):
        inp = build_setup_inputs(None, _config())
        assert inp.car == "Porsche Cayman GT4"
        assert inp.track == "Watkins Glen International"
        assert inp.is_known is True

    def test_nothing_configured_stays_unknown_rather_than_guessing(self):
        inp = build_setup_inputs(None, {})
        assert inp.is_known is False
        assert inp.car == "" and inp.track == ""

    def test_the_scope_keys_the_working_sheet(self):
        inp = build_setup_inputs(None, _config())
        assert "porsche cayman gt4" in inp.scope
        assert "watkins glen international" in inp.scope

    def test_an_active_event_is_read_from_the_database(self):
        db = _DB(event={"name": "GR Enduro Rd2", "track": "Fuji Speedway",
                        "race_type": "timed", "duration_mins": 120})
        cfg = _config()
        cfg["active_event_id"] = "GR Enduro Rd2"
        inp = build_setup_inputs(db, cfg)
        assert inp.track == "Fuji Speedway"          # the event wins over the config
        assert inp.duration_mins == 120


class TestRegulations:
    def test_a_tuning_locked_event_is_reported(self):
        db = _DB(event={"name": "E", "track": "T", "tuning": 0})
        cfg = _config()
        cfg["active_event_id"] = "E"
        assert build_setup_inputs(db, cfg).tuning_locked is True

    def test_wear_and_fuel_multipliers_are_carried(self):
        db = _DB(event={"name": "E", "track": "T", "tyre_wear": 4.0, "fuel_mult": 2.0})
        cfg = _config()
        cfg["active_event_id"] = "E"
        inp = build_setup_inputs(db, cfg)
        assert inp.tyre_wear_multiplier == 4.0
        assert inp.fuel_multiplier == 2.0


class TestHistoricalSetups:
    def test_no_database_means_no_history_rather_than_an_error(self):
        assert build_setup_inputs(None, _config()).historical_setups == ()

    def test_saved_setups_are_annotated_with_the_drivers_rating(self):
        """Only PROVEN setups should influence a new one, and the rating is what makes
        a setup proven — so an unrated one is carried WITHOUT a rating, not assumed good."""
        db = _DB(setups=[{"setup_id": "s1"}, {"setup_id": "s2"}],
                 feedback=[{"setup_id": "s1", "rating": "liked"}])
        got = build_setup_inputs(db, _config()).historical_setups
        by_id = {s["setup_id"]: s for s in got}
        assert by_id["s1"]["rating"] == "liked"
        assert "rating" not in by_id["s2"]

    def test_an_existing_rating_is_never_overwritten(self):
        db = _DB(setups=[{"setup_id": "s1", "rating": "hated"}],
                 feedback=[{"setup_id": "s1", "rating": "liked"}])
        assert build_setup_inputs(db, _config()).historical_setups[0]["rating"] == "hated"


class TestNeverRaises:
    def test_a_database_that_throws_degrades_to_unknown(self):
        class _Boom:
            def get_event(self, name):
                raise RuntimeError("db down")

            def get_setups_for_car_track(self, car, track):
                raise RuntimeError("db down")

        inp = build_setup_inputs(_Boom(), _config())
        assert isinstance(inp, SetupInputs)
        assert inp.car == "Porsche Cayman GT4"      # config still resolves it
        assert inp.historical_setups == ()

    def test_garbage_config_returns_an_empty_snapshot(self):
        assert build_setup_inputs(None, None).is_known is False

    def test_an_unknown_car_has_no_specs_and_no_gear_count(self):
        inp = build_setup_inputs(None, _config(car="Not A Real Car"))
        assert inp.car_specs == {}
        assert inp.num_gears == 0
        assert inp.car_class == ""
