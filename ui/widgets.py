"""Reusable custom PyQt6 widgets for the GT7 dashboard."""
from __future__ import annotations
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import (
    QFrame, QLabel, QProgressBar, QSizePolicy, QVBoxLayout, QHBoxLayout,
    QWidget,
)

from telemetry.state import TyreState

# Tyre state → (background hex, text color hex, display label)
_TYRE_STYLE: dict[TyreState, tuple[str, str, str]] = {
    TyreState.COLD:        ("#2C5F8A", "#FFFFFF", "COLD"),
    TyreState.WARMING:     ("#4A9B6F", "#FFFFFF", "WARMING"),
    TyreState.OPTIMAL:     ("#2EA043", "#FFFFFF", "OPTIMAL"),
    TyreState.HOT:         ("#E8771A", "#FFFFFF", "HOT"),
    TyreState.OVERHEATING: ("#C0392B", "#FFFFFF", "OVERHEAT"),
}


class TyreWidget(QFrame):
    """Displays one tyre's temperature and state with colour coding."""

    def __init__(self, position: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._position = position  # e.g. "FL"
        self.setFixedSize(QSize(110, 140))
        self.setFrameShape(QFrame.Shape.Box)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        pos_label = QLabel(position, self)
        pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pos_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        pos_label.setStyleSheet("color: #AAAAAA;")

        self._temp_label = QLabel("---°C", self)
        self._temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._temp_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))

        self._state_label = QLabel("—", self)
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

        layout.addWidget(pos_label)
        layout.addStretch()
        layout.addWidget(self._temp_label)
        layout.addWidget(self._state_label)
        layout.addStretch()

        self._apply_state(TyreState.COLD, 0.0)

    def update_tyre(self, temp: float, state: TyreState) -> None:
        self._temp_label.setText(f"{temp:.1f}°C")
        self._apply_state(state, temp)

    def _apply_state(self, state: TyreState, temp: float) -> None:
        bg, fg, label = _TYRE_STYLE[state]
        self.setStyleSheet(
            f"TyreWidget {{ background-color: {bg}; border: 1px solid #555; border-radius: 6px; }}"
        )
        self._temp_label.setStyleSheet(f"color: {fg};")
        self._state_label.setText(label)
        self._state_label.setStyleSheet(f"color: {fg};")


class FuelBar(QWidget):
    """Horizontal fuel level bar with overlaid text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(36)
        self._level = 0.0
        self._capacity = 100.0

    def update_fuel(self, level: float, capacity: float) -> None:
        self._level = max(0.0, level)
        self._capacity = max(1.0, capacity)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        ratio = self._level / self._capacity if self._capacity > 0 else 0.0
        ratio = min(max(ratio, 0.0), 1.0)
        filled = int(w * ratio)

        # Background
        painter.fillRect(0, 0, w, h, QColor("#2A2A2A"))

        # Fill colour by level
        if ratio > 0.4:
            fill_color = QColor("#2EA043")
        elif ratio > 0.2:
            fill_color = QColor("#E8771A")
        else:
            fill_color = QColor("#C0392B")

        if filled > 0:
            painter.fillRect(0, 0, filled, h, fill_color)

        # Border
        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        # Text
        text = f"{self._level:.1f} / {self._capacity:.1f} L"
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, text)


class ConnectionStatusWidget(QWidget):
    """Status bar widget showing connection LED + packet rate + race state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)

        self._led = QLabel("●", self)
        self._led.setFont(QFont("Segoe UI", 12))

        self._conn_label = QLabel("Waiting for connection…", self)
        self._conn_label.setFont(QFont("Segoe UI", 9))

        self._state_label = QLabel("", self)
        self._state_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._state_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(self._led)
        layout.addWidget(self._conn_label)
        layout.addWidget(self._state_label)

        self.set_disconnected()

    def set_connected(self, hz: float) -> None:
        self._led.setStyleSheet("color: #2EA043;")
        self._conn_label.setText(f"Connected  {hz:.1f} Hz")

    def set_disconnected(self) -> None:
        self._led.setStyleSheet("color: #C0392B;")
        self._conn_label.setText("Waiting for connection…")

    def set_race_state(self, text: str) -> None:
        self._state_label.setText(text)


class BigValueLabel(QLabel):
    """Large coloured metric label for speed, gear, position etc."""

    def __init__(self, value: str = "—", unit: str = "",
                 font_size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._unit = unit
        self.setFont(QFont("Segoe UI", font_size, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(value)

    def set_value(self, value: str) -> None:
        self.setText(f"{value} {self._unit}".strip())
