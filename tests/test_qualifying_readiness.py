"""Tests for the qualifying readiness checklist (F4)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.qualifying_readiness import (
    QualifyingReadiness, QualifyingReadinessVM, ReadinessItem,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _ready_vm():
    return QualifyingReadinessVM(
        items=(
            ReadinessItem("Qualifying setup selected", "ok", "Quali v3"),
            ReadinessItem("Soft tyres confirmed", "ok", "Racing: Soft"),
            ReadinessItem("Fuel target", "ok", "2 laps + margin"),
            ReadinessItem("Out-lap plan", "ok", "1 build lap"),
            ReadinessItem("Risk corners", "warn", "Turn 1 lock-up risk"),
        ),
        explanation="Softer rear ARB from practice gives more rotation; protect the fronts on the out-lap.",
    )


def _blocked_vm():
    return QualifyingReadinessVM(
        items=(
            ReadinessItem("Qualifying setup selected", "ok"),
            ReadinessItem("Soft tyres confirmed", "blocked", "Still on Mediums"),
        ),
        blockers=("Fit Soft tyres before qualifying",),
    )


class TestQualifyingReadiness:
    def test_ready_enables_begin(self, qapp):
        w = QualifyingReadiness()
        w.set_readiness(_ready_vm())
        assert w._vm.ready is True
        assert w._begin.isEnabled() is True

    def test_blocked_disables_begin_and_shows_blockers(self, qapp):
        w = QualifyingReadiness()
        w.set_readiness(_blocked_vm())
        assert w._vm.ready is False
        assert w._begin.isEnabled() is False
        assert w._blockers.isHidden() is False

    def test_begin_emits(self, qapp):
        w = QualifyingReadiness()
        w.set_readiness(_ready_vm())
        seen = []
        w.begin_requested.connect(lambda: seen.append(True))
        w._begin.click()
        assert seen == [True]

    def test_empty_is_not_ready(self, qapp):
        w = QualifyingReadiness()
        w.set_readiness(QualifyingReadinessVM())
        assert w._vm.ready is False
        assert w._begin.isEnabled() is False

    def test_vm_ready_logic(self):
        assert _ready_vm().ready is True
        assert _blocked_vm().ready is False
        # a 'warn' item does not block readiness; only 'blocked' + blockers do.
        assert QualifyingReadinessVM(items=(ReadinessItem("x", "warn"),)).ready is True

    def test_defensive(self, qapp):
        w = QualifyingReadiness()
        w.set_readiness("garbage")
        assert w._begin.isEnabled() is False
