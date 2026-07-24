"""SetupLineageTree — a vertical setup-lineage timeline (F2.4).

Shows the setup lineage as a top-down timeline (newest at top): each version is a
node coloured by its measured outcome (improved = green, worse = red and prominent,
unchanged/neutral, inconclusive = amber), the current setup is marked, and older
nodes offer Revert. Failed directions stay visible — the UI never hides a worse
result. Pure presentation: it renders LineageNode data the caller maps from the
canonical setup lineage / DB experiments; it computes no outcomes itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame

from ui import ngr_theme as _t
from ui.components.status import StatusPill, TONE_BASE_COLOR
from ui.components.buttons import SecondaryActionButton


@dataclass(frozen=True)
class LineageNode:
    node_id: str
    label: str                 # e.g. "Quali v3"
    outcome: str = ""          # improved|worse|unchanged|inconclusive|"" (baseline/unmeasured)
    is_current: bool = False
    summary: str = ""          # short "what changed / why" line
    discipline: str = ""       # base|qualifying|race (optional)
    revertable: bool = True     # older, applied nodes can be reverted to


class SetupLineageTree(QWidget):
    revert_requested = pyqtSignal(str)   # node_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrLineageTree")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        self._root.addLayout(self._body)
        self._empty = QLabel("No setup lineage yet — the first applied setup starts the tree.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._root.addWidget(self._empty)
        self._root.addStretch(1)
        self.set_nodes(())

    def set_nodes(self, nodes: Iterable[LineageNode]) -> None:
        _clear_layout(self._body)
        nodes = [n for n in (nodes or ()) if isinstance(n, LineageNode)]
        self._empty.setVisible(not nodes)
        last = len(nodes) - 1
        for i, node in enumerate(nodes):
            self._body.addWidget(self._render_node(node, is_last=(i == last)))

    # ---- rendering --------------------------------------------------------
    def _render_node(self, node: LineageNode, is_last: bool) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(_t.SPACE_SM)

        # Rail: dot + connector line (drops to the next node).
        rail = QWidget()
        rail.setFixedWidth(18)
        rv = QVBoxLayout(rail)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        tone = _outcome_tone(node)
        dot = QLabel()
        dot.setFixedSize(12, 12)
        dot_colour = _t.NGR_GREEN if node.is_current else TONE_BASE_COLOR.get(tone, _t.NEUTRAL)
        dot.setStyleSheet(
            f"background: {dot_colour}; border-radius: 6px; "
            f"border: 2px solid {_t.INK_BLACK};"
        )
        rv.addSpacing(4)
        rv.addWidget(dot, 0, Qt.AlignmentFlag.AlignHCenter)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"color: {_t.HAIRLINE}; background: {_t.HAIRLINE}; max-width: 2px;")
        line.setVisible(not is_last)
        rv.addWidget(line, 1, Qt.AlignmentFlag.AlignHCenter)

        # Card
        card = QFrame()
        card.setObjectName("ngrLineageCard")
        edge = _t.NGR_GREEN if node.is_current else TONE_BASE_COLOR.get(tone, _t.HAIRLINE)
        card.setStyleSheet(
            f"#ngrLineageCard {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; border-left: 3px solid {edge}; "
            f"border-radius: {_t.RADIUS_SM}px; }}"
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
        cv.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        name = QLabel(node.label + ("  ▶ current" if node.is_current else ""))
        name.setStyleSheet(
            f"color: {_t.TEXT_HI if node.is_current else _t.TEXT}; "
            f"font-weight: 700; font-size: {_t.FS_LABEL}pt;")
        top.addWidget(name)
        if node.discipline:
            disc = QLabel(node.discipline.title())
            disc.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
            top.addWidget(disc)
        top.addStretch(1)
        if node.outcome:
            desc = _t.outcome_tone(node.outcome)
            pill = StatusPill(desc["label"], tone=desc["tone"], glyph=desc.get("glyph", ""))
            top.addWidget(pill)
        cv.addLayout(top)

        if node.summary:
            s = QLabel(node.summary)
            s.setWordWrap(True)
            s.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
            cv.addWidget(s)

        if node.revertable and not node.is_current:
            act = QHBoxLayout()
            act.setContentsMargins(0, 0, 0, 0)
            act.addStretch(1)
            # Loads this revision's values back onto the sheet so the driver can re-enter
            # them in GT7 — "the settings I'm running" — not a silent undo.
            btn = SecondaryActionButton("Load this setup")
            btn.clicked.connect(lambda _=False, nid=node.node_id: self.revert_requested.emit(nid))
            act.addWidget(btn)
            cv.addLayout(act)

        h.addWidget(rail)
        h.addWidget(card, 1)
        # tighten vertical gap between nodes
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, _t.SPACE_XS)
        wl.setSpacing(0)
        wl.addWidget(row)
        return wrap


def _outcome_tone(node: LineageNode) -> str:
    if not node.outcome:
        return "neutral"
    return _t.outcome_tone(node.outcome)["tone"]


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
