"""Sprint 4 — discrete wheel-slip episodes (telemetry/slip_events.py).

Includes the spec's cross-lap fixtures that belong at the episode layer:
  Fixture C — one continuous slide represented by many packets → 1 episode.
  Fixture D — rear-wheel slip under braking → lockup, NOT acceleration wheelspin.
Plus suppression (shift/downshift transient, kerb unload, airborne, noise),
hysteresis, and merging.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from telemetry.slip_events import (
    extract_slip_episodes, evidence_episodes, EpisodeConfig,
)

_TWO_PI = 2.0 * math.pi
_RADIUS = 0.33


def _rps_for_ground(speed_kmh: float) -> float:
    return (speed_kmh / 3.6) / (_RADIUS * _TWO_PI)


def _frame(t_ms, *, speed_kmh=100.0, throttle=0.0, brake=0.0, gear=4,
           rear_ratio=1.0, front_ratio=1.0, suspension=0.0, road_plane_y=1.0,
           angvel_z=0.0, road_distance=None):
    """Build a duck-typed telemetry frame.

    rear_ratio/front_ratio scale that axle's wheel speed vs the ground
    (>1 spinning, <1 locked).
    """
    base = _rps_for_ground(speed_kmh)
    rps = (base * front_ratio, base * front_ratio, base * rear_ratio, base * rear_ratio)
    rad = (_RADIUS,) * 4
    return SimpleNamespace(
        elapsed_ms=t_ms, speed_kmh=speed_kmh, throttle=throttle, brake=brake,
        gear=gear, rpm=6000.0,
        road_distance=(road_distance if road_distance is not None else t_ms * 0.03),
        wheel_rps=rps, tyre_radius=rad,
        suspension=(suspension,) * 4, angvel_z=angvel_z, road_plane_y=road_plane_y,
    )


def _spin_frames(n, *, start_ms=0, step=10, gear=4):
    # rear driven axle spinning at 1.5x ground under full throttle
    return [_frame(start_ms + i * step, throttle=1.0, brake=0.0, gear=gear,
                   rear_ratio=1.5) for i in range(n)]


# --------------------------------------------------------------------------- #
# Fixture C — one slide = one episode
# --------------------------------------------------------------------------- #
def test_fixture_c_one_continuous_slide_is_one_episode():
    frames = _spin_frames(40, step=10)   # 40 samples over ~400 ms — one slide
    eps = extract_slip_episodes(frames, drivetrain="FR")
    spins = [e for e in eps if e.kind == "wheelspin"]
    assert len(spins) == 1, f"expected 1 episode, got {len(spins)}"
    ep = spins[0]
    assert ep.sample_count >= 30
    assert ep.duration_s >= 0.3
    assert ep.is_evidence
    assert ep.axle == "rear"


# --------------------------------------------------------------------------- #
# Fixture D — brake-side rear slip is lockup, not wheelspin
# --------------------------------------------------------------------------- #
def test_fixture_d_braking_rear_slip_is_lockup_not_wheelspin():
    # Under braking the rear wheels drop below ground speed (locking), no throttle.
    frames = [_frame(i * 10, throttle=0.0, brake=0.8, gear=3, rear_ratio=0.3)
              for i in range(20)]
    eps = extract_slip_episodes(frames, drivetrain="FR")
    assert eps, "expected at least one episode"
    assert all(e.kind == "lockup" for e in eps)
    assert not any(e.kind == "wheelspin" for e in eps)
    assert eps[0].axle == "rear"


def test_downshift_transient_lockup_is_suppressed():
    # A brief rear-speed drop DURING a downshift (gear 4 -> 3) is a driveline
    # transient, not a braking lockup: suppressed from evidence.
    frames = [_frame(0, brake=0.5, gear=4, rear_ratio=0.3),
              _frame(10, brake=0.5, gear=4, rear_ratio=0.3),
              _frame(20, brake=0.5, gear=3, rear_ratio=0.3)]
    eps = extract_slip_episodes(frames, drivetrain="FR")
    assert eps
    ep = eps[0]
    assert ep.subtype == "downshift_transient"
    assert ep.exclusion_reason == "downshift_transient"
    assert not ep.is_evidence


def test_kerb_unload_spin_is_suppressed():
    # A short spin coinciding with a big suspension deflection = kerb unloading.
    frames = [_frame(0, throttle=1.0, gear=3, rear_ratio=1.6, suspension=0.06),
              _frame(10, throttle=1.0, gear=3, rear_ratio=1.6, suspension=0.06)]
    eps = extract_slip_episodes(frames, drivetrain="FR")
    assert eps
    assert eps[0].exclusion_reason == "kerb_unload"
    assert not eps[0].is_evidence


def test_airborne_wheel_is_suppressed():
    frames = [_frame(i * 10, throttle=1.0, gear=3, rear_ratio=1.6, road_plane_y=0.5)
              for i in range(6)]
    eps = extract_slip_episodes(frames, drivetrain="FR")
    assert eps
    assert eps[0].exclusion_reason == "airborne"
    assert not eps[0].is_evidence


def test_two_separate_spins_are_two_episodes():
    frames = _spin_frames(10, start_ms=0, step=10)  # 0-90ms
    # long clean gap, then another spin
    clean = [_frame(200 + i * 10, throttle=0.2, brake=0.0, rear_ratio=1.0) for i in range(20)]
    frames += clean
    frames += _spin_frames(10, start_ms=500, step=10)
    eps = [e for e in extract_slip_episodes(frames, drivetrain="FR") if e.kind == "wheelspin"]
    assert len(eps) == 2


def test_evidence_filter_excludes_suppressed():
    frames = [_frame(i * 10, throttle=1.0, gear=3, rear_ratio=1.6, road_plane_y=0.5)
              for i in range(6)]
    eps = extract_slip_episodes(frames, drivetrain="FR")
    assert evidence_episodes(eps) == []


def test_segment_resolver_is_applied():
    frames = _spin_frames(10, step=10)
    eps = extract_slip_episodes(
        frames, drivetrain="FR",
        segment_resolver=lambda d, s, t, b: ("T3", "exit"))
    assert eps[0].segment_id == "T3"
    assert eps[0].corner_phase == "exit"


def test_empty_frames_returns_empty():
    assert extract_slip_episodes([], drivetrain="FR") == []


def test_deterministic_repeatable():
    frames = _spin_frames(12)
    a = extract_slip_episodes(frames, drivetrain="FR")
    b = extract_slip_episodes(frames, drivetrain="FR")
    assert a == b


def test_fwd_car_front_axle_spin():
    frames = [_frame(i * 10, throttle=1.0, gear=3, front_ratio=1.6, rear_ratio=1.0)
              for i in range(6)]
    eps = extract_slip_episodes(frames, drivetrain="FF")
    assert eps and eps[0].kind == "wheelspin"
    assert eps[0].axle == "front"
