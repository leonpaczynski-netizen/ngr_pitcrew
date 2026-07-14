"""Live per-corner telemetry aggregation → Phase-5 corner diagnosis (pure, Qt-free).

Accumulates per-corner slip/lock/throttle/gear evidence from a stream of classified
telemetry samples (see :mod:`strategy.wheel_slip`), keyed by the reviewed-segment the
live resolver reports we are in. When a corner has enough evidence, the dominant slip
signature becomes a telemetry-derived ``CornerFeedback`` and is fed straight into the
existing :func:`strategy.corner_diagnosis.diagnose_corner_feedback` with
``telemetry_available=True`` — so the per-corner diagnosis runs on measured data, not
only on the driver's free-text feeling.

Pure and thread-safe (a lock guards the running dict); authors no setup values, calls
no AI, touches no Qt/DB/files. The caller resolves the segment + classifies the slip and
feeds plain data in, keeping this module free of any telemetry/Qt import.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

# Segment type (from the reviewed-segment model) → corner phase vocabulary used by
# strategy.corner_diagnosis. Non-corner segments map to "" and are not attributed.
_SEGMENT_PHASE = {
    "braking_zone": "braking",
    "corner_entry": "entry",
    "apex_zone": "apex",
    "corner_exit": "exit",
    "traction_zone": "exit",
}

# Evidence bars before a corner emits a telemetry-derived symptom (avoid noise).
_MIN_SAMPLES = 8
_MIN_EVENTS = 2


def phase_from_segment_type(segment_type: str) -> str:
    """Map a reviewed-segment type to an entry/apex/exit/braking phase ("" if none)."""
    return _SEGMENT_PHASE.get(str(segment_type or "").strip().lower(), "")


@dataclass
class CornerTelemetryAggregate:
    segment_id: str
    turn: Optional[int]
    display_name: str
    direction: str
    samples: int
    wheelspin_events: int
    lockup_events: int
    wheelspin_by_phase: dict         # phase -> count
    lockup_by_phase: dict            # phase -> count
    spin_axle_counts: dict           # axle -> count
    lock_axle_counts: dict           # axle -> count
    avg_throttle: float
    avg_brake: float
    exit_gear: Optional[int]         # modal gear seen in exit/traction phase
    exit_rpm_avg: Optional[float]

    def as_json(self) -> dict:
        return {
            "segment_id": self.segment_id, "turn": self.turn,
            "display_name": self.display_name, "direction": self.direction,
            "samples": self.samples,
            "wheelspin_events": self.wheelspin_events, "lockup_events": self.lockup_events,
            "wheelspin_by_phase": dict(self.wheelspin_by_phase),
            "lockup_by_phase": dict(self.lockup_by_phase),
            "spin_axle_counts": dict(self.spin_axle_counts),
            "lock_axle_counts": dict(self.lock_axle_counts),
            "avg_throttle": round(self.avg_throttle, 3),
            "avg_brake": round(self.avg_brake, 3),
            "exit_gear": self.exit_gear, "exit_rpm_avg": self.exit_rpm_avg,
        }


class _Acc:
    __slots__ = ("segment_id", "turn", "display_name", "direction", "samples",
                 "spin_events", "lock_events", "spin_phase", "lock_phase",
                 "spin_axle", "lock_axle", "throttle_sum", "brake_sum",
                 "exit_gears", "exit_rpms", "in_spin", "in_lock")

    def __init__(self, segment_id, turn, display_name, direction):
        self.segment_id = segment_id
        self.turn = turn
        self.display_name = display_name
        self.direction = direction
        self.samples = 0
        self.spin_events = 0
        self.lock_events = 0
        self.spin_phase: dict = {}
        self.lock_phase: dict = {}
        self.spin_axle: dict = {}
        self.lock_axle: dict = {}
        self.throttle_sum = 0.0
        self.brake_sum = 0.0
        self.exit_gears: list = []
        self.exit_rpms: list = []
        self.in_spin = False
        self.in_lock = False

    def to_aggregate(self) -> CornerTelemetryAggregate:
        gear = None
        if self.exit_gears:
            gear = max(set(self.exit_gears), key=self.exit_gears.count)  # modal gear
        rpm = (sum(self.exit_rpms) / len(self.exit_rpms)) if self.exit_rpms else None
        n = max(1, self.samples)
        return CornerTelemetryAggregate(
            segment_id=self.segment_id, turn=self.turn,
            display_name=self.display_name, direction=self.direction,
            samples=self.samples, wheelspin_events=self.spin_events,
            lockup_events=self.lock_events, wheelspin_by_phase=dict(self.spin_phase),
            lockup_by_phase=dict(self.lock_phase), spin_axle_counts=dict(self.spin_axle),
            lock_axle_counts=dict(self.lock_axle),
            avg_throttle=self.throttle_sum / n, avg_brake=self.brake_sum / n,
            exit_gear=gear, exit_rpm_avg=(round(rpm, 0) if rpm is not None else None))


class LiveCornerAggregator:
    """Thread-safe accumulator of per-corner slip evidence over a session."""

    def __init__(self):
        self._lock = threading.Lock()
        self._corners: dict = {}

    def add_sample(self, *, segment_id: str, turn=None, phase: str = "",
                   display_name: str = "", direction: str = "", slip=None,
                   throttle: float = 0.0, brake: float = 0.0,
                   gear=None, rpm=None) -> None:
        """Fold one classified frame into its corner. ``slip`` is a wheel_slip.SlipSample.

        Wheelspin/lockup are counted as discrete edge-triggered EVENTS (a latch per
        corner), matching the recorder's per-lap counting, so a long slide counts once.
        """
        if not segment_id:
            return
        with self._lock:
            acc = self._corners.get(segment_id)
            if acc is None:
                acc = _Acc(segment_id, turn, display_name, direction)
                self._corners[segment_id] = acc
            acc.samples += 1
            acc.throttle_sum += float(throttle or 0.0)
            acc.brake_sum += float(brake or 0.0)

            kind = getattr(slip, "kind", "clean") if slip is not None else "clean"
            axle = getattr(slip, "axle", "") if slip is not None else ""
            if kind == "wheelspin":
                if not acc.in_spin:
                    acc.spin_events += 1
                    if phase:
                        acc.spin_phase[phase] = acc.spin_phase.get(phase, 0) + 1
                    if axle:
                        acc.spin_axle[axle] = acc.spin_axle.get(axle, 0) + 1
                    acc.in_spin = True
            else:
                acc.in_spin = False
            if kind == "lockup":
                if not acc.in_lock:
                    acc.lock_events += 1
                    if phase:
                        acc.lock_phase[phase] = acc.lock_phase.get(phase, 0) + 1
                    if axle:
                        acc.lock_axle[axle] = acc.lock_axle.get(axle, 0) + 1
                    acc.in_lock = True
            else:
                acc.in_lock = False

            if phase == "exit" and gear:
                acc.exit_gears.append(int(gear))
                if rpm:
                    acc.exit_rpms.append(float(rpm))

    def finalize(self) -> list:
        """Snapshot the accumulated corners (those with at least one sample)."""
        with self._lock:
            return [a.to_aggregate() for a in self._corners.values() if a.samples > 0]

    def reset(self) -> None:
        with self._lock:
            self._corners.clear()


def observed_symptom(agg: CornerTelemetryAggregate):
    """The dominant measured symptom for a corner, or None if the evidence is too thin.

    Returns ``(phase, symptom, severity, evidence_str)``. Wheelspin on the driven axle
    reads as a "loose" (traction/power-oversteer) symptom at its dominant phase; front/
    axle lockup under braking reads as a "loose" (brake-instability) symptom.
    """
    if agg.samples < _MIN_SAMPLES:
        return None
    spin, lock = agg.wheelspin_events, agg.lockup_events
    if spin < _MIN_EVENTS and lock < _MIN_EVENTS:
        return None
    severity = "high" if max(spin, lock) >= 5 else "medium"
    if spin >= lock and spin >= _MIN_EVENTS:
        phase = (max(agg.wheelspin_by_phase, key=agg.wheelspin_by_phase.get)
                 if agg.wheelspin_by_phase else "exit")
        axle = (max(agg.spin_axle_counts, key=agg.spin_axle_counts.get)
                if agg.spin_axle_counts else "rear")
        ev = f"{spin} wheelspin event(s), {axle} axle (measured live)"
        return (phase or "exit", "loose", severity, ev)
    if lock >= _MIN_EVENTS:
        phase = (max(agg.lockup_by_phase, key=agg.lockup_by_phase.get)
                 if agg.lockup_by_phase else "braking")
        axle = (max(agg.lock_axle_counts, key=agg.lock_axle_counts.get)
                if agg.lock_axle_counts else "front")
        ev = f"{lock} lockup event(s), {axle} axle (measured live)"
        return (phase if phase in ("braking", "entry") else "braking", "loose",
                severity, ev)
    return None


def diagnoses_from_telemetry(aggregates: list, segments: list) -> list:
    """Turn per-corner aggregates into telemetry-grounded corner diagnoses.

    Each corner with a clear measured signature becomes a ``CornerFeedback`` fed to
    :func:`strategy.corner_diagnosis.diagnose_corner_feedback` with
    ``telemetry_available=True``. Returns a list of diagnosis JSON dicts (each tagged
    with the measured evidence + source).
    """
    from strategy.corner_diagnosis import CornerFeedback, diagnose_corner_feedback
    out = []
    for agg in (aggregates or []):
        obs = observed_symptom(agg)
        if obs is None:
            continue
        phase, symptom, severity, evidence = obs
        ref = agg.turn if agg.turn is not None else (agg.display_name or agg.segment_id)
        fb = CornerFeedback(corner_ref=ref, phase=phase, symptom=symptom,
                            severity=severity)
        diag = diagnose_corner_feedback(fb, segments, telemetry_available=True)
        d = diag.as_json()
        d["telemetry_evidence"] = evidence
        d["source"] = "live_telemetry"
        d["samples"] = agg.samples
        out.append(d)
    return out
