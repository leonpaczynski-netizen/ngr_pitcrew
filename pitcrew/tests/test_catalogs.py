"""Reference catalogs carried over from the old data layer."""
from __future__ import annotations

from pitcrew.store import catalogs
from pitcrew.store.tyres import ALL_COMPOUNDS


def test_track_names_load():
    names = catalogs.track_names()
    assert len(names) > 50
    assert any(name.startswith("Autodromo Nazionale Monza") for name in names)


def test_track_names_are_sorted_and_unique():
    names = catalogs.track_names()
    assert list(names) == sorted(set(names))


def test_names_are_read_as_utf8():
    """Layout separators are en dashes; reading with the cp1252 default mangles them."""
    names = catalogs.track_names()
    assert any("–" in name for name in names)
    assert not any(marker in name for name in names for marker in ("Ã", "â"))


def test_track_list_is_suggestions_not_a_closed_set():
    """The catalog is incomplete - Monza only appears as the No Chicane variant."""
    assert "Autodromo Nazionale Monza" not in catalogs.track_names()


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
