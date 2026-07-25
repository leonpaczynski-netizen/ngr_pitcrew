"""Per-domain run briefs.

UAT-6: "I did the coaching session and can't see how it's different to any other
session", and "nothing ever appears under monitor on practice page". Every objective
produced the same run card from one generic template, whose monitor line was the
literal placeholder "whatever the coaching run is meant to show".

These tests pin the property that actually matters: two different domains must produce
genuinely different instructions, not the same card with a different title.
"""

from __future__ import annotations

import pytest

from strategy.practice_run_recording import DOMAIN_RUN_TYPE, run_type_for_domain
from strategy.run_brief import (
    RunBrief, brief_for_domain, brief_for_run_type, known_domains,
    lap_progress_note,
)


class TestEveryBriefIsComplete:
    @pytest.mark.parametrize("domain", known_domains())
    def test_a_brief_says_how_to_drive_what_to_watch_and_what_it_buys(self, domain):
        b = brief_for_domain(domain)
        assert b.is_known
        assert b.objective and b.run_name
        assert b.how_to_drive, "a run with no driving instructions is the old template"
        assert b.monitor and b.reports
        assert b.fuel and b.tyre and b.target_laps and b.push_level
        assert b.invalidation

    @pytest.mark.parametrize("domain", known_domains())
    def test_no_placeholder_text_survives(self, domain):
        """The old card literally rendered "whatever the coaching run is meant to show"."""
        text = " ".join((
            brief_for_domain(domain).objective,
            *brief_for_domain(domain).how_to_drive,
            *brief_for_domain(domain).monitor,
            *brief_for_domain(domain).reports,
        )).lower()
        for placeholder in ("whatever", "tbd", "todo", "meant to show"):
            assert placeholder not in text


class TestBriefsAreActuallyDifferent:
    def test_a_coaching_run_is_not_a_tyre_test(self):
        coaching = brief_for_domain("driver_coaching")
        tyre = brief_for_domain("tyre_model")
        assert coaching.how_to_drive != tyre.how_to_drive
        assert coaching.monitor != tyre.monitor
        assert coaching.fuel != tyre.fuel
        assert coaching.push_level != tyre.push_level

    def test_every_domain_has_a_distinct_driving_instruction_set(self):
        seen = {}
        for d in known_domains():
            key = brief_for_domain(d).how_to_drive
            assert key not in seen, f"{d} drives identically to {seen.get(key)}"
            seen[key] = d

    def test_qualifying_is_the_short_low_fuel_run_and_the_race_run_is_not(self):
        quali = brief_for_domain("setup_qualifying")
        race = brief_for_domain("setup_race")
        assert "minimum" in quali.fuel.lower()
        assert "full" in race.fuel.lower()
        assert quali.target_laps != race.target_laps

    def test_an_experiment_is_pinned_to_one_change_at_a_time(self):
        b = brief_for_domain("working_window")
        joined = " ".join(b.how_to_drive + b.invalidation).lower()
        assert "one change" in joined


class TestUnknownStaysHonest:
    def test_an_unrecognised_domain_never_pretends_to_be_a_controlled_test(self):
        b = brief_for_domain("no_such_domain")
        assert not b.is_known or b.domain == "no_such_domain"
        assert "no specific test" in " ".join(b.how_to_drive).lower()

    @pytest.mark.parametrize("junk", ["", None, 0, [], "   "])
    def test_junk_never_raises(self, junk):
        b = brief_for_domain(junk)
        assert isinstance(b, RunBrief) and b.run_name


class TestRunTypeLookup:
    @pytest.mark.parametrize("domain", sorted(DOMAIN_RUN_TYPE))
    def test_a_recorded_run_resolves_back_to_its_own_brief(self, domain):
        """A recorded run keeps its activity type, not the objective that started it."""
        run_type = run_type_for_domain(domain)
        brief = brief_for_run_type(run_type.value)
        assert brief.run_name
        # The round trip must land on a brief that serves the same domain, allowing for
        # the domains that legitimately share one run type (race pace / race setup).
        assert run_type_for_domain(brief.domain) is run_type

    def test_an_unknown_run_type_falls_back_rather_than_raising(self):
        assert brief_for_run_type("something_else").run_name == "practice run"
        assert brief_for_run_type(None).run_name == "practice run"


class TestLapProgressNote:
    """The live 'am I done yet?' guidance shown while a practice run is recording."""

    def test_before_any_lap_it_states_the_target_window(self):
        note = lap_progress_note("5–8", 0)
        assert "5–8" in note and "aim for" in note.lower()

    def test_below_the_window_says_keep_going(self):
        note = lap_progress_note("5–8", 3)
        assert "3 of 5–8" in note and "keep going" in note.lower()

    def test_inside_the_window_says_enough_for_a_read(self):
        assert "enough for a read" in lap_progress_note("5–8", 6).lower()
        # Boundaries are inclusive: the minimum counts as enough.
        assert "enough for a read" in lap_progress_note("5–8", 5).lower()
        assert "enough for a read" in lap_progress_note("5–8", 8).lower()

    def test_past_the_window_says_end_on_a_clean_lap(self):
        assert "end the run on a clean lap" in lap_progress_note("5–8", 12).lower()

    def test_a_single_number_target_is_treated_as_the_window(self):
        assert "aim for 3" in lap_progress_note("3 (out · flyer · in)", 0).lower()
        assert "1 of 3" in lap_progress_note("3 (out · flyer · in)", 1)
        assert "enough for a read" in lap_progress_note("3 (out · flyer · in)", 3).lower()

    def test_a_range_buried_in_prose_is_still_read(self):
        # "12–20, or until the tyre is done" — the tyre test's target.
        assert "12–20" in lap_progress_note("12–20, or until the tyre is done", 0)
        assert "keep going" in lap_progress_note("12–20, or until the tyre is done", 8).lower()

    def test_prose_only_target_falls_back_to_a_completeness_reminder(self):
        assert "full planned stint" in lap_progress_note("A full stint", 0).lower()
        note = lap_progress_note("The planned stint length", 4)
        assert "4 lap" in note and "full planned stint" in note.lower()

    @pytest.mark.parametrize("laps", [-3, 0, 5, "bad", None])
    def test_it_never_raises_on_odd_lap_counts(self, laps):
        assert isinstance(lap_progress_note("5–8", laps), str)

    def test_every_brief_target_yields_a_note_at_every_stage(self):
        for d in known_domains():
            tl = brief_for_domain(d).target_laps
            for laps in (0, 4, 10, 25):
                assert lap_progress_note(tl, laps)  # non-empty, never raises
