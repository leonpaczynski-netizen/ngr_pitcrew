"""EventExportPanel — explicit export of the post-event engineering spec (C17/C21).

Presents a single Export button. The destination is chosen by the owner via a
QFileDialog — never defaulted, never auto-triggered. The export worker runs OFF
the Qt thread; progress is shown while it runs; the resulting content digest
(sha256) is displayed on completion. If the target file already exists an
explicit overwrite-confirmation dialog is shown and the write is only retried
with ``allow_overwrite=True`` after the owner confirms.

The panel is READ-ONLY with respect to all engineering state. It produces a
deterministic JSON file that Leon uploads to his external Claude project; the
Pit Crew app does not consume it.

Modelled after ``ui/assurance_review_pack_panel.py`` (explicit buttons, work
off the Qt thread via a QThread worker, destination status shown OUTSIDE the
deterministic content).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget,
)

from ui import ngr_theme as _t
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton


# ---------------------------------------------------------------------------
# Off-thread worker
# ---------------------------------------------------------------------------

class _ExportWorker(QThread):
    """Run ``services.event_export_service.export_to_file`` off the Qt thread.

    ``finished_ok`` carries the result dict from the service.
    ``failed`` carries a structured error string.
    """

    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, db, event_id: int, destination_dir: str, *,
                 car: str = "", track: str = "", layout_id: str = "",
                 allow_overwrite: bool = False,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._db = db
        self._event_id = event_id
        self._destination_dir = destination_dir
        self._car = car
        self._track = track
        self._layout_id = layout_id
        self._allow_overwrite = allow_overwrite

    def run(self) -> None:
        """Executes on the worker thread — no Qt widget access."""
        try:
            from services.event_export_service import export_to_file
            result = export_to_file(
                self._db,
                self._event_id,
                self._destination_dir,
                car=self._car,
                track=self._track,
                layout_id=self._layout_id,
                allow_overwrite=self._allow_overwrite,
            )
            self.finished_ok.emit(dict(result or {}))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Panel widget
# ---------------------------------------------------------------------------

class EventExportPanel(QWidget):
    """Export button, progress, sha256 digest display, overwrite confirmation.

    Call :meth:`set_event` before the owner can export. The panel is inert
    while ``event_id == 0``.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ngrEventExportPanel")
        self._event_id: int = 0
        self._car: str = ""
        self._track: str = ""
        self._layout_id: str = ""
        self._db = None
        self._worker: Optional[_ExportWorker] = None
        self._last_destination_dir: str = ""
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_SM)

        title = QLabel("Export Engineering Spec")
        title.setStyleSheet(_t.heading_qss(2))
        lay.addWidget(title)

        note = QLabel(
            "Generate the deterministic event engineering file for upload to your "
            "Claude project. The export includes owner baselines, all session "
            "proposals (proposed, accepted, rejected, edited), unresolved riders, "
            "suppressed changes, and session evidence. "
            "Export is NEVER automatic — you choose the destination."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        lay.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(_t.SPACE_SM)
        self._export_btn = PrimaryActionButton("Export event spec...")
        self._export_btn.clicked.connect(self._on_export_clicked)
        self._export_btn.setEnabled(False)
        btn_row.addWidget(self._export_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        # Progress / status — OUTSIDE the deterministic content area.
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        lay.addWidget(self._status)

        # sha256 digest — large, copyable, highlighted on success.
        self._digest = QLabel("")
        self._digest.setWordWrap(True)
        self._digest.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._digest.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._digest.setVisible(False)
        lay.addWidget(self._digest)

    # ------------------------------------------------------------------ public
    def set_event(self, event_id: int, *, car: str = "", track: str = "",
                  layout_id: str = "", db=None) -> None:
        """Point the panel at an event. Must be called before the export can run."""
        self._event_id = int(event_id or 0)
        self._car = str(car or "")
        self._track = str(track or "")
        self._layout_id = str(layout_id or "")
        self._db = db
        self._export_btn.setEnabled(bool(self._event_id and self._db is not None))
        self._status.setText("")
        self._digest.setVisible(False)

    # ----------------------------------------------------------------- slots
    def _on_export_clicked(self) -> None:
        """Ask for a destination directory then kick off the export worker."""
        if self._worker is not None and self._worker.isRunning():
            self._status.setText("Export already in progress — wait for it to finish.")
            return
        destination_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose export destination folder",
            self._last_destination_dir or "",
        )
        if not destination_dir:
            return  # cancelled
        self._last_destination_dir = destination_dir
        self._run_export(destination_dir, allow_overwrite=False)

    def _run_export(self, destination_dir: str, *, allow_overwrite: bool) -> None:
        """Start the off-thread export worker."""
        self._export_btn.setEnabled(False)
        self._status.setText("Exporting — please wait...")
        self._status.setStyleSheet(
            f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._digest.setVisible(False)

        self._worker = _ExportWorker(
            self._db, self._event_id, destination_dir,
            car=self._car, track=self._track, layout_id=self._layout_id,
            allow_overwrite=allow_overwrite,
            parent=self,
        )
        self._worker.finished_ok.connect(self._on_export_done)
        self._worker.failed.connect(self._on_export_failed)
        self._worker.start()

    def _on_export_done(self, result: dict) -> None:
        """Handle the worker result on the Qt thread."""
        self._export_btn.setEnabled(bool(self._event_id and self._db is not None))
        ok = bool(result.get("ok"))
        errors = list(result.get("errors") or [])
        warnings = list(result.get("warnings") or [])
        filename = str(result.get("filename") or "")
        sha = str(result.get("file_sha256") or "")
        dest = str(result.get("destination") or self._last_destination_dir or "")

        # C21 overwrite guard: if the only error is "already exists at destination",
        # ask for explicit confirmation before retrying.
        if not ok and errors:
            overwrite_error = any("already exists at destination" in e for e in errors)
            if overwrite_error:
                choice = QMessageBox.question(
                    self,
                    "File already exists",
                    f"A file named \"{filename}\" already exists at the chosen "
                    f"destination.\n\nOverwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if choice == QMessageBox.StandardButton.Yes:
                    self._run_export(dest, allow_overwrite=True)
                else:
                    self._status.setText("Export cancelled — file not overwritten.")
                    self._status.setStyleSheet(
                        f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
                return

        if ok:
            # C21: show the resulting digest prominently and separately.
            parts = [f"Exported: {filename}"]
            if dest:
                parts.append(f"Location: {dest}")
            if warnings:
                parts.append("Warnings: " + "; ".join(warnings))
            self._status.setText("  ".join(parts))
            self._status.setStyleSheet(
                f"color: {_t.SUCCESS}; font-size: {_t.FS_CAPTION}pt; "
                f"font-weight: 600;")
            if sha:
                self._digest.setText(f"Content digest (sha256): {sha}")
                self._digest.setStyleSheet(
                    f"color: {_t.TEXT}; font-size: {_t.FS_CAPTION}pt; "
                    f"font-family: monospace;")
                self._digest.setVisible(True)
        else:
            err_text = "; ".join(errors) if errors else "Unknown error."
            self._status.setText(f"Export failed: {err_text}")
            self._status.setStyleSheet(
                f"color: {_t.DANGER}; font-size: {_t.FS_CAPTION}pt; "
                f"font-weight: 600;")

    def _on_export_failed(self, message: str) -> None:
        """Handle a worker-thread exception (not a service-level failure)."""
        self._export_btn.setEnabled(bool(self._event_id and self._db is not None))
        self._status.setText(f"Export failed (internal error): {message}")
        self._status.setStyleSheet(
            f"color: {_t.DANGER}; font-size: {_t.FS_CAPTION}pt; "
            f"font-weight: 600;")
