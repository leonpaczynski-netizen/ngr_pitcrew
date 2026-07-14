"""Per-corner diagnosis + telemetry calibration (pure, Qt-free) — Engineering-Brain
Phase 5.

The plan: a corner-scoped complaint ("not hooking up at the apex, especially Corner 2")
must resolve to the actual track corner, identify WHICH PHASE it happens in, separate the
candidate causes (front-grip limit vs LSD preload vs excessive accel-lock vs insufficient
rear support vs wrong gear vs poor compliance), and — when speed / wheel-slip telemetry is
unavailable — reduce confidence and prescribe a PRECISE test rather than guess.

This module is that reasoning. It resolves the corner against the reviewed track segments,
buckets the complaint by phase, maps it to candidate causes (each with the setup fields
and handling targets involved), and attaches a controlled test when the evidence to pick
between causes is missing. It authors no setup values and calls no AI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as _dc_field
from typing import Optional


# Corner phases.
PHASE_ENTRY = "entry"
PHASE_APEX = "apex"
PHASE_EXIT = "exit"
PHASE_BRAKING = "braking"


@dataclass(frozen=True)
class CornerReference:
    resolved: bool
    turn: Optional[int]
    display_name: str
    apex_progress: Optional[float]     # 0..1
    direction: str
    confidence: str                    # high (matched a reviewed corner) / low (unresolved)
    note: str = ""


def _norm(s) -> str:
    return str(s or "").strip().lower()


def parse_corner_number(text: str) -> Optional[int]:
    """Pull a corner number from 'Corner 2' / 'T2' / 'turn 2' / '#2'."""
    if text is None:
        return None
    m = re.search(r"(?:corner|turn|t|#)\s*0*(\d{1,2})", str(text).lower())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def resolve_corner_reference(corner_ref, segments: list) -> CornerReference:
    """Resolve a corner reference (a turn number, or text like 'Corner 2') against the
    reviewed track segments (apex_zone entries carry turn_number + apex progress +
    direction). Honest low-confidence result when it cannot be matched."""
    num = corner_ref if isinstance(corner_ref, int) else parse_corner_number(corner_ref)
    apexes = [s for s in (segments or [])
              if isinstance(s, dict) and _norm(s.get("segment_type")) in
              ("apex_zone", "corner_apex", "apex")]
    if num is not None:
        for a in apexes:
            if a.get("turn_number") == num:
                return CornerReference(
                    True, num,
                    str(a.get("reviewed_display_name") or a.get("original_display_name")
                        or a.get("display_name") or f"Turn {num}"),
                    _num(a.get("lap_progress_mid")), _norm(a.get("direction")), "high")
        # Number given but no matching reviewed corner.
        return CornerReference(False, num, f"Turn {num}", None, "", "low",
                               "corner named but no reviewed segment matches — confirm the "
                               "track model or the corner number")
    return CornerReference(False, None, str(corner_ref or "unspecified corner"), None, "",
                           "low", "no corner number given — resolve the corner before a "
                           "corner-specific change")


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CornerFeedback:
    corner_ref: object                 # turn number or text
    phase: str                         # entry/apex/exit/braking
    symptom: str                       # e.g. "not_hooking_up" / "understeer" / "loose"
    severity: str = "medium"


# Phase + symptom → candidate causes. Each cause: {cause, fields, targets, needs}.
# `needs` lists the telemetry evidence required to CONFIRM this cause over the others.
_CORNER_CAUSES: dict = {
    (PHASE_APEX, "not_hooking_up"): [
        {"cause": "LSD preload too low (diff not connecting off the apex)",
         "fields": ("lsd_initial",), "targets": ("apex_connection",),
         "needs": ("throttle trace at apex", "rear wheel-slip by wheel")},
        {"cause": "front grip limit (front won't take the load at the apex)",
         "fields": ("aero_front", "arb_front", "camber_front"),
         "targets": ("apex_front_support",),
         "needs": ("front slip angle / steering vs yaw",)},
    ],
    (PHASE_APEX, "understeer"): [
        {"cause": "front grip limit", "fields": ("arb_front", "aero_front", "toe_front"),
         "targets": ("apex_front_support", "entry_rotation"),
         "needs": ("front slip / steering vs yaw",)},
    ],
    (PHASE_EXIT, "loose"): [
        {"cause": "excessive acceleration lock (whole-axle power oversteer)",
         "fields": ("lsd_accel",), "targets": ("power_oversteer_resistance",),
         "needs": ("rear wheel-slip by wheel", "throttle vs yaw on exit")},
        {"cause": "insufficient rear support",
         "fields": ("aero_rear", "toe_rear", "arb_rear"),
         "targets": ("power_oversteer_resistance", "exit_traction"),
         "needs": ("rear grip / ride height under load",)},
        {"cause": "wrong gear (too short — spikes torque on exit)",
         "fields": ("final_drive", "gear_2", "gear_3"),
         "targets": ("exit_traction",),
         "needs": ("gear + RPM at corner exit", "wheel-slip vs gear")},
    ],
    (PHASE_ENTRY, "loose"): [
        {"cause": "coast/brake-side diff or rear platform on entry",
         "fields": ("lsd_decel", "brake_bias", "ride_height_rear"),
         "targets": ("trail_braking_stability",),
         "needs": ("brake trace vs yaw on entry",)},
    ],
    (PHASE_BRAKING, "loose"): [
        {"cause": "brake bias too rearward / engine-braking instability",
         "fields": ("brake_bias", "lsd_decel"),
         "targets": ("trail_braking_stability",),
         "needs": ("per-axle brake lock", "straight-line vs trail-brake lock")},
    ],
}

# Loose symptom vocabulary → canonical symptom key.
_SYMPTOM_ALIASES = {
    "not_hooking_up": "not_hooking_up", "not hooking up": "not_hooking_up",
    "wont_connect": "not_hooking_up", "floaty": "not_hooking_up",
    "understeer": "understeer", "pushes": "understeer", "won't turn": "understeer",
    "loose": "loose", "oversteer": "loose", "steps out": "loose", "snap": "loose",
    "lock": "loose", "locks": "loose", "nervous": "loose", "wag": "loose",
}


def _canonical_symptom(symptom: str) -> str:
    s = _norm(symptom)
    for k, v in _SYMPTOM_ALIASES.items():
        if k in s:
            return v
    return s


@dataclass(frozen=True)
class CornerDiagnosis:
    corner: CornerReference
    phase: str
    symptom: str
    causes: list                       # candidate causes (dicts)
    confidence: str
    controlled_test: str
    fields_involved: tuple

    def as_json(self) -> dict:
        return {
            "corner": {"resolved": self.corner.resolved, "turn": self.corner.turn,
                       "name": self.corner.display_name,
                       "apex_progress": self.corner.apex_progress,
                       "direction": self.corner.direction,
                       "confidence": self.corner.confidence, "note": self.corner.note},
            "phase": self.phase, "symptom": self.symptom,
            "causes": [dict(c) for c in self.causes],
            "confidence": self.confidence,
            "controlled_test": self.controlled_test,
            "fields_involved": list(self.fields_involved),
        }


def diagnose_corner_feedback(
    feedback: CornerFeedback, segments: list, *, telemetry_available: bool = False,
) -> CornerDiagnosis:
    """Resolve the corner, list the candidate causes for the phase+symptom, and — when the
    telemetry to pick between them is unavailable — reduce confidence and prescribe a
    precise controlled test instead of guessing a single cause."""
    corner = resolve_corner_reference(feedback.corner_ref, segments)
    phase = _norm(feedback.phase) or PHASE_APEX
    symptom = _canonical_symptom(feedback.symptom)
    causes = _CORNER_CAUSES.get((phase, symptom), [])

    fields: tuple = tuple({f for c in causes for f in c.get("fields", ())})
    # Confidence: high only when the corner resolved AND telemetry can separate causes
    # AND there is a single candidate cause; otherwise reduced.
    if not causes:
        conf = "low"
    elif corner.resolved and telemetry_available and len(causes) == 1:
        conf = "high"
    elif corner.resolved and (telemetry_available or len(causes) == 1):
        conf = "medium"
    else:
        conf = "low"

    if len(causes) > 1 and not telemetry_available:
        needs = sorted({n for c in causes for n in c.get("needs", ())})
        test = (f"{len(causes)} candidate causes at {corner.display_name} "
                f"({', '.join(c['cause'].split(' (')[0] for c in causes)}). Capture "
                + ", ".join(needs) + " over 3 clean laps to tell them apart before changing "
                "the differential/aero/gearing — do not guess a single cause.")
    elif not corner.resolved:
        test = (f"Resolve the corner first: {corner.note}. Then log the corner's telemetry "
                "to confirm the cause.")
    elif not telemetry_available and causes:
        needs = sorted({n for c in causes for n in c.get("needs", ())})
        test = ("Confirm with a targeted run capturing " + ", ".join(needs) +
                f" at {corner.display_name} before applying the change.")
    else:
        test = ""

    return CornerDiagnosis(corner, phase, symptom, causes, conf, test, fields)


# Free-text phase cues.
_PHASE_CUES = (
    (PHASE_BRAKING, ("under braking", "braking", "on the brakes", "trail brak")),
    (PHASE_EXIT, ("on exit", "exit", "on throttle", "on power", "corner exit", "drive off")),
    (PHASE_APEX, ("apex", "mid-corner", "mid corner", "hooking up", "connect")),
    (PHASE_ENTRY, ("entry", "turn-in", "turn in", "on the way in")),
)


def diagnose_from_feeling(feeling: str, segments: list, *,
                          telemetry_available: bool = False):
    """Best-effort per-corner diagnosis from free-text feedback: only fires when a corner
    number is mentioned. Returns a CornerDiagnosis, or None when no corner is named."""
    if not feeling:
        return None
    num = parse_corner_number(feeling)
    if num is None:
        return None
    text = _norm(feeling)
    phase = PHASE_APEX
    for ph, cues in _PHASE_CUES:
        if any(c in text for c in cues):
            phase = ph
            break
    symptom = _canonical_symptom(feeling)
    return diagnose_corner_feedback(
        CornerFeedback(num, phase, symptom), segments,
        telemetry_available=telemetry_available)
