"""The shared centreline geometry core — signed curvature and heading.

These lock in the properties the whole track model now depends on: a straight has zero
curvature, a constant-radius arc has curvature 1/R, the sign flips between a left and a
right turn, and the apex sits at the curvature peak (phase-preserving). Pure geometry —
no speed, no yaw, in the magnitude.
"""

from __future__ import annotations

import math

import pytest

from data.track_geometry_core import (
    compute_headings, compute_signed_curvature, compute_geometry,
    yaw_curvature_discrepancy,
)


def _arc(radius: float, sweep_rad: float, n: int, *, sign: float = 1.0, spacing_deg=None):
    """A constant-radius arc of `n` XZ points, centred at the origin's right.

    sign=+1 turns one way, sign=-1 the other. Points are ~evenly spaced in angle.
    """
    pts = []
    for i in range(n):
        a = sweep_rad * i / (n - 1)
        # Centre at (radius, 0); trace the circle. Sign flips turn direction.
        x = radius * math.sin(a) * sign
        z = radius * (1.0 - math.cos(a))
        pts.append((x, z))
    return pts


def test_straight_line_has_zero_curvature():
    pts = [(0.0, float(z)) for z in range(0, 100)]   # due +z
    curv = compute_signed_curvature(pts)
    # Interior points are dead straight.
    assert max(abs(c) for c in curv[5:-5]) < 1e-6


def test_constant_radius_arc_has_curvature_one_over_r():
    R = 50.0
    pts = _arc(R, math.pi / 2, 200)            # quarter circle, ~1 m spacing
    curv = compute_signed_curvature(pts)
    interior = [abs(c) for c in curv[20:-20]]
    mean_k = sum(interior) / len(interior)
    assert mean_k == pytest.approx(1.0 / R, rel=0.15)   # ~0.02 rad/m


def test_left_and_right_turns_have_opposite_signs():
    R = 40.0
    left = compute_signed_curvature(_arc(R, math.pi / 2, 200, sign=1.0))
    right = compute_signed_curvature(_arc(R, math.pi / 2, 200, sign=-1.0))
    lmid = left[len(left) // 2]
    rmid = right[len(right) // 2]
    assert lmid * rmid < 0                      # opposite handedness
    assert abs(lmid) == pytest.approx(abs(rmid), rel=0.2)


def test_tighter_radius_gives_higher_curvature():
    tight = compute_signed_curvature(_arc(20.0, math.pi / 2, 200))
    wide = compute_signed_curvature(_arc(120.0, math.pi / 2, 200))
    kt = max(abs(c) for c in tight[20:-20])
    kw = max(abs(c) for c in wide[20:-20])
    assert kt > kw


def _path_from_curvature(kappas, ds: float = 1.0):
    """Integrate a curvature profile (rad/m) into an XZ path at `ds` spacing.

    heading θ = ∫κ ds, position from (dx,dz)=(sinθ,cosθ)ds — the exact inverse of the
    core's ``atan2(dx, dz)`` heading, so the recovered curvature should match the input.
    """
    theta = 0.0
    x = z = 0.0
    pts = [(x, z)]
    for k in kappas:
        theta += k * ds
        x += math.sin(theta) * ds
        z += math.cos(theta) * ds
        pts.append((x, z))
    return pts


def test_curvature_peak_lands_at_the_apex_phase_preserving():
    # A single corner whose curvature peaks at a KNOWN station. The recovered peak must
    # sit at that station, not smeared downstream (the old trailing box-car bug).
    n = 200
    center = 100
    width = 18.0
    kappas = [0.03 * math.exp(-((i - center) / width) ** 2) for i in range(n)]
    pts = _path_from_curvature(kappas, ds=1.0)
    curv = compute_signed_curvature(pts)
    peak_i = max(range(len(curv)), key=lambda i: abs(curv[i]))
    assert abs(peak_i - center) <= 3          # apex within 3 m of ground truth
    assert curv[peak_i] > 0                    # positive kappa -> positive curvature


def test_compute_geometry_returns_headings_and_curvature_same_length():
    pts = _arc(50.0, math.pi / 3, 80)
    headings, curv = compute_geometry(pts)
    assert len(headings) == len(curv) == len(pts)


def test_short_paths_do_not_raise():
    assert compute_signed_curvature([]) == []
    assert compute_signed_curvature([(0.0, 0.0)]) == [0.0]
    assert compute_signed_curvature([(0.0, 0.0), (0.0, 1.0)]) == [0.0, 0.0]


def test_yaw_discrepancy_is_a_crosscheck_not_a_blend():
    # Geometry says straight (curv 0); yaw says turning. The discrepancy is reported,
    # but nothing here changes the geometric curvature itself.
    curv = [0.0, 0.0, 0.0]
    yaw = [0.5, 0.5, 0.5]           # rad/s
    spd = [25.0, 25.0, 25.0]        # m/s -> yaw curvature 0.02
    d = yaw_curvature_discrepancy(curv, yaw, spd)
    assert d == pytest.approx(0.02, rel=0.01)


def test_yaw_discrepancy_none_without_usable_samples():
    assert yaw_curvature_discrepancy([0.0], [None], [None]) is None
    assert yaw_curvature_discrepancy([0.0], [0.5], [1.0]) is None   # speed below threshold
