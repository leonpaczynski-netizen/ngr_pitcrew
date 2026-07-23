"""A layout must never resolve to a DIFFERENT layout's reference path.

Found 2026-07-23 while building the guided Track Model surface: an unmodelled layout
silently loaded a neighbouring layout's approved path and reported it as available.
``_ids_match`` compared *significant* tokens, and ``_GENERIC_TOKENS`` discarded the very
words that distinguish layouts of one circuit — "full", "short", "long", "course",
"reverse", "gp", "national" — so both reduced to the same token set.

Consequences, all silent: live progress resolution, station mapping and the trusted lap
length could read another layout's racing line, and the Track Model surface would
announce "This track is modelled" for a layout that never was.

The asymmetry these tests pin: a TRACK id stays tolerant (callers legitimately pass a
display name as ``track_hint``), a LAYOUT id must be exact.
"""

import pytest

from data.reference_path_loader import (
    _layout_ids_match, _track_ids_match, validate_reference_path_identity,
)

WATKINS = "watkins_glen_international"
WATKINS_LONG = "watkins_glen_international__long_course"
WATKINS_SHORT = "watkins_glen_international__short_course"
FUJI_FULL = "fuji_international_speedway__full_course"
FUJI_REVERSE = "fuji_international_speedway__full_course_reverse"
DAYTONA_ROAD = "daytona_international_speedway__road_course"
DAYTONA_OVAL = "daytona_international_speedway__oval"


class TestLayoutsAreNeverConfused:
    @pytest.mark.parametrize("requested,stored", [
        (WATKINS_SHORT, WATKINS_LONG),
        (FUJI_REVERSE, FUJI_FULL),          # the track driven BACKWARDS
        (DAYTONA_OVAL, DAYTONA_ROAD),       # an oval is not a road course
        ("fuji_international_speedway__short_course", FUJI_FULL),
        (WATKINS_LONG, WATKINS_SHORT),      # and not the other way either
    ])
    def test_a_different_layout_never_matches(self, requested, stored):
        assert _layout_ids_match(requested, stored) is False

    @pytest.mark.parametrize("layout", [WATKINS_LONG, FUJI_FULL, DAYTONA_ROAD])
    def test_a_layout_still_matches_itself(self, layout):
        assert _layout_ids_match(layout, layout) is True


class TestStrictIsNotBrittle:
    """Exactness is on IDENTITY, not on formatting — ``_norm_id`` still normalises."""

    @pytest.mark.parametrize("written", [
        "Watkins Glen International__Long Course",
        "watkins-glen-international--long-course",
        "  WATKINS_GLEN_INTERNATIONAL__LONG_COURSE  ",
    ])
    def test_case_and_separators_still_match(self, written):
        assert _layout_ids_match(written, WATKINS_LONG) is True

    def test_an_empty_layout_is_a_wildcard_for_the_track_only_lookup(self):
        assert _layout_ids_match("", WATKINS_LONG) is True

    def test_an_asset_with_no_layout_recorded_cannot_claim_a_layout(self):
        assert _layout_ids_match(WATKINS_LONG, "") is False


class TestTrackMatchingStaysTolerant:
    """Callers pass a display name as ``track_hint`` when no canonical id is known
    (ui/dashboard.py and ui/live_ui.py both do), so the TRACK side must stay loose."""

    @pytest.mark.parametrize("hint", [
        "Watkins Glen", "watkins glen international",
        "Watkins Glen International", WATKINS,
    ])
    def test_a_display_name_still_resolves_the_track(self, hint):
        assert _track_ids_match(hint, WATKINS) is True

    def test_a_different_circuit_still_does_not_match(self):
        assert _track_ids_match(WATKINS, "fuji_international_speedway") is False

    def test_an_empty_track_matches_anything(self):
        assert _track_ids_match("", WATKINS) is True


class TestIdentityValidation:
    """``validate_reference_path_identity`` gates whether pit confidence may be lifted —
    it must not verify an asset belonging to another layout."""

    class _Asset:
        def __init__(self, track_id, layout_id):
            self.track_id, self.layout_id = track_id, layout_id

    def test_the_right_layout_verifies(self):
        ok, _msg = validate_reference_path_identity(
            self._Asset(WATKINS, WATKINS_LONG), WATKINS, WATKINS_LONG)
        assert ok is True

    def test_a_neighbouring_layout_is_rejected(self):
        ok, msg = validate_reference_path_identity(
            self._Asset(WATKINS, WATKINS_LONG), WATKINS, WATKINS_SHORT)
        assert ok is False
        assert "mismatch" in msg

    def test_a_display_name_track_still_verifies(self):
        ok, _msg = validate_reference_path_identity(
            self._Asset(WATKINS, WATKINS_LONG), "Watkins Glen", WATKINS_LONG)
        assert ok is True

    def test_no_asset_is_a_mismatch_not_a_crash(self):
        ok, _msg = validate_reference_path_identity(None, WATKINS, WATKINS_LONG)
        assert ok is False


class TestEndToEnd:
    """Against the reference paths actually on disk."""

    def test_an_unmodelled_layout_reports_unavailable(self):
        from data.reference_path_loader import reference_path_asset_summary
        summary = reference_path_asset_summary(WATKINS, WATKINS_SHORT)
        assert summary["available"] is False
        assert summary["station_count"] == 0
        assert summary["lap_length_m"] == 0.0

    def test_the_modelled_layout_still_reports_available(self):
        from data.reference_path_loader import reference_path_asset_summary
        summary = reference_path_asset_summary(WATKINS, WATKINS_LONG)
        assert summary["available"] is True
        assert summary["station_count"] > 0

    def test_an_unmodelled_layout_has_no_trusted_lap_length(self):
        """A wrong lap length silently corrupts fuel and stint maths."""
        from data.reference_path_loader import resolve_trusted_lap_length
        assert resolve_trusted_lap_length(WATKINS, WATKINS_SHORT) is None

    def test_readiness_no_longer_calls_an_unmodelled_layout_approved(self):
        from data.track_readiness_disk import resolve_track_readiness_from_disk
        assert resolve_track_readiness_from_disk(WATKINS, WATKINS_SHORT).is_approved is False
        assert resolve_track_readiness_from_disk(WATKINS, WATKINS_LONG).is_approved is True
