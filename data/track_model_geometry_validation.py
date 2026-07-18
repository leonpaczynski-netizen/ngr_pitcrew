"""Deterministic track-model geometry validation (pure, Qt-free).

UAT Finding 4, Step 5 (Validate). The existing alignment layer checks lap-length
delta and corner-position match against the seed, but the overhaul brief calls
out gaps: no explicit closed-path/loop-closure check, no monotonic corner
ordering / duplicate-segment check, and full-lap coverage was only inferred
indirectly. This module fills those, and — importantly — turns geometric
uncertainty into a lowered confidence that **blocks corner-specific authoring**
so a shaky model never drives corner identity (required behaviour: track-model
uncertainty must lower confidence and gate corner-specific authoring).

Pure math over a lap's ordered (x, z) points (metres); no Qt, no I/O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class GeometryValidationResult:
    passed: bool                      # no blockers
    confidence: str                   # "high" | "medium" | "low" | "none"
    coverage_ok: bool
    closed_path_ok: bool
    lap_length_ok: bool
    ordering_ok: bool
    duplicates_ok: bool
    measured_lap_length_m: float = 0.0
    max_gap_m: float = 0.0
    closure_gap_m: float = 0.0
    issues: Tuple[str, ...] = ()      # non-blocking concerns (lower confidence)
    blockers: Tuple[str, ...] = ()    # must-fix before validation passes
    corner_authoring_allowed: bool = False

    @property
    def next_action(self) -> str:
        if self.blockers:
            return self.blockers[0]
        if self.issues:
            return self.issues[0]
        return "Geometry validated."


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def validate_track_geometry(
    points: Sequence[Sequence[float]],
    *,
    turn_numbers: Optional[Sequence[int]] = None,
    expected_lap_length_m: Optional[float] = None,
    station_gap_tolerance_m: float = 25.0,
    closure_tolerance_m: float = 30.0,
    lap_length_tolerance_pct: float = 0.15,
    min_points: int = 20,
    min_plausible_lap_m: float = 400.0,
    max_plausible_lap_m: float = 30000.0,
) -> GeometryValidationResult:
    """Validate a lap's ordered (x, z) points.

    Checks: full-lap coverage (no oversized gaps), closed path (start≈end),
    plausible + expected lap length, monotonic corner ordering, and duplicate /
    overlapping segments. Returns a confidence and whether corner-specific
    authoring is trustworthy.
    """
    pts = [(float(p[0]), float(p[1])) for p in (points or [])]
    if len(pts) < min_points:
        return GeometryValidationResult(
            passed=False, confidence="none",
            coverage_ok=False, closed_path_ok=False, lap_length_ok=False,
            ordering_ok=False, duplicates_ok=False,
            blockers=(f"Not enough points to validate ({len(pts)} < {min_points}).",),
            corner_authoring_allowed=False,
        )

    issues: list[str] = []
    blockers: list[str] = []

    # --- coverage: largest gap between consecutive points -----------------
    seg_lengths = [_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    max_gap = max(seg_lengths) if seg_lengths else 0.0
    coverage_ok = max_gap <= station_gap_tolerance_m
    if not coverage_ok:
        blockers.append(
            f"Full-lap coverage gap of {max_gap:.0f} m exceeds "
            f"{station_gap_tolerance_m:.0f} m — capture more clean laps.")

    # --- closed path: start ≈ end -----------------------------------------
    closure_gap = _dist(pts[0], pts[-1])
    closed_path_ok = closure_gap <= closure_tolerance_m
    if not closed_path_ok:
        blockers.append(
            f"Path is not closed — start and end are {closure_gap:.0f} m apart "
            f"(tolerance {closure_tolerance_m:.0f} m).")

    # --- lap length -------------------------------------------------------
    measured = sum(seg_lengths) + closure_gap
    plausible = min_plausible_lap_m <= measured <= max_plausible_lap_m
    lap_length_ok = plausible
    if not plausible:
        blockers.append(
            f"Implausible lap length {measured:.0f} m.")
    elif expected_lap_length_m and expected_lap_length_m > 0:
        delta = abs(measured - expected_lap_length_m) / expected_lap_length_m
        if delta > lap_length_tolerance_pct:
            lap_length_ok = False
            issues.append(
                f"Lap length {measured:.0f} m differs from expected "
                f"{expected_lap_length_m:.0f} m by {delta*100:.0f}%.")

    # --- corner ordering + duplicates -------------------------------------
    ordering_ok = True
    duplicates_ok = True
    if turn_numbers:
        nums = [int(t) for t in turn_numbers if t is not None and int(t) > 0]
        if nums:
            # Duplicates: a turn number appearing more than once.
            seen = set()
            dupes = set()
            for n in nums:
                if n in seen:
                    dupes.add(n)
                seen.add(n)
            if dupes:
                duplicates_ok = False
                issues.append(
                    "Duplicate/overlapping corner numbers: "
                    + ", ".join(f"T{n}" for n in sorted(dupes)) + ".")
            # Ordering: the ordered turn numbers should be non-decreasing.
            if nums != sorted(nums):
                ordering_ok = False
                issues.append(
                    "Corner numbering is out of order along the lap.")

    passed = not blockers
    # Confidence: high only when everything is clean; degrade with each concern.
    if blockers:
        confidence = "low"
    elif issues:
        confidence = "medium"
    else:
        confidence = "high"

    # Corner-specific authoring is only trustworthy when corner identity is
    # sound: coverage + ordering + no duplicates, and the model validated.
    corner_authoring_allowed = (
        passed and ordering_ok and duplicates_ok and coverage_ok
        and confidence in ("high", "medium")
    )

    return GeometryValidationResult(
        passed=passed,
        confidence=confidence,
        coverage_ok=coverage_ok,
        closed_path_ok=closed_path_ok,
        lap_length_ok=lap_length_ok,
        ordering_ok=ordering_ok,
        duplicates_ok=duplicates_ok,
        measured_lap_length_m=measured,
        max_gap_m=max_gap,
        closure_gap_m=closure_gap,
        issues=tuple(issues),
        blockers=tuple(blockers),
        corner_authoring_allowed=corner_authoring_allowed,
    )
