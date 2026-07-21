"""Event Command Centre panel — the primary Home surface (Program 2, Phase 51).

Renders the active NGR event as the centre of the app: a status hero + ONE prominent primary action,
attention items, an explicit event selector when several cycles are open, per-dimension readiness, a
cumulative-learning card, the preparation timeline and quick-action navigation into specialist surfaces.
Read-only and advisory — NO Apply, no setup mutation, no experiment/outcome/session/lock/finalise here;
those are explicit workflows on their own surfaces. The heavy build runs OFF the Qt thread (worker +
stale-result guard); this panel renders the finished dict and shows a loading state meanwhile.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ui import ngr_theme as ngr
from ui import event_command_centre_vm as vm


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class EventCommandCentrePanel(QWidget):
    """Self-contained read-only command centre. Call :meth:`update_result` with the dict from
    ``command_centre_to_dict``. Navigation and selection are delegated to the dashboard via handlers."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("NGR Event Command Centre")
        self._on_navigate: Optional[Callable[[str], None]] = None
        self._on_select: Optional[Callable[[str], None]] = None

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("NGR Event Command Centre")
        title.setStyleSheet(ngr.heading_qss(1))
        self._root.addWidget(title)

        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setStyleSheet(ngr.banner_qss("advisory"))
        self._root.addWidget(self._header)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(ngr.SPACE_SM)
        self._root.addWidget(self._body)
        self._widgets: list = []

        self.update_result(None)

    def set_handlers(self, *, navigate: Optional[Callable[[str], None]] = None,
                     select: Optional[Callable[[str], None]] = None) -> None:
        self._on_navigate = navigate
        self._on_select = select

    @staticmethod
    def _fire(handler, arg) -> None:
        if callable(handler):
            try:
                handler(arg)
            except Exception:  # pragma: no cover - defensive; never propagate into Qt
                pass

    def update_result(self, result: Optional[dict]) -> None:
        self._clear()
        self._header.setText(vm.header_text(result))
        self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(result)))
        self._header.setAccessibleDescription(vm.header_text(result))
        if vm.is_loading(result) or vm.is_empty(result):
            # loading / no-event: the primary action still renders (create/select) when present
            na = vm.next_action_card(result)
            if na:
                self._add_card(na, heading_level=2)
            return

        # 1 — prominent primary action
        na = vm.next_action_card(result)
        if na:
            self._add_card(na, heading_level=2)
        # 2 — explicit event selector (only when several cycles are open)
        rows = vm.candidate_rows(result)
        if rows:
            self._add_selector(rows)
        # 3 — attention items
        for card in vm.attention_cards(result):
            self._add_card(card)
        # 4 — readiness grid
        self._add_readiness(vm.readiness_rows(result))
        # 5 — cumulative learning
        self._add_card(vm.progress_card(result))
        # 6 — timeline strip
        self._add_timeline(vm.timeline_nodes(result))
        # 7 — quick-action navigation
        self._add_quick_actions(vm.quick_actions(result))

    def _clear(self) -> None:
        for w in self._widgets:
            w.setParent(None)
            w.deleteLater()
        self._widgets = []

    def _add(self, w) -> None:
        self._body_layout.addWidget(w)
        self._widgets.append(w)

    def _add_card(self, card: dict, heading_level: int = 3) -> None:
        tone = card.get("tone") or "neutral"
        frame = QFrame()
        frame.setAccessibleName(f"{card.get('title')} - {card.get('status_tag') or ''}".strip(" -"))
        frame.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_SM, ngr.SPACE_MD, ngr.SPACE_SM)
        lay.setSpacing(ngr.SPACE_XS)
        hdr = QWidget(); hrow = QHBoxLayout(hdr); hrow.setContentsMargins(0, 0, 0, 0)
        htitle = QLabel(str(card.get("title") or "")); htitle.setStyleSheet(ngr.heading_qss(heading_level))
        hrow.addWidget(htitle); hrow.addStretch(1)
        has_action = bool(card.get("action_target")) and callable(self._on_navigate)
        # DEF-UAT-073-005/006: on an action card the pill badge is suppressed — it previously LOOKED like a
        # button but was an inert QLabel. The real CTA button below is the only clickable control.
        if card.get("status_tag") and not has_action:
            badge = QLabel(card["status_tag"]); badge.setStyleSheet(ngr.badge_qss(tone))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter); hrow.addWidget(badge)
        lay.addWidget(hdr)
        for ln in card.get("lines", []):
            if not str(ln).strip():
                continue
            lbl = QLabel(str(ln)); lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
            lay.addWidget(lbl)
        if has_action:
            arow = QHBoxLayout(); arow.setContentsMargins(0, ngr.SPACE_XS, 0, 0)
            btn = QPushButton(str(card.get("action_label") or "Open"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(ngr.TOUCH_MIN_H)
            btn.setStyleSheet(ngr.primary_button_qss() if heading_level <= 2 else ngr.secondary_button_qss())
            target = card.get("action_target")
            btn.clicked.connect(lambda _=False, t=target: self._fire(self._on_navigate, t))
            arow.addStretch(1); arow.addWidget(btn)
            lay.addLayout(arow)
        self._add(frame)

    def _add_selector(self, rows) -> None:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border('warn')}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_SM, ngr.SPACE_MD, ngr.SPACE_SM)
        t = QLabel("Select the active NGR event"); t.setStyleSheet(ngr.heading_qss(3)); lay.addWidget(t)
        for row in rows:
            r = QWidget(); rr = QHBoxLayout(r); rr.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(f"{row.get('label')}  [{row.get('state')}]  {row.get('race_date') or ''}")
            lbl.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
            rr.addWidget(lbl); rr.addStretch(1)
            btn = QPushButton("Select")
            cid = row.get("cycle_id")
            btn.clicked.connect(lambda _=False, c=cid: self._fire(self._on_select, c))
            rr.addWidget(btn)
            lay.addWidget(r)
        self._add(frame)

    def _add_readiness(self, rows) -> None:
        if not rows:
            return
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border('info')}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_SM, ngr.SPACE_MD, ngr.SPACE_SM)
        t = QLabel("Engineering Readiness"); t.setStyleSheet(ngr.heading_qss(3)); lay.addWidget(t)
        for row in rows:
            r = QWidget(); rr = QHBoxLayout(r); rr.setContentsMargins(0, 0, 0, 0)
            name = QLabel(str(row.get("name"))); name.setStyleSheet(f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
            rr.addWidget(name); rr.addStretch(1)
            badge = QLabel(str(row.get("level"))); badge.setStyleSheet(ngr.badge_qss(row.get("tone") or "neutral"))
            rr.addWidget(badge)
            lay.addWidget(r)
        self._add(frame)

    def _add_timeline(self, nodes) -> None:
        if not nodes:
            return
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedHeight(78)
        host = QWidget(); row = QHBoxLayout(host); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(ngr.SPACE_XS)
        for n in nodes:
            f = QFrame()
            f.setStyleSheet(f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(n.get('tone') or 'neutral')}; }}")
            fl = QVBoxLayout(f); fl.setContentsMargins(ngr.SPACE_SM, ngr.SPACE_XS, ngr.SPACE_SM, ngr.SPACE_XS)
            nm = QLabel(str(n.get("label"))); nm.setStyleSheet(f"color:{ngr.TEXT_HI}; font-weight:600; font-size:{ngr.FS_CAPTION}pt;")
            fl.addWidget(nm)
            meta = QLabel(f"{n.get('date') or ''} {n.get('tag') or ''}".strip()); meta.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
            fl.addWidget(meta)
            row.addWidget(f)
        row.addStretch(1)
        scroll.setWidget(host)
        self._add(scroll)

    def _add_quick_actions(self, actions) -> None:
        if not actions:
            return
        bar = QWidget(); brow = QHBoxLayout(bar); brow.setContentsMargins(0, 0, 0, 0)
        lead = QLabel("Departments:"); lead.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        brow.addWidget(lead)
        for a in actions:
            btn = QPushButton(str(a.get("label")))
            target = a.get("target")
            btn.clicked.connect(lambda _=False, t=target: self._fire(self._on_navigate, t))
            brow.addWidget(btn)
        brow.addStretch(1)
        wrap = QScrollArea(); wrap.setWidgetResizable(True); wrap.setFrameShape(QFrame.Shape.NoFrame)
        wrap.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wrap.setFixedHeight(48); wrap.setWidget(bar)
        self._add(wrap)
