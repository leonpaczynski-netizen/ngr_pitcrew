"""Discrete wheel-slip EPISODES from a lap's telemetry frames (pure, Qt-free).

Sprint 4 of the determinism rebuild. The legacy path counted telemetry *frames*
(or edge-latched them per lap) and treated every sample as evidence, so one
continuous slide, a downshift blip, or a wheel unloading over a kerb each
inflated the "wheelspin/lockup events" tally. That is not trustworthy setup
evidence.

This module turns a frame sequence into a small set of discrete
:class:`SlipEpisode` objects — each with a start/end, duration, peak and mean
slip, driven axle, corner phase, and a classification/exclusion reason — using:

  * per-frame, per-axle classification (``strategy.wheel_slip.classify_wheel_slip``),
    so brake-side slip is a LOCKUP, never acceleration wheelspin;
  * hysteresis (enter high, leave low) so a single slide is one episode;
  * a minimum duration and adjacent-episode merging (a slide sampled as many
    frames = one episode, not N events);
  * suppression of shift/downshift transients, kerb-unloading, airborne wheels,
    and brake-conflict frames — flagged with an ``exclusion_reason`` and NOT
    counted as setup evidence.

Authors no setup values, calls no AI, touches no Qt/DB/files. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from strategy.wheel_slip import classify_wheel_slip, driven_axle


@dataclass(frozen=True)
class EpisodeConfig:
    """Tunable, tested thresholds for episode extraction (one place, visible)."""
    min_speed_ms: float = 2.0
    min_throttle: float = 0.7          # enter-wheelspin throttle floor (matches classifier)
    min_brake: float = 0.3             # enter-lockup brake floor
    # Hysteresis: enter at the classifier ratio, leave only past these looser ratios.
    spin_exit_ratio: float = 1.15      # stay "spinning" until driven-axle ratio < this
    lock_exit_ratio: float = 0.6       # stay "locked" until axle ratio > this
    # Episode shaping.
    min_duration_ms: int = 80          # discard sub-80 ms flickers as noise
    merge_gap_ms: int = 120            # merge same-kind episodes separated by < this
    min_samples: int = 2               # a lone sample is noise unless it is long enough
    # Suppression windows / thresholds.
    shift_window_ms: int = 200         # slip within this of a gear change → shift transient
    kerb_suspension_m: float = 0.04    # >40 mm travel during a short episode → kerb unload
    airborne_road_plane_y: float = 0.9 # road normal Y below this → wheel unloaded / airborne
    # Confidence shaping.
    strong_duration_ms: int = 250
    strong_slip_margin: float = 0.25   # |ratio-1| beyond threshold considered strong


DEFAULT_CONFIG = EpisodeConfig()


@dataclass(frozen=True)
class SlipEpisode:
    kind: str               # "wheelspin" | "lockup"
    subtype: str            # power_wheelspin | inside_wheel_spin | both_wheel_power_oversteer
                            # | rear_lockup | front_lockup | downshift_transient | ...
    axle: str               # "front" | "rear" | "all"
    start_ms: int
    end_ms: int
    duration_s: float
    max_slip: float         # peak |wheel/ground ratio|
    mean_slip: float
    sample_count: int
    throttle: float         # mean over the episode
    brake: float            # mean over the episode
    speed_kmh: float        # mean over the episode
    gear: int               # gear at episode start
    yaw_rate: float         # mean |angvel_z| — rotation proxy (no direct steering channel)
    road_distance: float    # metres at episode start
    segment_id: str = ""
    corner_phase: str = ""
    confidence: float = 0.0
    exclusion_reason: str = ""   # "" = counts as evidence; else why it is suppressed
    provenance: str = "episode_extractor_v1"

    @property
    def is_evidence(self) -> bool:
        """True when this episode is admissible as setup evidence (not suppressed)."""
        return not self.exclusion_reason


# --------------------------------------------------------------------------- #
# Duck-typed frame access (works with TelemetryFrame or any namespace)
# --------------------------------------------------------------------------- #
def _f(frame, name, default=0.0):
    v = getattr(frame, name, default)
    return default if v is None else v


def _classify_frame(frame, drivetrain: str):
    return classify_wheel_slip(
        _f(frame, "wheel_rps", (0.0, 0.0, 0.0, 0.0)),
        _f(frame, "tyre_radius", (0.0, 0.0, 0.0, 0.0)),
        _f(frame, "speed_kmh", 0.0) / 3.6,
        _f(frame, "throttle", 0.0),
        _f(frame, "brake", 0.0),
        drivetrain,
    )


def _mean(vals) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _suspension_max(frame) -> float:
    susp = _f(frame, "suspension", (0.0, 0.0, 0.0, 0.0))
    try:
        return max(abs(float(s)) for s in susp)
    except (TypeError, ValueError):
        return 0.0


def _episode_from_run(run, drivetrain, cfg, segment_resolver) -> Optional[SlipEpisode]:
    """Build one SlipEpisode from a contiguous run of same-kind slip frames."""
    if not run:
        return None
    kind = run[0][1].kind
    frames = [fr for fr, _s in run]
    samples = [s for _fr, s in run]

    start_ms = int(_f(frames[0], "elapsed_ms", 0))
    end_ms = int(_f(frames[-1], "elapsed_ms", 0))
    duration_ms = max(0, end_ms - start_ms)
    duration_s = duration_ms / 1000.0

    ratios = [abs(s.slip_ratio) for s in samples]
    max_slip = max(ratios) if ratios else 0.0
    mean_slip = _mean(ratios)
    mean_thr = _mean([_f(fr, "throttle", 0.0) for fr in frames])
    mean_brk = _mean([_f(fr, "brake", 0.0) for fr in frames])
    mean_spd = _mean([_f(fr, "speed_kmh", 0.0) for fr in frames])
    yaw = _mean([abs(_f(fr, "angvel_z", 0.0)) for fr in frames])
    start_gear = int(_f(frames[0], "gear", 0))
    end_gear = int(_f(frames[-1], "gear", 0))
    road_dist = float(_f(frames[0], "road_distance", 0.0))

    # Dominant axle across the run.
    axle_votes: dict[str, int] = {}
    for s in samples:
        axle_votes[s.axle] = axle_votes.get(s.axle, 0) + 1
    axle = max(axle_votes, key=axle_votes.get) if axle_votes else ""

    seg_id, phase = ("", "")
    if segment_resolver is not None:
        try:
            seg_id, phase = segment_resolver(road_dist, mean_spd, mean_thr, mean_brk)
        except Exception:
            seg_id, phase = ("", "")

    # ---- subtype + exclusion --------------------------------------------- #
    exclusion = ""
    if kind == "wheelspin":
        if axle == "all":
            subtype = "both_wheel_power_oversteer"
        elif axle in ("front", "rear"):
            subtype = "inside_wheel_spin"
        else:
            subtype = "power_wheelspin"
        # An upshift right at slip onset is a driveline transient, not traction loss.
        if end_gear > start_gear and duration_ms <= cfg.shift_window_ms:
            exclusion = "shift_transient"
    else:  # lockup
        subtype = {"front": "front_lockup", "rear": "rear_lockup"}.get(axle, "axle_lockup")
        # A downshift during a brief rear-speed drop is a driveline transient.
        if end_gear < start_gear and duration_ms <= cfg.shift_window_ms:
            subtype = "downshift_transient"
            exclusion = "downshift_transient"

    # Kerb unloading: big suspension travel during a short episode.
    if not exclusion:
        max_susp = max((_suspension_max(fr) for fr in frames), default=0.0)
        if max_susp > cfg.kerb_suspension_m and duration_ms <= cfg.shift_window_ms:
            exclusion = "kerb_unload"

    # Airborne / unloaded wheel: road normal Y collapses.
    if not exclusion:
        min_plane = min((float(_f(fr, "road_plane_y", 1.0)) for fr in frames), default=1.0)
        if min_plane < cfg.airborne_road_plane_y:
            exclusion = "airborne"

    # Noise: too short and too few samples, and barely past threshold.
    if not exclusion:
        if duration_ms < cfg.min_duration_ms and len(samples) < cfg.min_samples:
            exclusion = "noise"

    # ---- confidence ------------------------------------------------------ #
    margin = abs(max_slip - (1.3 if kind == "wheelspin" else 0.5))
    conf = 0.4
    if duration_ms >= cfg.strong_duration_ms:
        conf += 0.3
    if margin >= cfg.strong_slip_margin:
        conf += 0.2
    if len(samples) >= 4:
        conf += 0.1
    confidence = 0.0 if exclusion else min(1.0, conf)

    return SlipEpisode(
        kind=kind, subtype=subtype, axle=axle,
        start_ms=start_ms, end_ms=end_ms, duration_s=round(duration_s, 3),
        max_slip=round(max_slip, 3), mean_slip=round(mean_slip, 3),
        sample_count=len(samples),
        throttle=round(mean_thr, 3), brake=round(mean_brk, 3),
        speed_kmh=round(mean_spd, 1), gear=start_gear, yaw_rate=round(yaw, 3),
        road_distance=round(road_dist, 1), segment_id=seg_id, corner_phase=phase,
        confidence=round(confidence, 2), exclusion_reason=exclusion,
    )


def extract_slip_episodes(
    frames,
    drivetrain: str = "",
    *,
    config: EpisodeConfig = DEFAULT_CONFIG,
    segment_resolver: Optional[Callable[[float, float, float, float], tuple]] = None,
) -> list[SlipEpisode]:
    """Return the discrete wheel-slip episodes in one lap's ``frames``.

    ``segment_resolver(road_distance, speed_kmh, throttle, brake) -> (segment_id, phase)``
    is optional; when omitted, episodes carry empty segment/phase (wired at the
    call site with the real resolver).
    """
    cfg = config or DEFAULT_CONFIG
    if not frames:
        return []

    # 1) Classify each frame (per-axle); build contiguous same-kind runs with
    #    hysteresis so a single slide stays one run.
    runs: list[list] = []
    current: list = []
    current_kind = ""
    for fr in frames:
        speed_ms = _f(fr, "speed_kmh", 0.0) / 3.6
        sample = _classify_frame(fr, drivetrain)
        active = sample.kind if sample.kind in ("wheelspin", "lockup") else ""

        if active and speed_ms > cfg.min_speed_ms:
            if current_kind == active:
                current.append((fr, sample))
            else:
                if current:
                    runs.append(current)
                current = [(fr, sample)]
                current_kind = active
        else:
            # Hysteresis: allow a marginal same-kind frame to keep a run alive.
            kept = False
            if current_kind == "wheelspin" and float(_f(fr, "throttle", 0.0)) >= cfg.min_throttle:
                # still on throttle — treat as tail of the spin if barely dropped
                ratio = abs(sample.slip_ratio) if sample.kind == "wheelspin" else 0.0
                if ratio >= cfg.spin_exit_ratio:
                    current.append((fr, sample)); kept = True
            elif current_kind == "lockup" and float(_f(fr, "brake", 0.0)) >= cfg.min_brake:
                ratio = abs(sample.slip_ratio) if sample.kind == "lockup" else 1.0
                if ratio <= cfg.lock_exit_ratio:
                    current.append((fr, sample)); kept = True
            if not kept and current:
                runs.append(current)
                current = []
                current_kind = ""

    if current:
        runs.append(current)

    # 2) Merge adjacent same-kind runs separated by a sub-threshold gap.
    merged: list[list] = []
    for run in runs:
        if merged:
            prev = merged[-1]
            same_kind = prev[0][1].kind == run[0][1].kind
            gap = int(_f(run[0][0], "elapsed_ms", 0)) - int(_f(prev[-1][0], "elapsed_ms", 0))
            if same_kind and 0 <= gap <= cfg.merge_gap_ms:
                prev.extend(run)
                continue
        merged.append(run)

    # 3) Build episodes; drop sub-duration noise runs that also lack samples.
    episodes: list[SlipEpisode] = []
    for run in merged:
        ep = _episode_from_run(run, drivetrain, cfg, segment_resolver)
        if ep is None:
            continue
        # Discard the truly-empty flickers entirely (kept-but-noise episodes are
        # returned with exclusion_reason="noise" so callers can see them).
        dur_ms = ep.duration_s * 1000.0
        if dur_ms < cfg.min_duration_ms and ep.sample_count < cfg.min_samples and ep.max_slip <= (
                1.3 if ep.kind == "wheelspin" else 1.0):
            # keep as a visible, suppressed noise episode rather than silently dropping
            ep = SlipEpisode(**{**ep.__dict__, "exclusion_reason": ep.exclusion_reason or "noise",
                                "confidence": 0.0})
        episodes.append(ep)
    return episodes


def evidence_episodes(episodes) -> list[SlipEpisode]:
    """Filter to episodes admissible as setup evidence (not suppressed)."""
    return [e for e in episodes if getattr(e, "is_evidence", False)]
