"""Detection thresholds — the app's, not the game's.

Every one of these is restated in `derived.thresholds` on each export, so that
retuning a detector reads as a change in the detector rather than a change in
the car. Nothing here is measured; it is all a choice, and the export says so.

Changing a number in this file changes what past sessions would have reported.
Bump `DETECTOR_VERSION` when you do, so two exports are never silently
incomparable.
"""
from __future__ import annotations

DETECTOR_VERSION = 2

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

# A flag has to fire on this share of the counted laps before it describes the
# corner. Union across laps made every corner carry every flag once enough laps
# were run, which reads as seven findings and is none: `flagLaps` keeps the
# one-offs visible as one-offs.
FLAG_MIN_SHARE = 0.25

# --- fresh tyres -----------------------------------------------------------
#
# **GT7 does not fit every set at the same temperature.** That is a correction.
# The 11 Aug Monza captures contain six runs and three of them - on Racing
# Soft, Racing Medium and Racing Hard - open at exactly 70.0 C on all four
# corners, which is where the constant below came from and why it was written
# down as measured. Widening the search to all 132 recorded laps says
# otherwise: sets are fitted anywhere from **60.0 to 70.0 C**, and the figure
# tracks the hour. The 14 Aug pit stop fitted at 60.0 C at 18:50 game time in
# a session that started at 15:56 and opened at 72 C.
#
# So 70.0 is the **highest** fitting temperature observed, not the fitting
# temperature. Anything gated on it as an absolute rejects a genuinely fresh
# set fitted on a cool evening - which is exactly what happened to the only
# real tyre change in the capture set, where `fresh_by_temperature` returned
# "cannot tell" for a set that had just been bolted on.
#
# The discriminating signal is **not** the absolute value, it is that all four
# corners read the same. A set that has been driven carries corner-to-corner
# asymmetry within a lap and keeps it.
#
# Stronger still, where it is available: the moment of fitting is visible as a
# one-frame step in the stream, and `telemetry/pit_detect` finds it outright.
# This band is the fallback for a run whose stop was not captured.
FRESH_TYRE_TEMP_C = 70.0
FRESH_TYRE_TEMP_MIN_C = 60.0
# Corner-to-corner spread a set that has never turned a wheel stays inside.
FRESH_TYRE_SPREAD_C = 0.3
# How far below the fitting temperature a fresh set may have cooled while
# waiting in the box and still be recognised. Below this the reading cannot
# tell a fresh set from one left long enough to equalise, and it says so
# rather than guessing.
FRESH_TYRE_COOLING_C = 8.0
# Above this the car is moving and the frame is no longer a reading of the set
# as fitted.
FRESH_TYRE_MAX_SPEED_KPH = 5.0
# Measured at this GT7 version. The physics and tyre model have been rewritten
# twice in two updates, so the figure travels with the version it was taken
# under and is re-measured rather than assumed after the next one.
FRESH_TYRE_MEASURED_AT = ("GT7 1.70, 132 recorded laps across Monza, Yas Marina "
                          "and Watkins Glen, 11-14 Aug 2026")

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
        "flagMinShareOfLaps": FLAG_MIN_SHARE,
        "freshTyreTempC": FRESH_TYRE_TEMP_C,
        "freshTyreTempMinC": FRESH_TYRE_TEMP_MIN_C,
        "freshTyreTempSource": (
            f"measured in-house - {FRESH_TYRE_MEASURED_AT}. GT7 fits a set "
            f"anywhere in this band depending on the hour; the four corners "
            f"reading the same is the discriminator, not the level."),
        "freshTyreSpreadC": FRESH_TYRE_SPREAD_C,
        "detectorVersion": DETECTOR_VERSION,
    }
