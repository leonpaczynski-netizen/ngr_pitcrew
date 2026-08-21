"""Detection thresholds — the app's, not the game's.

Every one of these is restated in `derived.thresholds` on each export, so that
retuning a detector reads as a change in the detector rather than a change in
the car. Nothing here is measured; it is all a choice, and the export says so.

Changing a number in this file changes what past sessions would have reported.
Bump `DETECTOR_VERSION` when you do, so two exports are never silently
incomparable.
"""
from __future__ import annotations

# 3: the corner detectors were rebuilt. `wheelspin` states which wheels it
# tested, `countersteer` requires the reversal to go against the corner's own
# direction, `trail-brake-instability` requires the two to coincide,
# `understeer-mid` gained magnitude thresholds, and the bottoming reference is
# now held out of the corner windows. A v2 export and a v3 export of the same
# session do not carry the same flags, and neither is wrong.
DETECTOR_VERSION = 3

# --- corner flags (EXPORT-CONTRACT.md 7.1) ---------------------------------

# Driven-wheel surface speed exceeding vehicle speed, under throttle.
WHEELSPIN_PCT = 8
# Wheel surface speed below vehicle speed, under brake.
LOCKUP_PCT = 15
# Steering sign reversal of this size counts as a correction.
COUNTERSTEER_DEG = 10
COUNTERSTEER_WINDOW_MS = 300
# **A reversal alone is not a correction.** An auto-segmented corner is one
# speed minimum, so a chicane is a single window and its left-right transition
# clears a 10 deg reversal by construction: at Monza the bare test marked the
# three chicanes on 82, 76 and 75 laps of 91 and almost nothing else. Two
# further conditions, both of them saying "this was a dab, not the corner's
# second direction":
#   * the reversal has to start from the corner's own direction, taken as the
#     sign of the steering at the apex frame, and
#   * the opposite lock has to be transient - either the wheel comes back to
#     the corner's own direction inside the window, or the opposite lock never
#     reaches this fraction of the lock already used in the corner's direction.
# Measured over 923 real corner windows: 31.7% of windows as built, 21.8% with
# the direction test alone, 5.9% with both.
COUNTERSTEER_RETURN_FRACTION = 0.5
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
# The bottoming reference is taken from frames **held out of every corner
# window** - straight-line running only. Taking it from the same frames the
# flag is tested against made the deepest corner flag by construction, and one
# session-wide minimum from the deepest corner silenced every other corner:
# measured, `bottoming` fired on 0 of 545 Monza windows. Straight-line means
# outside the windows and, where steering is available, under this much lock.
BOTTOMING_REF_MAX_STEER_PCT = 5.0

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

# How far back of the apex to look for the start of braking. Braking begins on
# the straight, outside the corner window, so a brake point measured only
# inside the window is systematically short - which matters most for a driver
# who brakes deep. Anchored on the apex rather than the window, because that is
# what `brakePointM` is measured from: anchoring it on the window let the
# reported figure exceed the lookback it declares.
BRAKE_LOOKBACK_M = 500.0

# --- drivetrain ------------------------------------------------------------
#
# Contract 7.1 defines `wheelspin` on the **driven** wheels. GT7 broadcasts no
# drivetrain channel in any packet format, so the app cannot read it off the
# stream - it has to be told. Where it has not been told, the detector falls
# back to all four wheels and **says so in `derived.thresholds`**: the silent
# substitution was the defect, not the substitution. The league's three cars
# are MR, FR and MR, i.e. rear-driven, so `rwd` is the answer whenever anyone
# gets round to recording it.
ALL_WHEELS = ("fl", "fr", "rl", "rr")
_RWD = ("rl", "rr")
_FWD = ("fl", "fr")
# **Both vocabularies, because the driver is reading GT7's.** The game states
# a car's layout as FF/FR/MR/RR/4WD - engine position and driven axle in one
# token - and that is what the Event screen offers, because asking him to
# translate his own car into `rwd` is asking him to make a mistake. The drive
# type is what the detector needs, so the layout codes resolve to it here.
DRIVEN_WHEELS = {
    "rwd": _RWD,
    "fwd": _FWD,
    "awd": ALL_WHEELS,
    "fr": _RWD,          # front engine, rear drive
    "mr": _RWD,          # mid engine, rear drive - the Huracan GT3
    "rr": _RWD,          # rear engine, rear drive - the 911 RSR
    "ff": _FWD,
    "4wd": ALL_WHEELS,
    "awd4": ALL_WHEELS,
}


def wheelspin_wheels(drivetrain: str | None) -> tuple[str, ...]:
    """Which wheels `wheelspin` is tested on."""
    if drivetrain is None:
        return ALL_WHEELS
    return DRIVEN_WHEELS.get(drivetrain.strip().lower(), ALL_WHEELS)


def wheelspin_wheels_note(drivetrain: str | None,
                          source: str | None = None) -> str:
    """Which wheels were watched, and **on whose authority.**

    GT7 broadcasts no drivetrain channel, so the value is either declared by
    the driver or looked up in the car catalogue. Those are different claims
    and CLAUDE.md §4.5 says so: the catalogue is a property of the model of car
    and cannot know about an engine swap, which this league's open tuning
    allows. So a catalogue answer says it is a catalogue answer, and a
    declaration still overrides it.
    """
    wheels = wheelspin_wheels(drivetrain)
    if (drivetrain is None
            or drivetrain.strip().lower() not in DRIVEN_WHEELS):
        return ("all four - GT7 broadcasts no drivetrain channel and none was "
                "declared, so the contract's driven-wheel test could not be "
                "applied. A front wheel light over a kerb under throttle reads "
                "as wheelspin on a rear-driven car")
    how = {
        "catalogue": ("from the car catalogue, not declared - correct for the "
                      "model as shipped, and blind to an engine swap"),
        "declared": "declared",
    }.get(source or "declared", "declared")
    return (f"{drivetrain.strip().upper()}, {how} - driven wheels "
            f"({', '.join(wheels)})")


# --- understeer-mid --------------------------------------------------------
#
# The v2 detector was "steering angle rising while yaw rate is flat or falling"
# with no magnitude on either side, and its constants were hardcoded where the
# export could never see them. On real laps it fired on **49.4% of 923 corner
# windows and all 25 corner objects** - and hardwiring the yaw term to True
# still fired on ~95%, so the steering term alone could not fail. A flag on
# every corner is not a finding.
#
# Rebuilt with a magnitude on each side. The yaw side needs an expectation to
# be short *of*, and the kinematic (Ackermann) one over-predicts a race car at
# the limit by about five times, because at the limit the steer angle is mostly
# tyre slip angle rather than path curvature. So the expectation is the
# kinematic form carrying a **measured** gain:
#
#     expected_yaw_rad_s = GAIN * speed_ms * (steering_deg / 180) / wheelbase_m
#
# GAIN is the median of `|yaw| * wheelbase / (speed_ms * steering_deg/180)`
# over 154,714 real cornering frames - 0.116, with p10 0.072 and p90 0.182. It
# is a **calibration of this driver in these cars**, not a physical constant,
# which is why it is declared on every export rather than buried here.
UNDERSTEER_YAW_GAIN = 0.116
UNDERSTEER_YAW_GAIN_SOURCE = (
    "median achieved yaw against the kinematic expectation over 154,714 "
    "cornering frames, 132 laps, Monza / Yas Marina / Watkins Glen, Aug 2026")
# How far below that expectation the car has to be rotating. 0.60 sits between
# the p10 and p25 of normal cornering, so turn-in lag alone does not reach it.
UNDERSTEER_YAW_DEFICIT = 0.60
# And the driver has to be *adding* lock while it happens. His median steering
# rate through a corner is 4-13 deg/s, so 20 deg/s is a deliberate input.
UNDERSTEER_STEER_RISE_DEG_S = 20.0
# Held for this long, which is longer than turn-in lag.
UNDERSTEER_MIN_MS = 100
# Below these the model is noise: no useful curvature, and yaw indistinguishable
# from reconstruction error.
UNDERSTEER_MIN_SPEED_KPH = 40.0
UNDERSTEER_MIN_STEER_DEG = 15.0
# Used when the caller does not know the car's wheelbase. `packet.wheelbase_m`
# carries the real one in the '~' and 'C' formats but the recorder does not
# store it per frame, so this travels with the export as the assumption it is.
DEFAULT_WHEELBASE_M = 2.516

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


def as_export(drivetrain: str | None = None, *,
              drivetrain_source: str | None = None,
              wheelbase_m: float | None = None) -> dict:
    """The `derived.thresholds` object.

    **Every constant that gates an emitted flag belongs here.** Contract 7.1
    asks for the thresholds to be restated on every export so that retuning a
    detector reads as a change in the detector rather than a change in the car,
    and twelve of them were missing - including the whole bottoming rule and
    the understeer rule, which did not exist in this file at all. A reader who
    cannot see the rule cannot tell a quieter flag from a calmer car.
    """
    return {
        "wheelspinPct": WHEELSPIN_PCT,
        # Contract 7.1 says driven wheels. Whether that is what happened
        # depends on whether anyone told the app what drives this car.
        "wheelspinWheels": wheelspin_wheels_note(drivetrain,
                                                 drivetrain_source),
        "lockupPct": LOCKUP_PCT,
        "countersteerDeg": COUNTERSTEER_DEG,
        "countersteerWindowMs": COUNTERSTEER_WINDOW_MS,
        "countersteerRule": (
            "a steering sign reversal of countersteerDeg inside "
            f"{COUNTERSTEER_WINDOW_MS} ms, starting from the corner's own "
            "direction (the sign of the steering at the apex frame), and "
            "transient - either the wheel returns to that direction inside "
            "the window, or the opposite lock stays under "
            f"{COUNTERSTEER_RETURN_FRACTION:.0%} of the lock used in it. "
            "Without the last two conditions the flag marks chicane "
            "transitions, which are one window under an auto-segment model"),
        "countersteerReturnFraction": COUNTERSTEER_RETURN_FRACTION,
        "trailBrakeSteerPct": TRAIL_BRAKE_STEER_PCT,
        "trailBrakeMinBrakePct": TRAIL_BRAKE_MIN_BRAKE_PCT,
        "trailBrakeInstabilityRule": (
            "the countersteer and the trail braking must be the same moment - "
            "one of the reversal's own frames has to be inside the trail-brake "
            "window. Two whole-window tests ANDed together made the flag an "
            "alias for countersteer on a driver who trail-brakes by design"),
        "kerbStrikeMm": KERB_STRIKE_MM,
        "kerbStrikeWindowMs": KERB_STRIKE_WINDOW_MS,
        "bottomingMinMs": BOTTOMING_MIN_MS,
        "bottomingBandMm": BOTTOMING_BAND_MM,
        "bottomingRefRule": (
            "lowest suspension height on straight-line frames - outside every "
            "corner window and under "
            f"{BOTTOMING_REF_MAX_STEER_PCT:g}% of lock - taken per setup "
            "sheet, because ride height and spring rate are setup values. "
            "Bottoming is inferred, never measured: GT7 reports absolute "
            "height, not travel remaining"),
        "bottomingRefMaxSteerPct": BOTTOMING_REF_MAX_STEER_PCT,
        "understeerYawGain": UNDERSTEER_YAW_GAIN,
        "understeerYawGainSource": UNDERSTEER_YAW_GAIN_SOURCE,
        "understeerYawDeficit": UNDERSTEER_YAW_DEFICIT,
        "understeerSteerRiseDegS": UNDERSTEER_STEER_RISE_DEG_S,
        "understeerMinMs": UNDERSTEER_MIN_MS,
        "understeerRule": (
            "steering rising at understeerSteerRiseDegS or more while the car "
            "rotates at less than understeerYawDeficit of "
            "understeerYawGain * speed * (steeringDeg/180) / wheelbase, held "
            f"for understeerMinMs. Above {UNDERSTEER_MIN_SPEED_KPH:g} km/h and "
            f"{UNDERSTEER_MIN_STEER_DEG:g} deg of steering"),
        "understeerWheelbaseM": wheelbase_m or DEFAULT_WHEELBASE_M,
        "understeerWheelbaseSource": (
            "measured on this car" if wheelbase_m else
            "assumed - this session predates the wheelbase column, so the "
            f"default of {DEFAULT_WHEELBASE_M:g} m is in use and it is the "
            "Porsche RSR's, not this car's"),
        "throttleOnPct": THROTTLE_ON_PCT,
        "brakeOnPct": BRAKE_ON_PCT,
        "brakeLookbackM": BRAKE_LOOKBACK_M,
        "onTrackSurfaces": sorted(ON_TRACK_SURFACES),
        "apexDefinition": APEX_DEFINITION,
        "cornerProminenceKph": CORNER_PROMINENCE_KPH,
        "cornerMinSeparationM": CORNER_MIN_SEPARATION_M,
        "speedSmoothingMs": SPEED_SMOOTHING_MS,
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
