"""CarRangesDialog — per-car setup parameter min/max editor.

Standalone QDialog so that test_init_not_in_mixin stays green (the mixin
must not contain any __init__). Import and use from setup_builder_ui.py.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from strategy.setup_ranges import GENERIC_DEFAULTS, resolve_ranges, save_car_ranges

_TEXT = "#E0E0E0"


class CarRangesDialog(QDialog):
    """Dialog for editing per-car setup parameter min/max bounds.

    Emits ``ranges_saved(car_name)`` after a successful save so the caller
    can re-bound the main-form spinboxes immediately.
    """

    ranges_saved = pyqtSignal(str)

    # Integer params (QSpinBox)
    _INT_PARAMS: frozenset[str] = frozenset({
        "ride_height_front", "ride_height_rear",
        "dampers_front_comp", "dampers_front_ext",
        "dampers_rear_comp",  "dampers_rear_ext",
        "arb_front", "arb_rear",
        "aero_front", "aero_rear",
        "lsd_initial", "lsd_accel", "lsd_decel",
        "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
        "brake_bias",
        "ballast_position",
    })

    # Human-readable labels for every GENERIC_DEFAULTS param
    _LABELS: dict[str, str] = {
        "ride_height_front":  "Ride Height Front (mm)",
        "ride_height_rear":   "Ride Height Rear (mm)",
        "springs_front":      "Springs Front (Hz)",
        "springs_rear":       "Springs Rear (Hz)",
        "dampers_front_comp": "Dampers Front Compression (%)",
        "dampers_front_ext":  "Dampers Front Extension (%)",
        "dampers_rear_comp":  "Dampers Rear Compression (%)",
        "dampers_rear_ext":   "Dampers Rear Extension (%)",
        "arb_front":          "ARB Front (Lv.)",
        "arb_rear":           "ARB Rear (Lv.)",
        "camber_front":       "Camber Front (°)",
        "camber_rear":        "Camber Rear (°)",
        "toe_front":          "Toe Front (°)",
        "toe_rear":           "Toe Rear (°)",
        "aero_front":         "Aero Front Downforce (kg)",
        "aero_rear":          "Aero Rear Downforce (kg)",
        "lsd_initial":        "LSD Initial Torque (rear)",
        "lsd_accel":          "LSD Accel Sensitivity (rear)",
        "lsd_decel":          "LSD Braking Sensitivity (rear)",
        "lsd_front_initial":  "LSD Initial Torque (front)",
        "lsd_front_accel":    "LSD Accel Sensitivity (front)",
        "lsd_front_decel":    "LSD Braking Sensitivity (front)",
        "brake_bias":         "Brake Bias (−5F … +5R)",
        "ballast_kg":         "Ballast (kg)",
        "ballast_position":   "Ballast Position (−50…+50)",
        "power_restrictor":   "Power Restrictor (%)",
    }

    def __init__(self, car_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._car_name = car_name.strip()
        self.setWindowTitle(
            f"Car Setup Ranges — {self._car_name or '(Generic)'}"
        )
        self.setMinimumWidth(520)
        # param -> (min_spin, max_spin)
        self._rows: dict[str, tuple[QSpinBox | QDoubleSpinBox,
                                     QSpinBox | QDoubleSpinBox]] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        info = QLabel(
            f"Per-car parameter bounds for <b>{self._car_name or 'Generic'}</b>.<br>"
            "Leave at defaults to use the generic GT7 range.  "
            "Set Min == Max to lock the parameter to a fixed value.",
            wordWrap=True,
            styleSheet="color: #AAAAAA; font-size: 10px;",
        )
        outer.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(420)
        inner_widget = QWidget()
        form = QFormLayout(inner_widget)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(4)
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

        resolved = resolve_ranges(self._car_name)

        for param in GENERIC_DEFAULTS:
            lo, hi = resolved[param]
            is_int = param in self._INT_PARAMS

            if is_int:
                g_lo, g_hi = GENERIC_DEFAULTS[param]
                # Generous editing range so users can set true car limits
                edit_lo = int(g_lo) - max(abs(int(g_lo)), 50)
                edit_hi = int(g_hi) + max(abs(int(g_hi)), 200)
                min_spin: QSpinBox | QDoubleSpinBox = QSpinBox()
                min_spin.setRange(edit_lo, edit_hi)
                min_spin.setValue(int(round(lo)))
                max_spin: QSpinBox | QDoubleSpinBox = QSpinBox()
                max_spin.setRange(edit_lo, edit_hi)
                max_spin.setValue(int(round(hi)))
            else:
                g_lo, g_hi = GENERIC_DEFAULTS[param]
                edit_lo = float(g_lo) - max(abs(float(g_lo)), 5.0)
                edit_hi = float(g_hi) + max(abs(float(g_hi)), 10.0)
                min_spin = QDoubleSpinBox()
                min_spin.setRange(edit_lo, edit_hi)
                min_spin.setDecimals(2)
                min_spin.setSingleStep(0.1)
                min_spin.setValue(float(lo))
                max_spin = QDoubleSpinBox()
                max_spin.setRange(edit_lo, edit_hi)
                max_spin.setDecimals(2)
                max_spin.setSingleStep(0.1)
                max_spin.setValue(float(hi))

            min_spin.setToolTip(f"Minimum allowed value for {param}")
            max_spin.setToolTip(f"Maximum allowed value for {param}")

            pair_w = QWidget()
            pair_h = QHBoxLayout(pair_w)
            pair_h.setContentsMargins(0, 0, 0, 0)
            pair_h.setSpacing(4)
            pair_h.addWidget(
                QLabel("Min:", styleSheet="color: #888; font-size: 10px;")
            )
            pair_h.addWidget(min_spin)
            pair_h.addSpacing(8)
            pair_h.addWidget(
                QLabel("Max:", styleSheet="color: #888; font-size: 10px;")
            )
            pair_h.addWidget(max_spin)
            pair_h.addStretch()

            label_text = self._LABELS.get(
                param, param.replace("_", " ").title()
            )
            form.addRow(
                QLabel(label_text, styleSheet=f"color: {_TEXT};"), pair_w
            )
            self._rows[param] = (min_spin, max_spin)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        outer.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Save handler
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        overrides: dict[str, dict] = {
            param: {"min": min_spin.value(), "max": max_spin.value()}
            for param, (min_spin, max_spin) in self._rows.items()
        }
        try:
            save_car_ranges(self._car_name, overrides)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Range", str(exc))
            return
        self.ranges_saved.emit(self._car_name)
        self.accept()
