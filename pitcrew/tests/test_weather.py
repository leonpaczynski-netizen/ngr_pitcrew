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
    assert can_rain("Fixed", rain_possible=True) is False
    assert can_rain("Fixed", rain_possible=None) is False


def test_random_weather_hands_it_to_the_circuit():
    assert can_rain("Random", rain_possible=True) is True
    assert can_rain("Random", rain_possible=False) is False


def test_an_unanswered_circuit_is_unknown_not_dry():
    """Most circuits added since 2022 are simply missing from the lists, and
    treating absence as a dry circuit retires the wet contingency at all of
    them."""
    assert can_rain("Random", rain_possible=None) is None


# ------------------------------------------------------------ what it means

def test_rain_impossible_retires_the_wets_entirely():
    report = wet_evidence("Fixed", True, wet_laps=0, track="Spa")
    assert report["canRain"] is False
    assert "irrelevant" in report["note"]


def test_rain_possible_with_no_wet_running_is_an_evidence_gap():
    """The plan is unaffected - weather cannot be known in advance, so wets
    are never planned. What changes is that every call after it rains would be
    made on a tyre nobody has driven."""
    report = wet_evidence("Random", True, wet_laps=0, track="Spa")
    assert report["canRain"] is True
    assert report["wetLaps"] == 0
    assert "no wet running has ever been recorded" in report["note"]
    assert "never planned" in report["note"]


def test_wet_running_on_record_closes_the_gap():
    report = wet_evidence("Random", True, wet_laps=8, track="Spa")
    assert report["wetLaps"] == 8
    assert "8 laps of wet running" in report["note"]


def test_an_unanswered_circuit_asks_and_shows_its_working():
    report = wet_evidence("Random", None, wet_laps=0, track="Suzuka")
    assert report["canRain"] is None
    assert "cannot be measured" in report["note"]
    assert "2022" in report["note"]


# --------------------------------------------------------------- the seed

def test_the_seed_knows_the_listed_circuits():
    assert rain_seed("Spa-Francorchamps") is True
    assert rain_seed("Suzuka") is True
    assert rain_seed("Fuji Speedway (Full)") is True


def test_the_seed_says_nothing_rather_than_no():
    """Monza is absent from both 2022 lists. That is not evidence it is dry -
    it is four years of circuit additions and an admittedly partial list."""
    assert rain_seed("Autodromo Nazionale Monza") is None
    assert rain_seed(None) is None
