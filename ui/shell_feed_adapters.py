"""Adapters mapping canonical domain outputs -> new-shell view-models (live wiring).

Each function turns a real service's output into the view-model a shell surface
renders, so the surfaces show *real* data rather than sample data. Every adapter is
defensive: unknown/missing fields fall back sensibly and nothing raises. The mappings
are best-effort against the documented service shapes and should be sanity-checked
against real GT7/DB data during UAT.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Live Pit Wall  <-  adaptive_live_strategy.LiveStrategyState
# ---------------------------------------------------------------------------
def live_pit_wall_vm_from_state(state, *, connected: bool = True):
    from ui.components.live_pit_wall import LivePitWallVM
    if state is None:
        return LivePitWallVM(freshness="live" if connected else "none",
                             engineer_instruction="" if connected else "Waiting for live telemetry…")
    g = lambda a: getattr(state, a, None)

    cur, rem = g("current_lap"), g("laps_remaining")
    if cur is not None and rem is not None:
        lap = f"{cur} / {cur + rem}"
    elif cur is not None:
        lap = str(cur)
    else:
        lap = "—"

    fuel = "—"
    if g("fuel_remaining_l") is not None:
        fuel = f"{g('fuel_remaining_l'):.1f} L"
        fpl = g("fuel_per_lap_actual") or g("fuel_per_lap_plan")
        if fpl:
            try:
                fuel += f" ({int(g('fuel_remaining_l') / fpl)} laps)"
            except Exception:
                pass

    tyre = g("current_compound") or "—"
    if g("tyre_age_laps") is not None:
        tyre = f"{tyre} · {g('tyre_age_laps')} laps"

    stint = "—"
    if g("pit_stops_completed") is not None:
        stint = f"After {g('pit_stops_completed')} stop(s)"
        if g("laps_since_pit") is not None:
            stint += f" · L{g('laps_since_pit')}"

    gap = "—"
    la, lp = g("lap_time_actual_s"), g("lap_time_plan_s")
    if la is not None and lp is not None:
        d = la - lp
        gap = "on plan" if abs(d) < 0.05 else f"{d:+.1f}s"

    fresh = "live" if g("telemetry_fresh") else "stale"
    if not connected:
        fresh = "none"

    stops = g("required_stops")
    pit_window = f"{stops} stop(s) required" if stops is not None else "—"

    return LivePitWallVM(
        lap=lap, position="—", stint=stint, fuel=fuel, tyre=tyre,
        pit_window=pit_window, gap_to_plan=gap,
        engineer_instruction="", next_decision="",
        freshness=fresh, confidence="unknown", map_trust="none",
    )


# ---------------------------------------------------------------------------
# Race Strategy  <-  ui.race_strategy_vm.RacePlanViewModel
# ---------------------------------------------------------------------------
def _conf_key(label: str) -> str:
    s = (label or "").strip().lower()
    if "high" in s:
        return "high"
    if "med" in s or "moderate" in s:
        return "medium"
    if "low" in s:
        return "low"
    return "unknown"


def strategy_plan_vm_from_rpvm(rpvm):
    from ui.components.strategy_plan import StrategyPlanVM, StrategyOption, StrategyInput
    if rpvm is None or not getattr(rpvm, "has_recommendation", False):
        return StrategyPlanVM()

    stints = tuple(
        f"{r.get('laps', '?')} {r.get('compound', '')}".strip()
        for r in (getattr(rpvm, "stint_plan_rows", None) or [])
    )
    options = []
    cand_rows = getattr(rpvm, "candidate_comparison_rows", None) or []
    if cand_rows:
        for r in cand_rows:
            recommended = str(r.get("status", "")).lower().startswith("recomm")
            options.append(StrategyOption(
                name=str(r.get("strategy", "Strategy")),
                total_time=str(r.get("total_time", "")),
                tyre_sequence=str(r.get("compounds", "")),
                pit_windows=(f"{r.get('pit_stops', '')} stop(s)"
                             if r.get("pit_stops") is not None else ""),
                confidence=_conf_key(str(r.get("confidence", ""))),
                summary=("" if str(r.get("risk", "—")) in ("—", "") else f"Risk: {r.get('risk')}"),
                stints=stints if recommended else (),
                recommended=recommended,
            ))
    else:
        options.append(StrategyOption(
            name=str(getattr(rpvm, "recommended_strategy_title", "Recommended")),
            total_time=str(getattr(rpvm, "estimated_total_time", "")),
            confidence=_conf_key(str(getattr(rpvm, "confidence_label", ""))),
            summary=str(getattr(rpvm, "driver_explanation", "")),
            stints=stints, recommended=True,
        ))

    risks = tuple((str(f), "") for f in (getattr(rpvm, "risk_flags", None) or []))
    inputs = tuple(
        StrategyInput(name=str(r.get("label", "")), value=str(r.get("detail", "")),
                      source=str(r.get("category", "assumed")))
        for r in (getattr(rpvm, "evidence_source_rows", None) or [])
    )
    inputs += tuple(
        StrategyInput(name=str(m), value="", source="missing")
        for m in (getattr(rpvm, "missing_evidence_rows", None) or [])
    )
    return StrategyPlanVM(options=tuple(options), risks=risks, inputs=inputs,
                          replan_triggers=tuple(getattr(rpvm, "warnings", None) or []))


# ---------------------------------------------------------------------------
# Qualifying readiness  <-  Event Command Centre view dict
# ---------------------------------------------------------------------------
def _readiness_status(level: str) -> str:
    s = (level or "").strip().lower()
    if any(t in s for t in ("ready", "ok", "green", "locked", "done", "complete", "pass")):
        return "ok"
    if any(t in s for t in ("block", "missing", "red", "fail", "not ")):
        return "blocked"
    return "warn"


def qualifying_vm_from_cc_view(view, *, active_setup_label: str = "", soft_confirmed: Optional[bool] = None):
    from ui.components.qualifying_readiness import QualifyingReadinessVM, ReadinessItem
    if not isinstance(view, dict) or not view.get("ok", True):
        return QualifyingReadinessVM()
    items = []
    if active_setup_label:
        items.append(ReadinessItem("Qualifying setup selected", "ok", active_setup_label))
    if soft_confirmed is not None:
        items.append(ReadinessItem("Soft tyres confirmed",
                                   "ok" if soft_confirmed else "blocked",
                                   "" if soft_confirmed else "Fit Soft tyres for qualifying"))
    for row in (view.get("readiness") or []):
        try:
            name, level, note = (list(row) + ["", "", ""])[:3]
        except Exception:
            continue
        if not name:
            continue
        items.append(ReadinessItem(str(name), _readiness_status(str(level)), str(note)))

    blockers = tuple(
        str(a.get("message", "")) for a in (view.get("attention") or [])
        if isinstance(a, dict) and str(a.get("tone", "")).lower() in ("warn", "danger")
        and str(a.get("message", ""))
    )
    na = view.get("next_action") or {}
    explanation = str(na.get("detail", "") or "")
    return QualifyingReadinessVM(items=tuple(items), explanation=explanation, blockers=blockers)


# ---------------------------------------------------------------------------
# Practice run card  <-  the current setup recommendation (what's being tested)
# ---------------------------------------------------------------------------
def run_card_vm_from_recommendation(rec_vm, *, active_setup_label: str = ""):
    from ui.components.run_card import RunCardVM
    if rec_vm is None or not getattr(rec_vm, "has_recommendation", False):
        return RunCardVM()
    rows = list(rec_vm.proposed_rows())
    changes = tuple(
        f"{r.setting} {r.current_value}→{r.recommended_value}".strip() for r in rows
    )
    # Corners/behaviours to watch come from the changes' target symptoms.
    monitor = tuple(dict.fromkeys(
        c.symptom for c in (getattr(rec_vm, "why_cards", None) or ()) if getattr(c, "symptom", "")
    ))
    issue = getattr(rec_vm.header, "primary_issue", "") if getattr(rec_vm, "header", None) else ""
    expected = ""
    for c in (getattr(rec_vm, "why_cards", None) or ()):
        if getattr(c, "rationale", ""):
            expected = c.rationale
            break
    return RunCardVM(
        objective=(f"Validate the recommended changes for {issue}" if issue
                   else "Validate the recommended setup changes"),
        setup_label=active_setup_label,
        changes=changes,
        expected_effect=expected,
        monitor=monitor,
        purpose="diagnosis",
        target_laps="3–5",
        push_level="Representative pace",
        invalidation=("A lock-up or off-track that skews the lap",),
    )


# ---------------------------------------------------------------------------
# Debrief  <-  session_db.build_cross_session_memory (conservative top-level map)
# ---------------------------------------------------------------------------
def debrief_vm_from_memory(mem, *, next_label: str = "Continue development", next_key: str = "continue"):
    from ui.components.debrief_view import DebriefVM
    if not isinstance(mem, dict) or mem.get("insufficient"):
        return DebriefVM()

    def _names(items, *keys):
        out = []
        for it in (items or []):
            if isinstance(it, dict):
                for k in keys:
                    if it.get(k):
                        out.append(str(it.get(k)))
                        break
            elif it:
                out.append(str(it))
        return tuple(out)

    issues = mem.get("issues") or {}
    resolved = issues.get("resolved") if isinstance(issues, dict) else None
    remaining = issues.get("remaining") if isinstance(issues, dict) else None
    band = str(mem.get("band", "") or mem.get("scorecard_band", "") or "")

    return DebriefVM(
        what_happened=(f"Development band: {band}." if band else ""),
        improved=_names(resolved, "label", "issue_type", "detail"),
        regressed=_names(mem.get("regressions"), "label", "detail"),
        learned=_names(mem.get("protected_knowledge") or mem.get("behaviour"), "label", "detail"),
        carry_forward=_names(mem.get("protected_behaviours"), "label", "detail"),
        contradictions=_names(mem.get("contradictions"), "label", "detail"),
        setup_outcome=str(mem.get("latest_setup_outcome", "") or ""),
        primary_action_label=next_label, primary_action_key=next_key,
    )
