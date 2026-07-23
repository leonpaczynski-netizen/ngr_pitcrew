"""HomePage — the "what should I do next?" landing surface (UAT-2 remediation).

The first Home was a title and a subtitle and nothing else, which told the driver
nothing. This renders the read-only Event Command Centre view the domain already
produces: the active event identity and countdown, the recommended next action,
readiness per dimension, anything demanding attention, and the evidence tally —
plus the event controls (switch the active event / manage events) that the new
shell previously had no route to at all.

It computes nothing. Every number, level and sentence comes from the command-centre
view dict (``SessionDB.build_event_command_centre_view``) or ``AppState``; when the
view is missing the page says so instead of inventing a state.
"""

from __future__ import annotations

from typing import Mapping, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea, QFrame,
)

from ui import ngr_theme as _t
from ui.app_state import AppState
from ui.components.cards import Card, SectionHeading
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton


#: Command-centre readiness level -> (display label, colour token).
_LEVEL_TONE = {
    "ready": (_t.SUCCESS, "Ready"),
    "developing": (_t.WARN, "Developing"),
    "thin": (_t.WARN, "Thin"),
    "missing": (_t.DANGER, "No runs yet"),
    "blocked": (_t.DANGER, "Blocked"),
    "unknown": (_t.TEXT_DIM, "Unknown"),
}

#: Resolution state -> the plain sentence the driver actually needs.
_RESOLUTION_TEXT = {
    "no_active_event": "No active event. Create one, or activate an existing event below.",
    "one_active_event": "",
    "multiple_active_events": "Several events are open — pick the one you are preparing.",
    "upcoming_event": "This event has not opened for preparation yet.",
    "paused_event": "Preparation on this event is paused.",
    "event_requires_selection": "Several events could be active — choose one to continue.",
    "event_context_changed": "The event details changed since preparation started — re-check the brief.",
    "event_blocked": "This event is blocked; resolve the blocker before preparing.",
}


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


class _Row(QLabel):
    """One dim caption line."""

    def __init__(self, text: str = "", colour: str = "", size: int = _t.FS_LABEL, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setStyleSheet(f"color: {colour or _t.TEXT_DIM}; font-size: {size}pt;")


class HomePage(QWidget):
    """The guided landing page: state of the event + the one next thing to do."""

    #: Navigate to a nav destination (already mapped by the caller's SURFACE_TO_NAV).
    navigate_requested = pyqtSignal(str)
    #: Activate a different event — carries the candidate's event_name (may be "").
    event_activate_requested = pyqtSignal(str)
    #: Open the full event editor (create / edit / delete an event).
    manage_events_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrHomePage")
        self._candidates: list[dict] = []
        self._primary_surface = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)
        scroll.setWidget(inner)

        lay.addWidget(SectionHeading("HOME", level=1))

        # ---- the event card (identity, countdown, switch/manage) -------------
        self._event_card = Card()
        self._event_title = QLabel("No active event")
        self._event_title.setWordWrap(True)
        self._event_title.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H2}pt; font-weight: 700;")
        self._event_card.add(self._event_title)
        self._event_sub = _Row("")
        self._event_card.add(self._event_sub)
        self._event_state = _Row("", _t.WARN, _t.FS_CAPTION)
        self._event_card.add(self._event_state)

        ev_row = QHBoxLayout()
        ev_row.setSpacing(_t.SPACE_SM)
        self._event_combo = QComboBox()
        self._event_combo.setMinimumWidth(240)
        self._event_combo.setMinimumHeight(_t.TOUCH_MIN_H)
        self._event_combo.setStyleSheet(
            f"QComboBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
            f"padding: 4px 10px; font-size: {_t.FS_LABEL}pt; }}"
        )
        ev_row.addWidget(self._event_combo)
        self._btn_switch = SecondaryActionButton("Switch to this event")
        self._btn_switch.clicked.connect(self._on_switch)
        ev_row.addWidget(self._btn_switch)
        self._btn_manage = SecondaryActionButton("Create / edit events")
        self._btn_manage.clicked.connect(lambda: self.manage_events_requested.emit())
        ev_row.addWidget(self._btn_manage)
        ev_row.addStretch(1)
        self._event_card.body.addLayout(ev_row)
        lay.addWidget(self._event_card)

        # ---- next action -----------------------------------------------------
        self._next_card = Card()
        self._next_card.add(SectionHeading("DO THIS NEXT", level=3))
        self._next_headline = QLabel("")
        self._next_headline.setWordWrap(True)
        self._next_headline.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt; font-weight: 600;")
        self._next_card.add(self._next_headline)
        self._next_detail = _Row("")
        self._next_card.add(self._next_detail)
        self._btn_next = PrimaryActionButton()
        self._btn_next.clicked.connect(
            lambda: self._primary_surface and self.navigate_requested.emit(self._primary_surface))
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._btn_next)
        btn_row.addStretch(1)
        self._next_card.body.addLayout(btn_row)
        lay.addWidget(self._next_card)

        # ---- attention -------------------------------------------------------
        self._attention_card = Card()
        self._attention_card.add(SectionHeading("NEEDS ATTENTION", level=3))
        self._attention = _Row("", _t.WARN)
        self._attention_card.add(self._attention)
        lay.addWidget(self._attention_card)

        # ---- readiness -------------------------------------------------------
        self._readiness_card = Card()
        self._readiness_card.add(SectionHeading("READINESS", level=3))
        self._readiness_box = QVBoxLayout()
        self._readiness_box.setSpacing(_t.SPACE_XS)
        self._readiness_card.body.addLayout(self._readiness_box)
        lay.addWidget(self._readiness_card)

        # ---- evidence --------------------------------------------------------
        self._evidence_card = Card()
        self._evidence_card.add(SectionHeading("EVIDENCE SO FAR", level=3))
        self._evidence = _Row("")
        self._evidence_card.add(self._evidence)
        self._learning = _Row("", _t.TEXT, _t.FS_CAPTION)
        self._evidence_card.add(self._learning)
        lay.addWidget(self._evidence_card)

        lay.addStretch(1)
        self.render(None, None)

    # ---- population -------------------------------------------------------
    def render(self, app_state: Optional[AppState], view: Optional[Mapping]) -> None:
        """Render AppState + the command-centre view. Never raises.

        The live bridge refreshes several times a second. Re-running the render on an
        unchanged state would rebuild the event combo under the driver's cursor (the
        same class of bug as the Garage discipline selector resetting), so an
        equivalent state is a no-op.
        """
        try:
            key = self._render_key(app_state, view)
            if key == self._render_key_cache:
                return
            self._render_key_cache = key
            self._render(app_state, view)
        except Exception:  # pragma: no cover - the shell must never die rendering
            pass

    _render_key_cache: object = object()

    @staticmethod
    def _render_key(app_state, view):
        """A cheap equality key: the domain fingerprint plus the display-only bits
        the fingerprint deliberately excludes."""
        v = view if isinstance(view, Mapping) else {}
        return (
            app_state if isinstance(app_state, AppState) else None,
            _norm(v.get("fingerprint")),
            _norm(v.get("resolution_state")),
            v.get("days_until_race"),
            bool(v.get("ok", True)) if v else False,
        )

    def _render(self, app_state: Optional[AppState], view: Optional[Mapping]) -> None:
        if not isinstance(app_state, AppState):
            app_state = AppState.empty()
        has_view = isinstance(view, Mapping) and bool(view.get("ok", True))

        # -- event identity
        if app_state.has_active_event:
            self._event_title.setText(app_state.event_name or "Active event")
            self._event_sub.setText(f"{app_state.car} · {app_state.track}")
        elif has_view and _norm((view.get("event") or {}).get("event_name")):
            ident = view.get("event") or {}
            self._event_title.setText(_norm(ident.get("event_name")))
            self._event_sub.setText(
                " · ".join(p for p in (_norm(ident.get("series")), _norm(ident.get("round")),
                                       _norm(ident.get("current_phase"))) if p))
        else:
            self._event_title.setText("No active event")
            self._event_sub.setText(
                "Activate an event below, or create one, before preparing a setup.")

        state_bits = []
        if has_view:
            days = view.get("days_until_race")
            if isinstance(days, int):
                state_bits.append(
                    "Race day" if days == 0 else
                    f"{days} day{'s' if days != 1 else ''} to race" if days > 0 else
                    f"{abs(days)} day{'s' if abs(days) != 1 else ''} since the race")
            note = _RESOLUTION_TEXT.get(_norm(view.get("resolution_state")).lower(), "")
            if note:
                state_bits.append(note)
        elif not app_state.has_active_event:
            state_bits.append("No event programme loaded yet.")
        self._event_state.setText("   ·   ".join(state_bits))
        self._event_state.setVisible(bool(state_bits))

        # -- candidates (the event switcher)
        cands = list(view.get("candidates") or []) if has_view else []
        self._candidates = [c for c in cands if isinstance(c, Mapping)]
        self._event_combo.clear()
        for c in self._candidates:
            label = _norm(c.get("event_name")) or _norm(c.get("cycle_id"))
            extra = " · ".join(p for p in (_norm(c.get("series")), _norm(c.get("round"))) if p)
            self._event_combo.addItem(f"{label} — {extra}" if extra else label)
        have_candidates = bool(self._candidates)
        self._event_combo.setVisible(have_candidates)
        self._btn_switch.setVisible(have_candidates)
        self._btn_switch.setEnabled(have_candidates)

        # -- next action
        na = (view.get("next_action") or {}) if has_view else {}
        headline = _norm(na.get("headline"))
        detail = _norm(na.get("detail"))
        self._primary_surface = _norm(na.get("target_surface"))
        # An evidence objective is satisfied by driving and recording a run, so it routes
        # to Practice — matching the guidance card, never back to the surface the driver
        # is already on. See ui.components.guidance_vm for the full reasoning.
        from ui.components.guidance_vm import evidence_domain_in, _EVIDENCE_RUN
        domain = evidence_domain_in(headline)
        if domain:
            run_name, cta = _EVIDENCE_RUN[domain]
            self._primary_surface = "practice"
            detail = (detail + "  " if detail else "") + \
                f"Evidence for this comes from a recorded {run_name} — nothing else builds it."
            headline = cta
        if not headline:
            headline = ("Activate an event to get a plan."
                        if not app_state.has_active_event else "Nothing outstanding.")
            detail = ""
        self._next_headline.setText(headline)
        self._next_detail.setText(detail)
        self._next_detail.setVisible(bool(detail))
        if self._primary_surface:
            self._btn_next.set_action(headline, enabled=True)
        else:
            self._btn_next.set_action("", enabled=False)

        # -- attention
        from ui.components.guidance_vm import _plain_attention
        msgs = []
        for item in (view.get("attention") or []) if has_view else []:
            if isinstance(item, Mapping):
                m = _plain_attention(_norm(item.get("message")))
                if m:
                    msgs.append(m)
        self._attention.setText("\n".join(f"⚠  {m}" for m in msgs))
        self._attention_card.setVisible(bool(msgs))

        # -- readiness
        while self._readiness_box.count():
            item = self._readiness_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        dims = list(view.get("readiness") or []) if has_view else []
        for dim in dims:
            try:
                name, level, note = (list(dim) + ["", "", ""])[:3]
            except Exception:
                continue
            colour, label = _LEVEL_TONE.get(_norm(level).lower(), (_t.TEXT_DIM, _norm(level) or "—"))
            row = QHBoxLayout()
            row.setSpacing(_t.SPACE_SM)
            n = QLabel(_norm(name).replace("_", " ").title())
            n.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
            n.setMinimumWidth(170)
            lvl = QLabel(label)
            lvl.setStyleSheet(f"color: {colour}; font-size: {_t.FS_LABEL}pt; font-weight: 700;")
            lvl.setMinimumWidth(90)
            # "no evidence collected" reads as a rejection; it means no run was recorded.
            note_text = _norm(note)
            if note_text == "no evidence collected":
                note_text = "no runs recorded for this yet"
            nt = QLabel(note_text)
            nt.setWordWrap(True)
            nt.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
            row.addWidget(n)
            row.addWidget(lvl)
            row.addWidget(nt, 1)
            holder = QWidget()
            holder.setLayout(row)
            self._readiness_box.addWidget(holder)
        self._readiness_card.setVisible(bool(dims))

        # -- evidence
        prog = (view.get("progress") or {}) if has_view else {}
        parts = []
        for key, singular, plural in (
            ("practice_sessions", "practice session", "practice sessions"),
            ("valid_laps", "valid lap", "valid laps"),
            ("setup_experiments", "setup experiment", "setup experiments"),
            ("tyre_samples", "tyre sample", "tyre samples"),
            ("fuel_samples", "fuel sample", "fuel samples"),
            ("race_simulations", "race sim", "race sims"),
        ):
            try:
                n = int(prog.get(key, 0) or 0)
            except (TypeError, ValueError):
                n = 0
            parts.append(f"{n} {singular if n == 1 else plural}")
        self._evidence.setText("   ·   ".join(parts) if prog else "No evidence gathered yet.")
        learning = [_norm(r) for r in (view.get("recent_learning") or []) if _norm(r)] if has_view else []
        self._learning.setText("\n".join(f"• {r}" for r in learning[:4]))
        self._learning.setVisible(bool(learning))

    # ---- signals ----------------------------------------------------------
    def _on_switch(self) -> None:
        idx = self._event_combo.currentIndex()
        if 0 <= idx < len(self._candidates):
            name = _norm(self._candidates[idx].get("event_name"))
            self.event_activate_requested.emit(name)
