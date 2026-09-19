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
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.store import catalogs
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    Field,
    Plate,
    Rule,
    StencilLabel,
)


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

        # Containers before contents - see `EventScreen._build` (19 Sep 2026).
        header = QVBoxLayout()
        header.setSpacing(2)
        page.addLayout(header)
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

        # **A way to find a row.** These are the knowledge base's tables, read
        # at the rig with the headset pushed up, and the only tool for finding
        # anything in them was the scroll wheel. Filtering hides plates that
        # do not match, which stays inside the screen's own constraint - it is
        # read-only, so this acts on nothing.
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Find a row…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        page.addWidget(Field("Filter", self.filter_edit,
                             hint="Hides sections with no match. Nothing here "
                                  "is editable."))

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page.addWidget(scroller, 1)

        inner = QWidget()
        stack = QVBoxLayout(inner)
        stack.setContentsMargins(0, 0, 4, 0)
        stack.setSpacing(theme.GAP_WIDE)
        scroller.setWidget(inner)

        sections = self._reference.get("sections") or []
        if not sections:
            stack.addWidget(BodyLabel(
                "The reference file is missing. Run "
                "`python tools/extract_reference.py` after checking the "
                "artifact into reference/.", colour=theme.WARNING))
        self._plates: list[tuple] = []
        for section in sections:
            plate = self._section_plate(section)
            stack.addWidget(plate)
            self._plates.append((plate, self._section_text(section)))
        stack.addStretch(1)

    @staticmethod
    def _section_text(section: dict) -> str:
        parts = [str(section.get("title", "")), str(section.get("hint", ""))]
        for entry in section.get("rows") or []:
            parts.extend(str(cell) for cell in entry)
        return " ".join(parts).lower()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        shown = 0
        for plate, haystack in getattr(self, "_plates", []):
            match = not needle or needle in haystack
            plate.setVisible(match)
            shown += int(match)
        if needle and not shown:
            self.filter_edit.setToolTip("Nothing in the reference matches.")
        else:
            self.filter_edit.setToolTip("")

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
                # **Not stencil white.** This is the knowledge base's own
                # table - neither measured here nor declared here - and the
                # design says so in as many words: shipped reference data set
                # in the measured ink would look like it came off the stream.
                # The rule is stated in DESIGN.md and was broken on the only
                # screen it governs. The first column still carries the
                # emphasis, by weight rather than by borrowing a register.
                label = BodyLabel(str(cell), size=14,
                                  colour=theme.STENCIL_DIM,
                                  bold=index == 0)
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
