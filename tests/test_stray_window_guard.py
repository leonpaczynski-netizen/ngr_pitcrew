"""The stray-window guard must suppress a bare focus-stealing top-level window while
leaving real dialogs, titled windows, and popups completely alone."""

import pytest

from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt, QEvent

from ui.stray_window_guard import StrayWindowGuard, install_stray_window_guard


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _show_event():
    return QEvent(QEvent.Type.Show)


class TestClassification:
    def test_bare_empty_toplevel_is_stray(self, qapp):
        g = StrayWindowGuard(main_window=None)
        w = QWidget()               # no parent, no title, no content -> top-level
        assert g._is_stray(w) is True
        assert g._looks_empty(w) is True

    def test_titled_window_is_not_stray(self, qapp):
        g = StrayWindowGuard(main_window=None)
        w = QWidget()
        w.setWindowTitle("Transcribe to GT7")
        assert g._is_stray(w) is False

    def test_real_dialog_is_not_stray(self, qapp):
        g = StrayWindowGuard(main_window=None)
        dlg = QDialog()
        assert g._is_stray(dlg) is False

    def test_popup_and_tooltip_are_not_stray(self, qapp):
        g = StrayWindowGuard(main_window=None)
        popup = QWidget(None, Qt.WindowType.Popup)
        tip = QWidget(None, Qt.WindowType.ToolTip)
        assert g._is_stray(popup) is False
        assert g._is_stray(tip) is False

    def test_child_widget_is_not_stray(self, qapp):
        g = StrayWindowGuard(main_window=None)
        parent = QWidget()
        child = QWidget(parent)     # not a window
        assert g._is_stray(child) is False

    def test_main_window_is_never_stray(self, qapp):
        main = QWidget()
        g = StrayWindowGuard(main_window=main)
        assert g._is_stray(main) is False

    def test_window_with_content_is_not_empty(self, qapp):
        g = StrayWindowGuard(main_window=None)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("hi"))
        lay.addWidget(QPushButton("ok"))
        assert g._looks_empty(w) is False


class TestSuppression:
    def test_show_event_hides_empty_stray_and_flags_no_activate(self, qapp):
        g = StrayWindowGuard(main_window=None)
        w = QWidget()
        w.show()
        assert w.isVisible() is True
        # Simulate the app event filter seeing the Show.
        g.eventFilter(w, _show_event())
        assert w.isVisible() is False   # empty stray hidden
        assert w.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating) is True

    def test_titled_window_is_left_visible(self, qapp):
        g = StrayWindowGuard(main_window=None)
        w = QWidget()
        w.setWindowTitle("Real Window")
        w.show()
        g.eventFilter(w, _show_event())
        assert w.isVisible() is True    # untouched
        w.close()

    def test_report_is_once_per_culprit(self, qapp, capsys):
        g = StrayWindowGuard(main_window=None)
        for _ in range(4):
            w = QWidget()
            w.show()
            g.eventFilter(w, _show_event())
        out = capsys.readouterr().out
        # Same class ('QWidget' with empty objectName) -> reported once despite 4 shows.
        assert out.count("suppressed a stray top-level window") == 1


class TestSourceCaptureAndFileSink:
    def test_report_written_to_log_file_with_source(self, qapp, tmp_path):
        # The injected logger (a LapDataLogger) has no .warning; the file sink must
        # still capture the report so the culprit survives a console-less run.
        log = tmp_path / "stray_window.log"
        g = StrayWindowGuard(main_window=None, log_path=str(log))

        def _make_and_show():           # a named frame we expect to see in the trace
            w = QWidget()
            w.show()
            g.eventFilter(w, _show_event())

        _make_and_show()
        text = log.read_text(encoding="utf-8")
        assert "suppressed a stray top-level window" in text
        assert "shown from:" in text
        # The capturing frame is the application code that showed the window.
        assert "_make_and_show" in text

    def test_logger_without_warning_falls_back_to_print(self, qapp, capsys, tmp_path):
        class _NoWarn:                  # mimics LapDataLogger (no .warning)
            pass
        g = StrayWindowGuard(main_window=None, logger=_NoWarn(),
                             log_path=str(tmp_path / "s.log"))
        w = QWidget()
        w.show()
        g.eventFilter(w, _show_event())
        assert "suppressed a stray top-level window" in capsys.readouterr().out


class TestInstall:
    def test_install_returns_guard_and_is_disablable(self, qapp, monkeypatch):
        monkeypatch.delenv("NGR_NO_STRAY_GUARD", raising=False)
        g = install_stray_window_guard(qapp, None)
        assert isinstance(g, StrayWindowGuard)
        qapp.removeEventFilter(g)
        monkeypatch.setenv("NGR_NO_STRAY_GUARD", "1")
        assert install_stray_window_guard(qapp, None) is None
