"""Live UAT Runtime Snapshot — pure, immutable, read-only (Program 2, Phase 69).

WHY IT EXISTS
  Before physical UAT the complete production live path must be *observable* without changing it. This is
  the ONE canonical, immutable snapshot of the current production runtime state — session/event identity,
  telemetry freshness, the canonical race-state availability matrix, fuel/pace/tyre-proxy/pit evidence,
  strategy readiness + recommendation, voice/PTT state and the honest certification summary — composed from
  the REAL production objects (``CanonicalLiveRaceState``, ``LiveStrategyState``, ``StrategyReplanDecision``,
  ``LiveEngineerAudioSnapshot``, ``EventProgrammeCertification``).

DOCTRINE
  Deterministic, offline, DB-free, Qt-free. The builder READS the production objects — it mutates nothing,
  recalculates no business logic (it reuses the canonical availability/confidence labels), records unknowns
  explicitly, labels the tyre-age *proxy* honestly (never as measured tyre condition), and NEVER raises.
  No wall clock: every timestamp is an injected string. No secrets / API keys / raw packet payloads.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

LIVE_UAT_RUNTIME_SNAPSHOT_VERSION = "live_uat_runtime_snapshot_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
            return None
        return f
    except (TypeError, ValueError):
        return None


def _int(x) -> Optional[int]:
    v = _num(x)
    return int(v) if v is not None else None


def _r(x) -> Optional[float]:
    v = _num(x)
    return round(v, 2) if v is not None else None


def _fp(payload) -> str:
    return (f"{LIVE_UAT_RUNTIME_SNAPSHOT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


@dataclass(frozen=True)
class LiveUatRuntimeSnapshot:
    """Immutable read-only view of the whole production live runtime, for UAT diagnosis. Every field is
    optional; unknown stays unknown. ``tyre_age_proxy_is_measured`` is ALWAYS False — the tyre value is a
    lap-time-drift proxy, never a measured tyre condition."""
    # identity + timing (injected timestamps, never a wall clock)
    timestamp: str = ""
    session_identity: str = ""
    event_identity: str = ""
    # telemetry
    tracker_connected: bool = False
    telemetry_fresh: bool = False
    last_packet_age_s: Optional[float] = None
    # race clock / laps
    objective: str = "unknown"                 # lap_count | time_certain | unknown
    current_lap: Optional[int] = None
    completed_laps: Optional[int] = None
    total_race_laps: Optional[int] = None
    race_elapsed_s: Optional[float] = None
    race_time_remaining_s: Optional[float] = None
    expected_completed_laps: Optional[int] = None
    # fuel
    fuel_remaining_l: Optional[float] = None
    fuel_burn_sample_count: int = 0
    fuel_burn_estimate_l: Optional[float] = None
    fuel_confidence: str = "none"
    # pace
    pace_sample_count: int = 0
    pace_estimate_s: Optional[float] = None
    pace_confidence: str = "none"
    # tyre / stint (PROXY)
    current_compound: Optional[str] = None
    tyre_age_proxy_laps: Optional[int] = None
    tyre_deg_proxy_s_per_lap: Optional[float] = None
    tyre_age_proxy_is_measured: bool = False   # ALWAYS False — honest proxy label
    # pit
    pit_state: str = "unknown"
    pit_stops_completed: Optional[int] = None
    # availability + evidence
    availability_matrix: Tuple[dict, ...] = ()
    missing_evidence: Tuple[str, ...] = ()
    stale_evidence: Tuple[str, ...] = ()
    # strategy
    replan_ready: bool = False
    recommendation: str = ""
    recommendation_confidence: str = ""
    last_eval_time: str = ""
    # voice / PTT
    last_spoken_time: str = ""
    ptt_state: str = ""
    recognition_state: str = ""
    voice_state: str = ""
    voice_readiness: str = ""
    # certification
    certification_summary: str = "not_tested"
    certification_weakest_area: str = ""
    active_blockers: Tuple[str, ...] = ()
    active_warnings: Tuple[str, ...] = ()
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        """Deterministic payload for the fingerprint / diagnostics (identity strings and injected
        timestamps are volatile and EXCLUDED from the fingerprint)."""
        return {
            "tracker_connected": bool(self.tracker_connected),
            "telemetry_fresh": bool(self.telemetry_fresh),
            "objective": self.objective, "current_lap": self.current_lap,
            "completed_laps": self.completed_laps, "total_race_laps": self.total_race_laps,
            "race_time_remaining_s": _r(self.race_time_remaining_s),
            "expected_completed_laps": self.expected_completed_laps,
            "fuel_remaining_l": _r(self.fuel_remaining_l),
            "fuel_burn_sample_count": int(self.fuel_burn_sample_count),
            "fuel_burn_estimate_l": _r(self.fuel_burn_estimate_l), "fuel_confidence": self.fuel_confidence,
            "pace_sample_count": int(self.pace_sample_count), "pace_estimate_s": _r(self.pace_estimate_s),
            "pace_confidence": self.pace_confidence, "current_compound": _norm(self.current_compound),
            "tyre_age_proxy_laps": self.tyre_age_proxy_laps,
            "tyre_deg_proxy_s_per_lap": _r(self.tyre_deg_proxy_s_per_lap),
            "tyre_age_proxy_is_measured": bool(self.tyre_age_proxy_is_measured),
            "pit_state": self.pit_state, "pit_stops_completed": self.pit_stops_completed,
            "availability_matrix": list(self.availability_matrix),
            "missing_evidence": list(self.missing_evidence), "stale_evidence": list(self.stale_evidence),
            "replan_ready": bool(self.replan_ready), "recommendation": self.recommendation,
            "recommendation_confidence": self.recommendation_confidence,
            "ptt_state": self.ptt_state, "recognition_state": self.recognition_state,
            "voice_state": self.voice_state, "voice_readiness": self.voice_readiness,
            "certification_summary": self.certification_summary,
            "certification_weakest_area": _norm(self.certification_weakest_area),
            "active_blockers": list(self.active_blockers), "active_warnings": list(self.active_warnings),
        }

    def to_dict(self) -> dict:
        d = self.as_stable_payload()
        d.update({"timestamp": self.timestamp, "session_identity": self.session_identity,
                  "event_identity": self.event_identity, "last_packet_age_s": _r(self.last_packet_age_s),
                  "race_elapsed_s": _r(self.race_elapsed_s), "last_eval_time": self.last_eval_time,
                  "last_spoken_time": self.last_spoken_time, "fingerprint": self.fingerprint})
        return d


def _classify_objective(canonical, strategy_state) -> str:
    try:
        # prefer the strategy objective (already resolved), else the canonical race type
        if strategy_state is not None:
            obj = getattr(getattr(strategy_state, "objective", None), "value", None)
            if obj in ("lap_count", "time_certain"):
                return obj
        if canonical is not None:
            rt = getattr(getattr(canonical, "clock", None), "race_type", None)
            rtv = getattr(rt, "value", rt)
            if rtv == "lap":
                return "lap_count"
            if rtv == "timed":
                return "time_certain"
    except Exception:  # pragma: no cover - defensive
        pass
    return "unknown"


def _availability_and_missing(canonical) -> Tuple[Tuple[dict, ...], Tuple[str, ...]]:
    matrix = []
    missing = []
    try:
        for f in getattr(canonical, "fields", ()) or ():
            avail = getattr(getattr(f, "availability", None), "value", "")
            conf = getattr(getattr(f, "confidence", None), "value", "")
            name = _norm(getattr(f, "name", ""))
            matrix.append({"name": name, "availability": avail, "confidence": conf})
            if avail == "unavailable":
                missing.append(name)
    except Exception:  # pragma: no cover - defensive
        pass
    return tuple(matrix), tuple(missing)


def build_live_uat_runtime_snapshot(
    *,
    timestamp: str = "",
    session_identity: str = "",
    event_identity: str = "",
    tracker_connected: bool = False,
    telemetry_fresh: bool = False,
    last_packet_age_s: Optional[float] = None,
    canonical=None,
    strategy_state=None,
    decision=None,
    audio=None,
    certification=None,
    fuel_sample_count: int = 0,
    pace_sample_count: int = 0,
    ptt_state: str = "",
    recognition_state: str = "",
    last_eval_time: str = "",
    last_spoken_time: str = "",
) -> LiveUatRuntimeSnapshot:
    """Compose ONE immutable runtime snapshot from the REAL production objects. Read-only; mutates nothing;
    never raises. Missing evidence is recorded explicitly; the tyre value is labelled a proxy; unknown stays
    unknown. ``certification`` may be an ``EventProgrammeCertification`` or its payload dict."""
    try:
        # derive a strategy state from the canonical mapping if one was not supplied
        ss = strategy_state
        if ss is None and canonical is not None and hasattr(canonical, "to_live_strategy_state"):
            try:
                ss = canonical.to_live_strategy_state()
            except Exception:
                ss = None

        objective = _classify_objective(canonical, ss)

        clock = getattr(canonical, "clock", None)
        stint = getattr(canonical, "stint", None)
        pit = getattr(canonical, "pit", None)

        current_lap = _int(getattr(clock, "current_lap", None)) if clock is not None else None
        total_laps = _int(getattr(clock, "scheduled_laps", None)) if clock is not None else None
        # completed laps: in a lap race the tracker's current_lap is laps recorded/completed so far
        completed_laps = current_lap
        race_elapsed = _num(getattr(clock, "elapsed_s", None)) if clock is not None else None
        race_remaining = _num(getattr(clock, "remaining_s", None)) if clock is not None else None
        expected_completed = _int(getattr(clock, "expected_completed_laps", None)) if clock is not None else None

        fuel_remaining = _num(getattr(canonical, "fuel_remaining_l", None))
        fuel_burn = _num(getattr(canonical, "fuel_per_lap_live", None))
        pace = _num(getattr(canonical, "lap_time_live_s", None))

        compound = _norm(getattr(stint, "compound", "")) or None if stint is not None else None
        tyre_age = _int(getattr(stint, "stint_age_laps", None)) if stint is not None else None
        tyre_deg = _num(getattr(stint, "tyre_deg_per_lap_s", None)) if stint is not None else None

        pit_state = getattr(getattr(pit, "phase", None), "value", "unknown") if pit is not None else "unknown"
        pit_stops = _int(getattr(pit, "pit_stops_completed", None)) if pit is not None else None

        # confidence labels come straight from the canonical availability record (no recompute)
        fmap = {}
        try:
            fmap = canonical.field_map() if canonical is not None else {}
        except Exception:
            fmap = {}

        def _conf(field_name: str) -> str:
            rec = fmap.get(field_name)
            return getattr(getattr(rec, "confidence", None), "value", "none") if rec is not None else "none"

        fuel_conf = _conf("fuel_per_lap_live")
        pace_conf = _conf("lap_time_live_s")

        matrix, missing = _availability_and_missing(canonical)
        missing_list = list(missing)
        # the richer pre-race plan is a distinct, honestly-absent input (Audit-A forward hooks)
        if ss is not None:
            if _num(getattr(ss, "fuel_per_lap_plan", None)) is None:
                missing_list.append("fuel_per_lap_plan")
            if _num(getattr(ss, "lap_time_plan_s", None)) is None:
                missing_list.append("lap_time_plan_s")
        stale = () if telemetry_fresh else ("telemetry",)

        # strategy readiness + recommendation (from the real decision if supplied)
        replan_ready = False
        recommendation = ""
        rec_conf = ""
        if decision is not None:
            recommendation = _norm(getattr(decision, "recommendation", ""))
            rec_conf = _norm(getattr(decision, "confidence", ""))
            replan_ready = recommendation not in ("", "INSUFFICIENT_EVIDENCE", "CONTEXT_MISMATCH")
        elif ss is not None:
            try:
                replan_ready = bool(ss.has_time_certain_inputs() or ss.has_lap_count_inputs())
            except Exception:
                replan_ready = False

        # voice / audio state
        voice_state = getattr(getattr(audio, "state", None), "value", "") if audio is not None else ""
        voice_readiness = getattr(getattr(audio, "readiness", None), "value", "") if audio is not None else ""

        # certification summary
        cert_payload = {}
        if certification is not None:
            if isinstance(certification, Mapping):
                cert_payload = dict(certification)
            elif hasattr(certification, "as_payload"):
                try:
                    cert_payload = certification.as_payload()
                except Exception:
                    cert_payload = {}
        cert_summary = _norm(cert_payload.get("overall_level")) or "not_tested"
        cert_weakest = _norm(cert_payload.get("weakest_area"))
        blockers = tuple(str(b) for b in (cert_payload.get("blockers") or ()))
        warnings = tuple(str(w) for w in (cert_payload.get("limitations") or ()))

        snap = LiveUatRuntimeSnapshot(
            timestamp=_norm(timestamp), session_identity=_norm(session_identity),
            event_identity=_norm(event_identity), tracker_connected=bool(tracker_connected),
            telemetry_fresh=bool(telemetry_fresh), last_packet_age_s=_num(last_packet_age_s),
            objective=objective, current_lap=current_lap, completed_laps=completed_laps,
            total_race_laps=total_laps, race_elapsed_s=race_elapsed, race_time_remaining_s=race_remaining,
            expected_completed_laps=expected_completed, fuel_remaining_l=fuel_remaining,
            fuel_burn_sample_count=max(0, _int(fuel_sample_count) or 0), fuel_burn_estimate_l=fuel_burn,
            fuel_confidence=fuel_conf, pace_sample_count=max(0, _int(pace_sample_count) or 0),
            pace_estimate_s=pace, pace_confidence=pace_conf, current_compound=compound,
            tyre_age_proxy_laps=tyre_age, tyre_deg_proxy_s_per_lap=tyre_deg,
            tyre_age_proxy_is_measured=False, pit_state=pit_state, pit_stops_completed=pit_stops,
            availability_matrix=matrix, missing_evidence=tuple(dict.fromkeys(missing_list)),
            stale_evidence=stale, replan_ready=bool(replan_ready), recommendation=recommendation,
            recommendation_confidence=rec_conf, last_eval_time=_norm(last_eval_time),
            last_spoken_time=_norm(last_spoken_time), ptt_state=_norm(ptt_state),
            recognition_state=_norm(recognition_state), voice_state=voice_state,
            voice_readiness=voice_readiness, certification_summary=cert_summary,
            certification_weakest_area=cert_weakest, active_blockers=blockers, active_warnings=warnings)
        return _stamp(snap)
    except Exception:  # pragma: no cover - defensive
        return _stamp(LiveUatRuntimeSnapshot(timestamp=_norm(timestamp)))


def _stamp(snap: LiveUatRuntimeSnapshot) -> LiveUatRuntimeSnapshot:
    import dataclasses
    return dataclasses.replace(snap, fingerprint=_fp(snap.as_stable_payload()))


def live_uat_runtime_snapshot_versions() -> dict:
    return {"live_uat_runtime_snapshot": LIVE_UAT_RUNTIME_SNAPSHOT_VERSION}
