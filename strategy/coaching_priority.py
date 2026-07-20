"""Coaching Priority & Verification — Layer 6 of the Race-Engineer Activation (Program 2, Phase 37).

Selects a SMALL number of evidence-backed coaching priorities from the driver-development state and
the recorded per-corner evidence. Each priority is a falsifiable coaching hypothesis with: the
affected corner/segment/phase, the current observed behaviour, the desired behaviour, why it matters,
the evidence confidence, ONE actionable technique focus, a measurable success criterion, the telemetry
/ outcome that would confirm improvement, what would falsify the hypothesis, and whether a setup
change should be held constant during the coaching test.

Corner-level learning includes gearing and drive-out: for exit / traction / gear priorities the plan
assesses whether the chosen gear supports rotation, throttle control, wheelspin management,
acceleration, speed onto the next straight, and fuel economy where relevant.

Doctrine: coaching targets DRIVER-attributable or interaction problems, not setup-only ones (a
setup-only problem is a setup fix, not a coaching priority). A persistent per-corner issue remains a
priority across sessions until the evidence shows it resolved.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value; issues no instruction to the car.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

COACHING_PRIORITY_VERSION = "coaching_priority_v1"
COACHING_PRIORITY_SCHEMA = 1

_MAX_PRIORITIES = 3


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{COACHING_PRIORITY_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


# per-dimension coaching template: desired behaviour, technique focus, success criterion, confirming
# evidence, falsifier, why-it-matters. Deterministic; evidence-agnostic wording.
_TEMPLATE = {
    "threshold_braking": {
        "desired": "brake at the limit without lock-up and release smoothly",
        "technique": "brake slightly earlier and trail pressure off as grip returns",
        "success": "no front lock-up flags in the braking zone across 3 consecutive laps",
        "confirm": "braking-zone lock-up count falls and entry speed holds",
        "falsify": "lock-ups persist unchanged after the technique change"},
    "trail_brake_release": {
        "desired": "release the brake progressively to rotate the car on entry",
        "technique": "hold a light trailing brake to the apex, releasing linearly",
        "success": "entry rotation improves with no new mid-corner instability over 3 laps",
        "confirm": "understeer-on-entry residual clears while rear stays stable",
        "falsify": "rotation does not improve or the rear becomes unstable"},
    "turn_in_front_load": {
        "desired": "load the front tyres on turn-in to reduce entry understeer",
        "technique": "commit the turn-in earlier with a firmer initial steering input",
        "success": "entry-understeer residual reduces across 3 laps with consistent line",
        "confirm": "turn-in understeer flag reduces at the affected corner",
        "falsify": "entry understeer persists or the car snaps to oversteer"},
    "minimum_corner_speed": {
        "desired": "carry more minimum speed through mid-corner",
        "technique": "smooth the mid-corner steering and delay throttle only as needed",
        "success": "minimum-corner-speed residual reduces without running wide",
        "confirm": "mid-corner understeer flag falls and exit line is held",
        "falsify": "the car runs wide or loses exit drive"},
    "rear_stability": {
        "desired": "keep the rear stable through mid-corner and exit",
        "technique": "smoother throttle application and avoid mid-corner lifts",
        "success": "no rear-instability flags on exit across 3 laps",
        "confirm": "rear-instability residual clears at the affected corner",
        "falsify": "the rear remains unstable regardless of throttle discipline"},
    "exit_wheelspin": {
        "desired": "put the power down on exit without wheelspin",
        "technique": "progressive throttle from the apex; short-shift if traction-limited",
        "success": "no exit-wheelspin flags across 3 consecutive laps",
        "confirm": "exit-wheelspin residual clears and exit speed rises",
        "falsify": "wheelspin persists even with progressive throttle (points to setup/gear)"},
    "drive_out": {
        "desired": "maximise drive out of the corner onto the following straight",
        "technique": "earlier, smoother throttle in the correct gear for rotation and traction",
        "success": "speed onto the next straight increases with no wheelspin",
        "confirm": "drive-out / traction residual clears; trap speed rises",
        "falsify": "drive-out does not improve after gear/throttle changes"},
    "gear_selection": {
        "desired": "select the gear that supports rotation and clean drive-out",
        "technique": "test one gear higher/lower for the corner and compare drive-out",
        "success": "chosen gear gives clean rotation and no bog/wheelspin over 3 laps",
        "confirm": "drive-out and speed onto the straight improve with the selected gear",
        "falsify": "no gear choice improves rotation or drive-out (points to setup)"},
    "apex_connection": {
        "desired": "connect the apex consistently and unwind smoothly",
        "technique": "fix a repeatable apex reference and unwind steering to track-out",
        "success": "apex-connection consistency improves across 3 laps",
        "confirm": "line consistency improves at the affected corner",
        "falsify": "apex connection stays inconsistent"},
    "throttle_progression": {
        "desired": "apply throttle progressively rather than abruptly",
        "technique": "roll onto the throttle from a defined point; avoid on/off inputs",
        "success": "smoother throttle trace with no traction loss over 3 laps",
        "confirm": "traction/wheelspin residual reduces",
        "falsify": "traction problems persist with smooth throttle (points to setup)"},
    "throttle_timing": {
        "desired": "time the throttle to the car's rotation",
        "technique": "wait for rotation to complete before committing to throttle",
        "success": "cleaner exits with no early-throttle instability",
        "confirm": "early-throttle instability flag reduces",
        "falsify": "timing changes do not affect the behaviour"},
    "steering_correction": {
        "desired": "reduce mid-corner steering corrections",
        "technique": "one smooth input; avoid sawing at the wheel",
        "success": "fewer steering corrections with a steadier line",
        "confirm": "correction count / line variance falls",
        "falsify": "corrections persist regardless of input smoothness"},
    "use_of_track_width": {
        "desired": "use the available track width on entry and exit",
        "technique": "widen entry and allow the car to run to the exit kerb",
        "success": "wider, more open line with higher minimum speed",
        "confirm": "line width increases and mid-corner speed rises",
        "falsify": "using more width does not improve the corner"},
}


def _matters(dimension: str, attribution: str) -> str:
    base = {"exit_wheelspin": "exit wheelspin costs drive onto the straight and wears the rear tyre",
            "drive_out": "drive-out sets speed for the entire following straight",
            "gear_selection": "the wrong gear compromises rotation, drive-out and fuel use",
            "threshold_braking": "braking repeatability underpins both lap time and consistency",
            "trail_brake_release": "entry rotation reduces mid-corner understeer without setup change",
            "rear_stability": "rear instability costs confidence and time on exit"}.get(
                dimension, "it is a repeated, evidence-backed limitation on pace or consistency")
    if attribution == "combined":
        base += " (a driver/setup interaction - test technique with the setup held constant)"
    return base


_GEAR_DIMS = ("exit_wheelspin", "drive_out", "gear_selection", "throttle_progression")


@dataclass(frozen=True)
class CoachingPriority:
    rank: int
    dimension: str
    corner: str
    phase: str
    current_behaviour: str
    desired_behaviour: str
    why_it_matters: str
    confidence: str
    technique_focus: str
    success_criterion: str
    confirming_evidence: str
    falsifier: str
    hold_setup_constant: bool
    attribution: str
    evidence_count: int
    gear_drive_out: dict

    def to_dict(self) -> dict:
        return {"rank": self.rank, "dimension": self.dimension, "corner": self.corner,
                "phase": self.phase, "current_behaviour": self.current_behaviour,
                "desired_behaviour": self.desired_behaviour, "why_it_matters": self.why_it_matters,
                "confidence": self.confidence, "technique_focus": self.technique_focus,
                "success_criterion": self.success_criterion,
                "confirming_evidence": self.confirming_evidence, "falsifier": self.falsifier,
                "hold_setup_constant": self.hold_setup_constant, "attribution": self.attribution,
                "evidence_count": self.evidence_count, "gear_drive_out": dict(self.gear_drive_out)}


@dataclass(frozen=True)
class CoachingPlan:
    scope_fingerprint: str
    priorities: Tuple[dict, ...]
    empty_state: str
    doctrine: str
    content_fingerprint: str
    schema_version: int = COACHING_PRIORITY_SCHEMA
    eval_version: str = COACHING_PRIORITY_VERSION

    def to_dict(self) -> dict:
        return {"scope_fingerprint": self.scope_fingerprint,
                "priorities": [dict(p) for p in self.priorities], "empty_state": self.empty_state,
                "doctrine": self.doctrine, "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_DOCTRINE = ("Coaching targets driver-attributable or interaction problems, not setup-only ones. Each "
             "priority is a falsifiable hypothesis with a measurable success criterion and a defined "
             "verification; a persistent per-corner issue stays a priority until evidence shows it "
             "resolved.")

# categories that warrant coaching, most-severe first.
_CATEGORY_SEVERITY = {"development_area": 2, "emerging": 1}
_COACHABLE_ATTRIBUTION = ("likely_technique", "combined", "track_interaction")


def _gear_assessment(dimension: str, corner: str) -> dict:
    if dimension not in _GEAR_DIMS:
        return {}
    return {"corner": corner or "(corner)",
            "supports_rotation": "verify the gear lets the car rotate without bogging",
            "supports_throttle_control": "verify the gear gives fine throttle control on exit",
            "wheelspin_management": "the recorded wheelspin indicates the gear may be too low - test",
            "acceleration": "compare acceleration out of the corner between adjacent gears",
            "speed_onto_next_straight": "confirm trap speed onto the following straight improves",
            "fuel_economy": "note fuel-rate impact for Race discipline where relevant",
            "note": "coaching test only - do NOT apply a gearbox change here; that is a setup step."}


def build_coaching_plan(scope_fingerprint: str, driver_development: Optional[Mapping],
                        setup_change_in_progress: bool = False) -> CoachingPlan:
    """Select up to a few coaching priorities from the driver-development state. ``setup_change_in_
    progress`` forces hold-setup-constant so a coaching test is not confounded. Deterministic; never
    raises."""
    try:
        dd = driver_development if isinstance(driver_development, Mapping) else {}
        dims = [d for d in (dd.get("dimensions") or []) if isinstance(d, Mapping)]
        candidates = []
        for d in dims:
            cat = _lc(d.get("category"))
            attr = _lc(d.get("attribution"))
            if cat not in _CATEGORY_SEVERITY or attr not in _COACHABLE_ATTRIBUTION:
                continue
            sev = _CATEGORY_SEVERITY[cat]
            score = (sev * 100 + int(d.get("evidence_count") or 0) * 5
                     + int(d.get("session_count") or 0) * 3)
            candidates.append((score, d))
        # deterministic order: score desc, then dimension name.
        candidates.sort(key=lambda t: (-t[0], _lc(t[1].get("dimension"))))

        priorities: List[CoachingPriority] = []
        for rank, (_score, d) in enumerate(candidates[:_MAX_PRIORITIES], start=1):
            dim = _lc(d.get("dimension"))
            tmpl = _TEMPLATE.get(dim, {
                "desired": "improve this behaviour", "technique": "isolate and repeat the input",
                "success": "the residual reduces across 3 consecutive laps",
                "confirm": "the recorded residual reduces", "falsify": "the residual persists unchanged"})
            corners = d.get("corners") or []
            corner = _norm(corners[0]) if corners else ""
            attr = _lc(d.get("attribution"))
            hold = bool(setup_change_in_progress) or attr in ("likely_technique", "track_interaction",
                                                              "combined")
            priorities.append(CoachingPriority(
                rank=rank, dimension=dim, corner=corner, phase="",
                current_behaviour=f"recorded {dim.replace('_', ' ')} limitation ({d.get('trend')})",
                desired_behaviour=tmpl["desired"], why_it_matters=_matters(dim, attr),
                confidence=_norm(d.get("confidence")), technique_focus=tmpl["technique"],
                success_criterion=tmpl["success"], confirming_evidence=tmpl["confirm"],
                falsifier=tmpl["falsify"], hold_setup_constant=hold, attribution=attr,
                evidence_count=int(d.get("evidence_count") or 0),
                gear_drive_out=_gear_assessment(dim, corner)))

        empty = "" if priorities else (
            "No driver-attributable coaching priority yet - either there is not enough repeated "
            "evidence, or the recorded problems are setup-attributable (a setup step, not coaching).")
        fp = _fp({"scope": _norm(scope_fingerprint),
                  "priorities": [(p.rank, p.dimension, p.corner, p.attribution, p.hold_setup_constant)
                                 for p in priorities]})
        return CoachingPlan(scope_fingerprint=_norm(scope_fingerprint),
                            priorities=tuple(p.to_dict() for p in priorities), empty_state=empty,
                            doctrine=_DOCTRINE, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return CoachingPlan(scope_fingerprint=_norm(scope_fingerprint), priorities=(),
                            empty_state="Coaching plan unavailable.", doctrine=_DOCTRINE,
                            content_fingerprint=_fp({"error": True}))


def coaching_versions() -> dict:
    return {"coaching_priority": COACHING_PRIORITY_VERSION, "schema": COACHING_PRIORITY_SCHEMA}
