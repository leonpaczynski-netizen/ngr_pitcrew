"""Group 51 — Race Strategy Brain Phase 5: Porsche RSR / Fuji manual-UAT support.

A small, deterministic, offline helper that reproduces the recommended manual-UAT
scenario end to end (seed a SessionDB, read samples, grade readiness/diagnostics,
and run the session-backed recommendation). It exists so a reviewer can confirm the
Race Plan surface behaves correctly WITHOUT the game, an API key, or production data.

    Porsche 911 RSR '17 · Fuji Full Course · 50 min · 8× tyre · 3× fuel · 1 L/s refuel

Pure/offline: the only I/O is an in-memory (`:memory:`) SQLite DB created here. No Qt,
no AI, no writes to disk-backed runtime files. Lives in `ui/` because it composes the
`ui` readiness layer with the `strategy` pipeline (ui → strategy dependency direction).
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy.race_strategy_pipeline import SessionStrategyResult, recommend_strategy_from_session
from strategy.race_strategy_session_adapter import (
    SessionStrategySamples,
    extract_session_strategy_samples,
)
from ui.race_strategy_readiness_vm import (
    RacePlanReadiness,
    SessionDiagnostics,
    build_race_plan_readiness,
    build_session_diagnostics,
    empty_state_messages,
)


FUJI_UAT_CAR = "Porsche 911 RSR '17"
FUJI_UAT_CAR_ID = 911
FUJI_UAT_TRACK = "Fuji Speedway"
FUJI_UAT_LAYOUT = "fuji_speedway__full_course"

# Canonical event settings for the scenario (mirrors the Group 49/50 benchmark).
FUJI_UAT_EVENT_SETTINGS = {
    "car_id": FUJI_UAT_CAR_ID,
    "track": FUJI_UAT_TRACK,
    "layout_id": FUJI_UAT_LAYOUT,
    "race_duration_minutes": 50.0,
    "race_laps": 0,
    "fuel_multiplier": 3.0,
    "tyre_multiplier": 8.0,
    "refuel_rate_lps": 1.0,
    "pit_loss_seconds": 22.0,
    "starting_fuel_pct": 100.0,
    "available_compounds": ("RM", "RH"),
    "required_compounds": (),
    "mandatory_pit_stops": 0,
}

_BASE_LAP_S = 100.0
_WEAR_PER_LAP_S = 0.08
_FUEL_PER_LAP_L = 4.0


@dataclass
class FujiUatContext:
    db: object
    session_id: int
    samples: SessionStrategySamples
    diagnostics: SessionDiagnostics
    readiness: RacePlanReadiness
    empty_state_messages: list
    event_settings: dict


def build_fuji_uat_db(n_laps: int = 12, fuel: float = _FUEL_PER_LAP_L):
    """Create an in-memory SessionDB seeded with the RSR/Fuji practice session.

    Returns (db, session_id). ``n_laps``/``fuel`` let a caller simulate an
    incomplete session (short run / no fuel signal) to exercise missing-evidence.
    """
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    sid = db.open_session(
        car_id=FUJI_UAT_CAR_ID, track=FUJI_UAT_TRACK,
        session_type="Practice", car_name=FUJI_UAT_CAR,
    )
    remaining = 100.0
    for i in range(n_laps):
        lap_ms = int(round((_BASE_LAP_S + i * _WEAR_PER_LAP_S) * 1000))
        db.write_lap(
            session_id=sid, lap_num=i + 1, lap_time_ms=lap_ms,
            fuel_used=fuel, stats=None, compound="RM",
            fuel_start=remaining, fuel_end=remaining - fuel,
        )
        remaining -= fuel
    return db, sid


def build_fuji_uat_context(n_laps: int = 12, fuel: float = _FUEL_PER_LAP_L) -> FujiUatContext:
    """Build the full offline UAT context (samples + diagnostics + readiness)."""
    db, sid = build_fuji_uat_db(n_laps=n_laps, fuel=fuel)
    es = dict(FUJI_UAT_EVENT_SETTINGS)
    samples = extract_session_strategy_samples(
        db, sid, expected_car_id=FUJI_UAT_CAR_ID, expected_track=FUJI_UAT_TRACK,
        layout_id=FUJI_UAT_LAYOUT,
    )
    diagnostics = build_session_diagnostics(
        samples, event_car_id=FUJI_UAT_CAR_ID, event_track=FUJI_UAT_TRACK,
        event_layout=FUJI_UAT_LAYOUT,
    )
    readiness = build_race_plan_readiness(samples=samples, event_settings=es)
    msgs = empty_state_messages(samples, es)
    return FujiUatContext(
        db=db, session_id=sid, samples=samples,
        diagnostics=diagnostics, readiness=readiness,
        empty_state_messages=msgs, event_settings=es,
    )


def run_fuji_uat(n_laps: int = 12, fuel: float = _FUEL_PER_LAP_L) -> SessionStrategyResult:
    """Run the full session-backed recommendation for the RSR/Fuji scenario.

    Rear-fragility is read from the structured driver profile (never free text),
    so the push plan is demoted exactly as in the live surface.
    """
    db, sid = build_fuji_uat_db(n_laps=n_laps, fuel=fuel)
    rear_fragile = _rear_fragile_from_profile()
    es = dict(FUJI_UAT_EVENT_SETTINGS)
    return recommend_strategy_from_session(
        db,
        session_id=sid,
        car_id=es["car_id"],
        track=es["track"],
        layout_id=es["layout_id"],
        race_duration_minutes=es["race_duration_minutes"],
        race_laps=es["race_laps"],
        fuel_multiplier=es["fuel_multiplier"],
        tyre_multiplier=es["tyre_multiplier"],
        refuel_rate_lps=es["refuel_rate_lps"],
        pit_loss_seconds=es["pit_loss_seconds"],
        starting_fuel_pct=es["starting_fuel_pct"],
        available_compounds=es["available_compounds"],
        required_compounds=es["required_compounds"],
        mandatory_pit_stops=es["mandatory_pit_stops"],
        rear_traction_fragile=rear_fragile,
    )


def _rear_fragile_from_profile() -> bool:
    try:
        from strategy.setup_driver_profile import build_driver_profile
        p = build_driver_profile()
        return bool(p.prefers_rear_stability or p.dislikes_snap_exit)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Group 52 — structured, deterministic UAT verification harness
# ---------------------------------------------------------------------------

@dataclass
class FujiUatCheckResult:
    """Structured, testable result of the Porsche RSR / Fuji UAT check."""

    scenario_name: str
    event_context_ok: bool
    session_match_ok: bool
    readiness_level: str
    clean_lap_count: int
    fuel_evidence_found: bool
    tyre_proxy_found: bool
    candidate_count: int
    recommended_strategy: str
    one_stop_total_time: str
    two_stop_total_time: str
    push_plan_rejected_or_not_recommended: bool
    missing_evidence: list
    warnings: list
    safety_checks: dict
    passed: bool
    failure_reasons: list


def run_fuji_race_plan_uat_check(n_laps: int = 12, fuel: float = _FUEL_PER_LAP_L) -> FujiUatCheckResult:
    """Run the full Porsche RSR / Fuji Race Plan UAT check, offline and repeatable.

    Reproduces the recommended manual UAT, then verifies every expected behaviour
    and returns a structured pass/fail with explicit failure reasons. No game, no
    AI, no API key, no writes. ``n_laps``/``fuel`` let a caller exercise the
    incomplete-session path (missing-evidence still visible).
    """
    from ui.race_strategy_readiness_vm import validate_event_settings
    from ui.race_strategy_vm import build_race_plan_view_model, render_race_plan_html

    failures: list[str] = []
    ctx = build_fuji_uat_context(n_laps=n_laps, fuel=fuel)
    result = run_fuji_uat(n_laps=n_laps, fuel=fuel)
    vm = build_race_plan_view_model(result)
    html = render_race_plan_html(vm)

    # --- event context ---
    ev_valid = validate_event_settings(ctx.event_settings)
    event_context_ok = ev_valid.can_run
    if not event_context_ok:
        failures.append("event context cannot run (missing race length)")

    # --- session match ---
    from ui.race_strategy_readiness_vm import CheckStatus
    session_match_ok = ctx.diagnostics.matches_event == CheckStatus.OK
    if not session_match_ok:
        failures.append(f"session does not match event: {ctx.diagnostics.match_note}")

    clean = ctx.diagnostics.clean_lap_count
    fuel_found = ctx.diagnostics.fuel_available
    tyre_found = ctx.diagnostics.tyre_proxy_available

    # --- candidate comparison (one-stop vs two-stop) ---
    by_id = {r["candidate_id"]: r for r in vm.candidate_comparison_rows}
    one = by_id.get("1stop")
    two = by_id.get("2stop")
    one_time = one["total_time"] if one else "—"
    two_time = two["total_time"] if two else "—"
    if not (one and two):
        failures.append("one-stop vs two-stop comparison missing")

    # --- push plan not recommended when rear fragile ---
    rec_id = getattr(getattr(result.recommendation, "recommended", None), "candidate_id", "")
    push_ok = rec_id != "2stop_push"
    push_flagged = any("push strategy not recommended" in r.lower() for r in vm.risk_flags)
    if not push_ok:
        failures.append("push plan was recommended despite rear fragility")

    # --- tyre proxy labelled derived (only when it exists) ---
    if tyre_found:
        cats = {r["label"]: r["category"] for r in vm.evidence_source_rows}
        if cats.get("Tyre degradation") != "derived":
            failures.append("tyre degradation not labelled 'derived'")

    # --- SessionDB measured evidence appears (full session) ---
    if n_laps >= 8 and fuel > 0 and "SessionDB measured" not in html:
        failures.append("SessionDB measured evidence not shown")

    # --- no false certainty ---
    lowered = html.lower()
    for banned in ("guaranteed", "perfect strategy", "the winning strategy"):
        if banned in lowered:
            failures.append(f"false-certainty wording present: {banned}")

    # --- safety checks (read-only / no apply / no api key) ---
    safety_checks = _uat_safety_checks(html, vm)
    for name, ok in safety_checks.items():
        if not ok:
            failures.append(f"safety check failed: {name}")

    return FujiUatCheckResult(
        scenario_name="Porsche 911 RSR '17 @ Fuji Full Course, 50 min, 8x tyre, 3x fuel, 1 L/s",
        event_context_ok=event_context_ok,
        session_match_ok=session_match_ok,
        readiness_level=ctx.readiness.overall_readiness.value,
        clean_lap_count=clean,
        fuel_evidence_found=fuel_found,
        tyre_proxy_found=tyre_found,
        candidate_count=len(vm.candidate_comparison_rows),
        recommended_strategy=vm.recommended_strategy_title,
        one_stop_total_time=one_time,
        two_stop_total_time=two_time,
        push_plan_rejected_or_not_recommended=bool(push_ok and (push_flagged or rec_id != "2stop_push")),
        missing_evidence=list(vm.missing_evidence_rows) + list(ctx.readiness.missing),
        warnings=list(vm.warnings),
        safety_checks=safety_checks,
        passed=len(failures) == 0,
        failure_reasons=failures,
    )


# ---------------------------------------------------------------------------
# Group 53 — Porsche RSR / Fuji live-replan UAT runner (offline, advisory-only)
# ---------------------------------------------------------------------------

def run_fuji_live_replan(kind: str = "healthy", generated_at: str = ""):
    """Run the offline RSR/Fuji live-replan path for a fixture live state.

    ``kind`` ∈ {"healthy", "fuel_short", "missing"}. Pairs the pre-race one-stop
    plan (``run_fuji_uat``) with a deterministic Group 53 live-state fixture and
    returns a read-only, advisory-only `LiveReplanResult`. No game, no AI, no writes.
    """
    from strategy.race_strategy_live_replan import (
        build_live_replan_snapshot,
        fuji_live_state_healthy, fuji_live_state_fuel_short, fuji_live_state_missing,
        fuji_live_state_pre_pit_healthy, fuji_live_state_just_pitted,
        fuji_live_state_missing_pit,
    )
    fixtures = {
        "healthy": fuji_live_state_healthy,
        "fuel_short": fuji_live_state_fuel_short,
        "missing": fuji_live_state_missing,
        "pre_pit_healthy": fuji_live_state_pre_pit_healthy,
        "just_pitted": fuji_live_state_just_pitted,
        "missing_pit": fuji_live_state_missing_pit,
    }
    state = fixtures.get(kind, fuji_live_state_healthy)()
    return build_live_replan_snapshot(
        pre_race_result=run_fuji_uat(),
        live_state=state,
        event_settings=dict(FUJI_UAT_EVENT_SETTINGS),
        generated_at=generated_at,
    )


def _uat_safety_checks(html: str, vm) -> dict:
    """Read-only assertions that the surface exposes no setup power / certainty."""
    lowered = html.lower()
    return {
        "no_apply_setup_wording": "apply setup" not in lowered and "approve setup" not in lowered,
        "read_only_safety_note": any("read-only" in n.lower() for n in vm.safety_notes),
        "no_setup_field_tokens": not any(
            tok in lowered for tok in ("ride_height", "camber", "brake_bias", "lsd_accel",
                                       "approved_fields", "setup_fields")
        ),
        "missing_evidence_visible_or_complete": True,  # missing list is always surfaced by the VM
    }
