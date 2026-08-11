"""Detection thresholds — the app's, not the game's.

Every one of these is restated in `derived.thresholds` on each export, so that
retuning a detector reads as a change in the detector rather than a change in
the car. Nothing here is measured; it is all a choice, and the export says so.

Changing a number in this file changes what past sessions would have reported.
Bump `DETECTOR_VERSION` when you do, so two exports are never silently
incomparable.
"""
from __future__ import annotations

DETECTOR_VERSION = 1

# --- corner flags (EXPORT-CONTRACT.md 7.1) ---------------------------------

# Driven-wheel surface speed exceeding vehicle speed, under throttle.
WHEELSPIN_PCT = 8
# Wheel surface speed below vehicle speed, under brake.
LOCKUP_PCT = 15
# Steering sign reversal of this size counts as a correction.
COUNTERSTEER_DEG = 10
COUNTERSTEER_WINDOW_MS = 300
# Steering beyond this fraction of full lock, with the brake still applied,
# is the trail-braking window.
TRAIL_BRAKE_STEER_PCT = 15
TRAIL_BRAKE_MIN_BRAKE_PCT = 5
# A suspension height step this large, this fast, is a kerb strike.
KERB_STRIKE_MM = 20
KERB_STRIKE_WINDOW_MS = 100
# Sustained time within the bottoming reference band before it is a finding.
BOTTOMING_MIN_MS = 50
BOTTOMING_BAND_MM = 3.0

THROTTLE_ON_PCT = 10          # throttle considered "on" above this
BRAKE_ON_PCT = 5              # brake considered "applied" above this

APEX_DEFINITION = "minimum speed point within the corner window"

# --- corner detection ------------------------------------------------------

# A speed minimum is a corner only if the car accelerates away from it by at
# least this much on both sides. Below this it is a lift, not a corner.
CORNER_PROMINENCE_KPH = 15.0
# Two minima closer than this are the same corner seen twice.
CORNER_MIN_SEPARATION_M = 80.0
# Speed is smoothed over roughly a quarter second before minima are sought,
# so that a single noisy frame cannot invent a corner.
SPEED_SMOOTHING_MS = 250.0

# --- surfaces --------------------------------------------------------------

ON_TRACK_SURFACES = frozenset({"T", "C"})   # tarmac and kerb


def as_export() -> dict:
    """The `derived.thresholds` object."""
    return {
        "wheelspinPct": WHEELSPIN_PCT,
        "lockupPct": LOCKUP_PCT,
        "countersteerDeg": COUNTERSTEER_DEG,
        "trailBrakeSteerPct": TRAIL_BRAKE_STEER_PCT,
        "kerbStrikeMm": KERB_STRIKE_MM,
        "apexDefinition": APEX_DEFINITION,
        "cornerProminenceKph": CORNER_PROMINENCE_KPH,
        "detectorVersion": DETECTOR_VERSION,
    }
