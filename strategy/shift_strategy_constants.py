"""Adaptive Per-Gear Shift Strategy — named algorithm constants (Phase 1).

All magic numbers live here.  Every constant has a name and a comment
explaining WHAT it represents and WHY the value was chosen.  No other
module may embed a bare numeric literal for this algorithm.

DOCTRINE  Deterministic, offline, pure.  No Qt, no DB, no network.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Version pin — frozen by golden vectors in test_shift_strategy_golden.py.
# Changing this string invalidates all stored fingerprints intentionally.
# ---------------------------------------------------------------------------
SHIFT_STRATEGY_VERSION = "shift_strategy_v1"

# ---------------------------------------------------------------------------
# Timing model
# ---------------------------------------------------------------------------

# Upshift interruption penalty (seconds).  The mechanical sequence of lifting
# throttle, declutching, selecting the next gear, and re-applying throttle on a
# GT car with sequential transmission costs roughly 100 ms of "dead time" where
# no power reaches the wheels.  0.10 s is a conservative mid-field estimate;
# an H-pattern gearbox would be 0.20 s.  Exposed as a constant so a future
# telemetry-derived calibration can replace it.
SHIFT_LOSS_S: float = 0.10

# Relative torque-window denominator used in the time-in-gear estimate.
# We compute elapsed-time proxy as:  SPEED_WINDOW / mean_torque_in_band
# where mean_torque is the normalised [0,1] torque averaged over the RPM
# sweep from the shift point to the redline (current gear) or from the
# post-shift RPM to the redline (next gear).  The absolute value of
# SPEED_WINDOW cancels in the qualifying/race COMPARISON but must be a
# positive, non-zero float.  1.0 keeps the arithmetic clean.
SPEED_WINDOW: float = 1.0

# ---------------------------------------------------------------------------
# Sweep resolution
# ---------------------------------------------------------------------------

# Step size (RPM) for the candidate-shift-RPM sweep in both the qualifying
# and race optimisers.  Finer resolution improves accuracy at the cost of
# compute time.  100 RPM gives ≤50 RPM median error relative to a continuous
# optimum on a piecewise-linear torque curve — well within the engine's own
# hysteresis band.  The sweep is O(redline / SWEEP_STEP_RPM) per gear pair,
# which is ≈100 iterations at most.
SWEEP_STEP_RPM: int = 100

# ---------------------------------------------------------------------------
# RPM floor fractions  (as fraction of peak-power RPM)
# ---------------------------------------------------------------------------

# The lowest candidate shift point we will evaluate for a QUALIFYING profile.
# Shifting before this fraction of peak-power RPM would take the engine out of
# its power band entirely before the next gear's post-shift RPM re-enters it.
# 0.75 × peak_power_rpm is a practical floor: below this the torque curve is
# rising strongly and shifting is never optimal.
QUAL_MIN_RPM_FRACTION: float = 0.75

# The lowest candidate shift point we will evaluate for a RACE / fuel-saving
# profile.  Wider than the qual floor because deliberate short-shifting for
# economy may extend into the lower torque plateau (especially for TC/SC cars
# with a flat torque band).  0.55 gives meaningful fuel savings without
# entering the off-cam region where the car becomes unresponsive.
RACE_MIN_RPM_FRACTION: float = 0.55

# If the post-shift RPM in the NEXT gear falls below this fraction of
# peak-power RPM the pairing is below the power band in the destination gear
# and must be marked invalid (valid=False, confidence=INSUFFICIENT_EVIDENCE).
# 0.45 × peak_power_rpm: below this the engine is essentially off-cam in the
# next gear; the upshift hurts lap time unconditionally.
MIN_USEFUL_RPM_FRACTION: float = 0.45

# ---------------------------------------------------------------------------
# Fuel-saving proxy coefficient  — UNVALIDATED / PROVISIONAL
# ---------------------------------------------------------------------------

# PROVISIONAL PROXY — outputs computed with this constant are ALWAYS tagged
# confidence=PROVISIONAL and must never be labelled HIGH or MEDIUM.
#
# Reducing the shift RPM reduces mean RPM in each gear, which reduces mean
# fuel burn.  The true relationship depends on fuel-map, injector duty cycle,
# enrichment strategies, and throttle position — none of which GT7 telemetry
# exposes per-gear.  This coefficient approximates:
#
#   fuel_saving_fraction ≈ (qual_rpm - race_rpm) / qual_rpm × coefficient
#
# 0.6 means that a 10 % RPM reduction translates to ≈ 6 % fuel saving,
# reflecting real-world diminishing-return effects (enrichment, friction, etc.).
# This will be replaced by a telemetry-calibrated per-car value in Phase 2.
FUEL_BURN_RPM_COEFFICIENT: float = 0.6

# NOTE ON DRIVELINE EFFICIENCY
# A full transmission-loss model would multiply every torque value by
# η_driveline (typically 0.88–0.93 for a RWD GT car).  This factor is
# OMITTED here because it appears as a CONSTANT multiplier on EVERY gear pair
# and therefore cancels completely in the per-pair relative comparison used by
# both the qualifying and race optimisers.  Including it would add complexity
# without changing any output.  If an absolute power figure is ever needed
# (e.g., traction-circle modelling) this constant must be reintroduced.

# ---------------------------------------------------------------------------
# Engine torque-curve shape anchors by aspiration
# ---------------------------------------------------------------------------

# Normalised torque [0,1] at the idle / low-RPM anchor point (below peak-
# torque RPM).  NA engines build torque slowly (narrow power band); TC/SC have
# a flatter torque curve due to boost; EV delivers near-maximum torque from
# zero RPM.

# NA — Naturally Aspirated.  Torque builds gradually; idle torque fraction
# is low because the engine has no boost to fill in the low-end.
NA_IDLE_TORQUE_FRAC: float = 0.05

# Torque at redline for NA cars drops sharply once the valvetrain can no
# longer fill the cylinders at high RPM.
NA_REDLINE_TORQUE_FRAC: float = 0.25

# TC — Turbocharged.  Boost plateau gives a flatter mid-range torque curve.
# Low-end (pre-boost) still limited, but the plateau is wide.
TC_IDLE_TORQUE_FRAC: float = 0.10
TC_REDLINE_TORQUE_FRAC: float = 0.45

# SC — Supercharged.  Similar to TC but boost builds from idle (no lag), so
# the idle fraction is slightly higher and the plateau slightly wider.
SC_IDLE_TORQUE_FRAC: float = 0.20
SC_REDLINE_TORQUE_FRAC: float = 0.50

# EV — Electric Vehicle.  Maximum torque available from near-zero RPM; the
# "peak_torque_rpm" for modelling purposes is very low.  Torque falls off
# above peak-power RPM as the motor enters field-weakening.
EV_IDLE_TORQUE_FRAC: float = 0.90
EV_REDLINE_TORQUE_FRAC: float = 0.30

# Idle RPM anchor used in the torque curve when no explicit idle RPM is known.
# Below this point the normalised curve is clamped to the aspiration-specific
# idle torque fraction.  1 000 rpm is the conventional GT car idle.
IDLE_RPM_ANCHOR: int = 1_000
