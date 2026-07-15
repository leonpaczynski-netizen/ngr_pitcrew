"""Sprint 3 — deterministic TrackReadinessResolver (pure core).

Verifies the single readiness verdict for every state, including the exact
UAT regression: a Fuji-like layout with an approved reference path + accepted
model on disk must read READY_APPROVED (never BLOCKED), and a layout usable
only from seed geometry / station map must read READY_SEED_GEOMETRY — not be
gated by the station-map-only rule that caused the original Command Centre block.
"""
from __future__ import annotations

from types import SimpleNamespace

from data.track_readiness import (
    TrackReadiness,
    resolve_track_readiness,
    READY_STATES,
)


def _ctx(*, loc="fuji_international_speedway",
         lay="fuji_international_speedway__full_course",
         complete=True, **availability):
    """Build a duck-typed TrackContext-like object for the resolver."""
    av_defaults = dict(
        accepted_model_available=False,
        reference_path_available=False,
        reference_path_point_count=0,
        station_map_available=False,
        reviewed_model_available=False,
        seed_geometry_available=False,
        seed_corner_windows_available=False,
        seed_lap_length_available=False,
        seed_metadata_available=False,
    )
    av_defaults.update(availability)
    identity = SimpleNamespace(
        track_location_id=loc, layout_id=lay, is_complete=complete,
    )
    return SimpleNamespace(identity=identity, availability=SimpleNamespace(**av_defaults))


def test_fuji_approved_reference_path_is_ready_approved():
    r = resolve_track_readiness(_ctx(
        reference_path_available=True, reference_path_point_count=1200,
        accepted_model_available=True, station_map_available=True,
    ))
    assert r.state is TrackReadiness.READY_APPROVED
    assert r.is_ready and r.is_approved
    assert r.confidence == "high"
    assert any("reference path" in a for a in r.assets)


def test_accepted_model_without_ref_path_is_ready_approved():
    r = resolve_track_readiness(_ctx(accepted_model_available=True))
    assert r.state is TrackReadiness.READY_APPROVED
    assert r.is_ready


def test_station_map_only_is_ready_seed_geometry_not_blocked():
    # The original bug: station-map-only was the ONLY 'ready' signal. It should
    # still be ready — but as SEED_GEOMETRY, and readiness must not require it.
    r = resolve_track_readiness(_ctx(station_map_available=True))
    assert r.state is TrackReadiness.READY_SEED_GEOMETRY
    assert r.is_ready and not r.is_approved
    assert r.confidence == "medium"


def test_reviewed_model_only_is_ready_seed_geometry():
    r = resolve_track_readiness(_ctx(reviewed_model_available=True))
    assert r.state is TrackReadiness.READY_SEED_GEOMETRY
    assert r.is_ready


def test_seed_geometry_only_is_ready_seed_geometry():
    r = resolve_track_readiness(_ctx(seed_geometry_available=True))
    assert r.state is TrackReadiness.READY_SEED_GEOMETRY


def test_seed_windows_plus_length_is_ready_seed_geometry():
    r = resolve_track_readiness(_ctx(
        seed_corner_windows_available=True, seed_lap_length_available=True))
    assert r.state is TrackReadiness.READY_SEED_GEOMETRY


def test_reference_path_present_but_empty_is_invalid_asset():
    r = resolve_track_readiness(_ctx(
        reference_path_available=True, reference_path_point_count=0))
    assert r.state is TrackReadiness.INVALID_ASSET
    assert not r.is_ready
    assert "Rebuild" in r.next_action


def test_broken_ref_path_does_not_block_when_accepted_model_present():
    # A broken ref path must not veto an otherwise-approved model.
    r = resolve_track_readiness(_ctx(
        reference_path_available=True, reference_path_point_count=0,
        accepted_model_available=True))
    assert r.state is TrackReadiness.READY_APPROVED


def test_seed_metadata_only_is_partial():
    r = resolve_track_readiness(_ctx(seed_metadata_available=True))
    assert r.state is TrackReadiness.PARTIAL
    assert not r.is_ready


def test_identity_complete_no_assets_is_missing():
    r = resolve_track_readiness(_ctx())
    assert r.state is TrackReadiness.MISSING_ASSET
    assert not r.is_ready


def test_no_track_selected_is_missing_asset():
    r = resolve_track_readiness(_ctx(loc="", lay="", complete=False))
    assert r.state is TrackReadiness.MISSING_ASSET
    assert "Select a track" in r.next_action


def test_partial_identity_is_identity_mismatch():
    r = resolve_track_readiness(_ctx(loc="fuji_international_speedway", lay="", complete=False))
    assert r.state is TrackReadiness.IDENTITY_MISMATCH


def test_none_context_is_missing_asset():
    r = resolve_track_readiness(None)
    assert r.state is TrackReadiness.MISSING_ASSET


def test_determinism_identical_inputs_identical_output():
    a = resolve_track_readiness(_ctx(accepted_model_available=True))
    b = resolve_track_readiness(_ctx(accepted_model_available=True))
    assert a == b


def test_ready_states_membership():
    assert TrackReadiness.READY_APPROVED in READY_STATES
    assert TrackReadiness.READY_SEED_GEOMETRY in READY_STATES
    assert TrackReadiness.PARTIAL not in READY_STATES
    assert TrackReadiness.MISSING_ASSET not in READY_STATES


# --------------------------------------------------------------------------- #
# Disk-first integration + Command Centre wiring (Sprint 3 acceptance)
# --------------------------------------------------------------------------- #
def test_disk_resolver_reads_real_fuji_assets_as_ready_approved():
    """Fresh-restart acceptance: Fuji resolves READY_APPROVED straight from disk,
    with NO Track Modelling opened and NO in-memory state."""
    from data.track_readiness_disk import resolve_track_readiness_from_disk
    r = resolve_track_readiness_from_disk(
        "fuji_international_speedway",
        "fuji_international_speedway__full_course",
    )
    assert r.state is TrackReadiness.READY_APPROVED
    assert r.is_ready and r.is_approved


def test_disk_resolver_unknown_track_is_missing_asset():
    from data.track_readiness_disk import resolve_track_readiness_from_disk
    r = resolve_track_readiness_from_disk("no_such_track", "no_such_track__x")
    assert r.state is TrackReadiness.MISSING_ASSET


def test_command_centre_track_card_is_ready_not_blocked_when_approved():
    """The Command Centre 'Track Intelligence' card must render READY (never
    BLOCKED) when the readiness verdict is approved — the exact Fuji UAT bug."""
    from types import SimpleNamespace
    from ui.home_dashboard_vm import (
        build_home_dashboard_state, CARD_TRACK, HomeDashboardStatus,
    )
    from data.track_readiness import TrackReadinessResult, TrackReadiness

    identity = SimpleNamespace(
        track_location_id="fuji_international_speedway",
        layout_id="fuji_international_speedway__full_course",
        track_display_name="Fuji Speedway",
        layout_display_name="Full Course",
        is_complete=True,
    )
    # station_map deliberately FALSE — proves readiness no longer requires it.
    availability = SimpleNamespace(
        seed_metadata_available=True, seed_geometry_available=True,
        reference_path_available=True, station_map_available=False,
        reviewed_model_available=True, accepted_model_available=True,
    )
    track_ctx = SimpleNamespace(
        identity=identity, availability=availability, source="contexts",
        geometry=None, alignment=None,
    )
    verdict = TrackReadinessResult(
        state=TrackReadiness.READY_APPROVED,
        location_id=identity.track_location_id, layout_id=identity.layout_id,
        confidence="high", provenance="approved reference path",
        next_action="Load or build the race setup.",
    )
    state = build_home_dashboard_state(track_context=track_ctx, track_readiness=verdict)
    card = state.card(CARD_TRACK)
    assert card is not None
    assert card.status == HomeDashboardStatus.READY
    assert not any(w.kind == "blocker" for w in card.warnings)


def test_command_centre_card_missing_when_no_assets():
    from types import SimpleNamespace
    from ui.home_dashboard_vm import (
        build_home_dashboard_state, CARD_TRACK, HomeDashboardStatus,
    )
    from data.track_readiness import TrackReadinessResult, TrackReadiness

    identity = SimpleNamespace(
        track_location_id="x", layout_id="x__y",
        track_display_name="X", layout_display_name="Y", is_complete=True,
    )
    availability = SimpleNamespace()
    track_ctx = SimpleNamespace(identity=identity, availability=availability,
                                source="contexts", geometry=None, alignment=None)
    verdict = TrackReadinessResult(
        state=TrackReadiness.MISSING_ASSET, location_id="x", layout_id="x__y",
        next_action="Open Track Modelling to build the track model.",
        blockers=("No track model assets found for this layout.",),
    )
    state = build_home_dashboard_state(track_context=track_ctx, track_readiness=verdict)
    card = state.card(CARD_TRACK)
    assert card.status == HomeDashboardStatus.MISSING
