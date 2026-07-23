"""TrackModellingPage — modelling a circuit, as a guided flow (stage 4b).

Not the classic tab rebuilt. That screen showed fourteen sections at once — search, seed
facts, readiness, calibration, path building, station map, segment table, alignment,
track truth, resolver, refinement, lap offset, AI verify, file audit — all visible
whether or not they applied, so nothing told the driver what to do next.

Here the state machine drives the screen: **pick the track → drive it → build the model
→ check the corners → validate → use it**. One step is live at a time, with one primary
action, and the step's own controls appear only where they are the point.

Pure presentation over ``data.track_modelling_guide``. It decides nothing: the
coordinator says which actions are legal and what the next step is, and this renders it.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from ui import ngr_theme as _t
from ui.components.cards import Card, SectionHeading
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton
from data.track_modelling_guide import STEPS, GuidedView, build_guided_view, step_states
from data.track_modelling_session import TrackModellingSession

_CORNER_COLUMNS = ("#", "Corner", "Type", "Confidence", "")


class TrackModellingPage(QWidget):
    """The guided track-modelling surface."""

    #: A coordinator action the driver chose (``TrackModellingAction`` value).
    action_requested = pyqtSignal(str)
    #: (location_id, layout_id) selected.
    track_selected = pyqtSignal(str, str)
    #: (segment index, action) from the corner review list.
    segment_action = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrTrackModelling")
        self._view = GuidedView()
        self._locations: list = []
        self._layouts: list = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
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

        lay.addWidget(SectionHeading("TRACK MODEL", level=1))
        self._intro = QLabel(
            "Teach the app a circuit: drive some clean laps and it learns the racing "
            "line and where the corners are. Only needed once per layout.")
        self._intro.setWordWrap(True)
        self._intro.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._intro)

        # Progress — six steps, always visible, so the driver knows how far in they are.
        self._chips = QHBoxLayout()
        self._chips.setSpacing(_t.SPACE_SM)
        self._chip_labels: list = []
        for _step, title, _purpose in STEPS:
            chip = QLabel(title)
            self._chip_labels.append(chip)
            self._chips.addWidget(chip)
        self._chips.addStretch(1)
        lay.addLayout(self._chips)

        # The one live step.
        self._card = Card()
        self._headline = QLabel("")
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H2}pt; font-weight: 700;")
        self._card.add(self._headline)
        self._purpose = QLabel("")
        self._purpose.setWordWrap(True)
        self._purpose.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._card.add(self._purpose)
        self._next_step = QLabel("")
        self._next_step.setWordWrap(True)
        self._next_step.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
        self._card.add(self._next_step)
        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(
            f"color: {_t.DANGER}; font-size: {_t.FS_LABEL}pt; font-weight: 600;")
        self._detail.setVisible(False)
        self._card.add(self._detail)

        # Track pickers — shown only on the step where choosing is the point.
        self._picker = QWidget()
        pick = QHBoxLayout(self._picker)
        pick.setContentsMargins(0, 0, 0, 0)
        pick.setSpacing(_t.SPACE_SM)
        self._location = QComboBox()
        self._layout_combo = QComboBox()
        for combo, width in ((self._location, 280), (self._layout_combo, 240)):
            combo.setMinimumWidth(width)
            combo.setMinimumHeight(_t.TOUCH_MIN_H)
            combo.setStyleSheet(
                f"QComboBox {{ color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
                f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
                f"padding: 4px 10px; font-size: {_t.FS_LABEL}pt; }}")
            pick.addWidget(combo)
        self._location.activated.connect(lambda _i: self._emit_selection())
        self._layout_combo.activated.connect(lambda _i: self._emit_selection())
        pick.addStretch(1)
        self._card.body.addWidget(self._picker)

        # Live capture status — only while recording or just after.
        self._capture = QLabel("")
        self._capture.setWordWrap(True)
        self._capture.setStyleSheet(
            f"color: {_t.NGR_GREEN}; font-size: {_t.FS_LABEL}pt; font-weight: 700;")
        self._card.add(self._capture)

        # Actions: one primary, escapes beside it.
        act = QHBoxLayout()
        self._primary = PrimaryActionButton()
        self._primary.clicked.connect(self._on_primary)
        act.addWidget(self._primary)
        self._secondaries: list = []
        self._secondary_row = act
        act.addStretch(1)
        self._card.body.addLayout(act)
        lay.addWidget(self._card)

        # Corner review — only on the review/validate steps.
        self._corners_card = Card()
        self._corners_card.add(SectionHeading("DETECTED CORNERS", level=3))
        self._corners_hint = QLabel(
            "Check these against the real circuit. Anything wrong can be renamed, "
            "renumbered, merged, split or rejected before you validate.")
        self._corners_hint.setWordWrap(True)
        self._corners_hint.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._corners_card.add(self._corners_hint)
        self._corners = QTableWidget(0, len(_CORNER_COLUMNS))
        self._corners.setHorizontalHeaderLabels(list(_CORNER_COLUMNS))
        self._corners.verticalHeader().setVisible(False)
        self._corners.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._corners.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._corners.setStyleSheet(
            f"QTableWidget {{ color: {_t.TEXT_HI}; background: {_t.CARBON_RAISED}; "
            f"alternate-background-color: {_t.CARBON}; gridline-color: {_t.HAIRLINE_SOFT}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; }}")
        self._corners.setAlternatingRowColors(True)
        hh = self._corners.horizontalHeader()
        for c in range(len(_CORNER_COLUMNS) - 1):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(len(_CORNER_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self._corners_card.add(self._corners)

        edits = QHBoxLayout()
        edits.setSpacing(_t.SPACE_SM)
        self._edit_buttons: dict = {}
        for key, label in (("approve", "Looks right"), ("reject", "Not a corner"),
                           ("rename", "Rename"), ("merge", "Merge with next"),
                           ("split", "Split")):
            btn = SecondaryActionButton(label)
            btn.clicked.connect(lambda _=False, k=key: self._on_segment_action(k))
            self._edit_buttons[key] = btn
            edits.addWidget(btn)
        edits.addStretch(1)
        self._corners_card.body.addLayout(edits)
        lay.addWidget(self._corners_card)

        self._empty_corners = QLabel("")
        self._empty_corners.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        self._corners_card.add(self._empty_corners)

        lay.addStretch(1)
        self.set_view(GuidedView(), session=None)

    # ---- population -------------------------------------------------------
    def set_tracks(self, locations: Sequence = (), layouts: Sequence = ()) -> None:
        """Fill the pickers. Items are (id, label) pairs."""
        self._locations = list(locations or [])
        self._layouts = list(layouts or [])
        for combo, items, placeholder in (
                (self._location, self._locations, "Choose a circuit…"),
                (self._layout_combo, self._layouts, "Choose a layout…")):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(placeholder, "")
            for item in items:
                try:
                    ident, label = item
                except (TypeError, ValueError):
                    ident = label = str(item)
                combo.addItem(str(label), str(ident))
            idx = combo.findData(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
        self._layout_combo.setEnabled(bool(self._layouts))

    def set_session(self, session: Optional[TrackModellingSession],
                    *, laps_captured: int = 0, corners: Sequence = ()) -> None:
        """Render a modelling session — the one call the host needs."""
        self.set_view(build_guided_view(session), session=session,
                      laps_captured=laps_captured, corners=corners)

    def set_view(self, view: GuidedView, *, session=None,
                 laps_captured: int = 0, corners: Sequence = ()) -> None:
        if not isinstance(view, GuidedView):
            view = GuidedView()
        self._view = view

        for i, (label, status) in enumerate(step_states(session)):
            chip = self._chip_labels[i]
            colour = {"done": _t.TEXT, "current": _t.NGR_GREEN}.get(status, _t.TEXT_MUTE)
            weight = "700" if status == "current" else "400"
            chip.setText(("✓ " if status == "done" else "") + label)
            chip.setStyleSheet(
                f"color: {colour}; font-size: {_t.FS_CAPTION}pt; font-weight: {weight};")

        self._headline.setText(view.headline)
        self._purpose.setText(view.step_purpose)
        self._next_step.setText(view.next_step)
        self._detail.setText(view.detail)
        self._detail.setVisible(bool(view.detail))
        self._picker.setVisible(view.shows_track_picker)

        if view.shows_capture_status:
            self._capture.setText(
                f"● RECORDING — {laps_captured} clean lap"
                f"{'s' if laps_captured != 1 else ''} captured"
                if view.busy else
                f"{laps_captured} lap{'s' if laps_captured != 1 else ''} captured")
        self._capture.setVisible(view.shows_capture_status)

        self._primary.set_action(view.primary.label if view.primary else "",
                                 enabled=bool(view.primary) and not view.busy)
        self._render_secondaries(view)

        self._corners_card.setVisible(view.shows_corner_list)
        if view.shows_corner_list:
            self._render_corners(corners)

    def _render_secondaries(self, view: GuidedView) -> None:
        for btn in self._secondaries:
            self._secondary_row.removeWidget(btn)
            btn.setParent(None)
        self._secondaries = []
        for i, action in enumerate(view.secondary):
            btn = SecondaryActionButton(action.label)
            btn.clicked.connect(
                lambda _=False, a=action.action: self.action_requested.emit(a))
            self._secondary_row.insertWidget(1 + i, btn)
            self._secondaries.append(btn)

    def _render_corners(self, corners: Sequence) -> None:
        rows = list(corners or [])
        self._corners.setRowCount(len(rows))
        for r, corner in enumerate(rows):
            values = (
                str(corner.get("number", r + 1)), str(corner.get("name", "")),
                str(corner.get("type", "")), str(corner.get("confidence", "")),
                str(corner.get("note", "")))
            for c, text in enumerate(values):
                self._corners.setItem(r, c, QTableWidgetItem(text))
        self._corners.setVisible(bool(rows))
        self._empty_corners.setText(
            "" if rows else "No corners detected yet — build the model first.")
        self._empty_corners.setVisible(not rows)
        for btn in self._edit_buttons.values():
            btn.setEnabled(bool(rows))

    # ---- signals ----------------------------------------------------------
    def _emit_selection(self) -> None:
        loc = self._location.currentData() or ""
        lay = self._layout_combo.currentData() or ""
        if loc and lay:
            self.track_selected.emit(str(loc), str(lay))

    def _on_primary(self) -> None:
        if self._view.primary:
            self.action_requested.emit(self._view.primary.action)

    def _on_segment_action(self, key: str) -> None:
        row = self._corners.currentRow()
        if row >= 0:
            self.segment_action.emit(row, key)

    def current_view(self) -> GuidedView:
        return self._view
