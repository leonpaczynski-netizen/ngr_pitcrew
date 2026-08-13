"""Whether it can rain in this race - the one thing here nothing can measure.

Two things decide it and only one is about the circuit: the league's rule
(the V8 rounds run fixed sunny whatever the circuit offers) and the circuit's
own capability (most cannot produce rain at all).

GT7 broadcasts no weather channel in any packet format, so unlike the game
clock there is nothing to read it off and nothing to check a claim against.
The driver answers; the app never decides.
"""
from __future__ import annotations

from pitcrew.analysis.weather import can_rain, rain_seed, wet_evidence


# ------------------------------------------------------------- the two rules

def test_fixed_weather_makes_the_circuit_irrelevant():
    """The V8 rounds run sunny whatever the circuit can throw up."""
    assert can_rain("Fixed", True, "Spa-Francorchamps")[0] is False
    assert can_rain("Fixed", None, "Spa-Francorchamps")[0] is False


def test_random_weather_hands_it_to_the_circuit():
    assert can_rain("Random", True, "Spa")[0] is True
    assert can_rain("Random", False, "Spa")[0] is False


def test_the_driver_outranks_the_list():
    """He can see the lobby; the list is someone else's reading of it."""
    possible, why = can_rain("Random", True, "Autodromo Nazionale Monza")
    assert possible is True
    assert "declared on the event page" in why


def test_an_unlisted_circuit_is_unknown_not_dry():
    """A circuit added since the table was read. Treating absence as dry would
    quietly retire the wet contingency at every new one."""
    assert can_rain("Random", None, "Circuit Added In 2027")[0] is None


# ------------------------------------------------------------ what it means

def test_rain_impossible_retires_the_wets_entirely():
    report = wet_evidence("Fixed", True, wet_laps=0, track="Spa-Francorchamps")
    assert report["canRain"] is False
    assert "irrelevant" in report["note"]


def test_rain_possible_with_no_wet_running_is_an_evidence_gap():
    """The plan is unaffected - weather cannot be known in advance, so wets
    are never planned. What changes is that every call after it rains would be
    made on a tyre nobody has driven."""
    report = wet_evidence("Random", True, wet_laps=0, track="Spa-Francorchamps")
    assert report["canRain"] is True
    assert report["wetLaps"] == 0
    assert "no wet running has ever been recorded" in report["note"]
    assert "never planned" in report["note"]


def test_wet_running_on_record_closes_the_gap():
    report = wet_evidence("Random", True, wet_laps=8, track="Spa-Francorchamps")
    assert report["wetLaps"] == 8
    assert "8 laps of wet running" in report["note"]


def test_an_unlisted_circuit_asks_and_names_its_authority():
    report = wet_evidence("Random", None, wet_laps=0, track="Circuit From 2027")
    assert report["canRain"] is None
    assert "cannot be measured" in report["note"]
    assert "added since" in report["note"]


# --------------------------------------------------------------- the seed

def test_the_list_knows_the_rain_circuits():
    assert rain_seed("Circuit de Spa-Francorchamps")[0] is True
    assert rain_seed("Suzuka Circuit")[0] is True
    assert rain_seed("Fuji International Speedway")[0] is True


def test_rain_is_a_property_of_the_layout_not_the_track():
    """The part the 2022 lists got wrong. Dragon Trail Gardens rains and
    Seaside does not; Tokyo Expressway South does not while East does."""
    assert rain_seed("Dragon Trail", "Gardens")[0] is True
    assert rain_seed("Dragon Trail", "Seaside")[0] is False
    assert rain_seed("Tokyo Expressway", "East Clockwise")[0] is True
    assert rain_seed("Tokyo Expressway", "South Clockwise")[0] is False


def test_a_complete_list_can_say_no():
    """The wiki table covers all 41 tracks, so a circuit in it with no rain
    layout genuinely cannot rain - unlike the partial lists it replaced."""
    possible, why = rain_seed("Watkins Glen International", "Long Course")
    assert possible is False
    assert "GT Wiki" in why


def test_an_in_game_confirmation_outranks_the_list():
    """Monza, checked in the game by the driver."""
    possible, why = rain_seed("Autodromo Nazionale Monza")
    assert possible is False
    assert "confirmed in game" in why


def test_an_unlisted_circuit_says_nothing_rather_than_no():
    assert rain_seed("Circuit Added In 2027")[0] is None
    assert rain_seed(None)[0] is None
