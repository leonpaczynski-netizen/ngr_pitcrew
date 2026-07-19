"""Assurance Review Pack section (Engineering Brain Program 2, Phases 33-35).

A compact READ-ONLY section of the Development History page for producing an external assurance
review package. It previews the current assurance-chain export / review package, can compare against
an explicitly-chosen baseline manifest, and can export the review package to an explicitly-chosen
destination - all on explicit user action only (never automatically).

It is read-only with respect to knowledge and database state. There is NO Apply control, NO
experiment/campaign creation, NO scheduling, NO editable assurance grade or priority, NO setup
values, and NO API-key access. The three action buttons (Preview / Compare Baseline / Export Review
Package) delegate to handlers wired by the dashboard, which run the heavy build / file write OFF the
Qt thread. A successful export destination is shown OUTSIDE the deterministic report content.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtWidgets import QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui import ngr_theme as ngr
from ui import assurance_review_pack_vm as vm


class AssuranceReviewPackPanel(QWidget):
    """Self-contained section. Call :meth:`update_result` with the dict from
    ``SessionDB.build_assurance_review_package_report``. Action buttons delegate to handlers set via
    :meth:`set_action_handlers` (the dashboard wires them to off-thread build/write)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._on_preview: Optional[Callable[[], None]] = None
        self._on_compare: Optional[Callable[[], None]] = None
        self._on_export: Optional[Callable[[], None]] = None

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(ngr.SPACE_SM)

        title = QLabel("Assurance Review Pack")
        title.setStyleSheet(ngr.heading_qss(2))
        self._root.addWidget(title)

        note = QLabel("Read-only. Generate a deterministic, shareable external assurance review "
                      "package from the current assurance chain (Phases 26-32), optionally compared "
                      "against a baseline manifest. It is not a certification, not an experiment, "
                      "not a setup and not permission to Apply. Files are written only when you "
                      "choose a destination; nothing is exported automatically; no setup values.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(note)

        self._header = QLabel("")
        self._header.setWordWrap(True)
        self._header.setStyleSheet(ngr.banner_qss("info"))
        self._root.addWidget(self._header)

        # explicit-action buttons (no Apply / experiment / campaign / schedule wording).
        btn_row = QWidget()
        row = QHBoxLayout(btn_row)
        row.setContentsMargins(0, 0, 0, 0)
        self._preview_btn = QPushButton("Preview Assurance Review")
        self._compare_btn = QPushButton("Compare Baseline...")
        self._export_btn = QPushButton("Export Review Package...")
        for b in (self._preview_btn, self._compare_btn, self._export_btn):
            row.addWidget(b)
        row.addStretch(1)
        self._root.addWidget(btn_row)
        self._preview_btn.clicked.connect(lambda: self._fire(self._on_preview))
        self._compare_btn.clicked.connect(lambda: self._fire(self._on_compare))
        self._export_btn.clicked.connect(lambda: self._fire(self._on_export))

        # export destination / errors shown OUTSIDE the deterministic report content.
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        self._root.addWidget(self._status)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(ngr.SPACE_SM)
        self._root.addWidget(self._cards_container)
        self._cards: list = []

        self.update_result(None)

    def set_action_handlers(self, *, preview: Optional[Callable[[], None]] = None,
                            compare: Optional[Callable[[], None]] = None,
                            export: Optional[Callable[[], None]] = None) -> None:
        self._on_preview = preview
        self._on_compare = compare
        self._on_export = export

    @staticmethod
    def _fire(handler: Optional[Callable[[], None]]) -> None:
        if callable(handler):
            try:
                handler()
            except Exception:  # pragma: no cover - defensive; never propagate into Qt
                pass

    def update_result(self, result: Optional[dict]) -> None:
        self._clear_cards()
        data = vm.build(result)
        self._header.setText(vm.header_text(data))
        self._header.setStyleSheet(ngr.banner_qss(vm.banner_tone(data)))
        # compare/export only meaningful once there IS a current package to work with.
        has_pkg = not vm.is_empty(data)
        self._compare_btn.setEnabled(has_pkg)
        self._export_btn.setEnabled(has_pkg)
        if vm.is_empty(data):
            return
        for card in vm.review_cards(data):
            self._add_card(card)

    def update_export_status(self, write_result: Optional[dict]) -> None:
        text = vm.export_status_text(write_result)
        self._status.setText(text)
        tone = "success" if (write_result or {}).get("ok") else (
            "warn" if write_result else "info")
        colour = ngr.SUCCESS if tone == "success" else (ngr.WARN if tone == "warn" else ngr.TEXT_DIM)
        self._status.setStyleSheet(f"color:{colour}; font-size:{ngr.FS_CAPTION}pt;")

    def _clear_cards(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []

    def _add_card(self, card: dict) -> None:
        box = QGroupBox(f"{card['title']}   -   {card['status']}")
        box.setStyleSheet(ngr.card_qss())
        lay = QVBoxLayout(box)
        for section_title, lines in card["sections"]:
            hdr = QLabel(section_title)
            hdr.setStyleSheet(f"color:{ngr.TEXT_HI}; font-weight:600; font-size:{ngr.FS_LABEL}pt;")
            lay.addWidget(hdr)
            for ln in lines:
                if not str(ln).strip():
                    continue
                lbl = QLabel(str(ln))
                lbl.setWordWrap(True)
                lbl.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
                lay.addWidget(lbl)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color:{ngr.HAIRLINE};")
            lay.addWidget(sep)
        self._cards_layout.addWidget(box)
        self._cards.append(box)
