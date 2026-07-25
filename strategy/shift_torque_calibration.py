"""Adaptive Per-Gear Shift Strategy — telemetry torque calibration (Phase 2).

Estimates the engine's torque-curve ANCHORS — peak-torque RPM, peak-power RPM and
redline — from RECORDED wide-open-throttle telemetry, so the shift engine can rise
above its Phase-1 PROVISIONAL ceiling without the driver hand-entering engine data.

DOCTRINE
  Deterministic, offline, pure. No Qt, no DB, no network, no I/O. Never raises —
  every entry point returns an INSUFFICIENT calibration on failure or thin evidence.

METHOD — shape-only, and honest about the load-model gap
  In a FIXED gear at wide-open throttle, engine torque is proportional to
  longitudinal acceleration:  T ∝ m·a·r / ratio, and m (mass), r (wheel radius) and
  ratio are all constant within one gear. So the torque-curve SHAPE — which is all
  the shift optimiser consumes — equals the acceleration-vs-RPM shape. We therefore:

    1. keep only wide-open-throttle, on-track, non-braking, non-limiter frames;
    2. compute longitudinal acceleration a = Δspeed/Δt from consecutive frames in
       the SAME gear within a lap (elapsed_ms is per-lap, so acceleration is only
       ever differenced within one lap, never across the lap boundary);
    3. pick the LOWEST clean gear (least aero drag, so a(rpm) tracks torque(rpm) most
       faithfully — high gears understate torque at speed because drag is not modelled);
    4. bin acceleration by RPM and take the MEDIAN per bin (10 Hz dv/dt is noisy);
    5. read the anchors off the binned shape:
         peak_torque_rpm = argmax(a)
         peak_power_rpm  = argmax(a · rpm)
         redline         = highest WOT rpm seen, or where the rev-limiter fires.

  We do NOT model aerodynamic drag or rolling resistance and never claim ABSOLUTE
  torque — only the relative shape and the RPM anchors. The reported confidence
  reflects how much of the powerband the evidence actually covers.

CONFIDENCE
  HIGH   — a clean low-gear pull covering peak-torque up to near-redline, plenty of
           binned samples, and a sane peak_torque < peak_power < redline ordering.
  MEDIUM — anchors are identifiable but coverage is partial / the pull is short.
  INSUFFICIENT — not enough clean WOT evidence; the caller keeps manual data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

# --- calibration tunables (local to Phase 2; kept out of the golden-tested
#     shift_strategy_constants so the Phase-1 engine is untouched) --------------
WOT_THROTTLE_MIN = 0.98        # ≥ this counts as wide-open throttle (matches recorder)
MAX_BRAKE = 0.02               # reject any frame with meaningful brake
MIN_ACCEL_MS2 = 0.05           # reject coasting / limiter / shift frames (a ≤ this)
MAX_ACCEL_MS2 = 25.0           # reject impossible spikes (bad Δt, teleport, respawn)
MIN_DT_MS = 1                  # reject zero/negative Δt
MAX_DT_MS = 300                # reject gaps (dropped packets / lap seam) — 10 Hz ⇒ ~100 ms
RPM_BIN = 250                  # RPM bin width for denoising the accel-vs-RPM shape
MIN_BIN_SAMPLES = 3            # a bin needs this many samples to be trusted
MIN_TOTAL_SAMPLES = 40         # minimum accel samples in the chosen gear
MIN_POPULATED_BINS = 6         # minimum trusted bins in the chosen gear
PREFERRED_MIN_GEAR = 2         # prefer 2nd gear up (1st is traction-/wheelspin-limited)
HIGH_COVERAGE_FRAC = 0.90      # rpm_max must reach this fraction of redline for HIGH


def _g(frame, key, default=0.0):
    """Null-safe field read from a frame dict OR a TelemetryFrame-like object."""
    try:
        if isinstance(frame, dict):
            v = frame.get(key, default)
        else:
            v = getattr(frame, key, default)
        return default if v is None else v
    except Exception:
        return default


def _iter_lap_frames(laps) -> List[list]:
    """Normalise ``laps`` into a list of per-lap frame lists.

    Accepts: a list of laps where each lap is a dict with a ``frames`` list, or an
    object with a ``.frames`` attribute, or is itself a list of frames. Anything
    unrecognised is skipped. Never raises.
    """
    out: List[list] = []
    try:
        for lap in (laps or []):
            frames = None
            if isinstance(lap, dict):
                frames = lap.get("frames")
            elif hasattr(lap, "frames"):
                frames = getattr(lap, "frames")
            elif isinstance(lap, (list, tuple)):
                frames = lap
            if isinstance(frames, (list, tuple)) and frames:
                out.append(list(frames))
    except Exception:
        return out
    return out


@dataclass(frozen=True)
class TorqueCalibration:
    """Result of calibrating the torque-curve anchors from recorded telemetry."""

    peak_torque_rpm: Optional[int]
    peak_power_rpm: Optional[int]
    redline: Optional[int]
    confidence: str                      # "high" | "medium" | "insufficient"
    source: str = "telemetry_calibrated"
    gear_used: int = 0
    sample_count: int = 0
    rpm_min: int = 0
    rpm_max: int = 0
    #: The measured normalised torque shape (rpm -> [0,1]); advisory, for display / later use.
    curve: Tuple[Tuple[int, float], ...] = ()
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """Whether the calibration produced usable, above-provisional engine data."""
        return (self.confidence in ("high", "medium")
                and self.peak_torque_rpm is not None
                and self.peak_power_rpm is not None
                and self.redline is not None)

    def to_engine_data(self) -> dict:
        """The engine-data dict the shift inputs consume (mirrors manual_engine_data,
        plus the telemetry provenance so the engine can lift the confidence cap)."""
        return {
            "peak_power_rpm": self.peak_power_rpm,
            "peak_torque_rpm": self.peak_torque_rpm,
            "redline": self.redline,
            "source": "telemetry",
            "calibration_confidence": self.confidence,
        }

    def to_dict(self) -> dict:
        return {
            "peak_torque_rpm": self.peak_torque_rpm,
            "peak_power_rpm": self.peak_power_rpm,
            "redline": self.redline,
            "confidence": self.confidence,
            "source": self.source,
            "gear_used": self.gear_used,
            "sample_count": self.sample_count,
            "rpm_min": self.rpm_min,
            "rpm_max": self.rpm_max,
            "curve": [list(p) for p in self.curve],
            "warnings": list(self.warnings),
        }


def _insufficient(reason: str, sample_count: int = 0) -> TorqueCalibration:
    return TorqueCalibration(
        peak_torque_rpm=None, peak_power_rpm=None, redline=None,
        confidence="insufficient", sample_count=sample_count,
        warnings=(reason,))


def _median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])


def calibrate_torque_from_laps(laps) -> TorqueCalibration:
    """Estimate torque-curve anchors from recorded laps. Never raises.

    ``laps`` — an iterable of laps, each carrying a ``frames`` list of recorded
    telemetry frames (dicts or TelemetryFrame objects) with at least ``elapsed_ms``,
    ``speed_kmh``, ``throttle``, ``brake``, ``gear``, ``rpm`` and ``rev_limiter``.
    """
    try:
        lap_frames = _iter_lap_frames(laps)
        if not lap_frames:
            return _insufficient("No recorded telemetry frames to calibrate from.")

        # accel samples per gear: gear -> list of (rpm, accel_ms2)
        accel_by_gear: dict = {}
        # redline evidence
        limiter_rpms: List[float] = []
        wot_rpms: List[float] = []

        for frames in lap_frames:
            prev = None
            for f in frames:
                thr = float(_g(f, "throttle"))
                rpm = float(_g(f, "rpm"))
                lim = bool(_g(f, "rev_limiter", False))
                if rpm > 0 and lim:
                    limiter_rpms.append(rpm)
                wot = thr >= WOT_THROTTLE_MIN and float(_g(f, "brake")) <= MAX_BRAKE
                gear = int(_g(f, "gear", 0))
                if wot and rpm > 0 and gear > 0:
                    wot_rpms.append(rpm)
                # Differentiate speed within a lap, same gear, no shift/limiter between.
                if prev is not None:
                    p_thr, p_rpm, p_gear, p_t, p_spd = prev
                    dt = float(_g(f, "elapsed_ms")) - p_t
                    if (wot and p_thr >= WOT_THROTTLE_MIN and gear == p_gear
                            and gear > 0 and not lim
                            and MIN_DT_MS <= dt <= MAX_DT_MS):
                        spd = float(_g(f, "speed_kmh")) / 3.6      # m/s
                        a = (spd - p_spd) / (dt / 1000.0)
                        if MIN_ACCEL_MS2 < a <= MAX_ACCEL_MS2:
                            rpm_mid = 0.5 * (rpm + p_rpm)
                            accel_by_gear.setdefault(gear, []).append((rpm_mid, a))
                prev = (thr, rpm, gear, float(_g(f, "elapsed_ms")),
                        float(_g(f, "speed_kmh")) / 3.6)

        if not accel_by_gear:
            return _insufficient(
                "No clean wide-open-throttle acceleration found — drive a full-throttle "
                "pull through the gears (no lifting, no braking) and record the lap.")

        # --- choose the calibration gear: lowest clean gear (least drag) that has
        #     enough samples; prefer 2nd+ (1st is traction-/wheelspin-limited). ---
        def _qualifies(gear: int) -> bool:
            return len(accel_by_gear.get(gear, ())) >= MIN_TOTAL_SAMPLES

        candidates = sorted(g for g in accel_by_gear if _qualifies(g))
        gear_used = 0
        for g in candidates:
            if g >= PREFERRED_MIN_GEAR:
                gear_used = g
                break
        if gear_used == 0 and candidates:
            gear_used = candidates[0]                 # only 1st gear qualified
        if gear_used == 0:
            # Nothing hit the sample floor — fall back to the richest gear so we can
            # still return a MEDIUM/insufficient estimate rather than nothing.
            gear_used = max(accel_by_gear, key=lambda g: len(accel_by_gear[g]))

        samples = accel_by_gear[gear_used]
        sample_count = len(samples)

        # --- bin by RPM, median accel per bin ---
        bins: dict = {}
        for rpm, a in samples:
            b = int(rpm // RPM_BIN)
            bins.setdefault(b, []).append(a)
        binned: List[Tuple[float, float]] = []     # (rpm_center, median_accel)
        for b, vals in bins.items():
            if len(vals) >= MIN_BIN_SAMPLES:
                binned.append(((b + 0.5) * RPM_BIN, _median(vals)))
        binned.sort(key=lambda p: p[0])
        if len(binned) < 2:
            return _insufficient(
                "Not enough of the powerband was covered at wide-open throttle to "
                "read the torque curve.", sample_count=sample_count)

        # --- anchors off the shape ---
        peak_torque_rpm = int(round(max(binned, key=lambda p: p[1])[0]))
        peak_power_rpm = int(round(max(binned, key=lambda p: p[1] * p[0])[0]))
        rpm_min = int(round(binned[0][0]))
        rpm_max = int(round(binned[-1][0]))

        # redline: rev-limiter truth first, else the top of the WOT rpm range.
        if limiter_rpms:
            redline = int(round(min(limiter_rpms)))   # limiter FIRST engages here
        elif wot_rpms:
            redline = int(round(max(wot_rpms)))
        else:
            redline = rpm_max

        warnings: List[str] = []

        # sane ordering peak_torque < peak_power < redline; nudge + warn if the noisy
        # shape violated it rather than emitting nonsense.
        if peak_power_rpm <= peak_torque_rpm:
            warnings.append(
                "Measured peak-power RPM was not above peak-torque RPM; the pull was "
                "likely too short or too noisy. Confidence reduced.")
            peak_power_rpm = max(peak_power_rpm, peak_torque_rpm + RPM_BIN)
        if redline <= peak_power_rpm:
            redline = max(redline, peak_power_rpm + RPM_BIN)

        # normalised shape for display / later use
        max_a = max(a for _, a in binned) or 1.0
        curve = tuple((int(round(rpm)), round(a / max_a, 4)) for rpm, a in binned)

        # --- confidence from coverage ---
        covers_low = rpm_min <= peak_torque_rpm
        covers_high = redline > 0 and rpm_max >= HIGH_COVERAGE_FRAC * redline
        enough_bins = len(binned) >= MIN_POPULATED_BINS
        clean_order = not warnings
        if (covers_low and covers_high and enough_bins
                and sample_count >= MIN_TOTAL_SAMPLES and clean_order):
            confidence = "high"
        elif enough_bins and sample_count >= MIN_TOTAL_SAMPLES:
            confidence = "medium"
        elif len(binned) >= 3:
            confidence = "medium"
            warnings.append("Partial powerband coverage — calibrate with a longer "
                            "full-throttle pull for higher confidence.")
        else:
            return _insufficient(
                "Too little of the powerband was sampled to calibrate confidently.",
                sample_count=sample_count)

        return TorqueCalibration(
            peak_torque_rpm=peak_torque_rpm,
            peak_power_rpm=peak_power_rpm,
            redline=redline,
            confidence=confidence,
            gear_used=gear_used,
            sample_count=sample_count,
            rpm_min=rpm_min,
            rpm_max=rpm_max,
            curve=curve,
            warnings=tuple(warnings),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return _insufficient(f"Calibration error: {exc!r}")
