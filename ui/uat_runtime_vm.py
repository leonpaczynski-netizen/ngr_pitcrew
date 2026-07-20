"""Pure view-model for the Live UAT Runtime diagnostics surface (Qt-free, Program 2, Phase 69).

Turns a ``LiveUatRuntimeSnapshot`` payload dict into a glanceable developer/UAT display: an overall
feed/readiness banner + grouped status rows (feed, session/event binding, fuel/pace/tyre-proxy evidence,
pit state, strategy readiness + recommendation, voice/PTT, certification, blockers/warnings). Every row
carries a text tag + tone (meaning never by colour alone). Display strings only; no raw object dumps; never
raises. It reports; it decides nothing and changes nothing.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not (r.get("fingerprint") or r.get("availability_matrix") or r.get("objective"))


_CONF_TONE = {"high": "success", "medium": "info", "low": "warn", "none": "neutral"}
_CERT_TONE = {"not_tested": "neutral", "automated_only": "info", "offscreen_validated": "info",
              "replay_validated": "info", "visual_uat_partial": "warn", "visual_uat_validated": "success",
              "live_gt7_partial": "warn", "live_gt7_validated": "success",
              "operationally_ready_with_limitations": "success", "operationally_ready": "success"}


def _fmt_num(v, suffix: str = "") -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No live runtime yet. This read-only developer/UAT surface reports the production live path "
                "(feed → canonical state → strategy → voice/PTT → certification). It changes nothing.")
    if r.get("tracker_connected") and r.get("telemetry_fresh"):
        feed = "LIVE FEED"
    elif r.get("tracker_connected"):
        feed = "STALE FEED"
    else:
        feed = "NO FEED"
    obj = str(r.get("objective") or "unknown").replace("_", " ").upper()
    rec = str(r.get("recommendation") or "").replace("_", " ") or "no recommendation"
    return f"[{feed}]  objective {obj}  ·  strategy: {rec.lower()}"


def banner_tone(result) -> str:
    r = build(result)
    if is_empty(result):
        return "advisory"
    if r.get("active_blockers"):
        return "warn"
    if r.get("tracker_connected") and r.get("telemetry_fresh"):
        return "success" if r.get("replan_ready") else "info"
    return "neutral"


def feed_row(result) -> dict:
    r = build(result)
    connected = bool(r.get("tracker_connected"))
    fresh = bool(r.get("telemetry_fresh"))
    age = r.get("last_packet_age_s")
    tag = "LIVE" if (connected and fresh) else ("STALE" if connected else "OFFLINE")
    tone = "success" if tag == "LIVE" else ("warn" if tag == "STALE" else "neutral")
    lines = [f"Tracker: {'connected' if connected else 'not connected'}; "
             f"telemetry {'fresh' if fresh else 'stale/absent'}.",
             f"Last packet age: {_fmt_num(age, ' s')}."]
    return {"title": "Live Feed", "status_tag": tag, "tone": tone, "lines": lines}


def session_row(result) -> dict:
    r = build(result)
    sess = str(r.get("session_identity") or "—")
    ev = str(r.get("event_identity") or "—")
    bound = bool(r.get("session_identity") or r.get("event_identity"))
    return {"title": "Session / Event Binding",
            "status_tag": "BOUND" if bound else "UNBOUND",
            "tone": "info" if bound else "neutral",
            "lines": [f"Session: {sess}.", f"Event: {ev}.",
                      f"Current lap: {r.get('current_lap') if r.get('current_lap') is not None else '—'}"
                      f" / total {r.get('total_race_laps') if r.get('total_race_laps') is not None else '—'}."]}


def clock_row(result) -> dict:
    r = build(result)
    obj = str(r.get("objective") or "unknown")
    lines = []
    if obj == "time_certain":
        lines.append(f"Time remaining: {_fmt_num(r.get('race_time_remaining_s'), ' s')}; "
                     f"expected completed laps: "
                     f"{r.get('expected_completed_laps') if r.get('expected_completed_laps') is not None else '—'}.")
    elif obj == "lap_count":
        lines.append(f"Laps: {r.get('current_lap') if r.get('current_lap') is not None else '—'}"
                     f" of {r.get('total_race_laps') if r.get('total_race_laps') is not None else '—'}.")
    else:
        lines.append("Race objective not yet resolved (no live race feed).")
    lines.append(f"Elapsed: {_fmt_num(r.get('race_elapsed_s'), ' s')}.")
    return {"title": "Race Clock", "status_tag": obj.replace("_", " ").upper(),
            "tone": "info" if obj != "unknown" else "neutral", "lines": lines}


def fuel_row(result) -> dict:
    r = build(result)
    conf = str(r.get("fuel_confidence") or "none")
    return {"title": "Fuel Evidence", "status_tag": conf.upper(),
            "tone": _CONF_TONE.get(conf, "neutral"),
            "lines": [f"Remaining: {_fmt_num(r.get('fuel_remaining_l'), ' L')}; "
                      f"burn estimate: {_fmt_num(r.get('fuel_burn_estimate_l'), ' L/lap')}.",
                      f"Samples: {r.get('fuel_burn_sample_count', 0)} (robust median; one anomalous lap "
                      f"never drives the value)."]}


def pace_row(result) -> dict:
    r = build(result)
    conf = str(r.get("pace_confidence") or "none")
    return {"title": "Pace Evidence", "status_tag": conf.upper(),
            "tone": _CONF_TONE.get(conf, "neutral"),
            "lines": [f"Estimate: {_fmt_num(r.get('pace_estimate_s'), ' s/lap')} (clean-lap median).",
                      f"Samples: {r.get('pace_sample_count', 0)}."]}


def tyre_row(result) -> dict:
    r = build(result)
    comp = str(r.get("current_compound") or "—")
    return {"title": "Tyre Proxy", "status_tag": "PROXY (LOW)", "tone": "warn",
            "lines": [f"Compound: {comp}; stint age: "
                      f"{r.get('tyre_age_proxy_laps') if r.get('tyre_age_proxy_laps') is not None else '—'} laps.",
                      f"Degradation proxy: {_fmt_num(r.get('tyre_deg_proxy_s_per_lap'), ' s/lap')}.",
                      "This is a lap-time-drift PROXY — not a measured tyre condition (GT7 does not broadcast "
                      "tyre wear)."]}


def pit_row(result) -> dict:
    r = build(result)
    st = str(r.get("pit_state") or "unknown")
    return {"title": "Pit State", "status_tag": st.replace("_", " ").upper(),
            "tone": "info" if st not in ("unknown", "uncertain") else "neutral",
            "lines": [f"Phase: {st.replace('_', ' ')}.",
                      f"Stops completed: "
                      f"{r.get('pit_stops_completed') if r.get('pit_stops_completed') is not None else '—'}."]}


def strategy_row(result) -> dict:
    r = build(result)
    ready = bool(r.get("replan_ready"))
    rec = str(r.get("recommendation") or "").replace("_", " ") or "—"
    conf = str(r.get("recommendation_confidence") or "")
    return {"title": "Strategy Readiness", "status_tag": "READY" if ready else "INSUFFICIENT",
            "tone": "success" if ready else "neutral",
            "lines": [f"Recommendation: {rec.lower()}"
                      f"{f' ({conf} confidence)' if conf else ''}.",
                      "Advisory only — no pit call, tyre, fuel-map, setup or game control is executed."]}


def voice_row(result) -> dict:
    r = build(result)
    vs = str(r.get("voice_state") or "—")
    vr = str(r.get("voice_readiness") or "—")
    ptt = str(r.get("ptt_state") or "—")
    recog = str(r.get("recognition_state") or "—")
    return {"title": "Voice / PTT", "status_tag": vr.replace("_", " ").upper(),
            "tone": "info" if vr not in ("—", "unavailable", "not_audio_first") else "neutral",
            "lines": [f"Voice state: {vs.replace('_', ' ')}; readiness: {vr.replace('_', ' ')}.",
                      f"PTT: {ptt}; recognition: {recog}."]}


def certification_row(result) -> dict:
    r = build(result)
    cert = str(r.get("certification_summary") or "not_tested")
    return {"title": "Certification (overall)", "status_tag": cert.replace("_", " ").upper(),
            "tone": _CERT_TONE.get(cert, "neutral"),
            "lines": [f"Overall: {cert.replace('_', ' ')}; weakest area: "
                      f"{r.get('certification_weakest_area') or '—'}.",
                      "Automated/bench evidence never certifies physical microphone, wheel/PTT, TTS, PSVR2 "
                      "or live GT7 — those need explicit manual UAT evidence."]}


def evidence_gaps_lines(result) -> List[str]:
    r = build(result)
    lines = []
    missing = r.get("missing_evidence") or ()
    stale = r.get("stale_evidence") or ()
    if missing:
        lines.append("Missing evidence: " + ", ".join(str(m).replace("_", " ") for m in missing) + ".")
    if stale:
        lines.append("Stale evidence: " + ", ".join(str(s).replace("_", " ") for s in stale) + ".")
    if not lines:
        lines.append("No missing or stale evidence recorded.")
    return lines


def blocker_lines(result) -> List[str]:
    r = build(result)
    lines = []
    for b in (r.get("active_blockers") or []):
        lines.append(f"[BLOCKER] {b}")
    for w in (r.get("active_warnings") or []):
        lines.append(f"[LIMITATION] {w}")
    if not lines:
        lines.append("No active blockers or warnings.")
    return lines


def all_rows(result) -> List[dict]:
    """The ordered rows for the panel (feed → session → clock → fuel → pace → tyre → pit → strategy →
    voice → certification)."""
    if is_empty(result):
        return []
    return [feed_row(result), session_row(result), clock_row(result), fuel_row(result), pace_row(result),
            tyre_row(result), pit_row(result), strategy_row(result), voice_row(result),
            certification_row(result)]
