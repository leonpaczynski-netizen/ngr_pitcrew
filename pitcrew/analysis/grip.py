"""The grip observable, derived offline from frames already on disk.

**GT7 broadcasts no tyre wear channel, in any packet format.** That is the fact
this module exists around. The app cannot read tyre life, so it measures the
*effect* of tyre life instead, from a quantity the driver's own laps already
contain: how much grip he actually used.

**The observable is `comb_p95`** — the 95th percentile, over one lap, of the
magnitude of the combined acceleration vector, `sqrt(lat_g^2 + long_g^2)`, over
frames above 15 m/s. Measured over 95 clean laps at three circuits:

* **It is no noisier than the stopwatch.** Lap-to-lap CV, from consecutive-lap
  differences so a stint's own drift is not counted as noise: 0.72 % at Monza,
  1.10 % at Yas, 1.54 % at Watkins, against lap time's 0.81 / 1.17 / 1.52 %.
* **It orders compounds and lap time does not.** Monza / Porsche, clean laps:
  RH 1.848, RM 1.896, RS 1.968 — monotone in compound softness, Welch t = 8.65.
  Lap time puts RS *slower* than RM and separates RS from RH at t = 0.72.

**WHAT IT ACTUALLY MEASURES, and this is not what it was first sold as.** A
percentile sweep settles it, and the two headline claims turn out to rest on
different physics:

* **Compound ordering is a ceiling effect, and it is real.** The separation
  survives all the way to the top of the distribution — at Monza the *p99*
  orders RH 2.144 / RM 2.194 / RS 2.215 at Welch t = 8.6, and `top240` (a
  fixed-count high-end mean, immune to how much of the lap was spent near the
  limit) orders them at t = 7.8. A softer tyre genuinely raises the friction
  ceiling and this observable sees it.
* **Within-stint degradation is NOT a ceiling effect.** Slope t by percentile
  at Monza RH: p80 −0.1, p85 −1.9, **p90 −5.9, p93 −7.8, p95 −6.4**, p97 −3.0,
  **p99 +0.1**. The signal lives in a band and vanishes at the top. Every
  fixed-count statistic — `top30` −0.8, `top60` −0.5, `top120` −0.6, `top240`
  −1.4 — shows nothing, with per-stint slopes of mixed sign. Corroborating:
  `comb_p95` correlates **+0.91** with the *count* of frames above 1.8 g and
  only weakly with the ceiling.

  So what declines through a stint is **how much of the lap he could hold near
  the limit, not how high the limit was.** That is consistent with CLAUDE.md
  §5.1 — balance shifts before the stopwatch does — and it is equally
  consistent with him simply tapering his effort. The data cannot separate
  those two, which is why **the magnitude is not speakable and the fitted
  models say only that the direction is down.**

  **Do not "fix" this by moving to p90 or p93.** They have the larger t, but
  they also have the *higher* correlation with time-near-the-limit (+0.73 and
  +0.95), so they are more of the confounded quantity rather than less. There
  is no percentile that escapes the band, and the statistics that do escape it
  carry no signal. The statistic is not the thing to change; the claim is.

Three constructions in here are not obvious and are all measured findings:

* **A percentile, never a maximum.** `comb_max` has a CV of 26-28 %. Not
  because of kerb strikes — that explanation was wrong — but because the speed
  channel drops to exactly 0.0 for runs of frames mid-straight on 35 of the 175
  archived laps. See `MAX_PLAUSIBLE_COMB_G`.
* **The fuel direction is NOT known, and this module used to claim it was.**
  The argument was a_lat = mu(mg + D)/m, so d a/d m <= 0, therefore burning
  fuel can only raise the observable and every decline is a lower bound. The
  data does not agree: the partial fuel coefficient is **+0.00059 g/L at
  t = +1.73**, the opposite sign to the prediction, and it is unidentifiable
  anyway because `corr(lap_in_stint, fuel) = −0.946` within a stint. What can
  be said is narrower and is worth more: substituting lap time for fuel leaves
  the trend essentially unchanged (−0.00406 g/lap, t = −5.46 against −0.00415,
  t = −6.42), so the decline is not simply the tank emptying.
* **Effort is filtered, not corrected.** `comb_p95` is a level *achieved*, and
  a level not attempted is not measured — session 44's deliberate fuel-save
  lap read 5.3 % low. Two commitment covariates were tried and moved the fitted
  coefficients by under 7 %, so they are recorded and not trusted. What keeps
  the fit honest is the push-lap filter below.

Nothing here runs on the telemetry thread and nothing here captures anything
new. `CLAUDE.md` §6 kept the raw stream on disk so a stored session could be
re-aggregated after a detector was fixed; every number above was computed from
frames that were already there.

---

Three decisions worth stating so the next reader does not undo them:

**1. The apex-stability threshold rejects most corners, and that is correct.**
Applied literally - observed-apex sd against a quarter of the window half-width
- it fails **19 of the 25 corners** in the archive. The design pass named only
two as marginal, but its own measured figures (apex sd 9-48 m, median 17 m,
against windows of 61-228 m, median 110 m) put the *median* corner at
17 / 55 = 0.31, above its own 0.25 threshold. So the threshold was set wrong,
not the implementation, and it is left as written. **Do not loosen it to make
the count look better.** Nothing downstream is harmed: the corner is
deliberately not the fit unit, so the effect is confined to which corner rows
carry `counts_toward_fit = 1`. If it should move, move it on purpose.

Its one genuine perversity, recorded so the next reader is not surprised by it:
**the rule is sample-size perverse.** The observed-apex sd is estimated from
whatever clean laps exist, and more laps estimate a wider one, so the same
corner reads `stable` on 16 laps and `unstable` on 53 - the evidence improved
and the verdict got worse. That is the wrong way round for a stability test,
and it is a reason to replace the rule rather than retune it: the right shape
is a bound on the *standard error* of the apex, or a flat metre tolerance,
neither of which punishes a corner for being well measured.

**2. The apex anchor lives on the observation, not on `corner_models`.** The
design pass asked for `apex_m_observed` beside `apex_m` in the stored corner
model. It is here instead, and on reflection this is the better home rather
than a deferral: **every row is explainable by the exact window that produced
it**, which a shared mutable model row cannot promise. The stored corner model
is also upserted in place by `Store.save_corner_model`, so "bump the version,
never overwrite" is not achievable there without changing that write path. To
move it later, three things have to change together: a field on the frozen
`Corner` dataclass, `CornerModel.from_dict` tolerating its absence on every
model already stored, and `save_corner_model` inserting a new version rather
than upserting - and `export/build.py` reads `Corner`, so it moves with them.

**3. The push-lap filter makes this module's figures differ from the design
pass's, in the filter's favour.** Session 19's two stint slopes come out
-0.00196 and -0.00678 g/lap here against the pass's -0.00297 and -0.00635. The
difference is entirely that **the pass's windows kept the spin laps and this
filter drops them**; a lap he spun on is not a measurement of what the tyre
would give. The figures here are the ones to trust.

**4. The "+3.5 % step at the tyre change" does not survive a fair comparison,
and neither did the +2.91 % this module first reported.** Both compare one lap
- lap 17, which is the *peak of the second stint's warm-up* - against a
stint-1 line extrapolated four laps past its own data. Both stints of session
19 started on fresh sets, so the fair comparison is mean to mean over matched
`lap_in_stint` ranges, and that gives **1.8384 against 1.8384 — zero, to four
figures, on 8 laps against 7.** Last-lap-before against first-lap-after gives
+1.76 %, and that one is a warm-up too. **There is no measured
grip step at the stop in this archive.** Session 19 still shows a warm-up, a
decline, a stop and a second decline - the shape is real - but the size of the
reset is not established and must not be quoted.
"""
from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field

from pitcrew.analysis.resolve import circuit_key as circuit_key_for

# **Bump this and rebuild wholesale; never patch a stored row.** A fitted model
# names the derivation version it was fitted under, and that is the only thing
# making its coefficients resolvable back to the observations behind them.
DERIVATION_VERSION = 1

# The two ways a lap's yaw rate can have reached us, and they are not
# interchangeable. See `yaw_source_for`.
YAW_FROM_PACKET = "packet-angvel-y"
YAW_FROM_PATH = "path-reconstructed"

G = 9.81

# 15 m/s. Below it the rig's own vehicle model returns defaults rather than
# nulls and a lateral-g reading is mostly quantisation of a crawling car.
MIN_SPEED_KPH = 54.0
# Speed is stored to 0.1 km/h; a single-frame difference is largely rounding.
# A 5-frame boxcar differenced over +-3 frames is 100 ms of stencil, which is
# what the measurement pass used and what every figure in the docstring rests on.
SMOOTH_HALF_FRAMES = 2
DIFF_HALF_FRAMES = 3

# |frames/sample_hz - lap_time| / lap_time. Good laps sit at -0.10 %; a phantom
# lap from a lobby join sits at +14 %, because GT7 reports a lap time for a lap
# the app never saw the frames of. Two per cent separates them with room to spare.
FRAMES_GATE_TOLERANCE = 0.02

# The push-lap filter's tolerances. Off-track is allowed a couple of seconds
# because a wheel over a kerb exit line is not an incident; crawling and
# rotating are allowed none.
MAX_OFF_TRACK_S = 2.0

# **A combined-g reading above this is not a measurement, it is a dropout.**
# Measured: 35 of the 175 archived laps carry frames above 3 g, one peaking at
# 138.6 g. The mechanism was traced and it is not a kerb strike - it is the
# speed channel reading **exactly 0.0 for a run of frames in the middle of a
# straight**, at 268 km/h, so the differencing stencil spans the cliff and
# reports a deceleration no car can produce. That is CLAUDE.md §7's warning
# exactly: zeros are the one failure mode that survives into a recommendation.
#
# Frames above the ceiling are **discarded, not clipped**: a clipped frame is a
# fabricated measurement at the bound, and the honest reading of a dropout is
# that the lap was not measured there. They are counted and reported, because a
# lap that loses many of them has a stream problem worth knowing about.
#
# 3.0 g is chosen as a physical bound rather than a statistical one - no Gr.3
# car on slicks reaches it - so it cannot move with the data. It discards
# nothing real: the highest genuine per-lap p99 in the archive is 2.4 g.
MAX_PLAUSIBLE_COMB_G = 3.0

# A corner window under this many usable frames is not an observation of a
# corner. Eight frames is 133 ms.
MIN_CORNER_FRAMES = 8
# The approach over which entry temperature is read, and the braking zone.
ENTRY_WINDOW_M = 150.0
BRAKE_APPROACH_M = 250.0
MIN_BRAKE_PCT = 40.0
FULL_THROTTLE_PCT = 95.0

# Corner windows are anchored on the apex he actually drove, not the one
# auto-segmentation guessed: measured across 25 corners, the systematic offset
# between the two runs -39 m to +26 m and is consistently signed per corner, so
# it is a model-calibration error rather than instability.
APEX_ANCHOR_MIN_LAPS = 10
# A corner whose observed apex scatters by more than a quarter of its window
# half-width has no stable identity, and observations from it are written with
# `counts_toward_fit = 0` rather than quietly pooled with the rest.
#
# **Applied to this archive the rule is far stricter than the design pass
# expected, and that is reported rather than tuned away.** The pass named two
# corners as marginal - Yas T7 and Watkins T2 - but its own measured figures
# (apex sd 9-48 m, median 17 m, against windows of 61-228 m, median 110 m) put
# the *median* corner at 17 / 55 = 0.31 of a half-width, which this threshold
# rejects. Measured here it fails 19 of 25 corners. Nothing downstream breaks,
# because the corner is deliberately not the fit unit - see `observation_rows` -
# but if the threshold is wrong it should be moved on purpose.
APEX_SD_LIMIT_FRACTION = 0.25

_AXLES = (("temp_fl", "temp_fr"), ("temp_rl", "temp_rr"))
_SURFACES = ("surf_fl", "surf_fr", "surf_rl", "surf_rr")


def yaw_source_for(frame_schema_version: int | None) -> str:
    """Which way this lap's yaw rate reached us. **Never null, never guessed.**

    v1 blobs stored the roll rate where the yaw rate belonged, and
    `repair_frames` recovers ground-track yaw by differencing the stored path.
    v2 laps carry the packet's own `angvel_y`. Measured on identical setup
    sheets, v2 reads **3-4 % higher**: Yas sheet 12 read 1.694 on v1 against
    1.729-1.766 on v2; Monza sheet 3 read 1.848 on v1 against 1.915 on v2.

    **That offset is the same size as the compound step the model exists to
    detect**, so a fit that pooled across it would read a change of storage
    format as a change in the car. The refusal to pool stands on that
    measurement alone and needs no mechanism.

    **The mechanism previously stated here was wrong, and it mattered.** The
    claim was that the +-0.1 s path stencil "attenuates" the peak, i.e. that v1
    is a smoothed version of v2. Two things are against it. First the size:
    inflating `lat_g` by the full 4 % moves Monza's `comb_p95` by only +1.77 %,
    under half the observed gap - and the observed gap rests on **one** v2 lap
    at that circuit. Second, and more important, **the two are not the same
    quantity**. Path-reconstructed yaw is the rate of change of the direction
    of travel; `angvel_y` is the rate of rotation of the body, and they differ
    by the rate of change of sideslip. A cornering car has a non-zero one. So
    it is not settled which of the two is the biased estimate of the lateral
    acceleration the tyre actually produced - **v2 may be the biased one.**

    **The way out, and it retires this whole problem.** `vel_x/y/z` are stored
    on 39 of the 175 archived laps and on everything recorded from now on.
    Differencing world velocity gives a lateral acceleration directly, with no
    yaw rate in it at all - identical in construction across both schema
    versions, and closer to what a tyre is doing than either. Once enough laps
    carry it, derive the observable that way, compare on the laps that carry
    both, and this refusal can be retired rather than lived with.
    """
    return YAW_FROM_PATH if (frame_schema_version or 1) < 2 else YAW_FROM_PACKET


def frames_gate(lap_time_ms: int | None, frame_count: int | None,
                sample_hz: float | None) -> tuple[bool, float | None]:
    """Do the frames we hold account for the lap time GT7 claimed?

    Returns `(passed, error_fraction)`. `error_fraction` is None when the
    question cannot be asked at all — no lap time, no frames.

    **An unanswerable gate returns `passed = False`, and that is deliberate
    rather than a conflation.** The two states are distinguishable by the
    caller — `error_fraction is None` says the question could not be put — but
    they get the same verdict, because a lap whose frames cannot be checked
    against its claimed time has not been shown to be a lap. Letting an
    unverifiable lap into the fit on the grounds that nothing disproved it is
    how a phantom gets counted.
    """
    if not lap_time_ms or not frame_count or not sample_hz:
        return False, None
    claimed_s = lap_time_ms / 1000.0
    if claimed_s <= 0:
        return False, None
    error = (frame_count / sample_hz - claimed_s) / claimed_s
    return abs(error) <= FRAMES_GATE_TOLERANCE, error


def _percentile(values, p: float) -> float | None:
    """Nearest-rank percentile, no interpolation.

    Deliberately the same arithmetic the measurement pass used, because every
    calibration figure in this module's docstring was produced by it and an
    interpolating percentile would move them by enough to matter at the third
    decimal.
    """
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(p * len(ordered)))
    return ordered[index]


def _mean(values) -> float | None:
    return sum(values) / len(values) if values else None


def _nan_array(count: int) -> array:
    return array("d", [math.nan]) * count if count else array("d")


@dataclass
class LapTrace:
    """One lap reduced to the channels the observable needs.

    Held as `array('d')` with NaN for absent rather than as the frame dicts: a
    circuit's worth of laps has to be in memory at once so the apex anchors can
    be computed before any observation is written, and the dicts are two orders
    of magnitude larger. NaN is the in-array spelling of null here and is
    converted back to None at every boundary.
    """
    lap_id: int
    session_id: int
    lap_num: int
    sample_hz: float
    frame_schema_version: int
    frame_count: int
    dist: array
    speed: array
    lat: array
    comb: array
    temp_front: array
    temp_rear: array
    brake: array
    throttle: array
    kerb: array
    kerb_measured: bool = False
    # Frames discarded as physically impossible; see `MAX_PLAUSIBLE_COMB_G`.
    implausible_frames: int = 0

    @property
    def yaw_source(self) -> str:
        return yaw_source_for(self.frame_schema_version)


def trace_lap(frames: list[dict], sample_hz: float, *, lap_id: int,
              session_id: int, lap_num: int,
              frame_schema_version: int) -> LapTrace:
    """Reduce one lap's repaired frames to the traced channels.

    `frames` must already have been through `repair_frames` — the caller gets
    that from `Store.get_lap_frames`, and it is never re-implemented here. The
    repair is what makes the 132 v1 laps readable at all, and a private copy of
    it would drift.
    """
    count = len(frames)
    rate = sample_hz or 60.0
    dt = 1.0 / rate

    dist = _nan_array(count)
    speed = _nan_array(count)
    lat = _nan_array(count)
    comb = _nan_array(count)
    temp_front = _nan_array(count)
    temp_rear = _nan_array(count)
    brake = _nan_array(count)
    throttle = _nan_array(count)
    kerb = _nan_array(count)
    kerb_measured = False

    speeds_ms: list[float | None] = []
    for index, frame in enumerate(frames):
        value = frame.get("speed_kph")
        speeds_ms.append(None if value is None else value / 3.6)
        if value is not None:
            speed[index] = value
        for name, target in (("lap_distance_m", dist), ("lat_g", lat),
                             ("brake_pct", brake), ("throttle_pct", throttle)):
            raw = frame.get(name)
            if raw is not None:
                target[index] = abs(raw) if name == "lat_g" else raw
        for axle, target in zip(_AXLES, (temp_front, temp_rear)):
            left, right = frame.get(axle[0]), frame.get(axle[1])
            if left is not None and right is not None:
                target[index] = (left + right) / 2.0
        surfaces = [frame.get(name) for name in _SURFACES]
        if any(s is not None for s in surfaces):
            kerb_measured = True
            kerb[index] = 1.0 if any(s == "C" for s in surfaces) else 0.0

    # Longitudinal g: a 5-frame boxcar of speed, differenced over +-3 frames.
    smoothed: list[float | None] = []
    for index in range(count):
        window = [v for v in speeds_ms[max(0, index - SMOOTH_HALF_FRAMES):
                                       index + SMOOTH_HALF_FRAMES + 1]
                  if v is not None]
        smoothed.append(sum(window) / len(window) if window else None)

    implausible = 0
    for index in range(DIFF_HALF_FRAMES, count - DIFF_HALF_FRAMES):
        ahead = smoothed[index + DIFF_HALF_FRAMES]
        behind = smoothed[index - DIFF_HALF_FRAMES]
        if ahead is None or behind is None or math.isnan(lat[index]):
            continue
        if math.isnan(speed[index]) or speed[index] < MIN_SPEED_KPH:
            continue
        long_g = (ahead - behind) / (2 * DIFF_HALF_FRAMES * dt) / G
        magnitude = math.hypot(lat[index], long_g)
        if magnitude > MAX_PLAUSIBLE_COMB_G:
            implausible += 1
            continue                    # a dropout, left unmeasured
        comb[index] = magnitude

    return LapTrace(lap_id=lap_id, session_id=session_id, lap_num=lap_num,
                    sample_hz=rate, frame_schema_version=frame_schema_version,
                    frame_count=count, dist=dist, speed=speed, lat=lat,
                    comb=comb, temp_front=temp_front, temp_rear=temp_rear,
                    brake=brake, throttle=throttle, kerb=kerb,
                    kerb_measured=kerb_measured, implausible_frames=implausible)


# ------------------------------------------------------------ apex anchoring


@dataclass(frozen=True)
class ApexAnchor:
    """Where a corner's apex actually is, and whether it holds still.

    `stable` is False when the observed apex scatters by more than a quarter of
    the corner's window half-width. Two of the 25 corners measured fail it —
    Yas T7 (61 m window against 14 m of scatter) and Watkins T2 (48 m of
    scatter) — and observations from an unstable corner are written and marked
    rather than dropped, because "we cannot tell which corner this was" is
    itself worth recording.
    """
    corner_id: str
    apex_m_model: float
    apex_m_observed: float | None
    laps: int
    sd_m: float | None
    stable: bool
    half_width_m: float

    @property
    def offset_m(self) -> float:
        """How far the window moves. Zero when there is nothing to move it by."""
        if self.apex_m_observed is None:
            return 0.0
        return self.apex_m_observed - self.apex_m_model


def _speed_minimum_distance(trace: LapTrace, start_m: float,
                            end_m: float) -> float | None:
    best_speed, best_dist = None, None
    for index in range(trace.frame_count):
        d, v = trace.dist[index], trace.speed[index]
        if math.isnan(d) or math.isnan(v) or not start_m <= d <= end_m:
            continue
        if best_speed is None or v < best_speed:
            best_speed, best_dist = v, d
    return best_dist


def apex_anchors(corner_model, traces: list[LapTrace]) -> dict[str, ApexAnchor]:
    """Re-derive each corner's apex from the laps he actually drove.

    The median rather than the mean: one lap taken a corner short of the apex
    should not drag the window that every other lap is measured in.

    With fewer than `APEX_ANCHOR_MIN_LAPS` clean laps the anchor is left
    unmeasured and the model's own apex stands. That is not a fallback to a
    guess — the auto-segmented apex is what corner identity has always been
    keyed on — it is a refusal to move the window on evidence too thin to move it.
    """
    anchors: dict[str, ApexAnchor] = {}
    for corner in corner_model.corners:
        # Half the window, not the longer side of an off-centre apex. That is
        # the reading the design pass used when it called Yas T7 marginal: a
        # 61 m window against 14 m of scatter is "half-width is 2.1 sigma".
        half_width = (corner.end_m - corner.start_m) / 2.0
        observed = [d for d in
                    (_speed_minimum_distance(t, corner.start_m, corner.end_m)
                     for t in traces) if d is not None]
        if len(observed) < APEX_ANCHOR_MIN_LAPS:
            anchors[corner.id] = ApexAnchor(
                corner_id=corner.id, apex_m_model=corner.apex_m,
                apex_m_observed=None, laps=len(observed), sd_m=None,
                stable=True, half_width_m=half_width)
            continue
        observed.sort()
        middle = len(observed) // 2
        median = (observed[middle] if len(observed) % 2
                  else (observed[middle - 1] + observed[middle]) / 2.0)
        mean = sum(observed) / len(observed)
        sd = math.sqrt(sum((d - mean) ** 2 for d in observed) / len(observed))
        anchors[corner.id] = ApexAnchor(
            corner_id=corner.id, apex_m_model=corner.apex_m,
            apex_m_observed=median, laps=len(observed), sd_m=sd,
            stable=sd <= APEX_SD_LIMIT_FRACTION * half_width,
            half_width_m=half_width)
    return anchors


# -------------------------------------------------------- the push-lap filter


@dataclass(frozen=True)
class LapEligibility:
    """Whether one lap is evidence about grip, and if not, why not."""
    counts: bool
    reason: str | None
    gate_error: float | None


def lap_eligibility(lap: dict, *, frame_count: int | None,
                    sample_hz: float | None, is_pit_lap: bool,
                    is_out_lap: bool) -> LapEligibility:
    """The push-lap filter, as a stored verdict rather than a live decision.

    A lap that fails is still written, with `counts_toward_fit = 0` and this
    reason on it — a fuel-save lap is a measurement of something, just not of
    grip, and an exclusion that can be read back is one that can be argued with.

    The order of the tests is the order of severity, so the reason a lap gives
    is the worst thing about it rather than the first thing checked.
    """
    passed, error = frames_gate(lap.get("lap_time_ms"), frame_count, sample_hz)
    if not passed:
        # A lobby-join phantom lap: GT7 reports a lap time for a lap whose
        # frames we never saw. It reads +14 % here where a real lap reads -0.10 %.
        return LapEligibility(False, "frames-gate", error)
    if lap.get("excluded"):
        return LapEligibility(False, "excluded", error)
    if lap.get("standing_start_ms"):
        return LapEligibility(False, "standing-start", error)
    if is_pit_lap:
        return LapEligibility(False, "pit-lap", error)
    if is_out_lap:
        return LapEligibility(False, "out-lap", error)
    # Null is not zero. A lap whose frames were never read for incidents has
    # not been cleared of them.
    for column, label in (("crawl_s", "crawl"), ("spin_s", "spin")):
        value = lap.get(column)
        if value is None:
            return LapEligibility(False, f"{label}-unmeasured", error)
        if value > 0:
            return LapEligibility(False, label, error)
    off_track = lap.get("off_track_s")
    if off_track is None:
        return LapEligibility(False, "off-track-unmeasured", error)
    if off_track > MAX_OFF_TRACK_S:
        return LapEligibility(False, "off-track", error)
    # **A lap driven under the app's own fuel-saving instruction is not
    # evidence about the car.** `short_shift_rpm` is null where it was never
    # recorded and 0.0 where the lap ran the normal threshold; only a positive
    # value is a lap he was asked to give something up on.
    if (lap.get("short_shift_rpm") or 0) > 0:
        return LapEligibility(False, "save-lap-short-shift", error)
    return LapEligibility(True, None, error)


# --------------------------------------------------------- the observations


def _window_indices(trace: LapTrace, start_m: float, end_m: float) -> list[int]:
    return [i for i in range(trace.frame_count)
            if not math.isnan(trace.dist[i]) and start_m <= trace.dist[i] <= end_m]


def _values(channel: array, indices) -> list[float]:
    return [channel[i] for i in indices if not math.isnan(channel[i])]


def _fast_indices(trace: LapTrace, indices) -> list[int]:
    return [i for i in indices
            if not math.isnan(trace.speed[i]) and trace.speed[i] >= MIN_SPEED_KPH]


def _decel_p90(trace: LapTrace, apex_m: float) -> float | None:
    """Peak deceleration in the braking zone, as the mean of its top decile.

    Front-axle-specific, which is why it is kept beside the combined figure:
    the balance shifts before the stopwatch does, and on most Gr.3 cars the
    front goes first.
    """
    dt = 1.0 / trace.sample_hz
    indices = sorted(_window_indices(trace, apex_m - BRAKE_APPROACH_M, apex_m),
                     key=lambda i: trace.dist[i])
    if len(indices) < 10:
        return None
    speeds = [trace.speed[i] / 3.6 if not math.isnan(trace.speed[i]) else None
              for i in indices]
    if any(v is None for v in speeds):
        return None
    smoothed = [sum(speeds[max(0, i - SMOOTH_HALF_FRAMES):
                           i + SMOOTH_HALF_FRAMES + 1])
                / len(speeds[max(0, i - SMOOTH_HALF_FRAMES):
                             i + SMOOTH_HALF_FRAMES + 1])
                for i in range(len(speeds))]
    decels = []
    for position in range(DIFF_HALF_FRAMES, len(speeds) - DIFF_HALF_FRAMES):
        braking = trace.brake[indices[position]]
        if math.isnan(braking) or braking < MIN_BRAKE_PCT:
            continue
        rate = ((smoothed[position + DIFF_HALF_FRAMES]
                 - smoothed[position - DIFF_HALF_FRAMES])
                / (2 * DIFF_HALF_FRAMES * dt))
        decels.append(-rate / G)
    if not decels:
        return None
    decels.sort(reverse=True)
    decile = max(1, int(round(0.10 * len(decels))))
    return sum(decels[:decile]) / decile


def _unit_metrics(trace: LapTrace, indices: list[int], *,
                  percentile: float) -> dict:
    """The observable and its covariates over one window of a lap.

    Every value is None when its channel is absent over the window. None means
    the window was not measured; a zero here would be read as a measurement of
    no grip, no heat, or no kerb, and would be believed.
    """
    fast = _fast_indices(trace, indices)
    comb = _values(trace.comb, fast)
    lat = _values(trace.lat, fast)
    speeds = _values(trace.speed, indices)
    front = _values(trace.temp_front, indices)
    rear = _values(trace.temp_rear, indices)
    brake = _values(trace.brake, indices)
    throttle = _values(trace.throttle, indices)
    kerb = _values(trace.kerb, indices)
    return {
        "grip_g": _percentile(comb, percentile),
        "lat_p95_g": _percentile(lat, 0.95),
        "min_speed_kph": min(speeds) if speeds else None,
        "temp_front_c": _mean(front),
        "temp_rear_c": _mean(rear),
        "temp_front_max_c": max(front) if front else None,
        "temp_rear_max_c": max(rear) if rear else None,
        "commit_brake_pct": max(brake) if brake else None,
        "commit_full_thr_frac": (
            sum(1 for v in throttle if v >= FULL_THROTTLE_PCT) / len(throttle)
            if throttle else None),
        # Null rather than 0.0 on the packet formats that carry no surface
        # channel: `A` and `B` do not offer it, and "not offered" is not "no kerb".
        "kerb_frac": (sum(kerb) / len(kerb)
                      if trace.kerb_measured and kerb else None),
        "sample_frames": len(comb),
    }


def _gauge_worst(lap: dict) -> float | None:
    """The worst corner of his gauge reading, or None if he did not read it.

    Worst corner rather than an axle or a four-wheel mean because the stint ends
    when the worst single tyre is done, not when an average is. None where any
    corner is unread: a partial reading averaged with nulls is a fabrication.
    """
    values = [lap.get(f"wear_{corner}") for corner in ("fl", "fr", "rl", "rr")]
    present = [v for v in values if v is not None]
    return max(present) if present else None


@dataclass
class SessionContext:
    """Everything about a session an observation has to carry with it."""
    session_id: int
    car_key: str
    circuit_key: str
    corner_model_version: int | None
    started_at: str | None = None
    stints: dict[int, tuple[str, int]] = field(default_factory=dict)
    pit_laps: set[int] = field(default_factory=set)
    out_laps: set[int] = field(default_factory=set)
    laps_on_set: dict[int, int | None] = field(default_factory=dict)
    elapsed_s: dict[int, float | None] = field(default_factory=dict)
    clock_frozen: dict[int, bool] = field(default_factory=dict)


def observation_rows(trace: LapTrace, lap: dict, context: SessionContext,
                     corner_model, anchors: dict[str, ApexAnchor], *,
                     derivation_version: int = DERIVATION_VERSION) -> list[dict]:
    """One LAP row and one CORNER row per corner, for one lap.

    The LAP row is the unit the fit runs on. The corner rows exist for
    diagnosis and for the export, and **deliberately not for the temperature
    fit**: the within-lap fixed-effects design that looked like it would break
    the fuel-and-wear confound was run and it fails, producing slopes of
    +0.029, -0.025 and +0.019 g/degC on three circuits — conflicting signs at
    t > 3. Two-way demeaning leaves 0.28-1.10 degC of usable variation and into
    that residual walks a confounder the design was supposed to remove: how hard
    he drove the *preceding* corner. It swaps fuel-and-wear for preceding-corner
    effort and the new confounder is stronger. So the rows are written, and the
    within-lap contrast is a diagnostic to be watched rather than an
    identification strategy.
    """
    eligibility = lap_eligibility(
        lap, frame_count=trace.frame_count, sample_hz=trace.sample_hz,
        is_pit_lap=lap["lap_num"] in context.pit_laps,
        is_out_lap=lap["lap_num"] in context.out_laps)
    stint_key, lap_in_stint = context.stints.get(lap["lap_num"], (None, None))

    shared = {
        "lap_id": lap["id"],
        "derivation_version": derivation_version,
        "frame_schema_version": trace.frame_schema_version,
        "yaw_source": trace.yaw_source,
        "car_key": context.car_key,
        "circuit_key": context.circuit_key,
        "compound": lap.get("compound"),
        "session_id": context.session_id,
        "lap_num": lap["lap_num"],
        "stint_key": stint_key,
        "lap_in_stint": lap_in_stint,
        "lap_time_ms": lap.get("lap_time_ms"),
        # Fuel at the lap's start: the load the lap was driven under, not the
        # load it finished on.
        "fuel_l": lap.get("fuel_start"),
        "laps_on_set": context.laps_on_set.get(lap["lap_num"]),
        "gauge_worst_frac": _gauge_worst(lap),
        "tod_ms": lap.get("tod_start_ms"),
        "clock_frozen": (1 if context.clock_frozen.get(lap["lap_num"]) else
                         (None if lap.get("tod_start_ms") is None else 0)),
        "session_elapsed_s": context.elapsed_s.get(lap["lap_num"]),
    }

    whole_lap = list(range(trace.frame_count))
    lap_metrics = _unit_metrics(trace, whole_lap, percentile=0.95)
    reason = eligibility.reason
    counts = eligibility.counts
    if lap_metrics["grip_g"] is None:
        counts, reason = False, reason or "no-observable"
    rows = [{**shared, **lap_metrics,
             "unit_kind": "LAP", "unit_id": "LAP",
             "corner_model_version": None,
             "grip_stat": "comb_p95",
             "decel_p90_g": None,
             "entry_temp_front_c": None, "entry_temp_rear_c": None,
             "apex_m_model": None, "apex_m_observed": None,
             "apex_anchor_laps": None, "apex_anchor_sd_m": None,
             "identity_stable": None,
             "counts_toward_fit": int(counts),
             "exclusion_reason": reason}]

    if corner_model is None:
        return rows

    for corner in corner_model.corners:
        anchor = anchors.get(corner.id)
        shift = anchor.offset_m if anchor else 0.0
        indices = _window_indices(trace, corner.start_m + shift,
                                  corner.end_m + shift)
        metrics = _unit_metrics(trace, indices, percentile=0.90)
        entry = _window_indices(trace,
                                corner.start_m + shift - ENTRY_WINDOW_M,
                                corner.start_m + shift)
        entry_front = _values(trace.temp_front, entry)
        entry_rear = _values(trace.temp_rear, entry)

        corner_counts, corner_reason = counts, reason
        if metrics["sample_frames"] < MIN_CORNER_FRAMES:
            corner_counts, corner_reason = False, corner_reason or "thin-window"
        elif metrics["grip_g"] is None:
            corner_counts, corner_reason = False, corner_reason or "no-observable"
        if anchor is not None and not anchor.stable:
            corner_counts = False
            corner_reason = corner_reason or "corner-identity-unstable"

        rows.append({
            **shared, **metrics,
            "unit_kind": "CORNER", "unit_id": corner.id,
            "corner_model_version": context.corner_model_version,
            "grip_stat": "comb_p90",
            "decel_p90_g": _decel_p90(trace, corner.apex_m + shift),
            "entry_temp_front_c": _mean(entry_front),
            "entry_temp_rear_c": _mean(entry_rear),
            "apex_m_model": corner.apex_m,
            "apex_m_observed": anchor.apex_m_observed if anchor else None,
            "apex_anchor_laps": anchor.laps if anchor else None,
            "apex_anchor_sd_m": anchor.sd_m if anchor else None,
            "identity_stable": (None if anchor is None
                                else int(anchor.stable)),
            "counts_toward_fit": int(corner_counts),
            "exclusion_reason": corner_reason,
        })
    return rows


# ----------------------------------------------------------- the derivation
#
# One pass per circuit, because the apex anchors need every clean lap at the
# circuit before the first observation can be written, and decoding the archive
# twice to get them costs a minute of wall clock for nothing.


@dataclass
class DerivationReport:
    """What a derivation run did, and what it declined to do."""
    derivation_version: int
    rows: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    anchors: dict[str, dict[str, ApexAnchor]] = field(default_factory=dict)
    sessions: set[int] = field(default_factory=set)
    # Frames discarded as physically impossible. Not stored on the row - that
    # would need a column in a table another agent currently holds - but
    # reported, because a lap losing many of them has a stream problem.
    implausible_frames: int = 0

    @property
    def lap_rows(self) -> list[dict]:
        return [r for r in self.rows if r["unit_kind"] == "LAP"]

    @property
    def counted_lap_rows(self) -> list[dict]:
        return [r for r in self.lap_rows if r["counts_toward_fit"]]

    def summary(self) -> str:
        corners = len(self.rows) - len(self.lap_rows)
        return (f"{len(self.lap_rows)} lap observations "
                f"({len(self.counted_lap_rows)} counting toward a fit), "
                f"{corners} corner observations, "
                f"{len(self.sessions)} session(s), "
                f"{len(self.skipped)} lap(s) skipped, "
                f"{self.implausible_frames} frame(s) discarded as implausible")


def _clock_frozen(lap: dict) -> bool:
    """GT7's clock stopped while the car kept driving.

    A circuit without a 24-hour cycle runs its day to the end of its range and
    holds it there. Session 19's laps 17-26 all read 18:50 exactly across ten
    more laps of driving. Reading that as a multiplier of zero is how a poisoned
    `track_clock` row came to be cached once.
    """
    start, end = lap.get("tod_start_ms"), lap.get("tod_end_ms")
    return start is not None and end is not None and start == end


def _session_context(store, event: dict, session: dict,
                     laps: list[dict]) -> SessionContext:
    """Everything about a session that an observation has to carry.

    Stops are re-read from the frames rather than taken from `laps.is_pit_lap`,
    which is 0 on every lap in the archive: the live detector asked for the tank
    to rise 0.05 L between consecutive frames and GT7 fills at 0.0167 L per
    frame, so the gate could not fire. `analysis/reaggregate` already does this
    reading and is reused verbatim; **nothing here writes those flags back**,
    because setting them is that tool's job and this one only derives.
    """
    from pitcrew.analysis.reaggregate import read_session

    model = store.get_corner_model(event_circuit_key(event))
    context = SessionContext(
        session_id=session["id"],
        car_key=event_car_key(event),
        circuit_key=event_circuit_key(event),
        corner_model_version=getattr(model, "version", None),
        started_at=session.get("started_at"),
    )

    def frames_for(lap_id: int):
        stored = store.get_lap_frames(lap_id)
        return stored["frames"] if stored else None

    for lap in laps:
        stored = store.get_lap_frames(lap["id"])
        lap["sample_hz"] = stored["sample_hz"] if stored else 60.0

    changed_at: set[int] = set()
    for finding in read_session(list(laps), frames_for):
        if finding.is_pit_lap:
            context.pit_laps.add(finding.lap_num)
        if finding.is_out_lap:
            context.out_laps.add(finding.lap_num)
        if finding.tyres_changed:
            changed_at.add(finding.lap_num)

    # A session is one run, so it opens a stint; an observed tyre change opens
    # another. **`laps_on_set` stays null unless the set's age is actually
    # known** - a declared fresh set or an observed change. GT7 broadcasts no
    # tyre-change event, so most of the archive genuinely does not know, and a 0
    # there would claim a fresh set on every session's first lap.
    ordinal, on_set, in_stint = 0, None, 0
    elapsed = 0.0
    for index, lap in enumerate(laps):
        fresh = bool(lap.get("tyres_fresh"))
        if index and (lap["lap_num"] in changed_at or fresh):
            ordinal, on_set, in_stint = ordinal + 1, 0, 0
        elif index == 0:
            on_set = 0 if fresh else None
        elif on_set is not None:
            on_set += 1
        context.stints[lap["lap_num"]] = (f"{session['id']}:{ordinal}", in_stint)
        context.laps_on_set[lap["lap_num"]] = on_set
        context.clock_frozen[lap["lap_num"]] = _clock_frozen(lap)
        # Seconds of driving since the session's first lap, accumulated from
        # the lap times themselves rather than from GT7's clock: that one runs
        # at the event's time multiplier and is a stratifier, not a stopwatch.
        context.elapsed_s[lap["lap_num"]] = elapsed
        elapsed += (lap.get("lap_time_ms") or 0) / 1000.0
        in_stint += 1
    return context


def derive_event(store, event: dict, *, session_ids: set[int] | None = None,
                 derivation_version: int = DERIVATION_VERSION,
                 progress=None) -> DerivationReport:
    """Derive every observation this event's stored frames support.

    Two phases over one decode: trace every lap into compact channel arrays,
    anchor the corner windows on the apexes the clean laps actually show, then
    emit the rows. A lap with no frames is skipped and said so — it was not
    measured, which is not the same as having nothing in it.
    """
    report = DerivationReport(derivation_version=derivation_version)
    circuit = event_circuit_key(event)
    corner_model = store.get_corner_model(circuit)

    # **The apex anchors are computed over the whole circuit, always, even when
    # only one session is being written.** They were not, and the consequence
    # was silent: `--session 19 --apply` re-anchored on 16 laps instead of 53
    # and rewrote 156 corner rows at the SAME derivation version - 61 grip
    # values changed, `identity_stable` flipped on 26 corners and
    # `counts_toward_fit` on 16. Two rows written under one version then meant
    # two different windows, which is exactly the reproducibility the version
    # number exists to promise. Tracing every lap costs a minute; a version
    # whose rows disagree with each other costs the model.
    anchor_traced: list[tuple[LapTrace, dict, SessionContext]] = []
    traced: list[tuple[LapTrace, dict, SessionContext]] = []
    for session in store.list_sessions(event["id"]):
        selected = session_ids is None or session["id"] in session_ids
        if not selected and corner_model is None:
            continue
        laps = store.list_laps(session["id"])
        if not laps:
            continue
        context = _session_context(store, event, session, laps)
        if selected:
            report.sessions.add(session["id"])
        for lap in laps:
            stored = store.get_lap_frames(lap["id"])
            if stored is None:
                if selected:
                    report.skipped.append(
                        f"s{session['id']} lap {lap['lap_num']}: no frames stored")
                continue
            trace = trace_lap(
                stored["frames"], stored["sample_hz"], lap_id=lap["id"],
                session_id=session["id"], lap_num=lap["lap_num"],
                frame_schema_version=stored["frame_schema_version"])
            anchor_traced.append((trace, lap, context))
            if selected:
                traced.append((trace, lap, context))
            report.implausible_frames += trace.implausible_frames
            if progress is not None:
                progress(lap["id"])

    anchors: dict[str, ApexAnchor] = {}
    if corner_model is not None:
        # Anchored on the clean laps only. A lap he spun on is not evidence
        # about where the apex is. Every session at the circuit, not only the
        # selected ones - see the note above.
        clean = [t for t, lap, context in anchor_traced
                 if lap_eligibility(
                     lap, frame_count=t.frame_count, sample_hz=t.sample_hz,
                     is_pit_lap=lap["lap_num"] in context.pit_laps,
                     is_out_lap=lap["lap_num"] in context.out_laps).counts]
        anchors = apex_anchors(corner_model, clean)
        report.anchors[circuit] = anchors

    for trace, lap, context in traced:
        report.rows.extend(observation_rows(
            trace, lap, context, corner_model, anchors,
            derivation_version=derivation_version))
    return report


def event_circuit_key(event: dict) -> str:
    return circuit_key_for(event.get("track") or "unknown", event.get("layout"))


def event_car_key(event: dict) -> str:
    """The car, slugged by the app's one rule.

    `car_name` rather than `car_id`: the id is null on two of the three events
    on record, and a fit keyed on null pools two cars.

    **It delegates to `store.tyres.slugify` and must keep doing so.** This
    function briefly carried its own rule, written as "keep alphanumerics" -
    and `str.isalnum()` is True for an accented letter, so it wrote
    `lamborghini-huracan-gt3-15` with the acute intact while the scope
    composition in `store/tyres.py` folded it away. The two keys could never
    match, and the Huracan's 300 grip observations and 8 fitted models were
    unreachable by any scope lookup. Both sides were internally consistent,
    which is why it was invisible.
    """
    from pitcrew.store.tyres import slugify

    return slugify(event.get("car_name") or "unknown-car")
