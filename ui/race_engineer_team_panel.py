"""Race-Engineer Team Brief section (Engineering Brain Program 2, Phase 38).

A compact READ-ONLY section of the Development History page that renders the integrated race-engineer
team brief for the current context: exact vs transferable evidence, the current best-known setup,
lineage, latest outcome, protected strengths, working windows, driver progression, coaching
priorities, the coordinated crew plan, confidence, missing evidence and the next best action with its
verification criteria.

Visual design follows the NGR pit-wall design system (`ui/ngr_theme.py`): one scannable card per crew
role, each with a semantic tone AND an explicit text status tag (meaning is never carried by colour
alone), a clear type hierarchy (bright sub-headers, readable body, dim secondary), and tabular figures
for working-window values. It is read-only with respect to knowledge and database state: NO Apply
control, NO setup mutation, NO experiment/campaign creation, NO scheduler, NO editable grade or
priority, NO AI call and NO automatic export. The heavy build runs OFF the Qt thread (dashboard worker
+ stale-result guard); this panel only renders the finished immutable dict.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import race_engineer_team_vm as vm

# a platform monospace stack for tabular figures (working-window numbers align in columns).
_MONO = "Consolas, 'Cascadia Mono', 'DejaVu Sans Mono', monospace"


def _tone_border(tone: str) -> str:
    return ngr.STATUS_TONES.get(tone, ngr.STATUS_TONES["neutral"])[2]


class RaceEngineerTeamPanel(QWidget):
    """Self-contained read-only section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_race_engineer_team_brief``."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAccessibleName("Race-Engineer Team Brief")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Race-Engineer Team Brief")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. One coordinated race-engineer plan for the current event - context, "
                      "exact vs transferable evidence, current best-PROVEN setup, working windows, "
                      "driver progression, coaching priorities and the next controlled step. It is "
                      "not a certification, not an experiment, not a setup and not permission to "
                      "Apply; it never claims a final or 'ultimate' setup; no setup values.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        # overall status banner (tone + an explicit status tag inside the text).
        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setStyleSheet(ngr.banner_qss("advisory"))
        self._root.addWidget(self._header)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_SM)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_result(None)

    def update_result(self, result: Optional[dict]) -> None:
        self._clear_cards()
        data = vm.build(result)
        self._header.setText(vm.header_text(data))
        self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(data)))
        tag, _tone = vm.status_summary(data)
        self._header.setAccessibleDescription(f"Overall status: {tag}. {vm.header_text(data)}")
        if vm.is_empty(data):
            return
        for card in vm.brief_cards(data):
            self._add_card(card)

    def _clear_cards(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _add_card(self, card: dict) -> None:
        tone = card.get("tone") or "neutral"
        frame = QFrame()
        frame.setAccessibleName(f"{card['title']} - {card.get('status_tag') or ''}".strip(" -"))
        # standard NGR card + a coloured left accent that echoes the status tone (severity is ALSO
        # shown as a text badge below, so colour is never the only signal).
        frame.setStyleSheet(
            f"QFrame {{ {ngr.card_qss()} border-left: 4px solid {_tone_border(tone)}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(ngr.SPACE_MD, ngr.SPACE_SM, ngr.SPACE_MD, ngr.SPACE_SM)
        lay.setSpacing(ngr.SPACE_XS)

        # header row: role title + a text status badge (tone secondary to the words).
        header = QWidget()
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(0, 0, 0, 0)
        htitle = QLabel(str(card["title"]))
        htitle.setStyleSheet(ngr.heading_qss(3))
        hrow.addWidget(htitle)
        hrow.addStretch(1)
        if card.get("status_tag"):
            badge = QLabel(card["status_tag"])
            badge.setStyleSheet(ngr.badge_qss(tone))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hrow.addWidget(badge)
        lay.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{ngr.HAIRLINE};")
        lay.addWidget(sep)

        for ln in card.get("lines", []):
            lbl = QLabel(str(ln))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(self._line_qss(str(ln)))
            lay.addWidget(lbl)

        self._cards_layout.addWidget(frame)
        self._cards.append(frame)

    @staticmethod
    def _line_qss(line: str) -> str:
        """Type hierarchy: bright sub-headers, readable body, dim secondary, tabular numerics.
        Deterministic (depends only on the line text)."""
        stripped = line.strip()
        # working-window / numeric evidence rows -> tabular monospace so columns align.
        if "conf " in line and "[" in line:
            return (f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt; "
                    f"font-family:{_MONO};")
        # sub-headers (a label line ending in a colon) -> bright + medium weight.
        if stripped.endswith(":"):
            return (f"color:{ngr.TEXT_HI}; font-weight:600; font-size:{ngr.FS_CAPTION}pt;")
        # numbered plan / ordered actions -> readable primary body.
        if stripped[:2].strip().isdigit() or stripped.startswith(tuple(f"{n}." for n in range(1, 10))):
            return (f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
        # limitations / advisory / secondary -> dim.
        low = stripped.lower()
        if low.startswith(("advisory", "read-only")) or "not permission" in low:
            return (f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt; font-style:italic;")
        return (f"color:{ngr.TEXT}; font-size:{ngr.FS_CAPTION}pt;")
