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
def live_pit_wall_vm_from_state(state, *, connected: bool = True, audio_view=None):
    """Build the LivePitWallVM from a LiveStrategyState + optional audio view.

    When ``audio_view`` is supplied (from ``build_live_audio_strategy_view``), the
    engineer_instruction, next_decision, confidence, and warning fields are populated
    from the adaptive strategy decision and message; the gap_to_plan field is also
    extended with the fuel-per-lap delta when both plan and actual are present.

    When ``audio_view`` is None the function behaves exactly as before (backward
    compatible, no behaviour change for existing callers).  Never raises.
    """
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

    # When the audio view is present, extend gap_to_plan with the fuel-per-lap delta
    # so the driver can see both pace and fuel-burn divergence at a glance.
    if audio_view is not None:
        try:
            fa, fp = g("fuel_per_lap_actual"), g("fuel_per_lap_plan")
            if fa is not None and fp is not None:
                df = float(fa) - float(fp)
                fuel_delta_str = f"{df:+.1f} L per lap"
                if gap == "—":
                    gap = fuel_delta_str
                elif gap == "on plan" and abs(df) < 0.05:
                    pass  # both pace and fuel on plan — leave "on plan"
                elif gap == "on plan":
                    # Pace is on plan but fuel is not — keep the pace context so the
                    # driver sees it isn't a pace problem, only fuel.
                    gap = f"pace on plan / {fuel_delta_str}"
                else:
                    gap = f"{gap} / {fuel_delta_str}"
        except Exception:
            pass

    fresh = "live" if g("telemetry_fresh") else "stale"
    if not connected:
        fresh = "none"

    stops = g("required_stops")
    pit_window = f"{stops} stop(s) required" if stops is not None else "—"

    # Defaults when no audio view is provided — behaviour exactly as before.
    engineer_instruction = ""
    next_decision = ""
    confidence = "unknown"
    warning = ""

    if audio_view is not None:
        try:
            msg = audio_view.get("strategy_message") or {}
            dec = audio_view.get("strategy_decision") or {}
            engineer_instruction = str(msg.get("headline") or "")
            next_decision = str(msg.get("next_review") or "")
            confidence = str(dec.get("confidence") or "unknown")
            rec = str(dec.get("recommendation") or "")
            if rec in ("REPLAN_RECOMMENDED", "REPLAN_URGENT"):
                hl = engineer_instruction or rec
                warning = f"{hl} Say 'accept plan' to switch, or 'keep plan' to stay out."
        except Exception:
            pass

    return LivePitWallVM(
        lap=lap, position="—", stint=stint, fuel=fuel, tyre=tyre,
        pit_window=pit_window, gap_to_plan=gap,
        engineer_instruction=engineer_instruction, next_decision=next_decision,
        warning=warning, freshness=fresh, confidence=confidence, map_trust="none",
    )


# ---------------------------------------------------------------------------
# Live replan candidate  ->  show_plan dict (pit wall plan card)
# ---------------------------------------------------------------------------
def live_plan_dict_from_candidate(candidate: dict) -> dict:
    """Reshape a replan candidate's fields onto the show_plan shape.

    Input:  ``StrategyReplanCandidate.to_dict()`` result (keys: label,
            stop_count_delta, projected_total_time_s, expected_completed_laps,
            fuel_target_note, tyre_note, expected_gain_detail, assumptions, …).
    Output: {name, expected_laps, total_time, pit_windows, pit_stops} for
            ``LivePitWall.show_plan()``.  An empty/no-label candidate returns {}
            (which hides the card).  Pure reshaping — no invented data, never raises.
    """
    try:
        if not isinstance(candidate, dict):
            return {}
        name = str(candidate.get("label") or "").strip()
        if not name:
            return {}

        # expected_laps (time-certain races: maximise completed laps)
        laps = candidate.get("expected_completed_laps")
        expected_laps = f"{int(laps)} laps" if laps is not None else ""

        # total_time (lap-count races: minimise total race time)
        total_time = ""
        total_s = candidate.get("projected_total_time_s")
        if total_s is not None:
            try:
                secs = float(total_s)
                h = int(secs // 3600)
                m = int((secs % 3600) // 60)
                s = int(secs % 60)
                total_time = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            except Exception:
                pass

        # pit_windows: how many extra stops this candidate proposes
        delta = 0
        try:
            delta = int(candidate.get("stop_count_delta", 0))
        except (TypeError, ValueError):
            delta = 0
        if delta > 0:
            pit_windows = f"+{delta} extra stop(s)"
        elif delta < 0:
            pit_windows = f"{delta} stop(s) fewer"
        else:
            pit_windows = "Keep current plan"

        # pit_stops: concise notes from the candidate's intent fields
        notes = []
        fuel_note = str(candidate.get("fuel_target_note") or "").strip()
        tyre_note = str(candidate.get("tyre_note") or "").strip()
        gain = str(candidate.get("expected_gain_detail") or "").strip()
        if fuel_note:
            notes.append(f"Fuel: {fuel_note}")
        if tyre_note:
            notes.append(f"Tyres: {tyre_note}")
        if gain:
            notes.append(gain)

        return {
            "name": name,
            "expected_laps": expected_laps,
            "total_time": total_time,
            "pit_windows": pit_windows,
            "pit_stops": notes,
        }
    except Exception:
        return {}


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


def _pit_stop_lines(stint_rows) -> tuple:
    """One line per pit stop: what to leave the pits with and how long it takes.

    Built from the detailed stint rows (each stint after the first begins with a stop).
    Answers "how much fuel to leave the pits with at each stop and how long estimated pit
    time will be … changing tyres or not and refuel." Parts with no data are omitted
    rather than shown as zero.
    """
    def _num(v, default=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    lines = []
    rows = [r for r in (stint_rows or []) if isinstance(r, dict)]
    cumulative = 0
    for i, r in enumerate(rows):
        laps = int(_num(r.get("laps")))
        if i > 0:
            stop_no = i
            lap_at = cumulative
            bits = []
            fuel = _num(r.get("fuel_to_leave_l"))
            if fuel > 0:
                bits.append(f"leave with {fuel:.0f} L")
            secs = _num(r.get("stop_seconds"))
            if secs > 0:
                bits.append(f"~{secs:.0f}s in the pits")
            comp = str(r.get("compound") or "").strip()
            if r.get("tyre_change") and comp:
                bits.append(f"fit {comp}")
            elif comp:
                bits.append(f"stay on {comp}")
            head = f"Stop {stop_no}" + (f" (lap {lap_at})" if lap_at else "")
            lines.append(head + ": " + " · ".join(bits) if bits else head)
        cumulative += laps
    return tuple(lines)


def strategy_plan_vm_from_rpvm(rpvm):
    from ui.components.strategy_plan import StrategyPlanVM, StrategyOption, StrategyInput
    if rpvm is None or not getattr(rpvm, "has_recommendation", False):
        return StrategyPlanVM()

    stints = tuple(
        f"{r.get('laps', '?')} {r.get('compound', '')}".strip()
        for r in (getattr(rpvm, "stint_plan_rows", None) or [])
    )
    # The detailed per-stop plan (fuel to leave with, estimated stop time, tyre change)
    # is computed for the recommended plan only — the driver asked for exactly this.
    pit_stops = _pit_stop_lines(getattr(rpvm, "stint_plan_rows", None) or [])
    options = []
    cand_rows = getattr(rpvm, "candidate_comparison_rows", None) or []
    if cand_rows:
        for r in cand_rows:
            recommended = str(r.get("status", "")).lower().startswith("recomm")
            # Every plan carries its OWN stint lengths and lap count — only the
            # recommended one used to, so the alternatives were unreadable. The lap
            # count matters in a time-certain race: it is what the driver races to.
            own_stints = tuple(r.get("stints") or ()) or (stints if recommended else ())
            laps = r.get("total_laps")
            risk = str(r.get("risk", "—"))
            why = str(r.get("why", "") or "")
            summary = "  ".join(
                p for p in (why, ("" if risk in ("—", "") else f"Risk: {risk}")) if p)
            options.append(StrategyOption(
                key=str(r.get("candidate_id", "") or ""),
                name=str(r.get("strategy", "Strategy")),
                total_time=str(r.get("total_time", "")),
                expected_laps=(f"{int(laps)} laps" if laps else ""),
                tyre_sequence=str(r.get("compounds", "")),
                pit_windows=(f"{r.get('pit_stops', '')} stop(s)"
                             if r.get("pit_stops") is not None else ""),
                confidence=_conf_key(str(r.get("confidence", ""))),
                summary=summary,
                gap=str(r.get("gap_to_best", "") or ""),
                stints=own_stints,
                pit_stops=(pit_stops if recommended else ()),
                recommended=recommended,
            ))
    else:
        options.append(StrategyOption(
            name=str(getattr(rpvm, "recommended_strategy_title", "Recommended")),
            total_time=str(getattr(rpvm, "estimated_total_time", "")),
            pit_stops=pit_stops,
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
    # Validating a recommendation IS a setup experiment, so it is driven by the
    # working-window brief: same fuel, same compound, same commitment as the baseline,
    # one change at a time. Only the parts the recommendation actually knows about —
    # the changes, the issue and the symptoms to watch — override the brief.
    from strategy.run_brief import brief_for_domain
    brief = brief_for_domain("working_window")
    return RunCardVM(
        objective=(f"Validate the recommended changes for {issue}" if issue
                   else "Validate the recommended setup changes"),
        setup_label=active_setup_label,
        changes=changes,
        expected_effect=expected,
        how_to_drive=brief.how_to_drive,
        monitor=monitor or brief.monitor,
        reports=brief.reports,
        fuel=brief.fuel,
        tyre=brief.tyre,
        purpose="diagnosis",
        target_laps=brief.target_laps,
        push_level=brief.push_level,
        invalidation=brief.invalidation,
    )


# ---------------------------------------------------------------------------
# Debrief  <-  session_db.build_cross_session_memory
# ---------------------------------------------------------------------------
# build_cross_session_memory returns the NESTED shape
#   {ok, history, memory, metrics, scorecard, comparison, timeline, record_count}
# where memory = EngineeringMemory.to_dict (issues / protected_knowledge / ...),
# scorecard = EngineeringScorecard.to_dict (band / issues_solved / confidence),
# and comparison = SessionComparison.to_dict (verdict / *_delta). The previous adapter
# read issues/band/regressions/protected_knowledge as TOP-LEVEL keys — none of which
# exist there — so every field mapped to nothing and the Debrief was always empty.

def _issue_label(issue) -> str:
    """A human line for one IssueMemory dict: 'understeer at Turn 6 (entry)'."""
    if not isinstance(issue, dict):
        return str(issue or "")
    what = str(issue.get("issue_type") or issue.get("family") or "issue").replace("_", " ")
    corner = str(issue.get("corner") or "").strip()
    phase = str(issue.get("phase") or "").strip().replace("_", " ")
    bits = [what]
    if corner:
        bits.append(f"at {corner}")
    if phase:
        bits.append(f"({phase})")
    return " ".join(bits)


def _knowledge_label(item) -> str:
    """A human line for one ProtectedKnowledgeItem dict: 'front_wing — higher is better'."""
    if not isinstance(item, dict):
        return str(item or "")
    field = str(item.get("field") or item.get("kind") or "").strip()
    direction = str(item.get("direction") or "").strip()
    if field and direction:
        return f"{field} — {direction}"
    return field or direction or str(item.get("value") or "")


def _behaviour_label(item) -> str:
    if isinstance(item, dict):
        for k in ("label", "behaviour", "field", "detail", "name"):
            if item.get(k):
                return str(item.get(k))
        return ""
    return str(item or "")


def debrief_vm_from_memory(mem, *, next_label: str = "Continue development", next_key: str = "continue"):
    from ui.components.debrief_view import DebriefVM
    if not isinstance(mem, dict) or not mem.get("ok", True) or mem.get("insufficient"):
        return DebriefVM()

    # No records = no debrief. An empty programme still reports a scorecard band of
    # "insufficient", which would render a hollow "Development band: insufficient"
    # debrief instead of the honest "No debrief yet — complete a session" placeholder.
    try:
        if int(mem.get("record_count") or 0) <= 0:
            return DebriefVM()
    except (TypeError, ValueError):
        return DebriefVM()

    memory = mem.get("memory") if isinstance(mem.get("memory"), dict) else {}
    scorecard = mem.get("scorecard") if isinstance(mem.get("scorecard"), dict) else {}
    comparison = mem.get("comparison") if isinstance(mem.get("comparison"), dict) else {}

    issues = [i for i in (memory.get("issues") or []) if isinstance(i, dict)]
    resolved = [i for i in issues if i.get("currently_resolved")]
    # A regression is an issue that HAS been regressed and is not currently resolved —
    # this is the prominent, colour-coded section, so it must not include stale history.
    regressed = [i for i in issues
                 if int(i.get("times_regressed") or 0) > 0 and not i.get("currently_resolved")]
    remaining = [i for i in issues
                 if not i.get("currently_resolved") and i not in regressed]

    band = str(scorecard.get("band") or "").replace("_", " ")
    verdict = str(comparison.get("verdict") or "").strip()

    # "What happened" = the session-to-session verdict, then the development band.
    happened_bits = []
    if comparison:
        earlier = str(comparison.get("earlier_label") or "the previous session")
        later = str(comparison.get("later_label") or "this session")
        if verdict:
            happened_bits.append(f"{later} vs {earlier}: {verdict}.")
    if band:
        happened_bits.append(f"Development band: {band}.")
    what_happened = " ".join(happened_bits)

    # The setup outcome line reports the measured deltas behind the verdict.
    outcome_bits = []
    for key, word in (("issues_resolved_delta", "issues resolved"),
                      ("regressions_delta", "regressions"),
                      ("improvements_delta", "improvements")):
        try:
            n = int(comparison.get(key) or 0)
        except (TypeError, ValueError):
            n = 0
        if n:
            outcome_bits.append(f"{n:+d} {word}")
    setup_outcome = ", ".join(outcome_bits)

    return DebriefVM(
        what_happened=what_happened,
        improved=tuple(_issue_label(i) for i in resolved),
        regressed=tuple(_issue_label(i) for i in regressed),
        learned=tuple(_knowledge_label(k) for k in (memory.get("protected_knowledge") or [])),
        carry_forward=tuple(filter(None, (_behaviour_label(b)
                                          for b in (memory.get("protected_behaviours") or [])))),
        findings=tuple(f"Still open: {_issue_label(i)}" for i in remaining),
        setup_outcome=setup_outcome,
        primary_action_label=next_label, primary_action_key=next_key,
    )
