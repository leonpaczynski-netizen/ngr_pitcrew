"""Immutable Runtime Snapshot adapter (Program 2, Phase 44).

Assembles the immutable per-evaluation runtime snapshot the live advisory engine reasons over, by
MAPPING existing canonical inputs (the context fingerprint, the run plan, the assisted-workflow state,
the Phase-42 material trust, and a telemetry frame). It creates NO second telemetry authority - it only
normalises already-available fields into a stable snapshot dict.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no WALL-CLOCK; deterministic;
never raises.
"""
from __future__ import annotations

from typing import Mapping, Optional, Sequence

RUNTIME_SNAPSHOT_VERSION = "runtime_snapshot_v1"

_HIGH_WORKLOAD = {"braking", "turn_in", "apex", "corner_entry", "corner"}


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def build_runtime_snapshot(*, context_fingerprint: str = "", run_plan: Optional[Mapping] = None,
                           workflow: Optional[Mapping] = None, material_trust: Optional[Mapping] = None,
                           telemetry: Optional[Mapping] = None,
                           passed_corners: Optional[Sequence[str]] = None,
                           plan_conflicts: Optional[Sequence[str]] = None,
                           event_is_near: bool = False,
                           strategy_evidence_incomplete: bool = False) -> dict:
    """Build the immutable runtime snapshot. ``telemetry`` is a read-only frame with lap/clean_laps/
    segment/workload/in_pit/at_finish_line/telemetry_fresh/compound. Deterministic; never raises."""
    try:
        rp = run_plan if isinstance(run_plan, Mapping) else {}
        wf = workflow if isinstance(workflow, Mapping) else {}
        mt = material_trust if isinstance(material_trust, Mapping) else {}
        tm = telemetry if isinstance(telemetry, Mapping) else {}
        segment = _lc(tm.get("segment_type"))
        workload = _lc(tm.get("workload")) or ("high" if segment in _HIGH_WORKLOAD else "low")
        state = _lc(wf.get("state"))
        rs = rp.get("run_structure") or {}
        min_clean = int(rs.get("minimum_clean_laps") or 0)
        clean = int(tm.get("clean_laps") or 0)
        compound_used = _lc(tm.get("compound"))
        planned_compound = _lc((rp.get("held_constant") or {}).get("compound")) \
            or _lc((rp.get("context") or {}).get("compound"))
        wrong_compound = bool(compound_used and planned_compound and planned_compound not in
                              ("as-planned", "") and compound_used != planned_compound)
        return {
            "context_fingerprint": _norm(context_fingerprint),
            "run_plan_fingerprint": _norm(rp.get("content_fingerprint")),
            "run_active": state in ("run_active",) or bool(tm.get("run_active")),
            "lap": int(tm.get("lap") or 0), "clean_laps": clean,
            "telemetry_fresh": bool(tm.get("telemetry_fresh", True)),
            "telemetry_unavailable": bool(tm.get("telemetry_unavailable")),
            "plan_current": bool(wf.get("plan_current", True) if "plan_current" in wf else True),
            "session_active": bool(tm.get("session_active", True)),
            "segment_type": segment, "workload": workload, "in_pit": bool(tm.get("in_pit")),
            "at_finish_line": bool(tm.get("at_finish_line")),
            "before_measurement": bool(tm.get("before_measurement")),
            "approaching_corner": _norm(tm.get("approaching_corner")),
            "passed_corners": [ _norm(c) for c in (passed_corners or tm.get("passed_corners") or []) ],
            "plan_conflicts": [ _norm(c) for c in (plan_conflicts or []) ],
            "context_trust": _lc(mt.get("overall_trust")),
            "setup_mismatch": _lc(wf.get("state")) == "invalid"
            and any("setup" in _lc(b) for b in (wf.get("blockers") or [])),
            "mismatch_reason": "; ".join(wf.get("blockers") or []),
            "wrong_compound": wrong_compound,
            "run_invalidated": state == "invalid",
            "stop_condition_reached": bool(tm.get("stop_condition_reached")),
            "stop_condition_reason": _norm(tm.get("stop_condition_reason")),
            "coaching_suppressed": bool(tm.get("coaching_suppressed")),
            "repetition_permitted": bool((rp.get("run_structure") or {}).get("repetition_permitted")),
            "event_is_near": bool(event_is_near),
            "strategy_evidence_incomplete": bool(strategy_evidence_incomplete),
            "min_clean_laps": min_clean, "eval_version": RUNTIME_SNAPSHOT_VERSION}
    except Exception:  # pragma: no cover - defensive
        return {"context_fingerprint": _norm(context_fingerprint), "run_active": False,
                "telemetry_fresh": False, "eval_version": RUNTIME_SNAPSHOT_VERSION}


def snapshot_versions() -> dict:
    return {"runtime_snapshot": RUNTIME_SNAPSHOT_VERSION}
