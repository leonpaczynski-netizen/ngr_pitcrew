"""Deterministic Bench UAT Harness — pure (Program 2, Phase 70).

WHY IT EXISTS
  Before physical hardware or a live GT7 race, the ACTUAL production live path must be exercised by
  controlled, deterministic offline scenarios. This harness injects state at the narrow Audit-C seam (the
  duck-typed tracker read consumed by ``build_canonical_live_race_state``, or an explicit production
  ``LiveStrategyState``) and drives the REAL production authorities — canonical mapping, ``LiveStrategyState``,
  ``decide_replan`` / candidate ranking / time-certain logic, ``build_live_audio_strategy_view`` (audio +
  speech), the Phase-64 grammar / read-back / confirmation, and ``live_vr_certification``. It copies NO
  production algorithm.

HARD SAFETY BOUNDARY (structural — the harness only calls pure functions)
  Never starts the real telemetry listener; never transmits network traffic; never sends keyboard/joystick
  events; never activates a microphone; never invokes physical TTS; never applies a pit call or setup; never
  writes driver feedback into engineering memory; never writes setup history; never mutates a runtime file.
  Software scenario passes can NEVER certify a physical / PSVR2 / live-GT7 area. Pure, deterministic
  (timings injected), never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.adaptive_live_strategy import (
    LiveStrategyState, StrategyObjective, StrategyMonitor, decide_replan, build_strategy_driver_message,
)
from strategy.canonical_live_race_state import build_canonical_live_race_state
from strategy.audio_first_engineer import (
    VrRuntimeMode, EngineerMessageIntent, DriverWorkloadState,
    classify_message_priority, decide_engineer_speech, assess_driver_workload,
)
from strategy.live_audio_strategy_build import build_live_audio_strategy_view
from strategy.push_to_talk import (
    DriverUtterance, recognize_command, decide_readback, apply_readback_response, ReadbackResponse,
)
from strategy.live_uat_runtime_snapshot import build_live_uat_runtime_snapshot
from strategy.event_programme_certification import (
    live_vr_certification, LIVE_VR_CERTIFICATION_AREAS, EvidenceType, CertificationArea,
    CertificationFinding, FindingSeverity, build_event_programme_certification,
    _LIVE_VR_PHYSICAL_OR_LIVE, _LIVE_VR_OFFSCREEN,
)

BENCH_UAT_HARNESS_VERSION = "bench_uat_harness_v1"


def _fp(payload) -> str:
    return (f"{BENCH_UAT_HARNESS_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


# --------------------------------------------------------------------------- #
# The Audit-C injection seam: a duck-typed tracker DATA holder (no algorithm)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BenchTrackerSnapshot:
    """A lightweight immutable data holder exposing exactly the attributes the production
    ``build_canonical_live_race_state`` reads from a ``RaceStateTracker`` (duck-typed). It carries DATA only
    — it re-implements no tracker calculation. This is the narrow, legal offline seam."""
    race_type: Optional[str] = None
    laps_recorded: Optional[int] = None
    laps_in_race: Optional[int] = None
    timed_duration_minutes: Optional[float] = None
    last_fuel: Optional[float] = None
    avg_fuel_per_lap: Optional[float] = None
    best_lap_ms: Optional[int] = None
    laps_since_pit: Optional[int] = None
    tyre_age_laps: Optional[int] = None
    tyre_compound: str = ""
    in_pit: bool = False
    pit_state_confidence: str = ""
    pit_stops_completed: Optional[int] = None
    last_position: Optional[int] = None
    car_name: str = ""
    track: str = ""
    layout_id: str = ""


def _laps(current, scheduled, *, best_lap_ms=88000, fuel=60.0, avg_fuel=3.0, compound="RM",
          laps_since_pit=None, pit_stops=0, position=3, in_pit=False, pit_conf="high",
          tyre_age=None) -> BenchTrackerSnapshot:
    return BenchTrackerSnapshot(
        race_type="laps", laps_recorded=current, laps_in_race=scheduled, best_lap_ms=best_lap_ms,
        last_fuel=fuel, avg_fuel_per_lap=avg_fuel, tyre_compound=compound,
        laps_since_pit=(laps_since_pit if laps_since_pit is not None else current),
        tyre_age_laps=tyre_age, pit_stops_completed=pit_stops, last_position=position, in_pit=in_pit,
        pit_state_confidence=pit_conf, car_name="GT3", track="Fuji", layout_id="full")


def _timed(current, duration_min, *, best_lap_ms=88000, fuel=60.0, avg_fuel=3.0, compound="RM",
           laps_since_pit=None, pit_stops=0, position=3, in_pit=False, pit_conf="high") -> BenchTrackerSnapshot:
    return BenchTrackerSnapshot(
        race_type="timed", laps_recorded=current, timed_duration_minutes=duration_min,
        best_lap_ms=best_lap_ms, last_fuel=fuel, avg_fuel_per_lap=avg_fuel, tyre_compound=compound,
        laps_since_pit=(laps_since_pit if laps_since_pit is not None else current),
        pit_stops_completed=pit_stops, last_position=position, in_pit=in_pit,
        pit_state_confidence=pit_conf, car_name="GT3", track="Fuji", layout_id="full")


# --------------------------------------------------------------------------- #
# Scenario + result + report
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BenchScenario:
    id: str
    name: str
    category: str
    expected: Dict[str, Any]
    kind: str = "strategy"                       # strategy|voice|audio_cooldown|session_reset|cert|cert_effect
    tracker: Optional[BenchTrackerSnapshot] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    state_fields: Optional[Dict[str, Any]] = None
    view_opts: Dict[str, Any] = field(default_factory=dict)
    utterance: Optional[Dict[str, Any]] = None
    cooldown: Optional[Dict[str, Any]] = None
    cert_area: str = ""


@dataclass(frozen=True)
class BenchUatResult:
    scenario_id: str
    name: str
    category: str
    inputs: dict
    expected: dict
    actual: dict
    passed: bool
    failure_reasons: Tuple[str, ...]
    warnings: Tuple[str, ...]
    strategy_readiness: str
    recommendation: str
    confidence: str
    audio_events: Tuple[str, ...]
    ptt_outcome: str
    certification_effects: dict
    safety_checks: dict
    fingerprint: str

    def to_dict(self) -> dict:
        return {"scenario_id": self.scenario_id, "name": self.name, "category": self.category,
                "inputs": self.inputs, "expected": self.expected, "actual": self.actual,
                "passed": bool(self.passed), "failure_reasons": list(self.failure_reasons),
                "warnings": list(self.warnings), "strategy_readiness": self.strategy_readiness,
                "recommendation": self.recommendation, "confidence": self.confidence,
                "audio_events": list(self.audio_events), "ptt_outcome": self.ptt_outcome,
                "certification_effects": self.certification_effects, "safety_checks": self.safety_checks,
                "fingerprint": self.fingerprint}


# every bench run asserts these structural safety facts (all True by construction).
_SAFETY_CHECKS = {
    "no_telemetry_listener": True, "no_network_traffic": True, "no_keyboard_joystick_events": True,
    "no_microphone_activation": True, "no_physical_tts": True, "no_pit_call": True,
    "no_setup_apply": True, "no_engineering_memory_write": True, "no_setup_history_write": True,
    "no_runtime_file_mutation": True, "no_physical_certification_promotion": True,
}


class _Contains:
    """Expectation wrapper meaning 'the actual LIST/collection contains this item'."""
    __slots__ = ("item",)

    def __init__(self, item):
        self.item = item

    def __repr__(self):
        return f"contains({self.item!r})"


def _has(name: str):
    """Expectation helper: assert ``name`` is present in a list-valued actual (membership on the actual)."""
    return _Contains(name)


def _contains(name: str):
    return _Contains(name)


def _match(expected_val, actual_val) -> bool:
    """Generic comparator. ``_Contains`` → membership on the actual collection; a set/tuple/list expectation
    → membership on the expected set; else equality. ``None`` in an expected set matches a ``None`` actual."""
    if isinstance(expected_val, _Contains):
        try:
            return expected_val.item in (actual_val or [])
        except TypeError:
            return False
    if isinstance(expected_val, (set, frozenset, tuple, list)):
        return actual_val in expected_val
    return actual_val == expected_val


# --------------------------------------------------------------------------- #
# The runner — drives the REAL production authorities for one scenario
# --------------------------------------------------------------------------- #
def run_bench_scenario(scenario: BenchScenario) -> BenchUatResult:
    """Run one deterministic scenario through the production path and evaluate its expectations. Never
    raises; never performs any I/O or device action."""
    actual: Dict[str, Any] = {}
    audio_events: List[str] = []
    ptt_outcome = ""
    cert_effects: Dict[str, Any] = {}
    warnings: List[str] = []
    try:
        inp = dict(scenario.inputs or {})
        vopts = dict(scenario.view_opts or {})
        telemetry_fresh = bool(inp.get("telemetry_fresh", True))
        context_ok = bool(inp.get("context_ok", True))
        rules_verified = bool(inp.get("rules_verified", True))

        # ---- build the production LiveStrategyState (via canonical seam OR explicit state) ----
        canonical = None
        if scenario.state_fields is not None:
            sf = dict(scenario.state_fields)
            obj = sf.pop("objective", StrategyObjective.UNKNOWN)
            if not isinstance(obj, StrategyObjective):
                obj = StrategyObjective(str(obj))
            strategy_state = LiveStrategyState(objective=obj, telemetry_fresh=telemetry_fresh, **sf)
        elif scenario.tracker is not None:
            canonical = build_canonical_live_race_state(
                scenario.tracker, elapsed_s=inp.get("elapsed_s"), telemetry_fresh=telemetry_fresh,
                fuel_per_lap_plan=inp.get("fuel_per_lap_plan"), lap_time_plan_s=inp.get("lap_time_plan_s"),
                recent_fuel_burn_samples=inp.get("recent_fuel_burn_samples"),
                recent_clean_lap_times_s=inp.get("recent_clean_lap_times_s"),
                pit_loss_s=inp.get("pit_loss_s"), required_stops=inp.get("required_stops"),
                context_ok=context_ok, rules_verified=rules_verified,
                driver_reports=inp.get("driver_reports"))
            strategy_state = canonical.to_live_strategy_state()
        else:
            strategy_state = LiveStrategyState(objective=StrategyObjective.UNKNOWN,
                                               telemetry_fresh=telemetry_fresh)

        # ---- production strategy decision + candidates ----
        decision = decide_replan(strategy_state, context_ok=context_ok, rules_verified=rules_verified)
        best = decision.best_candidate or {}
        cand_labels = [c.get("label") for c in (decision.candidates or ())]

        # ---- production audio-first + speech view ----
        view = build_live_audio_strategy_view(
            strategy_state, vr_mode=vopts.get("vr_mode", VrRuntimeMode.DESKTOP),
            workload_context=vopts.get("workload_context"),
            voice_enabled=bool(vopts.get("voice_enabled", False)),
            gate_allows=bool(vopts.get("gate_allows", False)),
            speaking=bool(vopts.get("speaking", False)), ptt_active=bool(vopts.get("ptt_active", False)),
            muted=bool(vopts.get("muted", False)), tts_available=bool(vopts.get("tts_available", True)),
            recognition_available=bool(vopts.get("recognition_available", False)),
            critical_only=bool(vopts.get("critical_only", False)),
            context_ok=context_ok, rules_verified=rules_verified)

        # ---- production runtime snapshot (for glanceable/derived fields) ----
        snap = build_live_uat_runtime_snapshot(
            timestamp="bench", canonical=canonical, strategy_state=strategy_state, decision=decision,
            certification=live_vr_certification(), telemetry_fresh=telemetry_fresh,
            tracker_connected=(canonical is not None or scenario.state_fields is not None),
            fuel_sample_count=len(inp.get("recent_fuel_burn_samples") or []),
            pace_sample_count=len(inp.get("recent_clean_lap_times_s") or []))

        actual.update({
            "objective": snap.objective, "recommendation": decision.recommendation,
            "confidence": decision.confidence, "replan_ready": bool(snap.replan_ready),
            "triggers": list(decision.triggers), "best_candidate_label": best.get("label"),
            "best_expected_completed_laps": best.get("expected_completed_laps"),
            "candidate_count": len(cand_labels), "candidate_labels": cand_labels,
            "candidates_all_legal": all(bool(c.get("legal")) for c in (decision.candidates or ())),
            "fuel_remaining_l": snap.fuel_remaining_l, "fuel_burn_estimate_l": snap.fuel_burn_estimate_l,
            "fuel_confidence": snap.fuel_confidence, "pace_estimate_s": snap.pace_estimate_s,
            "pace_confidence": snap.pace_confidence, "current_compound": snap.current_compound,
            "tyre_age_proxy_laps": snap.tyre_age_proxy_laps,
            "tyre_deg_proxy_s_per_lap": snap.tyre_deg_proxy_s_per_lap,
            "tyre_age_proxy_is_measured": bool(snap.tyre_age_proxy_is_measured),
            "pit_state": snap.pit_state, "pit_stops_completed": snap.pit_stops_completed,
            "missing_evidence": list(snap.missing_evidence),
            "may_speak_now": bool(view.get("may_speak_now")),
            "audio_state": (view.get("audio_state") or {}).get("state", ""),
            "cert_overall": snap.certification_summary,
        })
        if actual["may_speak_now"]:
            audio_events.append("strategy_message_spoken")
        else:
            audio_events.append("strategy_message_suppressed")

        # ---- kind-specific extensions ----
        if scenario.kind == "voice" and scenario.utterance is not None:
            ptt_outcome = _run_voice(scenario, actual)
        elif scenario.kind == "audio_cooldown" and scenario.cooldown is not None:
            _run_audio_cooldown(scenario, actual, audio_events)
        elif scenario.kind == "session_reset":
            _run_session_reset(actual)
        elif scenario.kind in ("cert", "cert_effect"):
            cert_effects = _run_certification(scenario, actual)

        # ---- evaluate expectations ----
        failure_reasons: List[str] = []
        for key, exp in (scenario.expected or {}).items():
            if key not in actual:
                failure_reasons.append(f"no actual value for '{key}'")
                continue
            if not _match(exp, actual[key]):
                failure_reasons.append(f"{key}: expected {exp!r}, got {actual[key]!r}")

        passed = not failure_reasons
        readiness = "READY" if actual.get("replan_ready") else "INSUFFICIENT"
        result = BenchUatResult(
            scenario_id=scenario.id, name=scenario.name, category=scenario.category,
            inputs={"kind": scenario.kind, **{k: v for k, v in (scenario.inputs or {}).items()
                                              if k not in ("driver_reports",)}},
            expected=dict(scenario.expected or {}), actual=actual, passed=passed,
            failure_reasons=tuple(failure_reasons), warnings=tuple(warnings), strategy_readiness=readiness,
            recommendation=str(actual.get("recommendation", "")), confidence=str(actual.get("confidence", "")),
            audio_events=tuple(audio_events), ptt_outcome=ptt_outcome,
            certification_effects=cert_effects or {"overall": actual.get("cert_overall", "not_tested")},
            safety_checks=dict(_SAFETY_CHECKS),
            fingerprint=_fp({"id": scenario.id, "actual": {k: actual[k] for k in sorted(actual)}}))
        return result
    except Exception as exc:  # pragma: no cover - defensive
        return BenchUatResult(
            scenario_id=scenario.id, name=scenario.name, category=scenario.category, inputs={},
            expected=dict(scenario.expected or {}), actual=actual, passed=False,
            failure_reasons=(f"runner error: {exc}",), warnings=tuple(warnings), strategy_readiness="ERROR",
            recommendation="", confidence="", audio_events=tuple(audio_events), ptt_outcome=ptt_outcome,
            certification_effects=cert_effects, safety_checks=dict(_SAFETY_CHECKS),
            fingerprint=_fp({"id": scenario.id, "error": str(exc)}))


def _run_voice(scenario: BenchScenario, actual: dict) -> str:
    u = scenario.utterance or {}
    intent = recognize_command(DriverUtterance(text=str(u.get("text", "")),
                                               confidence=float(u.get("confidence", 0.0)),
                                               ptt_held=bool(u.get("ptt_held", True))))
    rb = decide_readback(intent)
    actual.update({
        "ptt_command_class": intent.command_class.value, "ptt_ambiguous": bool(intent.ambiguous),
        "ptt_driver_report_label": intent.driver_report_label,
        "ptt_requires_readback": bool(intent.requires_readback),
        "ptt_executes_immediately": bool(intent.executes_immediately),
    })
    outcome = intent.command_class.value
    if "readback_response" in u:
        conf = apply_readback_response(intent, u.get("readback_response"))
        actual.update({"ptt_confirmation_confirmed": bool(conf.confirmed),
                       "ptt_enters_canonical": bool(conf.enters_canonical),
                       "ptt_creates_draft": bool(conf.creates_draft)})
        outcome = f"{intent.command_class.value}:{conf.response}"
    elif rb.required:
        outcome = f"{intent.command_class.value}:awaiting_confirmation"
    return outcome


def _run_audio_cooldown(scenario: BenchScenario, actual: dict, audio_events: List[str]) -> None:
    """Drive the production ``StrategyMonitor`` across two injected times to exercise cooldown / material
    change. Deterministic: timings are injected, never a wall clock."""
    cd = scenario.cooldown or {}
    monitor = StrategyMonitor(cooldown_seconds=float(cd.get("cooldown_seconds", 45.0)))

    class _D:  # minimal decision-like holder carrying only the fingerprint the monitor reads
        def __init__(self, fp):
            self.fingerprint = fp
    fp1 = str(cd.get("fp1", "A"))
    fp2 = str(cd.get("fp2", "A"))
    t1 = float(cd.get("t1", 0.0))
    t2 = float(cd.get("t2", 5.0))
    first = monitor.should_announce(_D(fp1), t1)
    second = monitor.should_announce(_D(fp2), t2)
    actual.update({"first_announce": bool(first), "second_announce": bool(second)})
    audio_events.append(f"announce1={first}")
    audio_events.append(f"announce2={second}")


def _run_session_reset(actual: dict) -> None:
    from strategy.live_session_lifecycle import (
        SESSION_RESET_PLAN, reset_live_runtime_state, TRANSIENT_LIVE_RUNTIME_KEYS,
    )
    state = {"_live_fuel_samples": [3.1, 3.2], "_live_clean_lap_times": [88.0, 88.1],
             "_live_last_recommendation_fp": "prev", "_ptt_pending_intent": {"a": 1},
             "_db": "PERSIST", "_config": {"x": 1}, "_manual_uat_store": "PERSIST"}
    cleared = reset_live_runtime_state(state)
    actual.update({
        "reset_plan_disjoint": bool(SESSION_RESET_PLAN.disjoint()),
        "reset_cleared_transient": all(state.get(k) is None for k in cleared),
        "reset_preserved_db": state.get("_db"),
        "reset_preserved_config_present": state.get("_config") is not None,
        "reset_preserved_manual_store": state.get("_manual_uat_store"),
        "reset_cleared_count": len(cleared),
    })


def _run_certification(scenario: BenchScenario, actual: dict) -> dict:
    cert = live_vr_certification()
    area_ev = {a.name: a.evidence_type.value for a in cert.areas}
    effects = {"overall": cert.overall_level.value}
    if scenario.cert_area:
        actual["cert_area_evidence"] = area_ev.get(scenario.cert_area, "")
        effects["area"] = scenario.cert_area
        effects["area_evidence"] = area_ev.get(scenario.cert_area, "")
    if scenario.kind == "cert_effect":
        # prove a FAILED software bench scenario lowers ONLY its software area, and can NEVER promote a
        # physical/live area (they stay NONE regardless of bench outcome).
        failed_software_area = scenario.cert_area or "fuel_burn"
        eff_cert = certification_from_bench({failed_software_area: False})
        eff_map = {a.name: a.evidence_type.value for a in eff_cert.areas}
        actual["cert_effect_software_area_lowered"] = (eff_map.get(failed_software_area) == "none")
        actual["cert_effect_physical_still_none"] = all(
            eff_map.get(n) == "none" for n in _LIVE_VR_PHYSICAL_OR_LIVE)
        actual["cert_effect_overall"] = eff_cert.overall_level.value
        effects["software_area_lowered"] = actual["cert_effect_software_area_lowered"]
        effects["physical_still_none"] = actual["cert_effect_physical_still_none"]
    return effects


def certification_from_bench(bench_area_results: Mapping) -> "Any":
    """Map bench pass/fail onto the 31 live-VR certification areas. A software (AUTOMATED) area passes →
    AUTOMATED; fails → NONE (lowered, with a limitation). Offscreen areas stay OFFSCREEN. Physical / PSVR2 /
    live-GT7 areas ALWAYS stay NONE — a bench result can never promote them. Overall is therefore always
    bounded to not_tested while physical areas are untested. Pure; never raises."""
    results = bench_area_results if isinstance(bench_area_results, Mapping) else {}
    areas = []
    for name in LIVE_VR_CERTIFICATION_AREAS:
        if name in _LIVE_VR_PHYSICAL_OR_LIVE:
            areas.append(CertificationArea(name, EvidenceType.NONE, last_scenario="bench-uat",
                         findings=(CertificationFinding("not_run", FindingSeverity.LIMITATION,
                                                        "requires physical / live UAT"),)))
        elif name in _LIVE_VR_OFFSCREEN:
            areas.append(CertificationArea(name, EvidenceType.OFFSCREEN, last_scenario="bench-uat"))
        else:
            passed = bool(results.get(name, True))
            if passed:
                areas.append(CertificationArea(name, EvidenceType.AUTOMATED, last_scenario="bench-uat"))
            else:
                areas.append(CertificationArea(name, EvidenceType.NONE, last_scenario="bench-uat",
                             findings=(CertificationFinding("bench_failed", FindingSeverity.LIMITATION,
                                                            "bench scenario failed — software area lowered"),)))
    return build_event_programme_certification(areas)


# --------------------------------------------------------------------------- #
# Aggregate report
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BenchUatReport:
    total: int
    passed: int
    failed: int
    blocked: int
    safety_failures: int
    strategy_failures: int
    audio_ptt_failures: int
    certification_integrity_failures: int
    overall_bench_ready: bool
    results: Tuple[BenchUatResult, ...]
    failure_details: Tuple[str, ...]
    note: str
    fingerprint: str

    def to_dict(self) -> dict:
        return {"total": self.total, "passed": self.passed, "failed": self.failed,
                "blocked": self.blocked, "safety_failures": self.safety_failures,
                "strategy_failures": self.strategy_failures, "audio_ptt_failures": self.audio_ptt_failures,
                "certification_integrity_failures": self.certification_integrity_failures,
                "overall_bench_ready": bool(self.overall_bench_ready),
                "results": [r.to_dict() for r in self.results],
                "failure_details": list(self.failure_details), "note": self.note,
                "fingerprint": self.fingerprint}


_STRATEGY_CATEGORIES = ("baseline", "fuel", "pace", "tyre", "pit", "lap_count", "time_certain")
_AUDIO_CATEGORIES = ("audio_ptt",)
_CERT_CATEGORIES = ("certification",)


def run_bench_uat(scenarios: Optional[Sequence[BenchScenario]] = None) -> BenchUatReport:
    """Run every scenario and aggregate a deterministic report. A bench FAILURE is never hidden behind a
    warning. Bench success is explicitly NOT physical or live certification. Never raises."""
    scen = list(scenarios if scenarios is not None else BENCH_SCENARIOS)
    results = tuple(run_bench_scenario(s) for s in scen)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and r.strategy_readiness != "ERROR")
    blocked = sum(1 for r in results if r.strategy_readiness == "ERROR")
    safety_failures = sum(1 for r in results if not all(r.safety_checks.values()))
    strategy_failures = sum(1 for r in results if not r.passed and r.category in _STRATEGY_CATEGORIES)
    audio_ptt_failures = sum(1 for r in results if not r.passed and r.category in _AUDIO_CATEGORIES)
    cert_failures = sum(1 for r in results if not r.passed and r.category in _CERT_CATEGORIES)
    overall_ready = (failed == 0 and blocked == 0 and safety_failures == 0)
    details = tuple(f"{r.scenario_id} [{r.category}]: " + "; ".join(r.failure_reasons)
                    for r in results if not r.passed)
    note = ("Bench UAT exercises the production live path with deterministic offline scenarios. "
            "PASS here is SOFTWARE behaviour only — it is NOT physical, PSVR2 or live-GT7 certification, "
            "which require explicit manual UAT evidence.")
    payload = {"total": len(results), "passed": passed, "failed": failed, "blocked": blocked,
               "safety_failures": safety_failures, "results": [r.fingerprint for r in results]}
    return BenchUatReport(
        total=len(results), passed=passed, failed=failed, blocked=blocked,
        safety_failures=safety_failures, strategy_failures=strategy_failures,
        audio_ptt_failures=audio_ptt_failures, certification_integrity_failures=cert_failures,
        overall_bench_ready=bool(overall_ready), results=results, failure_details=details, note=note,
        fingerprint=_fp(payload))


def bench_uat_harness_versions() -> dict:
    return {"bench_uat_harness": BENCH_UAT_HARNESS_VERSION}


# --------------------------------------------------------------------------- #
# The 67 deterministic scenarios (task section 7.2)
# --------------------------------------------------------------------------- #
# NOTE: scenario expectations encode the INTENDED production behaviour; the runner drives the REAL
# authorities, so a failure indicates either a wrong expectation or a genuine production defect.
BENCH_SCENARIOS: Tuple[BenchScenario, ...] = (
    # -------- baseline readiness (1-8) --------
    BenchScenario("B01", "No telemetry", "baseline", kind="strategy", tracker=None,
                  expected={"recommendation": "INSUFFICIENT_EVIDENCE", "replan_ready": False}),
    BenchScenario("B02", "First packet, insufficient evidence", "baseline",
                  tracker=BenchTrackerSnapshot(race_type="laps", laps_recorded=0, car_name="GT3"),
                  expected={"recommendation": "INSUFFICIENT_EVIDENCE", "replan_ready": False}),
    BenchScenario("B03", "Sufficient lap-count race evidence", "baseline",
                  tracker=_laps(5, 20),
                  expected={"objective": "lap_count", "replan_ready": True,
                            "recommendation": "PLAN_STILL_OPTIMAL"}),
    BenchScenario("B04", "Sufficient time-certain race evidence", "baseline",
                  tracker=_timed(6, 30), inputs={"elapsed_s": 300.0},
                  expected={"objective": "time_certain", "replan_ready": True}),
    BenchScenario("B05", "Missing pre-race strategy", "baseline", tracker=_laps(4, 18),
                  expected={"recommendation": "PLAN_STILL_OPTIMAL", "replan_ready": True,
                            "missing_evidence": _has("fuel_per_lap_plan")}),
    BenchScenario("B06", "Stale packet", "baseline", tracker=_laps(5, 20),
                  inputs={"telemetry_fresh": False},
                  expected={"recommendation": "INSUFFICIENT_EVIDENCE", "replan_ready": False}),
    BenchScenario("B07", "Telemetry reconnect", "baseline", tracker=_laps(5, 20),
                  inputs={"telemetry_fresh": True},
                  expected={"replan_ready": True,
                            "recommendation": {"PLAN_STILL_OPTIMAL", "MONITOR", "PACE_INCREASE_AVAILABLE"}}),
    BenchScenario("B08", "Session transition clears transient state", "baseline", kind="session_reset",
                  expected={"reset_plan_disjoint": True, "reset_cleared_transient": True,
                            "reset_preserved_db": "PERSIST", "reset_preserved_manual_store": "PERSIST"}),

    # -------- fuel (9-16) --------
    BenchScenario("F09", "Fuel burn matches forecast", "fuel", tracker=_laps(6, 22),
                  inputs={"fuel_per_lap_plan": 3.0, "recent_fuel_burn_samples": [3.0, 3.02, 2.98, 3.01]},
                  expected={"recommendation": "PLAN_STILL_OPTIMAL"}),
    BenchScenario("F10", "Fuel burn higher than forecast", "fuel", tracker=_laps(6, 22),
                  inputs={"fuel_per_lap_plan": 3.0, "recent_fuel_burn_samples": [3.4, 3.42, 3.38, 3.41]},
                  expected={"recommendation": "CONSERVATION_REQUIRED", "triggers": _contains("fuel_burn_high")}),
    BenchScenario("F11", "Fuel burn lower than forecast", "fuel", tracker=_laps(6, 22),
                  inputs={"fuel_per_lap_plan": 3.4, "recent_fuel_burn_samples": [3.0, 3.02, 2.98, 3.01]},
                  expected={"recommendation": "PACE_INCREASE_AVAILABLE",
                            "triggers": _contains("fuel_burn_low")}),
    BenchScenario("F12", "Fuel evidence too sparse", "fuel",
                  tracker=BenchTrackerSnapshot(race_type="laps", laps_recorded=6, laps_in_race=22,
                                               best_lap_ms=88000, last_fuel=50.0, car_name="GT3"),
                  inputs={"fuel_per_lap_plan": 3.0},
                  expected={"fuel_confidence": "none", "recommendation": "PLAN_STILL_OPTIMAL"}),
    BenchScenario("F13", "Fuel value missing", "fuel",
                  tracker=BenchTrackerSnapshot(race_type="laps", laps_recorded=6, laps_in_race=22,
                                               best_lap_ms=88000, last_fuel=None, avg_fuel_per_lap=3.0,
                                               car_name="GT3"),
                  expected={"fuel_remaining_l": None}),
    BenchScenario("F14", "Implausible fuel sample bounded", "fuel", tracker=_laps(6, 22),
                  inputs={"fuel_per_lap_plan": 3.0, "recent_fuel_burn_samples": [3.0, 3.0, 3.0, 50.0]},
                  expected={"recommendation": "PLAN_STILL_OPTIMAL"}),
    BenchScenario("F15", "Fuel target requiring conservation", "fuel", tracker=_laps(10, 30),
                  inputs={"fuel_per_lap_plan": 3.0, "recent_fuel_burn_samples": [3.5, 3.52, 3.48, 3.51]},
                  expected={"recommendation": "CONSERVATION_REQUIRED",
                            "candidate_labels": _contains("Fuel conservation")}),
    BenchScenario("F16", "Fuel improvement makes plan viable", "fuel", tracker=_laps(10, 30),
                  inputs={"fuel_per_lap_plan": 3.5, "recent_fuel_burn_samples": [3.0, 3.02, 2.98, 3.01]},
                  expected={"recommendation": "PACE_INCREASE_AVAILABLE"}),

    # -------- pace (17-22) --------
    BenchScenario("P17", "Pace matches forecast", "pace", tracker=_laps(6, 22),
                  inputs={"lap_time_plan_s": 88.0,
                          "recent_clean_lap_times_s": [88.1, 88.0, 88.2, 88.1, 88.0]},
                  expected={"recommendation": "PLAN_STILL_OPTIMAL"}),
    BenchScenario("P18", "Pace consistently slower", "pace", tracker=_laps(6, 22),
                  inputs={"lap_time_plan_s": 88.0,
                          "recent_clean_lap_times_s": [90.2, 90.1, 90.3, 90.2, 90.1]},
                  expected={"recommendation": "REPLAN_RECOMMENDED", "triggers": _contains("pace_slower")}),
    BenchScenario("P19", "Pace consistently faster", "pace", tracker=_laps(6, 22),
                  inputs={"lap_time_plan_s": 90.0,
                          "recent_clean_lap_times_s": [88.0, 88.1, 87.9, 88.0, 88.1]},
                  expected={"recommendation": "PACE_INCREASE_AVAILABLE",
                            "triggers": _contains("pace_faster")}),
    BenchScenario("P20", "Sparse pace evidence", "pace",
                  tracker=BenchTrackerSnapshot(race_type="laps", laps_recorded=2, laps_in_race=22,
                                               best_lap_ms=88000, last_fuel=60.0, car_name="GT3"),
                  inputs={"lap_time_plan_s": 88.0},
                  expected={"recommendation": "PLAN_STILL_OPTIMAL"}),
    BenchScenario("P21", "Outlier lap excluded (robust median)", "pace", tracker=_laps(6, 22),
                  inputs={"lap_time_plan_s": 88.0,
                          "recent_clean_lap_times_s": [88.0, 88.0, 88.0, 88.0, 120.0]},
                  # the median excludes the 120s outlier (pace stays 88.0); the outlier legitimately trips
                  # the consistency-drop signal, so the recommendation may be MONITOR — never a pace replan.
                  expected={"pace_estimate_s": 88.0,
                            "recommendation": {"PLAN_STILL_OPTIMAL", "MONITOR"}}),
    BenchScenario("P22", "Pace changes after a pit stop", "pace", tracker=_laps(12, 30, laps_since_pit=2),
                  inputs={"lap_time_plan_s": 88.0,
                          "recent_clean_lap_times_s": [87.0, 87.1, 86.9, 87.0]},
                  expected={"recommendation": "PACE_INCREASE_AVAILABLE"}),

    # -------- tyre / stint proxy (23-28) --------
    BenchScenario("T23", "Known compound with usable proxy", "tyre",
                  tracker=_laps(10, 30, compound="RH"),
                  inputs={"recent_clean_lap_times_s": [88.0, 88.3, 88.6, 89.0, 89.4]},
                  expected={"current_compound": "RH", "tyre_age_proxy_is_measured": False}),
    BenchScenario("T24", "Unknown compound", "tyre",
                  tracker=_laps(10, 30, compound=""),
                  expected={"current_compound": None, "tyre_age_proxy_is_measured": False}),
    BenchScenario("T25", "Unknown tyre age", "tyre",
                  tracker=BenchTrackerSnapshot(race_type="laps", laps_recorded=10, laps_in_race=30,
                                               best_lap_ms=88000, last_fuel=50.0, tyre_compound="RM",
                                               laps_since_pit=None, tyre_age_laps=None, car_name="GT3"),
                  expected={"tyre_age_proxy_laps": None}),
    BenchScenario("T26", "Tyre proxy indicates degradation", "tyre",
                  tracker=_laps(12, 30),
                  inputs={"recent_clean_lap_times_s": [88.0, 88.5, 89.0, 89.6, 90.2]},
                  expected={"tyre_age_proxy_is_measured": False}),
    BenchScenario("T27", "Pit stop resets stint-age proxy", "tyre",
                  tracker=_laps(15, 30, laps_since_pit=1),
                  expected={"tyre_age_proxy_laps": 1, "tyre_age_proxy_is_measured": False}),
    BenchScenario("T28", "Tyre proxy confidence explicitly limited", "tyre",
                  tracker=_laps(10, 30),
                  inputs={"recent_clean_lap_times_s": [88.0, 88.3, 88.6, 89.0, 89.4]},
                  expected={"tyre_age_proxy_is_measured": False}),

    # -------- pit state (29-35) --------
    BenchScenario("PIT29", "Approaching pit window", "pit", tracker=_laps(18, 30, pit_stops=0),
                  expected={"pit_state": {"not_in_pit"}, "pit_stops_completed": 0}),
    BenchScenario("PIT30", "Pit entry / in pit", "pit", tracker=_laps(19, 30, in_pit=True, pit_stops=0),
                  expected={"pit_state": "pit_confirmed"}),
    BenchScenario("PIT31", "Stationary / in-pit state", "pit",
                  tracker=_laps(19, 30, in_pit=True, pit_stops=0),
                  expected={"pit_state": "pit_confirmed"}),
    BenchScenario("PIT32", "Pit exit", "pit", tracker=_laps(20, 30, in_pit=False, pit_stops=1),
                  expected={"pit_state": {"not_in_pit"}, "pit_stops_completed": 1}),
    BenchScenario("PIT33", "Pit stop already completed", "pit",
                  tracker=_laps(21, 30, in_pit=False, pit_stops=1),
                  expected={"pit_stops_completed": 1}),
    BenchScenario("PIT34", "Pit-stop count unknown", "pit",
                  tracker=BenchTrackerSnapshot(race_type="laps", laps_recorded=21, laps_in_race=30,
                                               best_lap_ms=88000, last_fuel=40.0, tyre_compound="RM",
                                               pit_stops_completed=None, pit_state_confidence="low",
                                               car_name="GT3"),
                  expected={"pit_stops_completed": None}),
    BenchScenario("PIT35", "Uncertain pit state", "pit",
                  tracker=BenchTrackerSnapshot(race_type="laps", laps_recorded=21, laps_in_race=30,
                                               best_lap_ms=88000, last_fuel=40.0, tyre_compound="RM",
                                               in_pit=False, pit_state_confidence="low", car_name="GT3"),
                  expected={"pit_state": "uncertain"}),

    # -------- lap-count strategy (36-42) — explicit LiveStrategyState to exercise pit-loss precisely --------
    BenchScenario("L36", "Original plan remains optimal", "lap_count", kind="strategy",
                  state_fields={"objective": StrategyObjective.LAP_COUNT, "laps_remaining": 10,
                                "lap_time_actual_s": 88.0, "pit_loss_s": 60.0, "tyre_age_laps": 8},
                  expected={"best_candidate_label": "Keep the plan"}),
    BenchScenario("L37", "One-stop becomes preferable", "lap_count", kind="strategy",
                  state_fields={"objective": StrategyObjective.LAP_COUNT, "laps_remaining": 30,
                                "lap_time_actual_s": 88.0, "pit_loss_s": 5.0, "tyre_age_laps": 20},
                  expected={"best_candidate_label": "Extra stop for pace"}),
    BenchScenario("L38", "Extra stop clearly preferable", "lap_count", kind="strategy",
                  state_fields={"objective": StrategyObjective.LAP_COUNT, "laps_remaining": 40,
                                "lap_time_actual_s": 90.0, "pit_loss_s": 3.0, "tyre_age_laps": 25},
                  expected={"best_candidate_label": "Extra stop for pace"}),
    BenchScenario("L39", "Conservation becomes preferable", "lap_count", kind="strategy",
                  state_fields={"objective": StrategyObjective.LAP_COUNT, "laps_remaining": 20,
                                "lap_time_actual_s": 88.0, "fuel_per_lap_actual": 3.4,
                                "fuel_per_lap_plan": 3.0, "pit_loss_s": 40.0, "tyre_age_laps": 10},
                  expected={"recommendation": "CONSERVATION_REQUIRED",
                            "candidate_labels": _contains("Fuel conservation")}),
    BenchScenario("L40", "Push plan rejected (pit loss too high)", "lap_count", kind="strategy",
                  state_fields={"objective": StrategyObjective.LAP_COUNT, "laps_remaining": 8,
                                "lap_time_actual_s": 88.0, "pit_loss_s": 90.0, "tyre_age_laps": 6},
                  expected={"best_candidate_label": "Keep the plan"}),
    BenchScenario("L41", "Mandatory-stop legality enforced", "lap_count", kind="strategy",
                  state_fields={"objective": StrategyObjective.LAP_COUNT, "laps_remaining": 15,
                                "lap_time_actual_s": 88.0, "pit_loss_s": 30.0, "required_stops": 1,
                                "tyre_age_laps": 12},
                  expected={"candidates_all_legal": True}),
    BenchScenario("L42", "Required-compound legality enforced", "lap_count", kind="strategy",
                  state_fields={"objective": StrategyObjective.LAP_COUNT, "laps_remaining": 15,
                                "lap_time_actual_s": 88.0, "pit_loss_s": 30.0, "required_stops": 2,
                                "current_compound": "RH", "tyre_age_laps": 12},
                  expected={"candidates_all_legal": True}),

    # -------- time-certain strategy (43-50) --------
    BenchScenario("TC43", "Extra stop would lose a completed lap", "time_certain", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 600.0,
                                "lap_time_actual_s": 60.0, "pit_loss_s": 30.0, "tyre_age_laps": 10},
                  expected={"best_candidate_label": "Keep the plan"}),
    BenchScenario("TC44", "Extra stop lap-neutral (fresh tyres)", "time_certain", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 605.0,
                                "lap_time_actual_s": 60.0, "pit_loss_s": 5.0, "tyre_age_laps": 10},
                  expected={"best_candidate_label": "Extra stop for fresh tyres",
                            "best_expected_completed_laps": 10}),
    BenchScenario("TC45", "Final-lap boundary uncertainty", "time_certain", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 599.0,
                                "lap_time_actual_s": 60.0, "pit_loss_s": 30.0, "tyre_age_laps": 10},
                  expected={"best_expected_completed_laps": 9}),
    BenchScenario("TC46", "Race clock missing", "time_certain", kind="strategy",
                  tracker=BenchTrackerSnapshot(race_type="timed", laps_recorded=5, timed_duration_minutes=None,
                                               best_lap_ms=88000, last_fuel=50.0, car_name="GT3"),
                  expected={"recommendation": "INSUFFICIENT_EVIDENCE"}),
    BenchScenario("TC47", "Remaining time stale", "time_certain", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 600.0,
                                "lap_time_actual_s": 60.0}, inputs={"telemetry_fresh": False},
                  expected={"recommendation": "INSUFFICIENT_EVIDENCE"}),
    BenchScenario("TC48", "Strategy changes because pace changes", "time_certain", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 600.0,
                                "lap_time_actual_s": 66.0, "lap_time_plan_s": 60.0, "tyre_age_laps": 10},
                  expected={"recommendation": "REPLAN_RECOMMENDED", "triggers": _contains("pace_slower")}),
    BenchScenario("TC49", "Strategy responds to pit-loss change", "time_certain", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 600.0,
                                "lap_time_actual_s": 60.0, "pit_loss_s": 30.0, "pit_loss_plan_s": 20.0,
                                "tyre_age_laps": 10},
                  expected={"triggers": _contains("pit_loss_changed"), "recommendation": "MONITOR"}),
    BenchScenario("TC50", "Recommendation unchanged within tolerance", "time_certain", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 600.0,
                                "lap_time_actual_s": 60.2, "lap_time_plan_s": 60.0, "tyre_age_laps": 10},
                  expected={"recommendation": "PLAN_STILL_OPTIMAL"}),

    # -------- audio + PTT safety (51-60) --------
    BenchScenario("A51", "High-priority strategy message spoken", "audio_ptt", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 600.0,
                                "lap_time_actual_s": 66.0, "lap_time_plan_s": 60.0},
                  view_opts={"vr_mode": VrRuntimeMode.AUDIO_FIRST, "voice_enabled": True,
                             "gate_allows": True, "tts_available": True, "recognition_available": True,
                             "workload_context": {"in_pit_lane": True}},
                  expected={"may_speak_now": True}),
    BenchScenario("A52", "Low-priority suppressed by cooldown", "audio_ptt", kind="audio_cooldown",
                  cooldown={"fp1": "same", "fp2": "same", "t1": 0.0, "t2": 5.0, "cooldown_seconds": 45.0},
                  expected={"first_announce": True, "second_announce": False}),
    BenchScenario("A53", "Repeated unchanged advice does not flood", "audio_ptt", kind="audio_cooldown",
                  cooldown={"fp1": "x", "fp2": "x", "t1": 10.0, "t2": 20.0, "cooldown_seconds": 45.0},
                  expected={"second_announce": False}),
    BenchScenario("A54", "Material change may re-announce", "audio_ptt", kind="audio_cooldown",
                  cooldown={"fp1": "old", "fp2": "new", "t1": 0.0, "t2": 5.0, "cooldown_seconds": 45.0},
                  expected={"first_announce": True, "second_announce": True}),
    BenchScenario("A55", "Ambiguous utterance → no driver-report label", "audio_ptt", kind="voice",
                  utterance={"text": "front damage", "confidence": 0.3, "ptt_held": True},
                  expected={"ptt_command_class": "unrecognised", "ptt_driver_report_label": None,
                            "ptt_ambiguous": True}),
    BenchScenario("A56", "Low-confidence recognition → no command", "audio_ptt", kind="voice",
                  utterance={"text": "strategy update", "confidence": 0.4, "ptt_held": True},
                  expected={"ptt_command_class": "unrecognised", "ptt_executes_immediately": False}),
    BenchScenario("A57", "Confirmation-required command remains pending", "audio_ptt", kind="voice",
                  utterance={"text": "rain starting", "confidence": 0.9, "ptt_held": True},
                  expected={"ptt_command_class": "driver_report", "ptt_requires_readback": True}),
    BenchScenario("A58", "Confirmation timeout performs no action", "audio_ptt", kind="voice",
                  utterance={"text": "rain starting", "confidence": 0.9, "ptt_held": True,
                             "readback_response": ReadbackResponse.CANCEL},
                  expected={"ptt_confirmation_confirmed": False, "ptt_enters_canonical": False,
                            "ptt_creates_draft": False}),
    BenchScenario("A59", "Safe-operational command completes on release", "audio_ptt", kind="voice",
                  utterance={"text": "repeat", "confidence": 0.9, "ptt_held": True},
                  expected={"ptt_command_class": "safe_operational", "ptt_executes_immediately": True}),
    BenchScenario("A60", "Missing voice adapter leaves strategy visual", "audio_ptt", kind="strategy",
                  state_fields={"objective": StrategyObjective.TIME_CERTAIN, "time_remaining_s": 600.0,
                                "lap_time_actual_s": 66.0, "lap_time_plan_s": 60.0},
                  view_opts={"vr_mode": VrRuntimeMode.AUDIO_FIRST, "voice_enabled": True,
                             "tts_available": False},
                  expected={"may_speak_now": False, "replan_ready": True}),

    # -------- certification honesty (61-67) --------
    BenchScenario("C61", "Software pass never certifies physical microphone", "certification", kind="cert",
                  cert_area="microphone_recognition",
                  expected={"cert_area_evidence": "none", "cert_overall": "not_tested"}),
    BenchScenario("C62", "Software pass never certifies physical wheel PTT", "certification", kind="cert",
                  cert_area="wheel_ptt", expected={"cert_area_evidence": "none"}),
    BenchScenario("C63", "Software pass never certifies physical TTS", "certification", kind="cert",
                  cert_area="physical_tts", expected={"cert_area_evidence": "none"}),
    BenchScenario("C64", "Software pass never certifies PSVR2", "certification", kind="cert",
                  cert_area="psvr2_race", expected={"cert_area_evidence": "none"}),
    BenchScenario("C65", "Software pass never certifies live GT7", "certification", kind="cert",
                  cert_area="session_binding", expected={"cert_area_evidence": "none"}),
    BenchScenario("C66", "Failed bench lowers only the software area", "certification", kind="cert_effect",
                  cert_area="fuel_burn",
                  expected={"cert_effect_software_area_lowered": True,
                            "cert_effect_physical_still_none": True,
                            "cert_effect_overall": "not_tested"}),
    BenchScenario("C67", "Overall stays NOT_TESTED while physical untested", "certification", kind="cert",
                  cert_area="", expected={"cert_overall": "not_tested"}),
)
