"""Setup Builder tab — mixin for MainWindow (DashboardWindow)."""
from __future__ import annotations

import json
import json as _json  # alias used in _display_setup_result (verbatim copy from dashboard.py)
import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QLabel, QPushButton, QButtonGroup,
    QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QLineEdit, QTextEdit,
    QComboBox, QScrollArea, QSplitter, QMessageBox,
)

from strategy.setup_ranges import resolve_ranges, save_car_ranges, GENERIC_DEFAULTS
from ui.car_ranges_dialog import CarRangesDialog  # noqa: F401 — used in _open_car_ranges_dialog
from ui.setup_form_widget import SetupFormWidget

# Module-level display constants — sourced from the NGR design system.
from ui import ngr_theme as _ngr_t
_DARK_CARD = _ngr_t.CARBON_RAISED   # was "#2A2A2A"
_TEXT       = _ngr_t.TEXT           # was "#E0E0E0"


def _format_validation_errors_banner(validation_errors: list) -> str:
    """Return an HTML banner string for validation_errors from the AI response.

    Pure helper (no Qt) — renders validation errors as an orange warning
    banner in the same style as the DEF-P2-007 event-restriction banner.
    Returns "" when there are no errors to display.
    """
    if not validation_errors:
        return ""
    items = "".join(
        f"<li style='margin:2px 0;'>{e}</li>" for e in validation_errors
    )
    return (
        "<div style='background:#1A1A00; border:1px solid #C8A020; "
        "border-radius:4px; padding:8px; margin-bottom:8px; color:#C8A020;'>"
        "&#9888; <b>Setup Validation Warnings</b>"
        f"<ul style='margin:4px 0 0 0; padding-left:16px;'>{items}</ul>"
        "</div>"
    )


def _format_engineering_validation_banner(eng_errors: list) -> str:
    """Return an HTML banner string for engineering validation failures.

    Distinct from the standard validation-errors banner — uses a red border
    to signal a higher-severity warning: the AI retry did not resolve the
    engineering contradiction and the recommendation should not be applied.
    Returns "" when there are no errors to display.
    """
    if not eng_errors:
        return ""
    items = "".join(
        f"<li style='margin:2px 0;'>{e}</li>" for e in eng_errors
    )
    return (
        "<div style='background:#2A0A0A; border:2px solid #E05050; "
        "border-radius:4px; padding:8px; margin-bottom:8px; color:#E08080;'>"
        "&#9940; <b>Engineering validation failed after AI retry — review before applying.</b>"
        f"<ul style='margin:6px 0 0 0; padding-left:16px;'>{items}</ul>"
        "</div>"
    )


def _format_status_banner(status: str, validation_warnings: list) -> str:
    """Return an HTML banner for the recommendation lifecycle status.

    Returns "" when status is "approved" (no banner needed).
    Banner text follows the frontend contract in the sprint brief.
    """
    if status == "approved":
        return ""
    if status == "approved_with_warnings":
        if validation_warnings:
            items = "".join(
                f"<li style='margin:2px 0;'>{w}</li>" for w in validation_warnings
            )
            return (
                "<div style='background:#1A1A00; border:1px solid #C8A020; "
                "border-radius:4px; padding:8px; margin-bottom:8px; color:#C8A020;'>"
                "&#9888; <b>Setup approved with notes:</b>"
                f"<ul style='margin:4px 0 0 0; padding-left:16px;'>{items}</ul>"
                "</div>"
            )
        return ""
    if status == "approved_with_rejections":
        return (
            "<div style='background:#1A1A00; border:1px solid #C8A020; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#C8A020;'>"
            "&#10003; <b>Setup approved &mdash; valid changes applied.</b> "
            "One or more contradicted fields were rejected by engineering validation "
            "and left unchanged (see details below)."
            "</div>"
        )
    if status == "partial_recommendation":
        return (
            "<div style='background:#1A1A00; border:1px solid #C8A020; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#C8A020;'>"
            "&#9888; <b>Partial recommendation.</b> The valid changes below can be "
            "applied, but your dominant problem is NOT yet addressed &mdash; it is "
            "deferred pending more evidence or a targeted test (see the analysis)."
            "</div>"
        )
    if status == "balance_recommendation":
        return (
            "<div style='background:#0E1A16; border:1px solid #3FA07A; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#7FD0AC;'>"
            "&#9878; <b>Coordinated balance setup.</b> Several problems interact, so "
            "these changes were engineered as a SET (free the front, plant the rear, "
            "brake forward). Apply them together and validate over a few clean laps "
            "&mdash; see the balance breakdown and test plan below."
            "</div>"
        )
    if status == "evidence_required":
        return (
            "<div style='background:#2A0A0A; border:2px solid #E05050; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#E08080;'>"
            "&#9940; <b>More evidence required.</b> Your dominant problem can't be "
            "safely acted on from the current data &mdash; run more clean laps or "
            "confirm the track model. No changes are applied (see the analysis)."
            "</div>"
        )
    if status == "fallback_generated":
        return (
            "<div style='background:#1A2A1A; border:1px solid #4CAF50; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#88BB88;'>"
            "&#10003; <b>Safe fallback generated. Use only the fallback changes below.</b>"
            "</div>"
        )
    if status == "blocked_no_safe_recommendation":
        return (
            "<div style='background:#2A0A0A; border:2px solid #E05050; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#E08080;'>"
            "&#9940; <b>No safe setup recommendation generated. Run more laps or review "
            "telemetry before changing setup.</b>"
            "</div>"
        )
    if status == "validation_failed":
        return (
            "<div style='background:#2A0A0A; border:2px solid #E05050; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#E08080;'>"
            "&#9940; <b>Recommendation rejected by engineering validation. "
            "No setup changes from this AI response are approved.</b>"
            "</div>"
        )
    if status == "retry_failed":
        return (
            "<div style='background:#2A0A0A; border:2px solid #E05050; "
            "border-radius:4px; padding:8px; margin-bottom:8px; color:#E08080;'>"
            "&#9940; <b>AI recommendation rejected after retry. "
            "No AI setup changes are approved.</b>"
            "</div>"
        )
    # Default: show status text for any other/unknown status
    return (
        "<div style='background:#1A1A00; border:1px solid #888; "
        "border-radius:4px; padding:8px; margin-bottom:8px; color:#AAA;'>"
        f"Status: {status}"
        "</div>"
    )


# Tone → (background, border, text) for the structured advice cards. Keys match
# ui.setup_advice_render.TONE_* so the pure card list drives colour here.
_ADVICE_TONE_STYLE = {
    "ok":     ("#0E1A16", "#3FA07A", "#7FD0AC"),
    "warn":   ("#1A1A00", "#C8A020", "#E6C34A"),
    "danger": ("#2A0A0A", "#E05050", "#E08080"),
    "info":   ("#0E1622", "#3A6B8C", "#8FC0DC"),
}


def _advice_cards_to_html(cards) -> str:
    """Render an ordered ``AdviceCard`` list (ui.setup_advice_render) as themed HTML.

    Sprint 10 of the determinism rebuild: the deterministic ``SetupDecision`` is
    surfaced as discrete typed cards — a decision banner, approved-changes /
    preserved / rejected tables, evidence-conflict + controlled-test cards, and
    cross-lap / tyre-crossover evidence — instead of one free-form advice blob.
    Pure string rendering; safe to unit-test without Qt.
    """
    if not cards:
        return ""
    out = ["<div style='margin-bottom:10px;'>"]
    for c in cards:
        tone = getattr(c, "tone", "info")
        bg, border, text = _ADVICE_TONE_STYLE.get(tone, _ADVICE_TONE_STYLE["info"])
        kind = getattr(c, "kind", "")
        title = getattr(c, "title", "") or ""
        lines = tuple(getattr(c, "lines", ()) or ())
        rows = tuple(getattr(c, "rows", ()) or ())

        if kind == "banner":
            body = "".join(
                f"<div style='color:{text}; font-size:12px; margin-top:4px;'>{ln}</div>"
                for ln in lines)
            out.append(
                f"<div style='background:{bg}; border-left:4px solid {border}; "
                f"border-radius:5px; padding:10px 12px; margin-bottom:8px;'>"
                f"<div style='color:{text}; font-size:14px; font-weight:bold;'>{title}</div>"
                f"{body}</div>")
            continue

        parts = [
            f"<div style='background:{bg}; border:1px solid {border}; "
            f"border-radius:4px; padding:8px 10px; margin-bottom:6px;'>"
            f"<div style='color:{text}; font-weight:bold; font-size:12px; "
            f"margin-bottom:4px;'>{title}</div>"]
        for ln in lines:
            parts.append(
                f"<div style='color:#CCC; font-size:11px; margin:2px 0;'>{ln}</div>")
        if rows:
            parts.append("<table style='font-size:11px; border-collapse:collapse; "
                         "width:100%;'>")
            for row in rows:
                cells = "".join(
                    f"<td style='color:{'#E0E0E0' if i == 0 else '#AAA'}; "
                    f"padding:2px 8px 2px 0; vertical-align:top; "
                    f"{'font-weight:bold;' if i == 0 else ''}'>{cell}</td>"
                    for i, cell in enumerate(row))
                parts.append(f"<tr>{cells}</tr>")
            parts.append("</table>")
        parts.append("</div>")
        out.append("".join(parts))
    out.append("</div>")
    return "".join(out)


def _setup_response_looks_complete(payload: str) -> bool:
    """Heuristic: does the advisor payload look like a complete setup JSON?

    A response truncated at the API token cap ends mid-value (no closing brace)
    or omits the ``setup_fields`` key entirely.  Detecting that lets the UI show
    a clear "try again" message instead of dumping raw/partial JSON at the user
    (UAT: analyse button "returned jargon to text box").
    """
    s = (payload or "").strip()
    return s.endswith("}") and '"setup_fields"' in s


def _set_spin_readonly(spin, readonly: bool) -> None:
    """Make a spinbox read-only (min==max case) or editable again.

    Read-only is preferred over disabled so the value remains visible and
    copyable.  Buttons are hidden when read-only to signal non-editability.
    """
    spin.setReadOnly(readonly)
    spin.setButtonSymbols(
        QAbstractSpinBox.ButtonSymbols.NoButtons
        if readonly
        else QAbstractSpinBox.ButtonSymbols.UpDownArrows
    )


# Human-readable disposition labels for the discipline table (Group 64).
_DISCIPLINE_DISPOSITION_LABELS = {
    "AUTHORED": ("authored", "#8BC34A"),
    "PROVEN_HISTORY_SEED": ("proven", "#5FA8D3"),
    "DRIVER_PROFILE_SEED": ("profile", "#B0A0D0"),
    "TRACK_MODEL_SEED": ("track", "#5FA8D3"),
    "EVENT_CONSTRAINT": ("locked", "#E0A458"),
    "CONTROLLED_TEST_REQUIRED": ("test", "#E0A458"),
    "INSUFFICIENT_EVIDENCE": ("default", "#999999"),
    "NOT_ADJUSTABLE": ("n/a", "#666666"),
    "NOT_RELEVANT": ("n/a", "#666666"),
    "REJECTED_FOR_SAFETY": ("blocked", "#E86A5E"),
}


def _fmt_plan_value(v) -> str:
    """Format a setup value for the discipline table (numbers trimmed, None → —)."""
    if v is None:
        return "<span style='color:#666;'>&mdash;</span>"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{v:g}"
    return str(v)


def _discipline_field_plan_html(plan: dict) -> str:
    """Render Base / Qualifying / Race as a side-by-side field table (Group 64).

    Module-level (needs no widget) and self-guarding: an absent/empty plan renders
    nothing. Rows where all three disciplines share a value are dimmed; genuinely
    differing fields are highlighted so the driver sees what each discipline changes.
    """
    if not isinstance(plan, dict):
        return ""
    rows = plan.get("rows") or []
    rows = [r for r in rows if isinstance(r, dict)
            and any(r.get(k) is not None for k in ("base", "qualifying", "race"))]
    if not rows:
        return ""
    differing = plan.get("differing_fields") or []
    seeded = plan.get("seeded_from_history") or []
    rows = sorted(rows, key=lambda r: (not r.get("differs"), str(r.get("field", ""))))

    _hdr = (
        "<th style='text-align:left; color:#888; padding:2px 10px 4px 0;'>Field</th>"
        "<th style='text-align:right; color:#9FB6C4; padding:2px 10px 4px 0;'>Base</th>"
        "<th style='text-align:right; color:#F5A623; padding:2px 10px 4px 0;'>Qualifying</th>"
        "<th style='text-align:right; color:#8BC34A; padding:2px 10px 4px 0;'>Race</th>"
        "<th style='text-align:right; color:#5FA8D3; padding:2px 10px 4px 0;'>Proven</th>"
        "<th style='text-align:left; color:#888; padding:2px 0 4px 0;'>Source</th>"
    )
    _body = ""
    for r in rows:
        _field = str(r.get("field", "")).replace("_", " ")
        _differs = bool(r.get("differs"))
        _name_col = "#EDE3C8" if _differs else "#999"
        _row_bg = "background:#141C10;" if _differs else ""
        _disp = str(r.get("disposition", ""))
        _disp_label, _disp_colour = _DISCIPLINE_DISPOSITION_LABELS.get(
            _disp, (_disp.lower().replace("_", " "), "#888"))
        _mark = " &#9679;" if _differs else ""
        _body += (
            f"<tr style='{_row_bg}'>"
            f"<td style='color:{_name_col}; padding:2px 10px 2px 0; font-size:11px;'>"
            f"{_field}<span style='color:#8BC34A;'>{_mark}</span></td>"
            f"<td style='text-align:right; color:#9FB6C4; padding:2px 10px 2px 0; font-size:11px;'>"
            f"{_fmt_plan_value(r.get('base'))}</td>"
            f"<td style='text-align:right; color:#F5C77E; padding:2px 10px 2px 0; font-size:11px;'>"
            f"{_fmt_plan_value(r.get('qualifying'))}</td>"
            f"<td style='text-align:right; color:#A9D275; padding:2px 10px 2px 0; font-size:11px;'>"
            f"{_fmt_plan_value(r.get('race'))}</td>"
            f"<td style='text-align:right; color:#7FBEDF; padding:2px 10px 2px 0; font-size:11px;'>"
            f"{_fmt_plan_value(r.get('proven'))}</td>"
            f"<td style='color:{_disp_colour}; padding:2px 0 2px 0; font-size:10px;'>"
            f"{_disp_label}</td>"
            "</tr>"
        )

    _seeded_note = ""
    if seeded:
        _seeded_note = (
            "<p style='margin:5px 0 0 0; color:#7FBEDF; font-size:10px;'>"
            "&#10003; Seeded from your proven setup: "
            + ", ".join(str(s).replace("_", " ") for s in seeded) + ".</p>"
        )
    _diff_note = (
        f"<p style='margin:3px 0 0 0; color:#999; font-size:10px;'>"
        f"&#9679; {len(differing)} field(s) genuinely differ between disciplines "
        "(Qualifying = one-lap attack; Race = repeatable pace over the stint).</p>"
        if differing else ""
    )
    return (
        "<div style='background:#0E1410; border:1px solid #2E4636; "
        "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
        "<b style='color:#8BC34A; font-size:12px;'>"
        "&#128203; Base &middot; Qualifying &middot; Race &mdash; side by side</b>"
        "<table style='border-collapse:collapse; margin-top:6px; width:100%;'>"
        f"<tr>{_hdr}</tr>{_body}</table>"
        f"{_diff_note}{_seeded_note}</div>"
    )


# Subsystem grouping for the comparison workspace — ordered so related fields sit
# together (aero, then the mechanical platform, alignment, diff, gearing, brakes).
# Each entry: (group label, predicate over the field name). First match wins.
_SETUP_SUBSYSTEMS = [
    ("Aerodynamics", lambda f: f.startswith("aero") or "downforce" in f or "wing" in f),
    ("Springs & ride height", lambda f: f.startswith("spring") or f.startswith("ride_height")
        or "natural_freq" in f),
    ("Dampers", lambda f: f.startswith("damper") or "bump" in f or "rebound" in f),
    ("Anti-roll bars", lambda f: f.startswith("arb") or "anti_roll" in f or "roll_bar" in f),
    ("Alignment", lambda f: f.startswith("camber") or f.startswith("toe")
        or f.startswith("caster")),
    ("Differential", lambda f: f.startswith("lsd") or "differential" in f or f == "diff"),
    ("Gearing", lambda f: f.startswith("gear") or f == "final_drive"),
    ("Brakes", lambda f: f.startswith("brake")),
    ("Tyres & pressure", lambda f: f.startswith("tyre") or f.startswith("tire")
        or "pressure" in f),
    ("Ballast & weight", lambda f: "ballast" in f or "weight" in f),
]


def _subsystem_for_field(field: str) -> str:
    """Classify a setup field name into a human subsystem group (workspace)."""
    f = (field or "").lower()
    for label, pred in _SETUP_SUBSYSTEMS:
        try:
            if pred(f):
                return label
        except Exception:
            continue
    return "Other adjustments"


def _discipline_comparison_workspace_html(plan: dict) -> str:
    """Render the Base / Qualifying / Race comparison workspace (Phase 7).

    A fuller, self-contained view than the compact field table: three objective
    header cards, a shared-foundation summary, and the genuinely-differing fields
    grouped by subsystem — each divergence annotated with WHY that discipline
    leans the way it does. Module-level and self-guarding: an absent/empty plan
    (or one with no differing fields) renders nothing, so the caller can fall back
    to the compact table.
    """
    if not isinstance(plan, dict):
        return ""
    rows = [r for r in (plan.get("rows") or []) if isinstance(r, dict)]
    rows = [r for r in rows
            if any(r.get(k) is not None for k in ("base", "qualifying", "race"))]
    if not rows:
        return ""
    differing = [r for r in rows if r.get("differs")]
    # Nothing genuinely differs → the compact table is the better surface.
    if not differing:
        return ""

    # --- Objective header cards (Base / Qualifying / Race) ---
    _card_colour = {"base": "#9FB6C4", "qualifying": "#F5A623", "race": "#8BC34A"}
    _discs = [d for d in (plan.get("disciplines") or []) if isinstance(d, dict)]
    _cards = ""
    for d in _discs:
        _k = str(d.get("key", ""))
        _col = _card_colour.get(_k, "#AAA")
        _conf = str(d.get("confidence", "")).lower()
        _conf_chip = (
            f"<span style='color:#888; font-size:9px;'> &middot; {_conf} confidence</span>"
            if _conf and _conf != "n/a" else ""
        )
        _cards += (
            f"<td style='vertical-align:top; padding:0 6px 0 0; width:33%;'>"
            f"<div style='background:#12160F; border:1px solid #2E3A2A; border-top:2px solid {_col}; "
            f"border-radius:4px; padding:6px 8px;'>"
            f"<b style='color:{_col}; font-size:11px;'>{d.get('label', _k.title())}</b>{_conf_chip}"
            f"<p style='margin:3px 0 0 0; color:#AEB8AE; font-size:10px; line-height:1.35;'>"
            f"{d.get('objective', '')}</p></div></td>"
        )
    _cards_row = (
        f"<table style='border-collapse:separate; border-spacing:0; width:100%; "
        f"margin-top:6px;'><tr>{_cards}</tr></table>" if _cards else ""
    )

    # --- Shared-foundation summary ---
    _shared = len(rows) - len(differing)
    _shared_note = (
        f"<p style='margin:7px 0 2px 0; color:#7FBEDF; font-size:10px;'>"
        f"&#128279; <b>{_shared}</b> of {len(rows)} fields are identical across all "
        f"three disciplines &mdash; your shared platform. The "
        f"<b style='color:#8BC34A;'>{len(differing)}</b> below are where they diverge.</p>"
    )

    # --- Differing fields grouped by subsystem ---
    _by_sub: dict = {}
    for r in differing:
        _by_sub.setdefault(_subsystem_for_field(str(r.get("field", ""))), []).append(r)
    _ordered_subs = [lbl for lbl, _ in _SETUP_SUBSYSTEMS if lbl in _by_sub]
    _ordered_subs += [s for s in _by_sub if s not in _ordered_subs]  # "Other" last

    _groups = ""
    for _sub in _ordered_subs:
        _sub_rows = ""
        for r in _by_sub[_sub]:
            _field = str(r.get("field", "")).replace("_", " ")
            _bv, _qv, _rv = r.get("base"), r.get("qualifying"), r.get("race")
            _q_hl = "#F5C77E" if _qv != _bv else "#6B6B6B"
            _r_hl = "#A9D275" if _rv != _bv else "#6B6B6B"
            _proven = ""
            if r.get("proven") is not None:
                _proven = (f"<span style='color:#5FA8D3; font-size:9px;'> "
                           f"(proven {_fmt_plan_value(r.get('proven'))})</span>")
            _why_bits = []
            if r.get("why_qualifying"):
                _why_bits.append(
                    f"<span style='color:#F5A623;'>Q:</span> {r['why_qualifying']}")
            if r.get("why_race"):
                _why_bits.append(
                    f"<span style='color:#8BC34A;'>R:</span> {r['why_race']}")
            _why = ""
            if _why_bits:
                _why = (
                    "<div style='margin:0 0 3px 0; color:#8FA69A; font-size:9px; "
                    "line-height:1.35;'>" + " &nbsp; ".join(_why_bits) + "</div>"
                )
            _sub_rows += (
                f"<div style='padding:3px 0; border-top:1px solid #1C241A;'>"
                f"<div style='color:#EDE3C8; font-size:11px;'>{_field}{_proven}</div>"
                f"<div style='color:#999; font-size:10px; margin:1px 0;'>"
                f"<span style='color:#9FB6C4;'>Base {_fmt_plan_value(_bv)}</span> "
                f"&rarr; <span style='color:{_q_hl};'>Q {_fmt_plan_value(_qv)}</span> "
                f"&nbsp; <span style='color:{_r_hl};'>R {_fmt_plan_value(_rv)}</span></div>"
                f"{_why}</div>"
            )
        _sub_label = _sub.replace("&", "&amp;")
        _groups += (
            f"<div style='margin-top:6px;'>"
            f"<p style='margin:0; color:#7FD0AC; font-size:10px; "
            f"text-transform:uppercase; letter-spacing:0.5px;'><b>{_sub_label}</b></p>"
            f"{_sub_rows}</div>"
        )

    _seeded = plan.get("seeded_from_history") or []
    _seeded_note = ""
    if _seeded:
        _seeded_note = (
            "<p style='margin:6px 0 0 0; color:#7FBEDF; font-size:10px;'>"
            "&#10003; Seeded from your proven setup: "
            + ", ".join(str(s).replace("_", " ") for s in _seeded) + ".</p>"
        )

    return (
        "<div style='background:#0E1410; border:1px solid #2E4636; "
        "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
        "<b style='color:#8BC34A; font-size:12px;'>"
        "&#128295; Base &middot; Qualifying &middot; Race &mdash; comparison workspace</b>"
        f"{_cards_row}{_shared_note}{_groups}{_seeded_note}</div>"
    )


_BALANCE_AXIS_LABEL = {"entry": "Turn-in / entry", "exit": "Corner exit / traction",
                       "braking": "Braking stability"}


def _balance_solution_html(sol: dict) -> str:
    """Render the coordinated balance solution (moves grouped by axis + trade-off +
    test protocol). Module-level, self-guarding — absent/unsolved renders nothing."""
    if not isinstance(sol, dict) or not sol.get("solved"):
        return ""
    moves = sol.get("moves") or []
    if not moves:
        return ""
    by_axis: dict = {}
    for m in moves:
        by_axis.setdefault(str(m.get("axis", "")), []).append(m)
    _body = ""
    for axis in ("entry", "exit", "braking"):
        ax_moves = by_axis.get(axis) or []
        if not ax_moves:
            continue
        _rows = ""
        for m in ax_moves:
            _fld = str(m.get("field", "")).replace("_", " ")
            _rows += (
                f"<p style='margin:1px 0; color:#CBD8D0; font-size:11px;'>"
                f"<b>{_fld}</b> {m.get('from')} &rarr; {m.get('to')} "
                f"<span style='color:#8FA69A;'>— {m.get('reason', '')}</span></p>"
            )
        _body += (
            f"<p style='margin:5px 0 1px 0; color:#7FD0AC; font-size:11px;'>"
            f"<b>{_BALANCE_AXIS_LABEL.get(axis, axis.title())}</b></p>{_rows}"
        )
    _trade = ""
    for t in (sol.get("tradeoffs") or []):
        _trade += (f"<p style='margin:4px 0 0 0; color:#E0C890; font-size:10px;'>"
                   f"&#8644; {t}</p>")
    _tests = ""
    for t in (sol.get("targeted_tests") or []):
        _tests += (f"<p style='margin:1px 0; color:#9FB6C4; font-size:10px;'>"
                   f"&#128300; {t}</p>")
    _proto = ""
    if sol.get("test_protocol"):
        _proto = (f"<p style='margin:5px 0 0 0; color:#AAB; font-size:10px;'>"
                  f"<b>How to test:</b> {sol['test_protocol']}</p>")
    return (
        "<div style='background:#0C1512; border:1px solid #2E5044; "
        "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
        "<b style='color:#7FD0AC; font-size:12px;'>&#9878; Coordinated balance change "
        "&mdash; engineered as a set</b>"
        f"{_body}{_trade}{_tests}{_proto}</div>"
    )


def _driver_fit_html(reasoning: dict) -> str:
    """Render how the setup was tailored to the driver's style, evidence-scaled.
    Module-level, self-guarding — absent/empty renders nothing."""
    if not isinstance(reasoning, dict):
        return ""
    intents = reasoning.get("intents") or []
    if not intents:
        return ""
    _rows = ""
    for i in intents:
        _fld = str(i.get("field", "")).replace("_", " ")
        _conf = str(i.get("confidence", ""))
        _rows += (
            f"<p style='margin:1px 0; color:#CBC8D8; font-size:11px;'>"
            f"<b>{_fld}</b> {i.get('from')} &rarr; {i.get('to')} "
            f"<span style='color:#8F8CA6;'>({_conf}) — {i.get('reason', '')}</span></p>"
        )
    _note = str(reasoning.get("note", ""))
    _note_html = (f"<p style='margin:4px 0 0 0; color:#9A97AE; font-size:10px;'>{_note}</p>"
                  if _note else "")
    return (
        "<div style='background:#12101A; border:1px solid #4A3E64; "
        "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
        "<b style='color:#B0A0D0; font-size:12px;'>&#128100; Tailored to your driving "
        "style</b>"
        f"{_rows}{_note_html}</div>"
    )


def _closed_loop_html(data: dict) -> str:
    """Render the closed-loop signals (Engineering-Brain Phase 1): a rollback advisory,
    changes withheld for conflicting evidence, and changes NOT repeated because they
    previously worsened the car. Module-level + self-guarding — nothing renders when the
    fields are absent (legacy responses unaffected)."""
    if not isinstance(data, dict):
        return ""
    html = ""
    _rb = data.get("rollback") or {}
    if isinstance(_rb, dict) and _rb.get("recommend_rollback"):
        _rev = _rb.get("revert_changes") or []
        _rev_txt = ", ".join(
            f"{str(c.get('field', '')).replace('_', ' ')} &rarr; {c.get('to')}"
            for c in _rev if isinstance(c, dict))
        html += (
            "<div style='background:#2A1410; border:1px solid #A0562E; "
            "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
            "<b style='color:#E08A5E; font-size:12px;'>&#8617; Consider rolling back</b>"
            f"<p style='margin:2px 0; color:#D8B8A8; font-size:11px;'>{_rb.get('reason', '')}</p>"
            + (f"<p style='margin:1px 0; color:#B89888; font-size:10px;'>Revert: {_rev_txt}</p>"
               if _rev_txt else "")
            + "</div>"
        )
    _contra = data.get("diagnosis_contradictions") or []
    if _contra:
        _body = "".join(
            f"<p style='margin:1px 0; color:#CCC; font-size:11px;'>&#9888; {c.get('detail', '')}</p>"
            for c in _contra if isinstance(c, dict))
        html += (
            "<div style='background:#201A0A; border:1px solid #8A6A2A; "
            "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
            "<b style='color:#E0B84A; font-size:12px;'>&#9878; Withheld — conflicting "
            "evidence</b>"
            f"{_body}</div>"
        )
    _lk = data.get("closed_loop_lockouts") or []
    if _lk:
        _seen = set()
        _rows = ""
        for m in _lk:
            if not isinstance(m, dict):
                continue
            _key = m.get("field") or m.get("rule_id")
            if _key in _seen:
                continue
            _seen.add(_key)
            _label = str(m.get("field") or m.get("rule_id") or "").replace("_", " ")
            _rows += (f"<p style='margin:1px 0; color:#CCC; font-size:11px;'>&#128683; "
                      f"<b>{_label}</b> — {m.get('reason', '')}</p>")
        if _rows:
            html += (
                "<div style='background:#1A1414; border:1px solid #6A4A4A; "
                "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
                "<b style='color:#D08A8A; font-size:12px;'>&#128260; Not repeating "
                "(made the car worse before)</b>"
                f"{_rows}</div>"
            )
    return html


_VERDICT_STYLE = {
    "improved": ("&#9650; better", "#8BC34A"),
    "worsened": ("&#9660; worse", "#E86A5E"),
    "neutral": ("&#9644; no change", "#C8A020"),
    "": ("&#9679; not yet tested", "#7A7A7A"),
}


def _development_timeline_html(data: dict) -> str:
    """Render the setup DEVELOPMENT TIMELINE (Phase 7): the chain of applied setups, what
    each changed from its parent, and whether it made the car better or worse — plus the
    rollback recommendation. Module-level + self-guarding."""
    if not isinstance(data, dict):
        return ""
    import json as _json
    nodes = data.get("setup_lineage") or []
    if not nodes:
        return ""
    # Oldest → newest for a readable chain.
    ordered = sorted(nodes, key=lambda n: (n.get("id") or 0))
    _rows = ""
    for i, n in enumerate(ordered):
        verdict = str(n.get("outcome_verdict") or "").strip().lower()
        label = str(n.get("label") or f"Setup {n.get('id')}")
        vtext, vcol = _VERDICT_STYLE.get(verdict, _VERDICT_STYLE[""])
        try:
            changes = _json.loads(n.get("changes_json") or "[]")
        except Exception:
            changes = []
        chg = ", ".join(
            f"{str(c.get('field', '')).replace('_', ' ')} {c.get('from')}&rarr;{c.get('to')}"
            for c in changes if isinstance(c, dict) and c.get("field"))[:120]
        _connector = ("<div style='color:#556; font-size:12px; margin:0 0 0 6px;'>"
                      "&#8615;</div>") if i > 0 else ""
        _chg_line = (f"<span style='color:#8A93A6; font-size:10px;'> &mdash; {chg}</span>"
                     if chg else "")
        _rows += (
            f"{_connector}"
            f"<div style='margin:1px 0; font-size:11px;'>"
            f"<b style='color:#CDD6E0;'>{label}</b>{_chg_line} "
            f"<span style='color:{vcol};'>{vtext}</span></div>"
        )
    _rb = data.get("rollback") or {}
    _rb_line = ""
    if isinstance(_rb, dict) and _rb.get("recommend_rollback"):
        _rev = ", ".join(
            f"{str(c.get('field', '')).replace('_', ' ')}&rarr;{c.get('to')}"
            for c in (_rb.get("revert_changes") or []) if isinstance(c, dict))
        _rb_line = (
            "<p style='margin:5px 0 0 0; color:#E08A5E; font-size:11px;'>"
            "&#8617; <b>Roll back</b> — the last setup tested worse. Revert: "
            f"{_rev or 'to the previous setup'}.</p>")
    return (
        "<div style='background:#0C1016; border:1px solid #2E3A4E; border-radius:4px; "
        "padding:8px 10px; margin-top:8px;'>"
        "<b style='color:#9FB6D4; font-size:12px;'>&#128203; Setup development timeline</b>"
        f"<div style='margin-top:4px;'>{_rows}</div>{_rb_line}</div>"
    )


def _engineering_brain_html(data: dict) -> str:
    """Surface the engineering-brain reasoning (Phases 2-6) — synthesis target + best
    candidate, discipline objective, per-corner diagnosis, and the strategy handoff.
    Module-level + self-guarding: absent/empty fields render nothing."""
    if not isinstance(data, dict):
        return ""
    html = ""

    # Phase 4 — discipline objective (what this setup optimises + soft-tyre + RPM).
    _do = data.get("discipline_objective") or {}
    if _do.get("objective"):
        _tyre = _do.get("tyre") or {}
        _rpm = _do.get("rpm") or {}
        _tyre_line = (f"<p style='margin:1px 0; color:#CBD; font-size:11px;'>Tyre: "
                      f"<b>{_tyre.get('name', _tyre.get('compound', ''))}</b> — "
                      f"{_tyre.get('reason', '')}</p>" if _tyre.get("compound") else "")
        html += (
            "<div style='background:#0E141C; border:1px solid #2E4A66; border-radius:4px; "
            "padding:8px 10px; margin-top:8px;'>"
            f"<b style='color:#6FB0E0; font-size:12px;'>&#127942; {_do['objective'].title()} "
            "objective</b>"
            f"{_tyre_line}"
            f"<p style='margin:1px 0; color:#9FB6C4; font-size:11px;'>{_rpm.get('note', '')}</p>"
            "</div>"
        )

    # Phase 3 — setup synthesis (target handling + best candidate).
    _ss = data.get("setup_synthesis") or {}
    _best = _ss.get("best") or {}
    if _best:
        _th = (_ss.get("target_handling") or {}).get("drivers") or []
        _drv = "".join(f"<p style='margin:1px 0; color:#B8D0B8; font-size:10px;'>&bull; {d}</p>"
                       for d in _th[:4])
        _cands = ", ".join(f"{c.get('lens')} {c.get('score')}"
                           for c in (_ss.get("candidates") or [])[:3])
        # When synthesis authored fields as PRIMARY (confidence-gated), name them so the
        # driver sees the coupled engineer — not the one-field rule stack — built the base.
        _sp = data.get("synthesis_primary") or {}
        _applied = _sp.get("applied") or []
        _primary_line = ""
        if _applied:
            _fields = ", ".join(str(f).replace("_", " ") for f in _applied)
            _kept = _sp.get("kept_proven") or []
            _kept_line = (f" Kept your proven {', '.join(str(k).replace('_', ' ') for k in _kept)}."
                          if _kept else "")
            _primary_line = (
                f"<p style='margin:3px 0 0 0; color:#7FD0A0; font-size:10px;'>"
                f"&#10003; Authored {len(_applied)} handling field(s) as primary: "
                f"{_fields}.{_kept_line}</p>")
        html += (
            "<div style='background:#0C1410; border:1px solid #2E5040; border-radius:4px; "
            "padding:8px 10px; margin-top:8px;'>"
            "<b style='color:#7FD0A0; font-size:12px;'>&#129504; Complete-setup synthesis</b>"
            f"<p style='margin:2px 0; color:#CBD8D0; font-size:11px;'>Target for "
            f"<b>{_ss.get('objective', '')}</b> — best candidate: <b>{_best.get('lens', '')}</b> "
            f"(confidence {_ss.get('confidence', '')})</p>"
            f"{_drv}{_primary_line}"
            f"<p style='margin:2px 0 0 0; color:#889; font-size:10px;'>Candidates scored: {_cands}</p>"
            "</div>"
        )

    # Phase 5 — per-corner diagnosis.
    _cd = data.get("corner_diagnosis") or {}
    _corner = _cd.get("corner") or {}
    if _corner.get("name"):
        _causes = "".join(
            f"<p style='margin:1px 0; color:#CCC; font-size:11px;'>&bull; {c.get('cause', '')}</p>"
            for c in (_cd.get("causes") or []))
        _test = (f"<p style='margin:3px 0 0 0; color:#9FB6C4; font-size:10px;'>&#128300; "
                 f"{_cd.get('controlled_test', '')}</p>" if _cd.get("controlled_test") else "")
        html += (
            "<div style='background:#14100A; border:1px solid #5A4A2E; border-radius:4px; "
            "padding:8px 10px; margin-top:8px;'>"
            f"<b style='color:#E0B84A; font-size:12px;'>&#128205; {_corner.get('name', '')} "
            f"({_cd.get('phase', '')}) — {_cd.get('confidence', '')} confidence</b>"
            f"{_causes}{_test}</div>"
        )

    # Phase 5 (live) — telemetry-measured per-corner diagnoses. Each corner where the
    # session's slip/lock evidence was strong enough to diagnose from DATA, not feeling.
    _tel = [d for d in (data.get("corner_telemetry_diagnoses") or []) if isinstance(d, dict)]
    if _tel:
        _rows = ""
        for d in _tel[:6]:
            _c = d.get("corner") or {}
            _causes = "".join(
                f"<p style='margin:1px 0 1px 8px; color:#CCC; font-size:10px;'>&bull; "
                f"{c.get('cause', '')}</p>" for c in (d.get("causes") or [])[:2])
            _rows += (
                f"<p style='margin:4px 0 0 0; color:#A9D275; font-size:11px;'>"
                f"<b>{_c.get('name', 'Corner')}</b> ({d.get('phase', '')}, "
                f"{d.get('symptom', '')}) — {d.get('confidence', '')} confidence "
                f"<span style='color:#7FA070;'>&middot; {d.get('telemetry_evidence', '')}</span></p>"
                f"{_causes}")
        html += (
            "<div style='background:#0C140C; border:1px solid #2E5A2E; border-radius:4px; "
            "padding:8px 10px; margin-top:8px;'>"
            "<b style='color:#8BC34A; font-size:12px;'>&#128225; Measured per-corner "
            "diagnosis (live telemetry)</b>"
            f"{_rows}</div>"
        )

    # Phase 6 — setup -> strategy handoff.
    _hoff = data.get("setup_strategy_handoff") or {}
    if _hoff.get("characteristics"):
        _str = "".join(f"<p style='margin:1px 0; color:#B8C8D8; font-size:10px;'>&#10003; {s}</p>"
                       for s in (_hoff.get("strengths") or []))
        html += (
            "<div style='background:#0A1014; border:1px solid #2E4658; border-radius:4px; "
            "padding:8px 10px; margin-top:8px;'>"
            "<b style='color:#7FB0C8; font-size:12px;'>&#127937; For the Strategy tab</b>"
            f"<p style='margin:2px 0; color:#9FB6C4; font-size:11px;'>This race setup's "
            "tyre/fuel/consistency evidence — the Strategy Brain owns the pit plan.</p>"
            f"{_str}</div>"
        )
    return html


class SetupBuilderMixin:
    """Setup Builder tab methods — mixed into MainWindow."""

    def _live_corner_aggregates(self) -> list:
        """Snapshot of the live per-corner telemetry aggregates ([] when inert).

        Reads the optional live aggregator the dashboard maintains; returns [] on any
        host that doesn't run one, so the analyse worker can always call it.
        """
        tel = getattr(self, "_live_corner_tel", None)
        if tel is None:
            return []
        try:
            return tel.aggregates()
        except Exception:
            return []

    def _persist_live_corner_slip(self) -> None:
        """Upsert the current run's per-corner slip aggregates so they accumulate across
        sessions. Keyed by the event's track/layout (matching the advisor's read) and the
        consumer's run_id (idempotent). Best-effort; inert without a DB/aggregator."""
        tel = getattr(self, "_live_corner_tel", None)
        db = getattr(self, "_db", None)
        if tel is None or db is None:
            return
        try:
            aggs = tel.aggregates()
            if not aggs:
                return
            ec = self._build_event_context()
            track = str(getattr(ec, "track", "") or "")
            layout = str(getattr(ec, "layout_id", "") or "")
            cid = int(self._car_id_ref[0]) if getattr(self, "_car_id_ref", None) else 0
            if cid <= 0 or not track:
                return
            db.save_corner_slip_aggregates(cid, track, layout, tel.run_id, aggs)
        except Exception:
            pass

    def _active_form(self) -> "SetupFormWidget":
        """Return the currently-active setup form (Race form by default).

        The Race form's widgets are aliased to ``self._setup_*`` attributes, so
        all legacy mixin methods (``_current_setup_dict``, ``_fill_setup_fields``,
        ``_apply_build_setup_result``, etc.) continue to work unchanged.
        Exposed as a method so callers can be parameterised by form in the future.
        """
        return self._race_form

    def _build_car_setup_group(self) -> QWidget:
        """Build the side-by-side Race + Qualifying setup panel.

        Returns a QWidget that contains:
        - A tab-level "Live Session Mode" row (self._setup_type combo)
        - A QSplitter with Race form on the left and Qualifying form on the right
        - Shared Shift RPM display box below the splitter

        All self._setup_* widget attributes are aliased to the Race form's widgets
        so that every existing mixin method (AI, save, load, highlight, rebound)
        continues to operate on the Race form through self.
        """
        lbl_s = f"color: {_TEXT};"
        container = QWidget()
        outer_layout = QVBoxLayout(container)
        outer_layout.setSpacing(8)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        if hasattr(self, "_tab_intro_header"):
            outer_layout.addWidget(self._tab_intro_header(
                "Setup Builder",
                "Build and tune your qualifying and race setups side by side. "
                "Describe a handling issue and click Analyse to get Pit Crew's "
                "rule-based, validated setup changes, then Apply and Save."))

        # self._setup_type stays on self (required by main.py + tests). It picks
        # which shift-RPM threshold the live beep uses during Practice telemetry.
        # It is NOT a form-selector — both forms are always visible side-by-side —
        # so it lives in the Shift RPM box below (next to the two RPM values it
        # chooses between) rather than as a prominent row at the top of the tab.
        self._setup_type = QComboBox()
        self._setup_type.addItems(["Race Setup", "Qualifying Setup"])
        self._setup_type.setToolTip(
            "Which shift-RPM threshold the live beep uses during Practice telemetry.\n"
            "Race Setup: use race shift RPM.  Qualifying Setup: use qualifying shift RPM."
        )
        # Connect session-type signals (required by tests + main.py sync)
        self._setup_type.currentTextChanged.connect(self._on_setup_type_changed)
        self._on_setup_type_changed(self._setup_type.currentText())

        # ── Create Race and Qualifying form widgets ────────────────────────────
        self._race_form = SetupFormWidget("Race", self)
        self._qual_form = SetupFormWidget("Qualifying", self)

        # ── Alias self._setup_* to Race form widgets ──────────────────────────
        # Every legacy mixin method that accesses self._setup_rh_f etc. will
        # transparently read/write the Race form's widgets.
        _RACE_ALIASES = [
            "_setup_rh_f", "_setup_rh_r",
            "_setup_spr_f", "_setup_spr_r",
            "_setup_dmp_f_comp", "_setup_dmp_f_ext",
            "_setup_dmp_r_comp", "_setup_dmp_r_ext",
            "_setup_arb_f", "_setup_arb_r",
            "_setup_cam_f", "_setup_cam_r",
            "_setup_toe_f", "_setup_toe_r",
            "_setup_aero_f", "_setup_aero_r",
            "_setup_lsd_i", "_setup_lsd_a", "_setup_lsd_d",
            "_setup_lsd_f_i", "_setup_lsd_f_a", "_setup_lsd_f_d",
            "_setup_tvcd", "_setup_torque_dist", "_setup_bb",
            "_setup_tyre_f", "_setup_tyre_r",
            "_setup_ecu", "_setup_ecu_output",
            "_setup_trans_type",
            "_setup_nitrous", "_setup_nitrous_output",
            "_setup_min_weight", "_setup_max_power",
            "_setup_ballast_kg", "_setup_ballast_pos", "_setup_power_rest",
            "_setup_actual_bhp", "_setup_num_gears", "_setup_drivetrain",
            "_setup_label", "_setup_notes",
            "_gear_ratio_spins", "_spin_final_drive", "_spin_top_speed",
            "_lbl_ecu_rec",
            # UI-state widgets referenced by dashboard.py helpers
            "_lbl_car_specs_info",
            "_lbl_bop_info", "_btn_bop_edit", "_btn_bop_reload", "_bop_info_row_label",
            "_lbl_lsd_front", "_lsd_front_widget",
            "_setup_locked_banner",
            # Action/result widgets for existing mixin methods
            "_setup_result_text", "_btn_analyse_setup",
            "_btn_apply_ai_setup", "_btn_revert_setup",
            "_setup_feeling_input",
            "_build_setup_result", "_btn_build_setup", "_btn_set_car_ranges",
            "_btn_baseline",
            "_setup_load_combo", "_lbl_setup_save_status",
            "_btn_applied_in_game", "_lbl_apply_status",
            "_re_brief_label", "_re_brief_input",
            "_btn_reread_gears",
        ]
        for _attr in _RACE_ALIASES:
            setattr(self, _attr, getattr(self._race_form, _attr))

        # State attributes that live on self (not on the form widget)
        self._last_setup_ai_fields: dict = {}
        self._highlighted_fields: set = set()

        # ── Wire Race form buttons to existing mixin methods ──────────────────
        self._race_form._btn_save_setup.clicked.connect(self._setup_save)
        self._race_form._btn_load_setup.clicked.connect(self._setup_load_selected)
        self._race_form._btn_analyse_setup.clicked.connect(self._setup_analyse_ai)
        self._race_form._btn_apply_ai_setup.clicked.connect(self._apply_and_save_ai_setup)
        self._race_form._btn_revert_setup.clicked.connect(self._revert_last_change)
        self._race_form._btn_build_setup.clicked.connect(self._run_build_setup)
        self._race_form._btn_applied_in_game.clicked.connect(
            lambda: self._on_changes_applied_in_game(self._race_form))
        self._race_form._btn_review_outcome.clicked.connect(
            lambda: self._review_experiment_outcome(self._race_form))
        # Race-form baseline button builds BOTH race + qualifying baselines in one
        # go (UAT); the Qualifying form's own button still builds just qualifying.
        self._race_form._btn_baseline.setText("Build Baseline (Race + Quali)")
        self._race_form._btn_baseline.clicked.connect(self._generate_baseline_setup_both)
        self._race_form._btn_set_car_ranges.clicked.connect(self._open_car_ranges_dialog)
        self._race_form._btn_bop_edit.clicked.connect(self._open_bop_file)
        self._race_form._btn_bop_reload.clicked.connect(self._reload_bop_data)

        # ── Wire Qualifying form buttons to per-form handlers ─────────────────
        qf = self._qual_form
        qf._btn_save_setup.clicked.connect(
            lambda: self._setup_save_for_form(self._qual_form)
        )
        qf._btn_load_setup.clicked.connect(
            lambda: self._setup_load_selected_for_form(self._qual_form)
        )
        qf._btn_analyse_setup.clicked.connect(
            lambda: self._setup_analyse_ai_for_form(self._qual_form)
        )
        qf._btn_apply_ai_setup.clicked.connect(
            lambda: self._apply_ai_setup_for_form(self._qual_form)
        )
        qf._btn_revert_setup.clicked.connect(
            lambda: self._revert_last_change_for_form(self._qual_form)
        )
        qf._btn_build_setup.clicked.connect(
            lambda: self._run_build_setup_for_form(self._qual_form)
        )
        qf._btn_applied_in_game.clicked.connect(
            lambda: self._on_changes_applied_in_game(self._qual_form)
        )
        qf._btn_review_outcome.clicked.connect(
            lambda: self._review_experiment_outcome(self._qual_form)
        )
        qf._btn_baseline.clicked.connect(
            lambda: self._generate_baseline_setup_for_form(self._qual_form)
        )
        qf._btn_set_car_ranges.clicked.connect(self._open_car_ranges_dialog)
        qf._btn_bop_edit.clicked.connect(self._open_bop_file)
        qf._btn_bop_reload.clicked.connect(self._reload_bop_data)

        # ── Tyre compound → Lap Data tab default compound (Race form only) ────
        self._race_form._setup_tyre_f.currentTextChanged.connect(
            lambda name: setattr(self, "_default_lap_compound",
                                 self._TYRE_NAME_TO_CODE.get(name, ""))
        )
        self._race_form._setup_tyre_f.currentTextChanged.connect(
            lambda _: self._refresh_live_tyre_label()
        )

        # ── Segmented discipline-view switch ──────────────────────────────────
        # One focused editor at a time (Race / Qualifying) or both side-by-side.
        # A pure visibility toggle over the two existing forms — no data moves.
        _seg_row = QHBoxLayout()
        _seg_row.setSpacing(0)
        _seg_row.addWidget(QLabel("Editor view:", styleSheet=lbl_s))
        self._discipline_view_group = QButtonGroup(container)
        self._disc_view_btns: dict = {}
        _seg_qss = (
            "QPushButton { background:#242424; color:#BBB; border:1px solid #444; "
            "padding:4px 14px; } "
            "QPushButton:checked { background:#1A5C2A; color:white; font-weight:bold; } ")
        for _i, (_key, _label) in enumerate(
                [("race", "Race"), ("qualifying", "Qualifying"), ("both", "Both")]):
            _b = QPushButton(_label)
            _b.setCheckable(True)
            _b.setStyleSheet(_seg_qss)
            _b.setToolTip(
                "Show only the Race setup editor." if _key == "race"
                else "Show only the Qualifying setup editor." if _key == "qualifying"
                else "Show both editors side by side (default).")
            self._discipline_view_group.addButton(_b, _i)
            _b.clicked.connect(
                lambda _checked=False, k=_key: self._on_discipline_view_changed(k))
            self._disc_view_btns[_key] = _b
            _seg_row.addWidget(_b)
        _seg_row.addStretch()
        outer_layout.addLayout(_seg_row)

        # ── QSplitter — Race left, Qualifying right ───────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Wrap each form in a QScrollArea so it scrolls independently
        race_scroll = QScrollArea()
        race_scroll.setWidgetResizable(True)
        race_scroll.setWidget(self._race_form)
        race_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        qual_scroll = QScrollArea()
        qual_scroll.setWidgetResizable(True)
        qual_scroll.setWidget(self._qual_form)
        qual_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        splitter.addWidget(race_scroll)
        splitter.addWidget(qual_scroll)
        splitter.setSizes([1, 1])  # equal initial split
        outer_layout.addWidget(splitter, 1)  # the splitter takes all extra height

        # Keep scroll-area refs so the view switch can toggle their visibility.
        self._race_scroll = race_scroll
        self._qual_scroll = qual_scroll
        self._disc_view_btns["both"].setChecked(True)  # default: side-by-side

        # ── Shift RPM (shared, below the splitter) — COMPACT single row ───────
        # DEF-UAT-073-017: this box used a 5-row full-width QFormLayout that ate a large vertical band and
        # squeezed the setup fields. It is now ONE compact row (Qualifying · Race · Live-beep · Recommend)
        # that hugs its content, freeing that space for the car setup.
        _sb = self._config.get("shift_beep", {})
        shift_rpm_box = QGroupBox("Shift RPM")
        shift_rpm_box.setStyleSheet(self._group_style())

        def _mk_rpm_spin(value: int, tip: str) -> QSpinBox:
            s = QSpinBox()
            s.setRange(0, 20000)
            s.setSingleStep(100)
            s.setSuffix(" RPM")
            s.setSpecialValueText("Not set")
            s.setValue(int(value))
            s.setToolTip(tip)
            s.setMaximumWidth(110)
            _set_spin_readonly(s, True)
            return s

        self._spin_shift_rpm_qual = _mk_rpm_spin(
            _sb.get("qual_rpm", _sb.get("rpm", 0)),
            "Optimal RPM to upshift for qualifying / unrestricted power.\nEdit via the Live tab Shift Beep controls.")
        self._spin_shift_rpm_race = _mk_rpm_spin(
            _sb.get("race_rpm", _sb.get("rpm", 0)),
            "Optimal RPM to upshift during the race (may be lower if ECU/power restrictor is applied).\n"
            "Edit via the Live tab Shift Beep controls.")

        _srl = QVBoxLayout(shift_rpm_box)
        _srl.setContentsMargins(10, 4, 10, 4)
        _srl.setSpacing(3)
        _srr = QHBoxLayout()
        _srr.setSpacing(6)
        _srr.addWidget(QLabel("Qualifying:", styleSheet=f"color:{_TEXT};"))
        _srr.addWidget(self._spin_shift_rpm_qual)
        _srr.addSpacing(14)
        _srr.addWidget(QLabel("Race:", styleSheet=f"color:{_TEXT};"))
        _srr.addWidget(self._spin_shift_rpm_race)
        _srr.addSpacing(14)
        _srr.addWidget(QLabel("Live beep uses:", styleSheet=f"color:{_TEXT};"))
        self._setup_type.setMaximumWidth(150)
        _srr.addWidget(self._setup_type)
        _srr.addSpacing(14)
        # ENH-073-001: recommend the shift RPM from the car's REAL data (never fabricated).
        try:
            from ui import ngr_theme as _ngr_sr
            self._btn_recommend_shift_rpm = QPushButton("Recommend from car")
            self._btn_recommend_shift_rpm.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_recommend_shift_rpm.setStyleSheet(_ngr_sr.secondary_button_qss())
            self._btn_recommend_shift_rpm.setMaximumWidth(170)
            self._btn_recommend_shift_rpm.setToolTip(
                "Suggest the shift-beep RPM from the car's own data. Drive the car once so GT7 broadcasts its "
                "rpm-alert band for a high-confidence value; no value is guessed.")
            self._btn_recommend_shift_rpm.clicked.connect(self._on_recommend_shift_rpm)
            _srr.addWidget(self._btn_recommend_shift_rpm)
            _srr.addStretch(1)
            _srl.addLayout(_srr)
            self._shift_rpm_reco_lbl = QLabel("")
            self._shift_rpm_reco_lbl.setWordWrap(True)
            self._shift_rpm_reco_lbl.setStyleSheet(f"color:{_ngr_sr.TEXT_DIM}; font-size:{_ngr_sr.FS_CAPTION}pt;")
            _srl.addWidget(self._shift_rpm_reco_lbl)
        except Exception:  # pragma: no cover - defensive; the box must still build
            self._btn_recommend_shift_rpm = None
            self._shift_rpm_reco_lbl = None
            _srr.addStretch(1)
            _srl.addLayout(_srr)
        # hug the content vertically so the box never stretches into a tall band
        shift_rpm_box.setMaximumHeight(shift_rpm_box.sizeHint().height() + 8)
        outer_layout.addWidget(shift_rpm_box)

        self._refresh_setup_combo()
        self._refresh_qual_setup_combo()
        # Sprint 10: seed the saved-vs-applied-in-GT7 three-state labels.
        self._refresh_apply_status_for_form(self._race_form)
        self._refresh_apply_status_for_form(self._qual_form)
        return container

    def _on_recommend_shift_rpm(self) -> None:
        """ENH-073-001: fill the shift-beep RPM from the car's REAL data. Prefers GT7's per-car rpm-alert band
        (from the last live packet), else the car spec's peak-power RPM. Never fabricates — an unknown car
        yields a clear 'drive it first' message rather than a guessed value. Never raises."""
        try:
            from strategy.shift_rpm_recommendation import recommend_shift_rpm
            rpm_alert_max = None
            p = getattr(self, "_last_packet", None)
            if p is not None:
                rpm_alert_max = getattr(p, "rpm_alert_max", None)
            power_rpm = None
            try:
                _name, specs = self._load_car_specs_for_current()
                power_rpm = (specs or {}).get("power_rpm")
            except Exception:
                power_rpm = None
            rec = recommend_shift_rpm(rpm_alert_max=rpm_alert_max, power_rpm=power_rpm)
            lbl = getattr(self, "_shift_rpm_reco_lbl", None)
            if rec.qualifying_rpm is None:
                if lbl is not None:
                    lbl.setText(rec.rationale)   # honest "no data yet — drive the car" message
                return
            sb = self._config.setdefault("shift_beep", {})
            sb["qual_rpm"] = int(rec.qualifying_rpm)
            sb["race_rpm"] = int(rec.race_rpm)
            self._persist_config()
            # reflect on the read-only Setup Builder displays + the editable Live-tab spins
            for attr, val in (("_spin_shift_rpm_qual", rec.qualifying_rpm), ("_spin_shift_rpm_race", rec.race_rpm),
                              ("_spin_live_shift_rpm_qual", rec.qualifying_rpm),
                              ("_spin_live_shift_rpm_race", rec.race_rpm)):
                w = getattr(self, attr, None)
                if w is not None:
                    try:
                        w.setValue(int(val))
                    except Exception:
                        pass
            if lbl is not None:
                lbl.setText(f"[{rec.confidence.value.upper()}] Qualifying {rec.qualifying_rpm} · "
                            f"Race {rec.race_rpm} rpm — {rec.rationale}")
        except Exception:  # pragma: no cover - defensive
            pass

    def _current_setup_dict(self) -> dict:
        """Read all manual fields including editable gear ratios.

        Phase 5: the event-identity fields (car/track/weather/bop) come from
        the canonical EventContext (DB-first) instead of the legacy fan-out —
        byte-identical in sync. Safe off the UI thread too (the voice query
        listener holds this as its setup getter): SessionDB is
        check_same_thread=False with an internal lock.
        """
        gear_ratios = [s.value() for s in self._gear_ratio_spins if s.value() > 0.0]
        _ev_ctx = self._build_event_context()
        return {
            "name":      _ev_ctx.car or "Unknown Car",
            "car":       _ev_ctx.car or "Unknown Car",
            "setup_label": self._setup_label.text().strip() or "Setup 1",
            "track":     _ev_ctx.track,
            "condition": {
                "Fixed Dry": "Dry", "Dry": "Dry", "Random Weather": "Dry",
                "Fixed Wet": "Wet", "Wet": "Wet", "Heavy Rain": "Wet",
                "Light Rain": "Damp", "Wet Risk": "Damp", "Damp": "Damp",
            }.get(_ev_ctx.weather, "Dry"),
            "setup_type": (
                self._race_form.purpose + " Setup"
                if hasattr(self, "_race_form")
                else self._setup_type.currentText()
            ),
            "ride_height_front": self._setup_rh_f.value(),
            "ride_height_rear":  self._setup_rh_r.value(),
            "springs_front": self._setup_spr_f.value(),
            "springs_rear":  self._setup_spr_r.value(),
            "dampers_front_comp": self._setup_dmp_f_comp.value(),
            "dampers_front_ext":  self._setup_dmp_f_ext.value(),
            "dampers_rear_comp":  self._setup_dmp_r_comp.value(),
            "dampers_rear_ext":   self._setup_dmp_r_ext.value(),
            "arb_front":     self._setup_arb_f.value(),
            "arb_rear":      self._setup_arb_r.value(),
            "camber_front":  self._setup_cam_f.value(),
            "camber_rear":   self._setup_cam_r.value(),
            "toe_front":     self._setup_toe_f.value(),
            "toe_rear":      self._setup_toe_r.value(),
            "aero_front":    self._setup_aero_f.value(),
            "aero_rear":     self._setup_aero_r.value(),
            "lsd_initial":   self._setup_lsd_i.value(),
            "lsd_accel":     self._setup_lsd_a.value(),
            "lsd_decel":     self._setup_lsd_d.value(),
            "lsd_front_initial": self._setup_lsd_f_i.value() if self._setup_drivetrain.currentText() == "AWD" else 0,
            "lsd_front_accel":   self._setup_lsd_f_a.value() if self._setup_drivetrain.currentText() == "AWD" else 0,
            "lsd_front_decel":   self._setup_lsd_f_d.value() if self._setup_drivetrain.currentText() == "AWD" else 0,
            "tvcd":          self._setup_tvcd.currentText(),
            "torque_distribution_rear": self._setup_torque_dist.value(),
            "brake_bias_front": self._setup_bb.value(),
            "ballast_kg":       self._setup_ballast_kg.value(),
            "ballast_position": self._setup_ballast_pos.value(),
            "power_restrictor": self._setup_power_rest.value(),
            "tyre_front":     self._setup_tyre_f.currentText(),
            "tyre_rear":      self._setup_tyre_r.currentText(),
            "ecu_ingame":     self._setup_ecu.currentText(),
            "ecu_ingame_output": self._setup_ecu_output.value(),
            "transmission_type": self._setup_trans_type.currentText(),
            "nitrous_type":   self._setup_nitrous.currentText(),
            "nitrous_output": self._setup_nitrous_output.value(),
            "notes":          self._setup_notes.text().strip(),
            "ecu_recommendation": self._lbl_ecu_rec.text() if hasattr(self, "_lbl_ecu_rec") else "",
            "bop_race":       _ev_ctx.bop_enabled,
            "gear_ratios":    gear_ratios,
            "final_drive":    self._spin_final_drive.value(),
            "transmission_max_speed_kmh": int(self._spin_top_speed.value()),
            "captured_at":    time.strftime("%Y-%m-%d %H:%M"),
        }

    def _fill_setup_fields(self, d: dict) -> None:
        car = d.get("name", "")
        if car:
            self._autofill_car_specs(car)
        # Re-bound spinbox ranges for this car BEFORE setting values, so per-car
        # range overrides take effect and values are not silently truncated.
        # NOTE: _rebound_setup_spinboxes must NOT trigger an AI/build call.
        self._rebound_setup_spinboxes(car or None)
        # The setup type is now spatial (two side-by-side forms with fixed purposes).
        # Loading a saved setup does NOT switch the tab-level live-session combo
        # (self._setup_type) — that combo controls shift-RPM threshold selection,
        # not which form panel is active.  The form panel is fixed by its purpose.
        self._setup_rh_f.setValue(d.get("ride_height_front", 80))
        self._setup_rh_r.setValue(d.get("ride_height_rear", 80))
        self._setup_spr_f.setValue(d.get("springs_front", 3.50))
        self._setup_spr_r.setValue(d.get("springs_rear",  3.00))
        self._setup_dmp_f_comp.setValue(d.get("dampers_front_comp", d.get("dampers_front", 30)))
        self._setup_dmp_f_ext.setValue(d.get("dampers_front_ext", d.get("dampers_front", 40)))
        self._setup_dmp_r_comp.setValue(d.get("dampers_rear_comp", d.get("dampers_rear", 25)))
        self._setup_dmp_r_ext.setValue(d.get("dampers_rear_ext", d.get("dampers_rear", 35)))
        self._setup_arb_f.setValue(d.get("arb_front", 5))
        self._setup_arb_r.setValue(d.get("arb_rear", 4))
        self._setup_cam_f.setValue(abs(d.get("camber_front", 1.0)))
        self._setup_cam_r.setValue(abs(d.get("camber_rear", 1.5)))
        self._setup_toe_f.setValue(d.get("toe_front", 0.00))
        self._setup_toe_r.setValue(d.get("toe_rear", 0.05))
        self._setup_aero_f.setValue(d.get("aero_front", 400))
        self._setup_aero_r.setValue(d.get("aero_rear", 600))
        self._setup_lsd_i.setValue(d.get("lsd_initial", 10))
        self._setup_lsd_a.setValue(d.get("lsd_accel", 15))
        self._setup_lsd_d.setValue(d.get("lsd_decel", 5))
        self._setup_lsd_f_i.setValue(int(d.get("lsd_front_initial", 10)))
        self._setup_lsd_f_a.setValue(int(d.get("lsd_front_accel", 15)))
        self._setup_lsd_f_d.setValue(int(d.get("lsd_front_decel", 5)))
        _tvcd_idx = self._setup_tvcd.findText(d.get("tvcd", "None"))
        if _tvcd_idx >= 0: self._setup_tvcd.setCurrentIndex(_tvcd_idx)
        self._setup_torque_dist.setValue(int(d.get("torque_distribution_rear", 50)))
        self._setup_bb.setValue(int(d.get("brake_bias_front", 0)))
        self._setup_ballast_kg.setValue(float(d.get("ballast_kg", 0.0)))
        self._setup_ballast_pos.setValue(int(d.get("ballast_position", 0)))
        self._setup_power_rest.setValue(float(d.get("power_restrictor", 100.0)))
        from data.tyres import normalise_name as _nn
        _tf = _nn(d.get("tyre_front", "Racing Medium")) or "Racing Medium"
        _tf_idx = self._setup_tyre_f.findText(_tf)
        if _tf_idx >= 0: self._setup_tyre_f.setCurrentIndex(_tf_idx)
        _tr = _nn(d.get("tyre_rear", "Racing Medium")) or "Racing Medium"
        _tr_idx = self._setup_tyre_r.findText(_tr)
        if _tr_idx >= 0: self._setup_tyre_r.setCurrentIndex(_tr_idx)
        _ecu_idx = self._setup_ecu.findText(d.get("ecu_ingame", "Stock"))
        if _ecu_idx >= 0: self._setup_ecu.setCurrentIndex(_ecu_idx)
        self._setup_ecu_output.setValue(float(d.get("ecu_ingame_output", 100.0)))
        _tt_idx = self._setup_trans_type.findText(d.get("transmission_type", "Stock"))
        if _tt_idx >= 0: self._setup_trans_type.setCurrentIndex(_tt_idx)
        _nos_idx = self._setup_nitrous.findText(d.get("nitrous_type", "None"))
        if _nos_idx >= 0: self._setup_nitrous.setCurrentIndex(_nos_idx)
        self._setup_nitrous_output.setValue(float(d.get("nitrous_output", 0.0)))
        self._setup_label.setText(d.get("setup_label", "Setup 1"))
        self._setup_notes.setText(d.get("notes", ""))
        ecu = d.get("ecu_recommendation", "")
        self._lbl_ecu_rec.setText(ecu if ecu and ecu != "—" else "—")
        saved_ratios = d.get("gear_ratios", [])
        for i, spin in enumerate(self._gear_ratio_spins):
            spin.setValue(float(saved_ratios[i]) if i < len(saved_ratios) else 0.0)
        self._gear_ratios_captured = any(r > 0.0 for r in saved_ratios)
        self._spin_final_drive.setValue(float(d.get("final_drive", 0.0)))
        self._spin_top_speed.setValue(float(d.get("transmission_max_speed_kmh", 0)))

    # ── Applied-in-GT7 checkpoint (Sprint 10 UI) ──────────────────────────────
    # Identity/advisory keys that are NOT part of what the driver dials into GT7's
    # tuning menu; excluded from the checkpoint hash so re-reading the same setup
    # (which restamps captured_at) doesn't read as a pending change.
    _APPLY_CHECKPOINT_META = frozenset({
        "name", "car", "setup_label", "track", "condition", "setup_type",
        "notes", "ecu_recommendation", "captured_at", "bop_race",
    })

    def _apply_checkpoint_fields(self, form: "SetupFormWidget") -> dict:
        """The tuning-field subset of a form's setup used for apply comparison."""
        try:
            d = form.current_setup_dict()
        except Exception:
            return {}
        out = {}
        for k, v in (d or {}).items():
            if k in self._APPLY_CHECKPOINT_META:
                continue
            # Lists (gear ratios) → a hashable, stable representation.
            out[k] = tuple(v) if isinstance(v, list) else v
        return out

    def _apply_checkpoint_scope(self, form: "SetupFormWidget"):
        """(car_id, track, layout_id, purpose, setup_id) key for this form's setup."""
        car_id, track, layout_id, setup_id = 0, "", "", ""
        try:
            ev = self._build_event_context()
            track = str(getattr(ev, "track", "") or "")
            layout_id = str(getattr(ev, "layout_id", "") or "")
            car = str(getattr(ev, "car", "") or "")
            if self._db is not None and car:
                car_id = int(self._db.get_car_id(car) or 0)
        except Exception:
            pass
        purpose = getattr(form, "purpose", "Race") or "Race"
        # Reference the saved setup id when the current label matches one, else the
        # label text — used only for the checkpoint id, not the scope lookup.
        try:
            label = form._setup_label.text().strip()
            for s in (getattr(self, "_saved_setups", []) or []):
                if s.get("setup_label") == label and s.get("setup_id"):
                    setup_id = str(s.get("setup_id"))
                    break
            if not setup_id:
                setup_id = label
        except Exception:
            pass
        return car_id, track, layout_id, purpose, setup_id

    def _latest_applied_checkpoint(self, form: "SetupFormWidget"):
        """Rebuild the last AppliedCheckpoint for this form's scope, or None."""
        if self._db is None:
            return None
        car_id, track, layout_id, purpose, _sid = self._apply_checkpoint_scope(form)
        row = self._db.get_latest_applied_checkpoint(car_id, track, layout_id, purpose)
        if not row:
            return None
        import json as _json
        from data.applied_checkpoint import AppliedCheckpoint
        try:
            fields = _json.loads(row.get("fields_json") or "{}")
        except Exception:
            fields = {}
        # JSON turns tuples into lists; re-tuple so hashes match the live fields.
        fields = {k: (tuple(v) if isinstance(v, list) else v)
                  for k, v in fields.items()}
        return AppliedCheckpoint(
            checkpoint_id=str(row.get("checkpoint_id") or ""),
            setup_id=str(row.get("setup_id") or ""),
            setup_hash=str(row.get("setup_hash") or ""),
            fields=fields,
            confirmed_at=str(row.get("confirmed_at") or ""),
        )

    def _on_changes_applied_in_game(self, form: "SetupFormWidget") -> None:
        """Record that the current setup was applied in GT7 (button handler)."""
        from data.applied_checkpoint import make_checkpoint
        fields = self._apply_checkpoint_fields(form)
        if not fields:
            return
        car_id, track, layout_id, purpose, setup_id = self._apply_checkpoint_scope(form)
        confirmed_at = time.strftime("%Y-%m-%d %H:%M")
        cp = make_checkpoint(setup_id=setup_id, fields=fields,
                             confirmed_at=confirmed_at)
        if self._db is not None:
            self._db.save_applied_checkpoint(car_id, track, layout_id, purpose, cp)
            # Engineering-Brain Phase 2: link this applied checkpoint to the
            # experiment awaiting apply for this scope (→ APPLIED + proposed-vs-
            # applied comparison). Does NOT auto-apply and NEVER alters the
            # original recommendation. Best-effort; never blocks the UI action.
            try:
                self._last_apply_match = self._db.link_apply_to_experiment(
                    car_id=car_id, track=track, layout_id=layout_id,
                    discipline=purpose, parent_setup_id=setup_id,
                    checkpoint_id=cp.checkpoint_id, applied_fields=dict(fields))
            except Exception:
                self._last_apply_match = None

        # UAT Finding 1: make this the canonical active setup for the Live Race
        # Engineer. Persist the COMPLETE setup snapshot (not just the tuning
        # subset used for the three-state comparison) under the authority so the
        # Live baseline, telemetry attachment and analysis gate all resolve to
        # exactly what was applied — no duplicate manual selection.
        auth = getattr(self, "_setup_authority", None)
        if auth is not None:
            try:
                from data.setup_state_authority import SetupIdentity
                ev = self._build_event_context()
                ident = SetupIdentity(
                    car=str(getattr(ev, "car", "") or ""),
                    track=str(getattr(ev, "track", "") or ""),
                    layout_id=str(getattr(ev, "layout_id", "") or ""),
                )
                try:
                    complete = dict(form.current_setup_dict() or {})
                except Exception:
                    complete = dict(fields)
                name = ""
                try:
                    name = form._setup_label.text().strip()
                except Exception:
                    name = ""
                auth.mark_applied(
                    ident, setup_id=setup_id or name,
                    name=name or setup_id or f"{purpose} setup",
                    fields=complete, purpose=purpose, applied_at=confirmed_at)
                self._refresh_active_setup_display()
            except Exception:
                pass

        try:
            self._bridge.event_log_entry.emit(
                f"[Setup] {purpose} setup confirmed applied in GT7 ({confirmed_at})")
        except Exception:
            pass
        self._refresh_apply_status_for_form(form)

        # UAT Finding 3: flip the structured recommendation rows proposed->applied
        # (visibility/highlight unchanged) when the Race setup is applied.
        if form is getattr(self, "_race_form", None):
            view = getattr(self, "_setup_rec_view", None)
            if view is not None and view.current_vm() is not None:
                view.mark_applied()
        # Phase 3: an applied experiment now exists → reveal the outcome-review action.
        try:
            btn = getattr(form, "_btn_review_outcome", None)
            if btn is not None:
                btn.setVisible(True)
        except Exception:
            pass

    def _review_experiment_outcome(self, form: "SetupFormWidget") -> None:
        """Driver-triggered, OFF-THREAD closed-loop outcome review (Phase 3).

        Finds the latest applied experiment for this scope and evaluates it against
        measured test evidence via the deterministic outcome engine. Read-only:
        it never applies or reverts a setup. Runs on a worker thread (never the
        telemetry packet thread); the result is drained + rendered on the Qt tick."""
        db = getattr(self, "_db", None)
        lbl = getattr(form, "_lbl_outcome_summary", None)
        if db is None:
            return
        try:
            car_id, track, layout_id, purpose, _sid = self._apply_checkpoint_scope(form)
        except Exception:
            return
        exp = db.find_latest_reviewable_experiment(car_id, track, layout_id, purpose)
        if exp is None:
            if lbl is not None:
                lbl.setText("No applied experiment to review for this car/track/layout yet.")
            return
        if lbl is not None:
            lbl.setText("Evaluating test outcome…")
        # Pick the two most-recent sessions for this scope as test/baseline windows.
        test_sid = base_sid = None
        try:
            sessions = db.get_practice_sessions(car_id, track) or []
            if sessions:
                test_sid = sessions[0].get("id")
            if len(sessions) > 1:
                base_sid = sessions[1].get("id")
        except Exception:
            pass
        import threading as _threading

        q = self._ensure_outcome_queue()
        exp_id = int(exp.get("id") or 0)

        def _worker():
            # Phase 4/5: the canonical assembler resolves the applied-checkpoint scope,
            # selects baseline/test sessions, evaluates lap validity, and assembles
            # per-corner baseline/test observations from the persisted stores — then
            # calls the Phase 3 evaluator with REAL evidence, LEARNS working-window
            # updates from the canonical outcome, and SELECTS the minimum-effective
            # next experiment. Read-only: never applies or reverts a setup.
            try:
                res = db.review_and_learn(
                    exp_id, test_session_id=test_sid, baseline_session_id=base_sid,
                    complete_on_success=True)
            except Exception as exc:  # never let the worker crash the app
                res = {"ok": False, "phase": "infrastructure", "error": str(exc)}
            try:
                q.put((res, form))
            except Exception:
                pass

        _threading.Thread(target=_worker, daemon=True).start()

    def _ensure_outcome_queue(self):
        q = getattr(self, "_outcome_result_queue", None)
        if q is None:
            import queue as _queue
            q = _queue.Queue()
            self._outcome_result_queue = q
        return q

    def _display_outcome_result(self, payload: tuple) -> None:
        """Render a compact, honest outcome summary next to the setup form."""
        try:
            res, form = payload
        except Exception:
            return
        lbl = getattr(form, "_lbl_outcome_summary", None)
        if lbl is None:
            return
        if not isinstance(res, dict) or not res.get("ok"):
            # Distinguish an infrastructure failure from honest engineering
            # insufficiency (never present a DB/parse error as a verdict).
            if (res or {}).get("phase") in ("infrastructure", "assembly"):
                reason = (res or {}).get("error") or (res or {}).get("reason") or "unavailable"
                lbl.setText(f"Outcome review could not run ({res.get('phase')}): {reason}")
                return
            reason = (res or {}).get("reason") or (res or {}).get("error") or "no result"
            lbl.setText(f"Outcome review unavailable: {reason}")
            return
        status = str(res.get("status", "")).replace("_", " ").title()
        conf = str(res.get("confidence_level", "") or "")
        laps = res.get("valid_laps", 0)
        nxt = str(res.get("next_action", "") or "").replace("_", " ")
        # Canonical driver-facing decision state (Phase 4 authority) — the UI
        # renders it, never re-derives it.
        decision = ""
        try:
            from strategy.setup_decision_status import resolve_setup_decision
            _exp_status = "rejected" if res.get("status") == "regression" else (
                "completed" if res.get("lifecycle") and "completed" in res.get("lifecycle")
                else "ready_for_review")
            decision = resolve_setup_decision(
                experiment_status=_exp_status, outcome_status=res.get("status", ""),
                outcome_confidence_level=conf,
                rollback_eligible=bool(res.get("rollback_eligible"))).state.value
        except Exception:
            decision = ""
        parts = [f"Decision: {decision.replace('_',' ').title()}." if decision else "",
                 f"Outcome: {status} (confidence {conf}; {laps} valid laps).",
                 f"Recommended next: {nxt}."]
        # Evidence readiness (from the canonical assembler).
        asm = res.get("assembly") or {}
        if asm:
            ct = asm.get("corner_test_count", 0)
            cb = asm.get("corner_baseline_count", 0)
            twl = asm.get("test_whole_lap") or {}
            rej = twl.get("rejected_lap_count", 0)
            parts.append(f"Evidence: {ct} test / {cb} baseline corners; "
                         f"{rej} rejected laps.")
            miss = asm.get("missing_evidence") or []
            if miss:
                parts.append("Missing: " + "; ".join(str(m) for m in miss[:2]) + ".")
        parts = [p for p in parts if p]
        regs = res.get("regressions") or []
        if regs:
            parts.append("Regressions: " + "; ".join(str(r) for r in regs[:3]) + ".")
        imps = res.get("improvements") or []
        if imps:
            parts.append("Improvements: " + "; ".join(str(i) for i in imps[:3]) + ".")
        fds = res.get("failed_directions") or []
        if fds:
            strengths = {str(f.get("strength")) for f in fds}
            if "lockout" in strengths:
                parts.append("A failed-direction LOCKOUT was recorded for this scope.")
            elif "caution" in strengths:
                parts.append("A failed-direction CAUTION was recorded for this scope.")
        if res.get("rollback_eligible"):
            parts.append(f"Rollback target if you revert: {res.get('rollback_target') or 'parent setup'} "
                         "(not applied automatically).")
        # Phase 5: learning + the selected minimum-effective next experiment.
        learn = res.get("learning") or {}
        if learn.get("ok") and learn.get("updated_fields"):
            parts.append("Learned working windows updated for: "
                         + ", ".join(str(f) for f in learn["updated_fields"][:4]) + ".")
        nxt = res.get("next_experiment") or {}
        sel = nxt.get("selected")
        if sel:
            parts.append(
                f"Next experiment: {sel.get('field')} {sel.get('direction')} "
                f"({sel.get('current_value')}→{sel.get('proposed_value')}). "
                f"{sel.get('selection_rationale', '')} — apply manually to test "
                "(nothing is applied automatically).")
            blocked = [c for c in (nxt.get("rejected") or []) if c.get("hard_blockers")]
            if blocked:
                b0 = blocked[0]
                parts.append(f"Blocked alternative: {b0.get('candidate_id')} — "
                             + "; ".join(b0.get("hard_blockers", [])) + ".")
            # Phase 10: deterministic engineering pre-flight review of the EXACT selected
            # experiment (read-only, advisory, never blocks). Surfaced beside the proposal.
            try:
                ev = self._build_event_context()
                pf = self._db.build_experiment_preflight(
                    dict(sel), car=str(getattr(ev, "car", "") or ""),
                    track=str(getattr(ev, "track", "") or ""),
                    layout_id=str(getattr(ev, "layout_id", "") or ""),
                    discipline=str(getattr(ev, "discipline", "") or "")) \
                    if self._db is not None else {"ok": False}
                if pf.get("ok"):
                    from ui import preflight_review_vm as _pf_vm
                    for _line in _pf_vm.compact_summary(pf):
                        parts.append(_line)
            except Exception:
                pass
        elif nxt.get("no_selection_reason"):
            parts.append("No safe next experiment: "
                         + str(nxt["no_selection_reason"]).replace("_", " ")
                         + " (current setup should be retained / more evidence needed).")
        # Phase 6: current engineering state + multi-symptom development plan.
        plan_wrap = res.get("engineering_plan") or {}
        if plan_wrap.get("ok"):
            snap = plan_wrap.get("snapshot") or {}
            plan = plan_wrap.get("plan") or {}
            parts.append(
                "Engineering state: "
                f"{len(snap.get('resolved') or [])} resolved, "
                f"{len(snap.get('improved') or [])} improved, "
                f"{len(snap.get('unchanged') or [])} unchanged, "
                f"{len(snap.get('worsened') or [])} worsened, "
                f"{len(snap.get('new_issues') or [])} new, "
                f"{len(snap.get('damaged_good') or [])} damaged-good.")
            imm = plan.get("immediate_experiment")
            if imm:
                parts.append(
                    f"Development plan: 1 immediate experiment ({imm.get('field')} "
                    f"{imm.get('direction')}), {len(plan.get('queued') or [])} queued "
                    "hypothesis(es). One change at a time — apply manually.")
            else:
                parts.append(
                    "Development plan: "
                    + str(plan.get("status", "")).replace("_", " ")
                    + " — no immediate setup change; "
                    + f"{len(plan.get('deferred_issues') or [])} review/evidence task(s).")
            if plan.get("conflicts"):
                parts.append(f"{len(plan['conflicts'])} candidate conflict(s) flagged.")
            parts.append("Plan is advisory — setup values are not applied automatically.")
        lbl.setText(" ".join(p for p in parts if p))

    def _refresh_apply_status_for_form(self, form: "SetupFormWidget") -> None:
        """Recompute + render the saved-vs-applied-in-GT7 three-state for ``form``.

        The Race form's status is mirrored to ``self._setup_apply_status`` so the
        Command Centre workflow stepper (dashboard) reflects apply state."""
        from data.applied_checkpoint import compute_apply_status, SetupApplyState
        lbl = getattr(form, "_lbl_apply_status", None)
        if lbl is None:
            return
        checkpoint = self._latest_applied_checkpoint(form)
        has_setup = bool(getattr(self, "_saved_setups", []) or []) or checkpoint is not None
        fields = self._apply_checkpoint_fields(form) if has_setup else None
        status = compute_apply_status(fields, checkpoint)

        _COLOR = {
            SetupApplyState.NOT_SAVED: "#9AA0A6",
            SetupApplyState.CHANGED_SINCE_GT7: "#F0C070",
            SetupApplyState.CONFIRMED_IN_GT7: "#8BC34A",
        }
        _PREFIX = {
            SetupApplyState.NOT_SAVED: "",
            SetupApplyState.CHANGED_SINCE_GT7: "⚠ ",
            SetupApplyState.CONFIRMED_IN_GT7: "✓ ",
        }
        color = _COLOR.get(status.state, "#9AA0A6")
        lbl.setText(_PREFIX.get(status.state, "") + status.message)
        lbl.setStyleSheet(f"color: {color}; font-size: 10px; padding: 2px 0;")
        # The button is only meaningful once there is a setup to confirm.
        btn = getattr(form, "_btn_applied_in_game", None)
        if btn is not None:
            btn.setEnabled(bool(fields))

        # Mirror the Race form's status to the workflow-stepper input the Command
        # Centre reads, then nudge Home to re-render the stepper.
        if form is getattr(self, "_race_form", None):
            self._setup_apply_status = status
            _home_refresh = getattr(self, "_home_refresh", None)
            if callable(_home_refresh):
                try:
                    _home_refresh()
                except Exception:
                    pass

    def _load_car_specs_for_current(self) -> tuple[str, dict]:
        """Return (car_name, specs_dict) for the currently selected car in the Setup tab."""
        car_name = self._config.get("strategy", {}).get("car", "")
        if not car_name:
            return "", {}
        from pathlib import Path
        specs_path = Path(__file__).parent.parent / "data" / "car_specs.json"
        try:
            all_specs: dict = json.loads(specs_path.read_text(encoding="utf-8"))
            return car_name, all_specs.get(car_name, {})
        except Exception:
            return car_name, {}

    def _apply_setup_permissions(
        self,
        bop: bool,
        tuning_allowed: bool,
        allowed_cats: list[str],
    ) -> None:
        if not hasattr(self, "_setup_locked_banner"):
            return
        fully_locked = not tuning_allowed
        partially_restricted = tuning_allowed and bool(allowed_cats)
        if fully_locked:
            if bop:
                msg = ("Setup Builder is locked — BoP is enabled and tuning is not allowed for this Event.\n"
                       "You can view the car and event context but cannot edit or generate a setup.")
            else:
                msg = ("Setup Builder is locked — this Event has tuning disabled.\n"
                       "You can view the car and event context but cannot edit or generate a setup.")
            self._setup_locked_banner.setText(msg)
            self._setup_locked_banner.show()
        else:
            self._setup_locked_banner.hide()
        for cat, attrs in self._SETUP_TUNING_GROUPS.items():
            enabled = not fully_locked and (not partially_restricted or cat in allowed_cats)
            for attr in attrs:
                w = getattr(self, attr, None)
                if w is not None:
                    w.setEnabled(enabled)
            if cat == "transmission":
                for gs in getattr(self, "_gear_ratio_spins", []):
                    gs.setEnabled(enabled and not bop)
        # Tyre compound selection is NEVER locked by BoP in GT7 — BoP only locks
        # mechanical tuning. Always re-enable tyre widgets regardless of permissions.
        for attr in ("_setup_tyre_f", "_setup_tyre_r"):
            w = getattr(self, attr, None)
            if w is not None:
                w.setEnabled(True)
        for attr in ("_setup_label", "_setup_notes"):
            w = getattr(self, attr, None)
            if w:
                w.setEnabled(True)
        # Progressive disclosure (DEF-073): when the Event permits tuning but only a
        # subset of categories, hide the sections that are fully locked out — on BOTH
        # forms — so the operator only scrolls what they can edit. Fully-locked and
        # unrestricted contexts leave every section visible.
        for _form_attr in ("_race_form", "_qual_form"):
            _form = getattr(self, _form_attr, None)
            _apply_vis = getattr(_form, "apply_section_visibility", None)
            if callable(_apply_vis):
                _apply_vis(allowed_cats, partially_restricted)

    def _refresh_setup_combo(self, select_index: int = -1) -> None:
        """Refresh the Race form's load combo (filters to Race setups)."""
        if not hasattr(self, "_setup_load_combo"):
            return
        self._setup_load_combo.blockSignals(True)
        self._setup_load_combo.clear()
        self._setup_load_combo.addItem("— select to load —")   # placeholder at index 0
        for s in self._saved_setups:
            setup_lbl = s.get("setup_label") or "Setup"
            car_name  = s.get("name", "Unnamed")
            label = f"{setup_lbl} ({car_name}) — {s.get('track', '')} [{s.get('setup_type', s.get('session', ''))}]"
            self._setup_load_combo.addItem(label)
        # select_index is relative to _saved_setups; shift by 1 for the placeholder
        if 0 <= select_index < len(self._saved_setups):
            self._setup_load_combo.setCurrentIndex(select_index + 1)
        else:
            self._setup_load_combo.setCurrentIndex(0)   # show placeholder
        self._setup_load_combo.blockSignals(False)

    def _refresh_qual_setup_combo(self, select_index: int = -1) -> None:
        """Refresh the Qualifying form's load combo (all setups; filter to Q if desired)."""
        if not hasattr(self, "_qual_form"):
            return
        combo = self._qual_form._setup_load_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— select to load —")
        for s in self._saved_setups:
            setup_lbl = s.get("setup_label") or "Setup"
            car_name  = s.get("name", "Unnamed")
            label = f"{setup_lbl} ({car_name}) — {s.get('track', '')} [{s.get('setup_type', s.get('session', ''))}]"
            combo.addItem(label)
        if 0 <= select_index < len(self._saved_setups):
            combo.setCurrentIndex(select_index + 1)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Per-form handlers for the Qualifying panel
    # ------------------------------------------------------------------

    def _setup_save_for_form(self, form: "SetupFormWidget") -> None:
        """Save the setup from ``form`` (used for the Qualifying panel)."""
        from PyQt6.QtWidgets import QMessageBox
        _evt_name = ""
        if hasattr(self, "_active_event"):
            _evt_name = (self._active_event() or {}).get("name", "") or ""
        if not _evt_name:
            QMessageBox.warning(
                self,
                "No Active Event",
                "Please select an active event in the Event Planner before saving a setup.",
            )
            return
        from ui.setup_name_helper import resolve_save_name
        _prefix = form.purpose_prefix()
        form._setup_label.setText(
            resolve_save_name(
                form._setup_label.text(),
                _prefix,
                _evt_name,
                self._saved_setups,
            )
        )
        form.clear_highlights()
        if form.purpose == "Race":
            self._save_re_brief_to_active_event()
        d = form.current_setup_dict()
        ca = self._config.setdefault("car_setup", {})
        existing = next(
            (i for i, s in enumerate(self._saved_setups)
             if s.get("name") == d["name"] and s.get("setup_label") == d["setup_label"]),
            None,
        )
        if existing is not None:
            d["setup_id"] = self._saved_setups[existing].get("setup_id") or d.get("setup_id")
            self._saved_setups[existing] = d
            target_idx = existing
        else:
            if not d.get("setup_id"):
                next_id = ca.get("next_setup_id", 1)
                d["setup_id"] = next_id
                ca["next_setup_id"] = next_id + 1
            self._saved_setups.append(d)
            target_idx = len(self._saved_setups) - 1

        if self._db is not None:
            _meta_keys = {"name", "setup_label", "setup_id", "captured_at", "ai_notes"}
            _car_name = d.get("name", "")
            _car_id = self._db.get_car_id(_car_name) if _car_name else 0
            _event_id = int(self._build_event_context().event_id or 0)
            _label = d.get("setup_label", "Setup")
            _fields = {k: v for k, v in d.items() if k not in _meta_keys}
            _existing_db_id = d.get("setup_id") if existing is not None else 0
            if _existing_db_id:
                self._db.update_setup(_existing_db_id, _label, _fields)
            else:
                _new_id = self._db.save_setup(_car_id, _event_id, _label, _fields)
                d["setup_id"] = _new_id
                self._saved_setups[target_idx]["setup_id"] = _new_id

        ca["setups"] = self._saved_setups
        self._persist_config()
        self._refresh_setup_combo(select_index=target_idx)
        self._refresh_qual_setup_combo(select_index=target_idx)
        self._refresh_all_setup_combos()
        self._bridge.event_log_entry.emit(f"[Setup] saved: {d['name']} (ID {d.get('setup_id', '?')})")
        lbl = d.get("setup_label", "") or "Setup"
        form._lbl_setup_save_status.setText(f"Saved: {lbl}  (ID {d.get('setup_id', '?')})")
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(4000, lambda: (
            form._lbl_setup_save_status.setText("")
            if hasattr(form, "_lbl_setup_save_status") else None
        ))
        # Sprint 10: saving may create pending (not-yet-applied-in-GT7) changes.
        self._refresh_apply_status_for_form(form)

    def _setup_load_selected_for_form(self, form: "SetupFormWidget") -> None:
        """Load the selected setup into ``form``."""
        idx = form._setup_load_combo.currentIndex()
        real_idx = idx - 1
        if 0 <= real_idx < len(self._saved_setups):
            form.fill_setup_fields(self._saved_setups[real_idx])
            self._after_setup_load()

    def _setup_analyse_ai_for_form(self, form: "SetupFormWidget") -> None:
        """Run the AI setup-analysis for ``form`` and put results in that form's result text."""
        if self._driving_advisor is None:
            form._setup_result_text.setPlainText("Driving advisor not available.")
            return
        d = form.current_setup_dict()
        _car_name, _car_specs = self._load_car_specs_for_current()
        setup_id = d.get("setup_id")
        n_laps = 5
        if setup_id:
            count = sum(
                1 for r in range(self._lap_table.rowCount())
                if (w := self._lap_table.cellWidget(r, 14)) is not None
                and w.currentText().startswith(f"{setup_id} —")
            )
            if count > 0:
                n_laps = count
        feeling = form._setup_feeling_input.toPlainText().strip()
        form._setup_result_text.setPlainText("Analysing setup… please wait.")
        form._btn_analyse_setup.setEnabled(False)
        import threading as _threading
        _ai_snap = self._build_setup_inputs()
        _allowed  = _ai_snap.allowed_tuning_or_none()
        _locked   = _ai_snap.tuning_locked
        _compound = _ai_snap.mandatory_compounds_str
        # Group 45: pass session context params to the backend.
        # purpose: form.purpose is "Race" or "Qualifying" — always available here.
        _purpose = form.purpose
        # car_class: car_specs.category (empty string when no specs loaded — backend maps to neutral).
        _car_class = (_car_specs or {}).get("category", "")
        # drivetrain: explicit combo selection wins (empty string = "Auto-detect" →
        # backend falls back to CAR_DRIVETRAIN_OVERRIDES by car name, e.g. Porsche).
        _drivetrain = (
            form._setup_drivetrain.currentData()
            if hasattr(form, "_setup_drivetrain")
            else ""
        ) or ""
        # Candidate columns (Race/Quali forms + from-scratch base) — Qt read on the
        # main thread here, before the worker.
        _tp_form = self._build_track_tune_profile_for_current()
        _extra_candidates = self._build_candidate_columns(
            _car_name, _drivetrain, _allowed, _locked, _tp_form)

        def _worker():
            try:
                resp = self._driving_advisor.build_combined_setup_response(
                    d, n_laps=n_laps, car_name=_car_name, car_specs=_car_specs,
                    feeling=feeling or None,
                    allowed_tuning=_allowed, tuning_locked=_locked,
                    compound=_compound,
                    purpose=_purpose,
                    car_class=_car_class,
                    drivetrain=_drivetrain,
                    extra_candidates=_extra_candidates,
                    live_corner_aggregates=self._live_corner_aggregates())
                self._setup_result_queue.put(("ok", resp, "analyse_setup", feeling or None, form))
            except Exception as exc:
                self._setup_result_queue.put(("error", str(exc), "analyse_setup", None, form))

        # Persist the live per-corner slip evidence (UI thread) so the advisor's
        # cross-session read includes this run before it diagnoses.
        self._persist_live_corner_slip()
        _threading.Thread(target=_worker, daemon=True).start()

    def _apply_ai_setup_for_form(self, form: "SetupFormWidget") -> None:
        """Apply AI-recommended fields to ``form`` (per-form apply button handler)."""
        if not getattr(form, "last_ai_fields", {}):
            return
        form.apply_ai_fields(form.last_ai_fields)
        # Keep the form's structured Q/R setup name — do NOT rename to "AI Fix N".
        # Save advances the structured name to the next numbered attempt.
        form.last_ai_fields = {}
        # Auto-save the applied setup (see _autosave_applied_setup) — applying it
        # means it is now the current setup on the car.
        self._autosave_applied_setup(form)
        form._btn_apply_ai_setup.setVisible(False)
        self._refresh_revert_buttons()

    # ------------------------------------------------------------------
    # Discipline-view switch + rollback controls (one-setup editor)
    # ------------------------------------------------------------------

    def _on_discipline_view_changed(self, mode: str) -> None:
        """Toggle which setup editor(s) are visible: 'race', 'qualifying' or 'both'.

        Pure visibility switch over the two existing forms — no data is moved or
        cleared, so the aliased Race-form mixin methods keep working unchanged.
        """
        _r = getattr(self, "_race_scroll", None)
        _q = getattr(self, "_qual_scroll", None)
        if _r is None or _q is None:
            return
        _r.setVisible(mode in ("race", "both"))
        _q.setVisible(mode in ("qualifying", "both"))

    def _refresh_revert_buttons(self) -> None:
        """Re-evaluate the 'Revert last change' control on both editor forms."""
        for _f in (getattr(self, "_race_form", None), getattr(self, "_qual_form", None)):
            if _f is not None:
                self._refresh_revert_button_for_form(_f)

    def _revert_state_for_current_event(self) -> dict:
        """Pure rollback decision for the active car/track/layout (empty when none)."""
        from strategy.setup_lineage import revert_button_state
        try:
            evc = self._build_event_context()
            cid = int(self._car_id_ref[0]) if getattr(self, "_car_id_ref", None) else 0
            if cid <= 0 or not getattr(evc, "track", ""):
                return {"visible": False, "revert_changes": [], "reason": "", "count": 0}
            lineage = self._db.get_lineage(cid, evc.track, evc.layout_id)
            return revert_button_state(lineage)
        except Exception:
            return {"visible": False, "revert_changes": [], "reason": "", "count": 0}

    def _refresh_revert_button_for_form(self, form: "SetupFormWidget") -> None:
        """Show/hide ``form``'s revert button from the (pure) rollback decision."""
        btn = getattr(form, "_btn_revert_setup", None)
        if btn is None:
            return
        st = self._revert_state_for_current_event()
        btn.setVisible(bool(st.get("visible")))
        if st.get("visible"):
            btn.setToolTip(st.get("tooltip") or btn.toolTip())

    def _revert_last_change(self) -> None:
        """Race-form revert handler (delegates to the per-form implementation)."""
        self._revert_last_change_for_form(self._race_form)

    def _revert_last_change_for_form(self, form: "SetupFormWidget") -> None:
        """Revert ``form`` to the previous setup when the last change tested worse.

        Restores the changed fields to their proven prior values (from the lineage
        delta), records the rollback as a new lineage node so the chain stays honest,
        and auto-saves — mirroring the Apply idiom. Never authors a new value; only
        puts back a value the driver has already run. Requires confirmation.
        """
        from strategy.setup_lineage import apply_revert_to_setup
        st = self._revert_state_for_current_event()
        if not st.get("visible") or not st.get("revert_changes"):
            QMessageBox.information(
                self, "Nothing to revert",
                "There's no worse-rated change to roll back right now.")
            self._refresh_revert_button_for_form(form)
            return
        _fields = ", ".join(
            str(c.get("field", "")).replace("_", " ") for c in st["revert_changes"])
        _resp = QMessageBox.question(
            self, "Revert last change",
            f"Revert {st['count']} field(s) to your previous setup?\n\n"
            f"{_fields}\n\n{st.get('reason', '')}")
        if _resp != QMessageBox.StandardButton.Yes:
            return
        reverted = apply_revert_to_setup(form.current_setup_dict(), st["revert_changes"])
        form.fill_setup_fields(reverted)
        # Record the rollback as a new lineage node (best-effort) so subsequent
        # rollback decisions see that this direction was already reverted.
        try:
            import json as _json
            evc = self._build_event_context()
            cid = int(self._car_id_ref[0]) if getattr(self, "_car_id_ref", None) else 0
            if cid > 0 and getattr(evc, "track", ""):
                self._db.record_lineage(
                    cid, evc.track, evc.layout_id,
                    changes_json=_json.dumps(st["revert_changes"]), label="rollback")
        except Exception:
            pass
        self._autosave_applied_setup(form)
        form._btn_revert_setup.setVisible(False)
        self._refresh_revert_buttons()

    def _run_build_setup_for_form(self, form: "SetupFormWidget") -> None:
        """Retired: the from-scratch AI build path was removed in the
        determinism rebuild (Sprint 1). Use "Build Baseline Setup" for a
        deterministic from-scratch setup, or "Analyse" for rule-validated
        changes. Retained as a no-op so existing wiring stays valid."""
        return

    # ------------------------------------------------------------------
    # Group 44: Rule-first baseline setup generator
    # ------------------------------------------------------------------

    def _generate_baseline_setup(self) -> None:
        """Handler for the Race form 'Build Baseline Setup' button.

        Calls build_baseline_setup_response on the DrivingAdvisor (no API key,
        no telemetry required), then enqueues the result onto
        self._baseline_result_queue for display via _display_baseline_result.
        Pattern mirrors _setup_analyse_ai.
        """
        import threading as _threading
        from strategy.setup_ranges import resolve_ranges as _resolve_ranges

        _ai_snap = self._build_setup_inputs()
        car   = _ai_snap.car
        track = _ai_snap.track
        if not car or not track:
            self._build_setup_result.setPlainText(
                "Select a car and track first — baseline setup needs a car and track context.")
            self._build_setup_result.setVisible(True)
            return

        _allowed  = _ai_snap.allowed_tuning_or_none()
        _locked   = _ai_snap.tuning_locked

        if _locked:
            self._build_setup_result.setPlainText(
                "All tuning categories are locked for this Event — baseline unavailable.")
            self._build_setup_result.setVisible(True)
            return

        _ranges      = _resolve_ranges(car)
        _drivetrain  = (
            self._setup_drivetrain.currentData()
            if hasattr(self, "_setup_drivetrain")
            else ""
        ) or ""
        _num_gears   = (
            self._setup_num_gears.value()
            if hasattr(self, "_setup_num_gears")
            else 0
        )
        # Group 45: real session purpose from the Race form (never a hardcoded string).
        _session_type = self._active_form().purpose if hasattr(self, "_active_form") else "Race"
        # Group 45: tyre_wear_multiplier from the event snapshot — pass None when no
        # real event is active (EMPTY source) so the backend treats context as unknown.
        from data.analysis_inputs import AnalysisInputsSource as _SnapSrc
        _tyre_wear = (
            _ai_snap.tyre_wear_multiplier
            if _ai_snap.core.source != _SnapSrc.EMPTY
            else None
        )
        # Group 45: car_class from car_specs.category (empty string when no specs loaded).
        _, _car_specs_bl = self._load_car_specs_for_current()
        _car_class = (_car_specs_bl or {}).get("category", "")

        self._btn_baseline.setEnabled(False)
        self._btn_baseline.setText("Building baseline…")
        self._build_setup_result.setPlainText(
            "Building baseline setup from car ranges and driving profile…")
        self._build_setup_result.setVisible(True)

        # Group 46: pass real race duration so build_baseline_setup_response can
        # classify session bias (race + duration>=60 → endurance bias).
        # _ai_snap.duration_mins is 0 when no event is configured — backend treats
        # 0 / <=0 as sprint/conservative (by design — safe default).
        _duration_mins_bl = float(_ai_snap.duration_mins)
        _track_profile_bl = self._build_track_tune_profile_for_current()
        # Phase 9 baseline lift: proven successful setups so the from-scratch base
        # can seed personal-fit geometry (camber/toe) from validated history.
        _hist_setups_bl = self._successful_historical_setups(car, track)

        def _worker():
            try:
                json_str = self._driving_advisor.build_baseline_setup_response(
                    car_name=car,
                    ranges=_ranges,
                    drivetrain=_drivetrain,
                    num_gears=_num_gears,
                    allowed_tuning=_allowed,
                    tuning_locked=_locked,
                    session_type=_session_type,
                    tyre_wear_multiplier=_tyre_wear,
                    car_class=_car_class,
                    duration_mins=_duration_mins_bl,
                    track_profile=_track_profile_bl,
                    track_name=track,
                    historical_setups=_hist_setups_bl,
                )
                self._baseline_result_queue.put(("ok", json_str, "baseline_setup", None))
            except Exception as exc:
                self._baseline_result_queue.put(("error", str(exc), "baseline_setup", None))

        _threading.Thread(target=_worker, daemon=True).start()

    def _successful_historical_setups(self, car_name: str = "", track: str = "") -> list:
        """Phase 9: saved setups annotated with the driver's rating (from feedback),
        so the historical prior can use only PROVEN (liked) setups. Best-effort —
        returns [] on any failure; never raises into the analyse path."""
        setups = list(getattr(self, "_saved_setups", []) or [])
        if not setups:
            return []
        ratings: dict = {}
        try:
            car_id = int(getattr(self, "_car_id_build", 0) or 0)
            if self._db is not None and car_id and track:
                for fb in (self._db.get_recent_feedback(car_id, track, limit=100) or []):
                    _sid, _rt = fb.get("setup_id"), fb.get("rating")
                    if _sid and _rt:
                        ratings.setdefault(_sid, _rt)
        except Exception:
            ratings = {}
        out = []
        for s in setups:
            s2 = dict(s)
            if not s2.get("rating") and s2.get("setup_id") in ratings:
                s2["rating"] = ratings[s2["setup_id"]]
            out.append(s2)
        return out

    def _build_candidate_columns(self, car_name, drivetrain, allowed, locked,
                                 track_profile) -> list:
        """Assemble candidate columns for the comparison table: the driver's own
        Race and Quali setups plus a from-scratch base. Qt widgets are read on the
        calling (main) thread. Best-effort — returns [] on any failure and never
        raises into the analyse path. Fabricates nothing: a form with no values or a
        failed base generation simply contributes no column."""
        cols: list = []
        try:
            _rf = getattr(self, "_race_form", None)
            if _rf is not None:
                _rv = _rf.current_setup_dict() or {}
                if _rv:
                    cols.append({"name": "race", "label": "Race setup",
                                 "source": "your Race form", "values": _rv})
            _qf = getattr(self, "_qual_form", None)
            if _qf is not None:
                _qv = _qf.current_setup_dict() or {}
                if _qv:
                    cols.append({"name": "quali", "label": "Quali setup",
                                 "source": "your Qualifying form", "values": _qv})
            # From-scratch base — pure generator (no AI, no Qt); num_gears read here.
            try:
                from strategy.setup_baseline import build_baseline_setup as _bbs
                from strategy.setup_driver_profile import build_driver_profile as _bdp
                from strategy.setup_ranges import resolve_ranges as _rr
                _ng = int(self._setup_num_gears.value()) if hasattr(self, "_setup_num_gears") else 0
                _base = _bbs(car_name, _rr(car_name), drivetrain or "", _ng,
                             _bdp(), allowed, locked, track_profile=track_profile)
                _bf = _base.get("setup_fields") or {}
                if _bf:
                    cols.append({"name": "base", "label": "Base (from scratch)",
                                 "source": "neutral generator", "values": _bf})
            except Exception:
                pass
        except Exception:
            return cols
        return cols

    def _build_track_tune_profile_for_current(self):
        """Phase 5: build a TrackTuneProfile from the current track/layout's seed +
        accepted model, so the baseline is track-shaped. Returns None on any
        failure (the baseline then stays track-neutral and discloses it)."""
        try:
            # Canonical identity via EventContext (not a raw config["strategy"] read).
            ec = self._build_event_context() if hasattr(self, "_build_event_context") else None
            loc = str(getattr(ec, "track_location_id", "") or "").strip()
            lay = str(getattr(ec, "layout_id", "") or "").strip()
            if not loc or not lay:
                return None
            from data.track_intelligence import resolve_track_layout
            from data.track_model_alignment import (
                import_accepted_model_json, find_accepted_model_path,
            )
            from strategy.track_tune_profile import build_track_tune_profile
            seed_layout = resolve_track_layout(loc, lay)
            accepted = None
            _p = find_accepted_model_path(loc, lay)
            if _p is not None:
                accepted = import_accepted_model_json(_p)
            return build_track_tune_profile(loc, lay, seed_layout=seed_layout,
                                            accepted_model=accepted)
        except Exception:
            return None

    def _generate_baseline_setup_both(self) -> None:
        """Build baseline setups for BOTH the Race and Qualifying forms at once.

        UAT: the initial base build should produce a race and a qualifying setup
        together. Fires the existing per-form baseline builders; each runs in its
        own worker thread and routes its result to the correct form via
        _display_baseline_result. The Qualifying form's own button still builds
        just the qualifying baseline when needed.
        """
        self._generate_baseline_setup()
        if getattr(self, "_qual_form", None) is not None:
            self._generate_baseline_setup_for_form(self._qual_form)

    def _generate_baseline_setup_for_form(self, form: "SetupFormWidget") -> None:
        """Handler for the Qualifying form 'Build Baseline Setup' button.

        Mirror of _generate_baseline_setup, targeting the given form's widgets
        and enqueuing a form-tagged result for per-form display routing.
        """
        import threading as _threading
        from strategy.setup_ranges import resolve_ranges as _resolve_ranges

        _ai_snap = self._build_setup_inputs()
        car   = _ai_snap.car
        track = _ai_snap.track
        if not car or not track:
            form._build_setup_result.setPlainText(
                "Select a car and track first — baseline setup needs a car and track context.")
            form._build_setup_result.setVisible(True)
            return

        _allowed  = _ai_snap.allowed_tuning_or_none()
        _locked   = _ai_snap.tuning_locked

        if _locked:
            form._build_setup_result.setPlainText(
                "All tuning categories are locked for this Event — baseline unavailable.")
            form._build_setup_result.setVisible(True)
            return

        _ranges      = _resolve_ranges(car)
        _drivetrain  = (
            form._setup_drivetrain.currentData()
            if hasattr(form, "_setup_drivetrain")
            else ""
        ) or ""
        _num_gears   = (
            form._setup_num_gears.value()
            if hasattr(form, "_setup_num_gears")
            else 0
        )
        # Group 45: pass form's raw purpose (e.g. "Qualifying") — backend calls
        # normalise_purpose which accepts both "Qualifying" and "Qualifying Setup".
        _session_type = f"{form.purpose} Setup"
        # Group 45: tyre_wear_multiplier from the event snapshot — pass None when no
        # real event is active (EMPTY source) so the backend treats context as unknown.
        from data.analysis_inputs import AnalysisInputsSource as _SnapSrc
        _tyre_wear = (
            _ai_snap.tyre_wear_multiplier
            if _ai_snap.core.source != _SnapSrc.EMPTY
            else None
        )
        # Group 45: car_class from car_specs.category (empty string when no specs loaded).
        _, _car_specs_bl = self._load_car_specs_for_current()
        _car_class = (_car_specs_bl or {}).get("category", "")
        # UAT: the Qualifying form's gear-count spinbox is NOT populated by the
        # Race-form car-specs autofill (it writes only self._setup_num_gears, the
        # Race alias), so a qualifying baseline built no gear ratios. Fall back to
        # the car spec's gear count, then the Race form, so gears are authored.
        if not _num_gears:
            _num_gears = int((_car_specs_bl or {}).get("num_gears", 0) or 0)
        if not _num_gears and hasattr(self, "_setup_num_gears"):
            _num_gears = int(self._setup_num_gears.value() or 0)
        # Group 46: pass real race duration so build_baseline_setup_response can
        # classify session bias (race + duration>=60 → endurance bias).
        # _ai_snap.duration_mins is 0 when no event is configured — backend treats
        # 0 / <=0 as sprint/conservative (by design — safe default).
        _duration_mins_bl = float(_ai_snap.duration_mins)

        form._btn_baseline.setEnabled(False)
        form._btn_baseline.setText("Building baseline…")
        form._build_setup_result.setPlainText(
            "Building baseline setup from car ranges and driving profile…")
        form._build_setup_result.setVisible(True)
        _track_profile_bl = self._build_track_tune_profile_for_current()
        # Phase 9 baseline lift: proven successful setups to seed personal-fit
        # geometry (camber/toe) from validated history.
        _hist_setups_bl = self._successful_historical_setups(car, track)

        def _worker():
            try:
                json_str = self._driving_advisor.build_baseline_setup_response(
                    car_name=car,
                    ranges=_ranges,
                    drivetrain=_drivetrain,
                    num_gears=_num_gears,
                    allowed_tuning=_allowed,
                    tuning_locked=_locked,
                    session_type=_session_type,
                    tyre_wear_multiplier=_tyre_wear,
                    car_class=_car_class,
                    duration_mins=_duration_mins_bl,
                    track_profile=_track_profile_bl,
                    track_name=track,
                    historical_setups=_hist_setups_bl,
                )
                self._baseline_result_queue.put(("ok", json_str, "baseline_setup", None, form))
            except Exception as exc:
                self._baseline_result_queue.put(("error", str(exc), "baseline_setup", None, form))

        _threading.Thread(target=_worker, daemon=True).start()

    def _display_baseline_result(self, result: tuple) -> None:
        """Re-enable the baseline button then delegate rendering to _display_setup_result.

        The result tuple from the queue has the same shape expected by
        _display_setup_result: (status, payload, entry_type, feeling[, form]).
        Both the Race-form button (aliased to self._btn_baseline) and the
        per-form button (result[4]) are re-enabled here before delegation so
        the correct button is restored regardless of which form fired.
        """
        # Re-enable the race-form baseline button (aliased on self)
        if hasattr(self, "_btn_baseline"):
            self._btn_baseline.setEnabled(True)
            self._btn_baseline.setText("Build Baseline (Race + Quali)")

        # Re-enable the per-form button if a form is in the tuple (position 4)
        _form = result[4] if len(result) > 4 else None
        if _form is not None and hasattr(_form, "_btn_baseline"):
            _form._btn_baseline.setEnabled(True)
            _form._btn_baseline.setText("Build Baseline Setup")

        # Route result through the shared renderer (handles Apply gate, HTML, history)
        self._display_setup_result(result)

    def _build_setup_context(self, recommendation: dict | None = None,
                             diagnosis: dict | None = None):
        """Canonical read model of the active setup recommendation.

        State Consolidation 3: separates setup-recommendation state (purpose,
        source, adjustments, baseline/target setup, confidence, validation) from
        the event truth (EventContext) and strategy truth (StrategyContext /
        StrategyPromptSnapshot) it was built against, keying the setup to
        ``EventContext.change_hash`` and ``StrategyPromptSnapshot.snapshot_id``
        so stale setups are detectable (see ``data/setup_context.py``). Reads the
        baseline from ``_current_setup_dict()`` and event/strategy keys from the
        other context helpers. Never raises — returns an EMPTY-source context on
        failure. Legacy config/DB setup storage is unchanged.
        """
        try:
            from data.setup_context import build_setup_context
            ev = self._build_event_context() if hasattr(self, "_build_event_context") else None
            strat_snap = None
            try:
                from data.strategy_context import (
                    build_strategy_context, build_strategy_prompt_snapshot,
                )
                sc = build_strategy_context(
                    strategy=self._config.get("strategy", {}), event_context=ev)
                strat_snap = build_strategy_prompt_snapshot(sc, ev)
            except Exception:  # pragma: no cover - defensive
                strat_snap = None
            return build_setup_context(
                setup=self._current_setup_dict(),
                recommendation=recommendation,
                event_context=ev,
                strategy_snapshot=strat_snap,
                diagnosis=diagnosis,
            )
        except Exception:  # pragma: no cover - defensive; must never break the UI
            from data.setup_context import empty_setup_context
            return empty_setup_context()

    def _build_setup_inputs(self):
        """Frozen AI-input snapshot for the setup AI paths.

        AI Snapshot Migration: freezes the event/track fields the Build-Setup
        and Analyse-Setup calls need (owners: EventContext race rules,
        StrategyContext pit loss, TrackContext identity, SetupContext via the
        last captured setup context) instead of live config["strategy"] reads.
        Byte-identical to the legacy expressions when the stores are in sync
        (proven by tests/test_analysis_inputs.py). Never raises; falls back
        to exact legacy expressions when no event context exists.
        OFR-2: session_type is passed so SetupInputs.discipline is real.
        """
        # OFR-2: read session_type defensively — combo may not exist yet.
        _stype = self._setup_type.currentText() if hasattr(self, "_setup_type") else None
        try:
            from data.analysis_inputs import build_setup_inputs
            ev = self._build_event_context() if hasattr(self, "_build_event_context") else None
            sc = self._build_strategy_context() if hasattr(self, "_build_strategy_context") else None
            tc = self._build_track_context() if hasattr(self, "_build_track_context") else None
            setup_snap = None
            try:
                last = getattr(self, "_last_setup_context", None)
                if last is not None:
                    from data.setup_context import build_setup_prompt_snapshot
                    setup_snap = build_setup_prompt_snapshot(last)
            except Exception:
                setup_snap = None
            return build_setup_inputs(
                event_context=ev, strategy_context=sc,
                setup_snapshot=setup_snap, track_context=tc,
                legacy_strategy=self._config.get("strategy", {}),
                session_type=_stype)
        except Exception:  # pragma: no cover - defensive; must never break AI calls
            from data.analysis_inputs import build_setup_inputs
            _legacy = self._config.get("strategy", {}) if hasattr(self, "_config") else None
            return build_setup_inputs(legacy_strategy=_legacy, session_type=_stype)

    def _setup_type_prefix(self) -> str:
        """'Q' for a qualifying setup, 'R' for a race setup.

        State Consolidation 3: setup purpose classification is owned by
        SetupContext — derive it via the canonical ``normalise_purpose`` rather
        than an ad-hoc substring test (behaviour-preserving: "qual" → Q, else R).

        After the side-by-side refactor: reads self._setup_type.currentText() so
        that the tab-level "Live Session Mode" combo (and test stubs that set it)
        still drive the prefix.  When the Race form is active (mixin default),
        this returns "R"; when a stub sets it to "Qualifying Setup" the tests
        still get "Q" as expected.
        """
        from data.setup_context import normalise_purpose, SetupPurpose
        purpose = normalise_purpose(self._setup_type.currentText())
        return "Q" if purpose == SetupPurpose.QUALIFYING else "R"

    def _generate_setup_name(self, prefix: str | None = None) -> str | None:
        """Build '<Q|R> <event name> <number>' for the active event, or None if no event.

        ``prefix`` defaults to ``_setup_type_prefix()`` (reads the tab-level combo,
        so test stubs that set ``self._setup_type`` keep working).  Callers that
        want the prefix fixed to a specific form purpose pass it explicitly.
        """
        from ui.setup_name_helper import build_setup_name, next_setup_number
        event_name = ""
        if hasattr(self, "_active_event"):
            event_name = (self._active_event() or {}).get("name", "") or ""
        if not event_name:
            return None
        _prefix = prefix if prefix is not None else self._setup_type_prefix()
        n = next_setup_number(self._saved_setups, _prefix, event_name)
        return build_setup_name(_prefix, event_name, n)

    def _prefill_setup_label(self) -> None:
        """Pre-fill the editable setup-label field with the auto-generated name.

        Fires when the active event changes.  Uses the Race form's purpose prefix
        ("R") so the Race panel label matches correctly regardless of the Live
        Session Mode combo state.  No-op when there is no active event.
        """
        _prefix = (
            self._race_form.purpose_prefix()
            if hasattr(self, "_race_form")
            else self._setup_type_prefix()
        )
        name = self._generate_setup_name(prefix=_prefix)
        if name:
            self._setup_label.setText(name)
        # Also prefill the Qualifying form label
        if hasattr(self, "_qual_form"):
            _q_prefix = self._qual_form.purpose_prefix()
            _q_name = self._generate_setup_name(prefix=_q_prefix)
            if _q_name:
                self._qual_form._setup_label.setText(_q_name)

    def _setup_save(self) -> None:
        # Require an active event so setups are always named/grouped by event.
        _evt_name = ""
        if hasattr(self, "_active_event"):
            _evt_name = (self._active_event() or {}).get("name", "") or ""
        if not _evt_name:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "No Active Event",
                "Please select an active event in the Event Planner before saving a setup.",
            )
            return
        # D-RESAVE: resolve the final label before persisting. A structured auto-name
        # (or empty field) advances to the next numbered attempt for this event, so
        # saving a loaded/previously-saved structured setup creates a NEW number
        # instead of overwriting. Manual/freeform names are kept exactly as typed.
        from ui.setup_name_helper import resolve_save_name
        # Side-by-side refactor: the Race form's mixin save path always uses "R"
        # prefix.  _setup_type_prefix() now reads from the Live Session Mode
        # toggle (tab-level combo) which is independent of the form purpose.
        # Use the Race form's purpose_prefix() directly so the label is correct.
        _save_prefix = (
            self._race_form.purpose_prefix()
            if hasattr(self, "_race_form")
            else self._setup_type_prefix()
        )
        self._setup_label.setText(
            resolve_save_name(
                self._setup_label.text(),
                _save_prefix,
                _evt_name,
                self._saved_setups,
            )
        )
        # Clear any field highlights from AI apply — user has chosen to persist.
        self._clear_setup_highlights()
        # Persist race engineer brief to active event before saving setup
        self._save_re_brief_to_active_event()
        d = self._current_setup_dict()
        ca = self._config.setdefault("car_setup", {})
        existing = next(
            (i for i, s in enumerate(self._saved_setups)
             if s.get("name") == d["name"] and s.get("setup_label") == d["setup_label"]),
            None,
        )
        if existing is not None:
            d["setup_id"] = self._saved_setups[existing].get("setup_id") or d.get("setup_id")
            self._saved_setups[existing] = d
            target_idx = existing
        else:
            if not d.get("setup_id"):
                next_id = ca.get("next_setup_id", 1)
                d["setup_id"] = next_id
                ca["next_setup_id"] = next_id + 1
            self._saved_setups.append(d)
            target_idx = len(self._saved_setups) - 1

        # Write to DB (authoritative store for setups)
        if self._db is not None:
            _meta_keys = {"name", "setup_label", "setup_id", "captured_at", "ai_notes"}
            _car_name = d.get("name", "")
            _car_id = self._db.get_car_id(_car_name) if _car_name else 0
            # Phase 5: event id from the canonical EventContext (DB-first;
            # byte-identical in sync — the fan-out stored the same DB id).
            _event_id = int(self._build_event_context().event_id or 0)
            _label = d.get("setup_label", "Setup")
            _fields = {k: v for k, v in d.items() if k not in _meta_keys}
            _existing_db_id = d.get("setup_id") if existing is not None else 0
            if _existing_db_id:
                self._db.update_setup(_existing_db_id, _label, _fields)
            else:
                _new_id = self._db.save_setup(_car_id, _event_id, _label, _fields)
                d["setup_id"] = _new_id
                self._saved_setups[target_idx]["setup_id"] = _new_id

        # Keep config in sync during transition period
        ca["setups"] = self._saved_setups
        self._persist_config()
        self._refresh_setup_combo(select_index=target_idx)
        self._refresh_all_setup_combos()
        self._bridge.event_log_entry.emit(f"[Setup] saved: {d['name']} (ID {d.get('setup_id', '?')})")
        if hasattr(self, "_lbl_setup_save_status"):
            lbl = d.get("setup_label", "") or "Setup"
            self._lbl_setup_save_status.setText(f"Saved: {lbl}  (ID {d.get('setup_id', '?')})")
            from PyQt6.QtCore import QTimer as _QTimer
            _QTimer.singleShot(4000, lambda: (
                self._lbl_setup_save_status.setText("") if hasattr(self, "_lbl_setup_save_status") else None
            ))
        # Sprint 10: saving may create pending (not-yet-applied-in-GT7) changes.
        if hasattr(self, "_race_form"):
            self._refresh_apply_status_for_form(self._race_form)

    def _after_setup_load(self) -> None:
        """Refresh the Home Setup card after a setup is loaded into a form.

        Loading only filled the form widgets; unlike Save and AI-apply it never
        rebuilt the canonical SetupContext (`_last_setup_context`) or refreshed
        Home, so the Home 'Setup Brain' card stayed stale after a load.
        """
        try:
            self._last_setup_context = self._build_setup_context()
        except Exception:
            pass
        # Sprint 10: a load may change which setup differs from the GT7 checkpoint.
        for _f in (getattr(self, "_race_form", None), getattr(self, "_qual_form", None)):
            if _f is not None:
                self._refresh_apply_status_for_form(_f)
        if hasattr(self, "_home_refresh_if_visible"):
            self._home_refresh_if_visible()

    def _setup_load_selected(self) -> None:
        idx = self._setup_load_combo.currentIndex()
        # index 0 is the placeholder; real setups start at index 1
        real_idx = idx - 1
        if 0 <= real_idx < len(self._saved_setups):
            self._fill_setup_fields(self._saved_setups[real_idx])
            self._after_setup_load()

    def _setup_analyse_ai(self) -> None:
        if self._driving_advisor is None:
            self._setup_result_text.setPlainText(
                "Driving advisor not available.")
            return
        d = self._current_setup_dict()
        _car_name, _car_specs = self._load_car_specs_for_current()
        # Record the analysed car id so a later Apply can link the recommendation
        # to the live session for the learning loop (apply_recommendation_for_car_track).
        # The legacy build-with-AI path set this too, but it is disabled — the live
        # Analyse→Apply flow is now the only path, so set it here.
        _db_for_car = getattr(self, "_db", None)
        self._car_id_build = (
            _db_for_car.get_car_id(_car_name)
            if _db_for_car and _car_name and _car_name != "Unknown"
            else 0
        )

        # Count laps tagged with this setup in the lap table so the AI
        # sees all relevant laps (not just the last 5).
        setup_id = d.get("setup_id")
        n_laps = 5  # fallback if no setup ID or no tagged laps
        if setup_id:
            count = sum(
                1 for r in range(self._lap_table.rowCount())
                if (w := self._lap_table.cellWidget(r, 14)) is not None
                and w.currentText().startswith(f"{setup_id} —")
            )
            if count > 0:
                n_laps = count

        feeling = self._setup_feeling_input.toPlainText().strip()
        self._setup_result_text.setPlainText("Analysing setup… please wait.")
        if hasattr(self, "_btn_analyse_setup"):
            self._btn_analyse_setup.setEnabled(False)
        import threading as _threading

        # AI Snapshot Migration: event tuning-legality + mandatory compounds
        # come from a frozen snapshot (owner: EventContext) instead of live
        # config["strategy"] reads. Byte-identical when the stores are in sync
        # (tests/test_analysis_inputs.py).
        _ai_snap = self._build_setup_inputs()
        _allowed  = _ai_snap.allowed_tuning_or_none()
        _locked   = _ai_snap.tuning_locked
        _compound = _ai_snap.mandatory_compounds_str
        # Group 45: thread session-context params so the Race form's Analyse
        # button is context-aware, matching _setup_analyse_ai_for_form exactly.
        # purpose: race form always carries purpose="Race" (set at construction).
        _purpose = self._race_form.purpose
        # car_class: specs category, or "" when no specs loaded (backend neutral fallback).
        _car_class = (_car_specs or {}).get("category", "")
        # drivetrain: explicit combo selection wins; "" = Auto-detect (backend uses
        # CAR_DRIVETRAIN_OVERRIDES by car name, e.g. Porsche).
        _drivetrain = (
            self._race_form._setup_drivetrain.currentData()
            if hasattr(self._race_form, "_setup_drivetrain")
            else ""
        ) or ""
        # Phase 9: proven successful setups for the historical prior/comparison.
        _track_bl = str(getattr(_ai_snap, "track", "") or "")
        _hist_setups = self._successful_historical_setups(_car_name, _track_bl)
        # Phase 8: race-time fuel/aero context (event fuel multiplier + refuel rate,
        # Phase-5 track profile) so a fuel-heavy drag-sensitive circuit gets an aero
        # comparison-run recommendation instead of a blanket "fuel isn't setup".
        _fuel_mult_bl, _refuel_rate_bl = 1.0, 0.0
        try:
            _ec_bl = self._build_event_context() if hasattr(self, "_build_event_context") else None
            _fuel_mult_bl = float(getattr(_ec_bl, "fuel_multiplier", 1.0) or 1.0)
            _refuel_rate_bl = float(getattr(_ec_bl, "refuel_rate_lps", 0.0) or 0.0)
        except Exception:
            _fuel_mult_bl, _refuel_rate_bl = 1.0, 0.0
        _track_profile_an = self._build_track_tune_profile_for_current()
        # Candidate columns for the comparison table — the driver's own Race and
        # Quali setups plus a from-scratch base, so the recommended values sit in
        # context. Qt widgets are read HERE on the main thread (never in the worker).
        _extra_candidates = self._build_candidate_columns(
            _car_name, _drivetrain, _allowed, _locked, _track_profile_an)

        def _worker():
            try:
                resp = self._driving_advisor.build_combined_setup_response(
                    d, n_laps=n_laps, car_name=_car_name, car_specs=_car_specs,
                    feeling=feeling or None,
                    allowed_tuning=_allowed, tuning_locked=_locked,
                    compound=_compound,
                    purpose=_purpose,
                    car_class=_car_class,
                    drivetrain=_drivetrain,
                    historical_setups=_hist_setups,
                    track_name=_track_bl,
                    fuel_multiplier=_fuel_mult_bl,
                    refuel_rate_lps=_refuel_rate_bl,
                    track_profile=_track_profile_an,
                    extra_candidates=_extra_candidates,
                    live_corner_aggregates=self._live_corner_aggregates())
                self._setup_result_queue.put(("ok", resp, "analyse_setup", feeling or None))
            except Exception as exc:
                self._setup_result_queue.put(("error", str(exc), "analyse_setup", None))

        # Persist the live per-corner slip evidence (UI thread) so the advisor's
        # cross-session read includes this run before it diagnoses.
        self._persist_live_corner_slip()
        _threading.Thread(target=_worker, daemon=True).start()

    def _build_setup_advice_cards(
        self, data: dict, *, approved_changes, rejected_changes,
        protected_fields, validation_failed: bool, status_approved: bool,
    ) -> list:
        """Turn the deterministic analysis payload into a :class:`SetupDecision`
        and render it to structured advice cards (Sprint 10).

        The decision mirrors what the backend already decided — approved,
        rejected, and preserved fields — so the structured cards never
        re-arbitrate or contradict the detailed sections below them. Cross-lap
        persistence rows are threaded through when the payload carries them.
        """
        from strategy.setup_decision import (
            SetupDecision, FieldDecision, DecisionStatus)
        from ui.setup_advice_render import render_setup_decision

        def _label(ch, default="setup"):
            if isinstance(ch, dict):
                return str(ch.get("setting") or ch.get("field") or default)
            return str(ch or default)

        def _reason(ch, *keys, default=""):
            if isinstance(ch, dict):
                for k in keys:
                    if ch.get(k):
                        return str(ch.get(k))
            return default

        fds: list = []
        for ch in (approved_changes or []):
            fds.append(FieldDecision(
                _label(ch), "approved",
                _reason(ch, "why", "rationale", "symptom")))
        for ch in (rejected_changes or []):
            fds.append(FieldDecision(
                _label(ch, "field"), "rejected",
                _reason(ch, "reason", "why",
                        default="rejected by engineering validation")))
        for f in (protected_fields or []):
            fds.append(FieldDecision(str(f), "preserved", "protected — left unchanged"))

        if validation_failed:
            status = DecisionStatus.ENGINEERING_FAILURE
        elif status_approved and approved_changes:
            status = DecisionStatus.APPROVED_WITH_CHANGES
        elif status_approved:
            status = DecisionStatus.APPROVED_NO_CHANGE
        elif rejected_changes and not approved_changes:
            status = DecisionStatus.REJECTED_UNSAFE
        else:
            status = DecisionStatus.INSUFFICIENT_EVIDENCE

        _HEADLINE = {
            DecisionStatus.APPROVED_WITH_CHANGES: "Approved — apply the changes below",
            DecisionStatus.APPROVED_NO_CHANGE: "Approved — no change needed",
            DecisionStatus.REJECTED_UNSAFE: "Rejected — changes left unapplied",
            DecisionStatus.ENGINEERING_FAILURE:
                "Engineering validation failed — no changes applied",
            DecisionStatus.INSUFFICIENT_EVIDENCE:
                "Insufficient evidence — no changes applied",
        }
        # Rationale stays empty here: the full analysis renders in its own card
        # below, so the banner would only duplicate it.
        decision = SetupDecision(
            status=status, field_decisions=tuple(fds),
            validation_failed=bool(validation_failed),
            headline=_HEADLINE.get(status, status.value), rationale="")

        _persistence = getattr(self, "_last_persistence_results", ()) or ()
        return render_setup_decision(decision, persistence_results=_persistence)

    def _display_setup_result(self, result: tuple) -> None:
        if not hasattr(self, "_setup_result_text"):
            return
        status = result[0]
        payload = result[1]
        entry_type = result[2] if len(result) > 2 else "analyse_setup"
        feeling = result[3] if len(result) > 3 else None
        # Per-form routing: if a SetupFormWidget is in position 4, use its result
        # text and buttons instead of the (Race-aliased) self attrs.
        _form = result[4] if len(result) > 4 else None
        _result_text   = _form._setup_result_text   if _form else self._setup_result_text
        _btn_analyse   = _form._btn_analyse_setup   if _form else getattr(self, "_btn_analyse_setup", None)
        _btn_apply     = _form._btn_apply_ai_setup  if _form else getattr(self, "_btn_apply_ai_setup", None)

        if _btn_analyse:
            _btn_analyse.setEnabled(True)

        if status == "error":
            _result_text.setHtml(
                f"<span style='color:#F55;'>Analysis failed:</span> {payload}")
            return

        # DEF-P2-007 — validate the recommendation for event tuning compliance before display
        from strategy.setup_compliance import validate_setup_tuning_compliance as _vld_setup
        _sc_v = self._config.get("strategy", {})
        _viol_cats = _vld_setup(
            payload if isinstance(payload, str) else "",
            not bool(_sc_v.get("tuning", True)),
            _sc_v.get("allowed_tuning_categories", []) or None,
        )
        _violation_banner = ""
        if _viol_cats:
            _vc = ", ".join(_viol_cats)
            _violation_banner = (
                "<div style='background:#2A1A00; border:1px solid #F5A623; "
                "border-radius:4px; padding:8px; margin-bottom:8px; color:#F5A623;'>"
                f"&#9888; <b>Event Restriction Warning</b> — the recommendation may touch "
                f"locked areas: <b>{_vc}</b>. Review before applying.</div>"
            )

        # Rating/applied labels are no longer captured here — the rate control
        # moved to the Practice Review per-run feedback and "applied" is derived
        # from lap setup tags. History entries save without subjective labels.

        # Try to parse structured JSON from the advisor.  A truncated response
        # (the model hit the token cap mid-JSON) or a non-JSON reply must NEVER
        # dump raw text at the user — guard for completeness first, then show a
        # clear, actionable message instead of leaking JSON.
        try:
            if not _setup_response_looks_complete(payload):
                raise _json.JSONDecodeError(
                    "response appears truncated or non-JSON", (payload or "").strip() or " ", 0)
            data = json.loads(payload)
            analysis = str(data.get("analysis", ""))
            # approved_changes and approved_fields are already gated by _finalise_recommendation:
            # data["changes"] = approved_changes, data["setup_fields"] = approved_fields.
            approved_changes: list = data.get("changes", [])
            approved_fields: dict = data.get("setup_fields", {})
            rejected_changes: list = data.get("rejected_changes", [])
            _validation_errors: list = data.get("validation_errors", [])
            _validation_warnings: list = data.get("validation_warnings", []) or []
            _eng_validation_errors: list = data.get("engineering_validation_errors", [])
            _rec_status: str = data.get("recommendation_status", "")
            _diagnosis: dict = data.get("diagnosis") or {}
        except (_json.JSONDecodeError, AttributeError):
            # Friendly fallback — never surface raw JSON to the user.
            _err_html = (
                "<div style='background:#2A1A1A; border:1px solid #C0453B; "
                "border-radius:4px; padding:10px; color:#E8A9A3;'>"
                "<b style='color:#E86A5E;'>Couldn't read the setup analysis</b><br>"
                "The AI response looks incomplete — it was likely cut off. "
                "Click <b>Analyse &amp; Get Setup Fix</b> again to retry. "
                "If it keeps happening, shorten the driver-feeling text and try once more."
                "</div>"
            )
            _result_text.setHtml(_violation_banner + _err_html)
            if _btn_apply:
                _btn_apply.setVisible(False)
            return

        # Group 42: extract new optional keys (defensive — absent on legacy/fallback responses).
        _protected_fields: list = data.get("protected_fields") or []
        _ai_audit: dict | None = data.get("ai_audit") or None
        # deterministic_plan is informational only — not rendered in this sprint.

        # Determine whether this recommendation is approved for display/apply.
        # AC17: absent/empty/None/unrecognised recommendation_status MUST resolve to
        # legacy_unknown = display-only.  is_legacy_unknown already handles all of
        # these cases (empty string and None both return True at the first guard).
        # Call it unconditionally — no falsy short-circuit.
        from strategy._setup_constants import APPROVED_STATUSES as _APPROVED_STATUSES
        from data.setup_history import is_legacy_unknown as _is_legacy_unknown, LEGACY_UNKNOWN as _LEGACY_UNKNOWN
        _is_legacy: bool = _is_legacy_unknown(_rec_status)  # True for "", None, unrecognised
        _status_approved: bool = (not _is_legacy) and (_rec_status in _APPROVED_STATUSES)

        # Engineering-Brain Phase 2: persist a controlled setup EXPERIMENT for a
        # valid actionable Analyse recommendation (source-of-truth `data` dict, not
        # rendered HTML). Idempotent — re-rendering/reopening never duplicates it.
        # Baseline Build (entry_type == "baseline_setup") is deliberately EXCLUDED:
        # a from-scratch full-field baseline is a setup ARTEFACT, not a reversible
        # test of a hypothesis against a parent setup. Best-effort; never blocks UI.
        self._last_experiment_id = getattr(self, "_last_experiment_id", None)
        _exp_db = getattr(self, "_db", None)
        if _status_approved and entry_type == "analyse_setup" and _exp_db is not None:
            try:
                _exp_form = _form or getattr(self, "_race_form", None)
                if _exp_form is not None:
                    _cid, _trk, _lay, _purpose, _psid = \
                        self._apply_checkpoint_scope(_exp_form)
                    self._last_experiment_id = _exp_db.record_recommendation_experiment(
                        data, recommendation_source="analyse", car_id=_cid,
                        track=_trk, layout_id=_lay, discipline=_purpose,
                        parent_setup_id=_psid,
                        label=f"{_purpose} setup experiment")
            except Exception:
                self._last_experiment_id = None

        # Build status banner (replaces old eng_banner + validation_banner logic).
        # For known non-approved statuses (validation_failed, blocked_no_safe_recommendation,
        # etc.) _rec_status is truthy and non-empty — render the status banner normally.
        # For legacy/absent status _is_legacy is True — skip the status banner and fall
        # through to legacy-banner rendering in the HTML block below.
        if _rec_status and not _is_legacy:
            _status_banner = _format_status_banner(_rec_status, _validation_warnings)
            _eng_banner = ""
            _validation_banner = ""
        elif _rec_status and _is_legacy:
            # Present but unrecognised status: render the status banner so the user
            # sees the raw status string, then the legacy banner explains it cannot apply.
            _status_banner = _format_status_banner(_rec_status, _validation_warnings)
            _eng_banner = ""
            _validation_banner = ""
        else:
            # Absent/empty status (old-format JSON from before the validation gate).
            # AC17: display-only — no status banner, show legacy-specific banners instead.
            _status_banner = ""
            _eng_validation_failed: bool = bool(data.get("engineering_validation_failed", False))
            _eng_banner = (
                _format_engineering_validation_banner(_eng_validation_errors)
                if _eng_validation_failed else ""
            )
            _validation_banner = _format_validation_errors_banner(_validation_errors)

        # Build a compact diagnosis summary when the backend diagnosis is present.
        _diagnosis_html = ""
        if _diagnosis:
            _dom   = _diagnosis.get("dominant_problem") or "—"
            # Group 64: render the ONE canonical bottoming state (consequence-graded),
            # never the raw count band — so the header can no longer contradict the
            # bottoming-impact panel ("required" vs "normal / expected").
            _bds   = _diagnosis.get("bottoming_display_state") or {}
            _btm   = (_bds.get("state") if isinstance(_bds, dict) and _bds.get("state")
                      else (_diagnosis.get("bottoming_band") or "—"))
            _ws    = _diagnosis.get("wheelspin_band") or "—"
            _gbx   = _diagnosis.get("gearbox_flag") or "none"
            _conf  = _diagnosis.get("location_confidence") or "—"
            _diagnosis_html = (
                "<div style='background:#1A2A1A; border:1px solid #3A5A3A; "
                "border-radius:4px; padding:6px 10px; margin-bottom:6px; "
                "color:#88BB88; font-size:11px;'>"
                "<b style='color:#8BC34A;'>App diagnosis:</b>&nbsp;"
                f"<b>{_dom}</b>"
                f" &nbsp;|&nbsp; bottoming: {_btm}"
                f" &nbsp;|&nbsp; wheelspin: {_ws}"
                f" &nbsp;|&nbsp; gearbox: {_gbx}"
                f" &nbsp;|&nbsp; track-model confidence: {_conf}"
                "</div>"
            )

        # Store APPROVED fields only so the apply button can use them.
        # _parsed_ai_fields comes from approved_fields (already gated by backend).
        # Route to the per-form storage when a form widget is in the result tuple.
        _parsed_ai_fields = {
            k: v for k, v in approved_fields.items()
            if isinstance(v, (int, float))
        }
        # Apply button: VISIBLE only when status is in APPROVED_STATUSES and NOT legacy.
        # AC17: _is_legacy is True for absent/empty/unrecognised statuses — those NEVER show Apply.
        # _status_approved already incorporates _is_legacy (see above), so `and not _is_legacy`
        # is a belt-and-suspenders guard that makes the constraint visible at the call site.
        _show_apply = _status_approved and bool(_parsed_ai_fields) and not _is_legacy
        if _form is not None:
            _form.last_ai_fields = _parsed_ai_fields if _show_apply else {}
        else:
            self._last_setup_ai_fields = _parsed_ai_fields if _show_apply else {}
        if _btn_apply:
            _btn_apply.setVisible(_show_apply)

        # State Consolidation 3: capture the canonical SetupContext for this
        # displayed recommendation, keyed to EventContext.change_hash and the
        # StrategyPromptSnapshot.snapshot_id it was built against, so a later
        # sprint can detect a stale setup. Read-only and additive — it does not
        # alter the displayed HTML, the history save, or the apply button.
        try:
            self._last_setup_context = self._build_setup_context(
                recommendation={
                    "analysis": analysis,
                    "changes": approved_changes,
                    "setup_fields": approved_fields,
                    "validation_errors": _validation_errors,
                    "primary_issue": data.get("primary_issue", ""),
                    "confidence": data.get("confidence", ""),
                },
                diagnosis=_diagnosis,
            )
        except Exception:  # pragma: no cover - defensive; never break the display
            self._last_setup_context = None

        # Build HTML — Group 42 section hierarchy (AC22):
        #   0. Status banner + legacy banners + event-restriction banner
        #   1. Pit Crew diagnosis block
        #   2. Analysis card
        #   3. Pit Crew recommendation (approved changes only, with per-change explainability)
        #   4. Protected fields (collapsed)
        #   5. Rejected candidate changes (collapsed, rule-engine rejects — distinct from Rejected AI output)
        #   6. AI audit result (only when present)
        #   7. Engineering gate failures (for rejected statuses)
        #   8. Rejected AI text (existing collapsed block, validation_failed / retry_failed statuses)
        card = "background:#1C2A3A; border-radius:6px; padding:10px; margin-bottom:8px;"
        chg_hdr = "background:#2A3A1C; border-left:4px solid #8BC34A; border-radius:4px; " \
                  "padding:8px 12px; margin-bottom:4px;"
        chg_row = "padding:4px 0 4px 8px; border-bottom:1px solid #2A3A1C;"

        # Legacy-unknown banner — rendered when a response's status is absent, None, or
        # unrecognised. All such cases resolve to _is_legacy=True and _status_approved=False
        # (via is_legacy_unknown), so the banner shows and Apply stays hidden. Absent status
        # is NEVER treated as approved (AC17 — closes the previous sprint's default-approved hole).
        _legacy_banner = ""
        if _is_legacy:
            _legacy_banner = (
                "<div style='background:#1A1A2A; border:1px solid #8888CC; "
                "border-radius:4px; padding:8px; margin-bottom:8px; color:#AAAAEE;'>"
                "&#9432; <b>Legacy recommendation — display only, cannot apply</b><br>"
                "<span style='font-size:11px;'>This recommendation was saved before the "
                "engineering validation gate and has no verified status. "
                "It is shown for reference only and cannot be applied.</span>"
                "</div>"
            )

        # Group 47: honest outcome-verification block — confidence/ranking/
        # explanation only.  Rendered only when the backend supplies a non-empty
        # explanation string (absent on legacy responses / when no cross-session
        # history exists).  It never adds an actionable field.
        _learning_outcome_html = ""
        try:
            _lo_expl = str(data.get("_learning_outcome_explanation", "") or "").strip()
            if _lo_expl:
                _lo_body = _lo_expl.replace("\n", "<br>")
                _learning_outcome_html = (
                    "<div style='background:#1A2618; border:1px solid #4A6B3A; "
                    "border-radius:4px; padding:8px; margin-bottom:8px; "
                    "color:#A9C99A; font-size:11px;'>"
                    f"{_lo_body}</div>"
                )
        except Exception:
            _learning_outcome_html = ""

        # Sprint 10: structured decision cards (ui.setup_advice_render) rendered
        # ABOVE the free-form analysis. When a legacy status banner is already
        # shown, drop the cards' own banner so the status isn't stated twice; the
        # approved/preserved/rejected tables still render.
        _advice_html = ""
        try:
            _cards = self._build_setup_advice_cards(
                data,
                approved_changes=approved_changes,
                rejected_changes=rejected_changes,
                protected_fields=_protected_fields,
                validation_failed=bool(data.get("engineering_validation_failed", False)),
                status_approved=_status_approved,
            )
            if _status_banner:
                _cards = [c for c in _cards if getattr(c, "kind", "") != "banner"]
            _advice_html = _advice_cards_to_html(_cards)
        except Exception:  # pragma: no cover - defensive; never break the display
            _advice_html = ""

        html = (
            _status_banner
            + _eng_banner
            + _legacy_banner
            + _diagnosis_html
            + _violation_banner
            + _validation_banner
            + _advice_html
            + f"<div style='{card}'><p style='margin:0;line-height:1.5;'>{analysis}</p></div>"
            + _learning_outcome_html
        )

        # --- Section 3: Pit Crew recommendation ---
        # ONLY shown when status is approved and changes exist.
        if _status_approved and approved_changes:
            html += (
                f"<div style='{chg_hdr}'>"
                "<b style='color:#8BC34A;'>&#9745; Pit Crew recommendation</b>"
                "</div>"
            )
            for ch in approved_changes:
                s        = ch.get("setting", "?")
                frm      = ch.get("from", "?")
                to_raw   = ch.get("to", "?")
                # Backend supplies to_clamped (value already within the car's allowed range).
                # Falls back to raw to when field is None or to is non-numeric.
                _clamped_val = ch.get("to_clamped", to_raw)
                why      = ch.get("why", "")
                # Prefer the clamped value when the param field was resolved by the backend.
                # field is None when the backend could not identify the param — show raw value.
                _field = ch.get("field")
                _clamp_note = ""
                if _field is not None:
                    # Field resolved — display the clamped value, never the raw out-of-range one.
                    to_display = _clamped_val
                    # Annotate only when clamped differs from raw (numeric guard).
                    try:
                        if abs(float(_clamped_val) - float(to_raw)) > 1e-9:
                            _clamp_note = f" (clamped to {_clamped_val})"
                    except (TypeError, ValueError):
                        pass  # non-numeric (e.g. tyre name) — no annotation needed
                else:
                    # Field unresolvable — acceptable degradation: show raw value as-is.
                    to_display = to_raw

                # Base change line (always shown).
                _ch_html = (
                    f"<div style='{chg_row}'>"
                    f"<b style='color:#E0E0E0;'>{s}</b>&nbsp;&nbsp;"
                    f"<span style='color:#F5A623;'>{frm}</span>"
                    f"&nbsp;&#8594;&nbsp;"
                    f"<span style='color:#8BC34A;'>{to_display}</span>"
                    + (f"<span style='color:#AAA; font-size:10px;'>{_clamp_note}</span>" if _clamp_note else "")
                    + (f"<br><span style='color:#888;font-size:11px;'>&nbsp;&nbsp;&nbsp;{why}</span>" if why else "")
                )

                # Per-change explainability sub-row (Group 42, AC22).
                # Only rendered when rule_id is present — absent on legacy/fallback changes.
                _rule_id = ch.get("rule_id", "")
                if _rule_id:
                    _symptom    = ch.get("symptom", "")
                    _rationale  = ch.get("rationale", "")
                    _evidence   = ch.get("evidence") or []
                    _rej_alts   = ch.get("rejected_alternatives") or []
                    _risk       = ch.get("risk_level", "")
                    _conf       = ch.get("confidence_level", "")
                    _align      = ch.get("driver_style_alignment", "")

                    # Badge colours for risk and confidence.
                    _risk_colour = {"low": "#8BC34A", "med": "#F5A623", "high": "#E86A5E"}.get(
                        str(_risk).lower(), "#AAAAAA")
                    _align_colour = {"aligned": "#8BC34A", "neutral": "#AAAAAA", "caution": "#F5A623"}.get(
                        str(_align).lower(), "#AAAAAA")

                    _ev_text   = "; ".join(_evidence) if _evidence else "—"
                    _alt_text  = "; ".join(_rej_alts) if _rej_alts else "none"

                    _detail_rows = ""
                    if _symptom:
                        _detail_rows += f"<tr><td style='color:#888; padding-right:8px;'>Symptom</td><td style='color:#CCC;'>{_symptom}</td></tr>"
                    if _rationale:
                        _detail_rows += f"<tr><td style='color:#888; padding-right:8px;'>Rationale</td><td style='color:#CCC;'>{_rationale}</td></tr>"
                    _detail_rows += f"<tr><td style='color:#888; padding-right:8px;'>Evidence</td><td style='color:#CCC;'>{_ev_text}</td></tr>"
                    _detail_rows += f"<tr><td style='color:#888; padding-right:8px;'>Considered alternatives</td><td style='color:#CCC;'>{_alt_text}</td></tr>"
                    _detail_rows += (
                        f"<tr><td style='color:#888; padding-right:8px;'>Risk</td>"
                        f"<td style='color:{_risk_colour};'>{_risk or '—'}</td></tr>"
                    )
                    _detail_rows += (
                        f"<tr><td style='color:#888; padding-right:8px;'>Confidence</td>"
                        f"<td style='color:#CCC;'>{_conf or '—'}</td></tr>"
                    )
                    _detail_rows += (
                        f"<tr><td style='color:#888; padding-right:8px;'>Driver style</td>"
                        f"<td style='color:{_align_colour};'>{_align or '—'}</td></tr>"
                    )
                    _detail_rows += (
                        f"<tr><td style='color:#888; padding-right:8px;'>Rule</td>"
                        f"<td style='color:#888; font-size:10px;'>{_rule_id}</td></tr>"
                    )
                    # Group 45: source_label — "Porsche-specific rule", "generic rule", etc.
                    # Only shown when the backend populates it (absent on legacy responses).
                    _source_label = ch.get("source_label", "")
                    if _source_label:
                        _detail_rows += (
                            f"<tr><td style='color:#888; padding-right:8px;'>Source</td>"
                            f"<td style='color:#7AB3D4; font-size:10px; font-style:italic;'>{_source_label}</td></tr>"
                        )
                    # Group 46: learning_influence — shown only when backend populated it
                    # (non-empty = genuine cross-session learning effect occurred).
                    # Subdued style: small, italic, muted amber to distinguish from Source.
                    _learning_influence = ch.get("learning_influence", "")
                    if _learning_influence:
                        _detail_rows += (
                            f"<tr><td style='color:#888; padding-right:8px;'>Learning</td>"
                            f"<td style='color:#C8AA66; font-size:10px; font-style:italic;'>{_learning_influence}</td></tr>"
                        )
                    # Group 46: session_influence — shown only when backend populated it.
                    # No session_influence row existed before Group 46 — adding fresh.
                    # Distinct subdued teal to separate from the learning row.
                    _session_influence = ch.get("session_influence", "")
                    if _session_influence:
                        _detail_rows += (
                            f"<tr><td style='color:#888; padding-right:8px;'>Session</td>"
                            f"<td style='color:#7ABFBF; font-size:10px; font-style:italic;'>{_session_influence}</td></tr>"
                        )

                    _ch_html += (
                        "<details style='margin-top:4px; margin-left:8px;'>"
                        "<summary style='color:#7AB3D4; font-size:11px; cursor:pointer;'>"
                        "Why Pit Crew recommended this</summary>"
                        "<div style='margin-top:4px; padding:4px 6px; "
                        "background:#1A2A3A; border-radius:3px;'>"
                        f"<table style='font-size:11px; border-collapse:collapse;'>{_detail_rows}</table>"
                        "</div>"
                        "</details>"
                    )

                _ch_html += "</div>"
                html += _ch_html

        # --- Section 4: Protected fields (collapsed) ---
        if _protected_fields:
            _pf_items = "".join(
                f"<li style='margin:2px 0; color:#CCC; font-size:11px;'><code>{f}</code></li>"
                for f in _protected_fields
            )
            html += (
                "<div style='background:#1A1A2A; border:1px solid #555588; "
                "border-radius:4px; padding:6px 10px; margin-top:6px;'>"
                "<details>"
                "<summary style='color:#AAAACC; font-size:11px; cursor:pointer;'>"
                "Protected fields (Pit Crew will not change these)</summary>"
                f"<ul style='margin:6px 0 2px 0; padding-left:16px;'>{_pf_items}</ul>"
                "</details>"
                "</div>"
            )

        # --- Section 5: Rejected candidate changes (rule-engine rejects) ---
        # Distinct from section 8 ("Rejected AI output") — these are rule-engine
        # candidates that were evaluated and rejected before the AI saw the plan.
        # Shown regardless of status (informational — never actionable).
        _rule_rejects = [
            r for r in rejected_changes
            if r.get("rule_id")  # rule-engine rejects carry rule_id
        ]
        if _rule_rejects:
            _rj_rows = ""
            for _rch in _rule_rejects:
                _rf  = _rch.get("field", _rch.get("setting", "?"))
                _rrule = _rch.get("rule_id", "")
                _rreason = _rch.get("reason", _rch.get("why", ""))
                _rsymp   = _rch.get("symptom", "")
                _rrisk   = _rch.get("risk_level", "")
                _rconf   = _rch.get("confidence_level", "")
                _ralign  = _rch.get("driver_style_alignment", "")
                _rj_rows += (
                    f"<div style='padding:3px 0 3px 8px; border-bottom:1px solid #2A2A1A;'>"
                    f"<b style='color:#C8AA66;'>{_rf}</b>"
                    + (f"&nbsp;<span style='color:#777; font-size:10px;'>[{_rrule}]</span>" if _rrule else "")
                    + (f"<br><span style='color:#AAA;font-size:11px;'>{_rreason}</span>" if _rreason else "")
                    + (f"<br><span style='color:#888;font-size:10px;'>"
                       f"symptom: {_rsymp} &nbsp;|&nbsp; risk: {_rrisk} &nbsp;|&nbsp; "
                       f"confidence: {_rconf} &nbsp;|&nbsp; alignment: {_ralign}"
                       f"</span>" if (_rsymp or _rrisk or _rconf or _ralign) else "")
                    + "</div>"
                )
            html += (
                "<div style='background:#1A1A0A; border:1px solid #665533; "
                "border-radius:4px; padding:6px 10px; margin-top:6px;'>"
                "<details>"
                "<summary style='color:#C8AA66; font-size:11px; cursor:pointer;'>"
                "Rejected candidate changes (not applied)</summary>"
                f"<div style='margin-top:6px;'>{_rj_rows}</div>"
                "</details>"
                "</div>"
            )

        # --- Section 6: AI audit result ---
        # Rendered ONLY when ai_audit is present in the response.
        # Makes clear the AI audited (did not author) the plan.
        if _ai_audit:
            _aud_status = _ai_audit.get("status", "")
            _aud_warnings    = _ai_audit.get("warnings") or []
            _aud_contradictions = _ai_audit.get("contradictions") or []
            _aud_missing     = _ai_audit.get("missing_evidence") or []
            _aud_notes       = _ai_audit.get("explanation_notes", "")
            _aud_stripped    = _ai_audit.get("stripped_fields") or []

            # Status badge colour.
            _aud_colour = {
                "APPROVED":               "#8BC34A",
                "APPROVED_WITH_WARNINGS": "#F5A623",
                "REJECTED":               "#E86A5E",
                "NEEDS_MORE_DATA":        "#AAAAAA",
            }.get(str(_aud_status).upper(), "#AAAAAA")

            _aud_body = ""
            if _aud_notes:
                _aud_body += (
                    f"<p style='margin:4px 0; color:#CCC; font-size:11px;'>{_aud_notes}</p>"
                )
            for _label, _items in (
                ("Warnings", _aud_warnings),
                ("Contradictions", _aud_contradictions),
                ("Missing evidence", _aud_missing),
            ):
                if _items:
                    _li = "".join(f"<li style='margin:2px 0;'>{i}</li>" for i in _items)
                    _aud_body += (
                        f"<p style='margin:4px 0 0 0; color:#AAA; font-size:11px;'><b>{_label}:</b></p>"
                        f"<ul style='margin:2px 0 4px 0; padding-left:16px; color:#CCC; font-size:11px;'>{_li}</ul>"
                    )
            if _aud_stripped:
                _stripped_str = ", ".join(f"<code>{f}</code>" for f in _aud_stripped)
                _aud_body += (
                    f"<p style='margin:4px 0; color:#888; font-size:10px;'>"
                    f"Stripped AI fields: {_stripped_str}</p>"
                )

            html += (
                "<div style='background:#1A2A1A; border:1px solid #336633; "
                "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
                "<div style='margin-bottom:4px;'>"
                "<b style='color:#88BB88; font-size:12px;'>AI audit</b>"
                f"&nbsp;&nbsp;<span style='color:{_aud_colour}; font-weight:bold; font-size:12px;'>"
                f"{_aud_status}</span>"
                "<span style='color:#777; font-size:10px; margin-left:8px;'>"
                "(AI checked the plan — it did not author the setup changes)</span>"
                "</div>"
                + (_aud_body or "<p style='margin:0; color:#888; font-size:11px;'>No details available.</p>")
                + "</div>"
            )

        # --- Section 7: Engineering gate failures (for rejected statuses) ---
        # approved_with_rejections shows these too: the survivors are applied, but
        # the driver must still see which field(s) were dropped and why.
        if _rec_status in {"validation_failed", "retry_failed", "approved_with_rejections"} and _eng_validation_errors:
            _gate_label = (
                "Fields dropped by engineering validation (other changes still apply):"
                if _rec_status == "approved_with_rejections"
                else "Engineering gate failures:"
            )
            _err_items = "".join(
                f"<li style='margin:2px 0;'>{e}</li>" for e in _eng_validation_errors
            )
            html += (
                "<div style='background:#2A0A0A; border:1px solid #883333; "
                "border-radius:4px; padding:6px 10px; margin-top:6px; color:#CC8888; font-size:11px;'>"
                f"<b>{_gate_label}</b>"
                f"<ul style='margin:4px 0 0 0; padding-left:16px;'>{_err_items}</ul>"
                "</div>"
            )

        # --- Section 8: Rejected AI text (existing collapsed block) ---
        # For validation_failed / retry_failed / blocked_no_safe_recommendation
        # when rejected_changes is non-empty (AI-format rejects without rule_id).
        # Visually distinct: muted/red, no apply path, no green header.
        # Only show changes that are NOT rule-engine candidates (no rule_id) so
        # there is no overlap with section 5.
        # NOTE: blocked_no_safe_recommendation does NOT enable the CHANGES section or
        # the Apply button — those remain gated on _status_approved (APPROVED_STATUSES only).
        _ai_text_rejects = [
            r for r in rejected_changes
            if not r.get("rule_id")  # AI-format or old-format rejects lack rule_id
        ]
        if _rec_status in {"validation_failed", "retry_failed", "blocked_no_safe_recommendation"} and _ai_text_rejects:
            _rej_rows = ""
            for _rch in _ai_text_rejects:
                _rs = _rch.get("setting", "?")
                _rfr = _rch.get("from", "?")
                _rto = _rch.get("to", "?")
                _rwhy = _rch.get("why", "")
                _rej_rows += (
                    f"<div style='padding:3px 0 3px 8px; border-bottom:1px solid #3A1A1A;'>"
                    f"<b style='color:#AA8888;'>{_rs}</b>&nbsp;&nbsp;"
                    f"<span style='color:#CC8888;'>{_rfr}</span>"
                    f"&nbsp;&#8594;&nbsp;"
                    f"<span style='color:#AA6666;'>{_rto}</span>"
                    + (f"<br><span style='color:#777;font-size:10px;'>&nbsp;&nbsp;&nbsp;{_rwhy}</span>"
                       if _rwhy else "")
                    + "</div>"
                )
            html += (
                "<div style='background:#1A0A0A; border:1px solid #663333; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<details>"
                "<summary style='color:#CC6666; font-size:11px; cursor:pointer;'>"
                "Rejected AI output — not for use</summary>"
                f"<div style='margin-top:6px;'>{_rej_rows}</div>"
                "</details>"
                "</div>"
            )

        # --- Sections 9-14: Race-Engineer remediation surfaces (additive) ---
        # Read-only presentation of fields the deterministic backend now emits.
        # Wrapped so a malformed field can never break the core render above;
        # every section self-guards and is simply absent on legacy responses.
        try:
            html += self._render_race_engineer_surfaces(data)
        except Exception as _re_exc:
            print(f"[SetupBuilder] race-engineer surfaces render skipped: {_re_exc}")

        _result_text.setHtml(html)

        # Save to history
        config_id = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
        car  = self._config.get("strategy", {}).get("car", "")
        track = self._config.get("strategy", {}).get("track", "")
        if config_id:
            try:
                from data.setup_history import save_entry
                # Subjective labels (liked/hated/applied) are no longer written
                # from here — that signal now comes from the Practice Review
                # per-run rating. Still record the feeling text for context.
                save_entry(config_id, car, track, {
                    "type": entry_type,
                    "feeling": feeling or "",
                    "analysis": analysis,
                    "changes": approved_changes,
                }, driver_feedback=feeling or "",
                   validation_status=_rec_status)
            except Exception as _e:
                print(f"[SetupHistory] save failed: {_e}")

        # Home Dashboard: a new setup context was captured above — keep an open
        # Home tab current (display-only; no-op when Home is not visible).
        if hasattr(self, "_home_refresh_if_visible"):
            self._home_refresh_if_visible()

        # DEF-073-008: a from-scratch BASELINE is a COMPLETE authored setup, not an
        # incremental change to a parent — its values must POPULATE the Car Setup form
        # so the driver can read and transfer the whole setup into GT7. Previously the
        # form kept its defaults (fields were only highlighted), so e.g. ride height
        # showed the 80 mm default instead of the authored baseline value, and most
        # fields "didn't load". The Analyse path stays Apply-gated (it changes a handful
        # of fields over an existing setup and has something to apply over); a baseline
        # does not, so it fills directly. ``approved_fields`` is already category-gated
        # by the backend, so locked-category fields are never written.
        if entry_type == "baseline_setup" and approved_fields:
            _fill_form = _form or getattr(self, "_race_form", None)
            if _fill_form is not None and hasattr(_fill_form, "apply_ai_fields"):
                try:
                    _fill_form.apply_ai_fields(dict(approved_fields))
                    if _fill_form is getattr(self, "_race_form", None):
                        _bl_keys = [k for k, v in approved_fields.items()
                                    if isinstance(v, (int, float))]
                        if _bl_keys:
                            self._highlight_changed_fields(_bl_keys)
                except Exception as _bl_e:  # pragma: no cover - defensive; never break display
                    print(f"[Baseline] form fill failed: {_bl_e}")

        # UAT Finding 3: mirror the recommendation into the structured tabbed
        # view. Proposed changes highlight immediately here (at generate) — the
        # "Applied in Game" button only flips status later, it is not what first
        # highlights a field.
        try:
            self._populate_setup_recommendation_view(data, _status_approved)
            _is_race_form = (_form is None) or (_form is getattr(self, "_race_form", None))
            if _status_approved and approved_changes and _is_race_form:
                # Highlight the ACTUAL setup-box spinboxes for the proposed
                # fields at GENERATE time (previously only fired on Apply).
                _changed_keys = [c.get("field") for c in approved_changes if c.get("field")]
                if _changed_keys:
                    self._highlight_changed_fields(_changed_keys)
                # De-squash: the structured view is now the recommendation
                # surface, so collapse the old cramped HTML result box.
                if _result_text is not None:
                    _result_text.setVisible(False)
        except Exception as _e:
            print(f"[SetupRecView] populate failed: {_e}")

    def _render_discipline_field_plan(self, plan: dict) -> str:
        """Thin wrapper — delegates to the module-level renderer so the surfaces
        method (which is sometimes called with self=None in tests) never needs self."""
        return _discipline_field_plan_html(plan)

    def _render_discipline_comparison_workspace(self, plan: dict) -> str:
        """Thin wrapper — delegates to the module-level workspace renderer."""
        return _discipline_comparison_workspace_html(plan)

    def _render_race_engineer_surfaces(self, data: dict) -> str:
        """Build the additive Race-Engineer panels from the response dict.

        Every panel is optional: absent/empty backend fields render nothing, so
        legacy responses are unaffected. Pure presentation — no data is authored.
        """
        if not isinstance(data, dict):
            return ""
        html = ""

        # --- Section 8b: Discipline field plan (Group 64) ---
        # Base / Qualifying / Race authored side-by-side so the driver can SEE where
        # the three disciplines genuinely differ (not just a relabelled setup), with
        # the proven-history value and each field's disposition.
        html += _closed_loop_html(data)
        html += _development_timeline_html(data)
        html += _engineering_brain_html(data)
        html += _balance_solution_html(data.get("balance_solution"))
        html += _driver_fit_html(data.get("driver_fit_reasoning"))
        # Prefer the richer comparison workspace; fall back to the compact side-by-side
        # table when nothing genuinely differs between the disciplines.
        _dfp = data.get("discipline_field_plan")
        _workspace = _discipline_comparison_workspace_html(_dfp)
        html += _workspace if _workspace else _discipline_field_plan_html(_dfp)

        # --- Section 9: Qualifying discipline (Phase 7) ---
        _qb = data.get("qualifying_brief") or {}
        if _qb.get("is_qualifying"):
            _q_strengths = _qb.get("strengths") or []
            _q_compromises = _qb.get("compromises") or []
            _q_body = (
                f"<p style='margin:2px 0; color:#EED8B0; font-size:11px;'>"
                f"{_qb.get('objective', '')}</p>"
            )
            if _q_strengths:
                _q_body += (
                    "<p style='margin:4px 0 0 0; color:#AAA; font-size:11px;'>"
                    "<b style='color:#8BC34A;'>Buys:</b> "
                    + "; ".join(_q_strengths) + ".</p>"
                )
            if _q_compromises:
                _q_body += (
                    "<p style='margin:2px 0 0 0; color:#AAA; font-size:11px;'>"
                    "<b style='color:#E0A060;'>Trades away:</b> "
                    + "; ".join(_q_compromises) + ".</p>"
                )
            _q_warn = _qb.get("one_lap_warning", "")
            if _q_warn:
                _q_body += (
                    f"<p style='margin:5px 0 0 0; color:#E86A5E; font-size:11px;'>"
                    f"&#9888; {_q_warn}</p>"
                )
            html += (
                "<div style='background:#2A1D0A; border:1px solid #886633; "
                "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
                "<b style='color:#F5A623; font-size:12px;'>"
                "&#127937; Qualifying tune &mdash; one flying lap</b>"
                f"{_q_body}</div>"
            )

        # --- Section 10: Candidate comparison (Phase 14) ---
        _cc = data.get("candidate_comparison") or {}
        _cc_cols = _cc.get("columns") or []
        _cc_rows = _cc.get("rows") or []
        if _cc_cols and _cc_rows:
            _hdr = "<th style='text-align:left; color:#888; padding:2px 8px 2px 0;'>Field</th>"
            for _c in _cc_cols:
                _hdr += (f"<th style='text-align:left; color:#7AB3D4; "
                         f"padding:2px 8px 2px 0;' title='{_c.get('source', '')}'>"
                         f"{_c.get('label', _c.get('name', ''))}</th>")
            _body = ""
            for _r in _cc_rows:
                _differs = _r.get("differs")
                _fname_col = "#F5A623" if _differs else "#CCC"
                _row_cells = (f"<td style='color:{_fname_col}; padding:2px 8px 2px 0;'>"
                              f"<code>{_r.get('field', '')}</code></td>")
                _vals = _r.get("values") or {}
                for _c in _cc_cols:
                    _v = _vals.get(_c.get("name"))
                    _vtxt = "&mdash;" if _v is None else (
                        f"{_v:g}" if isinstance(_v, (int, float)) else str(_v))
                    _row_cells += (f"<td style='color:#CCC; padding:2px 8px 2px 0;'>"
                                   f"{_vtxt}</td>")
                _body += f"<tr>{_row_cells}</tr>"
            html += (
                "<div style='background:#12202A; border:1px solid #2E4A5A; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<details><summary style='color:#7AB3D4; font-size:11px; cursor:pointer;'>"
                "Candidate comparison (current vs proven vs recommended)</summary>"
                "<table style='font-size:11px; border-collapse:collapse; margin-top:6px;'>"
                f"<tr>{_hdr}</tr>{_body}</table>"
                "<p style='color:#666; font-size:10px; margin:4px 0 0 0;'>"
                "Amber field = candidates disagree.</p>"
                "</details></div>"
            )

        # --- Section 11: Controlled test sequence (Phase 13) ---
        _ts = data.get("test_sequence") or {}
        _ts_stages = _ts.get("stages") or []
        if _ts_stages:
            _stage_html = ""
            for _s in _ts_stages:
                _iso = _s.get("isolate_note", "")
                _stage_html += (
                    "<div style='padding:4px 0; border-bottom:1px solid #223022;'>"
                    f"<b style='color:#8BC34A;'>{_s.get('order', '')}. "
                    f"{_s.get('change', '')}</b>"
                    f"<span style='color:#666; font-size:10px;'>&nbsp;&nbsp;"
                    f"({_s.get('rationale', '')})</span>"
                    f"<br><span style='color:#AAA; font-size:11px;'>"
                    f"&#10003; {_s.get('success_criterion', '')}</span>"
                    f"<br><span style='color:#C89060; font-size:11px;'>"
                    f"&#8630; {_s.get('rollback', '')}</span>"
                    + (f"<br><span style='color:#E0A060; font-size:10px;'>"
                       f"&#9888; {_iso}</span>" if _iso else "")
                    + "</div>"
                )
            _ts_note = _ts.get("note", "")
            html += (
                "<div style='background:#12220E; border:1px solid #3A5A2E; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<details><summary style='color:#8BC34A; font-size:11px; cursor:pointer;'>"
                "How to test these changes (one at a time)</summary>"
                f"<div style='margin-top:6px;'>{_stage_html}</div>"
                + (f"<p style='color:#888; font-size:10px; margin:6px 0 0 0;'>{_ts_note}</p>"
                   if _ts_note else "")
                + "</details></div>"
            )

        # --- Section 12: Feedback dispositions (Phase 4) ---
        _fd = data.get("feedback_dispositions") or []
        if _fd:
            _state_colour = {"addressed": "#8BC34A", "deferred": "#F5A623",
                             "strategy": "#7AB3D4", "preserved": "#AAAAAA"}
            _fd_rows = ""
            for _d in _fd:
                _st = str(_d.get("state", "")).lower()
                _col = _state_colour.get(_st, "#AAAAAA")
                _fd_rows += (
                    "<div style='padding:3px 0; border-bottom:1px solid #222;'>"
                    f"<span style='color:{_col}; font-weight:bold; font-size:11px;'>"
                    f"[{_st or '?'}]</span> "
                    f"<span style='color:#CCC; font-size:11px;'>{_d.get('feedback', '')}</span>"
                    + (f"<br><span style='color:#888; font-size:10px;'>"
                       f"&nbsp;&nbsp;{_d.get('detail', '')}</span>"
                       if _d.get('detail') else "")
                    + "</div>"
                )
            html += (
                "<div style='background:#161622; border:1px solid #444466; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<details><summary style='color:#AAAACC; font-size:11px; cursor:pointer;'>"
                "What happened to each thing you reported</summary>"
                f"<div style='margin-top:6px;'>{_fd_rows}</div>"
                "</details></div>"
            )

        # --- Section 13: Historical comparison (Phase 9) ---
        _hc = data.get("historical_comparison") or []
        if _hc:
            _hc_rows = ""
            for _r in _hc:
                _flag = _r.get("deviation_flagged")
                _fcol = "#F5A623" if _flag else "#CCC"
                _hc_rows += (
                    "<div style='padding:3px 0; border-bottom:1px solid #2A2A1A;'>"
                    f"<b style='color:{_fcol};'><code>{_r.get('field', '')}</code></b> "
                    f"<span style='color:#888; font-size:11px;'>"
                    f"current {_r.get('current', '—')} &nbsp;|&nbsp; "
                    f"proven {_r.get('historical', '—')} &nbsp;|&nbsp; "
                    f"rec {_r.get('recommended', '—')}</span>"
                    + (f"<br><span style='color:#C8AA66; font-size:10px;'>"
                       f"&#9888; {_r.get('note', '')}</span>" if _flag and _r.get('note') else "")
                    + "</div>"
                )
            html += (
                "<div style='background:#1A1A0A; border:1px solid #665533; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<details><summary style='color:#C8AA66; font-size:11px; cursor:pointer;'>"
                "Compared to your proven setups</summary>"
                f"<div style='margin-top:6px;'>{_hc_rows}</div>"
                "<p style='color:#666; font-size:10px; margin:4px 0 0 0;'>"
                "Amber = the recommendation moves materially away from a proven value.</p>"
                "</details></div>"
            )

        # --- Section 14: Balance interaction (Phase 10) ---
        _arb = data.get("arbitration") or {}
        _arb_notes = _arb.get("notes") or []
        _arb_contrib = _arb.get("contributors") or []
        if _arb_notes and _arb_contrib:
            _arb_body = "".join(
                f"<p style='margin:2px 0; color:#CCC; font-size:11px;'>{_n}</p>"
                for _n in _arb_notes
            )
            html += (
                "<div style='background:#20161A; border:1px solid #5A3E4A; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<b style='color:#D48AB3; font-size:11px;'>&#9878; Balance interaction</b>"
                f"{_arb_body}</div>"
            )

        # --- Section 15: Bottoming impact verdict (Group 63) ---
        _bi = data.get("bottoming_impact") or {}
        if _bi.get("impact"):
            _bi_class = str(_bi.get("impact", ""))
            _bi_colour = {
                "REQUIRED": "#E86A5E", "PERFORMANCE_RELEVANT": "#E0A060",
                "ADVISORY": "#C9C075", "NORMAL_OR_EXPECTED": "#8BC34A",
                "UNKNOWN": "#9AA0A6",
            }.get(_bi_class, "#9AA0A6")
            html += (
                "<div style='background:#141A20; border:1px solid #33414E; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<b style='color:#7AB3D4; font-size:11px;'>&#128207; Bottoming &mdash; impact, not just count</b>"
                f"<p style='margin:3px 0 0 0; font-size:11px;'>"
                f"<b style='color:{_bi_colour};'>{_bi_class}</b> "
                f"<span style='color:#AAA;'>&mdash; {_bi.get('reason', '')}</span></p></div>"
            )

        # --- Section 16: LSD triplet assessment (Group 63) ---
        _lsd = data.get("lsd_assessment") or {}
        _lsd_fields = _lsd.get("fields") or []
        if _lsd_fields:
            _lsd_body = ""
            for _lf in _lsd_fields:
                _ev = "&#10003;" if _lf.get("evaluated") else "&#8211;"
                _cur = _lf.get("current")
                _pv = _lf.get("proven")
                _cur_s = f"{_cur:g}" if isinstance(_cur, (int, float)) else "?"
                _pv_s = (f", proven <b style='color:#8BC34A;'>{_pv:g}</b>"
                         if isinstance(_pv, (int, float)) else "")
                _lsd_body += (
                    f"<p style='margin:3px 0; color:#CCC; font-size:11px;'>"
                    f"{_ev} <b style='color:#DDD;'>{_lf.get('label', _lf.get('field',''))}</b> "
                    f"<span style='color:#888;'>(current {_cur_s}{_pv_s})</span> "
                    f"&mdash; {_lf.get('direction','')}: {_lf.get('evidence','')}</p>"
                )
                _ct = _lf.get("controlled_test")
                if _ct:
                    _lsd_body += (
                        f"<p style='margin:0 0 4px 16px; color:#7AB3D4; font-size:10px;'>"
                        f"&#128295; {_ct}</p>"
                    )
            html += (
                "<div style='background:#161A14; border:1px solid #3E5A3E; "
                "border-radius:4px; padding:8px 10px; margin-top:8px;'>"
                "<b style='color:#8BC34A; font-size:12px;'>&#9881; Differential (LSD) &mdash; all three fields</b>"
                f"<div style='margin-top:4px;'>{_lsd_body}</div>"
                "<p style='color:#666; font-size:10px; margin:4px 0 0 0;'>"
                "Initial / Acceleration / Braking evaluated independently against your proven "
                "same-car values; confirm direction by controlled test before applying.</p></div>"
            )

        # --- Section 17: Targeted tests to resolve unknowns (Group 63) ---
        _tt = data.get("_targeted_tests") or []
        if _tt:
            _tt_body = "".join(
                f"<p style='margin:2px 0; color:#CCC; font-size:11px;'>&#128295; {_t}</p>"
                for _t in _tt
            )
            html += (
                "<div style='background:#101820; border:1px solid #2E4658; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                "<b style='color:#5FA8D3; font-size:11px;'>&#128300; Precise targeted tests</b>"
                f"{_tt_body}</div>"
            )

        # --- Section 18: Recommendation completeness verdict (Group 64) ---
        # A change being safe is not the same as the setup being complete. Show the
        # driver whether this is a finished setup, a partial, or a test plan — and
        # which confirmed problems are still untreated.
        _comp = data.get("recommendation_completeness") or {}
        if isinstance(_comp, dict) and _comp.get("state"):
            _state = str(_comp.get("state", ""))
            _complete = bool(_comp.get("complete"))
            _untreated = _comp.get("untreated") or []
            _colour = "#8BC34A" if _complete else "#E0A458"
            _label_map = {
                "approved_complete": "Complete setup",
                "approved_incremental_test": "Incremental controlled test",
                "partial_recommendation": "Partial recommendation",
                "targeted_test_required": "Targeted test required",
                "insufficient_evidence": "Insufficient evidence",
                "conflicting_evidence": "Conflicting evidence",
                "blocked_unsafe": "Blocked — unsafe",
                "rejected_incoherent": "Rejected — incoherent",
            }
            _readable = _label_map.get(_state, _state.replace("_", " ").title())
            _untreated_html = ""
            if _untreated and not _complete:
                _names = ", ".join(str(u).replace("_", " ") for u in _untreated)
                _untreated_html = (
                    f"<p style='margin:2px 0; color:#CCC; font-size:11px;'>"
                    f"Still untreated: {_names}</p>")
            html += (
                "<div style='background:#14100A; border:1px solid #5A4A2E; "
                "border-radius:4px; padding:6px 10px; margin-top:8px;'>"
                f"<b style='color:{_colour}; font-size:11px;'>&#9878; Setup completeness: "
                f"{_readable}</b>{_untreated_html}</div>"
            )

        return html

    def _apply_and_save_ai_setup(self) -> None:
        """Apply approved AI setup fields to the form.

        Only writes from self._last_setup_ai_fields which is populated exclusively
        from approved_fields (never from raw setup_fields or rejected changes).
        The Apply button is only shown when status is in APPROVED_STATUSES, so
        this method is only reachable for approved recommendations.
        """
        if not getattr(self, "_last_setup_ai_fields", {}):
            return
        # Route through SetupFormWidget.apply_ai_fields so that:
        #   - transmission_max_speed_kmh is stripped (display-only, must not write spinbox)
        #   - gear_1..gear_6 keys are mapped to the gear_ratios list
        # This makes the Race-form path consistent with _apply_ai_setup_for_form
        # which calls form.apply_ai_fields() on the Qualifying form.
        self._race_form.apply_ai_fields(self._last_setup_ai_fields)
        # Keep the structured R/Q setup name (e.g. "R NGR Porsche Cup Rd7 2")
        # instead of overwriting it with "AI Fix N" — on Save, resolve_save_name
        # advances it to the next numbered attempt for the event, so the naming
        # convention is preserved. The AI-fix linkage for learning is recorded in
        # the DB (apply_recommendation_for_car_track) and setup_history, not here.
        # Highlight changed fields so the user can see what was modified.
        self._highlight_changed_fields(list(self._last_setup_ai_fields.keys()))
        # Link recommendation to this session
        _car_id_apply = getattr(self, "_car_id_build", 0)
        _track_apply = self._config.get("strategy", {}).get("track", "")
        _sid_apply = (
            int(self._dispatcher._session_id)
            if hasattr(self, "_dispatcher") and self._dispatcher is not None
            else 0
        )
        if self._db and _car_id_apply > 0 and _track_apply and _sid_apply > 0:
            try:
                self._db.apply_recommendation_for_car_track(
                    _car_id_apply, _track_apply, _sid_apply
                )
            except Exception as _are:
                print(f"[SetupHistory] apply_recommendation failed: {_are}")
        # Auto-save (UAT): applying a setup means it is now the current setup on
        # the car, so persist it immediately instead of requiring a separate Save
        # click. Only auto-saves when an active event exists (the save path needs
        # one to name/group the setup); with no event the user can still Save
        # manually, and we avoid interrupting the apply with a modal warning.
        self._autosave_applied_setup()
        if hasattr(self, "_btn_apply_ai_setup"):
            self._btn_apply_ai_setup.setVisible(False)
        self._last_setup_ai_fields = {}
        self._refresh_revert_buttons()

    def _autosave_applied_setup(self, form: "SetupFormWidget | None" = None) -> None:
        """Persist the just-applied setup when an active event exists.

        Best-effort: never raises into the apply path. Skips silently when no
        active event is selected so no modal warning interrupts the apply.
        """
        try:
            _evt = self._active_event() if hasattr(self, "_active_event") else None
            if not (_evt and _evt.get("name")):
                return
            if form is not None and form is not self._race_form:
                self._setup_save_for_form(form)
            else:
                self._setup_save()
        except Exception as _asv:  # pragma: no cover - defensive
            print(f"[SetupSave] auto-save on apply failed: {_asv}")

    def _resolve_recent_laps(self, car_id: int, track: str) -> list:
        """Return per-lap telemetry rows for the most recent session of car+track.

        OFR-2: feeds per_lap_telemetry into the setup engine so the discipline
        block in the setup-build prompt is real.  Always returns a list (empty
        on any error, missing DB, zero car_id, or no previous session).
        Fetches on the UI thread so the worker closure captures a plain list.
        """
        # OFR-2: guard — no db, no car, no track → nothing to resolve.
        if not (self._db and car_id > 0 and track):
            return []
        try:
            sid = self._db.get_previous_session_id(car_id, track, 99_999_999)
            if not sid:
                return []
            return self._db.get_session_laps(
                sid, exclude_pit=True, exclude_out=True, limit=5, latest=True
            )
        except Exception as _ofr2_err:  # pragma: no cover - defensive
            print(f"[OFR-2] _resolve_recent_laps failed: {_ofr2_err}")
            return []

    def _run_build_setup(self) -> None:
        """Retired: the from-scratch AI build path was removed in the
        determinism rebuild (Sprint 1). Use "Build Baseline Setup" for a
        deterministic from-scratch setup, or "Analyse" for rule-validated
        changes. Retained as a no-op so existing wiring stays valid."""
        return

    def _display_build_setup_result(self, result: tuple) -> None:
        status, payload, *rest = result
        session_type = rest[0] if rest else "Race"
        # Per-form routing: position 3 (rest[1]) may hold a SetupFormWidget
        _form = rest[1] if len(rest) > 1 and hasattr(rest[1], "purpose") else None
        _btn_build    = _form._btn_build_setup    if _form else self._btn_build_setup
        _build_result = _form._build_setup_result if _form else self._build_setup_result
        _btn_build.setEnabled(False)
        _btn_build.setText("Build Setup")
        if status == "err":
            _build_result.setPlainText(f"Build Setup failed: {payload}")
            return
        if _form is not None:
            self._apply_build_setup_result_for_form(payload, session_type, _form)
        else:
            self._apply_build_setup_result(payload, session_type)

    def _apply_build_setup_result(self, rec, session_type: str = "Race") -> None:
        """Fill all Car Setup form fields from a CarSetupRecommendation."""
        # Re-bound spinboxes with per-car ranges before setting values
        _car_name = self._config.get("strategy", {}).get("car", "") or ""
        _ranges = resolve_ranges(_car_name)

        def _set_int(spin, param, val):
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            spin.setRange(int(lo), int(hi))
            _set_spin_readonly(spin, lo >= hi)
            spin.setValue(max(int(lo), min(int(hi), int(round(val)))))

        def _set_dbl(spin, param, val):
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            spin.setRange(float(lo), float(hi))
            _set_spin_readonly(spin, lo >= hi)
            spin.setValue(max(float(lo), min(float(hi), float(val))))

        _set_int(self._setup_rh_f,       "ride_height_front",  rec.ride_height_front)
        _set_int(self._setup_rh_r,       "ride_height_rear",   rec.ride_height_rear)
        _set_dbl(self._setup_spr_f,      "springs_front",      rec.springs_front)
        _set_dbl(self._setup_spr_r,      "springs_rear",       rec.springs_rear)
        _set_int(self._setup_dmp_f_comp, "dampers_front_comp", rec.dampers_front_comp)
        _set_int(self._setup_dmp_f_ext,  "dampers_front_ext",  rec.dampers_front_ext)
        _set_int(self._setup_dmp_r_comp, "dampers_rear_comp",  rec.dampers_rear_comp)
        _set_int(self._setup_dmp_r_ext,  "dampers_rear_ext",   rec.dampers_rear_ext)
        _set_int(self._setup_arb_f,      "arb_front",          rec.arb_front)
        _set_int(self._setup_arb_r,      "arb_rear",           rec.arb_rear)
        _set_dbl(self._setup_cam_f,      "camber_front",       rec.camber_front)
        _set_dbl(self._setup_cam_r,      "camber_rear",        rec.camber_rear)
        _set_dbl(self._setup_toe_f,      "toe_front",          rec.toe_front)
        _set_dbl(self._setup_toe_r,      "toe_rear",           rec.toe_rear)
        _set_int(self._setup_aero_f,     "aero_front",         rec.aero_front)
        _set_int(self._setup_aero_r,     "aero_rear",          rec.aero_rear)
        _set_int(self._setup_lsd_i,      "lsd_initial",        rec.lsd_initial)
        _set_int(self._setup_lsd_a,      "lsd_accel",          rec.lsd_accel)
        _set_int(self._setup_lsd_d,      "lsd_decel",          rec.lsd_decel)
        _set_int(self._setup_lsd_f_i,    "lsd_front_initial",  rec.lsd_front_initial)
        _set_int(self._setup_lsd_f_a,    "lsd_front_accel",    rec.lsd_front_accel)
        _set_int(self._setup_lsd_f_d,    "lsd_front_decel",    rec.lsd_front_decel)
        _set_int(self._setup_bb,         "brake_bias",         rec.brake_bias)
        _set_dbl(self._setup_ballast_kg, "ballast_kg",         rec.ballast_kg)
        _set_int(self._setup_ballast_pos,"ballast_position",   rec.ballast_position)
        _set_dbl(self._setup_power_rest, "power_restrictor",   rec.power_restrictor)
        if hasattr(rec, "ecu_recommendation") and rec.ecu_recommendation:
            self._lbl_ecu_rec.setText(rec.ecu_recommendation)
        else:
            self._lbl_ecu_rec.setText("—")
        if rec.final_drive > 0.0:
            self._spin_final_drive.setValue(rec.final_drive)
        for i, spin in enumerate(self._gear_ratio_spins):
            spin.setValue(rec.gear_ratios[i] if i < len(rec.gear_ratios) else 0.0)
        if rec.transmission_max_speed_kmh > 0:
            self._spin_top_speed.setValue(rec.transmission_max_speed_kmh)
        # Prevent the telemetry packet timer from overwriting the AI-filled values.
        self._gear_ratios_captured = True
        # Highlight all params the build populated so the user can see what changed.
        _build_param_keys = [
            "ride_height_front", "ride_height_rear", "springs_front", "springs_rear",
            "dampers_front_comp", "dampers_front_ext", "dampers_rear_comp", "dampers_rear_ext",
            "arb_front", "arb_rear", "camber_front", "camber_rear", "toe_front", "toe_rear",
            "aero_front", "aero_rear", "lsd_initial", "lsd_accel", "lsd_decel",
            "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
            "brake_bias", "ballast_kg", "ballast_position", "power_restrictor",
        ]
        self._highlight_changed_fields(_build_param_keys)

        # Auto-fill shift RPM from AI recommendation.
        # Use new dual fields (shift_rpm_qual / shift_rpm_race) with legacy fallback.
        _qual_rpm = getattr(rec, "shift_rpm_qual", 0) or 0
        _race_rpm = getattr(rec, "shift_rpm_race", 0) or 0
        _legacy_rpm = getattr(rec, "shift_rpm", 0) or 0
        if _qual_rpm == 0 and _legacy_rpm > 0:
            _qual_rpm = _legacy_rpm
        if _race_rpm == 0 and _legacy_rpm > 0:
            _race_rpm = _legacy_rpm
        if _qual_rpm > 0 or _race_rpm > 0:
            sb = self._config.setdefault("shift_beep", {})
            if _qual_rpm > 0:
                sb["qual_rpm"] = _qual_rpm
                if hasattr(self, "_spin_shift_rpm_qual"):
                    self._spin_shift_rpm_qual.blockSignals(True)
                    self._spin_shift_rpm_qual.setValue(_qual_rpm)
                    self._spin_shift_rpm_qual.blockSignals(False)
                if hasattr(self, "_spin_live_shift_rpm_qual"):
                    self._spin_live_shift_rpm_qual.blockSignals(True)
                    self._spin_live_shift_rpm_qual.setValue(_qual_rpm)
                    self._spin_live_shift_rpm_qual.blockSignals(False)
            if _race_rpm > 0:
                sb["race_rpm"] = _race_rpm
                if hasattr(self, "_spin_shift_rpm_race"):
                    self._spin_shift_rpm_race.blockSignals(True)
                    self._spin_shift_rpm_race.setValue(_race_rpm)
                    self._spin_shift_rpm_race.blockSignals(False)
                if hasattr(self, "_spin_live_shift_rpm_race"):
                    self._spin_live_shift_rpm_race.blockSignals(True)
                    self._spin_live_shift_rpm_race.setValue(_race_rpm)
                    self._spin_live_shift_rpm_race.blockSignals(False)
            self._persist_config()

        gear_section = ""
        if rec.final_drive > 0.0 or rec.transmission_max_speed_kmh > 0 or rec.gear_ratios:
            gear_section = "<b>Transmission Recommendation</b><br>"
            if rec.final_drive > 0.0:
                gear_section += f"Final drive: <b>{rec.final_drive:.3f}</b>&nbsp;&nbsp;"
            if rec.transmission_max_speed_kmh > 0:
                gear_section += f"Top speed target: <b>{rec.transmission_max_speed_kmh:.0f} km/h</b><br>"
            else:
                gear_section += "<br>"
            if rec.gear_ratios:
                ratio_str = "&nbsp;&nbsp;".join(
                    f"G{i+1}: {r:.3f}" for i, r in enumerate(rec.gear_ratios)
                )
                gear_section += ratio_str + "<br>"
            gear_section += "<i style='color:#888;'>Enter these in GT7 transmission settings</i><br><br>"

        ecu_section = ""
        if hasattr(rec, "ecu_recommendation") and rec.ecu_recommendation and rec.ecu_recommendation != "—":
            ecu_section = (
                "<b>ECU / Power Advice</b><br>"
                f"<span style='color:#F5C542;'>{rec.ecu_recommendation}</span><br><br>"
            )

        rpm_section = ""
        if hasattr(rec, "shift_rpm") and rec.shift_rpm > 0:
            rpm_section = (
                f"<b>Shift RPM ({session_type}):</b> "
                f"<span style='color:#6CF;'>{rec.shift_rpm:,} RPM</span> "
                f"<span style='color:#888;'>(saved to Shift Beep settings)</span><br><br>"
            )
        # Format reasoning: AI returns paragraphs separated by \n\n — render as proper HTML paragraphs
        _para_style = "margin: 0 0 10px 0; line-height: 1.5;"
        _paras = [p.strip().replace("\n", " ") for p in rec.reasoning.split("\n\n") if p.strip()]
        if not _paras:  # fallback if AI returned a single block
            _paras = [s.strip() for s in rec.reasoning.split(". ") if s.strip()]
            _paras = [". ".join(_paras[:3]), ". ".join(_paras[3:6]), ". ".join(_paras[6:])]
            _paras = [p for p in _paras if p]
        reasoning_html = "".join(f"<p style='{_para_style}'>{p}</p>" for p in _paras)
        # Append a neutral note when reasoning is present to indicate that all values
        # have been clamped to the car's allowed parameter ranges.
        _range_note_html = ""
        if _paras:
            _range_note_html = (
                "<p style='color:#888; font-size:11px; margin:4px 0 0 0;'>"
                "(Values shown applied to the car's allowed range.)"
                "</p>"
            )
        self._build_setup_result.setHtml(
            rpm_section
            + ecu_section
            + gear_section
            + f"<b>AI Setup Reasoning</b><br>"
            + reasoning_html
            + _range_note_html
        )

        # Save build setup to history
        config_id = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
        car  = self._config.get("strategy", {}).get("car", "")
        track = self._config.get("strategy", {}).get("track", "")
        if config_id:
            try:
                from data.setup_history import save_entry
                snapshot = self._current_setup_dict()
                is_qual = "qual" in session_type.lower()
                save_entry(config_id, car, track, {
                    "type": "build_qual" if is_qual else "build_race",
                    "session_type": session_type,
                    "setup_snapshot": snapshot,
                    "reasoning": rec.reasoning,
                    "shift_rpm": getattr(rec, "shift_rpm", 0),
                    "shift_rpm_qual": getattr(rec, "shift_rpm_qual", 0),
                    "shift_rpm_race": getattr(rec, "shift_rpm_race", 0),
                    "ecu_recommendation": getattr(rec, "ecu_recommendation", ""),
                })
            except Exception as _e:
                print(f"[SetupHistory] build save failed: {_e}")

    def _apply_build_setup_result_for_form(
        self, rec, session_type: str, form: "SetupFormWidget"
    ) -> None:
        """Fill a specific form's fields from a CarSetupRecommendation.

        Mirrors ``_apply_build_setup_result`` but targets ``form``'s widgets
        instead of the aliased ``self._setup_*`` attrs (which always point to
        the Race form).  Used when the Qualifying panel's Build button fires.
        """
        from strategy.setup_ranges import resolve_ranges
        _car_name = (self._build_setup_inputs().car or "") if hasattr(self, "_build_setup_inputs") else ""
        _ranges = resolve_ranges(_car_name)

        def _set_int(spin, param, val):
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            spin.setRange(int(lo), int(hi))
            _set_spin_readonly(spin, lo >= hi)
            spin.setValue(max(int(lo), min(int(hi), int(round(val)))))

        def _set_dbl(spin, param, val):
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            spin.setRange(float(lo), float(hi))
            _set_spin_readonly(spin, lo >= hi)
            spin.setValue(max(float(lo), min(float(hi), float(val))))

        _set_int(form._setup_rh_f,       "ride_height_front",  rec.ride_height_front)
        _set_int(form._setup_rh_r,       "ride_height_rear",   rec.ride_height_rear)
        _set_dbl(form._setup_spr_f,      "springs_front",      rec.springs_front)
        _set_dbl(form._setup_spr_r,      "springs_rear",       rec.springs_rear)
        _set_int(form._setup_dmp_f_comp, "dampers_front_comp", rec.dampers_front_comp)
        _set_int(form._setup_dmp_f_ext,  "dampers_front_ext",  rec.dampers_front_ext)
        _set_int(form._setup_dmp_r_comp, "dampers_rear_comp",  rec.dampers_rear_comp)
        _set_int(form._setup_dmp_r_ext,  "dampers_rear_ext",   rec.dampers_rear_ext)
        _set_int(form._setup_arb_f,      "arb_front",          rec.arb_front)
        _set_int(form._setup_arb_r,      "arb_rear",           rec.arb_rear)
        _set_dbl(form._setup_cam_f,      "camber_front",       rec.camber_front)
        _set_dbl(form._setup_cam_r,      "camber_rear",        rec.camber_rear)
        _set_dbl(form._setup_toe_f,      "toe_front",          rec.toe_front)
        _set_dbl(form._setup_toe_r,      "toe_rear",           rec.toe_rear)
        _set_int(form._setup_aero_f,     "aero_front",         rec.aero_front)
        _set_int(form._setup_aero_r,     "aero_rear",          rec.aero_rear)
        _set_int(form._setup_lsd_i,      "lsd_initial",        rec.lsd_initial)
        _set_int(form._setup_lsd_a,      "lsd_accel",          rec.lsd_accel)
        _set_int(form._setup_lsd_d,      "lsd_decel",          rec.lsd_decel)
        _set_int(form._setup_lsd_f_i,    "lsd_front_initial",  rec.lsd_front_initial)
        _set_int(form._setup_lsd_f_a,    "lsd_front_accel",    rec.lsd_front_accel)
        _set_int(form._setup_lsd_f_d,    "lsd_front_decel",    rec.lsd_front_decel)
        _set_int(form._setup_bb,         "brake_bias",         rec.brake_bias)
        _set_dbl(form._setup_ballast_kg, "ballast_kg",         rec.ballast_kg)
        _set_int(form._setup_ballast_pos,"ballast_position",   rec.ballast_position)
        _set_dbl(form._setup_power_rest, "power_restrictor",   rec.power_restrictor)
        if hasattr(rec, "ecu_recommendation") and rec.ecu_recommendation:
            form._lbl_ecu_rec.setText(rec.ecu_recommendation)
        else:
            form._lbl_ecu_rec.setText("—")
        if rec.final_drive > 0.0:
            form._spin_final_drive.setValue(rec.final_drive)
        for i, spin in enumerate(form._gear_ratio_spins):
            spin.setValue(rec.gear_ratios[i] if i < len(rec.gear_ratios) else 0.0)
        if rec.transmission_max_speed_kmh > 0:
            form._spin_top_speed.setValue(rec.transmission_max_speed_kmh)
        form._build_setup_result.setHtml(
            f"<b>AI Setup Reasoning ({form.purpose})</b><br>"
            f"<p style='line-height:1.5;'>{rec.reasoning}</p>"
        )
        form._build_setup_result.setVisible(True)

    def _sync_qual_form_ui_state(self) -> None:
        """Sync the Qualifying form's BOP/locked/permissions state from the Race form.

        Called from ``_sync_setup_builder_from_event`` after the Race-form state
        is updated via the aliased self attrs.  Ensures the Qualifying panel's
        UI widgets reflect the same event constraints.
        """
        if not hasattr(self, "_qual_form"):
            return
        qf = self._qual_form
        rf = self._race_form
        # BOP row visibility (controlled by _on_bop_toggled which only updates
        # the aliased Race-form widgets through self)
        for _src, _dst in (
            ("_lbl_bop_info",       "_lbl_bop_info"),
            ("_btn_bop_edit",       "_btn_bop_edit"),
            ("_btn_bop_reload",     "_btn_bop_reload"),
            ("_bop_info_row_label", "_bop_info_row_label"),
        ):
            src_w = getattr(rf, _src, None)
            dst_w = getattr(qf, _dst, None)
            if src_w is not None and dst_w is not None:
                dst_w.setVisible(src_w.isVisible())
                if hasattr(src_w, "text"):
                    dst_w.setText(src_w.text())
        # Locked banner
        if hasattr(rf, "_setup_locked_banner") and hasattr(qf, "_setup_locked_banner"):
            qf._setup_locked_banner.setText(rf._setup_locked_banner.text())
            if rf._setup_locked_banner.isVisible():
                qf._setup_locked_banner.show()
            else:
                qf._setup_locked_banner.hide()

    def _sync_setup_builder_from_event(self) -> None:
        # Amendment B: _lbl_rc_* readout labels were removed from _build_setup_builder_tab.
        # This method now only updates _lbl_setup_event_ctx and runs all functional
        # side effects (BoP toggle, setup permissions, spinbox rebind, RE brief, qual sync).
        # The _lbl_rc_* hasattr guards below are retained as defensive checks so older
        # widget trees (e.g. tests that instantiate a partial UI) are not broken.
        try:
            evt = self._active_event()
            if not evt:
                if hasattr(self, "_lbl_setup_event_ctx"):
                    self._lbl_setup_event_ctx.setText(
                        "No active event — go to Event Planner and click 'Set as Active' first."
                    )
                return
            # Legacy Fan-Out Removal Phase 2+: the READOUT labels that were in
            # the (now-removed) Race Conditions group are gone. The canonical
            # EventContext is still read here for all functional gating.
            ev_ctx = self._build_event_context()
            name  = evt.get("name", "?")
            track = ev_ctx.track or "?"
            car   = ev_ctx.car or "—"

            if hasattr(self, "_lbl_setup_event_ctx"):
                self._lbl_setup_event_ctx.setText(
                    f"Active Event: {name}  |  Track: {track}  |  Car: {car}"
                )
            # Refresh the structured setup-name suggestion for the active event.
            if hasattr(self, "_setup_label"):
                self._prefill_setup_label()

            # Legacy Fan-Out Removal Phase 3 (functional gating): the BoP toggle
            # and setup-permission gating now read the canonical EventContext
            # (DB-event-first — consistent with the AI inputs, the Phase 2 labels,
            # and the DEF-P3-012 validation). Byte-identical when the DB event and
            # the config["strategy"] fan-out are in sync; when an event was edited
            # + Saved but not re-activated, the editable fields now follow the
            # fresh DB truth (the intended, signed-off behaviour change).
            _bop    = ev_ctx.bop_enabled
            _tuning = ev_ctx.tuning_allowed
            _cats   = list(ev_ctx.allowed_tuning_categories)
            self._on_bop_toggled(_bop)
            self._apply_setup_permissions(_bop, _tuning, _cats)
            self._refresh_live_tyre_label()
            # Re-bound spinboxes for the new car and load race engineer brief.
            # Phase 4: car via EventContext (strategy-first there and events
            # never store a car — byte-identical, proven in Phase 1 tests).
            self._rebound_setup_spinboxes(ev_ctx.car or "")
            self._load_re_brief_from_active_event()
            # Sync the Qualifying form's BOP/locked state from the Race-aliased widgets
            self._sync_qual_form_ui_state()
        except Exception:
            pass

    def _build_setup_builder_tab(self) -> QWidget:
        # Outer container: VBox holding the header strip (scrollable) + the
        # side-by-side form panel (expands to fill the tab, scrolls per-form).
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setSpacing(6)
        tab_layout.setContentsMargins(6, 6, 6, 6)

        # ── Header strip (event ctx banner + history) — scrollable ──
        # Amendment B: the "Race Conditions (from Event Planner)" group box was
        # removed (12 _lbl_rc_* QLabels deleted).  The _lbl_setup_event_ctx
        # one-line banner and the Setup History group are retained.
        header_scroll = QScrollArea()
        header_scroll.setWidgetResizable(True)
        # Amendment B: removed setMaximumHeight(320) cap — reclaimed space flows
        # to the setup panel below.
        header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header_container = QWidget()
        layout = QVBoxLayout(header_container)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        self._lbl_setup_event_ctx = QLabel("No active event — go to Event Planner and click 'Set as Active' first.")
        self._lbl_setup_event_ctx.setWordWrap(True)
        self._lbl_setup_event_ctx.setStyleSheet("color: #F5C542; font-size: 11px; padding: 4px;")
        layout.addWidget(self._lbl_setup_event_ctx)

        history_group = QGroupBox("Setup History")
        history_group.setStyleSheet(self._group_style())
        history_h = QHBoxLayout(history_group)
        history_h.addWidget(QLabel("Past AI iteration:"))
        self._setup_history_combo = QComboBox()
        self._setup_history_combo.setMinimumWidth(300)
        self._setup_history_combo.setToolTip("Select a past AI setup iteration to review")
        self._setup_history_combo.currentIndexChanged.connect(self._on_setup_history_selected)
        history_h.addWidget(self._setup_history_combo)
        btn_refresh_hist = QPushButton("Refresh")
        btn_refresh_hist.setStyleSheet(
            "QPushButton { background: #2A2A2A; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background: #3A3A3A; }"
        )
        btn_refresh_hist.clicked.connect(self._refresh_setup_history_combo)
        history_h.addWidget(btn_refresh_hist)
        history_h.addStretch()
        layout.addWidget(history_group)
        layout.addStretch()

        header_scroll.setWidget(header_container)
        tab_layout.addWidget(header_scroll, 0)  # fixed height

        # ── Side-by-side setup panel — expands to fill remaining space ─────────
        setup_panel = self._build_car_setup_group()

        # UAT Finding 3: the structured recommendation surface (header + tabbed
        # Recommendation/Why/Practice Analysis/Test Plan/Advanced + action bar),
        # replacing the text-box-first design. Shown once a recommendation
        # exists; sits in a vertical splitter with the editor forms.
        from ui.setup_recommendation_view import SetupRecommendationView
        self._setup_rec_view = SetupRecommendationView()
        self._setup_rec_view.setVisible(False)
        self._wire_setup_rec_view()

        _rec_split = QSplitter(Qt.Orientation.Vertical)
        _rec_split.addWidget(setup_panel)
        _rec_split.addWidget(self._setup_rec_view)
        # DEF-UAT-073-007/017: when a recommendation is present it should be readable, not a squished strip.
        # The rec pane gets the larger share; while hidden the setup form keeps all the height. The user can
        # still drag the splitter. Sizes are (re)applied in _populate_setup_recommendation_view.
        _rec_split.setStretchFactor(0, 3)
        _rec_split.setStretchFactor(1, 5)
        _rec_split.setCollapsible(1, True)
        self._rec_split = _rec_split
        tab_layout.addWidget(_rec_split, 1)  # stretch factor 1

        return tab_widget

    # ------------------------------------------------------------------ #
    # UAT Finding 3 — structured recommendation view wiring.
    # ------------------------------------------------------------------ #

    def _wire_setup_rec_view(self) -> None:
        v = self._setup_rec_view
        v.apply_in_game.connect(lambda: self._rec_view_apply_in_game())
        v.values_entered.connect(lambda: self._rec_view_values_entered())
        v.start_validation.connect(lambda: self._rec_view_start_validation())
        v.submit_feedback.connect(lambda: self._rec_view_submit_feedback())
        v.reject_recommendation.connect(lambda: self._rec_view_reject())
        v.accept_and_lock.connect(lambda: self._rec_view_accept_and_lock())

    def _populate_setup_recommendation_view(self, data: dict, status_approved: bool) -> None:
        """Build the structured VM from the recommendation payload and render it.

        Called at generate time from ``_display_setup_result`` so proposed
        changes highlight immediately — clicking "Applied in Game" later only
        flips the status, it is not what first highlights a field.
        """
        view = getattr(self, "_setup_rec_view", None)
        if view is None:
            return
        from ui.setup_recommendation_vm import build_recommendation_vm, HeaderInfo
        ev = self._build_event_context()
        active = ""
        if hasattr(self, "_active_setup_for_current"):
            a = self._active_setup_for_current("Race")
            if a is not None:
                active = a.label()
        name = ""
        try:
            name = self._race_form._setup_label.text().strip()
        except Exception:
            name = ""
        header = HeaderInfo(
            car=str(getattr(ev, "car", "") or ""),
            track=str(getattr(ev, "track", "") or ""),
            layout=str(getattr(ev, "layout_id", "") or ""),
            setup_name=name, revision="1", active_setup=active,
        )
        vm = build_recommendation_vm(data, header=header,
                                     status_approved=status_approved)
        view.set_vm(vm)
        view.setVisible(vm.has_recommendation)
        # DEF-UAT-073-007/017: give the recommendation generous, readable height when it appears (the user
        # can still drag the splitter); collapse it back so the setup form reclaims the space when there is
        # no recommendation.
        split = getattr(self, "_rec_split", None)
        if split is not None:
            try:
                total = max(split.height(), 600)
                if vm.has_recommendation:
                    split.setSizes([int(total * 0.42), int(total * 0.58)])
                else:
                    split.setSizes([total, 0])
            except Exception:
                pass

    def _rec_view_apply_in_game(self) -> None:
        form = getattr(self, "_race_form", None)
        if form is not None:
            self._on_changes_applied_in_game(form)
        view = getattr(self, "_setup_rec_view", None)
        if view is not None:
            view.mark_applied()
            # DEF-UAT-073-009: visible confirmation — the action previously only reached the event log.
            view.show_action_feedback("✓ Applied in game — marked as the active setup baseline.")

    def _rec_view_values_entered(self) -> None:
        try:
            self._bridge.event_log_entry.emit(
                "[Setup] Recommended values entered in GT7 (awaiting on-track confirmation).")
        except Exception:
            pass
        view = getattr(self, "_setup_rec_view", None)
        if view is not None:
            view.show_action_feedback("✓ Values entered — awaiting on-track confirmation.", "info")

    def _rec_view_start_validation(self) -> None:
        auth = getattr(self, "_setup_authority", None)
        if auth is not None and hasattr(self, "_current_setup_identity"):
            try:
                auth.start_validation(self._current_setup_identity(), "Race")
                if hasattr(self, "_refresh_active_setup_display"):
                    self._refresh_active_setup_display()
            except Exception:
                pass
        try:
            self._bridge.event_log_entry.emit(
                "[Setup] Validation started — run the test plan laps.")
        except Exception:
            pass
        view = getattr(self, "_setup_rec_view", None)
        if view is not None:
            if hasattr(view, "mark_validation_started"):
                view.mark_validation_started()
            view.show_action_feedback("✓ Validation started — run the test-plan laps, then submit feedback.")

    def _rec_view_submit_feedback(self) -> None:
        # Take the driver to the feedback surface (Practice Review).
        try:
            from ui.tab_registry import TAB_PRACTICE_REVIEW
            self.select_tab(TAB_PRACTICE_REVIEW)
        except Exception:
            pass

    def _rec_view_reject(self) -> None:
        view = getattr(self, "_setup_rec_view", None)
        if view is not None:
            view.setVisible(False)
        try:
            self._bridge.event_log_entry.emit("[Setup] Recommendation rejected by driver.")
        except Exception:
            pass

    def _rec_view_accept_and_lock(self) -> None:
        """Lock the current setup in as the confirmed baseline (ACCEPTED state)."""
        auth = getattr(self, "_setup_authority", None)
        locked = None
        if auth is not None and hasattr(self, "_current_setup_identity"):
            try:
                ident = self._current_setup_identity()
                # Ensure it's applied first, then accept -> ACCEPTED baseline.
                active = auth.active_setup(ident, "Race")
                if active is None:
                    # Nothing applied yet — apply the current form, then accept.
                    self._on_changes_applied_in_game(getattr(self, "_race_form", None))
                auth.start_validation(ident, "Race")
                locked = auth.accept(ident, "Race")
                if hasattr(self, "_refresh_active_setup_display"):
                    self._refresh_active_setup_display()
            except Exception as e:
                print(f"[Setup] accept/lock error: {e}")
        try:
            if locked is not None:
                self._bridge.event_log_entry.emit(
                    f"[Setup] Locked in as confirmed baseline: {locked.label()} "
                    f"(Accepted).")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "Setup locked in",
                    f"“{locked.name}” (rev {locked.revision}) is now your confirmed "
                    "baseline for this car, track and layout.")
            else:
                self._bridge.event_log_entry.emit(
                    "[Setup] Could not lock setup — apply a setup in game first.")
        except Exception:
            pass

    def _refresh_setup_history_combo(self) -> None:
        try:
            config_id    = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
            history_path = Path(__file__).parent.parent / "data" / "setup_history.json"
            if not history_path.exists():
                self._setup_history_combo.clear()
                return
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get(config_id, [])
            self._setup_history_combo.blockSignals(True)
            self._setup_history_combo.clear()
            for i, entry in enumerate(reversed(entries)):
                self._setup_history_combo.addItem(entry.get("timestamp", f"Entry {i + 1}"))
            self._setup_history_combo.blockSignals(False)
        except Exception:
            try:
                self._setup_history_combo.clear()
            except Exception:
                pass

    def _on_setup_history_selected(self, index: int) -> None:
        if index < 0:
            return
        try:
            config_id    = self._active_config_id()  # Phase 1: StrategyContext, not raw config["strategy"]
            history_path = Path(__file__).parent.parent / "data" / "setup_history.json"
            if not history_path.exists():
                return
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = list(reversed(data.get(config_id, [])))
            if index >= len(entries):
                return
            text = entries[index].get("reasoning", entries[index].get("analysis", "No details available."))
            result_widget = getattr(self, "_build_setup_result", None)
            if result_widget is not None:
                result_widget.setPlainText(text)
                result_widget.setVisible(True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Story 4 — field highlight helpers
    # ------------------------------------------------------------------

    # Param key → widget attribute name mapping (mirrors _rebound_setup_spinboxes _PARAM_MAP).
    _HIGHLIGHT_PARAM_MAP: dict[str, str] = {
        "ride_height_front":  "_setup_rh_f",
        "ride_height_rear":   "_setup_rh_r",
        "springs_front":      "_setup_spr_f",
        "springs_rear":       "_setup_spr_r",
        "dampers_front_comp": "_setup_dmp_f_comp",
        "dampers_front_ext":  "_setup_dmp_f_ext",
        "dampers_rear_comp":  "_setup_dmp_r_comp",
        "dampers_rear_ext":   "_setup_dmp_r_ext",
        "arb_front":          "_setup_arb_f",
        "arb_rear":           "_setup_arb_r",
        "camber_front":       "_setup_cam_f",
        "camber_rear":        "_setup_cam_r",
        "toe_front":          "_setup_toe_f",
        "toe_rear":           "_setup_toe_r",
        "aero_front":         "_setup_aero_f",
        "aero_rear":          "_setup_aero_r",
        "lsd_initial":        "_setup_lsd_i",
        "lsd_accel":          "_setup_lsd_a",
        "lsd_decel":          "_setup_lsd_d",
        "lsd_front_initial":  "_setup_lsd_f_i",
        "lsd_front_accel":    "_setup_lsd_f_a",
        "lsd_front_decel":    "_setup_lsd_f_d",
        "brake_bias":         "_setup_bb",
        "ballast_kg":         "_setup_ballast_kg",
        "ballast_position":   "_setup_ballast_pos",
        "power_restrictor":   "_setup_power_rest",
    }

    _HIGHLIGHT_STYLE = "background:#2A4A2A; border:1px solid #8BC34A;"

    def _highlight_changed_fields(self, field_names: list[str]) -> None:
        """Highlight spinboxes for the given param keys with a green tint.

        Clears any previous highlights first so re-applying replaces cleanly.
        """
        self._clear_setup_highlights()
        _highlighted: set[str] = getattr(self, "_highlighted_fields", set())
        for key in field_names:
            attr = self._HIGHLIGHT_PARAM_MAP.get(key)
            if attr is None:
                continue
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            widget.setStyleSheet(self._HIGHLIGHT_STYLE)
            _highlighted.add(key)
        self._highlighted_fields = _highlighted

    def _clear_setup_highlights(self) -> None:
        """Remove highlight styling from all currently-highlighted spinboxes."""
        _highlighted: set[str] = getattr(self, "_highlighted_fields", set())
        for key in list(_highlighted):
            attr = self._HIGHLIGHT_PARAM_MAP.get(key)
            if attr is None:
                continue
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            widget.setStyleSheet("")
        self._highlighted_fields = set()

    # ------------------------------------------------------------------
    # Task 1 — spinbox re-bounding slot
    # ------------------------------------------------------------------

    def _rebound_setup_spinboxes(self, car_name: str | None = None) -> None:
        """Re-apply per-car (min,max) to every in-scope setup spinbox.

        Called when the active car changes (via _sync_setup_builder_from_event /
        autofill) and after saving car ranges.  Must NOT trigger an AI call.
        """
        _car = (car_name or "").strip() or self._config.get("strategy", {}).get("car", "") or ""
        _ranges = resolve_ranges(_car)

        # Map: (param_key, spinbox_attr, is_double)
        _PARAM_MAP = [
            ("ride_height_front",  "_setup_rh_f",       False),
            ("ride_height_rear",   "_setup_rh_r",       False),
            ("springs_front",      "_setup_spr_f",      True),
            ("springs_rear",       "_setup_spr_r",      True),
            ("dampers_front_comp", "_setup_dmp_f_comp", False),
            ("dampers_front_ext",  "_setup_dmp_f_ext",  False),
            ("dampers_rear_comp",  "_setup_dmp_r_comp", False),
            ("dampers_rear_ext",   "_setup_dmp_r_ext",  False),
            ("arb_front",          "_setup_arb_f",      False),
            ("arb_rear",           "_setup_arb_r",      False),
            ("camber_front",       "_setup_cam_f",      True),
            ("camber_rear",        "_setup_cam_r",      True),
            ("toe_front",          "_setup_toe_f",      True),
            ("toe_rear",           "_setup_toe_r",      True),
            ("aero_front",         "_setup_aero_f",     False),
            ("aero_rear",          "_setup_aero_r",     False),
            ("lsd_initial",        "_setup_lsd_i",      False),
            ("lsd_accel",          "_setup_lsd_a",      False),
            ("lsd_decel",          "_setup_lsd_d",      False),
            ("lsd_front_initial",  "_setup_lsd_f_i",    False),
            ("lsd_front_accel",    "_setup_lsd_f_a",    False),
            ("lsd_front_decel",    "_setup_lsd_f_d",    False),
            ("brake_bias",         "_setup_bb",         False),
            ("ballast_kg",         "_setup_ballast_kg", True),
            ("ballast_position",   "_setup_ballast_pos",False),
            ("power_restrictor",   "_setup_power_rest", True),
        ]

        for param, attr, is_dbl in _PARAM_MAP:
            spin = getattr(self, attr, None)
            if spin is None:
                continue
            lo, hi = _ranges.get(param, (spin.minimum(), spin.maximum()))
            if is_dbl:
                lo, hi = float(lo), float(hi)
                spin.setRange(lo, hi)
                cur = spin.value()
                spin.setValue(max(lo, min(hi, cur)))
            else:
                lo, hi = int(lo), int(hi)
                spin.setRange(lo, hi)
                cur = spin.value()
                spin.setValue(max(lo, min(hi, cur)))
            # Read-only when min==max (parameter not adjustable on this car)
            _set_spin_readonly(spin, lo >= hi)

    # ------------------------------------------------------------------
    # Task 2 — "Set Car Ranges…" dialog
    # ------------------------------------------------------------------

    def _open_car_ranges_dialog(self) -> None:
        """Open the CarRangesDialog for the currently active car."""
        car_name = self._config.get("strategy", {}).get("car", "") or ""
        dlg = CarRangesDialog(car_name, self)
        dlg.ranges_saved.connect(self._rebound_setup_spinboxes)
        dlg.exec()

    # ------------------------------------------------------------------
    # Task 3 — Race Engineer Brief visibility + persistence helpers
    # ------------------------------------------------------------------

    def _on_setup_type_changed(self, session_type_text: str = "") -> None:
        """Write _practice_is_qual_ref[0] when the Setup-tab session type changes.

        The ref is read by on_packet in main.py to select the correct shift RPM
        threshold when the live mode is Practice.  Guard with hasattr since tests
        may construct the window before main() injects the ref.
        """
        is_qual = "qual" in (session_type_text or "").lower()
        if hasattr(self, "_practice_is_qual_ref"):
            import main
            with main._state_lock:
                self._practice_is_qual_ref[0] = is_qual
        # Regenerate the structured setup-name suggestion for the new Q/R prefix.
        if hasattr(self, "_setup_label"):
            self._prefill_setup_label()

    def _update_re_brief_visibility(self, session_type_text: str = "") -> None:
        """Show Race Engineer Brief for race sessions; hide for Qualifying."""
        is_qual = "qual" in (session_type_text or "").lower()
        for w in (getattr(self, "_re_brief_label", None),
                  getattr(self, "_re_brief_input", None)):
            if w is not None:
                w.setVisible(not is_qual)

    def _load_re_brief_from_active_event(self) -> None:
        """Populate _re_brief_input from the active event's race_engineer_brief."""
        if not hasattr(self, "_re_brief_input"):
            return
        evt = self._active_event() if hasattr(self, "_active_event") else {}
        brief = evt.get("race_engineer_brief", "") or ""
        self._re_brief_input.blockSignals(True)
        self._re_brief_input.setPlainText(brief)
        self._re_brief_input.blockSignals(False)

    def _save_re_brief_to_active_event(self) -> None:
        """Write _re_brief_input text into the active event in config and persist."""
        if not hasattr(self, "_re_brief_input"):
            return
        aid = self._config.get("active_event_id")
        if not aid:
            return
        brief = self._re_brief_input.toPlainText() or ""
        # Update in config["events"]
        for evt in self._config.get("events", []):
            if evt.get("name") == aid:
                evt["race_engineer_brief"] = brief
                break
        # Also update in DB if available
        if self._db is not None:
            try:
                existing = self._db.get_event(aid)
                if existing:
                    existing["race_engineer_brief"] = brief
                    self._db.upsert_event(existing)
            except Exception as _e:
                print(f"[SetupBuilder] re_brief DB save failed: {_e}")
        self._persist_config()
