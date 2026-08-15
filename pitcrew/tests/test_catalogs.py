"""Reference catalogs carried over from the old data layer."""
from __future__ import annotations

from pitcrew.store import catalogs
from pitcrew.store.tyres import ALL_COMPOUNDS


def test_track_names_load():
    names = catalogs.track_names()
    assert len(names) > 50
    assert any(name.startswith("Autodromo Nazionale Monza") for name in names)


def test_every_gt7_circuit_can_be_picked():
    """41 circuits and 84 layouts, which is what GT7 has.

    The catalogue this replaced held 27 circuits. The event screen offered
    what was in it, so a round at any of the other fourteen could not be
    entered at all - which is how this was found, preparing for Yas Marina.
    """
    records = catalogs.layout_records()
    assert len({row["track"] for row in records}) == 41
    assert len(records) == 84
    assert len(catalogs.track_bases()) == 41

    for circuit in ("Yas Marina Circuit", "Suzuka Circuit",
                    "Mount Panorama Circuit", "Autódromo de Interlagos",
                    "WeatherTech Raceway Laguna Seca", "Brands Hatch",
                    "Tsukuba Circuit", "Michelin Raceway Road Atlanta"):
        assert circuit in catalogs.track_bases()
        assert catalogs.layouts_for(circuit)


def test_a_circuit_offers_its_layouts_in_the_order_gt7_lists_them():
    assert catalogs.layouts_for("Yas Marina Circuit") == ("Full Course",)
    assert catalogs.layouts_for("Autodromo Nazionale Monza") == (
        "Full Course", "No Chicane")
    # Full Course first, then the cut-down variants: the console's order.
    assert catalogs.layouts_for("Nürburgring")[0] == "Nordschleife"
    assert "Grand Prix" in catalogs.layouts_for("Nürburgring")


def test_reversible_layouts_are_offered_as_their_own_layout():
    lago = catalogs.layouts_for("Autodrome Lago Maggiore")
    assert lago[:2] == ("Full Course", "Full Course (Reverse)")
    assert catalogs.is_reverse("Full Course (Reverse)")
    assert not catalogs.is_reverse("Full Course")
    # Monza is not reversible, and must not be offered as if it were.
    assert not any(catalogs.is_reverse(one)
                   for one in catalogs.layouts_for("Autodromo Nazionale Monza"))


def test_a_reversed_lap_gets_no_corner_model_rather_than_the_wrong_one():
    """The corners come in the opposite order, so the forward map mislabels
    every one of them. Silence beats confident wrong names."""
    assert catalogs.load_station_map(
        "Autodromo Nazionale Monza", "Full Course") is not None
    assert catalogs.load_station_map(
        "Autodromo Nazionale Monza", "Full Course (Reverse)") is None


def test_the_track_catalogue_and_the_rain_list_agree():
    """The two files are read off the same page on the same day, and they
    are the reason this bug existed: two lists of circuits that could drift.
    A circuit the picker offers but the rain lookup cannot resolve reports
    'unknown' during a race weekend - which is what the misspelt 'Eiger
    Norwand' did."""
    from pitcrew.analysis import weather

    for row in catalogs.layout_records():
        seeded, why = weather.rain_seed(row["track"], row["layout"])
        assert seeded is not None, (
            f"{row['track']} - {row['layout']} is in the picker but the rain "
            f"list cannot resolve it: {why}")
        assert seeded == row["rain"], (
            f"{row['track']} - {row['layout']}: catalogue says "
            f"rain={row['rain']}, rain list says {seeded} ({why})")


def test_track_names_are_sorted_and_unique():
    names = catalogs.track_names()
    assert list(names) == sorted(set(names))


def test_names_are_read_as_utf8():
    """Layout separators are en dashes; reading with the cp1252 default mangles them."""
    names = catalogs.track_names()
    assert any("–" in name for name in names)
    assert not any(marker in name for name in names for marker in ("Ã", "â"))


def test_a_track_not_in_the_catalogue_can_still_be_raced():
    """The list is complete for GT7 as read, not closed for ever. A circuit
    added by a later update has to be enterable the day it ships, which is
    what the store's custom catalogue is for - so nothing here may assume
    the shipped names are all the names."""
    assert "Nowhere Special" not in catalogs.track_bases()
    assert catalogs.layouts_for("Nowhere Special") == ()


def test_cars_load_and_map_by_id():
    cars = catalogs.cars_by_id()
    assert len(cars) > 100
    car_id = next(iter(cars))
    assert catalogs.car_name(car_id) == cars[car_id]


def test_unknown_car_id_is_none():
    assert catalogs.car_name(None) is None
    assert catalogs.car_name(999_999) is None


def test_compounds_are_available():
    codes = {c.code for c in ALL_COMPOUNDS}
    assert {"RH", "RM", "RS", "IM", "HW"} <= codes


def test_monza_has_a_station_map():
    """Monza is the one modelled track; the export hangs corners off this."""
    station_map = catalogs.load_station_map("Autodromo Nazionale Monza", "Full Course")
    assert station_map is not None
    assert station_map.get("lap_length_m", 0) > 5_000


def test_unmodelled_track_returns_none():
    assert catalogs.load_station_map("Nowhere Special") is None
