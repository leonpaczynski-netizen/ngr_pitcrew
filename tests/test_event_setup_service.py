"""Creating and activating an event, headless (single-system stage 3).

Deliberately NOT a port of the classic Event Planner's eighteen-widget form: the driver
states four things, everything else has a standard default and is only asked about when
the event actually differs.
"""

from services.event_setup import (
    DEFAULT_RULES, EventDraft, EventSetupService, draft_from_event, validate,
)


class _DB:
    def __init__(self, events=None, cycles=None):
        self.events = list(events or [])
        self.cycles = dict(cycles or {})
        self.next_id = 7

    def get_all_events(self):
        return list(self.events)

    def get_event(self, name):
        return next((e for e in self.events if e.get("name") == name), None)

    def upsert_event(self, row):
        for i, e in enumerate(self.events):
            if e["name"] == row["name"]:
                self.events[i] = dict(row)
                return e.get("id", self.next_id)
        row = dict(row)
        row["id"] = self.next_id
        self.events.append(row)
        return self.next_id

    def get_preparation_cycle(self, cycle_id):
        return dict(self.cycles[cycle_id]) if cycle_id in self.cycles else None

    def upsert_preparation_cycle(self, cycle):
        self.cycles[cycle["cycle_id"]] = dict(cycle)
        return cycle["cycle_id"]


def _draft(**kw):
    base = dict(name="GR Enduro Rd2", car="Porsche Cayman GT4",
                track="Watkins Glen International", race_type="timed", duration_mins=120)
    base.update(kw)
    return EventDraft(**base)


class TestOnlyFourThingsAreRequired:
    def test_a_complete_draft_validates(self):
        assert validate(_draft()) == ()

    def test_each_missing_essential_names_itself_and_says_why(self):
        """A blank draft is missing only identity — the format already has a workable
        default (25 laps), so the driver is never blocked on a number they can change."""
        issues = {i.field_name: i.message for i in validate(EventDraft())}
        assert set(issues) == {"name", "car", "track"}
        assert "setup and strategy are built for it" in issues["car"]

    def test_a_lap_race_needs_laps_a_timed_race_needs_minutes(self):
        assert [i.field_name for i in validate(_draft(race_type="lap", laps=0))] == ["laps"]
        assert [i.field_name for i in
                validate(_draft(race_type="timed", duration_mins=0))] == ["duration_mins"]

    def test_regulations_are_never_required(self):
        """Nothing in the rules block can block creating an event."""
        assert validate(_draft(rules={})) == ()


class TestRulesAreOptionalAndDefaulted:
    def test_a_fresh_draft_carries_the_standard_rules(self):
        assert EventDraft().rules == DEFAULT_RULES
        assert EventDraft().has_custom_rules is False

    def test_changing_one_rule_flags_the_event_as_non_standard(self):
        d = _draft().with_rule("tyre_wear", 4.0)
        assert d.has_custom_rules is True
        assert d.rule("fuel_mult") == 1.0        # the rest stay standard

    def test_unset_rules_fall_back_to_the_standard_value(self):
        assert _draft(rules={}).rule("mandatory_stops") == 0


class TestPlainEnglishSummary:
    def test_a_standard_event_reads_as_one_sentence(self):
        assert _draft().summary() == (
            "A 120-minute race at Watkins Glen International in the Porsche Cayman GT4.")

    def test_a_lap_race_says_laps(self):
        assert _draft(race_type="lap", laps=25).summary().startswith("A 25-lap race")

    def test_only_the_rules_that_differ_are_mentioned(self):
        d = (_draft().with_rule("tyre_wear", 4.0).with_rule("mandatory_stops", 1)
             .with_rule("abs", False))
        text = d.summary()
        assert "Tyres wear at 4x." in text
        assert "1 mandatory pit stop." in text
        assert "ABS is not allowed." in text
        assert "Fuel burns" not in text          # unchanged, so not mentioned
        assert "Weather" not in text

    def test_allowed_compounds_are_listed_when_restricted(self):
        assert "Allowed compounds: RM, RH." in _draft().with_rule(
            "avail_tyres", ["RM", "RH"]).summary()


class TestSaveAndActivate:
    def _svc(self, db=None, config=None):
        cfg = config if config is not None else {}
        return EventSetupService(db=db or _DB(), config=cfg, persist=None), cfg

    def test_an_invalid_draft_writes_nothing(self):
        db = _DB()
        svc, cfg = self._svc(db)
        result = svc.save_and_activate(EventDraft())
        assert result.ok is False
        assert result.issues
        assert db.events == [] and db.cycles == {}
        assert cfg == {}

    def test_saving_stores_the_event_and_activates_it(self):
        db = _DB()
        svc, cfg = self._svc(db)
        result = svc.save_and_activate(_draft())
        assert result.ok is True
        assert result.event_name == "GR Enduro Rd2"
        assert db.events[0]["track"] == "Watkins Glen International"
        assert db.events[0]["race_type"] == "timed"
        assert cfg["active_event_id"] == "GR Enduro Rd2"

    def test_a_preparation_cycle_is_created_or_the_command_centre_cannot_see_it(self):
        db = _DB()
        svc, cfg = self._svc(db)
        result = svc.save_and_activate(_draft())
        assert result.cycle_id == "cycle-gr-enduro-rd2"
        assert cfg["active_cycle_id"] == "cycle-gr-enduro-rd2"
        assert db.cycles["cycle-gr-enduro-rd2"]["car"] == "Porsche Cayman GT4"

    def test_activating_twice_never_makes_two_cycles(self):
        db = _DB()
        svc, _cfg = self._svc(db)
        svc.save_and_activate(_draft())
        svc.save_and_activate(_draft())
        assert len(db.cycles) == 1
        assert len(db.events) == 1

    def test_a_finished_cycle_is_never_silently_reopened(self):
        db = _DB(cycles={"cycle-gr-enduro-rd2": {
            "cycle_id": "cycle-gr-enduro-rd2", "explicit_state": "complete",
            "created_at": "2026-01-01T00:00:00"}})
        svc, _cfg = self._svc(db)
        svc.save_and_activate(_draft())
        assert db.cycles["cycle-gr-enduro-rd2"]["explicit_state"] == "complete"
        assert db.cycles["cycle-gr-enduro-rd2"]["created_at"] == "2026-01-01T00:00:00"

    def test_the_working_config_core_is_fanned_out(self):
        svc, cfg = self._svc()
        svc.save_and_activate(_draft())
        strat = cfg["strategy"]
        assert strat["car"] == "Porsche Cayman GT4"
        assert strat["track"] == "Watkins Glen International"
        assert strat["race_type"] == "timed"
        assert strat["race_duration_minutes"] == 120

    def test_rules_are_not_duplicated_into_the_config(self):
        """Every consumer reads rules DB-first; a second copy is a second thing to go
        stale — the exact cache the classic fan-out was stripped of."""
        svc, cfg = self._svc()
        svc.save_and_activate(_draft().with_rule("tyre_wear", 4.0))
        assert "tyre_wear" not in cfg["strategy"]
        assert "mandatory_stops" not in cfg["strategy"]

    def test_config_is_persisted_through_the_supplied_callable(self):
        saved = []
        svc = EventSetupService(db=_DB(), config={}, persist=lambda: saved.append(True))
        svc.save_and_activate(_draft())
        assert saved == [True]

    def test_no_database_reports_instead_of_pretending(self):
        svc = EventSetupService(db=None, config={})
        result = svc.save_and_activate(_draft())
        assert result.ok is False
        assert "database" in result.message


class TestEditing:
    def test_a_saved_event_round_trips_into_a_draft(self):
        db = _DB()
        svc = EventSetupService(db=db, config={"strategy": {"car": "Porsche Cayman GT4"}})
        svc.save_and_activate(_draft().with_rule("tyre_wear", 4.0))
        again = svc.draft_for("GR Enduro Rd2")
        assert again.name == "GR Enduro Rd2"
        assert again.track == "Watkins Glen International"
        assert again.is_timed is True
        assert again.duration_mins == 120
        assert again.rule("tyre_wear") == 4.0
        assert again.car == "Porsche Cayman GT4"

    def test_a_blank_draft_still_carries_the_current_car(self):
        svc = EventSetupService(db=_DB(), config={"strategy": {"car": "Mazda MX-5"}})
        assert svc.draft_for("").car == "Mazda MX-5"

    def test_draft_from_a_legacy_row_using_duration(self):
        d = draft_from_event({"name": "X", "race_type": "timed", "duration": 90})
        assert d.duration_mins == 90
