"""Reference — the knowledge base's own tables, read-only.

Ported from the retired HTML tool's Quick Reference tab so the driver does not
have to keep a browser open next to the app.

**Nothing on this screen is the app's.** It is the knowledge base's material,
displayed verbatim from `data/gt7_quick_reference.json`, and no other part of
the app reads it: not the prompt builder, not the export, not the setup form.
The app composes prompts and records what happened; it never decides what to
change. If this ever grows a control that acts on what it says, it has become
a second knowledge base and it is wrong.

It is set as prose rather than in the three registers, because none of it was
measured, declared or derived here.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.store import catalogs
from pitcrew.ui import theme
from pitcrew.ui.widgets import BodyLabel, Plate, Rule, StencilLabel


class ReferenceScreen(QWidget):
    """Static tables. No actions, because there is nothing here to act on."""

    def __init__(self, reference: dict | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._reference = (reference if reference is not None
                           else catalogs.quick_reference())
        self._build()

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(StencilLabel("Reference", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        header.addWidget(BodyLabel(
            "The knowledge base's tables, carried here so they are readable "
            "at the rig. The app does not use any of it — it composes "
            "prompts, it does not decide what to change.",
            colour=theme.STENCIL_DIM))
        baseline = self._reference.get("baseline")
        if baseline:
            header.addWidget(BodyLabel(baseline, size=13,
                                       colour=theme.WARNING))
        page.addLayout(header)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        stack = QVBoxLayout(inner)
        stack.setContentsMargins(0, 0, 4, 0)
        stack.setSpacing(theme.GAP_WIDE)

        sections = self._reference.get("sections") or []
        if not sections:
            stack.addWidget(BodyLabel(
                "The reference file is missing. Run "
                "`python tools/extract_reference.py` after checking the "
                "artifact into reference/.", colour=theme.WARNING))
        for section in sections:
            stack.addWidget(self._section_plate(section))
        stack.addStretch(1)

        scroller.setWidget(inner)
        page.addWidget(scroller, 1)

    def _section_plate(self, section: dict) -> Plate:
        plate = Plate(section.get("title", ""))
        if section.get("hint"):
            plate.body.addWidget(BodyLabel(section["hint"], size=13,
                                           colour=theme.STENCIL_DIM))

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP_WIDE)
        grid.setVerticalSpacing(theme.GAP_TIGHT)

        columns = [c for c in (section.get("columns") or []) if c]
        row = 0
        if columns:
            for index, name in enumerate(section.get("columns") or []):
                if name:
                    grid.addWidget(
                        StencilLabel(name, size=11, tracking=12.0), row, index)
            row += 1
            rule = Rule()
            grid.addWidget(rule, row, 0, 1,
                           len(section.get("columns") or []) or 1)
            row += 1

        for entry in section.get("rows") or []:
            for index, cell in enumerate(entry):
                # First column is the handle you find the row by, so it holds
                # the emphasis; the rest is explanation.
                label = BodyLabel(
                    str(cell), size=14,
                    colour=theme.STENCIL if index == 0 else theme.STENCIL_DIM)
                grid.addWidget(label, row, index)
            row += 1

        rows = section.get("rows") or []
        widths = max((len(entry) for entry in rows), default=1)
        # A first column of rank numbers gets no stretch at all - given a
        # share it opens a hand's width of nothing before the actual table.
        numbered = all(len(str(entry[0])) <= 3 for entry in rows) if rows \
            else False
        grid.setColumnStretch(0, 0 if numbered else 3)
        for index in range(1, widths):
            grid.setColumnStretch(index, 4 if index == widths - 1 else 2)
        plate.body.addLayout(grid)
        return plate
