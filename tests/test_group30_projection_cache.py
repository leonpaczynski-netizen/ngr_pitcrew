"""Group 30 — project_to_screen() caching.

The projection cache must cut per-frame allocation without ever serving a stale
live car dot, since the live path mutates draw_data.car_dot in place each packet
while keeping the same TrackMapDrawData object.
"""
from ui.track_map_vm import (
    CarDot,
    MapPoint,
    TrackMapDrawData,
    project_to_screen,
)


def _draw_data(car_dot=None):
    return TrackMapDrawData(
        centreline=[MapPoint(0, 0), MapPoint(50, 50), MapPoint(100, 100)],
        width_left=[MapPoint(0, 1), MapPoint(50, 51)],
        width_right=[MapPoint(0, -1), MapPoint(50, 49)],
        start_finish=MapPoint(0, 0),
        corner_labels=[],
        car_dot=car_dot,
        telemetry_trace=[],
        bounds=(0.0, 0.0, 100.0, 100.0),
        status_text="",
        confidence_color="#888",
        has_map=True,
    )


def test_same_object_and_size_reuses_projected_geometry():
    dd = _draw_data()
    r1 = project_to_screen(dd, 400, 300)
    r2 = project_to_screen(dd, 400, 300)
    # Cache hit returns the same projected object (no reallocation).
    assert r1 is r2
    assert r1.centreline is r2.centreline


def test_in_place_car_dot_mutation_is_not_served_stale():
    dd = _draw_data(car_dot=CarDot(x=10.0, y=10.0, confidence="high", is_valid=True))
    r1 = project_to_screen(dd, 400, 300)
    first_x = r1.car_dot.x

    # Live path mutates the dot in place on the SAME object, then repaints.
    dd.car_dot = CarDot(x=90.0, y=90.0, confidence="high", is_valid=True)
    r2 = project_to_screen(dd, 400, 300)

    assert r2 is r1                      # geometry served from cache
    assert r2.car_dot.x != first_x      # but the dot reflects the new position
    # Dot at x=90 projects further right than the dot at x=10.
    assert r2.car_dot.x > first_x


def test_car_dot_cleared_in_place_is_reflected():
    dd = _draw_data(car_dot=CarDot(x=10.0, y=10.0, confidence="high", is_valid=True))
    project_to_screen(dd, 400, 300)
    dd.car_dot = None
    r = project_to_screen(dd, 400, 300)
    assert r.car_dot is None


def test_highlight_scalars_refreshed_on_cache_hit():
    dd = _draw_data()
    project_to_screen(dd, 400, 300)
    dd.highlight_start_progress = 0.2
    dd.highlight_end_progress = 0.6
    r = project_to_screen(dd, 400, 300)
    assert r.highlight_start_progress == 0.2
    assert r.highlight_end_progress == 0.6


def test_different_canvas_size_projects_separately():
    dd = _draw_data()
    r_small = project_to_screen(dd, 400, 300)
    r_big = project_to_screen(dd, 800, 600)
    assert r_small is not r_big
    # Larger canvas scales the same world span to a larger pixel span.
    span_small = r_small.centreline[-1].x - r_small.centreline[0].x
    span_big = r_big.centreline[-1].x - r_big.centreline[0].x
    assert span_big > span_small


def test_cache_is_bounded():
    from ui.track_map_vm import _PROJ_CACHE, _PROJ_CACHE_MAX
    # Project many distinct objects; cache must not grow unbounded.
    for _ in range(_PROJ_CACHE_MAX * 3):
        project_to_screen(_draw_data(), 400, 300)
    assert len(_PROJ_CACHE) <= _PROJ_CACHE_MAX
