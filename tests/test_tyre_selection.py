"""Choosing a tyre compound in the Garage (UAT-4).

"Still can't see a way to change my tyres in app from medium to hard for the 2 hour
endurance race." The Garage had no tyre control at all, even though the event's
regulations, the compound table and a compound-comparing race-plan pass all existed.
"""

from strategy.tyre_selection import (
    DEFAULT_AVAILABLE, build_tyre_choice, current_code, setup_fields_for, softness_rank,
    resolve_qualifying_compound, is_wet_weather,
)


class TestOrdering:
    def test_softest_first(self):
        assert softness_rank("RS") < softness_rank("RM") < softness_rank("RH")

    def test_aliases_and_codes_both_rank(self):
        assert softness_rank("Racing Soft") == softness_rank("RS")
        assert softness_rank("nonsense") > softness_rank("HW")


class TestAvailability:
    def test_the_events_regulation_is_honoured(self):
        c = build_tyre_choice(discipline="race", available=["RM", "RH"])
        assert c.codes == ("RM", "RH")
        assert c.restricted is True

    def test_no_regulation_offers_the_dry_racing_compounds(self):
        c = build_tyre_choice(discipline="race", available=[])
        assert c.codes == DEFAULT_AVAILABLE
        assert c.restricted is False
        assert "no compound restriction" not in c.guidance   # the UI adds that note

    def test_a_required_compound_is_always_selectable(self):
        c = build_tyre_choice(discipline="race", available=["RM"], required=["RH"])
        assert "RH" in c.codes
        assert [o.required for o in c.options if o.code == "RH"] == [True]

    def test_softest_and_hardest_are_labelled(self):
        c = build_tyre_choice(discipline="race", available=["RH", "RM", "RS"])
        labels = {o.code: o.label for o in c.options}
        assert "softest allowed" in labels["RS"]
        assert "hardest allowed" in labels["RH"]
        assert "allowed" not in labels["RM"]

    def test_a_single_allowed_compound_is_neither_extreme(self):
        c = build_tyre_choice(discipline="race", available=["RM"])
        assert c.options[0].label == "Racing Medium"


class TestDisciplineRules:
    def test_qualifying_recommends_the_softest_allowed(self):
        c = build_tyre_choice(discipline="qualifying", available=["RH", "RM", "RS"])
        assert c.recommended_code == "RS"
        assert "softest compound this event allows" in c.recommendation_reason

    def test_qualifying_softest_respects_the_regulation(self):
        """When soft is banned, the softest ALLOWED is the recommendation — not RS."""
        c = build_tyre_choice(discipline="qualifying", available=["RH", "RM"])
        assert c.recommended_code == "RM"

    def test_race_recommends_nothing_because_it_must_be_measured(self):
        c = build_tyre_choice(discipline="race", available=["RM", "RH"])
        assert c.recommended_code == ""
        assert "only recorded runs settle" in c.guidance

    def test_a_long_race_names_the_two_compounds_to_compare(self):
        c = build_tyre_choice(discipline="race", available=["RM", "RH"],
                              race_duration_minutes=120)
        assert "120 minutes" in c.guidance
        assert "Racing Hard" in c.guidance and "Racing Medium" in c.guidance

    def test_a_sprint_race_gets_no_endurance_advice(self):
        c = build_tyre_choice(discipline="race", available=["RM", "RH"],
                              race_duration_minutes=20)
        assert "minutes a harder compound" not in c.guidance

    def test_an_unknown_discipline_falls_back_to_the_race_rules(self):
        """Race is the safe default: it recommends nothing rather than guessing."""
        c = build_tyre_choice(discipline="whatever", available=["RM", "RH"])
        assert c.recommended_code == ""
        assert "only recorded runs settle" in c.guidance


class TestApplying:
    def test_selecting_writes_both_axles(self):
        assert setup_fields_for("RH") == {"tyre_front": "Racing Hard",
                                          "tyre_rear": "Racing Hard"}

    def test_an_unknown_compound_writes_nothing(self):
        assert setup_fields_for("ZZ") == {}
        assert setup_fields_for("") == {}

    def test_reads_the_compound_on_the_sheet(self):
        assert current_code({"tyre_front": "Racing Medium",
                             "tyre_rear": "Racing Medium"}) == "RM"

    def test_split_axles_report_no_single_compound(self):
        assert current_code({"tyre_front": "Racing Medium",
                             "tyre_rear": "Racing Hard"}) == ""
        assert current_code(None) == ""

    def test_legacy_naming_still_resolves(self):
        assert current_code({"tyre_front": "Racing: Hard",
                             "tyre_rear": "Racing: Hard"}) == "RH"


class TestNeverRaises:
    def test_garbage_input_yields_an_empty_choice_not_an_error(self):
        c = build_tyre_choice(discipline=None, available=None, required=None)
        assert c.codes == DEFAULT_AVAILABLE


class TestQualifyingCompoundRule:
    """Qualifying always runs the softest compound — softest dry slick when dry, the rain
    tyre when wet. Wetness = event weather OR the driver's manual override (GT7 reports no
    live rain)."""

    def test_dry_default_is_the_softest_slick(self):
        code, name, wet, _ = resolve_qualifying_compound()
        assert code == "RS" and wet is False

    def test_restricted_dry_gives_softest_allowed_slick(self):
        code, _n, wet, _ = resolve_qualifying_compound(available=["RH", "RM"])
        assert code == "RM" and wet is False

    def test_light_rain_fits_intermediate(self):
        code, _n, wet, _ = resolve_qualifying_compound(weather="Light Rain")
        assert code == "IM" and wet is True

    def test_heavy_rain_fits_heavy_wet(self):
        code, _n, wet, _ = resolve_qualifying_compound(weather="Heavy Rain")
        assert code == "HW" and wet is True

    def test_fixed_wet_fits_intermediate(self):
        assert resolve_qualifying_compound(weather="Fixed Wet")[0] == "IM"

    def test_random_weather_stays_dry_without_an_override(self):
        # The app can't know a random-weather session is raining — dry until told.
        assert resolve_qualifying_compound(weather="Random Weather")[2] is False

    def test_manual_override_makes_it_wet_in_random_weather(self):
        code, _n, wet, _ = resolve_qualifying_compound(
            weather="Random Weather", wet_override=True)
        assert wet is True and code == "IM"

    def test_override_false_beats_a_wet_event_when_the_track_dries(self):
        code, _n, wet, _ = resolve_qualifying_compound(
            weather="Heavy Rain", wet_override=False)
        assert wet is False and code == "RS"

    def test_wet_honours_an_allowed_wet_restriction(self):
        # Only Heavy Wet allowed + light rain → still HW (the only legal wet).
        assert resolve_qualifying_compound(available=["HW"], weather="Light Rain")[0] == "HW"

    def test_is_wet_weather_excludes_dry_and_random(self):
        assert is_wet_weather("Light Rain") is True
        assert is_wet_weather("Fixed Dry") is False
        assert is_wet_weather("Random Weather") is False

    def test_never_raises_on_garbage(self):
        assert resolve_qualifying_compound(available=None, weather=None) is not None
