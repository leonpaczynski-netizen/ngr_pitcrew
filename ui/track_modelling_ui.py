"""Track Modelling tab — mixin for MainWindow (DashboardWindow)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data.track_geometry_builder import GeometryBuildResult, GeometrySaveResult

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QCheckBox,
    QScrollArea, QComboBox, QSplitter, QTextEdit,
    QFrame, QSizePolicy, QListWidget,
    QListWidgetItem, QPlainTextEdit, QFormLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QLineEdit,
)

from telemetry.state import Priority
from data.track_intelligence import (
    load_track_seed, search_track_layouts as _ti_search,
)
from ui.track_modelling_vm import (
    format_layout_facts, format_readiness, format_calibration_car,
    build_location_display_items, build_layout_display_items,
    get_selected_location, get_selected_layout,
    get_seed_warning_text, is_seed_only, build_prompt_preview,
    describe_seed_load_status, CALIBRATION_CAR_BOUNDARY_NOTE,
    format_segment_row       as _format_seg_row,
    format_review_summary    as _format_review_summary,
    get_review_button_states as _get_review_btns,
    format_resolver_summary  as _format_resolver_summary,
    format_lap_count_info          as _format_lap_count_info,
    format_file_audit_status       as _format_file_audit,
    format_build_failure_diagnostics as _format_build_diag,
    format_track_truth_status      as _format_track_truth_status,
)
from data.track_truth import (
    resolve_track_truth_model   as _resolve_track_truth,
    validate_track_truth_model  as _validate_track_truth,
)
from data.track_calibration import (
    audit_track_model_files      as _audit_track_files,
    import_calibration_laps_json as _import_cal_laps,
    import_reference_path_json   as _import_ref_path,
)
from data.track_calibration_runtime import TrackCalibrationCaptureController
from data.track_segment_detection import (
    detect_track_segments as _detect_track_segments,
    TrackSegmentType      as _TrackSegmentType,
)
from data.track_segment_review import (
    create_review_from_detection as _create_seg_review,
    confirm_segment              as _seg_confirm,
    rename_segment               as _seg_rename,
    reject_segment               as _seg_reject,
    mark_needs_more_laps         as _seg_needs_laps,
    mark_split_required          as _seg_split,
    mark_merge_required          as _seg_merge,
    export_review_json           as _export_seg_review,
)
from data.track_model_resolver import resolve_best_track_model as _resolve_track_model
from data.track_station_map import (
    build_track_station_map  as _build_station_map,
    export_station_map_json  as _export_station_map,
    import_station_map_json  as _import_station_map,
    find_station_map_path    as _find_station_map_path,
)
from data.track_model_alignment import (
    align_track_model             as _align_track_model,
    export_accepted_model_json    as _export_accepted_model,
    find_accepted_model_path      as _find_accepted_model_path,
    import_accepted_model_json    as _import_accepted_model,
)
from ui.track_model_alignment_vm import (
    format_alignment_summary      as _fmt_alignment_summary,
    get_acceptance_button_states  as _get_accept_btn_states,
    format_mismatch_reasons       as _fmt_mismatch_reasons,
)
from data.track_map_matching import match_position_to_map as _map_match, MapMatchConfidence
from ui.track_map_vm import (
    build_track_map_draw_data as _build_map_draw_data,
    TrackMapDrawData,
    CarDot,
)
from ui.track_map_widget import TrackMapWidget

# Telemetry-behaviour segment types that must NOT appear in Segment Review geometry table.
_TELEMETRY_OVERLAY_SEG_TYPES: frozenset = frozenset({
    _TrackSegmentType.BRAKING_ZONE,
    _TrackSegmentType.TRACTION_ZONE,
    _TrackSegmentType.GEAR_ZONE,
    _TrackSegmentType.LIMITER_ZONE,
    _TrackSegmentType.FUEL_SAVING_CANDIDATE,
    _TrackSegmentType.KERB_OR_BUMP_CANDIDATE,
})

# Module-level colour constants (mirrored from dashboard.py)
_DARK_BG   = "#1E1E1E"
_DARK_CARD  = "#2A2A2A"
_TEXT       = "#E0E0E0"
_ACCENT     = "#2EA043"


class TrackModellingMixin:
    """Mixin providing all Track Modelling tab UI and logic.

    Requires self._config (dict) and self._bridge to be set by MainWindow
    before _build_track_modelling_tab() is called.
    """

    # Group 20A — AI Corner Verify completion signal (thread-safe)
    _tm_ai_corner_verify_signal = pyqtSignal(object)

    # --- Track Modelling tab (Group 17B) ------------------------------------

    def _build_track_modelling_tab(self) -> QWidget:
        """Build the Track Modelling seed inspection tab."""
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel: selection ────────────────────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(260)
        left_scroll.setMaximumWidth(340)
        left_inner = QWidget()
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        left_scroll.setWidget(left_inner)

        _k = f"color: {_TEXT}; font-size: 11px;"
        _v = "color: #AAE4AA; font-size: 11px;"
        _muted = "color: #888; font-size: 11px;"

        # ── Search ──────────────────────────────────────────────────────
        search_grp = QGroupBox("Search")
        search_grp.setStyleSheet(self._group_style())
        search_layout = QVBoxLayout(search_grp)
        search_row = QHBoxLayout()
        self._tm_search_input = QLineEdit()
        self._tm_search_input.setPlaceholderText("Track name or alias…")
        self._tm_search_input.setStyleSheet(
            f"background:{_DARK_CARD}; color:{_TEXT}; border:1px solid #555;"
            f" border-radius:3px; padding:3px 6px; font-size:11px;"
        )
        self._tm_search_btn = QPushButton("Search")
        self._tm_search_btn.setFixedWidth(60)
        search_row.addWidget(self._tm_search_input)
        search_row.addWidget(self._tm_search_btn)
        search_layout.addLayout(search_row)
        self._tm_search_results = QListWidget()
        self._tm_search_results.setMaximumHeight(120)
        self._tm_search_results.setStyleSheet(
            f"background:{_DARK_CARD}; color:{_TEXT}; font-size:11px;"
            f" border:1px solid #444;"
        )
        self._tm_search_results.hide()
        search_layout.addWidget(self._tm_search_results)
        left_layout.addWidget(search_grp)

        # ── Track / Layout selection ─────────────────────────────────────
        sel_grp = QGroupBox("Track Selection")
        sel_grp.setStyleSheet(self._group_style())
        sel_form = QFormLayout(sel_grp)
        sel_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._tm_location_combo = QComboBox()
        self._tm_location_combo.setStyleSheet(
            f"QComboBox {{ background:{_DARK_CARD}; color:{_TEXT}; border:1px solid #555;"
            f" border-radius:3px; padding:2px 4px; font-size:11px; }}"
            f"QComboBox QAbstractItemView {{ background:{_DARK_CARD}; color:{_TEXT}; }}"
        )
        self._tm_layout_combo = QComboBox()
        self._tm_layout_combo.setStyleSheet(
            f"QComboBox {{ background:{_DARK_CARD}; color:{_TEXT}; border:1px solid #555;"
            f" border-radius:3px; padding:2px 4px; font-size:11px; }}"
            f"QComboBox QAbstractItemView {{ background:{_DARK_CARD}; color:{_TEXT}; }}"
        )
        sel_form.addRow(QLabel("Location:", styleSheet=_k), self._tm_location_combo)
        sel_form.addRow(QLabel("Layout:",   styleSheet=_k), self._tm_layout_combo)
        left_layout.addWidget(sel_grp)

        # ── Seed status ──────────────────────────────────────────────────
        status_grp = QGroupBox("Seed Status")
        status_grp.setStyleSheet(self._group_style())
        status_layout = QVBoxLayout(status_grp)
        self._tm_seed_status_lbl = QLabel("Loading seed…")
        self._tm_seed_status_lbl.setStyleSheet(_muted)
        self._tm_seed_status_lbl.setWordWrap(True)
        status_layout.addWidget(self._tm_seed_status_lbl)
        left_layout.addWidget(status_grp)

        left_layout.addStretch()
        splitter.addWidget(left_scroll)

        # ── Right panel: details ─────────────────────────────────────────
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_inner = QWidget()
        right_layout = QVBoxLayout(right_inner)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)
        right_scroll.setWidget(right_inner)

        # Seed warning banner
        self._tm_warning_grp = QGroupBox("Seed Data Warning")
        self._tm_warning_grp.setStyleSheet(
            "QGroupBox { color: #F5C542; border: 1px solid #F5A623; "
            "border-radius: 6px; margin-top: 8px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #F5C542; }"
        )
        warn_layout = QVBoxLayout(self._tm_warning_grp)
        self._tm_warning_lbl = QLabel()
        self._tm_warning_lbl.setStyleSheet(
            "color: #F5C542; font-size: 11px; background: #2A1A00;"
            " border-radius: 4px; padding: 6px;"
        )
        self._tm_warning_lbl.setWordWrap(True)
        warn_layout.addWidget(self._tm_warning_lbl)
        right_layout.addWidget(self._tm_warning_grp)

        # Layout facts
        facts_grp = QGroupBox("Layout Facts")
        facts_grp.setStyleSheet(self._group_style())
        self._tm_facts_form = QFormLayout(facts_grp)
        self._tm_facts_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._tm_fact_labels: dict[str, QLabel] = {}

        _fact_keys = [
            "Track Location", "Location ID", "Aliases",
            "Country", "Region", "Classification", "Surface", "Track Type",
            "Layout", "Layout ID", "Direction",
            "Length", "Corners", "Sectors", "Longest Straight",
            "Elevation Change", "Avg Gradient", "Pit Delta",
            "Reversible", "Rain Supported", "Night Supported", "24h Supported",
            "Modelling Status", "Validation Status",
            "Source Confidence", "Source URL", "Notes",
        ]
        for key in _fact_keys:
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(_muted)
            val_lbl.setWordWrap(True)
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._tm_facts_form.addRow(QLabel(f"{key}:", styleSheet=_k), val_lbl)
            self._tm_fact_labels[key] = val_lbl
        # ── Section 1: Seed Data (Group 23A) ────────────────────────────────
        _seed_data_grp = QGroupBox("1. Seed Data")
        _seed_data_grp.setStyleSheet(self._group_style())
        _seed_data_layout = QVBoxLayout(_seed_data_grp)
        _seed_data_layout.setContentsMargins(6, 12, 6, 6)
        _seed_data_layout.setSpacing(6)
        _seed_data_layout.addWidget(facts_grp)

        # Calibration readiness
        readiness_grp = QGroupBox("Calibration Readiness")
        readiness_grp.setStyleSheet(self._group_style())
        self._tm_readiness_form = QFormLayout(readiness_grp)
        self._tm_readiness_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._tm_readiness_labels: dict[str, QLabel] = {}

        _readiness_keys = [
            "Modelling Status", "Seed Data Only",
            "Ready for Calibration", "Ready for AI Use", "Missing Steps",
        ] + [f"  Step {i}" for i in range(1, 8)]
        for key in _readiness_keys:
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(_muted)
            val_lbl.setWordWrap(True)
            self._tm_readiness_form.addRow(QLabel(f"{key}:", styleSheet=_k), val_lbl)
            self._tm_readiness_labels[key] = val_lbl
        _seed_data_layout.addWidget(readiness_grp)

        # Calibration car
        car_grp = QGroupBox("Calibration Car — Porsche 911 RSR (991) '17")
        car_grp.setStyleSheet(self._group_style())
        car_layout = QVBoxLayout(car_grp)
        self._tm_car_form = QFormLayout()
        self._tm_car_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._tm_car_labels: dict[str, QLabel] = {}

        _car_keys = ["Car", "Class", "Drivetrain", "Power", "Weight", "Tyres", "Purpose", "PP (stock)"]
        for key in _car_keys:
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(_v)
            self._tm_car_form.addRow(QLabel(f"{key}:", styleSheet=_k), val_lbl)
            self._tm_car_labels[key] = val_lbl
        car_layout.addLayout(self._tm_car_form)

        self._tm_car_note_lbl = QLabel(CALIBRATION_CAR_BOUNDARY_NOTE)
        self._tm_car_note_lbl.setStyleSheet(
            "color: #F5C542; font-size: 10px; font-style: italic;"
            " background: #1A1400; border-radius: 4px; padding: 6px; margin-top: 4px;"
        )
        self._tm_car_note_lbl.setWordWrap(True)
        car_layout.addWidget(self._tm_car_note_lbl)
        _seed_data_layout.addWidget(car_grp)

        # Prompt preview
        prompt_grp = QGroupBox("AI Prompt Preview (Seed Only — Read Only)")
        prompt_grp.setStyleSheet(self._group_style())
        prompt_layout = QVBoxLayout(prompt_grp)
        prompt_warn = QLabel(
            "Seed-only preview. Corner/segment/camber/kerb/elevation details are NOT "
            "validated unless calibrated. Public data is a starting point only."
        )
        prompt_warn.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        prompt_warn.setWordWrap(True)
        prompt_layout.addWidget(prompt_warn)
        self._tm_prompt_txt = QPlainTextEdit()
        self._tm_prompt_txt.setReadOnly(True)
        self._tm_prompt_txt.setMinimumHeight(180)
        self._tm_prompt_txt.setStyleSheet(
            f"QPlainTextEdit {{ background:{_DARK_CARD}; color:{_TEXT};"
            f" border:1px solid #444; border-radius:4px; padding:6px; font-size:11px; }}"
        )
        prompt_layout.addWidget(self._tm_prompt_txt)
        _seed_data_layout.addWidget(prompt_grp)
        right_layout.addWidget(_seed_data_grp)

        # ── Section 2: Calibration (Group 23A) ──────────────────────────────
        _cal_section_grp = QGroupBox("2. Calibration")
        _cal_section_grp.setStyleSheet(self._group_style())
        _cal_section_layout = QVBoxLayout(_cal_section_grp)
        _cal_section_layout.setContentsMargins(6, 12, 6, 6)
        _cal_section_layout.setSpacing(6)

        # Calibration controls (Group 17D — live wired)
        cal_grp = QGroupBox("Calibration Session")
        cal_grp.setStyleSheet(self._group_style())
        cal_layout = QVBoxLayout(cal_grp)

        _btn_style = (
            f"QPushButton {{ background: #2A3A2A; color: #AAE4AA; border: 1px solid #4A6A4A;"
            f" border-radius: 4px; padding: 4px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #3A4A3A; }}"
            f"QPushButton:disabled {{ background: #222; color: #555; border-color: #333; }}"
        )
        self._tm_btn_start_cal = QPushButton("Start Calibration Session")
        self._tm_btn_start_cal.setStyleSheet(_btn_style)
        self._tm_btn_start_cal.setEnabled(False)
        self._tm_btn_start_cal.setToolTip("Select a track layout, then click to begin recording")
        cal_layout.addWidget(self._tm_btn_start_cal)

        self._tm_btn_stop_cal = QPushButton("Stop Recording")
        self._tm_btn_stop_cal.setStyleSheet(_btn_style)
        self._tm_btn_stop_cal.setEnabled(False)
        self._tm_btn_stop_cal.setToolTip("Stop the active calibration session")
        cal_layout.addWidget(self._tm_btn_stop_cal)

        self._tm_btn_build_path = QPushButton("Build Reference Path")
        self._tm_btn_build_path.setStyleSheet(_btn_style)
        self._tm_btn_build_path.setEnabled(False)
        self._tm_btn_build_path.setToolTip("Requires at least 2 usable calibration laps")
        cal_layout.addWidget(self._tm_btn_build_path)

        self._tm_btn_save_path = QPushButton("Save Reference Path")
        self._tm_btn_save_path.setStyleSheet(_btn_style)
        self._tm_btn_save_path.setEnabled(False)
        self._tm_btn_save_path.setToolTip("Export the built reference path to JSON")
        cal_layout.addWidget(self._tm_btn_save_path)

        self._tm_btn_ai_corner_verify = QPushButton("AI Corner Verify")
        self._tm_btn_ai_corner_verify.setStyleSheet(_btn_style)
        self._tm_btn_ai_corner_verify.setEnabled(False)
        self._tm_btn_ai_corner_verify.setToolTip(
            "Run AI verification of corner assignments against the station map"
        )
        cal_layout.addWidget(self._tm_btn_ai_corner_verify)

        self._tm_btn_detect_segs = QPushButton("Detect Segments")
        self._tm_btn_detect_segs.setStyleSheet(_btn_style)
        self._tm_btn_detect_segs.setEnabled(False)
        self._tm_btn_detect_segs.setToolTip(
            "Automatically detect track segments from calibration laps (requires built reference path)"
        )
        cal_layout.addWidget(self._tm_btn_detect_segs)

        _lbl_s = "color: #888; font-size: 10px;"
        self._tm_lbl_packet_age = QLabel("No packets received")   # Group 17M
        self._tm_lbl_packet_age.setStyleSheet(_lbl_s)
        cal_layout.addWidget(self._tm_lbl_packet_age)

        self._tm_lbl_sample_count = QLabel("Samples: 0  |  Lap: —")
        self._tm_lbl_sample_count.setStyleSheet(_lbl_s)
        cal_layout.addWidget(self._tm_lbl_sample_count)

        self._tm_lbl_lap_info = QLabel("Laps: 0  |  Usable: 0  |  Rejected: 0")
        self._tm_lbl_lap_info.setStyleSheet(_lbl_s)
        cal_layout.addWidget(self._tm_lbl_lap_info)

        self._tm_lbl_build_info = QLabel("Path: —  |  Confidence: —")
        self._tm_lbl_build_info.setStyleSheet(_lbl_s)
        cal_layout.addWidget(self._tm_lbl_build_info)

        self._tm_lbl_cal_status = QLabel("No calibration session active")
        self._tm_lbl_cal_status.setStyleSheet(_lbl_s)
        self._tm_lbl_cal_status.setWordWrap(True)
        cal_layout.addWidget(self._tm_lbl_cal_status)

        self._tm_lbl_save_path = QLabel("")
        self._tm_lbl_save_path.setStyleSheet("color: #6A9A6A; font-size: 10px;")
        self._tm_lbl_save_path.setWordWrap(True)
        cal_layout.addWidget(self._tm_lbl_save_path)

        self._tm_lbl_seg_summary = QLabel("Segments: — | Corners: —")
        self._tm_lbl_seg_summary.setStyleSheet(_lbl_s)
        cal_layout.addWidget(self._tm_lbl_seg_summary)

        self._tm_lbl_seg_expected = QLabel("Expected corners: —")
        self._tm_lbl_seg_expected.setStyleSheet(_lbl_s)
        cal_layout.addWidget(self._tm_lbl_seg_expected)

        self._tm_lbl_seg_status = QLabel("")
        self._tm_lbl_seg_status.setStyleSheet("color: #6A9A6A; font-size: 10px;")
        self._tm_lbl_seg_status.setWordWrap(True)
        cal_layout.addWidget(self._tm_lbl_seg_status)

        self._tm_lbl_pit_lane_status = QLabel("Pit lane: not detected")
        self._tm_lbl_pit_lane_status.setStyleSheet("color: #888888; font-size: 10px;")
        self._tm_lbl_pit_lane_status.setWordWrap(True)
        cal_layout.addWidget(self._tm_lbl_pit_lane_status)

        _cal_section_layout.addWidget(cal_grp)
        right_layout.addWidget(_cal_section_grp)

        # ── Section 3: Segment Detection (Group 23A) ─────────────────────────
        _seg_detect_grp = QGroupBox("3. Segment Detection")
        _seg_detect_grp.setStyleSheet(self._group_style())
        _seg_detect_layout = QVBoxLayout(_seg_detect_grp)
        _seg_detect_layout.setContentsMargins(6, 12, 6, 6)
        _seg_detect_layout.setSpacing(6)

        # ── Station Map Canvas (Group 17O) ────────────────────────────────
        map_grp = QGroupBox("Station Map")
        map_grp.setStyleSheet(self._group_style())
        map_grp_layout = QVBoxLayout(map_grp)
        self._tm_map_widget = TrackMapWidget()
        self._tm_map_widget.setMinimumHeight(300)
        map_grp_layout.addWidget(self._tm_map_widget)
        self._tm_map_note_lbl = QLabel(
            "Build Reference Path to generate the 1 m station map."
        )
        self._tm_map_note_lbl.setStyleSheet("color: #888; font-size: 10px;")
        map_grp_layout.addWidget(self._tm_map_note_lbl)
        _seg_detect_layout.addWidget(map_grp)

        # ── Segment Diagnostics (Group 17F / 17P) ────────────────────────
        seg_rev_grp = QGroupBox("Segment Diagnostics")
        seg_rev_grp.setStyleSheet(self._group_style())
        seg_rev_layout = QVBoxLayout(seg_rev_grp)

        _warn_note = QLabel(
            "Detected segments are CANDIDATES — not engineer-validated until reviewed. "
            "Car-specific segments (braking/traction/gear) reflect Porsche RSR behaviour only."
        )
        _warn_note.setStyleSheet("color: #F5C542; font-size: 10px; font-style: italic;")
        _warn_note.setWordWrap(True)
        seg_rev_layout.addWidget(_warn_note)

        # Segment table (read-only cells, row selection)
        _tbl_cols = ["Name", "Turn", "Type", "Progress", "Conf", "Laps", "Status", "Warnings"]
        self._tm_seg_table = QTableWidget(0, len(_tbl_cols))
        self._tm_seg_table.setHorizontalHeaderLabels(_tbl_cols)
        self._tm_seg_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tm_seg_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tm_seg_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tm_seg_table.horizontalHeader().setStretchLastSection(True)
        self._tm_seg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tm_seg_table.setMinimumHeight(160)
        self._tm_seg_table.setMaximumHeight(280)
        self._tm_seg_table.setStyleSheet(
            f"QTableWidget {{ background:{_DARK_CARD}; color:{_TEXT}; font-size:11px;"
            f" border:1px solid #444; gridline-color:#333; }}"
            f"QHeaderView::section {{ background:#1E2A1E; color:#AAE4AA; font-size:10px;"
            f" border:none; padding:2px; }}"
            f"QTableWidget::item:selected {{ background:#2A4A2A; }}"
        )
        seg_rev_layout.addWidget(self._tm_seg_table)

        # Manual review buttons — hidden in Group 17P (whole-model acceptance replaces per-segment workflow)
        _rev_btn_s = (
            f"QPushButton {{ background:#2A2A3A; color:#AAAAEE; border:1px solid #4A4A6A;"
            f" border-radius:3px; padding:3px 8px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#3A3A4A; }}"
            f"QPushButton:disabled {{ background:#222; color:#555; border-color:#333; }}"
        )
        _rev_btn_orange = (
            f"QPushButton {{ background:#3A2A1A; color:#F5A623; border:1px solid #7A5A2A;"
            f" border-radius:3px; padding:3px 8px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#4A3A2A; }}"
            f"QPushButton:disabled {{ background:#222; color:#555; border-color:#333; }}"
        )
        _rev_btn_red = (
            f"QPushButton {{ background:#3A1A1A; color:#EE8888; border:1px solid #6A3A3A;"
            f" border-radius:3px; padding:3px 8px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#4A2A2A; }}"
            f"QPushButton:disabled {{ background:#222; color:#555; border-color:#333; }}"
        )
        _rev_btn_green = (
            f"QPushButton {{ background:#1A3A1A; color:#88EE88; border:1px solid #3A6A3A;"
            f" border-radius:3px; padding:3px 8px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#2A4A2A; }}"
            f"QPushButton:disabled {{ background:#222; color:#555; border-color:#333; }}"
        )

        # Hidden legacy per-segment buttons (references kept to avoid AttributeError in handler methods)
        self._tm_btn_rev_confirm    = QPushButton("Confirm");    self._tm_btn_rev_confirm.hide()
        self._tm_btn_rev_rename     = QPushButton("Rename");     self._tm_btn_rev_rename.hide()
        self._tm_btn_rev_reject     = QPushButton("Reject");     self._tm_btn_rev_reject.hide()
        self._tm_btn_rev_needs_laps = QPushButton("Needs More Laps"); self._tm_btn_rev_needs_laps.hide()
        self._tm_btn_rev_split      = QPushButton("Split Required");  self._tm_btn_rev_split.hide()
        self._tm_btn_rev_merge      = QPushButton("Merge Required");  self._tm_btn_rev_merge.hide()
        self._tm_btn_rev_save       = QPushButton("Save Reviewed Model"); self._tm_btn_rev_save.hide()
        self._tm_lbl_rev_save_path  = QLabel(""); self._tm_lbl_rev_save_path.hide()

        _seg_detect_layout.addWidget(seg_rev_grp)
        right_layout.addWidget(_seg_detect_grp)

        # ── Section 4: Segment Review (Group 23A) ────────────────────────────
        _seg_review_grp = QGroupBox("4. Segment Review")
        _seg_review_grp.setStyleSheet(self._group_style())
        _seg_review_layout = QVBoxLayout(_seg_review_grp)
        _seg_review_layout.setContentsMargins(6, 12, 6, 6)
        _seg_review_layout.setSpacing(6)

        # ── Track Model Alignment Panel (Group 17P) ────────────────────────
        approval_grp = QGroupBox("Track Model Alignment")
        approval_grp.setStyleSheet(self._group_style())
        approval_form = QFormLayout(approval_grp)
        approval_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        _ap_val_s = "color: #AAE4AA; font-size: 11px;"
        _ap_key_s = f"color: {_TEXT}; font-size: 11px;"

        def _ap_row(label: str, attr_name: str) -> QLabel:
            lbl = QLabel("—")
            lbl.setStyleSheet(_ap_val_s)
            lbl.setWordWrap(True)
            lbl.setMinimumWidth(120)
            approval_form.addRow(QLabel(f"{label}:", styleSheet=_ap_key_s), lbl)
            setattr(self, attr_name, lbl)
            return lbl

        # New alignment status rows
        _ap_row("Workflow state",      "_tm_al_workflow_state")
        _ap_row("Match status",        "_tm_al_match_status")
        _ap_row("Seed corners",        "_tm_al_seed_corners")
        _ap_row("Model corners",       "_tm_al_model_corners")
        _ap_row("Extra peaks suppressed", "_tm_al_extra_peaks")
        _ap_row("Placeholders",        "_tm_al_placeholders")
        _ap_row("Seed source",          "_tm_al_seed_source")
        _ap_row("Seed truth source",    "_tm_al_seed_truth_source")
        _ap_row("Seed data available",  "_tm_al_seed_audit")
        _ap_row("Seed corner positions","_tm_al_seed_position_status")
        _ap_row("Corners matched",     "_tm_al_corners_matched")
        _ap_row("Corner pos match",    "_tm_al_corner_position_match")
        _ap_row("Lap length (model)",  "_tm_al_lap_model")
        _ap_row("Lap length (seed)",   "_tm_al_lap_seed")
        _ap_row("Lap delta",           "_tm_al_lap_delta")
        _ap_row("Geometry match",      "_tm_al_geometry_match")
        _ap_row("Stations",            "_tm_al_stations")
        _ap_row("Confidence",          "_tm_al_confidence")
        _ap_row("Accepted at",         "_tm_al_accepted_at")

        self._tm_al_blockers = QLabel("")
        self._tm_al_blockers.setStyleSheet("color: #EE9955; font-size: 10px;")
        self._tm_al_blockers.setWordWrap(True)
        approval_form.addRow(QLabel("Blockers:", styleSheet=_ap_key_s), self._tm_al_blockers)

        self._tm_al_warnings = QLabel("")
        self._tm_al_warnings.setStyleSheet("color: #CC9933; font-size: 10px;")
        self._tm_al_warnings.setWordWrap(True)
        approval_form.addRow(QLabel("Warnings:", styleSheet=_ap_key_s), self._tm_al_warnings)

        self._tm_al_sector_note = QLabel("")
        self._tm_al_sector_note.setStyleSheet("color: #888; font-size: 10px;")
        self._tm_al_sector_note.setWordWrap(True)
        approval_form.addRow(QLabel("Sectors:", styleSheet=_ap_key_s), self._tm_al_sector_note)

        # Accept / Rebuild buttons
        _acc_row = QHBoxLayout()
        _btn_accept_s = (
            f"QPushButton {{ background:#1A3A1A; color:#88EE88; border:1px solid #3A6A3A;"
            f" border-radius:4px; padding:5px 12px; font-size:11px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#2A4A2A; }}"
            f"QPushButton:disabled {{ background:#1A1A1A; color:#3A5A3A; border-color:#2A3A2A; }}"
        )
        _btn_rebuild_s = (
            f"QPushButton {{ background:#2A1A00; color:#F5A623; border:1px solid #6A4A10;"
            f" border-radius:4px; padding:5px 12px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#3A2A10; }}"
            f"QPushButton:disabled {{ background:#1A1A1A; color:#555; border-color:#333; }}"
        )
        self._tm_btn_accept = QPushButton("Accept Track Model")
        self._tm_btn_accept.setStyleSheet(_btn_accept_s)
        self._tm_btn_accept.setEnabled(False)
        self._tm_btn_accept.setToolTip(
            "Accept the whole-model alignment result and save this track model as official"
        )
        self._tm_btn_rebuild = QPushButton("Rebuild / Recalibrate")
        self._tm_btn_rebuild.setStyleSheet(_btn_rebuild_s)
        self._tm_btn_rebuild.setEnabled(False)
        self._tm_btn_rebuild.setToolTip(
            "Clear the built station map and require full recalibration. "
            "Use this if the track map looks wrong or was built from bad data. "
            "After resetting, drive clean calibration laps to rebuild the model."
        )
        _acc_row.addWidget(self._tm_btn_accept)
        _acc_row.addWidget(self._tm_btn_rebuild)
        approval_form.addRow(_acc_row)

        self._tm_al_seed_overlay_note = QLabel(
            "Seed centreline: not available in GT7 seed data — showing telemetry-derived model only."
        )
        self._tm_al_seed_overlay_note.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        self._tm_al_seed_overlay_note.setWordWrap(True)
        approval_form.addRow(self._tm_al_seed_overlay_note)

        _seg_review_layout.addWidget(approval_grp)

        # ── Track Model Status Panel (Group 17G; renamed from "Resolver
        #    Status" in the Product Consolidation Sprint — "resolver" is an
        #    internal term, not user language) ───────────────────────────────
        resolver_grp = QGroupBox("Track Model Status")
        resolver_grp.setStyleSheet(self._group_style())
        resolver_form = QFormLayout(resolver_grp)
        resolver_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        _rs_val_s = "color: #AAE4AA; font-size: 11px;"
        _rs_key_s = f"color: {_TEXT}; font-size: 11px;"

        def _rs_row(label: str, attr_name: str) -> QLabel:
            lbl = QLabel("—")
            lbl.setStyleSheet(_rs_val_s)
            resolver_form.addRow(QLabel(f"{label}:", styleSheet=_rs_key_s), lbl)
            setattr(self, attr_name, lbl)
            return lbl

        _rs_row("Source",           "_tm_rs_source")
        _rs_row("Status",           "_tm_rs_modelling_status")
        _rs_row("AI-ready",         "_tm_rs_ai_ready")
        _rs_row("Candidates",       "_tm_rs_candidates")
        _rs_row("Latest file",      "_tm_rs_path")

        self._tm_rs_blockers = QLabel("")
        self._tm_rs_blockers.setStyleSheet("color: #EE9955; font-size: 10px;")
        self._tm_rs_blockers.setWordWrap(True)
        resolver_form.addRow(QLabel("Blockers:", styleSheet=_rs_key_s), self._tm_rs_blockers)

        self._tm_rs_warnings = QLabel("")
        self._tm_rs_warnings.setStyleSheet("color: #CC9933; font-size: 10px;")
        self._tm_rs_warnings.setWordWrap(True)
        resolver_form.addRow(QLabel("Warnings:", styleSheet=_rs_key_s), self._tm_rs_warnings)

        _seg_review_layout.addWidget(resolver_grp)

        # ── Lap Offset Calibration Panel (Group 17M) ───────────────────────
        offset_grp = QGroupBox("Lap Offset Calibration")
        offset_grp.setStyleSheet(self._group_style())
        offset_layout = QVBoxLayout(offset_grp)

        _off_note = QLabel(
            "Lap offset calibration maps the car's in-lap road distance to lap-distance "
            "percentage. Status: Not loaded — no offset set; Zero offset — provisional "
            "(car assumed to start at S/F line); Calibrated — verified offset from a "
            "known-start lap. Zero offset is provisional: validate at the Start/Finish "
            "line before trusting road_distance → lap_distance mapping."
        )
        _off_note.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        _off_note.setWordWrap(True)
        offset_layout.addWidget(_off_note)

        _off_btn_s = (
            f"QPushButton {{ background: #2A2A3A; color: #AAAAEE; border: 1px solid #4A4A6A;"
            f" border-radius: 4px; padding: 4px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #3A3A4A; }}"
            f"QPushButton:disabled {{ background: #222; color: #555; border-color: #333; }}"
        )

        _off_row = QHBoxLayout()
        self._tm_btn_create_zero_offset = QPushButton("Create Zero Offset")
        self._tm_btn_create_zero_offset.setStyleSheet(_off_btn_s)
        self._tm_btn_create_zero_offset.setEnabled(False)
        self._tm_btn_create_zero_offset.setToolTip(
            "Create a provisional 0 m offset — assumes car starts at S/F line. "
            "Requires track length from seed or reference path."
        )
        _off_row.addWidget(self._tm_btn_create_zero_offset)

        self._tm_btn_load_offset = QPushButton("Load Offset")
        self._tm_btn_load_offset.setStyleSheet(_off_btn_s)
        self._tm_btn_load_offset.setEnabled(False)
        self._tm_btn_load_offset.setToolTip("Load offset calibration from saved JSON file")
        _off_row.addWidget(self._tm_btn_load_offset)

        self._tm_btn_save_offset = QPushButton("Save Offset")
        self._tm_btn_save_offset.setStyleSheet(_off_btn_s)
        self._tm_btn_save_offset.setEnabled(False)
        self._tm_btn_save_offset.setToolTip("Save current offset calibration to JSON")
        _off_row.addWidget(self._tm_btn_save_offset)
        offset_layout.addLayout(_off_row)

        _off_lbl_s   = "color: #888; font-size: 10px;"
        _off_val_s   = "color: #AAE4AA; font-size: 10px;"
        _off_warn_s  = "color: #F5C542; font-size: 10px;"

        self._tm_lbl_offset_status = QLabel("No offset calibration")
        self._tm_lbl_offset_status.setStyleSheet(_off_lbl_s)
        self._tm_lbl_offset_status.setWordWrap(True)
        offset_layout.addWidget(self._tm_lbl_offset_status)

        self._tm_lbl_offset_detail = QLabel("")
        self._tm_lbl_offset_detail.setStyleSheet(_off_val_s)
        self._tm_lbl_offset_detail.setWordWrap(True)
        offset_layout.addWidget(self._tm_lbl_offset_detail)

        self._tm_lbl_offset_warnings = QLabel("")
        self._tm_lbl_offset_warnings.setStyleSheet(_off_warn_s)
        self._tm_lbl_offset_warnings.setWordWrap(True)
        offset_layout.addWidget(self._tm_lbl_offset_warnings)

        _seg_review_layout.addWidget(offset_grp)

        # ── Seed Geometry (Group 17V) ──────────────────────────────────────
        seed_geo_grp = QGroupBox("Seed Geometry")
        seed_geo_grp.setStyleSheet(self._group_style())
        seed_geo_layout = QVBoxLayout(seed_geo_grp)

        _seed_btn_s = (
            f"QPushButton {{ background: #2A2A3A; color: #AAAAEE; border: 1px solid #4A4A6A;"
            f" border-radius: 4px; padding: 4px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #3A3A4A; }}"
            f"QPushButton:disabled {{ background: #222; color: #555; border-color: #333; }}"
        )
        self._tm_btn_generate_seed = QPushButton("Generate Seed Geometry")
        self._tm_btn_generate_seed.setStyleSheet(_seed_btn_s)
        self._tm_btn_generate_seed.setEnabled(False)
        self._tm_btn_generate_seed.setToolTip("Build a seed coordinate map from the current calibration session")
        seed_geo_layout.addWidget(self._tm_btn_generate_seed)

        self._tm_btn_save_seed = QPushButton("Save to Library")
        self._tm_btn_save_seed.setStyleSheet(_seed_btn_s)
        self._tm_btn_save_seed.setEnabled(False)
        self._tm_btn_save_seed.setToolTip("Save the generated seed geometry to the track library")
        seed_geo_layout.addWidget(self._tm_btn_save_seed)

        self._tm_btn_reload_seed = QPushButton("Reload Seed")
        self._tm_btn_reload_seed.setStyleSheet(_seed_btn_s)
        self._tm_btn_reload_seed.setEnabled(False)
        self._tm_btn_reload_seed.setToolTip("Reload seed geometry from the track library")
        seed_geo_layout.addWidget(self._tm_btn_reload_seed)

        self._tm_seed_geo_status_lbl = QLabel("")
        self._tm_seed_geo_status_lbl.setStyleSheet("color: #AAE4AA; font-size: 10px;")
        self._tm_seed_geo_status_lbl.setWordWrap(True)
        seed_geo_layout.addWidget(self._tm_seed_geo_status_lbl)

        right_layout.addWidget(_seg_review_grp)

        # ── Section 5: Seed Geometry (Group 23A). Renamed from the misleading
        #    "5. Track Model Alignment" (the alignment metrics live in Section 4;
        #    this section only generates/saves/reloads seed geometry) during the
        #    Product Consolidation Sprint. ─────────────────────────────────────
        _tm_align_section_grp = QGroupBox("5. Seed Geometry")
        _tm_align_section_grp.setStyleSheet(self._group_style())
        _tm_align_section_layout = QVBoxLayout(_tm_align_section_grp)
        _tm_align_section_layout.setContentsMargins(6, 12, 6, 6)
        _tm_align_section_layout.setSpacing(6)
        _tm_align_section_layout.addWidget(seed_geo_grp)
        right_layout.addWidget(_tm_align_section_grp)

        # ── Section 6: Track Truth / Mapping (Group 18A) ─────────────────────
        _truth_section_grp = QGroupBox("6. Track Truth / Mapping")
        _truth_section_grp.setStyleSheet(self._group_style())
        _truth_section_layout = QVBoxLayout(_truth_section_grp)
        _truth_section_layout.setContentsMargins(6, 12, 6, 6)
        _truth_section_layout.setSpacing(6)

        truth_grp = QGroupBox("Track Truth / Mapping")
        truth_grp.setStyleSheet(self._group_style())
        truth_form = QFormLayout(truth_grp)
        truth_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        _tt_key_s = f"color: {_TEXT}; font-size: 11px;"
        _tt_val_s = "color: #AAE4AA; font-size: 11px;"

        def _tt_row(label: str, attr_name: str, wrap: bool = False) -> QLabel:
            lbl = QLabel("—")
            lbl.setStyleSheet(_tt_val_s)
            if wrap:
                lbl.setWordWrap(True)
            lbl.setMinimumWidth(120)
            truth_form.addRow(QLabel(f"{label}:", styleSheet=_tt_key_s), lbl)
            setattr(self, attr_name, lbl)
            return lbl

        _tt_row("Track ID",           "_tm_truth_lbl_track_id")
        _tt_row("Layout ID",          "_tm_truth_lbl_layout_id")
        _tt_row("Library",            "_tm_truth_lbl_library_availability")
        _tt_row("Seed geometry",      "_tm_truth_lbl_seed_geometry")
        _tt_row("Corner metadata",    "_tm_truth_lbl_corner_metadata")
        _tt_row("Complex metadata",   "_tm_truth_lbl_complex_metadata")
        _tt_row("Geometry accepted",  "_tm_truth_lbl_geometry_acceptance")
        _tt_row("Live Mapping",       "_tm_truth_lbl_live_mapping_ready")
        _tt_row("AI context",         "_tm_truth_lbl_ai_context_ready")

        self._tm_truth_lbl_blockers = QLabel("—")
        self._tm_truth_lbl_blockers.setStyleSheet("color: #EE9955; font-size: 10px;")
        self._tm_truth_lbl_blockers.setWordWrap(True)
        truth_form.addRow(QLabel("Blockers:", styleSheet=_tt_key_s), self._tm_truth_lbl_blockers)

        self._tm_truth_lbl_warnings = QLabel("—")
        self._tm_truth_lbl_warnings.setStyleSheet("color: #CC9933; font-size: 10px;")
        self._tm_truth_lbl_warnings.setWordWrap(True)
        truth_form.addRow(QLabel("Warnings:", styleSheet=_tt_key_s), self._tm_truth_lbl_warnings)

        self._tm_truth_lbl_status_label = QLabel("—")
        self._tm_truth_lbl_status_label.setStyleSheet("color: #888888; font-size: 11px;")
        self._tm_truth_lbl_status_label.setWordWrap(True)
        truth_form.addRow(QLabel("Status:", styleSheet=_tt_key_s), self._tm_truth_lbl_status_label)

        _truth_section_layout.addWidget(truth_grp)
        right_layout.addWidget(_truth_section_grp)

        right_layout.addStretch()
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        outer_layout.addWidget(splitter)

        # Store seed result reference + review state
        self._tm_seed_result = None
        self._tm_controller = TrackCalibrationCaptureController()
        self._tm_detection_result = None   # last SegmentDetectionResult
        self._tm_review_result    = None   # current TrackModelReviewResult
        self._tm_selected_segment_id: Optional[str] = None
        self._tm_resolver_result  = None   # last TrackModelResolverResult (Group 17G)
        self._tm_offset_calibration = None  # LapStartOffsetCalibration or None (Group 17M)
        self._tm_last_packet_time: Optional[float] = None  # wall-clock of last cal packet (Group 17M)
        self._tm_station_map = None        # TrackStationMap (Group 17O)
        self._tm_seed_build_result: Optional["GeometryBuildResult"] = None   # Group 17V
        self._tm_seed_save_result:  Optional["GeometrySaveResult"]  = None   # Group 17V
        self._tm_seed_geometry_available: bool = False                        # Group 17V
        self._tm_highlight_start_p: float | None = None   # Group 23A — highlight persistence
        self._tm_highlight_end_p:   float | None = None   # Group 23A — highlight persistence

        # Wire signals
        self._tm_location_combo.currentIndexChanged.connect(self._tm_on_location_changed)
        self._tm_layout_combo.currentIndexChanged.connect(self._tm_on_layout_changed)
        self._tm_search_btn.clicked.connect(self._tm_do_search)
        self._tm_search_input.returnPressed.connect(self._tm_do_search)
        self._tm_search_results.itemDoubleClicked.connect(self._tm_on_search_result_selected)

        return outer

    def _tm_on_tab_shown(self) -> None:
        """Called when the Track Modelling tab is first shown or re-shown."""
        if self._tm_seed_result is not None:
            return  # already loaded
        try:
            result = load_track_seed()
            self._tm_seed_result = result
            self._tm_seed_status_lbl.setText(describe_seed_load_status(result))
            self._tm_seed_status_lbl.setStyleSheet(
                "color: #2EA043; font-size: 11px;" if result.success
                else "color: #F44336; font-size: 11px;"
            )
            if result.success:
                self._tm_populate_location_combo()
                self._tm_populate_calibration_car()
        except Exception as exc:
            self._tm_seed_status_lbl.setText(f"Error loading seed: {exc}")
            self._tm_seed_status_lbl.setStyleSheet("color: #F44336; font-size: 11px;")

    def _tm_populate_location_combo(self) -> None:
        if self._tm_seed_result is None:
            return
        items = build_location_display_items(self._tm_seed_result)
        self._tm_location_combo.blockSignals(True)
        self._tm_location_combo.clear()
        self._tm_location_combo.addItem("— Select track —", "")
        for display, loc_id in items:
            self._tm_location_combo.addItem(display, loc_id)
        self._tm_location_combo.blockSignals(False)

    def _tm_on_location_changed(self) -> None:
        if self._tm_seed_result is None:
            return
        loc_id = self._tm_location_combo.currentData() or ""
        self._tm_layout_combo.blockSignals(True)
        self._tm_layout_combo.clear()
        if not loc_id:
            self._tm_layout_combo.addItem("— Select track first —", "")
            self._tm_layout_combo.blockSignals(False)
            self._tm_clear_detail_panels()
            return
        items = build_layout_display_items(self._tm_seed_result, loc_id)
        self._tm_layout_combo.addItem("— Select layout —", "")
        for display, lay_id in items:
            self._tm_layout_combo.addItem(display, lay_id)
        self._tm_layout_combo.blockSignals(False)
        self._tm_clear_detail_panels()

    def _tm_on_layout_changed(self) -> None:
        # Group 24 AC1: clear stale highlight bounds from previous track
        self._tm_highlight_start_p = None
        self._tm_highlight_end_p = None
        # Group 24 AC2: reset pit-lane guard on layout change
        self._pit_lane_active = False
        if self._tm_seed_result is None:
            return
        loc_id = self._tm_location_combo.currentData() or ""
        lay_id = self._tm_layout_combo.currentData() or ""
        if not loc_id or not lay_id:
            self._tm_clear_detail_panels()
            return
        # Persist selected track/layout IDs for AI prompt injection (Group 17H)
        self._config.setdefault("strategy", {})["track_location_id"] = loc_id
        self._config.setdefault("strategy", {})["layout_id"] = lay_id
        self._tm_refresh_details(loc_id, lay_id)
        self._tm_refresh_resolver()
        self._tm_update_cal_buttons()
        # DEF-17M-UAT-003: audit saved files on disk so user sees existing data after restart
        self._tm_audit_and_show_saved_files(loc_id, lay_id)
        # DEF-17O-UAT-008: auto-load persisted station map if available for this layout
        self._tm_try_load_station_map_from_disk(loc_id, lay_id)
        # Group 17P: load previously accepted alignment result if available
        self._tm_try_load_accepted_model(loc_id, lay_id)
        # Group 18A: refresh Track Truth / Mapping panel
        self._tm_refresh_track_truth_panel()

    def _tm_clear_detail_panels(self) -> None:
        _muted = "color: #888; font-size: 11px;"
        for lbl in self._tm_fact_labels.values():
            lbl.setText("—")
            lbl.setStyleSheet(_muted)
        for lbl in self._tm_readiness_labels.values():
            lbl.setText("—")
            lbl.setStyleSheet(_muted)
        self._tm_warning_lbl.setText("")
        self._tm_prompt_txt.setPlainText("")
        self._tm_update_cal_buttons()

    def _tm_refresh_details(self, loc_id: str, lay_id: str) -> None:
        if self._tm_seed_result is None:
            return
        _v = "color: #AAE4AA; font-size: 11px;"
        _muted = "color: #888; font-size: 11px;"
        _warn = "color: #F5C542; font-size: 11px;"
        _UNKNOWN = "Unknown / needs calibration"

        loc = get_selected_location(self._tm_seed_result, loc_id)
        lay = get_selected_layout(self._tm_seed_result, loc_id, lay_id)
        if loc is None or lay is None:
            self._tm_clear_detail_panels()
            return

        # ── Layout facts ───────────────────────────────────────────────
        try:
            facts = format_layout_facts(lay, loc)
            for label_key, value in facts:
                lbl = self._tm_fact_labels.get(label_key)
                if lbl is not None:
                    lbl.setText(value)
                    if value == _UNKNOWN:
                        lbl.setStyleSheet(_warn)
                    else:
                        lbl.setStyleSheet(_v)
        except Exception:
            pass

        # ── Calibration readiness ──────────────────────────────────────
        try:
            readiness = format_readiness(lay)
            # Hide all step labels first
            for key, lbl in self._tm_readiness_labels.items():
                if key.startswith("  Step"):
                    lbl.setText("—")
                    lbl.setStyleSheet(_muted)
                    lbl.hide()
            for key_label, _ in self._tm_readiness_form.findChildren(QLabel):
                pass
            for label_key, value in readiness:
                lbl = self._tm_readiness_labels.get(label_key)
                if lbl is not None:
                    lbl.setText(value)
                    lbl.show()
                    if "No" in value or "needed" in value.lower():
                        lbl.setStyleSheet(_warn)
                    elif value == "—":
                        lbl.setStyleSheet(_muted)
                    else:
                        lbl.setStyleSheet(_v)
        except Exception:
            pass

        # ── Seed warning banner ────────────────────────────────────────
        try:
            warn_text = get_seed_warning_text(lay)
            self._tm_warning_lbl.setText(warn_text)
            self._tm_warning_grp.setVisible(bool(warn_text))
        except Exception:
            pass

        # ── Prompt preview ─────────────────────────────────────────────
        try:
            prompt = build_prompt_preview(self._tm_seed_result, loc_id, lay_id)
            self._tm_prompt_txt.setPlainText(prompt)
        except Exception as exc:
            self._tm_prompt_txt.setPlainText(f"Error building prompt preview: {exc}")

    def _tm_populate_calibration_car(self) -> None:
        if self._tm_seed_result is None or not self._tm_seed_result.calibration_cars:
            return
        _v = "color: #AAE4AA; font-size: 11px;"
        car = self._tm_seed_result.calibration_cars[0]
        try:
            car_rows = format_calibration_car(car)
            for label_key, value in car_rows:
                lbl = self._tm_car_labels.get(label_key)
                if lbl is not None:
                    lbl.setText(value)
                    lbl.setStyleSheet(_v)
        except Exception:
            pass

    def _tm_do_search(self) -> None:
        query = self._tm_search_input.text().strip()
        if not query or self._tm_seed_result is None:
            self._tm_search_results.hide()
            return
        try:
            layouts = _ti_search(query)
            self._tm_search_results.clear()
            if not layouts:
                self._tm_search_results.addItem("No results")
                self._tm_search_results.show()
                return
            for lay in layouts[:30]:
                loc = get_selected_location(self._tm_seed_result, lay.track_location_id)
                loc_name = loc.display_name if loc else lay.track_location_id
                item_text = f"{loc_name} — {lay.display_name}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, (lay.track_location_id, lay.layout_id))
                self._tm_search_results.addItem(item)
            self._tm_search_results.show()
        except Exception as exc:
            self._tm_search_results.clear()
            self._tm_search_results.addItem(f"Search error: {exc}")
            self._tm_search_results.show()

    def _tm_on_search_result_selected(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        loc_id, lay_id = data
        # Select the location in the combo
        for i in range(self._tm_location_combo.count()):
            if self._tm_location_combo.itemData(i) == loc_id:
                self._tm_location_combo.setCurrentIndex(i)
                break
        # Select the layout in the combo
        for i in range(self._tm_layout_combo.count()):
            if self._tm_layout_combo.itemData(i) == lay_id:
                self._tm_layout_combo.setCurrentIndex(i)
                break
        self._tm_search_results.hide()

    # ── Calibration session (Group 17D) ──────────────────────────────────────

    def _tm_update_cal_buttons(self) -> None:
        """Refresh enabled state of all calibration and offset buttons from controller state."""
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is None:
            return
        loc_id = (self._tm_location_combo.currentData() or "").strip()
        lay_id = (self._tm_layout_combo.currentData() or "").strip()
        has_track = bool(loc_id) and bool(lay_id)
        self._tm_btn_start_cal.setEnabled(ctrl.can_start and has_track)
        self._tm_btn_stop_cal.setEnabled(ctrl.can_stop)
        self._tm_btn_build_path.setEnabled(ctrl.can_build)
        self._tm_btn_save_path.setEnabled(ctrl.can_save)
        self._tm_btn_detect_segs.setEnabled(ctrl.can_save)

        # AI Corner Verify button (Group 20A)
        if hasattr(self, "_tm_btn_ai_corner_verify"):
            self._tm_btn_ai_corner_verify.setEnabled(
                getattr(self, "_tm_station_map", None) is not None
            )

        # Offset calibration buttons (Group 17M)
        track_length_m   = self._tm_get_track_length_m()
        has_track_length = track_length_m is not None
        has_offset       = getattr(self, "_tm_offset_calibration", None) is not None
        if hasattr(self, "_tm_btn_create_zero_offset"):
            self._tm_btn_create_zero_offset.setEnabled(has_track and has_track_length)
        if hasattr(self, "_tm_btn_load_offset"):
            self._tm_btn_load_offset.setEnabled(has_track)
        if hasattr(self, "_tm_btn_save_offset"):
            self._tm_btn_save_offset.setEnabled(has_offset)

    def _tm_update_cal_status(self) -> None:
        """Refresh all calibration status labels from controller state."""
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is None:
            return
        s = ctrl.get_status_summary()
        state = s["state"]

        if state == "recording":
            status_txt = f"Recording — lap {s['current_lap_number'] or '?'}"
            self._tm_lbl_cal_status.setStyleSheet("color: #AAE4AA; font-size: 10px;")
        elif state == "stopped":
            status_txt = "Stopped — ready to build"
            self._tm_lbl_cal_status.setStyleSheet("color: #E4D0AA; font-size: 10px;")
        elif state == "built":
            status_txt = "Path built — ready to save"
            self._tm_lbl_cal_status.setStyleSheet("color: #AAD0E4; font-size: 10px;")
        elif state == "error":
            status_txt = f"Error: {s['error']}"
            self._tm_lbl_cal_status.setStyleSheet("color: #E4AAAA; font-size: 10px;")
        else:
            status_txt = "No calibration session active"
            self._tm_lbl_cal_status.setStyleSheet("color: #888; font-size: 10px;")

        self._tm_lbl_cal_status.setText(status_txt)
        self._tm_lbl_sample_count.setText(
            f"Samples: {s['total_samples']:,}  |  Lap: {s['current_lap_number'] or '—'}"
            f"  ({s['in_progress_samples']} in progress)"
        )
        # Group 17M UAT DEF-17M-UAT-001: clearer lap count display
        _lci = _format_lap_count_info(s)
        _lap_parts = [_lci["captured_text"]]
        if _lci["quality_text"]:
            _lap_parts.append(_lci["quality_text"])
        self._tm_lbl_lap_info.setText("  |  ".join(_lap_parts))
        self._tm_lbl_lap_info.setToolTip(_lci["explanation"] or "")
        pts = s["reference_path_points"]
        conf = s["confidence"]
        self._tm_lbl_build_info.setText(
            f"Path: {pts} pts  |  Confidence: {conf:.2f}"
            if pts else "Path: —  |  Confidence: —"
        )
        saved = s.get("saved_path", "")
        self._tm_lbl_save_path.setText(f"Saved: {saved}" if saved else "")

    def _tm_on_calibration_packet(self, packet) -> None:
        """Slot: receives subsampled GT7 packet from SignalBridge on Qt main thread."""
        self._tm_last_packet_time = time.time()  # Group 17M: track last packet time
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is None or not ctrl.is_recording:
            self._tm_update_packet_age_label()
            self._tm_update_live_map_dot(packet)
            return
        ctrl.add_sample_from_packet(packet)
        self._tm_update_cal_status()
        self._tm_update_live_map_dot(packet)

    def _tm_update_live_map_dot(self, packet) -> None:
        """Update car dot on both map widgets using the current station map."""
        sm = getattr(self, "_tm_station_map", None)
        if sm is None or not sm.stations:
            return
        try:
            spd = getattr(packet, "car_speed", 0.0) or 0.0
            x   = getattr(packet, "position_x", 0.0) or 0.0
            y   = getattr(packet, "position_y", 0.0) or 0.0
            z   = getattr(packet, "position_z", 0.0) or 0.0
            match_result = _map_match(x, y, z, sm, speed_kph=spd)
            if self._tm_cached_draw_data is None:
                self._tm_cached_draw_data = _build_map_draw_data(sm, match_result=match_result)
            else:
                # Only recompute the car dot; full geometry is unchanged
                if match_result is not None and not match_result.is_pit_likely:
                    idx = match_result.nearest_station_idx
                    if idx < len(sm.stations):
                        import math as _math
                        st = sm.stations[idx]
                        self._tm_cached_draw_data.car_dot = CarDot(
                            x          = st.x + match_result.lateral_offset_m * _math.cos(st.heading_rad),
                            y          = st.z - match_result.lateral_offset_m * _math.sin(st.heading_rad),
                            confidence = match_result.confidence,
                            is_valid   = match_result.confidence != MapMatchConfidence.UNKNOWN,
                        )
                    else:
                        self._tm_cached_draw_data.car_dot = None
                else:
                    self._tm_cached_draw_data.car_dot = None
            dd = self._tm_cached_draw_data
            if hasattr(self, "_tm_map_widget"):
                self._tm_map_widget.set_draw_data(dd)
            # Group 21B — announce pit lane entry/exit transitions
            pit_now = bool(match_result.is_pit_likely)
            if pit_now != self._pit_lane_active:
                self._pit_lane_active = pit_now
                if self._announcer is not None:
                    if pit_now:
                        self._announcer.announce(
                            "Entering pit lane.",
                            Priority.HIGH, "pit_lane_entry", 5.0,
                        )
                    else:
                        self._announcer.announce(
                            "Pit lane exit.",
                            Priority.HIGH, "pit_lane_exit", 5.0,
                        )
        except Exception:
            pass

    def _tm_start_session(self) -> None:
        """Button handler: start a new calibration recording session."""
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is None:
            return
        loc_id = (self._tm_location_combo.currentData() or "").strip()
        lay_id = (self._tm_layout_combo.currentData() or "").strip()
        ctrl.start_session(loc_id, lay_id)
        self._tm_update_cal_buttons()
        self._tm_update_cal_status()

    def _tm_stop_session(self) -> None:
        """Button handler: stop the active calibration recording session."""
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is None:
            return
        ctrl.stop_session()
        self._tm_update_cal_buttons()
        self._tm_update_cal_status()

    def _tm_build_path(self) -> None:
        """Button handler: build a reference path from collected calibration laps."""
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is None:
            return
        result = ctrl.build_reference_path()
        self._tm_update_cal_buttons()
        self._tm_update_cal_status()
        # Group 21B — show all-pit-laps warning prominently, but ONLY when pit
        # detection actually ran.  DEF-17U-UAT-007: with pit detection off (the
        # default for Time Trial calibration) no pit warning may be surfaced, so
        # clean laps are never mislabelled "pit-in".
        if getattr(result, "pit_detection_enabled", False):
            pit_warns = [
                w for w in (result.warnings or [])
                if "pit" in w.lower() or "all calibration laps" in w.lower()
            ]
            if pit_warns and hasattr(self, "_tm_lbl_cal_status"):
                warn_text = " | ".join(pit_warns)
                self._tm_lbl_cal_status.setText(f"WARNING: {warn_text}")
                self._tm_lbl_cal_status.setStyleSheet(
                    "color: #FF4444; font-size: 10px; font-weight: bold;"
                )
        if result.success:
            self._tm_try_build_station_map()
        else:
            from PyQt6.QtWidgets import QMessageBox
            session = getattr(ctrl, "_session", None)
            detail  = _format_build_diag(result, session)
            QMessageBox.warning(self, "Build Failed", detail)

    def _tm_try_build_station_map(self, ref_path=None) -> None:
        """Build a 1 m station map and update the map canvas.

        If ref_path is None, reads from the controller's last successful build
        result (the correct attribute is _last_build_result.reference_path, NOT
        _ref_path which does not exist on the controller).  Callers that have
        already loaded a ReferencePath from disk can pass it directly.
        """
        try:
            if ref_path is None:
                ctrl = getattr(self, "_tm_controller", None)
                if ctrl is None:
                    return
                last_result = getattr(ctrl, "_last_build_result", None)
                ref_path = (
                    last_result.reference_path
                    if last_result is not None and last_result.success and last_result.reference_path
                    else None
                )
            if ref_path is None or not ref_path.points:
                return

            # Seed: get corners_expected if available — DEF-17O-UAT-005/007
            loc_id = (self._tm_location_combo.currentData() or "").strip()
            lay_id = (self._tm_layout_combo.currentData() or "").strip()
            seed = None
            if self._tm_seed_result and loc_id and lay_id:
                layout = get_selected_layout(self._tm_seed_result, loc_id, lay_id)
                if layout is not None:
                    import types
                    seed = types.SimpleNamespace(
                        corners_expected = getattr(layout, "corners_expected", 0) or 0,
                        length_m         = getattr(layout, "lap_length_m", 0) or 0,
                    )

            self._tm_station_map = _build_station_map(ref_path, layout_seed=seed)

            # Group 23A: wire pit lane boundary detection from any pit laps in the calibration session
            _ctrl_for_pit = getattr(self, "_tm_controller", None)
            _session_for_pit = getattr(_ctrl_for_pit, "_session", None)
            if _session_for_pit is not None:
                self._tm_cal_laps = list(getattr(_session_for_pit, "laps", []))
            _pit_laps = [lap for lap in (self._tm_cal_laps if hasattr(self, '_tm_cal_laps') else []) if getattr(lap, 'is_pit_lap', False)]
            if _pit_laps:
                from data.track_station_map import detect_pit_lane_from_pit_laps
                _pit_boundary = detect_pit_lane_from_pit_laps(_pit_laps, self._tm_station_map)
                if _pit_boundary is not None:
                    self._tm_station_map.pit_lane = _pit_boundary

            # Update pit lane status label (Group 23B)
            if hasattr(self, "_tm_lbl_pit_lane_status"):
                if getattr(self._tm_station_map, "pit_lane", None) is not None:
                    self._tm_lbl_pit_lane_status.setText("Pit lane: detected ✓")
                    self._tm_lbl_pit_lane_status.setStyleSheet("color: #4caf50; font-size: 10px;")
                else:
                    self._tm_lbl_pit_lane_status.setText("Pit lane: not detected")
                    self._tm_lbl_pit_lane_status.setStyleSheet("color: #888888; font-size: 10px;")

            self._tm_cached_draw_data = None  # AC1: invalidate cache on station map rebuild
            dd = _build_map_draw_data(self._tm_station_map)
            self._tm_cached_draw_data = dd
            if hasattr(self, "_tm_map_widget"):
                self._tm_map_widget.set_draw_data(dd)

            n  = self._tm_station_map.station_count()
            nc = len(self._tm_station_map.seeded_corners)
            if hasattr(self, "_tm_map_note_lbl"):
                self._tm_map_note_lbl.setText(
                    f"Station map: {n} stations | {nc} corners | spacing 1 m"
                )

            # DEF-17O-UAT-004: show both path stats and station map count
            if hasattr(self, "_tm_lbl_build_info"):
                ctrl = getattr(self, "_tm_controller", None)
                _pts, _conf = 0, 0.0
                if ctrl:
                    _s = ctrl.get_status_summary()
                    _pts  = _s.get("reference_path_points", 0)
                    _conf = _s.get("confidence", 0.0)
                if _pts:
                    self._tm_lbl_build_info.setText(
                        f"Path: {_pts} pts  |  Conf: {_conf:.2f}  |  "
                        f"Map: {n} stations / {nc} corners"
                    )

            # DEF-17O-UAT-008: auto-persist station map to disk
            try:
                _saved_path = _export_station_map(self._tm_station_map)
                if hasattr(self, "_tm_map_note_lbl"):
                    self._tm_map_note_lbl.setText(
                        f"Station map: {n} stations | {nc} corners | spacing 1 m"
                        f"  [saved]"
                    )
            except Exception:
                pass  # best-effort; in-memory map still usable

            # DEF-17S-005: re-filter warnings now that station map is authoritative
            self._tm_refresh_seg_diagnostics_labels()
            # Group 17P: run alignment after every successful station map build
            self._tm_run_alignment()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            if hasattr(self, "_tm_map_note_lbl"):
                self._tm_map_note_lbl.setText(f"Station map error: {exc}")

    def _tm_refresh_seg_diagnostics_labels(self) -> None:
        """DEF-17S-005: re-filter segment detection warnings using current station map state.

        Called whenever station map state changes so stale count-mismatch warnings
        from detect_track_segments() are suppressed when the station map is authoritative.
        """
        det    = getattr(self, "_tm_detection_result", None)
        review = getattr(self, "_tm_review_result", None)
        lbl    = getattr(self, "_tm_lbl_seg_status", None)
        if det is None or review is None or lbl is None:
            return

        sm = getattr(self, "_tm_station_map", None)
        warns = list(det.warnings)
        if sm is not None and sm.seeded_corners:
            warns = [
                w for w in warns
                if "Corner count mismatch" not in w
                and "corners vs expected" not in w
            ]

        geometry_segs = [s for s in review.segments if s.segment_type not in _TELEMETRY_OVERLAY_SEG_TYPES]
        overlay_segs  = [s for s in review.segments if s.segment_type in _TELEMETRY_OVERLAY_SEG_TYPES]
        seg_count     = len(geometry_segs)
        overlay_note  = f"  +{len(overlay_segs)} telemetry overlays hidden" if overlay_segs else ""
        warn_count    = len(warns)
        status_txt    = f"Detection complete — {seg_count} geometry segments found{overlay_note}"
        if warn_count:
            status_txt += f"  ({warn_count} warning{'s' if warn_count != 1 else ''})"
        lbl.setText(status_txt)

    def _tm_try_load_station_map_from_disk(self, loc_id: str, lay_id: str) -> None:
        """DEF-17O-UAT-008: load a persisted station map for this layout if one exists.

        Called when the layout combo changes so previously saved geometry is
        immediately available without having to re-run calibration.
        """
        if not loc_id or not lay_id:
            return
        try:
            p = _find_station_map_path(loc_id, lay_id)
            if p is None:
                return
            sm = _import_station_map(p)
            self._tm_station_map = sm
            # Group 24 AC2: reset pit-lane guard when station map changes
            self._pit_lane_active = False
            self._tm_cached_draw_data = None  # AC1: invalidate cache on station map load
            dd = _build_map_draw_data(sm)
            self._tm_cached_draw_data = dd
            if hasattr(self, "_tm_map_widget"):
                self._tm_map_widget.set_draw_data(dd)
            n  = sm.station_count()
            nc = len(sm.seeded_corners)
            if hasattr(self, "_tm_map_note_lbl"):
                self._tm_map_note_lbl.setText(
                    f"Station map: {n} stations | {nc} corners | spacing 1 m  [loaded from disk]"
                )
            # DEF-17S-005: re-filter warnings now that station map is authoritative
            self._tm_refresh_seg_diagnostics_labels()
            # Refresh turn column in segment review if segments are already displayed
            self._tm_refresh_seg_table()
            # Group 17P: run alignment after loading saved station map
            self._tm_run_alignment()
        except Exception:
            logging.debug("station map load failed", exc_info=True)
    def _tm_save_path(self) -> None:
        """Button handler: save the built reference path to JSON."""
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is None:
            return
        saved = ctrl.save_reference_path()
        self._tm_update_cal_buttons()
        self._tm_update_cal_status()
        if saved is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Save Failed", "Could not save reference path.")

    def _tm_detect_segments(self) -> None:
        """Button handler: run automatic segment detection on the current calibration session."""
        try:
            self._tm_detect_segments_safe()
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            _err = (
                "Segment detection could not run because the saved reference path is "
                f"incomplete or invalid. Your calibration file has not been deleted.\n\n"
                f"Technical detail: {type(exc).__name__}: {exc}"
            )
            _lbl_s = getattr(self, "_tm_lbl_seg_status", None)
            if _lbl_s is not None:
                _lbl_s.setText("Detection error — see dialog for details")
                _lbl_s.setStyleSheet("color: #C06060; font-size: 10px;")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Segment Detection Error", _err)
            print(f"[TrackModelling] _tm_detect_segments unhandled: {tb}")

    def _tm_detect_segments_safe(self) -> None:
        """Inner implementation — wrapped by _tm_detect_segments's try/except."""
        ctrl   = getattr(self, "_tm_controller", None)
        loc_id = (self._tm_location_combo.currentData() or "").strip()
        lay_id = (self._tm_layout_combo.currentData() or "").strip()

        # Primary path: active session with usable laps already in memory
        if ctrl is not None and ctrl.can_save and ctrl._session is not None:
            session = ctrl._session
        else:
            # DEF-17N-UAT-004: load persisted calibration laps from disk
            if not loc_id or not lay_id:
                return
            audit = _audit_track_files(loc_id, lay_id)

            if not (audit.ref_path_exists and audit.ref_path_load_ok):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "No Calibration Data",
                    f"No reference path found for {loc_id} / {lay_id}.\n\n"
                    "Start a calibration session, drive 3+ clean laps, then\n"
                    "Build Reference Path and Save Reference Path.",
                )
                return

            if audit.is_legacy_ref_path_only:
                # Ref path exists but no raw lap data — old format saved before Group 17N
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "Reference Path Found — Lap Data Required",
                    f"A saved reference path exists for {loc_id} / {lay_id}:\n"
                    f"  {audit.ref_path_file}\n"
                    f"  {audit.ref_path_point_count} pts  |  "
                    f"conf {audit.ref_path_confidence:.2f}  |  "
                    f"{audit.ref_path_source_laps} laps\n\n"
                    "However, the raw calibration lap data needed for segment\n"
                    "detection was not saved with this file (pre-17N format).\n\n"
                    "Fix: run one new calibration session at this track/layout,\n"
                    "Build Reference Path, then Save Reference Path.\n"
                    "This will persist the lap data alongside the reference path\n"
                    "so Detect Segments works after every future restart.",
                )
                return

            if not audit.can_detect_segments:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Saved Lap Data Not Loadable",
                    f"Saved calibration laps for {loc_id} / {lay_id} could not be read.\n\n"
                    f"{audit.calibration_laps_load_error or 'Unknown error'}\n\n"
                    "Re-run calibration to create a fresh set of lap data.",
                )
                return

            # Load persisted laps and reconstruct a CalibrationSession
            from pathlib import Path as _Path
            try:
                session = _import_cal_laps(_Path(audit.calibration_laps_file))
            except Exception as exc:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self, "Failed to Load Calibration Laps",
                    f"Could not load saved lap data:\n{exc}\n\n"
                    "Re-run calibration at this track/layout.",
                )
                return

            # DEF-17O-UAT-001/003: if no station map yet, build from the saved
            # reference path so corner counts are available during detection.
            if getattr(self, "_tm_station_map", None) is None and audit.ref_path_exists and audit.ref_path_load_ok:
                try:
                    _ref = _import_ref_path(_Path(audit.ref_path_file))
                    self._tm_try_build_station_map(ref_path=_ref)
                except Exception:
                    pass  # best-effort; detection proceeds without map

            # Inform user that detection is running from persisted data
            _lbl_s = getattr(self, "_tm_lbl_seg_status", None)
            if _lbl_s is not None:
                _lbl_s.setText(
                    f"Running from {session.calibration_car_id} laps saved on disk "
                    f"({audit.calibration_laps_usable_count} usable) …"
                )
                _lbl_s.setStyleSheet("color: #E4D0AA; font-size: 10px;")

        # Fetch layout seed for corner count hint (DEF-17M-UAT-002 fix: was seed_result.layouts)
        seed_result = getattr(self, "_tm_seed_result", None)
        layout_seed = (
            get_selected_layout(seed_result, loc_id, lay_id)
            if seed_result and seed_result.success
            else None
        )

        result = _detect_track_segments(session, layout_seed=layout_seed)

        # Update status labels
        if result.success:
            conf = result.confidence.value

            # DEF-17O-UAT-002: separate geometry segments from telemetry overlays.
            # Overlays (gear zones, limiter zones, kerb candidates, fuel-save candidates)
            # are car/driver behaviour; they are NOT shown in Segment Review geometry table.
            geometry_segs = [s for s in result.segments if s.segment_type not in _TELEMETRY_OVERLAY_SEG_TYPES]
            overlay_segs  = [s for s in result.segments if s.segment_type in _TELEMETRY_OVERLAY_SEG_TYPES]
            seg_count     = len(geometry_segs)

            overlay_note = f"  +{len(overlay_segs)} telemetry overlays hidden" if overlay_segs else ""
            self._tm_lbl_seg_summary.setText(
                f"Segments: {seg_count}  |  Confidence: {conf}{overlay_note}"
            )

            # DEF-17O-UAT-003: prefer station map corner count over old detection count.
            # The 17O station map fills placeholders to guarantee corners_expected is met
            # (e.g. Daytona always has 12).  The old detection count is XYZ-curvature only
            # and may return fewer (e.g. 5) when curvature peaks are shallow.
            sm = getattr(self, "_tm_station_map", None)
            if sm is not None and sm.seeded_corners:
                n_seeded = len(sm.seeded_corners)
                n_placeholder = sum(1 for c in sm.seeded_corners if c.is_seeded_placeholder)
                n_detected_geo = n_seeded - n_placeholder
                self._tm_lbl_seg_expected.setText(
                    f"{n_seeded} seeded corners  |  {n_detected_geo} curvature-detected  |  "
                    f"{n_placeholder} estimated"
                )
            else:
                exp = result.expected_corner_count
                if exp is not None:
                    match_str = "✓" if result.corner_count_matches_expected else "≠"
                    self._tm_lbl_seg_expected.setText(
                        f"Expected corners: {exp}  {match_str}  detected: {result.detected_corner_count}"
                    )
                else:
                    self._tm_lbl_seg_expected.setText("Expected corners: —")

            # DEF-17R-004: suppress old "Corner count mismatch" warnings when the
            # station map is authoritative.  detect_track_segments() uses telemetry
            # speed-minima and may see fewer corners than the seed expects — that is
            # expected and not a real warning when a station map exists.
            sm_check = getattr(self, "_tm_station_map", None)
            _warns_display = result.warnings
            if sm_check is not None and sm_check.seeded_corners:
                _warns_display = [
                    w for w in result.warnings
                    if "Corner count mismatch" not in w
                    and "corners vs expected" not in w
                ]
            warn_count = len(_warns_display)
            status_txt = f"Detection complete — {seg_count} geometry segments found{overlay_note}"
            if warn_count:
                status_txt += f"  ({warn_count} warning{'s' if warn_count != 1 else ''})"
            self._tm_lbl_seg_status.setText(status_txt)
            self._tm_lbl_seg_status.setStyleSheet("color: #6A9A6A; font-size: 10px;")

            # Auto-create review model from detection result (Group 17F).
            # Filter telemetry overlays so only geometry rows reach Segment Review.
            self._tm_detection_result    = result
            self._tm_review_result       = _create_seg_review(result)
            self._tm_review_result.segments = [
                s for s in self._tm_review_result.segments
                if s.segment_type not in _TELEMETRY_OVERLAY_SEG_TYPES
            ]
            self._tm_selected_segment_id = None
            self._tm_refresh_seg_table()
            self._tm_refresh_review_buttons()
            self._tm_refresh_approval_panel()
        else:
            error_txt = "; ".join(result.errors) if result.errors else "Unknown error"
            self._tm_lbl_seg_summary.setText("Segments: — | Corners: —")
            self._tm_lbl_seg_expected.setText("Expected corners: —")
            self._tm_lbl_seg_status.setText(f"Detection failed: {error_txt}")
            self._tm_lbl_seg_status.setStyleSheet("color: #C06060; font-size: 10px;")

            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Segment Detection Failed", error_txt)

    # --- Segment Review methods (Group 17F) ---------------------------------

    def _tm_refresh_seg_table(self) -> None:
        """Rebuild the segment review table from the current review result."""
        review = getattr(self, "_tm_review_result", None)
        tbl = getattr(self, "_tm_seg_table", None)
        if tbl is None:
            return

        segs = list(review.segments) if review else []
        tbl.setRowCount(len(segs))

        # DEF-17O-UAT: match non-apex segments to corner by progress
        sm = getattr(self, "_tm_station_map", None)
        sm_corners = sm.seeded_corners if sm is not None else []

        # DEF-17S-004: resolve seed corner windows for window-based turn assignment
        _seed_corner_defs: list = []
        try:
            from ui.track_modelling_vm import get_selected_layout as _gsl
            _sr = getattr(self, "_tm_seed_result", None)
            if _sr and _sr.success:
                _loc_id = getattr(getattr(self, "_tm_location_combo", None), "currentData", lambda: "")() or ""
                _lay_id = getattr(getattr(self, "_tm_layout_combo", None), "currentData", lambda: "")() or ""
                if _loc_id and _lay_id:
                    _sl = _gsl(_sr, _loc_id.strip(), _lay_id.strip())
                    _seed_corner_defs = getattr(_sl, "corner_definitions", []) or [] if _sl else []
        except Exception:
            pass

        for row, seg in enumerate(segs):
            row_data = _format_seg_row(seg)

            # Populate Turn column: seed windows (preferred) → station map nearest (fallback)
            if not row_data.get("turn"):
                mid = getattr(seg, "lap_progress_mid", None)
                assigned = None
                if _seed_corner_defs and mid is not None:
                    # Window-based: assign only if segment midpoint falls inside seed window
                    for _cdef in _seed_corner_defs:
                        _w_start = _cdef.start_progress_pct / 100.0
                        _w_end   = _cdef.end_progress_pct   / 100.0
                        if _w_start <= mid <= _w_end:
                            assigned = _cdef.corner_id
                            break
                elif sm_corners and mid is not None:
                    # Fallback: nearest station map corner within 15% progress
                    nearest = min(sm_corners, key=lambda c: abs(c.approx_progress - mid))
                    if abs(nearest.approx_progress - mid) < 0.15:
                        assigned = nearest.corner_id
                if assigned:
                    row_data = dict(row_data, turn=assigned)

            for col, key in enumerate(
                ("name", "turn", "type", "progress", "confidence", "laps", "status", "warnings")
            ):
                item = QTableWidgetItem(row_data.get(key, ""))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Status colour coding
                if key == "status":
                    v = row_data.get(key, "")
                    if "Confirmed" in v or "Validated" in v or "Renamed" in v:
                        item.setForeground(QColor("#88EE88"))
                    elif "Rejected" in v:
                        item.setForeground(QColor("#EE8888"))
                    elif "⚠" in v or "⟂" in v or "⇔" in v:
                        item.setForeground(QColor("#F5A623"))
                    else:
                        item.setForeground(QColor("#888888"))
                tbl.setItem(row, col, item)

        tbl.resizeColumnsToContents()

        # Group 23A: restore highlight after table rebuild without re-firing cellClicked
        if self._tm_highlight_start_p is not None:
            self._tm_set_map_highlight(self._tm_highlight_start_p, self._tm_highlight_end_p)

    def _tm_on_seg_selected(self, row: int, _col: int) -> None:
        """Slot: called when a row in the segment review table is clicked."""
        review = getattr(self, "_tm_review_result", None)
        if review is None or row < 0 or row >= len(review.segments):
            self._tm_selected_segment_id = None
            self._tm_clear_map_highlight()
        else:
            self._tm_selected_segment_id = review.segments[row].segment_id
            # Highlight the selected segment on the track map (Group 20A)
            seg = review.segments[row]
            start_p = getattr(seg, "lap_progress_start", None)
            end_p   = getattr(seg, "lap_progress_end",   None)
            if start_p is not None and end_p is not None:
                self._tm_set_map_highlight(start_p, end_p)
            else:
                self._tm_clear_map_highlight()
        self._tm_refresh_review_buttons()

    def _tm_refresh_review_buttons(self) -> None:
        """Update enabled/disabled state of all review action buttons."""
        review = getattr(self, "_tm_review_result", None)
        sel_id = getattr(self, "_tm_selected_segment_id", None)
        states = _get_review_btns(review, sel_id)

        btns = {
            "confirm":        getattr(self, "_tm_btn_rev_confirm",    None),
            "rename":         getattr(self, "_tm_btn_rev_rename",     None),
            "reject":         getattr(self, "_tm_btn_rev_reject",     None),
            "needs_more_laps": getattr(self, "_tm_btn_rev_needs_laps", None),
            "split_required": getattr(self, "_tm_btn_rev_split",      None),
            "merge_required": getattr(self, "_tm_btn_rev_merge",      None),
            "save":           getattr(self, "_tm_btn_rev_save",       None),
        }
        for key, btn in btns.items():
            if btn is not None:
                btn.setEnabled(states.get(key, False))

    def _tm_refresh_approval_panel(self) -> None:
        """Update the approval panel labels from the current review result.

        Legacy _tm_ap_* widgets have been removed (Group 23A). All information
        is now displayed via _tm_al_* alignment panel widgets.
        """

    # ── Group 17P: Track Model Alignment ─────────────────────────────────────

    def _tm_run_alignment(self) -> None:
        """Compute seed-vs-model alignment and refresh the alignment panel."""
        sm  = getattr(self, "_tm_station_map", None)
        if sm is None:
            self._tm_refresh_alignment_panel(None)
            return

        # Resolve the layout seed for alignment (same lookup used by station map build)
        from ui.track_modelling_vm import get_selected_layout
        loc_id = (self._tm_location_combo.currentData() or "").strip()
        lay_id = (self._tm_layout_combo.currentData() or "").strip()
        layout = None
        if self._tm_seed_result and loc_id and lay_id:
            layout = get_selected_layout(self._tm_seed_result, loc_id, lay_id)

        result = _align_track_model(sm, layout)
        self._tm_alignment_result = result
        self._tm_refresh_alignment_panel(result)
        self._tm_refresh_track_truth_panel()

    def _tm_refresh_alignment_panel(self, result) -> None:
        """Update the Track Model Alignment panel labels from result."""
        has_map = getattr(self, "_tm_station_map", None) is not None

        # Resolve layout_seed for the seed audit display (Group 17S/17T)
        _layout_seed = None
        _loc_id_str  = ""
        _lay_id_str  = ""
        try:
            from ui.track_modelling_vm import get_selected_layout
            _sr = getattr(self, "_tm_seed_result", None)
            if _sr and _sr.success:
                _loc_id_str = getattr(getattr(self, "_tm_location_combo", None), "currentData", lambda: "")() or ""
                _lay_id_str = getattr(getattr(self, "_tm_layout_combo", None), "currentData", lambda: "")() or ""
                if _loc_id_str and _lay_id_str:
                    _layout_seed = get_selected_layout(_sr, _loc_id_str.strip(), _lay_id_str.strip())
        except Exception:
            pass

        # Geometry alignment — library-first seed map resolution (Group 17T/17U)
        _geo_result = None
        try:
            _sm = getattr(self, "_tm_station_map", None)
            if _sm is not None:
                from data.track_map_geometry_alignment import align_maps_geometry as _align_geo
                from data.track_library import resolve_seed_coordinate_map as _resolve_seed
                _seed_coord_map = None
                if _loc_id_str and _lay_id_str:
                    _seed_coord_map, _ = _resolve_seed(
                        _loc_id_str.strip(), _lay_id_str.strip()
                    )
                _geo_result = _align_geo(_sm, _seed_coord_map, _layout_seed)
        except Exception:
            pass

        summary = _fmt_alignment_summary(result, _layout_seed, _geo_result)
        states  = _get_accept_btn_states(result, has_map)

        def _set(attr: str, val: str, color: str = "") -> None:
            lbl = getattr(self, attr, None)
            if lbl is not None:
                lbl.setText(val)
                if color:
                    lbl.setStyleSheet(f"color: {color}; font-size: 11px;")

        _set("_tm_al_workflow_state", summary["workflow_state"], summary["workflow_color"])
        _set("_tm_al_match_status",   summary["match_status"],   summary["match_color"])
        _set("_tm_al_seed_corners",   summary["seed_corners"])
        _set("_tm_al_model_corners",  summary["model_corners"])
        _set("_tm_al_extra_peaks",    summary["extra_peaks"])
        _set("_tm_al_placeholders",   summary["placeholders"])
        _set("_tm_al_seed_source",           summary.get("seed_source", "—"))
        _set("_tm_al_seed_truth_source",     summary.get("seed_truth_source", "—"))
        _set("_tm_al_seed_audit",            summary.get("seed_audit", "—"))
        _set("_tm_al_seed_position_status",  summary.get("seed_position_status", "—"))
        _set("_tm_al_corners_matched",       summary.get("corners_matched", "—"))
        _set("_tm_al_corner_position_match", summary.get("corner_position_match", "—"),
             summary.get("corner_position_color", ""))
        _set("_tm_al_lap_model",       summary["lap_model"])
        _set("_tm_al_lap_seed",        summary["lap_seed"])
        _set("_tm_al_lap_delta",       summary["lap_delta"], summary.get("lap_delta_color", ""))
        _set("_tm_al_geometry_match",  summary.get("geometry_match", "—"))
        _set("_tm_al_stations",        summary["stations"])
        _set("_tm_al_confidence",     summary["confidence"])
        _set("_tm_al_accepted_at",    summary["accepted_at"])

        blk = getattr(self, "_tm_al_blockers", None)
        if blk is not None:
            blk.setText(summary["blockers"])
        wrn = getattr(self, "_tm_al_warnings", None)
        if wrn is not None:
            wrn.setText(summary["warnings"])
        sec = getattr(self, "_tm_al_sector_note", None)
        if sec is not None:
            sec.setText(summary["sector"])

        acc_btn = getattr(self, "_tm_btn_accept", None)
        if acc_btn is not None:
            seed_available = getattr(self, "_tm_seed_geometry_available", False)
            accept_enabled = states.get("accept", False) and seed_available
            acc_btn.setEnabled(accept_enabled)
            if not seed_available:
                acc_btn.setToolTip("Seed geometry required before acceptance")
            else:
                acc_btn.setToolTip(
                    "Accept the whole-model alignment result and save this track model as official"
                )
            # Style the button to reflect match quality:
            # GOOD_MATCH → amber border (lower-quality acceptance hint)
            # ACCEPTABLE_MATCH → green (normal acceptance)
            _match_name = (
                result.match_status.name
                if result is not None and hasattr(result.match_status, "name")
                else ""
            )
            if _match_name == "GOOD_MATCH":
                acc_btn.setStyleSheet(
                    "QPushButton { background:#2A2000; color:#ffa500;"
                    " border:1px solid #ffa500;"
                    " border-radius:4px; padding:5px 12px;"
                    " font-size:11px; font-weight:bold; }"
                    "QPushButton:hover { background:#3A3000; }"
                    "QPushButton:disabled { background:#1A1A1A; color:#3A5A3A;"
                    " border-color:#2A3A2A; }"
                )
            else:
                acc_btn.setStyleSheet(
                    "QPushButton { background:#1A3A1A; color:#88EE88;"
                    " border:1px solid #3A6A3A;"
                    " border-radius:4px; padding:5px 12px;"
                    " font-size:11px; font-weight:bold; }"
                    "QPushButton:hover { background:#2A4A2A; }"
                    "QPushButton:disabled { background:#1A1A1A; color:#3A5A3A;"
                    " border-color:#2A3A2A; }"
                )
        reb_btn = getattr(self, "_tm_btn_rebuild", None)
        if reb_btn is not None:
            reb_btn.setEnabled(states.get("rebuild", False))

    def _tm_refresh_track_truth_panel(self) -> None:
        """Update the Track Truth / Mapping panel from the current track/layout selection.

        Calls resolve_track_truth_model + validate_track_truth_model then applies
        format_track_truth_status to every _tm_truth_lbl_* widget.
        Safe to call when no track is selected — placeholder dict handles it.
        """
        loc_id = (getattr(self._tm_location_combo, "currentData", lambda: "")() or "").strip()
        lay_id = (getattr(self._tm_layout_combo, "currentData", lambda: "")() or "").strip()

        model      = None
        validation = None
        try:
            if loc_id and lay_id:
                model = _resolve_track_truth(loc_id, lay_id)
                if model is not None:
                    validation = _validate_track_truth(model)
        except Exception:
            pass

        try:
            d = _format_track_truth_status(model, validation, loc_id or None, lay_id or None)
        except Exception:
            d = {
                "track_id": "—", "layout_id": "—",
                "library_availability": "—", "library_availability_color": "#888888",
                "seed_geometry": "—", "seed_geometry_color": "#888888",
                "corner_metadata": "—", "corner_metadata_color": "#888888",
                "complex_metadata": "—", "complex_metadata_color": "#888888",
                "geometry_acceptance": "—", "geometry_acceptance_color": "#888888",
                "live_mapping_ready": "—", "live_mapping_ready_color": "#888888",
                "ai_context_ready": "—", "ai_context_ready_color": "#888888",
                "blockers": "—", "warnings": "—",
                "status_label": "—", "status_color": "#888888",
            }

        # Simple value labels (value + color)
        _simple_pairs = [
            ("_tm_truth_lbl_track_id",            "track_id",           ""),
            ("_tm_truth_lbl_layout_id",           "layout_id",          ""),
            ("_tm_truth_lbl_library_availability","library_availability","library_availability_color"),
            ("_tm_truth_lbl_seed_geometry",       "seed_geometry",       "seed_geometry_color"),
            ("_tm_truth_lbl_corner_metadata",     "corner_metadata",     "corner_metadata_color"),
            ("_tm_truth_lbl_complex_metadata",    "complex_metadata",    "complex_metadata_color"),
            ("_tm_truth_lbl_geometry_acceptance", "geometry_acceptance", "geometry_acceptance_color"),
            ("_tm_truth_lbl_live_mapping_ready",  "live_mapping_ready",  "live_mapping_ready_color"),
            ("_tm_truth_lbl_ai_context_ready",    "ai_context_ready",    "ai_context_ready_color"),
        ]
        for attr, val_key, color_key in _simple_pairs:
            lbl = getattr(self, attr, None)
            if lbl is None:
                continue
            lbl.setText(d.get(val_key, "—"))
            if color_key:
                color = d.get(color_key, "#888888")
                lbl.setStyleSheet(f"color: {color}; font-size: 11px;")

        # Blockers label
        blk = getattr(self, "_tm_truth_lbl_blockers", None)
        if blk is not None:
            blk.setText(d.get("blockers", "—"))

        # Warnings label
        wrn = getattr(self, "_tm_truth_lbl_warnings", None)
        if wrn is not None:
            wrn.setText(d.get("warnings", "—"))

        # Status label
        sts = getattr(self, "_tm_truth_lbl_status_label", None)
        if sts is not None:
            sts.setText(d.get("status_label", "—"))
            sts.setStyleSheet(
                f"color: {d.get('status_color', '#888888')}; font-size: 11px;"
            )

    def _tm_accept_track_model(self) -> None:
        """Accept the whole-model alignment and persist to disk."""
        result = getattr(self, "_tm_alignment_result", None)
        sm     = getattr(self, "_tm_station_map", None)
        if result is None or sm is None:
            return
        from datetime import datetime, timezone
        result.accepted    = True
        result.accepted_at = datetime.now(timezone.utc).isoformat()
        try:
            _export_accepted_model(
                result,
                sm.track_location_id,
                sm.layout_id,
            )
        except Exception:
            pass  # best-effort
        self._tm_refresh_alignment_panel(result)
        self._tm_refresh_track_truth_panel()

    def _tm_rebuild_model(self) -> None:
        """Clear station map and alignment result — requires full recalibration.

        DEF-17R-005: the previous implementation was a silent no-op that only
        cleared the accepted flag.  This version destroys the station map so the
        user must drive calibration laps to rebuild it from scratch.
        """
        self._tm_station_map      = None
        self._tm_alignment_result = None

        # Push empty draw data to both map widgets so they go blank immediately
        from ui.track_map_vm import (
            build_track_map_draw_data as _build_draw,
            project_to_screen         as _proj,
        )
        _empty = _build_draw(None)
        for _attr in ("_tm_map_widget",):
            _w = getattr(self, _attr, None)
            if _w is not None and hasattr(_w, "set_draw_data"):
                _w.set_draw_data(_proj(_empty, _w.width() or 400, _w.height() or 300))

        # Reset alignment panel to "Not built" state
        self._tm_refresh_alignment_panel(None)
        self._tm_refresh_track_truth_panel()

        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Recalibration Reset",
            "Station map cleared.\n\n"
            "Next steps to rebuild a complete model:\n"
            "  1. Start Calibration mode in GT7 before leaving the pits.\n"
            "  2. Drive 2–3 full clean laps crossing the S/F line at the start and end.\n"
            "  3. Avoid pit-lane entries and lap-start offsets.\n"
            "  4. If lap length still mismatches the seed, check the correct layout is "
            "selected and repeat calibration.",
        )

    # ---------------------------------------------------------------- Group 20A

    def _tm_set_map_highlight(self, start_progress: float, end_progress: float) -> None:
        """Set an amber highlight band on the track map for the given progress range.

        start_progress / end_progress are 0.0–1.0 normalised lap progress values.
        """
        # Group 23A: persist bounds so _tm_refresh_seg_table() can restore after rebuild
        self._tm_highlight_start_p = start_progress
        self._tm_highlight_end_p   = end_progress
        sm = getattr(self, "_tm_station_map", None)
        w  = getattr(self, "_tm_map_widget", None)
        if sm is None or w is None:
            return
        from ui.track_map_vm import TrackMapDrawData
        dd = w._draw_data
        if dd is None:
            return
        import dataclasses
        dd_updated = dataclasses.replace(
            dd,
            highlight_start_progress = start_progress,
            highlight_end_progress   = end_progress,
        )
        w.set_draw_data(dd_updated)

    def _tm_clear_map_highlight(self) -> None:
        """Clear the highlight band from the track map."""
        # Group 23A: clear persisted bounds
        self._tm_highlight_start_p = None
        self._tm_highlight_end_p   = None
        w = getattr(self, "_tm_map_widget", None)
        if w is None or w._draw_data is None:
            return
        import dataclasses
        dd_cleared = dataclasses.replace(
            w._draw_data,
            highlight_start_progress = None,
            highlight_end_progress   = None,
        )
        w.set_draw_data(dd_cleared)

    def _tm_run_ai_corner_verify(self) -> None:
        """Button handler: run AI corner verification on the current station map."""
        if getattr(self, "_tm_station_map", None) is None:
            return
        self._tm_btn_ai_corner_verify.setEnabled(False)
        self._tm_btn_ai_corner_verify.setText("Verifying…")

        # Build peaks from station map seeded corners
        stations = self._tm_station_map.stations

        def _curvature_at_station(target_m):
            if not stations:
                return 0.0
            closest = min(stations, key=lambda s: abs(s.station_m - target_m))
            return abs(closest.curvature)

        peaks = [
            (c.approx_progress * 100.0, _curvature_at_station(c.approx_station_m), not c.is_seeded_placeholder)
            for c in self._tm_station_map.seeded_corners
        ]

        # Build seed windows from seed layout corner definitions
        seed_windows = []
        _sr = getattr(self, "_tm_seed_result", None)
        if _sr is not None and _sr.success:
            loc_id = (self._tm_location_combo.currentData() or "").strip()
            lay_id = (self._tm_layout_combo.currentData() or "").strip()
            if loc_id and lay_id:
                _lay = get_selected_layout(_sr, loc_id, lay_id)
                for cdef in (getattr(_lay, "corner_definitions", None) or []):
                    seed_windows.append((
                        cdef.corner_id,
                        getattr(cdef, "start_progress_pct", cdef.approx_progress * 100.0 - 3.0)
                        if not hasattr(cdef, "start_progress_pct") else cdef.start_progress_pct,
                        getattr(cdef, "end_progress_pct", cdef.approx_progress * 100.0 + 3.0)
                        if not hasattr(cdef, "end_progress_pct") else cdef.end_progress_pct,
                    ))

        # Build speed profile from last built reference path
        speed_profile = []
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is not None:
            last_result = getattr(ctrl, "_last_build_result", None)
            ref_path = (
                last_result.reference_path
                if last_result is not None and last_result.success and last_result.reference_path
                else None
            )
            if ref_path is not None:
                for pt in ref_path.points:
                    speed_profile.append((pt.lap_progress * 100.0, pt.speed_kph_avg))

        # API key from config
        api_key = self._config.get("ai", {}).get("api_key", "")

        # Track name from current layout selection
        lay_id_str = (self._tm_layout_combo.currentData() or "").strip()

        def _worker():
            from strategy.corner_verify_ai import verify_corners_with_ai
            result_tuple = verify_corners_with_ai(
                peaks, seed_windows, speed_profile, api_key, lay_id_str
            )
            self._tm_ai_corner_verify_signal.emit(result_tuple)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _tm_ai_corner_verify_done(self, result_tuple) -> None:
        """Slot: called via signal from AI verify worker thread (thread-safe)."""
        result, error_msg = result_tuple if isinstance(result_tuple, tuple) else (result_tuple, "")

        self._tm_btn_ai_corner_verify.setEnabled(
            getattr(self, "_tm_station_map", None) is not None
        )
        self._tm_btn_ai_corner_verify.setText("AI Corner Verify")

        if result is None:
            reason = error_msg or "Unknown error"
            self.statusBar().showMessage(
                f"AI corner verification failed: {reason}", 5000
            )
            return

        # Update verification_source on matched corners
        sm = getattr(self, "_tm_station_map", None)
        if sm is not None:
            for corner in sm.seeded_corners:
                if corner.corner_id in result:
                    corner.verification_source = "ai_verified"

        # Propagate verification_source to ReviewedTrackSegment (matched by turn_number)
        review = getattr(self, "_tm_review_result", None)
        if review is not None and sm is not None:
            corner_src: dict[str, str] = {
                c.corner_id: c.verification_source for c in sm.seeded_corners
            }
            for seg in review.segments:
                if seg.turn_number is not None:
                    cid = f"T{seg.turn_number}"
                    if cid in corner_src:
                        seg.verification_source = corner_src[cid]

        # Count updated corners and report
        n_updated = sum(
            1 for c in sm.seeded_corners
            if c.verification_source == "ai_verified"
        ) if sm is not None else 0

        self.statusBar().showMessage(
            f"AI corner verification complete — {n_updated} corners updated", 5000
        )
        self._tm_refresh_seg_table()

    # ----------------------------------------------------------------

    def _tm_try_load_accepted_model(self, loc_id: str, lay_id: str) -> None:
        """On layout select, load a previously accepted model if it exists."""
        if not loc_id or not lay_id:
            return
        try:
            p = _find_accepted_model_path(loc_id, lay_id)
            if p is None:
                return
            loaded = _import_accepted_model(p)
            if loaded is None:
                return
            self._tm_alignment_result = loaded
            self._tm_refresh_alignment_panel(loaded)
            self._tm_refresh_track_truth_panel()
        except Exception:
            logging.debug("no accepted model for this layout", exc_info=True)

    def _tm_review_confirm(self) -> None:
        review = getattr(self, "_tm_review_result", None)
        seg_id = getattr(self, "_tm_selected_segment_id", None)
        if review is None or seg_id is None:
            return
        _seg_confirm(review, seg_id)
        self._tm_refresh_seg_table()
        self._tm_refresh_review_buttons()
        self._tm_refresh_approval_panel()

    def _tm_review_rename(self) -> None:
        review = getattr(self, "_tm_review_result", None)
        seg_id = getattr(self, "_tm_selected_segment_id", None)
        if review is None or seg_id is None:
            return
        seg = next((s for s in review.segments if s.segment_id == seg_id), None)
        if seg is None:
            return
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Rename Segment", "New name:", text=seg.display_name
        )
        if ok and new_name.strip():
            _seg_rename(review, seg_id, new_name.strip())
            self._tm_refresh_seg_table()
            self._tm_refresh_review_buttons()
            self._tm_refresh_approval_panel()

    def _tm_review_reject(self) -> None:
        review = getattr(self, "_tm_review_result", None)
        seg_id = getattr(self, "_tm_selected_segment_id", None)
        if review is None or seg_id is None:
            return
        _seg_reject(review, seg_id)
        self._tm_refresh_seg_table()
        self._tm_refresh_review_buttons()
        self._tm_refresh_approval_panel()

    def _tm_review_needs_laps(self) -> None:
        review = getattr(self, "_tm_review_result", None)
        seg_id = getattr(self, "_tm_selected_segment_id", None)
        if review is None or seg_id is None:
            return
        _seg_needs_laps(review, seg_id)
        self._tm_refresh_seg_table()
        self._tm_refresh_review_buttons()
        self._tm_refresh_approval_panel()

    def _tm_review_split(self) -> None:
        review = getattr(self, "_tm_review_result", None)
        seg_id = getattr(self, "_tm_selected_segment_id", None)
        if review is None or seg_id is None:
            return
        _seg_split(review, seg_id)
        self._tm_refresh_seg_table()
        self._tm_refresh_review_buttons()
        self._tm_refresh_approval_panel()

    def _tm_review_merge(self) -> None:
        review = getattr(self, "_tm_review_result", None)
        seg_id = getattr(self, "_tm_selected_segment_id", None)
        if review is None or seg_id is None:
            return
        _seg_merge(review, seg_id)
        self._tm_refresh_seg_table()
        self._tm_refresh_review_buttons()
        self._tm_refresh_approval_panel()

    def _tm_review_save(self) -> None:
        """Export the reviewed segment model to JSON."""
        review = getattr(self, "_tm_review_result", None)
        if review is None:
            return
        try:
            out = _export_seg_review(review)
            lbl = getattr(self, "_tm_lbl_rev_save_path", None)
            if lbl is not None:
                lbl.setText(f"Saved: {out.name}")
            # Refresh resolver to reflect the newly saved model
            self._tm_refresh_resolver()
        except Exception as exc:  # noqa: BLE001
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Save Failed", f"Could not save reviewed model:\n{exc}")

    def _tm_refresh_resolver(self) -> None:
        """Re-resolve the best available track model and update the resolver status panel."""
        loc_id = getattr(self._tm_location_combo, "currentData", lambda: "")() or ""
        lay_id = getattr(self._tm_layout_combo, "currentData", lambda: "")() or ""
        if not loc_id or not lay_id:
            self._tm_resolver_result = None
        else:
            try:
                self._tm_resolver_result = _resolve_track_model(loc_id, lay_id)
            except Exception:
                self._tm_resolver_result = None

        summary = _format_resolver_summary(self._tm_resolver_result)

        for attr, key in (
            ("_tm_rs_source",           "source_type"),
            ("_tm_rs_modelling_status", "modelling_status"),
            ("_tm_rs_ai_ready",         "ai_ready"),
            ("_tm_rs_candidates",       "candidate_count"),
            ("_tm_rs_path",             "model_path"),
        ):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                lbl.setText(summary.get(key, "—"))

        ai_lbl = getattr(self, "_tm_rs_ai_ready", None)
        if ai_lbl is not None:
            colour = "#6AC46A" if summary.get("ai_ready") == "Yes" else "#CC4444"
            ai_lbl.setStyleSheet(f"color: {colour}; font-size: 11px; font-weight: bold;")

        blk = getattr(self, "_tm_rs_blockers", None)
        if blk is not None:
            blk.setText(summary.get("blockers", ""))

        warn = getattr(self, "_tm_rs_warnings", None)
        if warn is not None:
            warn.setText(summary.get("warnings", ""))

    # ── Group 17M: lap offset calibration helpers ────────────────────────────

    def _tm_get_track_length_m(self) -> Optional[float]:
        """Return track length in metres from reference path or seed, or None."""
        ctrl = getattr(self, "_tm_controller", None)
        if ctrl is not None:
            br = ctrl._last_build_result
            if br is not None and br.success and br.reference_path is not None:
                pts = br.reference_path.points
                if pts:
                    return pts[-1].distance_along_lap_m
        seed_result = getattr(self, "_tm_seed_result", None)
        if seed_result and seed_result.success:
            loc_id = (self._tm_location_combo.currentData() or "").strip()
            lay_id = (self._tm_layout_combo.currentData() or "").strip()
            for loc in seed_result.track_locations:
                if loc.track_location_id == loc_id:
                    for lay in loc.layouts:
                        if lay.layout_id == lay_id and lay.length_m is not None:
                            return lay.length_m
        return None

    def _tm_update_packet_age_label(self) -> None:
        """Refresh the packet age label from _tm_last_packet_time."""
        lbl = getattr(self, "_tm_lbl_packet_age", None)
        if lbl is None:
            return
        ts = getattr(self, "_tm_last_packet_time", None)
        if ts is None:
            lbl.setText("No packets received")
            lbl.setStyleSheet("color: #888; font-size: 10px;")
            return
        age = time.time() - ts
        if age < 1.0:
            lbl.setText(f"Last packet: {age * 1000:.0f} ms ago")
            lbl.setStyleSheet("color: #AAE4AA; font-size: 10px;")
        elif age < 10.0:
            lbl.setText(f"Last packet: {age:.1f} s ago")
            lbl.setStyleSheet("color: #E4D0AA; font-size: 10px;")
        else:
            lbl.setText(f"Last packet: {age:.0f} s ago — check connection")
            lbl.setStyleSheet("color: #E4AAAA; font-size: 10px;")

    def _tm_update_offset_status(self) -> None:
        """Refresh the offset calibration status labels."""
        from ui.track_modelling_vm import format_lap_offset_status
        cal    = getattr(self, "_tm_offset_calibration", None)
        length = self._tm_get_track_length_m()
        info   = format_lap_offset_status(cal, length)

        lbl = getattr(self, "_tm_lbl_offset_status", None)
        if lbl is not None:
            lbl.setText(info["status"])
            colour = "#AAE4AA" if cal is not None else "#888"
            lbl.setStyleSheet(f"color: {colour}; font-size: 10px;")

        detail_lbl = getattr(self, "_tm_lbl_offset_detail", None)
        if detail_lbl is not None:
            parts = []
            if info["offset_m"] != "—":
                parts.append(f"Offset: {info['offset_m']}")
            if info["track_length"] not in ("—", ""):
                parts.append(f"Track: {info['track_length']}")
            if info["source"] != "—":
                parts.append(f"Source: {info['source']}")
            detail_lbl.setText("  |  ".join(parts))

        warn_lbl = getattr(self, "_tm_lbl_offset_warnings", None)
        if warn_lbl is not None:
            note = info.get("provisional_note", "")
            warns = info.get("warnings", "")
            warn_lbl.setText(
                (note + ("\n" + warns if warns else ""))
                if note else warns
            )
            warn_lbl.setVisible(bool(note or warns))

    def _tm_create_zero_offset(self) -> None:
        """Button handler: create a provisional zero-offset calibration."""
        loc_id = (self._tm_location_combo.currentData() or "").strip()
        lay_id = (self._tm_layout_combo.currentData() or "").strip()
        if not loc_id or not lay_id:
            return
        length = self._tm_get_track_length_m()
        if length is None or length <= 0:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Missing Track Length",
                "Track length is not available. Check seed data or build/save a reference path.",
            )
            return
        try:
            from data.lap_distance_mapper import create_offset_zero
            self._tm_offset_calibration = create_offset_zero(loc_id, lay_id, length)
            self._tm_update_offset_status()
            self._tm_update_cal_buttons()
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Create Offset Failed", str(exc))

    def _tm_load_offset(self) -> None:
        """Button handler: load offset calibration from saved JSON file."""
        loc_id = (self._tm_location_combo.currentData() or "").strip()
        lay_id = (self._tm_layout_combo.currentData() or "").strip()
        if not loc_id or not lay_id:
            return
        try:
            from data.lap_distance_mapper import load_offset_calibration_for_track
            cal = load_offset_calibration_for_track(loc_id, lay_id)
            if cal is None:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "No Offset File",
                    f"No saved offset calibration found for {loc_id} / {lay_id}.",
                )
                return
            self._tm_offset_calibration = cal
            self._tm_update_offset_status()
            self._tm_update_cal_buttons()
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Load Offset Failed", str(exc))

    def _tm_save_offset(self) -> None:
        """Button handler: save current offset calibration to JSON."""
        cal = getattr(self, "_tm_offset_calibration", None)
        if cal is None:
            return
        try:
            from data.lap_distance_mapper import export_offset_calibration_json
            from pathlib import Path as _Path
            out_dir = _Path("data") / "track_models"
            out_dir.mkdir(parents=True, exist_ok=True)
            out = export_offset_calibration_json(cal, out_dir)
            lbl = getattr(self, "_tm_lbl_offset_status", None)
            if lbl is not None:
                lbl.setText(f"Saved: {out.name}")
                lbl.setStyleSheet("color: #6A9A6A; font-size: 10px;")
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Save Offset Failed", str(exc))

    # ── Group 17V: Seed Geometry ─────────────────────────────────────────────

    def _tm_generate_seed_geometry(self) -> None:
        """Button handler: build seed coordinate map from the active calibration session."""
        try:
            from data.track_geometry_builder import build_seed_geometry as _build_seed_geo
            ctrl = getattr(self, "_tm_controller", None)
            session = getattr(ctrl, "_session", None) if ctrl is not None else None
            loc_id = (self._tm_location_combo.currentData() or "").strip()
            lay_id = (self._tm_layout_combo.currentData() or "").strip()
            layout = None
            if self._tm_seed_result and loc_id and lay_id:
                layout = get_selected_layout(self._tm_seed_result, loc_id, lay_id)
            if session is None or layout is None:
                lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
                if lbl is not None:
                    lbl.setText("No active session or layout not selected.")
                return
            result = _build_seed_geo(
                session,
                getattr(layout, "lap_length_m", 0.0) or 0.0,
                loc_id,
                lay_id,
            )
            self._tm_seed_build_result = result
            self._tm_seed_save_result  = None
            # Refresh the panel FIRST — it sets per-lap diagnostics on the status
            # label — then APPEND our user-facing message so the refresh does not
            # overwrite it.
            self._tm_refresh_seed_geometry_panel()
            lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
            if not result.can_generate:
                if lbl is not None:
                    _existing = lbl.text()
                    lbl.setText(
                        (_existing + "\n\n" if _existing else "")
                        + "Not enough clean laps to build the map. Drive more full laps"
                        " starting and finishing on the grid, not from the pits."
                    )
                return
            from data.track_geometry_builder import CLOSURE_GAP_WARN_M as _CLOSURE_GAP_WARN_M
            if result.closure_gap_m > _CLOSURE_GAP_WARN_M and lbl is not None:
                _existing = lbl.text()
                lbl.setStyleSheet("color:#F5C542;")
                lbl.setText(
                    (_existing + "\n\n" if _existing else "")
                    + f"Map built but track loop gap is {result.closure_gap_m:.1f} m"
                    f" (>{_CLOSURE_GAP_WARN_M:.0f} m). More clean laps may improve closure."
                )
        except Exception as exc:
            lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
            if lbl is not None:
                lbl.setText(f"Error generating seed geometry: {exc}")

    def _tm_save_seed_geometry(self) -> None:
        """Button handler: save generated seed geometry to the track library."""
        try:
            from data.track_geometry_builder import save_seed_geometry_to_library as _save_seed_geo
            build_result = getattr(self, "_tm_seed_build_result", None)
            if build_result is None or not build_result.can_generate:
                return
            loc_id = (self._tm_location_combo.currentData() or "").strip()
            lay_id = (self._tm_layout_combo.currentData() or "").strip()
            save_result = _save_seed_geo(
                build_result.seed_map,
                loc_id,
                lay_id,
            )
            self._tm_seed_save_result = save_result
            if save_result.saved_path is not None and save_result.manifest_updated:
                # full success
                self._tm_seed_geometry_available = True
                # (no warning needed)
            elif save_result.saved_path is not None and not save_result.manifest_updated:
                # partial: file written but manifest update failed
                self._tm_seed_geometry_available = True
                if hasattr(self, "_tm_seed_geo_status_lbl"):
                    self._tm_seed_geo_status_lbl.setText(
                        "Geometry saved but manifest update failed — reload required"
                    )
            else:
                # total failure: file write failed
                self._tm_seed_geometry_available = False
                if hasattr(self, "_tm_seed_geo_status_lbl"):
                    self._tm_seed_geo_status_lbl.setText(
                        f"Save failed: {save_result.error}"
                    )
            self._tm_refresh_seed_geometry_panel()
        except Exception as exc:
            lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
            if lbl is not None:
                lbl.setText(f"Error saving seed geometry: {exc}")

    def _tm_reload_seed_geometry(self) -> None:
        """Button handler: reload seed geometry from the track library."""
        try:
            from data.track_library import resolve_seed_coordinate_map as _resolve_seed
            loc_id = (self._tm_location_combo.currentData() or "").strip()
            lay_id = (self._tm_layout_combo.currentData() or "").strip()
            if not loc_id or not lay_id:
                return
            seed_map, source = _resolve_seed(loc_id, lay_id)
            self._tm_seed_geometry_available = (seed_map is not None)
            lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
            if lbl is not None:
                if seed_map is not None:
                    lbl.setText(f"Seed geometry loaded (source: {source}, {len(seed_map.stations)} stations)")
                else:
                    lbl.setText("No seed geometry found — run Generate and Save first")
            self._tm_refresh_seed_geometry_panel()
        except Exception as exc:
            lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
            if lbl is not None:
                lbl.setText(f"Error reloading seed geometry: {exc}")

    def _tm_refresh_seed_geometry_panel(self) -> None:
        """Update seed geometry button states and status label from current state."""
        try:
            from ui.track_model_alignment_vm import (
                get_geometry_button_states,
                format_candidate_diagnostics,
            )
            from data.track_geometry_builder import LapGeometryFilterResult

            ctrl = getattr(self, "_tm_controller", None)
            session = getattr(ctrl, "_session", None) if ctrl is not None else None

            states = get_geometry_button_states(
                self._tm_seed_build_result,
                self._tm_seed_save_result,
                self._tm_seed_geometry_available,
                session_active=(session is not None),
            )
            for btn_attr, key in [
                ("_tm_btn_generate_seed", "generate"),
                ("_tm_btn_save_seed",     "save"),
                ("_tm_btn_reload_seed",   "reload"),
            ]:
                btn = getattr(self, btn_attr, None)
                if btn is None:
                    continue
                enabled, reason = states.get(key, (False, ""))
                btn.setEnabled(enabled)
                btn.setToolTip(reason if not enabled else "")

            filter_results = None
            build_result = self._tm_seed_build_result
            if build_result is not None:
                accepted = [
                    LapGeometryFilterResult(i, "accepted", "", 0.0, "")
                    for i in build_result.accepted_lap_indices
                ]
                filter_results = list(build_result.rejected_laps) + accepted

            lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
            if lbl is not None:
                lbl.setText(format_candidate_diagnostics(filter_results))
        except Exception as exc:
            lbl = getattr(self, "_tm_seed_geo_status_lbl", None)
            if lbl is not None:
                lbl.setText(f"Panel refresh error: {exc}")

    def _tm_audit_and_show_saved_files(self, loc_id: str, lay_id: str) -> None:
        """DEF-17M-UAT-003: audit disk for saved track model files and update UI.

        Called from _tm_on_layout_changed() so users see existing files after restart.
        Only updates the saved-path label when no active session has a saved path.
        """
        try:
            audit = _audit_track_files(loc_id, lay_id)
            info  = _format_file_audit(audit)

            # Only update the save-path label if the active session has no saved path
            ctrl      = getattr(self, "_tm_controller", None)
            ctrl_path = str(getattr(ctrl, "_saved_path", None) or "")
            lbl       = getattr(self, "_tm_lbl_save_path", None)
            if lbl is not None and not ctrl_path:
                if audit.ref_path_exists:
                    if audit.ref_path_load_ok:
                        lbl.setText(info["saved_text"])
                        lbl.setStyleSheet("color: #6A9A6A; font-size: 10px;")
                        # Update build-info label with saved path metadata
                        _bi = getattr(self, "_tm_lbl_build_info", None)
                        if _bi is not None and not ctrl_path:
                            _bi.setText(info["detail_text"])
                    else:
                        lbl.setText(info["saved_text"])
                        lbl.setStyleSheet("color: #E4AAAA; font-size: 10px;")
                else:
                    lbl.setText("No saved reference path for this track/layout")
                    lbl.setStyleSheet("color: #888; font-size: 10px;")

            # Update offset label if offset file found and no in-memory calibration
            if not getattr(self, "_tm_offset_calibration", None):
                off_lbl = getattr(self, "_tm_lbl_offset_status", None)
                if off_lbl is not None:
                    if audit.offset_exists:
                        off_lbl.setText("Offset calibration file found — click Load Offset")
                        off_lbl.setStyleSheet("color: #E4D0AA; font-size: 10px;")

            # Update Detect Segments button availability based on disk audit
            btn_detect = getattr(self, "_tm_btn_detect_segs", None)
            if btn_detect is not None:
                ctrl_has_ref = ctrl is not None and getattr(ctrl, "can_save", False)
                disk_can_detect = audit.can_detect_segments  # ref path + laps file
                disk_legacy     = audit.is_legacy_ref_path_only  # ref path only (pre-17N)
                # Enable if active session ready, OR disk has ref path + persisted laps
                # Also enable for legacy (old format) so user gets the clear message dialog
                btn_detect.setEnabled(ctrl_has_ref or disk_can_detect or disk_legacy)
                if not ctrl_has_ref:
                    if disk_can_detect:
                        btn_detect.setToolTip(
                            f"Detect segments from {audit.calibration_laps_usable_count} "
                            f"saved laps — {audit.ref_path_file}"
                        )
                    elif disk_legacy:
                        btn_detect.setToolTip(
                            "Reference path found but no lap data was saved (pre-17N format). "
                            "Click for instructions."
                        )

            # Show laps file status in the save path area
            lbl = getattr(self, "_tm_lbl_save_path", None)
            ctrl_path = str(getattr(ctrl, "_saved_path", None) or "")
            if lbl is not None and not ctrl_path and audit.ref_path_exists:
                if audit.can_detect_segments:
                    lbl.setText(
                        f"Saved: {audit.ref_path_file}\n"
                        f"  {audit.ref_path_point_count} pts  |  "
                        f"conf {audit.ref_path_confidence:.2f}  |  "
                        f"{audit.calibration_laps_usable_count} laps persisted "
                        f"— Detect Segments ready"
                    )
                    lbl.setStyleSheet("color: #6A9A6A; font-size: 10px;")
                elif audit.is_legacy_ref_path_only:
                    lbl.setText(
                        f"Saved: {audit.ref_path_file}\n"
                        f"  {audit.ref_path_point_count} pts  |  "
                        f"conf {audit.ref_path_confidence:.2f}  |  "
                        f"No lap data saved (pre-17N format) — re-run calibration once"
                    )
                    lbl.setStyleSheet("color: #E4D0AA; font-size: 10px;")
        except Exception:
            pass  # audit is best-effort; never crash the layout-changed handler

