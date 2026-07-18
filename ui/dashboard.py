"""Main PyQt6 window — 9-tab spec layout per REQUIREMENTS.md Section 12."""
from __future__ import annotations
from ui.track_modelling_ui import TrackModellingMixin
from ui.setup_builder_ui import SetupBuilderMixin
from ui.settings_ui import SettingsMixin
from ui.race_plan_ui import RacePlanMixin
from ui.event_planner_ui import EventPlannerMixin
from ui.live_ui import LiveMixin
import copy
import hashlib
import json
import logging
import math
import queue
import threading
import time
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, QEvent, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QPalette, QFont, QCloseEvent, QPixmap,
    QPainter, QPen, QBrush, QPolygonF,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFormLayout, QGroupBox, QLabel, QPushButton, QCheckBox,
    QSlider, QSpinBox, QDoubleSpinBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QScrollArea, QComboBox, QSplitter, QTextEdit,
    QStatusBar, QFrame, QSizePolicy, QDialog, QStackedWidget, QListWidget,
    QListWidgetItem, QPlainTextEdit, QMessageBox, QAbstractSpinBox,
)

from telemetry.packet import (
    GT7Packet, format_laptime_display, format_laptime_voice, format_delta_voice,
)
from telemetry.state import (
    RacePhase, RaceType, SessionType, TyreState, TyreThresholds, LapRecord, EventType,
    Priority,
)
from data.logger import LapDataLogger
from data.session_db import ms_to_str
from data.exporter import export_to_excel
from ui.track_map_vm import TrackMapDrawData
from voice.announcer import VoiceAnnouncer
from ui.widgets import (
    TyreWidget, FuelBar, ConnectionStatusWidget, BigValueLabel,
)
from ui.gt7_data import GT7_TRACKS, GT7_TRACK_INFO, GT7_CARS, GT7_CARS_BY_CATEGORY, TYRE_TEMP_PRESETS, normalise_compound
from ui.tab_registry import (
    build_default_registry,
    TAB_LIVE, TAB_EVENT_PLANNER, TAB_GARAGE, TAB_SETUP_BUILDER,
    TAB_PRACTICE_REVIEW, TAB_STRATEGY_BUILDER, TAB_TELEMETRY, TAB_DIAGNOSTICS,
    TAB_SETTINGS, TAB_HISTORY, TAB_TRACK_MODELLING,
    TAB_HOME,
)


# ---------------------------------------------------------------------------
# Group 47 — Outcome verification helpers (pure, best-effort, never raise)
# ---------------------------------------------------------------------------

# Structured driver_feedback columns whose text feeds outcome classification.
_FEEDBACK_TEXT_FIELDS = (
    "corner_entry", "mid_corner", "exit_stability", "rear_braking",
    "tyre_condition", "notes",
)


def _combine_driver_feedback_text(feedback_row: dict) -> str:
    """Join a driver_feedback row's free-text/structured fields into one string.

    Used only as evidence for deterministic outcome classification.  Never raises.
    """
    try:
        parts = []
        for f in _FEEDBACK_TEXT_FIELDS:
            v = (feedback_row.get(f) or "").strip()
            if v:
                parts.append(v)
        return "; ".join(parts)
    except Exception:
        return ""


def _verify_change_outcome(
    rule_id: str,
    field: str,
    car_id: int,
    track: str,
    layout_id: str,
    before_window,
    after_window,
    feedback_text: str,
) -> dict:
    """Run the Group 47 outcome-verification model for one applied change.

    Returns a small dict {target_issue, evidence_summary, safety_notes,
    outcome_kind} used to enrich the learning_outcomes record additively.  Any
    failure returns empty strings so the caller's persistence is never disrupted.
    """
    try:
        from strategy.setup_outcome_verification import (
            MetricSnapshot, verify_outcome, infer_target_issue_from_fields,
        )
        target_issue = infer_target_issue_from_fields([field])
        result = verify_outcome(
            rule_id=rule_id,
            car_id=car_id,
            track=track,
            layout_id=layout_id,
            target_issue=target_issue,
            before=MetricSnapshot.from_window(before_window),
            after=MetricSnapshot.from_window(after_window),
            driver_feedback=feedback_text,
        )
        return {
            "target_issue": result.target_issue,
            "evidence_summary": result.evidence_summary,
            "safety_notes": result.safety_notes,
            "outcome_kind": result.outcome.value,
        }
    except Exception:
        return {
            "target_issue": "", "evidence_summary": "",
            "safety_notes": "", "outcome_kind": "",
        }


# ---------------------------------------------------------------------------
# Cross-thread signal bridge
# ---------------------------------------------------------------------------

class SignalBridge(QObject):
    lap_completed           = pyqtSignal(object)      # LapRecord
    connection_changed      = pyqtSignal(bool, float) # connected, hz
    race_state_changed      = pyqtSignal(str)         # phase text
    event_log_entry         = pyqtSignal(str)         # debug log line
    strategy_status_changed = pyqtSignal(str)         # live stint status string
    tyre_preset_changed     = pyqtSignal(str)         # compound name → update tyre thresholds
    car_detected            = pyqtSignal(int, str)    # car_id, car_name (empty if unknown)
    grip_loss_detected      = pyqtSignal(int, str)    # score 0-100, level: normal/watch/warning/significant
    ptt_status              = pyqtSignal(str)         # PTT state: RADIO READY / TRANSMITTING / PROCESSING / ENGINEER RESPONDING
    calibration_packet      = pyqtSignal(object)      # GT7Packet subsampled at ~10 Hz for calibration capture


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

# Canonical display constants — sourced from the NGR design system so the whole
# app shares one palette (ui/ngr_theme.py) instead of ad-hoc hex.
from ui import ngr_theme as _ngrt
_DARK_BG   = _ngrt.CARBON          # was "#1E1E1E" — window surface
_DARK_CARD  = _ngrt.CARBON_RAISED  # was "#2A2A2A" — cards/panels
_TEXT       = _ngrt.TEXT           # was "#E0E0E0" — body text
_ACCENT     = _ngrt.NGR_GREEN      # was "#2EA043" — NGR neon-green accent

from ui.guide_content import GUIDE_HTML as _GUIDE_HTML

# Diagnostic Tab Cleanup (2026-07-03): the _TELEMETRY_REFERENCE_HTML constant
# (the 72-field GT7 UDP packet reference) was dead code - defined but never
# rendered anywhere - and was deleted. The packet format is documented in
# telemetry/parser.py and docs/.


class _NoWheelFilter(QObject):
    """App-wide event filter that stops the mouse wheel from changing spin box
    and combo box values. UAT request: values must change only by typing or by
    clicking the spin buttons, never by an accidental scroll over the control.

    The wheel event is consumed on the control so its value is untouched; scroll
    over the surrounding page (labels, gaps, group boxes) still works normally.
    """

    def eventFilter(self, obj, event):  # noqa: N802 (Qt signature)
        if (event.type() == QEvent.Type.Wheel
                and isinstance(obj, (QAbstractSpinBox, QComboBox))):
            event.ignore()
            return True
        return False


class MainWindow(TrackModellingMixin, SetupBuilderMixin, SettingsMixin, RacePlanMixin, EventPlannerMixin, LiveMixin, QMainWindow):

    _TUNING_CATEGORIES: list[tuple[str, str]] = [
        ("brake_balance", "Brake balance"),
        ("suspension",    "Ride height, springs, dampers, ARB, camber, toe"),
        ("differential",  "LSD (initial, acceleration, braking sensitivity)"),
        ("aero",          "Front and rear downforce"),
        ("transmission",  "Gearbox, final drive, top speed, gear ratios"),
        ("power",         "ECU output, power restrictor"),
        ("ballast",       "Ballast amount and position"),
        ("steering",      "Steering angle / 4-wheel steering"),
        ("nitrous",       "Nitrous / overtake system"),
    ]

    _SETUP_TUNING_GROUPS: dict[str, list[str]] = {
        "tyres":         ["_setup_tyre_f", "_setup_tyre_r"],
        "brake_balance": ["_setup_bb"],
        "suspension":    [
            "_setup_rh_f", "_setup_rh_r",
            "_setup_spr_f", "_setup_spr_r",
            "_setup_dmp_f_comp", "_setup_dmp_f_ext",
            "_setup_dmp_r_comp", "_setup_dmp_r_ext",
            "_setup_arb_f", "_setup_arb_r",
            "_setup_cam_f", "_setup_cam_r",
            "_setup_toe_f", "_setup_toe_r",
        ],
        "differential":  [
            "_setup_lsd_i", "_setup_lsd_a", "_setup_lsd_d",
            "_setup_lsd_f_i", "_setup_lsd_f_a", "_setup_lsd_f_d",
            "_setup_tvcd", "_setup_torque_dist",
        ],
        "aero":          ["_setup_aero_f", "_setup_aero_r"],
        "transmission":  [
            "_setup_trans_type", "_spin_final_drive", "_spin_top_speed",
            "_setup_num_gears",
        ],
        "power":         ["_setup_ecu", "_setup_ecu_output", "_setup_power_rest"],
        "ballast":       ["_setup_ballast_kg", "_setup_ballast_pos"],
        "steering":      [],
        "nitrous":       ["_setup_nitrous", "_setup_nitrous_output"],
    }


    def __init__(
        self,
        config: dict,
        logger: LapDataLogger,
        announcer: VoiceAnnouncer,
        bridge: SignalBridge,
        ui_queue: "queue.Queue[GT7Packet]",
        config_path: str = "config.json",
        tracker=None,
        query_listener=None,
        strategy_engine=None,
        driving_advisor=None,
        recorder=None,
        db=None,
        dispatcher=None,
        udp_listener=None,
    ) -> None:
        super().__init__()
        # Stop the mouse wheel from changing spin/combo values anywhere in the
        # app (values change only by typing or the spin buttons). Kept as an
        # attribute so the filter is not garbage-collected.
        self._no_wheel_filter = _NoWheelFilter(self)
        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self._no_wheel_filter)
        self._config          = config
        self._logger          = logger
        self._announcer       = announcer
        self._bridge          = bridge
        self._ui_queue        = ui_queue
        self._config_path     = config_path
        self._tracker         = tracker
        self._query_listener  = query_listener
        self._strategy_engine = strategy_engine
        self._driving_advisor = driving_advisor
        self._recorder        = recorder
        self._db              = db
        self._dispatcher      = dispatcher
        # Real UDP connection source (SessionContext connection-signal sprint,
        # 2026-07-04): the UDPListener owns the true connected/packet stats
        # (packet-timeout based). Duck-typed — needs .connected /
        # .total_received / .parse_errors / .packet_rate. None in tests/legacy
        # constructions → the old (always-False) tracker fallbacks apply.
        self._udp_listener    = udp_listener
        self._last_packet: Optional[GT7Packet] = None
        self._last_packet_received: float = 0.0  # Group 24 AC4: wall-clock of last received packet
        # Group 61: display-only live-progress stabiliser state (created on first use).
        self._live_stabiliser_state = None
        # Group 61: OFF-by-default raw road-distance capture (diagnostic, read-only).
        self._raw_rd_capture = None
        # UAT #6 Phase 1b/2A: live event-lap path capture for continuous
        # track-model refinement (auto-started during events when an accepted
        # model exists; also manually from the Track Modelling tab).
        self._track_path_capture = None
        self._last_refine_autostart_check = 0.0  # throttle for the auto-start probe
        self._refine_notice = ""                 # last "refined model available" notice
        # Live per-corner telemetry aggregation (inert until a track/layout is active).
        self._live_corner_tel = None
        self._live_corner_tel_key = None
        self._gear_ratios_captured: bool = False
        self._lap_compound_tags: dict[int, str] = {}
        self._default_lap_compound: str = ""
        self._strategy_result_queue: queue.Queue = queue.Queue()
        self._strategy_options: list = []
        self._strategy_options_html_base: str = ""
        self._setup_result_queue: queue.Queue = queue.Queue()
        self._practice_result_queue: queue.Queue = queue.Queue()
        self._build_setup_queue: queue.Queue = queue.Queue()
        self._baseline_result_queue: queue.Queue = queue.Queue()
        self._degradation_result_queue: queue.Queue = queue.Queue()
        self._profile_update_queue: queue.Queue = queue.Queue()
        self._tyre_degradation_cache: dict = {}
        self._strat_practice_sid: int = 0  # practice session id captured at pre-race analysis time
        self._pit_lane_active: bool = False  # Group 21B — pit lane transition tracking
        self._tm_cached_draw_data: Optional[TrackMapDrawData] = None  # AC1 dirty-flag cache
        self._live_label_cache: dict[str, str] = {}  # AC3 label dirty-flag cache
        # Load saved setups from DB if available; fall back to config on first run
        if db is not None:
            _db_setups = db.get_all_setups_legacy()
            if _db_setups:
                self._saved_setups = _db_setups
            else:
                self._saved_setups = list(config.get("car_setup", {}).get("setups", []))
                self._migrate_setup_ids()
                self._migrate_setups_to_db()
        else:
            self._saved_setups = list(config.get("car_setup", {}).get("setups", []))
            self._migrate_setup_ids()

        # Declared "setup running this stint" (label string). Set from the Live
        # practice panel, editable in Practice Review, and passed to the AI with
        # driver feedback so the setup fix knows which setup was on the car.
        self._live_running_setup: str = ""

        # UAT Finding 1: canonical applied-setup authority — the single owner of
        # "the setup that is actually on the car right now". The Live Race
        # Engineer defaults its baseline to this; the running-setup combo is only
        # a manual override. Backed by a small JSON file next to the config so the
        # last confirmed active setup restores after restart (and stays isolated
        # under the temp config used by tests).
        from data.setup_state_authority import ActiveSetupAuthority
        from data.active_setup_store import JsonActiveSetupStore
        _authority_store = None
        try:
            if self._config_path:
                _authority_store = JsonActiveSetupStore(
                    Path(self._config_path).with_name("active_setup_state.json"))
        except Exception:
            _authority_store = None
        self._setup_authority = ActiveSetupAuthority(store=_authority_store)

        # UAT Finding 2 wiring: per-lap slip-episode buffers feeding Practice
        # Analysis. Populated at lap completion in Practice mode; reset per
        # session so cross-session data never mixes.
        self._practice_lap_episodes: dict = {}
        self._practice_clean_laps: set = set()
        self._practice_total_laps: set = set()
        self._practice_corner_names: dict = {}
        self._practice_track_corners: list = []
        # Live references to in-flight analysis workers (QThreads) so they are
        # not garbage-collected mid-run. See _run_analysis_async.
        self._analysis_workers: set = set()

        self.setWindowTitle("Next Gear Racing Pit Crew")
        self.setMinimumSize(1100, 700)
        self._apply_dark_theme()
        self._setup_ui()
        self._connect_signals()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._poll_ui_queue)
        self._refresh_timer.start(config.get("ui", {}).get("refresh_ms", 100))

        # Restore persisted race plan stints into Strategy Builder only (Live tab starts with "No plan loaded")
        _saved_stops = self._config.get("strategy", {}).get("stops", [])
        if _saved_stops:
            for _d in _saved_stops:
                self._strategy_add_stint(preset=_d)

        # Load most recent saved race plan into the strategy engine (if available)
        if self._strategy_engine is not None:
            self._live_init_from_plan()
            # Wire the mid-race re-plan callback so the engine can launch the worker
            self._strategy_engine._replan_callback = self._launch_replan_worker

        # Restore last AI strategy analysis so results survive app restart
        self._restore_strategy_cache()

        # Push the saved live mode to tracker, announcer and strategy engine.
        # Without this call, the mode defaults to "Race" until the user touches
        # the combo — causing pit/fuel alerts in Practice and wrong session type.
        _saved_mode = self._config.get("live", {}).get("mode", "Race")
        if hasattr(self, "_combo_live_mode"):
            self._combo_live_mode.blockSignals(True)
            self._combo_live_mode.setCurrentText(_saved_mode)
            self._combo_live_mode.blockSignals(False)
        self._on_live_mode_changed(_saved_mode)

        if self._query_listener is not None:
            self._query_listener.set_active_setup_getter(self._current_setup_dict)

        # Home Dashboard Promotion (2026-07-03): Home is the default landing tab,
        # so render it once now that every context source it reads is wired.
        # Guarded/defensive — never blocks startup.
        self._home_refresh()

        # Phase 6a: align the telemetry dispatcher's frozen SessionTag with the
        # canonical contexts at startup (the dispatcher seeded itself from the
        # raw config at construction; identical in-sync — this is belt-and-
        # braces before its thread starts).
        self._push_session_tag()

        # Group 62: startup-restore ABS regulation into the engine so that an
        # already-active event keeps its ABS setting without the user having to
        # click "Set as Active" again after app restart.
        if getattr(self, "_strategy_engine", None) is not None:
            _startup_ae = self._active_event()
            if _startup_ae:
                self._strategy_engine.set_abs_allowed(
                    bool(_startup_ae.get("abs", True))
                )

    # ------------------------------------------------------------------ UI setup

    def _setup_ui(self) -> None:
        self._status_bar = ConnectionStatusWidget()
        self.statusBar().addPermanentWidget(self._status_bar, 1)

        self._tabs = QTabWidget()
        self._tabs.setFont(QFont("Segoe UI", 10))

        _strategy_builder_widget = self._build_strategy_builder_tab()

        # Home Dashboard Promotion (2026-07-03): the Race Engineer Command Centre
        # LEADS the tab bar and is the default landing page. The move is
        # order-only — DEFAULT_TAB_ORDER in ui/tab_registry.py leads with
        # TAB_HOME and the (positional) registry re-derives every index, so no
        # dispatch, navigation, or visibility code references a raw position.
        self._tabs.addTab(self._build_home_tab(),             "Home")             # 0
        self._tabs.addTab(self._build_live_tab(),             "Live Race Engineer") # 1
        self._tabs.addTab(self._build_event_planner_tab(),    "Event Planner")   # 2
        self._tabs.addTab(self._build_garage_tab(),           "Garage")           # 3
        self._tabs.addTab(self._build_setup_builder_tab(),    "Setup Builder")    # 4
        self._tabs.addTab(self._build_practice_review_tab(),  "Practice Review")  # 5
        self._tabs.addTab(_strategy_builder_widget,           "Strategy Builder") # 6
        self._tabs.addTab(self._build_telemetry_tab(),        "Telemetry")        # 7
        self._tabs.addTab(self._build_debug_tab(),            "Diagnostics")      # 8
        self._tabs.addTab(self._build_settings_tab(),         "Settings")         # 9
        self._tabs.addTab(self._build_history_tab(),          "History")          # 10
        self._tabs.addTab(self._build_track_modelling_tab(), "Track Modelling")  # 12
        # Tab Navigation Refactor (2026-07-03): stable tab keys, registered in
        # the SAME order as the addTab calls above (DEFAULT_TAB_ORDER mirrors
        # them; a source-scan test + this count check guard the pairing).
        # Dispatch and navigation go through the registry, never raw indices.
        self._tab_registry = build_default_registry()
        if self._tab_registry.count != self._tabs.count():  # pragma: no cover
            logging.warning(
                "Tab registry mismatch: %d keys vs %d tabs — update "
                "DEFAULT_TAB_ORDER in ui/tab_registry.py",
                self._tab_registry.count, self._tabs.count(),
            )
        # Product Consolidation Sprint: flag advanced/diagnostic tool tabs so the
        # normal race-engineer workflow reads cleanly. Roles are owned by
        # ui/product_flow.py (single source of truth); this only decorates the
        # tab titles and never changes tab order or indices (and the registry
        # is positional, so decorated labels can never break key lookup).
        self._apply_product_flow_tab_markers()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._tabs)
        # Home Dashboard Promotion (2026-07-03): open the app on Home. Home is
        # the first tab (index 0) so it is already current, but select by stable
        # key to make the landing tab explicit and position-independent. The
        # first render is triggered once at the end of __init__ via
        # _home_refresh() (state the dashboard reads is fully wired by then).
        self.select_tab(TAB_HOME)

    # --- Named tab navigation (Tab Navigation Refactor, 2026-07-03) ----------
    #
    # These helpers are the only sanctioned way to locate or select a tab.
    # All are safe on unknown keys (no-ops / -1 / None — never raise) so
    # future callers (e.g. Home click-to-navigate) cannot crash the UI.

    def get_tab_index(self, tab_key: str) -> int:
        """Current index for a stable tab key, or -1 when unknown."""
        reg = getattr(self, "_tab_registry", None)
        return reg.index_of(tab_key) if reg is not None else -1

    def has_tab(self, tab_key: str) -> bool:
        """True when the key is registered on the tab bar."""
        return self.get_tab_index(tab_key) >= 0

    def current_tab_key(self):
        """Stable key of the currently selected tab, or None."""
        reg = getattr(self, "_tab_registry", None)
        if reg is None or not hasattr(self, "_tabs"):
            return None
        return reg.key_at(self._tabs.currentIndex())

    def select_tab(self, tab_key: str) -> bool:
        """Select a tab by stable key. Returns False (no-op) on unknown keys."""
        idx = self.get_tab_index(tab_key)
        if idx < 0 or not hasattr(self, "_tabs"):
            return False
        self._tabs.setCurrentIndex(idx)
        return True

    def _apply_product_flow_tab_markers(self) -> None:
        """Prefix advanced/diagnostic tabs with a tool marker (see product_flow).

        Idempotent and display-only — tab indices used by _on_tab_changed are
        unaffected. Kept defensive so a UI import issue can never block startup.
        """
        try:
            from ui import product_flow
        except Exception:  # pragma: no cover - defensive; UI must still launch
            return
        for i in range(self._tabs.count()):
            self._tabs.setTabText(i, product_flow.decorate_tab_title(self._tabs.tabText(i)))

    # --- Home tab (Race Engineer Command Centre) -----------------------------
    #
    # Home Dashboard sprint (2026-07-03): the overview surface the audit found
    # was never built (REQUIREMENTS.md §12.2, audit §1.1). Display-only — it
    # renders ui/home_dashboard_vm.py state built from the canonical contexts
    # and owns/mutates no domain state. Refreshes when shown (_on_tab_changed)
    # and via _home_refresh_if_visible() hooks after key workflow actions.
    #
    # Home Dashboard Promotion (2026-07-03): Home leads the tab bar and its
    # cards offer click-to-navigate to the relevant tool tab via select_tab
    # (stable keys only). Navigation is tab-change only — see _home_navigate.

    # Shared style for the Home click-to-navigate buttons.
    _HOME_NAV_BTN_QSS = (
        "QPushButton { background: #333333; color: #E0E0E0;"
        " border: 1px solid #555; border-radius: 4px; padding: 3px 12px;"
        " font-size: 11px; }"
        "QPushButton:hover { background: #3A5A8A; border-color: #5A7ABA; }"
    )

    def _home_nav_button_text(self, tab_key: str) -> str:
        """"Open <Tab>" label from the UNDECORATED base title (never the ⚙
        label). Falls back to a plain "Open" if the key is unknown."""
        try:
            from ui.tab_registry import TAB_BASE_TITLES
            base = TAB_BASE_TITLES.get(tab_key)
            return f"Open {base}" if base else "Open"
        except Exception:  # pragma: no cover - defensive
            return "Open"

    def _home_navigate(self, tab_key: str) -> None:
        """Navigate from a Home card to a tool tab. **Tab-change only** — it
        never mutates domain state, starts AI/telemetry/calibration, or saves.
        Safe no-op when the target tab is unavailable (select_tab returns
        False on an unknown key). Never raises out to the UI."""
        try:
            if not tab_key or not self.has_tab(tab_key):
                return
            self.select_tab(tab_key)
        except Exception:  # pragma: no cover - defensive
            pass

    def _home_navigate_next_action(self) -> None:
        """Open the next-best-action's recommended tab (resolved in
        _home_refresh). No-op if nothing is currently recommended."""
        self._home_navigate(getattr(self, "_home_next_action_tab_key", None))

    def _build_home_tab(self) -> QWidget:
        from ui.home_dashboard_vm import CARD_ORDER
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # NGR-branded command-centre header: official logo slot on the left, a
        # strong uppercase identity, then the refresh control on the right. The
        # logo is the official supplied asset (repo-root logo.png), read-only and
        # scaled for display — never recoloured, cropped, or regenerated. If it is
        # missing we show a clean text slot rather than inventing a mark.
        from ui import ngr_theme as _ngr
        header_bar = QWidget()
        header_bar.setStyleSheet(
            f"background: {_ngr.INK_BLACK}; border: 1px solid {_ngr.HAIRLINE};"
            f" border-radius: {_ngr.RADIUS_MD}px;"
        )
        header_row = QHBoxLayout(header_bar)
        header_row.setContentsMargins(14, 10, 14, 10)
        header_row.setSpacing(12)

        self._home_logo_slot = QLabel()
        self._home_logo_slot.setObjectName("ngrLogoSlot")
        _pix = _ngr.logo_pixmap(height=34)
        if _pix is not None:
            self._home_logo_slot.setPixmap(_pix)
        else:
            self._home_logo_slot.setText(_ngr.logo_placeholder_text())
            self._home_logo_slot.setStyleSheet(
                f"color: {_ngr.NGR_GREEN}; font-weight: 700; letter-spacing: 1px;")
        self._home_logo_slot.setToolTip("Next Gear Racing")
        header_row.addWidget(self._home_logo_slot, 0, Qt.AlignmentFlag.AlignVCenter)

        _title_col = QVBoxLayout()
        _title_col.setSpacing(0)
        title = QLabel("RACE ENGINEER COMMAND CENTRE")
        title.setStyleSheet(_ngr.heading_qss(1))
        _subtitle = QLabel("NGR Pit Crew · Race Intelligence")
        _subtitle.setStyleSheet(
            f"color: {_ngr.TEXT_DIM}; font-size: {_ngr.FS_CAPTION}pt; letter-spacing: 1px;")
        _title_col.addWidget(title)
        _title_col.addWidget(_subtitle)
        header_row.addLayout(_title_col)
        header_row.addStretch()

        self._home_btn_refresh = QPushButton("Refresh")
        self._home_btn_refresh.setStyleSheet(_ngr.secondary_button_qss())
        self._home_btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_btn_refresh.clicked.connect(self._home_refresh)
        header_row.addWidget(self._home_btn_refresh, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(header_bar)

        # Sprint 10: guided workflow stepper — the "follow the bouncing ball"
        # 12-stage journey. Clicking its next-action button navigates to the tab
        # the current stage lives on.
        try:
            from ui.workflow_stepper_widget import WorkflowStepper
            self._home_stepper = WorkflowStepper()
            self._home_stepper.go_to_tab.connect(self.select_tab)
            root.addWidget(self._home_stepper)
        except Exception:
            self._home_stepper = None

        # Next-best-action banner + a click-to-navigate button (Home Dashboard
        # Promotion). The button opens the recommended tab via select_tab; its
        # target is resolved in _home_refresh from the flow summary's tab name
        # (mapped to a stable key with tab_registry.key_for_title).
        na_banner = QWidget()
        na_banner.setStyleSheet(
            f"background: {_DARK_CARD}; border-left: 4px solid #F5C542;"
            " border-radius: 6px;"
        )
        na_row = QHBoxLayout(na_banner)
        na_row.setContentsMargins(14, 10, 14, 10)
        self._home_next_action_lbl = QLabel("")
        self._home_next_action_lbl.setWordWrap(True)
        self._home_next_action_lbl.setTextFormat(Qt.TextFormat.RichText)
        na_row.addWidget(self._home_next_action_lbl, 1)
        self._home_next_action_btn = QPushButton("Open")
        self._home_next_action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_next_action_btn.setStyleSheet(self._HOME_NAV_BTN_QSS)
        self._home_next_action_btn.clicked.connect(self._home_navigate_next_action)
        self._home_next_action_btn.setVisible(False)
        self._home_next_action_tab_key = None
        na_row.addWidget(self._home_next_action_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(na_banner)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)
        from ui.home_dashboard_vm import tab_key_for_card
        self._home_card_labels = {}
        for i, key in enumerate(CARD_ORDER):
            cell = QWidget()
            cell.setStyleSheet(
                f"background: {_DARK_CARD}; border-radius: 6px;")
            cell_l = QVBoxLayout(cell)
            cell_l.setContentsMargins(10, 10, 10, 8)
            cell_l.setSpacing(6)

            lbl = QLabel("—")
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            lbl.setStyleSheet("background: transparent;")
            self._home_card_labels[key] = lbl
            cell_l.addWidget(lbl, 1)

            # Click-to-navigate: an "Open <Tab>" button per mapped card. Stable
            # key only (never the visible label) so the ⚙ decoration is
            # irrelevant. Tab-change only — see _home_navigate.
            tab_key = tab_key_for_card(key)
            if tab_key:
                btn = QPushButton(self._home_nav_button_text(tab_key))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(self._HOME_NAV_BTN_QSS)
                btn.setToolTip("Open this tool tab")
                btn.clicked.connect(
                    lambda _checked=False, k=tab_key: self._home_navigate(k))
                btn_row = QHBoxLayout()
                btn_row.setContentsMargins(0, 0, 0, 0)
                btn_row.addStretch(1)
                btn_row.addWidget(btn)
                cell_l.addLayout(btn_row)

            grid.addWidget(cell, i // 2, i % 2)
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # User Guide + reference, folded in from the old Guide tab (collapsed by
        # default). Keeps the how-to where the workflow starts.
        root.addWidget(self._build_guide_reference_widget())
        return w

    def _build_home_dashboard_state(self):
        """Assemble the Home Dashboard view-model state from the canonical
        contexts. Read-only: every input comes from the existing context
        builders (or captured contexts); nothing is written anywhere."""
        from ui.home_dashboard_vm import build_home_dashboard_state
        event_ctx = self._build_event_context()
        strategy_ctx = self._build_strategy_context()
        # The latest displayed setup recommendation (State Consolidation 3
        # capture). None until a setup result has been displayed this session.
        setup_ctx = getattr(self, "_last_setup_context", None)
        track_ctx = self._build_track_context()
        # Pure computation of what the AI-input snapshot would be right now —
        # no AI call is made; this reports frozen-vs-legacy input status.
        ai_snap = self._build_strategy_inputs()
        # SessionContext sprint: route the live/practice flags through the
        # canonical SessionContext instead of reaching into tracker internals.
        # `has_valid_laps` still approximates "recorded laps are reviewable"
        # (the DB query is owned by _home_has_practice_laps); SessionContext now
        # carries both flags plus live_active. Byte-identical to the prior reads.
        has_laps = self._home_has_practice_laps(event_ctx)
        session_ctx = self._build_session_context(
            has_practice_laps=has_laps, has_valid_laps=has_laps)
        # OFR-1: query DB for real learning state to light up journey step-13.
        learning = False
        try:
            if self._db is not None and event_ctx.car:
                _cid = self._db.get_car_id(event_ctx.car)
                if _cid:
                    learning = self._db.has_learning_for_car_track(_cid, event_ctx.track)
        except Exception:
            learning = False
        # Sprint 3: single disk-first track-readiness verdict. Uses the resolved
        # identity so the Command Centre reflects on-disk assets without opening
        # Track Modelling. Every other screen calls the same resolver.
        track_readiness = None
        try:
            from data.track_readiness_disk import resolve_track_readiness_from_disk
            _tid = getattr(track_ctx, "identity", None)
            _loc = str(getattr(_tid, "track_location_id", "") or "")
            _lay = str(getattr(_tid, "layout_id", "") or "")
            if _loc and _lay:
                track_readiness = resolve_track_readiness_from_disk(_loc, _lay)
        except Exception:
            track_readiness = None

        # Sprint 10: stash the guided-workflow inputs for the Home stepper. Uses
        # the strong signals available here; the applied-in-GT7 / pending-change
        # signals come from the setup-apply checkpoint set in Setup Builder.
        try:
            from ui.workflow_stepper import WorkflowInputs
            _setup_saved = bool(getattr(setup_ctx, "has_active_setup", False))
            _apply = getattr(self, "_setup_apply_status", None)
            self._home_workflow_inputs = WorkflowInputs(
                event_ready=bool(getattr(event_ctx, "car", "") and getattr(event_ctx, "track", "")),
                track_ready=bool(track_readiness and getattr(track_readiness, "is_ready", False)),
                track_blocker=(track_readiness.blockers[0] if track_readiness
                               and getattr(track_readiness, "blockers", ()) else ""),
                setup_saved=_setup_saved,
                setup_applied_in_gt7=bool(getattr(_apply, "is_confirmed", False)),
                setup_pending_changes=len(getattr(_apply, "pending_fields", ()) or ()),
                practice_captured=bool(has_laps),
                engineering_reviewed=_setup_saved,
                strategy_evidence_ready=bool(session_ctx.has_valid_laps),
                # Sprint 10 piece 4: lit once a race plan is built from a practice
                # bundle (see _run_race_plan_from_practice).
                race_plan_built=bool(getattr(self, "_race_plan_built", False)),
            )
        except Exception:
            self._home_workflow_inputs = None

        return build_home_dashboard_state(
            event_context=event_ctx,
            strategy_context=strategy_ctx,
            setup_context=setup_ctx,
            track_context=track_ctx,
            track_readiness=track_readiness,
            ai_snapshot=ai_snap,
            has_practice_laps=session_ctx.has_practice_laps,
            has_valid_laps=session_ctx.has_valid_laps,
            live_active=session_ctx.live_active,
            learning_saved=learning,
        )

    def _home_has_practice_laps(self, event_ctx) -> bool:
        """True when saved sessions with laps exist for the active car/track.
        Read-only DB query; defensive — returns False on any failure."""
        try:
            if self._db is None:
                return False
            car = getattr(event_ctx, "car", "") or ""
            track = getattr(event_ctx, "track", "") or ""
            if not car and not track:
                return False
            for s in self._db.get_all_sessions(limit=60):
                if car and (s.get("car_name") or "") != car:
                    continue
                if track and (s.get("track") or "") != track:
                    continue
                if int(s.get("total_laps") or 0) > 0:
                    return True
            return False
        except Exception:
            return False

    def _home_refresh(self) -> None:
        """Rebuild and render the Home Dashboard. Display-only; never raises."""
        if not hasattr(self, "_home_card_labels"):
            return
        try:
            from ui import home_dashboard_vm as hdvm
            state = self._build_home_dashboard_state()
            self._home_next_action_lbl.setText(
                hdvm.format_next_action_html(state.next_action))
            self._home_update_next_action_button(state.next_action)
            # Sprint 10: update the guided workflow stepper.
            _stepper = getattr(self, "_home_stepper", None)
            _wf = getattr(self, "_home_workflow_inputs", None)
            if _stepper is not None and _wf is not None:
                from ui.workflow_stepper import build_workflow_state
                _stepper.set_state(build_workflow_state(_wf))
            for key, lbl in self._home_card_labels.items():
                card = state.card(key)
                if card is not None:
                    lbl.setText(hdvm.format_card_html(card))
        except Exception:  # pragma: no cover - defensive; must never break the UI
            pass

    def _home_update_next_action_button(self, next_action) -> None:
        """Point the next-action button at the recommended tab, or hide it.

        The flow summary reports a display NAME ("Setup Builder"); resolve it to
        a stable key with tab_registry.key_for_title (⚙-decoration-safe). The
        button is hidden when the journey is complete or the name doesn't map to
        a real tab — no dependence on visible labels, no domain state touched."""
        btn = getattr(self, "_home_next_action_btn", None)
        if btn is None:
            return
        try:
            from ui.tab_registry import key_for_title
            tab_name = getattr(next_action, "tab", "") or ""
            complete = bool(getattr(next_action, "complete", False))
            key = key_for_title(tab_name) if tab_name and not complete else None
            self._home_next_action_tab_key = key
            if key and self.has_tab(key):
                btn.setText(self._home_nav_button_text(key))
                btn.setVisible(True)
            else:
                btn.setVisible(False)
        except Exception:  # pragma: no cover - defensive
            self._home_next_action_tab_key = None
            btn.setVisible(False)

    def _home_refresh_if_visible(self) -> None:
        """Refresh the Home Dashboard only when it is the current tab — the
        cheap hook workflow actions call so an open Home tab stays current
        without adding polling or background work."""
        try:
            if not hasattr(self, "_tabs") or not hasattr(self, "_home_card_labels"):
                return
            if self.current_tab_key() != TAB_HOME:
                return
            self._home_refresh()
        except Exception:  # pragma: no cover - defensive
            pass

    def _trigger_scoring_pass(
        self,
        car_id: int,
        track: str,
        layout_id: str,
        new_session_id: int,
    ) -> None:
        """OFR-1: score any applied-but-unscored setup recommendations from the
        prior session for this car+track immediately after a new session opens.

        What: fetches the most-recent finished session (before new_session_id),
        collects any applied-but-unscored recs for car+track+layout, scores each
        via pure recommendation_scoring helpers, persists the result, then nudges
        the Home Dashboard if ≥1 non-trivial verdict was written.

        Why: the scoring window is only knowable once the next session opens —
        that moment confirms the driver has finished a session with the new setup
        applied, so before/after telemetry can be compared.

        Never raises: the entire body is wrapped in try/except so a DB hiccup or
        unexpected data cannot block session opening.  Inputs come in as explicit
        params — never reads config['strategy']."""
        try:
            # Guard: DB must be present and car+track must be identified.
            if self._db is None or car_id <= 0 or not track:
                return
            # Resolve the "after" session: the session just finished (most recent
            # session for this car+track before the freshly opened new_session_id).
            after_sid = self._db.get_previous_session_id(car_id, track, new_session_id)
            if not after_sid:
                return
            # Fetch recs that are applied but not yet scored for this layout.
            recs = self._db.get_applied_unverified_recs(car_id, track, layout_id)
            # Skip any rec that was created in the after session itself —
            # a recommendation cannot be scored against its own creation session.
            scoreable = [r for r in recs if r.get("session_id") != after_sid]
            if not scoreable:
                return
            from data.recommendation_scoring import (
                aggregate_lap_window,
                compute_verdict_and_confidence,
            )
            # Fetch after-side laps once (shared across all recs).
            after_laps = self._db.get_laps_for_scoring(after_sid)
            after_window = aggregate_lap_window(after_laps)
            multi_count = len(scoreable)
            # Query driver feedback once for this car+track (not per rec).
            _feedback_rows = self._db.get_recent_feedback(car_id, track)
            has_driver_feedback = bool(_feedback_rows)
            # Group 47: build a single feedback string from the most-recent row's
            # free-text/structured fields for deterministic outcome classification.
            _feedback_text = _combine_driver_feedback_text(
                _feedback_rows[0] if _feedback_rows else {}
            )
            written = 0
            for rec in scoreable:
                # Fetch before-side laps per rec (each rec may have been created
                # in a different earlier session).
                before_laps = self._db.get_laps_for_scoring(rec["session_id"])
                before_window = aggregate_lap_window(before_laps)
                result = compute_verdict_and_confidence(
                    rec, before_window, after_window,
                    multi_rec_count=multi_count,
                    has_driver_feedback=has_driver_feedback,
                )
                self._db.persist_score(
                    result.rec_id, result.verdict, result.confidence, result.details
                )
                # Engineering-Brain Phase 1: stamp the measured verdict onto the setup
                # lineage node this rec produced, so rollback can find a worse setup.
                if result.verdict != "insufficient_data":
                    try:
                        self._db.record_lineage_outcome_by_rec(
                            result.rec_id, result.verdict, after_sid)
                    except Exception:
                        pass
                # Group 46: record per-rule learning outcomes (best-effort, never raises).
                # Only when verdict is not "insufficient_data" (no signal — skip).
                if result.verdict != "insufficient_data":
                    written += 1
                    try:
                        _ac_json = rec.get("approved_changes_json") or ""
                        if _ac_json:
                            _ac_list = json.loads(_ac_json)
                            if isinstance(_ac_list, list):
                                # All recs in get_applied_unverified_recs come from
                                # the analyse path (baseline path never calls
                                # insert_setup_recommendations), so source_path is "Analyse".
                                _source_path = "Analyse"
                                # session_type is not stored on setup_recommendations;
                                # default to "" (learning_outcomes schema has NOT NULL DEFAULT '').
                                _session_type_lo = ""
                                _dpv = rec.get("driver_profile_version") or ""
                                _rev = rec.get("rule_engine_version") or ""
                                for _ch in _ac_list:
                                    if not isinstance(_ch, dict):
                                        continue
                                    _rule_id = _ch.get("rule_id", "")
                                    if not _rule_id:
                                        continue
                                    # Group 47: derive richer outcome-verification
                                    # evidence for this change.  The persisted
                                    # confidence-feed `verdict` stays the telemetry
                                    # OFR-1 verdict (non-regressive); the typed
                                    # outcome_kind + evidence/feedback/safety notes
                                    # are stored additively for explainability.
                                    _g47 = _verify_change_outcome(
                                        _rule_id, _ch.get("field", ""),
                                        car_id, track, layout_id,
                                        before_window, after_window, _feedback_text,
                                    )
                                    self._db.record_learning_outcome(
                                        car_id=car_id,
                                        track=track,
                                        layout_id=layout_id,
                                        session_id=after_sid,
                                        session_type=_session_type_lo,
                                        rule_id=_rule_id,
                                        source_path=_source_path,
                                        verdict=result.verdict,
                                        confidence=result.confidence,
                                        driver_profile_version=_dpv,
                                        rule_engine_version=_rev,
                                        target_issue=_g47["target_issue"],
                                        evidence_summary=_g47["evidence_summary"],
                                        driver_feedback=_feedback_text,
                                        safety_notes=_g47["safety_notes"],
                                        outcome_kind=_g47["outcome_kind"],
                                    )
                    except Exception:
                        pass  # learning persistence is best-effort — never disrupt scoring
            print(f"[Learning] scored {len(scoreable)} recommendation(s) for "
                  f"{car_id}/{track} ({written} non-trivial)")
            if written >= 1:
                self._home_refresh_if_visible()
        except Exception as exc:
            print(f"[Learning] scoring pass error: {exc}")

    # --- Live tab -----------------------------------------------------------


    # --- Live tab mode panels -----------------------------------------------







    def _on_shift_beep_setting_changed(self, *_args) -> None:
        """Persist shift-beep settings to config and mirror to Setup spinboxes."""
        sb = self._config.setdefault("shift_beep", {})
        sb["enabled"]  = self._chk_shift_beep_enabled.isChecked()
        sb["qual_rpm"] = self._spin_live_shift_rpm_qual.value()
        sb["race_rpm"] = self._spin_live_shift_rpm_race.value()
        self._persist_config()
        # Mirror to read-only Setup-tab spinboxes (they display but cannot be
        # edited; blockSignals avoids triggering any re-entrant save handlers).
        if hasattr(self, "_spin_shift_rpm_qual"):
            self._spin_shift_rpm_qual.blockSignals(True)
            self._spin_shift_rpm_qual.setValue(sb["qual_rpm"])
            self._spin_shift_rpm_qual.blockSignals(False)
        if hasattr(self, "_spin_shift_rpm_race"):
            self._spin_shift_rpm_race.blockSignals(True)
            self._spin_shift_rpm_race.setValue(sb["race_rpm"])
            self._spin_shift_rpm_race.blockSignals(False)

    # --- Settings tab -------------------------------------------------------


    # --- Telemetry tab ------------------------------------------------------

    def _build_telemetry_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        def _grp(title):
            g = QGroupBox(title)
            g.setStyleSheet(self._group_style())
            return g

        _k = f"color: {_TEXT}; font-size: 11px;"
        _v = "color: #AAE4AA; font-size: 11px;"

        def _row(form, key, attr_name, default="—"):
            lbl = QLabel(default, styleSheet=_v)
            setattr(self, attr_name, lbl)
            form.addRow(QLabel(key, styleSheet=_k), lbl)

        # --- Group 1: Connection ---
        g1 = _grp("Connection")
        f1 = QFormLayout(g1)
        f1.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._telem_lbl_connection = QLabel("—", styleSheet=_v)
        f1.addRow(QLabel("Status:", styleSheet=_k), self._telem_lbl_connection)
        _host = self._config.get("connection", {}).get("host", "127.0.0.1")
        _port = self._config.get("connection", {}).get("port", 33741)
        _row(f1, "Console host:port:", "_telem_lbl_host", f"{_host}:{_port}")
        _row(f1, "UDP listener:", "_telem_lbl_udp_status", "Starting…")
        _row(f1, "Packet rate:", "_telem_lbl_pkt_rate_t", "— Hz")
        _row(f1, "Total packets:", "_telem_lbl_pkt_total_t", "0")
        _row(f1, "Errors:", "_telem_lbl_pkt_errors_t", "0")
        _row(f1, "Last packet:", "_telem_lbl_last_pkt", "—")
        layout.addWidget(g1)

        # --- Group 2: Session ---
        g2 = _grp("Session")
        f2 = QFormLayout(g2)
        f2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._telem_lbl_event     = QLabel("—", styleSheet=_v)
        self._telem_lbl_car       = QLabel("—", styleSheet=_v)
        self._telem_lbl_track     = QLabel("—", styleSheet=_v)
        self._telem_lbl_recording = QLabel("—", styleSheet=_v)
        f2.addRow(QLabel("Active event:", styleSheet=_k), self._telem_lbl_event)
        f2.addRow(QLabel("Car:", styleSheet=_k), self._telem_lbl_car)
        f2.addRow(QLabel("Track:", styleSheet=_k), self._telem_lbl_track)
        _row(f2, "Session mode:", "_telem_lbl_session_mode", "—")
        _row(f2, "Active setup:", "_telem_lbl_setup", "—")
        f2.addRow(QLabel("Recording:", styleSheet=_k), self._telem_lbl_recording)
        layout.addWidget(g2)

        # --- Group 3: Live Packet Data ---
        g3 = _grp("Live Packet Data (10 Hz)")
        f3 = QFormLayout(g3)
        f3.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _row(f3, "Speed:", "_telem_lbl_speed", "— km/h")
        _row(f3, "Gear:", "_telem_lbl_gear", "—")
        _row(f3, "RPM:", "_telem_lbl_rpm_t", "—")
        _row(f3, "Throttle:", "_telem_lbl_throttle_t", "—")
        _row(f3, "Brake:", "_telem_lbl_brake_t", "—")
        _row(f3, "Fuel remaining:", "_telem_lbl_fuel_t", "—")
        _row(f3, "Fuel burn avg:", "_telem_lbl_fuel_burn_t", "— (no data)")
        _row(f3, "Tyre compound:", "_telem_lbl_compound", "—")
        _row(f3, "Tyre temps F/R:", "_telem_lbl_temps", "—")
        _row(f3, "Tyre radius F/R:", "_telem_lbl_radius", "—")
        _row(f3, "Position XYZ:", "_telem_lbl_xyz", "—")
        _row(f3, "Road surface Y:", "_telem_lbl_road", "—")
        _row(f3, "Max speed (lap):", "_telem_lbl_max_speed", "—")
        layout.addWidget(g3)

        # --- Group 4: Lap Times ---
        g4 = _grp("Lap Times")
        f4 = QFormLayout(g4)
        f4.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _row(f4, "Current lap #:", "_telem_lbl_lap_num", "—")
        _row(f4, "Last lap:", "_telem_lbl_last_lap_t", "—")
        _row(f4, "Best lap:", "_telem_lbl_best_lap_t", "—")
        layout.addWidget(g4)

        # --- Group 5: Events (since lap start) ---
        g5 = _grp("Lap Events (last completed lap)")
        f5 = QFormLayout(g5)
        f5.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        _row(f5, "Lock-up events:", "_telem_lbl_lockups", "0")
        _row(f5, "Wheelspin events:", "_telem_lbl_wheelspin", "0")
        _row(f5, "Oversteer events:", "_telem_lbl_oversteer", "0")
        _row(f5, "Rev limiter hits:", "_telem_lbl_revlim", "0")
        _row(f5, "Kerb events:", "_telem_lbl_kerbs", "0")
        _row(f5, "Bottoming events:", "_telem_lbl_bottom", "0")
        _row(f5, "AI last call:", "_telem_lbl_ai_status", "No AI calls this session")
        self._telem_lbl_packets = self._telem_lbl_pkt_total_t  # backward-compat alias
        layout.addWidget(g5)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _update_telemetry_labels(self) -> None:
        if not hasattr(self, "_telem_lbl_speed"):
            return
        try:
            p  = getattr(self, "_last_packet", None)
            tr = self._tracker

            # Connection group — connection-signal sprint (2026-07-04): the
            # UDPListener owns the real stats (connected / total_received /
            # parse_errors / packet_rate). The old tracker attrs (_connected /
            # _packet_count / _error_count / _packet_rate_hz) never existed, so
            # this panel was frozen at "Disconnected / 0 / — Hz"; the tracker
            # getattr fallbacks preserve that exact behaviour when no listener
            # is wired (tests / legacy constructions).
            _lsn = getattr(self, "_udp_listener", None)
            if _lsn is not None:
                connected = bool(getattr(_lsn, "connected", False))
                pkt_count = getattr(_lsn, "total_received", 0)
                pkt_err   = getattr(_lsn, "parse_errors", 0)
                pkt_rate  = getattr(_lsn, "packet_rate", 0.0)
            else:
                connected = tr is not None and getattr(tr, "_connected", False)
                pkt_count = getattr(tr, "_packet_count", 0) if tr else 0
                pkt_err   = getattr(tr, "_error_count", 0) if tr else 0
                pkt_rate  = getattr(tr, "_packet_rate_hz", 0.0) if tr else 0.0
            self._telem_lbl_connection.setText("Connected" if connected else "Disconnected")
            self._telem_lbl_connection.setStyleSheet(
                "color: #AAE4AA; font-size: 11px;" if connected else "color: #FF6B6B; font-size: 11px;")
            self._telem_lbl_pkt_total_t.setText(str(pkt_count))
            self._telem_lbl_pkt_errors_t.setText(str(pkt_err))
            self._telem_lbl_pkt_rate_t.setText(f"{pkt_rate:.1f} Hz" if pkt_rate else "— Hz")
            udp_active = connected or pkt_count > 0
            self._telem_lbl_udp_status.setText("Listening" if udp_active else "Not started")

            import datetime as _dt
            if p is not None:
                self._telem_lbl_last_pkt.setText(_dt.datetime.now().strftime("%H:%M:%S"))

            # Session group
            sid = getattr(self, "_active_session_id", None)
            self._telem_lbl_recording.setText("Yes" if sid is not None else "No")
            phase = getattr(tr, "_phase", None) if tr else None
            self._telem_lbl_session_mode.setText(
                phase.value if phase is not None else "—")

            # Active setup label (last saved setup for this car)
            _setups = self._config.get("car_setup", {}).get("setups", [])
            _car_now = self._config.get("strategy", {}).get("car", "")
            _matching = [s for s in _setups if
                         s.get("car", "") == _car_now or s.get("name", "") == _car_now]
            from ui.setup_name_helper import setup_display_label
            self._telem_lbl_setup.setText(
                (setup_display_label(_matching[-1]) or "Unknown") if _matching else "—"
            )

            if p is None:
                return

            # Live packet group
            self._telem_lbl_speed.setText(f"{p.speed_kmh:.1f} km/h")
            gear = p.current_gear
            self._telem_lbl_gear.setText(str(gear) if gear > 0 else "N")
            self._telem_lbl_rpm_t.setText(f"{p.engine_rpm:,.0f} rpm")
            self._telem_lbl_throttle_t.setText(f"{p.throttle_raw} ({p.throttle * 100:.0f}%)")
            self._telem_lbl_brake_t.setText(f"{p.brake_raw} ({p.brake * 100:.0f}%)")
            self._telem_lbl_fuel_t.setText(f"{p.fuel_level:.2f} L")
            self._telem_lbl_xyz.setText(f"X:{p.pos_x:.1f}  Y:{p.pos_y:.1f}  Z:{p.pos_z:.1f}")
            self._telem_lbl_road.setText(f"{p.road_plane_y:.3f}")
            self._telem_lbl_temps.setText(
                f"FL:{p.tyre_temp_fl:.0f}°  FR:{p.tyre_temp_fr:.0f}°  "
                f"RL:{p.tyre_temp_rl:.0f}°  RR:{p.tyre_temp_rr:.0f}°"
            )
            r = p.tyre_radius
            self._telem_lbl_radius.setText(
                f"FL:{r[0]:.4f}  FR:{r[1]:.4f}  RL:{r[2]:.4f}  RR:{r[3]:.4f}"
            )
            recorded = tr.laps_recorded if tr is not None else 0
            self._telem_lbl_lap_num.setText(f"Lap {recorded + 1}")
            self._telem_lbl_last_lap_t.setText(
                format_laptime_display(p.last_lap_ms) if p.last_lap_ms > 0 else "—")
            self._telem_lbl_best_lap_t.setText(
                format_laptime_display(p.best_lap_ms) if p.best_lap_ms > 0 else "—")

            # Fuel burn average
            avg_fuel = getattr(tr, "avg_fuel_per_lap", 0) if tr else 0
            self._telem_lbl_fuel_burn_t.setText(
                f"{avg_fuel:.2f} L/lap" if avg_fuel > 0 else "— (no data)")

            # Max speed from tracker
            ms_kmh = getattr(tr, "max_speed_kmh", 0.0) if tr else 0.0
            self._telem_lbl_max_speed.setText(f"{ms_kmh:.1f} km/h" if ms_kmh > 0 else "—")

            # Last completed lap events from recorder
            _rec = getattr(self, "_recorder", None)
            last_stats = _rec.last_lap() if _rec is not None else None
            if last_stats is not None:
                self._telem_lbl_lockups.setText(str(last_stats.lock_up_count))
                self._telem_lbl_wheelspin.setText(str(last_stats.wheelspin_count))
                self._telem_lbl_oversteer.setText(str(last_stats.oversteer_count))
                self._telem_lbl_revlim.setText(str(last_stats.rev_limiter_count))
                self._telem_lbl_kerbs.setText(str(last_stats.kerb_count))
                self._telem_lbl_bottom.setText(str(last_stats.bottoming_count))

        except Exception:
            logging.warning("telemetry label update failed", exc_info=True)

    # --- Per-tab guidance header (post-UAT clarity overhaul) ----------------

    def _tab_intro_header(self, title: str, subtitle: str) -> QWidget:
        """A consistent 'what this tab is for + your next step' band for the top
        of a tab. Part of the clarity overhaul so every tab explains itself and
        points at the next action, instead of relying on a separate Guide tab."""
        band = QWidget()
        band.setStyleSheet(
            f"background: {_DARK_CARD}; border-left: 4px solid #2EA043;"
            " border-radius: 6px;")
        # Hug the content — never let a parent layout stretch the band tall.
        band.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        lay = QVBoxLayout(band)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(
            f"color: {_TEXT}; font-size: 13px; font-weight: bold; background: transparent;")
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet("color: #9FB0A6; font-size: 11px; background: transparent;")
        lay.addWidget(t)
        lay.addWidget(s)
        return band

    # --- User Guide (folded into Home) --------------------------------------

    def _build_guide_reference_widget(self) -> QWidget:
        """Collapsible User Guide + reference section, embedded at the bottom of
        the Home tab. The standalone Guide tab was removed — help now lives on
        Home, where the workflow starts, instead of a separate tab. Starts
        collapsed so it never crowds the status cards."""
        box = QGroupBox("\U0001F4D6  User Guide & Reference  —  click to expand")
        box.setCheckable(True)
        box.setChecked(False)
        try:
            box.setStyleSheet(self._group_style())
        except Exception:
            pass
        lay = QVBoxLayout(box)
        lay.setContentsMargins(6, 6, 6, 6)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setMinimumHeight(420)
        txt.setStyleSheet(
            f"QTextEdit {{ background: {_DARK_BG}; color: {_TEXT}; "
            f"border: none; padding: 12px; font-size: 12px; }}"
        )
        txt.setHtml(_GUIDE_HTML)
        txt.setVisible(False)
        lay.addWidget(txt)
        box.toggled.connect(txt.setVisible)
        return box

    # --- Debug tab ----------------------------------------------------------

    def _build_debug_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(3)

        def _sl(text: str = "—") -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {_TEXT};")
            lbl.setMinimumWidth(130)
            return lbl

        # ── Row 1: connection ────────────────────────────────────────────
        r1 = QHBoxLayout(); r1.setSpacing(16)
        self._lbl_pkt_rate   = _sl("Rate: — Hz")
        self._lbl_pkt_total  = _sl("Pkts: 0")
        self._lbl_pkt_errors = _sl("Errors: 0")
        for lbl in (self._lbl_pkt_rate, self._lbl_pkt_total, self._lbl_pkt_errors):
            r1.addWidget(lbl)
        r1.addStretch()
        root.addLayout(r1)

        # ── Row 2: tracker state ─────────────────────────────────────────
        r2 = QHBoxLayout(); r2.setSpacing(16)
        self._lbl_dbg_phase     = _sl("Phase: —")
        self._lbl_dbg_race_type = _sl("RaceType: —")
        self._lbl_dbg_session   = _sl("Session: —")
        self._lbl_dbg_laps      = _sl("Laps: —/—")
        self._lbl_dbg_rem_comp  = _sl("Time left: —")
        for lbl in (self._lbl_dbg_phase, self._lbl_dbg_race_type,
                    self._lbl_dbg_session, self._lbl_dbg_laps,
                    self._lbl_dbg_rem_comp):
            r2.addWidget(lbl)
        r2.addStretch()
        root.addLayout(r2)

        # ── Row 3: raw packet fields ─────────────────────────────────────
        r3 = QHBoxLayout(); r3.setSpacing(16)
        self._lbl_dbg_cars_raw = _sl("cars_in_race: —")
        self._lbl_dbg_laps_raw = _sl("laps_in_race: —")
        self._lbl_dbg_rem_raw  = _sl("remaining_time_ms: —")
        self._lbl_dbg_ontrack  = _sl("on_track: —")
        self._lbl_dbg_loading  = _sl("loading: —")
        self._lbl_dbg_pos_raw  = _sl("pos: —")
        for lbl in (self._lbl_dbg_cars_raw, self._lbl_dbg_laps_raw,
                    self._lbl_dbg_rem_raw, self._lbl_dbg_ontrack,
                    self._lbl_dbg_loading, self._lbl_dbg_pos_raw):
            r3.addWidget(lbl)
        r3.addStretch()
        root.addLayout(r3)

        # ── Row 4: announcer state ───────────────────────────────────────
        r4 = QHBoxLayout(); r4.setSpacing(16)
        self._lbl_dbg_ann_q    = _sl("Voice queue: —")
        self._lbl_dbg_ann_mute = _sl("Muted: No")
        for lbl in (self._lbl_dbg_ann_q, self._lbl_dbg_ann_mute):
            r4.addWidget(lbl)
        r4.addStretch()
        root.addLayout(r4)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        root.addWidget(sep)

        # ── Gearbox Analysis ─────────────────────────────────────────────
        gbx_hdr = QHBoxLayout()
        gbx_hdr.addWidget(QLabel("Gearbox Analysis (last lap):", styleSheet=f"color:{_TEXT}; font-weight: bold;"))
        btn_gbx_refresh = QPushButton("Refresh")
        btn_gbx_refresh.setFixedWidth(65)
        gbx_hdr.addWidget(btn_gbx_refresh)
        gbx_hdr.addStretch()
        root.addLayout(gbx_hdr)

        self._txt_gearbox_debug = QTextEdit()
        self._txt_gearbox_debug.setReadOnly(True)
        self._txt_gearbox_debug.setFont(QFont("Courier New", 9))
        self._txt_gearbox_debug.setStyleSheet(f"background: {_DARK_CARD}; color: {_TEXT};")
        self._txt_gearbox_debug.setFixedHeight(160)
        self._txt_gearbox_debug.setPlainText("No lap data — drive a lap to see gearbox analysis.")
        root.addWidget(self._txt_gearbox_debug)

        def _refresh_gearbox_debug() -> None:
            _rec = getattr(self, "_recorder", None)
            _lap = _rec.last_lap() if _rec else None
            if not _lap or not _lap.gearbox_analysis:
                self._txt_gearbox_debug.setPlainText("No gearbox data recorded yet.")
                return
            from strategy.gearbox_format import format_gearbox_summary
            self._txt_gearbox_debug.setPlainText(format_gearbox_summary(_lap.gearbox_analysis))

        btn_gbx_refresh.clicked.connect(_refresh_gearbox_debug)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #444;")
        root.addWidget(sep2)

        # ── Event log ────────────────────────────────────────────────────
        log_hdr = QHBoxLayout()
        log_hdr.addWidget(QLabel("Event log:", styleSheet=f"color:{_TEXT};"))
        btn_clear = QPushButton("Clear")
        btn_clear.setFixedWidth(55)
        btn_clear.clicked.connect(lambda: self._txt_log.clear())
        log_hdr.addWidget(btn_clear)
        log_hdr.addStretch()
        root.addLayout(log_hdr)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setFont(QFont("Courier New", 10))
        self._txt_log.setStyleSheet(f"background: {_DARK_CARD}; color: {_TEXT};")
        root.addWidget(self._txt_log)

        return w

    # ------------------------------------------------------------------ slots

    def _poll_ui_queue(self) -> None:
        for _ in range(5):
            try:
                packet: GT7Packet = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            self._last_packet = packet
            self._last_packet_received = time.time()  # Group 24 AC4
            # Group 61: read-only raw road-distance capture (inert unless started).
            if self._raw_rd_capture is not None:
                try:
                    _ln = self._tracker.laps_recorded if self._tracker is not None else None
                    self._raw_rd_capture.add_packet(packet, lap_number=_ln)
                except Exception:
                    pass
            # UAT #6 Phase 1b/2D: feed the live path capture when active (inert
            # otherwise); flag pit laps so the pit-lane corridor can be refined.
            if self._track_path_capture is not None:
                try:
                    _tln = self._tracker.laps_recorded if self._tracker is not None else 0
                    _inpit = bool(getattr(self._tracker, "in_pit", False)) if self._tracker is not None else False
                    self._track_path_capture.add_packet(packet, lap_number=_tln, in_pit=_inpit)
                except Exception:
                    pass
            # Live per-corner telemetry aggregation (inert until a track is active).
            if self._live_corner_tel is not None:
                try:
                    self._live_corner_tel.add_packet(packet)
                except Exception:
                    pass
            self._update_live(packet)
        # UAT #6 Phase 2A: throttled auto-start of refinement capture while driving
        # a track that already has an accepted model (inert when disabled/no model).
        try:
            _now = time.time()
            if _now - self._last_refine_autostart_check > 3.0:
                self._last_refine_autostart_check = _now
                self._maybe_autostart_refine_capture()
                self._maybe_init_live_corner_tel()
        except Exception:
            pass
        self._refresh_strategy_fuel_column()
        self._refresh_gear_ratios()
        self._update_telemetry_labels()
        for _q, _handler in [
            (self._strategy_result_queue,    self._display_strategy_results),
            (self._setup_result_queue,       self._display_setup_result),
            (self._practice_result_queue,    self._display_practice_results),
            (self._build_setup_queue,        self._display_build_setup_result),
            (self._baseline_result_queue,    self._display_baseline_result),
            (self._degradation_result_queue, self._display_degradation_result),
            (self._profile_update_queue,     self._display_profile_update_result),
        ]:
            try:
                _handler(_q.get_nowait())
            except queue.Empty:
                pass



    def on_lap_completed(self, record: LapRecord) -> None:
        self._add_lap_row(record)
        count = self._logger.lap_count()
        self._lbl_lap_count.setText(f"{count} lap{'s' if count != 1 else ''} recorded")

        if not hasattr(self, "_combo_live_mode"):
            return
        mode = self._combo_live_mode.currentText()
        if mode == "Practice":
            self._update_practice_stats(record)
            self._capture_practice_lap(record)
        elif mode == "Qualifying" and record.lap_time_ms > 0:
            if hasattr(self, "_spin_qual_min"):
                target_ms = int(self._spin_qual_min.value() * 60_000
                                + self._spin_qual_sec.value() * 1_000)
            else:
                target_ms = 0
            if target_ms > 0:
                delta = record.lap_time_ms - target_ms
                label = "vs tgt"
            else:
                best_ms = self._logger.best_lap_ms()
                delta = record.lap_time_ms - best_ms if best_ms > 0 else 0
                label = "vs best"
            sign = "+" if delta > 0 else ""
            col = "#E8771A" if delta > 0 else _ACCENT
            self._lbl_qual_last.setText(
                f"{format_laptime_display(record.lap_time_ms)} "
                f"({sign}{delta / 1000:.3f}s {label})")
            self._lbl_qual_last.setStyleSheet(f"color:{col};")

    def _qual_sync_target_to_announcer(self) -> None:
        ms = self._spin_qual_min.value() * 60000 + round(self._spin_qual_sec.value() * 1000)
        if hasattr(self, "_announcer") and self._announcer:
            self._announcer.set_qualifying_target_ms(ms)

    def _qual_use_practice_lap(self) -> None:
        evt = self._active_event() if hasattr(self, "_active_event") else {}
        car_name = self._config.get("strategy", {}).get("car", "")
        car_id = self._db.get_car_id(car_name) if self._db and car_name else 0
        track = evt.get("track", "") if evt else ""
        if not car_id or not track:
            self._lbl_qual_practice_status.setText("No active car or track set.")
            return
        best = self._db.get_best_practice_lap_ms(car_id, track)
        if best is None or best <= 0:
            self._lbl_qual_practice_status.setText("No practice laps recorded for this car and track.")
            return
        mins = best // 60000
        secs = (best % 60000) / 1000.0
        self._spin_qual_min.setValue(mins)
        self._spin_qual_sec.setValue(secs)
        from data.session_db import ms_to_str
        self._lbl_qual_practice_status.setText(f"Target set from practice: {ms_to_str(best)}")

    def _auto_refresh_gearbox_debug(self) -> None:
        if not hasattr(self, "_txt_gearbox_debug"):
            return
        _rec = getattr(self, "_recorder", None)
        _lap = _rec.last_lap() if _rec else None
        if not _lap or not _lap.gearbox_analysis:
            return
        from strategy.gearbox_format import format_gearbox_summary
        self._txt_gearbox_debug.setPlainText(format_gearbox_summary(_lap.gearbox_analysis))

    def _update_practice_stats(self, record: LapRecord) -> None:
        if not hasattr(self, "_lbl_prac_gap"):
            return
        recs = self._logger.records()
        valid = [r.lap_time_ms for r in recs if r.lap_time_ms > 0 and not r.is_pit_lap]
        if not valid:
            return

        best_ms = min(valid)
        last_ms = valid[-1]

        gap = last_ms - best_ms
        sign = "+" if gap > 0 else ""
        gap_col = "#E8771A" if gap > 500 else _ACCENT
        self._lbl_prac_gap.setText(f"{sign}{gap / 1000:.3f}s")
        self._lbl_prac_gap.setStyleSheet(f"color:{gap_col};")

        last5 = valid[-5:]
        std_ms = 0.0
        if len(last5) >= 2:
            avg5 = sum(last5) / len(last5)
            std_ms = (sum((t - avg5) ** 2 for t in last5) / len(last5)) ** 0.5
            std_col = _ACCENT if std_ms < 800 else ("#F5C542" if std_ms < 1500 else "#E8771A")
            self._lbl_prac_consist.setText(f"±{std_ms / 1000:.3f}s")
            self._lbl_prac_consist.setStyleSheet(f"color:{std_col};")

        if len(last5) >= 3:
            if last5[-1] < last5[0]:
                trend, trend_col = "Improving", _ACCENT
            elif last5[-1] > last5[0] + 500:
                trend, trend_col = "Slower", "#E8771A"
            else:
                trend, trend_col = "Consistent", _TEXT
            self._lbl_prac_trend.setText(trend)
            self._lbl_prac_trend.setStyleSheet(f"color:{trend_col};")

        html = self._generate_practice_advice_html(valid, std_ms)
        self._txt_practice_advice.setHtml(html)

    def _generate_practice_advice_html(self, valid_laps: list, std_ms: float) -> str:
        from data.practice_analysis import compute_practice_tips
        tips = compute_practice_tips(
            valid_laps,
            std_ms,
            self._last_packet,
            getattr(self._tracker, "_thresholds", None) if self._tracker is not None else None,
            self._driving_advisor._recorder.last_lap()
            if (hasattr(self, "_driving_advisor") and self._driving_advisor is not None
                and getattr(self._driving_advisor, "_recorder", None) is not None)
            else None,
        )

        tip_list: list[str] = []
        if tips.consistency_tip:
            tip_list.append(tips.consistency_tip)
        if tips.gap_tip:
            tip_list.append(tips.gap_tip)
        if tips.trend_tip:
            tip_list.append(tips.trend_tip)
        tip_list.extend(tips.tyre_tips)
        if tips.telemetry_tip:
            # telemetry_tip is already <br>-joined internally; split back to
            # individual items so they join uniformly with the rest.
            for part in tips.telemetry_tip.split("<br>"):
                if part:
                    tip_list.append(part)

        style = ("font-family:'Segoe UI'; font-size:11px; line-height:1.6; "
                 f"color:{_TEXT}; background:transparent;")
        inner = "<br>".join(tip_list) if tip_list else "Complete more laps to build advice."
        return f"<div style='{style}'>{inner}</div>"

    def on_connection_status(self, connected: bool, hz: float) -> None:
        # Group 24 AC4: suppress spurious disconnect if a packet arrived recently
        if not connected:
            last = getattr(self, "_last_packet_received", 0.0)
            if time.time() - last < 3.0:
                return  # recent packet — suppress spurious disconnect
        if connected:
            self._status_bar.set_connected(hz)
        else:
            self._status_bar.set_disconnected()

    def on_race_state(self, text: str) -> None:
        self._status_bar.set_race_state(text)

    def on_event_log(self, text: str) -> None:
        self._txt_log.append(text)
        sb = self._txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------------ helpers

    def _add_lap_row(self, r: LapRecord) -> None:
        self._loaded_session_avg_fuel = 0.0  # live lap → stop using historical avg
        self._lap_table.blockSignals(True)
        try:
            row = self._lap_table.rowCount()
            self._lap_table.insertRow(row)
            avg_fuel = getattr(self._tracker, "avg_fuel_per_lap", 0.0) if self._tracker else 0.0

            session_label_base = r.session_type.value.capitalize() if r.session_type else "Practice"
            session_label = (session_label_base + " (OL)") if r.is_out_lap else session_label_base

            cells = [
                str(r.lap_num),
                session_label,
                format_laptime_display(r.lap_time_ms),
                str(r.lap_time_ms),
                f"{r.delta_ms / 1000:+.3f}" if r.best_lap_ms > 0 else "—",
                format_laptime_display(r.best_lap_ms),
                f"{r.fuel_start:.2f}",
                f"{r.fuel_end:.2f}",
                f"{r.fuel_used:.2f}",
                f"{avg_fuel:.2f}",
                str(r.position) if r.position > 0 else "—",
                "Yes" if r.is_pit_lap else "",
                r.timestamp,
            ]

            _SESSION_COLOURS = {
                "Race":       "#003A20",
                "Qualifying": "#1A1A4A",
            }

            _read_only_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(_read_only_flags)
                if r.is_out_lap:
                    item.setBackground(QColor("#003A1A"))
                elif r.is_pit_lap:
                    item.setBackground(QColor("#4A4000"))
                elif session_label_base in _SESSION_COLOURS:
                    item.setBackground(QColor(_SESSION_COLOURS[session_label_base]))
                self._lap_table.setItem(row, col, item)
            # Store row-type flags in col 0 UserRole for _refresh_practice_summary() filtering
            col0 = self._lap_table.item(row, 0)
            if col0:
                col0.setData(Qt.ItemDataRole.UserRole,
                             {"is_out_lap": r.is_out_lap, "is_pit_lap": r.is_pit_lap})

            # Compound column (13) — dropdown combo; inherit from previous lap if untagged
            _cpd_default = (
                self._lap_compound_tags.get(r.lap_num) or
                self._lap_compound_tags.get(r.lap_num - 1, self._default_lap_compound)
            )
            combo = self._make_compound_combo(row, _cpd_default)
            if r.lap_num not in self._lap_compound_tags and self._default_lap_compound:
                self._lap_compound_tags[r.lap_num] = self._default_lap_compound
                self._persist_compound_tag(r.lap_num, self._default_lap_compound)
            self._lap_table.setCellWidget(row, 13, combo)

            # Setup column (14) — auto-tag then dropdown override
            auto_id = self._resolve_setup_id_for_lap()
            setup_combo = self._make_setup_combo(row, auto_id)
            self._lap_table.setCellWidget(row, 14, setup_combo)
            if auto_id:
                self._persist_setup_tag(r.lap_num, auto_id)
        finally:
            self._lap_table.blockSignals(False)

        self._lap_table.scrollToBottom()
        self._refresh_practice_summary()

    from data.tyres import compound_codes as _cc
    _COMPOUND_OPTIONS = [""] + _cc()
    from data.tyres import ALL_COMPOUNDS as _ALL_CPDS_CLS
    _TYRE_NAME_TO_CODE: dict = {c.name: c.code for c in _ALL_CPDS_CLS}

    def _make_compound_combo(self, row: int, current: str = "") -> "QComboBox":
        from PyQt6.QtWidgets import QComboBox as _QCB
        combo = _QCB()
        combo.addItems(self._COMPOUND_OPTIONS)
        combo.setStyleSheet(
            "QComboBox { background: #1E1E1E; color: #E0E0E0; border: 1px solid #555; "
            "padding: 1px 4px; } "
            "QComboBox::drop-down { border: none; } "
            "QComboBox QAbstractItemView { background: #2A2A2A; color: #E0E0E0; "
            "selection-background-color: #1F4E78; }"
        )
        idx = combo.findText(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentTextChanged.connect(lambda text, r=row: self._on_compound_selected(r, text))
        return combo

    def _on_compound_selected(self, start_row: int, compound: str) -> None:
        """Fill start_row and all rows below it with compound, stopping before
        the next row that already has a different (non-empty) compound set."""
        norm = compound.strip()

        # Push active compound to tracker so next lap save picks it up (P5-C)
        if norm:
            self._default_lap_compound = norm
            if self._tracker is not None:
                self._tracker.set_compound(norm)

        # Update tag dict for this row and persist to DB
        lap_item = self._lap_table.item(start_row, 0)
        if lap_item:
            try:
                lap_num = int(lap_item.text())
                self._lap_compound_tags[lap_num] = norm
                self._persist_compound_tag(lap_num, norm)
            except ValueError:
                pass

        # Fill downward — stop at the next pit lap (where the compound changed at a stop)
        total = self._lap_table.rowCount()
        for row in range(start_row + 1, total):
            li0 = self._lap_table.item(row, 0)
            row_flags = (li0.data(Qt.ItemDataRole.UserRole) or {}) if li0 else {}
            if row_flags.get("is_pit_lap", False):
                break  # next pit stop boundary — don't propagate past it
            combo = self._lap_table.cellWidget(row, 13)
            if combo is not None:
                combo.blockSignals(True)
                idx = combo.findText(norm)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
                combo.blockSignals(False)
            # Keep tag dict and DB in sync
            li = self._lap_table.item(row, 0)
            if li:
                try:
                    lap_num = int(li.text())
                    self._lap_compound_tags[lap_num] = norm
                    self._persist_compound_tag(lap_num, norm)
                except ValueError:
                    pass

    def _persist_compound_tag(self, lap_num: int, compound: str) -> None:
        """Write compound tag to the database for the current active session."""
        try:
            if self._db is not None and self._dispatcher is not None:
                sid = self._dispatcher._session_id
                if sid > 0:
                    self._db.update_lap_compound(sid, lap_num, compound)
        except Exception:
            pass

    def _compound_at_row(self, row: int) -> str:
        """Return the normalised compound string for the given table row, or ''."""
        combo = self._lap_table.cellWidget(row, 13)
        if combo is None:
            return ""
        return combo.currentText().strip()

    def _read_ui_lap_table(self) -> dict[str, list[float]]:
        """Extract compound-tagged lap times from the UI lap table.

        Returns {compound: [lap_time_ms, ...]} for all rows where compound
        is non-blank and lap_time_ms > 0. Used as fallback data for strategy
        analysis when DB has no laps for a compound.
        """
        result: dict[str, list[float]] = {}
        for row in range(self._lap_table.rowCount()):
            compound = self._compound_at_row(row)
            if not compound:
                continue
            item = self._lap_table.item(row, 3)
            if item is None:
                continue
            try:
                lt_ms = float(item.text())
            except (ValueError, AttributeError):
                continue
            if lt_ms > 0:
                result.setdefault(compound, []).append(lt_ms)
        return result

    # ------------------------------------------------------------------
    # Setup ID tracking
    # ------------------------------------------------------------------

    def _migrate_setup_ids(self) -> None:
        """Assign incrementing setup_ids to any saved setups that don't have one."""
        ca = self._config.setdefault("car_setup", {})
        next_id = ca.get("next_setup_id", 1)
        changed = False
        for s in ca.get("setups", []):
            if not s.get("setup_id"):
                s["setup_id"] = next_id
                next_id += 1
                changed = True
        if changed:
            ca["next_setup_id"] = next_id
            self._persist_config()

    def _migrate_setups_to_db(self) -> None:
        """One-time migration: write config setups into the DB setups table."""
        if self._db is None or not self._saved_setups:
            return
        event_name = self._config.get("active_event_id", "")
        event_id = self._db.get_event_id(event_name) if event_name else 0
        _meta_keys = {"name", "setup_label", "setup_id", "captured_at", "ai_notes"}
        changed = False
        from ui.setup_name_helper import setup_display_label
        for s in self._saved_setups:
            car_name = s.get("name", "")
            car_id = self._db.get_car_id(car_name) if car_name else 0
            label = setup_display_label(s) or "Setup"
            setup_fields = {k: v for k, v in s.items() if k not in _meta_keys}
            db_id = self._db.save_setup(car_id, event_id, label, setup_fields,
                                        ai_notes=s.get("ai_notes", ""))
            s["setup_id"] = db_id
            changed = True
        if changed:
            ca = self._config.setdefault("car_setup", {})
            ca["setups"] = self._saved_setups
            self._persist_config()

    def _resolve_setup_id_for_lap(self) -> int:
        """Return the setup_id of the most recently saved setup for the current
        car whose captured_at is <= now.  Returns 0 if nothing matches."""
        from datetime import datetime
        car = self._config.get("strategy", {}).get("car", "")
        now = datetime.now()
        best_id, best_dt = 0, None
        for s in self._saved_setups:
            if car and s.get("name", "") != car:
                continue
            raw = s.get("captured_at", "")
            try:
                dt = datetime.strptime(raw, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if dt <= now and (best_dt is None or dt > best_dt):
                best_dt = dt
                best_id = s.get("setup_id", 0)
        return best_id

    def _setup_id_options(self) -> list[str]:
        from ui.setup_name_helper import setup_display_label
        seen: dict[int, str] = {}
        for s in self._saved_setups:
            sid = s.get("setup_id")
            if sid:
                seen[sid] = setup_display_label(s) or s.get("name", "")
        return [""] + [f"{sid} — {name}" for sid, name in sorted(seen.items())]

    def _make_setup_combo(self, row: int, current_id: int = 0) -> "QComboBox":
        from PyQt6.QtWidgets import QComboBox as _QCB
        combo = _QCB()
        combo.addItems(self._setup_id_options())
        combo.setStyleSheet(
            "QComboBox { background: #1E1E1E; color: #E0E0E0; border: 1px solid #555; "
            "padding: 1px 4px; } "
            "QComboBox::drop-down { border: none; } "
            "QComboBox QAbstractItemView { background: #2A2A2A; color: #E0E0E0; "
            "selection-background-color: #1F4E78; }"
        )
        if current_id:
            target = str(current_id)
            for i in range(combo.count()):
                if combo.itemText(i).startswith(target + " —"):
                    combo.setCurrentIndex(i)
                    break
        combo.currentTextChanged.connect(lambda text, r=row: self._on_setup_id_selected(r, text))
        return combo

    def _on_setup_id_selected(self, row: int, text: str) -> None:
        try:
            setup_id = int(text.split(" —")[0]) if text else 0
        except ValueError:
            setup_id = 0
        lap_item = self._lap_table.item(row, 0)
        if not lap_item:
            return
        try:
            lap_num = int(lap_item.text())
        except ValueError:
            return
        self._persist_setup_tag(lap_num, setup_id)

    def _persist_setup_tag(self, lap_num: int, setup_id: int) -> None:
        try:
            if self._db is not None and self._dispatcher is not None:
                sid = self._dispatcher._session_id
                if sid > 0:
                    self._db.update_lap_setup_id(sid, lap_num, setup_id)
        except Exception:
            pass

    def _refresh_all_setup_combos(self) -> None:
        options = self._setup_id_options()
        for row in range(self._lap_table.rowCount()):
            combo = self._lap_table.cellWidget(row, 14)
            if combo is None:
                continue
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(options)
            for i in range(combo.count()):
                if combo.itemText(i) == current:
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)

    def _build_setup_comparison_text(self, track: str) -> str:
        try:
            import os
            from data.session_db import SessionDB as _SDB
            if not os.path.exists("data/gt7_sessions.db"):
                return ""
            db = _SDB("data/gt7_sessions.db")
            # Resolve the REAL car_id — the old code passed 0, which matched no
            # rows, so setup-history comparison was always empty.
            car_name = ""
            try:
                car_name = str(getattr(self._build_event_context(), "car", "") or "")
            except Exception:
                car_name = ""
            car_id = int(db.get_car_id(car_name)) if car_name else self._current_car_id()
            rows = db.get_setup_comparison(car_id, track)
            db.close()
            if not rows:
                return ""
            from ui.setup_name_helper import setup_display_label
            id_to_name: dict[int, str] = {
                s["setup_id"]: setup_display_label(s) or f"Setup {s['setup_id']}"
                for s in self._saved_setups if s.get("setup_id")
            }
            lines = ["## Setup comparison (session history)"]
            by_setup: dict = {}
            for r in rows:
                by_setup.setdefault(r["setup_id"], []).append(r)
            for sid, cpds in sorted(by_setup.items()):
                lines.append(f"\nSetup #{sid} — {id_to_name.get(sid, 'Unknown')}")
                for c in sorted(cpds, key=lambda x: x["compound"]):
                    lines.append(
                        f"  {c['compound']}: {c['laps']} laps  "
                        f"avg {c['avg_ms']/1000:.3f}s  best {c['best_ms']/1000:.3f}s  "
                        f"fuel {c['avg_fuel']:.2f} L/lap  "
                        f"wheelspin {c['avg_wheelspin']:.1f}/lap  "
                        f"lockups {c['avg_lockup']:.1f}/lap"
                    )
            return "\n".join(lines)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Race config ID + Practice Lap Bank helpers
    # ------------------------------------------------------------------

    def _working_race_config(self):
        """Canonical read model of the race config being worked on.

        Working Race Config sprint (2026-07-04, retirement-map item 3 readers):
        names the concept Phase 6b identified — the working race identity that
        usually mirrors the active event but deliberately holds a restored
        historical session's config during a lap-bank restore (which is why the
        match-key hash could not move to DB-first EventContext). The single
        bridge read of the legacy dict for this concept; consumers read the
        model. Never raises.
        """
        from data.working_race_config import WorkingRaceConfig
        return WorkingRaceConfig.from_strategy(self._config.get("strategy", {}))

    def _compute_race_config_id(self) -> str:
        """Derive the 10-char session match key from the working race config.

        The ALGORITHM lives in WorkingRaceConfig.compute_config_id() and is
        frozen by golden vectors (tests/test_race_config_id_hash.py) — same
        inputs always give the same ID; it is stored in config so live sessions
        are tagged with it.
        """
        return self._working_race_config().compute_config_id()

    def _computed_fuel_burn_lpl(self) -> float:
        # SessionContext sprint: the 3-tier fuel-burn fallback (loaded historical
        # session average → live telemetry average → config fallback 2.0) is now
        # owned by SessionContext. Byte-identical to the previous inline logic
        # (proven in tests/test_session_context.py); the config["strategy"] fuel
        # read moves into the context builder (the single legacy bridge).
        return self._build_session_context().fuel_burn_per_lap

    def _save_race_params(self) -> None:
        """Persist editable race analysis parameters (pit loss, tolerances) to config."""
        sc = self._config.setdefault("strategy", {})
        sc["fuel_burn_per_lap"] = self._computed_fuel_burn_lpl()
        if hasattr(self, "_ai_pit_loss"):
            sc["pit_loss_secs"]         = self._ai_pit_loss.value()
        if hasattr(self, "_ai_lap_tolerance"):
            sc["lap_time_tolerance_ms"] = int(self._ai_lap_tolerance.value() * 1000)
        if hasattr(self, "_ai_fuel_tolerance"):
            sc["fuel_tolerance_liters"] = self._ai_fuel_tolerance.value()
        self._persist_config()

    def _update_race_config(self) -> None:
        """Recompute the race config ID, update the label, persist to config, refresh lap bank."""
        if not hasattr(self, "_lbl_config_id"):
            return
        # Working Race Config sprint: label + snapshot values come from the
        # canonical WorkingRaceConfig read model (same bridge source, verbatim
        # semantics incl. the 25/60 defaults — byte-identical).
        wrc       = self._working_race_config()
        config_id = wrc.compute_config_id()
        track     = wrc.track
        car       = wrc.car
        race_type = wrc.race_type
        race_duration = wrc.race_duration_minutes
        total_laps    = wrc.total_laps
        length_str = wrc.length_text()
        parts = [p for p in [track, car, length_str] if p]
        detail = "  ·  " + " / ".join(parts) if parts else ""
        self._lbl_config_id.setText(f"{config_id}{detail}")

        wsc = self._config.setdefault("strategy", {})
        wsc["config_id"] = config_id

        # Snapshot full race params keyed by config_id so we can restore later
        if config_id and track and car:
            rc_snap = self._config.setdefault("race_configs", {})
            rc_snap[config_id] = {
                "car":                   car,
                "track":                 track,
                "race_type":             race_type,
                "total_laps":            total_laps,
                "race_duration_minutes": race_duration,
            }

        self._persist_config()
        self._refresh_lap_bank()
        # Phase 6a: config_id (and possibly track/car upstream) changed — push
        # a fresh SessionTag to the telemetry dispatcher. Set-as-Active, garage
        # car select, and the session-config restore all funnel through here.
        self._push_session_tag()
        # Home Dashboard: strategy inputs changed — keep an open Home tab
        # current (display-only; no-op when Home is not visible).
        self._home_refresh_if_visible()

    def _get_mandatory_compounds(self) -> list[str]:
        """Return mandatory compound display names (upper-cased) for the active
        event.

        Legacy Fan-Out Removal Phase 4: reads the canonical
        ``EventContext.required_tyres`` (compound CODES, DB-event-first) and maps
        them to display names via ``data.tyres.get_by_code`` — the same mapping
        the fan-out writer used to build its ``mandatory_compounds`` string, so
        the result is byte-identical when the DB event and the fan-out are in
        sync. Display-only (feeds the strategy context label).
        """
        try:
            from data.tyres import get_by_code
            return [
                get_by_code(c).name.upper()
                for c in self._build_event_context().required_tyres
                if get_by_code(c)
            ]
        except Exception:
            return []

    def _refresh_lap_bank(self) -> None:
        """Populate Track/Car combos and session combo; update recording status label."""
        if not hasattr(self, "_lap_bank_combo"):
            return
        if self._db is None:
            self._lap_bank_combo.blockSignals(True)
            self._lap_bank_combo.clear()
            self._lap_bank_combo.addItem("— session database unavailable —", None)
            self._lap_bank_combo.blockSignals(False)
            return
        try:
            sessions = self._db.get_all_sessions(limit=60)
        except Exception:
            sessions = []

        today = __import__("datetime").date.today().isoformat()

        # Update recording status label first (uses unfiltered sessions)
        if hasattr(self, "_lbl_bank_recording"):
            if sessions:
                newest = sessions[0]
                newest_date = (newest.get("date_utc") or "")[:10]
                if newest_date == today:
                    car  = newest.get("car_name") or "?"
                    trk  = newest.get("track") or "?"
                    laps = newest.get("total_laps", 0)
                    self._lbl_bank_recording.setText(
                        f"Recording:  {car}  ·  {trk}  —  {laps} lap{'s' if laps != 1 else ''} saved"
                    )
                else:
                    self._lbl_bank_recording.setText("")
            else:
                self._lbl_bank_recording.setText("")

        # Refresh Track combo (preserve current selection)
        if hasattr(self, "_bank_track_combo"):
            tracks = ["All"] + sorted({
                s.get("track") or "Unknown" for s in sessions
                if s.get("track") and s["track"] not in ("Unknown track", "")
            })
            saved_track = self._bank_track_combo.currentText()
            self._bank_track_combo.blockSignals(True)
            self._bank_track_combo.clear()
            self._bank_track_combo.addItems(tracks)
            idx = self._bank_track_combo.findText(saved_track)
            self._bank_track_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._bank_track_combo.blockSignals(False)

        # Refresh Car combo filtered by selected track
        sel_track = ""
        if hasattr(self, "_bank_track_combo"):
            sel_track = self._bank_track_combo.currentText()
            if sel_track == "All":
                sel_track = ""
        filtered_by_track = [s for s in sessions if not sel_track or s.get("track") == sel_track]
        if hasattr(self, "_bank_car_combo"):
            cars = ["All"] + sorted({
                s.get("car_name") or "Unknown" for s in filtered_by_track
                if s.get("car_name") and s["car_name"] not in ("Unknown car", "")
            })
            saved_car = self._bank_car_combo.currentText()
            self._bank_car_combo.blockSignals(True)
            self._bank_car_combo.clear()
            self._bank_car_combo.addItems(cars)
            idx = self._bank_car_combo.findText(saved_car)
            self._bank_car_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._bank_car_combo.blockSignals(False)

        # Build final session list filtered by both track + car
        sel_car = ""
        if hasattr(self, "_bank_car_combo"):
            sel_car = self._bank_car_combo.currentText()
            if sel_car == "All":
                sel_car = ""
        filtered = [
            s for s in sessions
            if (not sel_track or s.get("track") == sel_track)
            and (not sel_car or s.get("car_name") == sel_car)
        ]

        # State Consolidation 2: the active config_id is strategy-plan state —
        # read it from the canonical StrategyContext, not raw config["strategy"].
        current_config_id = self._build_strategy_context().config_id
        current_id = self._lap_bank_combo.currentData()
        self._lap_bank_combo.blockSignals(True)
        self._lap_bank_combo.clear()

        # If neither filter is active, show a prompt rather than auto-selecting a session
        no_filter = not sel_track and not sel_car
        if no_filter:
            self._lap_bank_combo.addItem("— select Track and Car above to filter —", None)
        elif not filtered:
            self._lap_bank_combo.addItem("— no sessions match filter —", None)
        else:
            restore_idx = 0
            for i, s in enumerate(filtered):
                raw_dt   = s.get("date_utc") or ""
                date_str = raw_dt[:10]
                time_str = raw_dt[11:16]
                dt_label = f"{date_str} {time_str}" if time_str else date_str
                car_name = s.get("car_name") or "?"
                track    = s.get("track") or "?"
                total    = s.get("total_laps", 0)
                tagged   = s.get("tagged_laps", 0)
                marker   = " ★" if s.get("config_id") == current_config_id and current_config_id else ""
                label    = f"{dt_label}  ·  {car_name}  ·  {track}  —  {total} laps  ({tagged} tagged){marker}"
                self._lap_bank_combo.addItem(label, s["id"])
                if s["id"] == current_id:
                    restore_idx = i
            self._lap_bank_combo.setCurrentIndex(restore_idx)
        self._lap_bank_combo.blockSignals(False)

    def _on_bank_track_changed(self) -> None:
        """Track selection changed — refresh Car combo then session list."""
        if not hasattr(self, "_lap_bank_combo"):
            return
        # Rebuild car combo for the new track, then refresh session list
        self._refresh_lap_bank()

    def _add_bank_lap_row(
        self,
        lap_num: int,
        lap_time_ms: int,
        fuel_used: float,
        compound: str,
        best_ms: int,
        session_date: str,
        fuel_start: float = 0.0,
        fuel_end: float = 0.0,
        is_pit_lap: bool = False,
        is_out_lap: bool = False,
    ) -> None:
        """Insert a single historical lap row from the practice bank into _lap_table."""
        from PyQt6.QtGui import QColor as _QC
        self._lap_table.blockSignals(True)
        try:
            row = self._lap_table.rowCount()
            self._lap_table.insertRow(row)

            if best_ms > 0 and lap_time_ms > 0:
                delta_s = (lap_time_ms - best_ms) / 1000.0
                delta_str = f"{delta_s:+.3f}"
            else:
                delta_str = "—"

            session_label = "Practice (OL)" if is_out_lap else "Practice"
            cells = [
                str(lap_num),
                session_label,
                format_laptime_display(lap_time_ms),
                str(lap_time_ms),
                delta_str,
                format_laptime_display(best_ms) if best_ms > 0 else "—",
                f"{fuel_start:.2f}" if fuel_start > 0 else "—",
                f"{fuel_end:.2f}" if fuel_end > 0 else "—",
                f"{fuel_used:.2f}" if fuel_used > 0 else "—",
                "—",
                "—",
                "Yes" if is_pit_lap else "",
                session_date,
            ]
            # Background priority: outlap > pit lap > default
            if is_out_lap:
                _bg = _QC("#003A1A")
            elif is_pit_lap:
                _bg = _QC("#4A4000")
            else:
                _bg = _QC("#0D1F2D")
            _read_only = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(_read_only)
                item.setBackground(_bg)
                self._lap_table.setItem(row, col, item)
            # Store row-type flags in col 0 UserRole for _refresh_practice_summary() filtering
            col0 = self._lap_table.item(row, 0)
            if col0:
                col0.setData(Qt.ItemDataRole.UserRole,
                             {"is_out_lap": is_out_lap, "is_pit_lap": is_pit_lap})

            # Prefer the DB compound over stale _lap_compound_tags from a prior session.
            # Only fall through to inherited/default if DB supplied nothing.
            if compound:
                resolved = compound
            elif lap_num in self._lap_compound_tags:
                resolved = self._lap_compound_tags[lap_num]
            else:
                prior_keys = [k for k in self._lap_compound_tags if k < lap_num]
                resolved = (self._lap_compound_tags[max(prior_keys)]
                            if prior_keys else self._default_lap_compound)
            self._lap_compound_tags[lap_num] = resolved
            combo = self._make_compound_combo(row, resolved)
            self._lap_table.setCellWidget(row, 13, combo)
            # Setup column (14) — no auto-resolve for historical rows; leave empty
            setup_combo = self._make_setup_combo(row, 0)
            self._lap_table.setCellWidget(row, 14, setup_combo)
        finally:
            self._lap_table.blockSignals(False)
        self._lap_table.scrollToBottom()

    def _import_bank_session(self) -> None:
        """Load the selected past session's laps into _lap_table."""
        if self._db is None:
            return
        session_id = self._lap_bank_combo.currentData()
        if not session_id:
            return
        try:
            laps = self._db.get_session_laps(session_id)
        except Exception as exc:
            self._set_bank_status(f"Error loading session: {exc}")
            return
        if not laps:
            self._set_bank_status("No laps found in this session.")
            return

        # Compute session best for delta column
        best_ms = min((l["lap_time_ms"] for l in laps if l["lap_time_ms"] > 0), default=0)
        session_date = self._lap_bank_combo.currentText()[:10]

        # Collect lap nums already in table to skip duplicates
        existing_nums: set[int] = set()
        for r in range(self._lap_table.rowCount()):
            item = self._lap_table.item(r, 0)
            if item:
                try:
                    existing_nums.add(int(item.text()))
                except ValueError:
                    pass

        # Clear stale compound tags for laps we are about to load (DEF-P1-006)
        for _lap in laps:
            if _lap["lap_num"] not in existing_nums:
                self._lap_compound_tags.pop(_lap["lap_num"], None)

        added = 0
        for lap in laps:
            ln = lap["lap_num"]
            if ln in existing_nums:
                continue
            self._add_bank_lap_row(
                lap_num=ln,
                lap_time_ms=lap["lap_time_ms"],
                fuel_used=float(lap.get("fuel_used") or 0),
                compound=lap.get("compound") or "",
                best_ms=best_ms,
                session_date=session_date,
                fuel_start=float(lap.get("fuel_start") or 0),
                fuel_end=float(lap.get("fuel_end") or 0),
                is_pit_lap=bool(lap.get("is_pit_lap", 0)),
                is_out_lap=bool(lap.get("is_out_lap", 0)),
            )
            added += 1

        # Compute session-scoped fuel average for Practice Analysis (DEF-P1-007)
        # Exclude pit laps and outlaps — both have unrepresentative fuel consumption
        _fuel_vals = [float(l.get("fuel_used") or 0) for l in laps
                      if float(l.get("fuel_used") or 0) > 0
                      and not bool(l.get("is_pit_lap", 0))
                      and not bool(l.get("is_out_lap", 0))]
        self._loaded_session_avg_fuel = (sum(_fuel_vals) / len(_fuel_vals)) if _fuel_vals else 0.0

        # DEF-P2-009: refresh Strategy Builder fuel burn label immediately after load
        if hasattr(self, "_lbl_fuel_burn_display") and self._loaded_session_avg_fuel > 0:
            self._lbl_fuel_burn_display.setText(
                f"{self._loaded_session_avg_fuel:.2f} L/lap (loaded session)")

        total_rows = self._lap_table.rowCount()
        tagged = sum(
            1 for r in range(total_rows)
            if self._compound_at_row(r)
        )
        self._set_bank_status(
            f"Added {added} lap(s) — {total_rows} total in table, {tagged} tagged."
        )

    def _clear_lap_table(self) -> None:
        """Remove all rows from _lap_table and reset compound tags."""
        self._lap_table.setRowCount(0)
        self._lap_compound_tags.clear()
        self._set_bank_status("Lap table cleared.")

    def _delete_selected_session(self) -> None:
        """Delete only the session currently selected in the bank combo."""
        from PyQt6.QtWidgets import QMessageBox
        if self._db is None:
            self._set_bank_status("Session database unavailable — recorded laps can't be loaded right now.")
            return
        session_id = self._lap_bank_combo.currentData()
        if not session_id:
            self._set_bank_status("No session selected.")
            return
        label = self._lap_bank_combo.currentText()
        reply = QMessageBox.question(
            self, "Delete Session",
            f"Permanently delete:\n{label}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._db.delete_session(session_id)
        except Exception as exc:
            self._set_bank_status(f"Delete failed: {exc}")
            return
        self._lap_table.setRowCount(0)
        self._lap_compound_tags.clear()
        self._refresh_lap_bank()
        self._set_bank_status("Session deleted.")

    def _set_bank_status(self, msg: str) -> None:
        if hasattr(self, "_lbl_bank_status"):
            self._set_bank_status(msg)

    def _save_session_to_db(self) -> None:
        """Save all in-memory laps to the database with current compound and setup tags.

        If the EventDispatcher already has an open session (auto-written by the live
        telemetry path), reuse that session and only update compounds + setup IDs —
        do NOT re-insert laps (they were already written). This prevents the duplicate
        session that was created when the Save Session button opened a second session.
        """
        if self._db is None:
            if hasattr(self, "_lbl_bank_status"):
                self._set_bank_status("Session database unavailable — recorded laps can't be loaded right now.")
            return
        laps = self._logger.records()
        if not laps:
            if hasattr(self, "_lbl_bank_status"):
                self._set_bank_status("No laps to save.")
            return

        # --- If the live session is already open, reuse it (DEF-P2-030 fix) ---
        existing_sid = (self._dispatcher._session_id
                        if self._dispatcher is not None else 0)
        if existing_sid:
            # Laps already written by EventDispatcher — just update compounds/setups.
            for lap in laps:
                compound = self._lap_compound_tags.get(lap.lap_num, "")
                if compound:
                    try:
                        self._db.update_lap_compound(existing_sid, lap.lap_num, compound)
                    except Exception:
                        pass
                setup_id = self._get_setup_id_for_saved_lap(lap.lap_num)
                if setup_id:
                    try:
                        self._db.update_lap_setup_id(existing_sid, lap.lap_num, setup_id)
                    except Exception:
                        pass
            self._refresh_lap_bank()
            self._set_bank_status(
                f"Session {existing_sid} updated with compounds ({len(laps)} lap(s)).")
            return

        # --- No live session: create a new one and write all laps ---
        # Working Race Config sprint: session tagging reads the named working-
        # config model (same bridge source — the session must be tagged with
        # what it was actually run under, incl. a restored historical config).
        wrc       = self._working_race_config()
        car_name  = wrc.car
        track     = wrc.track
        config_id = wrc.config_id
        car_id    = 0
        if self._dispatcher is not None:
            try:
                car_id = int(self._dispatcher._car_id_ref[0])
            except Exception:
                pass
        session_type = (self._combo_live_mode.currentText()
                        if hasattr(self, "_combo_live_mode") else "Practice")
        try:
            sid = self._db.open_session(car_id, track, session_type,
                                        car_name=car_name, config_id=config_id)
        except Exception as exc:
            self._set_bank_status(f"Save failed: {exc}")
            return
        # OFR-1: score prior recs now that the save session has an id; wrc has
        # no layout notion so pass "" (matches recs saved with empty layout_id).
        self._trigger_scoring_pass(car_id, wrc.track, "", sid)
        recorder = self._dispatcher._recorder if self._dispatcher else None
        for lap in laps:
            stats = None
            if recorder is not None:
                try:
                    stats = recorder.get_lap(lap.lap_num)
                except Exception:
                    pass
            compound = self._lap_compound_tags.get(lap.lap_num, "")
            try:
                self._db.write_lap(
                    sid, lap.lap_num, lap.lap_time_ms,
                    lap.fuel_used, stats, compound,
                    fuel_start=getattr(lap, "fuel_start", 0.0),
                    fuel_end=getattr(lap, "fuel_end", 0.0),
                    is_pit_lap=bool(getattr(lap, "is_pit_lap", False)),
                    is_out_lap=bool(getattr(lap, "is_out_lap", False)),
                    delta_ms=int(getattr(lap, "delta_ms", 0)),
                    session_type=(lap.session_type.value
                                  if hasattr(lap.session_type, "value")
                                  else str(getattr(lap, "session_type", ""))),
                )
            except Exception as exc:
                self._set_bank_status(f"Save failed on lap {lap.lap_num}: {exc}")
                return
            setup_id = self._get_setup_id_for_saved_lap(lap.lap_num)
            if setup_id:
                try:
                    self._db.update_lap_setup_id(sid, lap.lap_num, setup_id)
                except Exception:
                    pass
        self._refresh_lap_bank()
        self._set_bank_status(
            f"Saved {len(laps)} lap(s) to database (session {sid}).")

    def _get_setup_id_for_saved_lap(self, lap_num: int) -> int:
        """Read the setup ID from the combo widget in column 14 for the given lap number."""
        for row in range(self._lap_table.rowCount()):
            item = self._lap_table.item(row, 0)
            if item and item.text() == str(lap_num):
                widget = self._lap_table.cellWidget(row, 14)
                if isinstance(widget, QComboBox):
                    return widget.currentData() or 0
                return 0
        return 0

    def _save_setup_from_lapdata(self) -> None:
        """Save the current car setup to config (and a DB snapshot if DB is connected)."""
        if not hasattr(self, "_setup_car"):
            if hasattr(self, "_lbl_bank_status"):
                self._set_bank_status(
                    "Open the Strategy tab at least once to populate the setup form.")
            return
        self._setup_save()  # persist to config JSON + refresh combos
        if self._db is not None:
            try:
                d = self._current_setup_dict()
                car_id = 0
                if self._dispatcher is not None:
                    car_id = int(self._dispatcher._car_id_ref[0])
                track = self._config.get("strategy", {}).get("track", "")
                self._db.write_setup(session_id=0, car_id=car_id,
                                     track=track, setup_dict=d)
            except Exception as exc:
                print(f"[Setup] DB snapshot failed: {exc}")
        if hasattr(self, "_lbl_bank_status"):
            from ui.setup_name_helper import setup_display_label
            d = self._current_setup_dict()
            self._set_bank_status(
                f"Setup saved: {setup_display_label(d)} (ID {d.get('setup_id', '?')})")

    def _wipe_all_sessions(self) -> None:
        """Ask for confirmation then delete every session and lap record from the DB."""
        from PyQt6.QtWidgets import QMessageBox
        if self._db is None:
            return
        reply = QMessageBox.question(
            self,
            "Wipe All Sessions",
            "This will permanently delete ALL saved sessions and lap records.\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            n = self._db.clear_all_sessions()
        except Exception as exc:
            self._set_bank_status(f"Wipe failed: {exc}")
            return
        self._lap_table.setRowCount(0)
        self._lap_compound_tags.clear()
        self._refresh_lap_bank()
        self._set_bank_status(f"Wiped {n} session(s). Database is now empty — ready for fresh data.")

    def _load_session_config(self) -> None:
        """Restore car, track and race params from the selected session."""
        if self._db is None:
            return
        session_id = self._lap_bank_combo.currentData()
        if not session_id:
            return

        # Fetch the full session row to get car_name, track, config_id
        try:
            sessions = self._db.get_all_sessions(limit=60)
        except Exception as exc:
            self._set_bank_status(f"Error reading sessions: {exc}")
            return
        row = next((s for s in sessions if s["id"] == session_id), None)
        if not row:
            self._set_bank_status("Session not found.")
            return

        car_name  = row.get("car_name", "")
        track     = row.get("track", "")
        config_id = row.get("config_id", "")

        # Restore track + race params from stored race_configs snapshot into config["strategy"]
        if track:
            self._config.setdefault("strategy", {})["track"] = track
        if car_name:
            self._config.setdefault("strategy", {})["car"] = car_name
        stored = self._config.get("race_configs", {}).get(config_id, {})
        if stored:
            sc = self._config.setdefault("strategy", {})
            for k in ("race_type", "total_laps", "race_duration_minutes"):
                if k in stored:
                    sc[k] = stored[k]

        # Recompute config ID and refresh bank markers
        self._update_race_config()

        # Restore full Car Setup form — prefer saved setup, fall back to spec autofill
        if car_name:
            saved_setup = next(
                (s for s in self._saved_setups if s.get("name") == car_name), None
            )
            if saved_setup:
                self._fill_setup_fields(saved_setup)
            else:
                self._autofill_car_specs(car_name)
        self._gear_ratios_captured = False  # force fresh telemetry read for gear ratios

        parts = [p for p in [car_name, track] if p]
        hint = "  ·  ".join(parts) if parts else "session"
        if stored and car_name and next(
            (s for s in self._saved_setups if s.get("name") == car_name), None
        ):
            suffix = " (race params + full car setup restored)"
        elif stored:
            suffix = " (race params + car specs autofilled)"
        else:
            suffix = " (car + track restored; race length unknown)"
        self._set_bank_status(f"Loaded: {hint}{suffix}")

    # ------------------------------------------------------------------
    # AI analysis helpers
    # ------------------------------------------------------------------

    def _resolve_strat_session_id(self) -> int:
        """Resolve the session id used for strategy lap-data queries.

        Prefers the live dispatcher session (correct pre-race, when the active
        session IS the practice session), then falls back to the historian-selected
        session, then 0 (all car+track history). Shared by pre-race analysis and the
        mid-race re-plan input assembly so the two never drift apart.
        """
        _strat_sid = 0
        if hasattr(self, "_dispatcher") and self._dispatcher is not None:
            _live_sid = getattr(self._dispatcher, "_session_id", 0) or 0
            if _live_sid > 0:
                _strat_sid = _live_sid
        if _strat_sid == 0:
            _hist_sid = getattr(self, "_hist_selected_session_id", None)
            if _hist_sid and int(_hist_sid) > 0:
                _strat_sid = int(_hist_sid)
        return _strat_sid

    def _assemble_strategy_inputs(self, session_id_override: int | None = None) -> dict:
        """Collect all inputs needed for a strategy analysis call.

        Returns a dict with keys: params, lap_data_by_compound, car_id, session_id,
        car_name, car_specs, setup_comparison_text, tyre_degradation_cache,
        model_name, api_key.

        ``session_id_override`` — when provided and > 0, use it directly as the
        practice session id for the lap-data query instead of reading the live
        dispatcher session.  Pass 0 (or omit) to use the standard resolution:
        read the dispatcher's live session id, then fall back to
        ``_hist_selected_session_id``.  Callers that already know the practice
        session id (e.g. mid-race re-plan, which must NOT use the race session)
        should supply it via this parameter.

        lap_data_by_compound is always queried using the practice session id so
        that in-race laps do not pollute the practice compound baseline.
        Fallback when no practice session id is known: pass session_id=0 to
        get_compound_lap_sequences, which returns ALL history for this car+track
        (better than the race session alone).
        """
        from strategy.race_params import RaceParams
        _ui_lap_data = self._read_ui_lap_table()

        # AI Snapshot Migration: race parameters come from a frozen snapshot of
        # the canonical contexts (EventContext race rules, StrategyContext plan
        # fields incl. fuel burn/pit loss, TrackContext identity) instead of
        # live config["strategy"] reads. Byte-identical to the previous inline
        # expressions when the stores are in sync (proven by
        # tests/test_analysis_inputs.py); fresh DB event values win when
        # the event was edited after "Set as Active".
        _ai_snap = self._build_strategy_inputs()
        race_params = _ai_snap.race_params_dict()

        params = RaceParams(**race_params)

        _car_name, _car_specs = self._load_car_specs_for_current()
        _setup_comparison = self._build_setup_comparison_text(race_params["track"])
        _car_id_strat = self._db.get_car_id(_car_name) if self._db and _car_name else 0

        # Resolve the practice session id used for lap-data queries.
        # If session_id_override is supplied and > 0, use it directly — this is
        # the pre-race practice session id captured at pre-race analysis time and
        # stored in self._strat_practice_sid, preventing the mid-race re-plan from
        # querying only in-race laps (spec Risk #2 / AC8).
        # An explicit override is authoritative, INCLUDING 0: override == 0 means
        # "no known practice session" and is passed straight through so the DB query
        # uses session_id=0 (all car+track history, which includes practice laps) —
        # never the live race session.
        # When no override is given (None), fall back to the live dispatcher session
        # (correct pre-race when the active session IS the practice session), then to
        # the historian-selected session.
        if session_id_override is not None:
            _strat_sid: int = session_id_override
        else:
            _strat_sid = self._resolve_strat_session_id()

        lap_data_by_compound: dict[str, list[float]] = {}
        if self._db and _car_id_strat > 0 and race_params.get("track"):
            try:
                lap_data_by_compound = self._db.get_strategy_lap_data(
                    _car_id_strat,
                    race_params["track"],
                    _strat_sid,
                    _ui_lap_data,
                )
            except Exception as _e:
                print(f"[AssembleStrategyInputs] get_strategy_lap_data failed: {_e}")
                lap_data_by_compound = _ui_lap_data
        else:
            lap_data_by_compound = _ui_lap_data

        degradation = self._tyre_degradation_cache if self._tyre_degradation_cache else None

        return {
            "params":                  params,
            "lap_data_by_compound":    lap_data_by_compound,
            "car_id":                  _car_id_strat,
            "session_id":              _strat_sid,
            "car_name":                _car_name,
            "car_specs":               _car_specs,
            "setup_comparison_text":   _setup_comparison,
            "tyre_degradation_cache":  degradation,
        }

    def _config_pit_loss_secs(self) -> float:
        """The persisted strategy pit loss (seconds), default 20.

        Kept on MainWindow (not moved to RacePlanMixin) because it is the sole
        config["strategy"] access in the Race Plan surface and is pinned by the
        frozen fan-out allowlist; the mixin's methods call it via the MRO."""
        try:
            return float(self._config.get("strategy", {}).get("pit_loss_secs", 20.0) or 20.0)
        except (TypeError, ValueError):
            return 20.0

    def _launch_replan_worker(self, reason: str) -> None:
        """Post a graceful 'not yet available' status for a mid-race re-plan.

        Called by the engine's _replan_callback from the telemetry thread.
        The deterministic mid-race re-plan is not implemented in this build;
        rather than calling any AI, the worker posts a ("replan_error", str)
        message to _strategy_result_queue, which is drained on the Qt main thread
        by _display_strategy_results (which calls the engine's replan_failed()).
        """
        import threading as _threading

        def _worker():
            self._strategy_result_queue.put((
                "replan_error",
                "Live mid-race re-plan is not available in this build. Build the "
                "race plan before the race; live state is shown as read-only advisory.",
            ))

        _threading.Thread(target=_worker, daemon=True).start()

    def _display_practice_results(self, result: tuple) -> None:
        if not hasattr(self, "_practice_results_text"):
            return
        status, payload = result
        if status == "error":
            self._practice_results_text.setHtml(
                f"<span style='color:#F55;'>Practice analysis failed:</span><br>"
                f"<pre style='color:#AAA; white-space:pre-wrap;'>{payload}</pre>")
            return

        analysis = payload

        section_hdr = ("font-size:11px; color:#888; font-weight:bold; "
                       "margin:10px 0 4px 0; letter-spacing:1px;")
        card        = ("background:#1C2A3A; border-radius:6px; "
                       "padding:10px 14px; margin-bottom:10px;")
        chg_hdr     = ("background:#2A3A1C; border-left:4px solid #8BC34A; "
                       "border-radius:4px; padding:8px 12px; margin-bottom:4px;")
        chg_row     = "padding:4px 0 4px 8px; border-bottom:1px solid #1A2A10;"

        html = ""

        # Strategies — reuse existing card builder
        if analysis.strategies:
            html += f"<p style='{section_hdr}'>RACE STRATEGIES</p>"
            html += self._build_strategy_html(analysis.strategies)

        # Aero/fuel trade-off
        if analysis.aero_fuel_analysis:
            html += f"<p style='{section_hdr}'>AERO / FUEL TRADE-OFF</p>"
            html += (f"<div style='{card}'>"
                     f"<p style='margin:0; line-height:1.5;'>{analysis.aero_fuel_analysis}</p>"
                     f"</div>")

        # Fuel saving efficiency
        if analysis.fuel_saving_analysis:
            html += f"<p style='{section_hdr}'>FUEL SAVING EFFICIENCY</p>"
            html += (f"<div style='background:#1C2A3A; border-left:4px solid #4FC3F7; "
                     f"border-radius:6px; padding:10px 14px; margin-bottom:10px;'>"
                     f"<p style='margin:0; line-height:1.5;'>{analysis.fuel_saving_analysis}</p>"
                     f"</div>")

        # Tyre management
        if analysis.tyre_management:
            html += f"<p style='{section_hdr}'>TYRE MANAGEMENT</p>"
            html += (f"<div style='background:#1C2A3A; border-left:4px solid #F5A623; "
                     f"border-radius:6px; padding:10px 14px; margin-bottom:10px;'>"
                     f"<p style='margin:0; line-height:1.5;'>{analysis.tyre_management}</p>"
                     f"</div>")

        # Setup changes
        if analysis.setup_changes:
            html += f"<p style='{section_hdr}'>SETUP CHANGES</p>"
            html += (f"<div style='{chg_hdr}'>"
                     f"<b style='color:#8BC34A;'>&#9745; SETUP CHANGES — ENDURANCE PRIORITY</b></div>")
            for i, change in enumerate(analysis.setup_changes, 1):
                html += (f"<div style='{chg_row}'>"
                         f"<span style='color:#E0E0E0;'>"
                         f"<b style='color:#F5C542;'>{i}.</b>&nbsp;{change}"
                         f"</span></div>")

        # Further practice
        if analysis.further_practice:
            html += f"<p style='{section_hdr}'>FURTHER PRACTICE REQUIRED</p>"
            html += f"<div style='{card}'>"
            for i, item in enumerate(analysis.further_practice, 1):
                html += (f"<p style='margin:3px 0; line-height:1.5;'>"
                         f"<b style='color:#F5C542;'>{i}.</b>&nbsp;{item}</p>")
            html += "</div>"

        self._practice_results_text.setHtml(html)

        # Also populate Load Strategy buttons from practice analysis strategies
        if analysis.strategies:
            self._strategy_options = analysis.strategies
            for i, btn in enumerate(self._ai_apply_btns):
                if i < len(analysis.strategies):
                    btn.setText(f"Load Strategy {i+1}: {analysis.strategies[i].name}")
                    btn.setVisible(True)
                else:
                    btn.setVisible(False)
            self._refresh_live_strategy_combo()

    def _display_strategy_results(self, result: tuple) -> None:
        status, payload = result

        # Mid-race re-plan results — handled silently; the engine speaks the result
        if status == "replan_ok":
            if self._strategy_engine is not None:
                self._strategy_engine.apply_replan(payload)
            return
        if status == "replan_error":
            if self._strategy_engine is not None:
                self._strategy_engine.replan_failed()
            print(f"[Replan] failed: {payload}")
            return

        if status == "error":
            self._ai_results_text.setHtml(
                f"<span style='color:#F55;'>Analysis failed:</span><br><pre>{payload}</pre>")
            return

        # Task 1: extract .strategies explicitly from a StrategyResult; also
        # handle the legacy code path where payload is still a bare list
        # (e.g. any other caller that hasn't been updated yet).
        options = getattr(payload, "strategies", payload)
        self._strategy_options = options
        self._strategy_options_html_base = self._build_strategy_html(options)

        _warn_html = ""

        # Task 2: append feasibility metadata (rejected strategies, data gaps,
        # assumptions, calculation notes) below the strategy cards when present.
        # Only render a section if its list is non-empty; never show empty headers.
        _feasibility_html = self._build_feasibility_html(payload)

        _full_html = (_warn_html + self._strategy_options_html_base) if _warn_html else self._strategy_options_html_base
        if _feasibility_html:
            _full_html += _feasibility_html
        self._ai_results_text.setHtml(_full_html)

        for i, btn in enumerate(self._ai_apply_btns):
            if i < len(options):
                btn.setText(f"Load {options[i].name} Strategy")
                btn.setVisible(True)
            else:
                btn.setVisible(False)
        self._refresh_live_strategy_combo()

        # Persist so results survive app restart
        try:
            self._config["_strategy_cache"] = {
                "html":      self._strategy_options_html_base,
                "btn_labels": [options[i].name for i in range(len(options))],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            self._persist_config()
        except Exception:
            pass

    def _restore_strategy_cache(self) -> None:
        """Restore last AI strategy analysis HTML from config so results survive restart."""
        try:
            cache = self._config.get("_strategy_cache", {})
            html = cache.get("html", "")
            labels = cache.get("btn_labels", [])
            if not html:
                return
            self._strategy_options_html_base = html
            self._ai_results_text.setHtml(html)
            for i, btn in enumerate(self._ai_apply_btns):
                if i < len(labels):
                    btn.setText(f"Load Strategy {i + 1}: {labels[i]}")
                    btn.setVisible(True)
        except Exception:
            pass

    def _build_strategy_html(self, options: list, loaded_rank: int = 0) -> str:
        card    = "background:#1C2A3A; border-radius:6px; padding:10px 14px; margin-bottom:10px;"
        card_ok = "background:#1A2C1A; border-left:4px solid #8BC34A; border-radius:6px; " \
                  "padding:10px 14px; margin-bottom:10px;"
        html = ""
        for opt in options:
            stints_html = " &rarr; ".join(
                f"<b style='color:#8BC34A;'>{s['compound']}</b> "
                f"<span style='color:#AAA;'>({s['laps']} laps)</span>"
                for s in opt.stints
            )
            ai_m = int(opt.estimated_time_s // 60)
            ai_s = opt.estimated_time_s - ai_m * 60
            style = card_ok if opt.rank == loaded_rank else card

            # --- Deliverable 1: head-to-head delta and app-computed time ---
            det_time_s   = getattr(opt, "deterministic_time_s", 0.0) or 0.0
            delta_s      = getattr(opt, "delta_vs_fastest_s",  0.0) or 0.0
            if det_time_s > 0.0:
                det_m = int(det_time_s // 60)
                det_ss = det_time_s - det_m * 60
                app_time_str = f"{det_m}:{det_ss:05.2f}"
                if delta_s == 0.0:
                    delta_html = "<span style='color:#8BC34A;'>fastest</span>"
                else:
                    delta_html = f"<span style='color:#F5A623;'>+{delta_s:.1f}s vs fastest</span>"
                # Deliverable 2: outcome_confidence coloring
                oc = getattr(opt, "outcome_confidence", "") or ""
                if oc == "high":
                    oc_color   = "#8BC34A"
                elif oc == "medium":
                    oc_color   = "#F5C542"
                elif oc == "low":
                    oc_color   = "#F55"
                else:
                    oc_color   = "#888"
                conf_badge = (
                    f" <span style='color:{oc_color}; font-size:10px;'>"
                    f"(confidence: {oc})</span>" if oc else ""
                )
                time_line_html = (
                    f"<p style='margin:0 0 4px 0; color:#888; font-size:11px;'>"
                    f"<b style='color:#CCC;'>App: {app_time_str}</b>{conf_badge}"
                    f" &nbsp;{delta_html}"
                    f" &nbsp;|&nbsp; AI est: {ai_m}:{ai_s:05.2f}"
                    f" &nbsp;|&nbsp; pit time {opt.pit_time_s:.1f}s</p>"
                )
            else:
                # Thin-data / not computed: fall back to AI estimate only, no delta
                time_line_html = (
                    f"<p style='margin:0 0 4px 0; color:#888; font-size:11px;'>"
                    f"AI est: {ai_m}:{ai_s:05.2f}"
                    f" &nbsp;|&nbsp; pit time {opt.pit_time_s:.1f}s</p>"
                )

            # --- Deliverable 5: rank badge ---
            rank_by_time = getattr(opt, "rank_by_time", 0) or 0
            rank_badge = (
                f" <span style='background:#1C3A2A; color:#8BC34A; font-size:10px; "
                f"border-radius:3px; padding:0 4px;'>#{rank_by_time} by time</span>"
                if rank_by_time > 0 else ""
            )

            # --- Deliverable 3: risk fields and confidence_score ---
            tyre_risk      = getattr(opt, "tyre_risk",      "") or ""
            fuel_risk      = getattr(opt, "fuel_risk",      "") or ""
            undercut_risk  = getattr(opt, "undercut_risk",  "") or ""
            conf_score     = getattr(opt, "confidence_score", 0.0) or 0.0

            def _risk_chip(label: str, value: str) -> str:
                if not value:
                    return ""
                color = "#8BC34A" if value == "low" else ("#F5A623" if value == "medium" else "#F55")
                return (
                    f"<span style='color:{color}; background:#0D1A26; border-radius:3px; "
                    f"padding:0 5px; margin-right:4px; font-size:10px;'>"
                    f"{label}: {value}</span>"
                )

            risk_chips = (
                _risk_chip("tyre", tyre_risk)
                + _risk_chip("fuel", fuel_risk)
                + _risk_chip("undercut", undercut_risk)
            )
            score_chip = (
                f"<span style='color:#888; font-size:10px; margin-right:4px;'>"
                f"AI conf: {conf_score * 100:.0f}%</span>"
                if conf_score > 0.0 else ""
            )
            risk_row_html = (
                f"<p style='margin:2px 0 4px 0;'>{risk_chips}{score_chip}</p>"
                if (risk_chips or score_chip) else ""
            )

            pros_html = (f"<p style='margin:2px 0; color:#8BC34A; font-size:11px;'>"
                         f"&#10003; {opt.positives}</p>" if opt.positives else "")
            cons_html = (f"<p style='margin:2px 0; color:#F5A623; font-size:11px;'>"
                         f"&#10007; {opt.negatives}</p>" if opt.negatives else "")
            html += (
                f"<div style='{style}'>"
                f"<p style='margin:0 0 4px 0;'>"
                f"<b style='color:#F5C542; font-size:13px;'>Strategy {opt.rank}: {opt.name}</b>"
                f"{rank_badge}</p>"
                f"<p style='margin:0 0 6px 0;'>{stints_html}</p>"
                f"{time_line_html}"
                f"{risk_row_html}"
                f"<p style='margin:4px 0; line-height:1.5;'>{opt.summary}</p>"
                f"{pros_html}{cons_html}"
                f"<p style='margin:4px 0 0 0; color:#F5A623; font-size:11px;'>"
                f"&#9888; {opt.risks}</p>"
                f"</div>"
            )
        return html

    def _build_feasibility_html(self, payload) -> str:
        """Build compact HTML for rejected strategies, data gaps, assumptions, and
        calculation notes from a StrategyResult.  Returns an empty string if payload
        is a bare list (legacy path) or all four lists are empty, so no empty headers
        are ever rendered.
        """
        # Only process StrategyResult objects — bare list payloads have no metadata.
        rejected   = getattr(payload, "rejected_strategies", None) or []
        data_gaps  = getattr(payload, "data_gaps",            None) or []
        assumptions        = getattr(payload, "assumptions",         None) or []
        calculation_notes  = getattr(payload, "calculation_notes",   None) or []

        if not (rejected or data_gaps or assumptions or calculation_notes):
            return ""

        _sep    = "border-top:1px solid #2A3A4A; margin-top:12px; padding-top:10px;"
        _hdr    = "color:#AAA; font-size:11px; font-weight:bold; margin:6px 0 2px 0;"
        _item   = "color:#CCC; font-size:11px; margin:1px 0 1px 14px;"
        _note   = "color:#888; font-size:10px; margin:1px 0 1px 14px;"

        html = f"<div style='{_sep}'>"

        if rejected:
            html += f"<p style='{_hdr}'>Rejected Stop Counts</p>"
            for r in rejected:
                name   = getattr(r, "name",   str(r))
                reason = getattr(r, "reason", "")
                html += (
                    f"<p style='{_item}'>"
                    f"<span style='color:#F5A623;'>{name}</span>"
                    f"{(' — ' + reason) if reason else ''}</p>"
                )

        if data_gaps:
            html += f"<p style='{_hdr}'>Data Gaps</p>"
            for g in data_gaps:
                name = getattr(g, "name",        str(g))
                desc = getattr(g, "description", "")
                html += (
                    f"<p style='{_item}'>"
                    f"<span style='color:#F55;'>{name}</span>"
                    f"{(' — ' + desc) if desc else ''}</p>"
                )

        if assumptions:
            html += f"<p style='{_hdr}'>Assumptions</p>"
            for a in assumptions:
                html += f"<p style='{_note}'>&#8226; {a}</p>"

        if calculation_notes:
            html += f"<p style='{_hdr}'>Calculation Notes</p>"
            for n in calculation_notes:
                html += f"<p style='{_note}'>&#8226; {n}</p>"

        html += "</div>"
        return html

    def _apply_strategy_option(self, index: int) -> None:
        if index >= len(self._strategy_options):
            return
        opt = self._strategy_options[index]
        self._strategy_stint_table.setRowCount(0)
        for stint_dict in opt.stints:
            self._strategy_add_stint(preset=stint_dict)
        # Re-render with the loaded strategy highlighted
        loaded_html = self._build_strategy_html(self._strategy_options, loaded_rank=opt.rank)
        loaded_html += (
            f"<div style='background:#1A2C1A; border-left:4px solid #8BC34A; "
            f"border-radius:4px; padding:8px 12px;'>"
            f"<b style='color:#8BC34A;'>&#9745; Strategy {opt.rank} loaded into Stint Plan</b>"
            f"<span style='color:#888;'> — click  Apply Plan  to activate.</span></div>"
        )
        self._ai_results_text.setHtml(loaded_html)

    def _on_reset_clicked(self) -> None:
        # UAT #6 Phase 2A: a reset ends the stint — refine from whatever was captured.
        self._autorefine_capture(reason="reset")
        if self._tracker is not None:
            self._tracker.reset()
            self._tracker.set_session_type_override(None)
        self._bridge.race_state_changed.emit("IDLE")

    # ---------------------------------------------- UAT #6 Phase 2A: auto refinement

    def _refine_auto_capture_enabled(self) -> bool:
        """Auto-capture defaults ON; opt out via config['track_refinement']['auto_capture']."""
        try:
            return bool(self._config.get("track_refinement", {}).get("auto_capture", True))
        except Exception:
            return True

    def _refine_event_weight(self) -> float:
        """Phase 2B anchoring weight (event-lap influence, 0..1). Default 0.30;
        override via config['track_refinement']['event_weight']. Clamped to a sane
        band so a misconfig can't let event laps overturn the model."""
        from data.track_refinement import EVENT_WEIGHT_DEFAULT
        try:
            w = float(self._config.get("track_refinement", {}).get("event_weight", EVENT_WEIGHT_DEFAULT))
        except (TypeError, ValueError):
            w = EVENT_WEIGHT_DEFAULT
        return max(0.05, min(0.5, w))

    def _maybe_autostart_refine_capture(self) -> None:
        """Start (or re-target) live path capture when the driven track/layout has an
        accepted model. Cheap-guarded; called throttled from _poll_ui_queue.

        If a capture is already running for a DIFFERENT track/layout (the driver
        switched tracks without a reset), refine the old one first, then restart.
        """
        if not self._refine_auto_capture_enabled():
            return
        try:
            ec = self._build_event_context()
            loc = str(getattr(ec, "track_location_id", "") or "").strip()
            lay = str(getattr(ec, "layout_id", "") or "").strip()
            car = str(getattr(ec, "car", "") or "").strip()
        except Exception:
            return
        cap = getattr(self, "_track_path_capture", None)
        if cap is not None:
            # Already capturing — only act if the identity changed.
            if loc and lay and not cap.matches(loc, lay):
                self._autorefine_capture(reason="track_change")
            else:
                return
        if not loc or not lay:
            return
        from data.track_model_alignment import find_accepted_model_path
        if find_accepted_model_path(loc, lay) is None:
            return  # no model to refine — stay inert
        from data.live_track_path_capture import LiveTrackPathCapture
        self._track_path_capture = LiveTrackPathCapture(loc, lay, car_name=car)
        print(f"[Refine] auto-capture started for {loc}/{lay}")
        if hasattr(self, "_tm_refresh_refinement_panel"):
            try:
                self._tm_refresh_refinement_panel()
            except Exception:
                pass


    def _autorefine_capture(self, reason: str = "") -> None:
        """Build a candidate from the active capture (if any) and clear it.

        Non-destructive: produces a gated candidate the user reviews/accepts in
        the Track Modelling tab. Sets a one-line notice when an improving
        candidate is available. Best-effort; never raises into the caller.
        """
        cap = getattr(self, "_track_path_capture", None)
        self._track_path_capture = None
        if cap is None or cap.lap_count() == 0:
            return
        try:
            from data.track_refinement import refine_from_session
            session = cap.build_session()
            cars = [cap.car_name] if getattr(cap, "car_name", "") else []
            result = refine_from_session(
                session, cap.track_location_id, cap.layout_id, contributing_cars=cars,
                event_weight=self._refine_event_weight(),
            )
            if result.success and result.verdict is not None and result.verdict.improves:
                self._refine_notice = (
                    f"Refined track model available for {cap.track_location_id} "
                    f"({result.contributing_laps} lap(s)) — click to review in Track Modelling."
                )
                print(f"[Refine] {self._refine_notice} (trigger: {reason})")
            else:
                self._refine_notice = ""
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[Refine] auto-refine failed: {exc}")
        self._update_refine_banner()
        if hasattr(self, "_tm_refresh_refinement_panel"):
            try:
                self._tm_refresh_refinement_panel()
            except Exception:
                pass

    def _update_refine_banner(self) -> None:
        """Show/hide the Live-tab 'refined model available' notice from _refine_notice."""
        if not hasattr(self, "_live_refine_banner"):
            return
        notice = getattr(self, "_refine_notice", "") or ""
        self._live_refine_banner.setText(("✓  " + notice) if notice else "")
        self._live_refine_banner.setVisible(bool(notice))

    def _on_refine_banner_clicked(self) -> None:
        """Clear the notice and jump to the Track Modelling tab to review the candidate."""
        self._refine_notice = ""
        self._update_refine_banner()
        try:
            # Navigate via the single sanctioned path (select_tab → the one
            # permitted _tabs.setCurrentIndex call site) rather than a raw jump.
            self.select_tab(TAB_TRACK_MODELLING)
        except Exception:
            pass

    def _build_workflow_guide_group(self) -> QGroupBox:
        guide_box = QGroupBox("How to use this tab")
        guide_box.setStyleSheet(self._group_style())
        guide_outer = QVBoxLayout(guide_box)
        guide_outer.setContentsMargins(6, 6, 6, 6)
        guide_outer.setSpacing(4)

        self._guide_toggle = QPushButton("▼  Show workflow guide")
        self._guide_toggle.setStyleSheet(
            "QPushButton { background: transparent; color: #AAE4AA; "
            "border: none; text-align: left; font-weight: bold; padding: 2px 0; }"
            "QPushButton:hover { color: #2EA043; }"
        )

        self._guide_content = QFrame()
        self._guide_content.setStyleSheet(
            f"QFrame {{ background: #222; border: 1px solid #3A3A3A; "
            f"border-radius: 4px; padding: 4px; }}"
        )
        guide_text_layout = QVBoxLayout(self._guide_content)
        guide_text_layout.setContentsMargins(8, 6, 8, 6)
        guide_text_layout.setSpacing(4)

        _STEPS = [
            ("1  Drive practice laps",
             "Connect GT7 and drive laps. Every completed lap is recorded automatically "
             "in the Lap Data tab."),
            ("2  Tag tyre compounds",
             "In the Lap Data tab, click the editable Compound cell on each lap row and type "
             "the tyre you used — e.g. RS, RM, RH, IM, W  (or Soft / Medium / Hard / Inter / Wet). "
             "Tag all laps before analysing."),
            ("3  Fill race parameters",
             "Back here, choose your track and race type (Lap or Timed). "
             "Set Tyre Wear × to match the multiplier shown in the GT7 race lobby settings. "
             "Fuel Burn auto-fills from telemetry — leave it or override it. "
             "Pit Loss is the fixed time lost per stop (lane + stationary work, typically 20–30 s)."),
            ("4  Analyse",
             "Race Strategy Analysis → 3 ranked strategies from your tagged lap data "
             "(uses degradation data if available).\n"
             "Full Practice Analysis → full package: strategy + setup changes + "
             "aero/fuel trade-off + further practice recommendations.  (Deterministic, offline.)"),
            ("5  Load a strategy",
             "Click Load Strategy 1 / 2 / 3 to populate the Stint Plan below, "
             "then click Apply Plan to activate live tracking. "
             "Or add/edit stints manually in the Stint Plan table."),
            ("6  Race",
             "The engineer monitors your pace, fuel, and pit windows and gives voice alerts. "
             "Tyre temperature thresholds auto-switch when you pit to a new compound. "
             "Ask on the push-to-talk button at any time for a status update."),
        ]

        for step_title, step_text in _STEPS:
            step_widget = QWidget()
            step_layout = QHBoxLayout(step_widget)
            step_layout.setContentsMargins(0, 2, 0, 2)
            step_layout.setSpacing(8)

            num_lbl = QLabel(step_title)
            num_lbl.setStyleSheet("color: #AAE4AA; font-weight: bold;")
            num_lbl.setFixedWidth(165)
            num_lbl.setWordWrap(False)

            desc_lbl = QLabel(step_text)
            desc_lbl.setStyleSheet(f"color: {_TEXT};")
            desc_lbl.setWordWrap(True)

            step_layout.addWidget(num_lbl)
            step_layout.addWidget(desc_lbl, 1)
            guide_text_layout.addWidget(step_widget)

        self._guide_content.setVisible(False)  # collapsed by default

        def _toggle_guide() -> None:
            visible = not self._guide_content.isVisible()
            self._guide_content.setVisible(visible)
            self._guide_toggle.setText(
                "▲  Hide workflow guide" if visible else "▼  Show workflow guide"
            )
        self._guide_toggle.clicked.connect(_toggle_guide)

        guide_outer.addWidget(self._guide_toggle)
        guide_outer.addWidget(self._guide_content)
        return guide_box

    # ------------------------------------------------------------------
    # Group 50 — driver-facing Race Plan surface (deterministic, no AI/API key)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Group 53 — read-only live current-state replan snapshot (advisory only)
    # ------------------------------------------------------------------



    def start_raw_road_distance_capture(self, *, session_id: str = ""):
        """Start an OFF-by-default, read-only raw road-distance capture (Group 61 UAT).

        Diagnostic only: it records raw live-packet road_distance (+ position/lap) so a
        UAT run over ≥3 clean laps can settle the field's live semantics. It affects no
        strategy, setup, pit, or live-replan behaviour and writes no files.
        """
        try:
            from data.live_road_distance_capture import LiveRoadDistanceCapture
            ec = self._build_event_context()
            car_name = ""
            try:
                car_name, _ = self._load_car_specs_for_current()
            except Exception:
                car_name = ""
            self._raw_rd_capture = LiveRoadDistanceCapture(
                track_id=str(getattr(ec, "track_location_id", "") or getattr(ec, "track", "") or ""),
                layout_id=str(getattr(ec, "layout_id", "") or ""),
                car_id=str(car_name or ""), session_id=str(session_id or ""))
            return self._raw_rd_capture
        except Exception:
            self._raw_rd_capture = None
            return None

    def stop_raw_road_distance_capture(self):
        """Stop the raw capture and return the accumulator (or None). Never raises."""
        cap = self._raw_rd_capture
        self._raw_rd_capture = None
        return cap

    def raw_road_distance_capture_report(self):
        """Return report rows for the current/last raw capture, or a hint. Never raises."""
        try:
            cap = self._raw_rd_capture
            if cap is None:
                return ["No raw road-distance capture is running. "
                        "Call start_raw_road_distance_capture() and drive ≥3 clean laps."]
            from data.live_road_distance_capture import analyse_live_capture
            from data.road_distance_capture_analysis import build_capture_report
            return build_capture_report(analyse_live_capture(cap))
        except Exception:
            return ["Raw road-distance capture report unavailable."]



    def _resolve_road_distance_fallback_context(self):
        """Resolve Group 58 road-distance fallback inputs (read-only, defensive).

        Returns ``(lap_distance_m, road_distance, lap_length_m)`` — all None/absent
        when unavailable. ``lap_distance_m`` is the tracker's per-lap distance (from
        cumulative road_distance minus the lap-start reference); ``lap_length_m`` is a
        TRUSTED length (reference-path asset or track-library manifest) — never invented.
        Never raises. This only supplies inputs to the pure fallback resolver; it makes
        no pit call, writes nothing, and creates no pit event.
        """
        lap_distance_m = None
        road_distance = None
        lap_length_m = None
        try:
            tr = self._tracker
            if tr is not None:
                lap_distance_m = getattr(tr, "live_lap_distance", None)
                road_distance = getattr(tr, "live_road_distance", None)
        except Exception:
            lap_distance_m = None
            road_distance = None
        try:
            ec = self._build_event_context()
            track_id = str(getattr(ec, "track_location_id", "") or "").strip()
            layout_id = str(getattr(ec, "layout_id", "") or "").strip()
            track_hint = track_id or str(getattr(ec, "track", "") or "").strip()
            if track_hint or layout_id:
                from data.reference_path_loader import resolve_trusted_lap_length
                lap_length_m = resolve_trusted_lap_length(track_hint, layout_id)
        except Exception:
            lap_length_m = None
        return lap_distance_m, road_distance, lap_length_m




    # ------------------------------------------------------------------
    # Group 51 — session selection + readiness diagnostics (read-only)
    # ------------------------------------------------------------------





    # ------------------------------------------------------------------
    # Sprint 10 — Practice → Strategy hand-off (PracticeEvidenceBundle)
    # ------------------------------------------------------------------





    def _build_ai_analysis_group(self) -> QGroupBox:
        ai_box = QGroupBox("Race Analysis (evidence-based — no AI, no API key)")
        ai_layout = QVBoxLayout(ai_box)

        # --- Race context read-only panel (populated from active event) ---
        self._lbl_strategy_event_ctx = QLabel("No active event — set one in Event Planner first.")
        self._lbl_strategy_event_ctx.setWordWrap(True)
        self._lbl_strategy_event_ctx.setStyleSheet(
            "color: #F5C542; font-size: 11px; padding: 4px;"
        )
        ai_layout.addWidget(self._lbl_strategy_event_ctx)

        param_form = QFormLayout()
        param_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        lbl_style = f"color: {_TEXT};"

        self._lbl_fuel_burn_display = QLabel("— (complete practice laps to calibrate)")
        self._lbl_fuel_burn_display.setStyleSheet("color: #AAE4AA; font-size: 11px;")
        _saved_avg_fuel = self._config.get("strategy", {}).get("fuel_burn_per_lap", 0.0)
        if self._tracker is not None and getattr(self._tracker, "avg_fuel_per_lap", 0) > 0:
            self._lbl_fuel_burn_display.setText(f"{self._tracker.avg_fuel_per_lap:.2f} L/lap (from telemetry)")
        elif _saved_avg_fuel > 0:
            self._lbl_fuel_burn_display.setText(f"{float(_saved_avg_fuel):.2f} L/lap (last session)")

        _fm_init = int(self._config.get("strategy", {}).get("fuel_mult", 1))
        self._lbl_fuel_mult_display = QLabel(f"×{_fm_init} (from Event)")
        self._lbl_fuel_mult_display.setStyleSheet("color: #AAE4AA; font-size: 11px;")

        # Session match key (internally: race config_id) — derived from
        # track + car + race length. Diagnostic Tab Cleanup (2026-07-03):
        # relabelled from the developer-facing "Race Config ID".
        self._lbl_config_id = QLabel(
            "—",
            styleSheet="color: #64B5F6; font-family: monospace; font-size: 10px;",
        )
        self._lbl_config_id.setToolTip(
            "Identifies this exact race configuration (track + car + race length).\n"
            "The Practice Lap Bank only shows sessions recorded under the same configuration.\n"
            "Updates automatically when you change track, car, or race length."
        )

        param_form.addRow(QLabel("Fuel Multiplier:", styleSheet=lbl_style), self._lbl_fuel_mult_display)
        param_form.addRow(QLabel("Fuel Burn (auto):", styleSheet=lbl_style), self._lbl_fuel_burn_display)

        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.HLine)
        _sep.setStyleSheet("color: #444;")
        param_form.addRow(_sep)
        param_form.addRow(QLabel("Session Match Key:", styleSheet=lbl_style), self._lbl_config_id)
        ai_layout.addLayout(param_form)

        self._ai_results_text = QTextEdit()
        self._ai_results_text.setReadOnly(True)
        self._ai_results_text.setMinimumHeight(280)
        self._ai_results_text.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #444;")
        self._ai_results_text.setPlaceholderText(
            "No strategy analysis yet. To get a reliable read, complete at least a "
            "few clean timed laps, tag them with a tyre compound in Practice Review, "
            "then run the analysis. Results are advisory only.")
        ai_layout.addWidget(self._ai_results_text)

        self._ai_apply_row = QHBoxLayout()
        self._ai_apply_btns: list[QPushButton] = []
        for i in range(3):
            btn = QPushButton(f"Load Strategy {i + 1}")
            btn.setVisible(False)
            idx = i
            btn.clicked.connect(lambda _=False, n=idx: self._apply_strategy_option(n))
            self._ai_apply_row.addWidget(btn)
            self._ai_apply_btns.append(btn)
        self._ai_apply_row.addStretch()
        ai_layout.addLayout(self._ai_apply_row)

        return ai_box

    def _build_stint_plan_group(self) -> QGroupBox:
        plan_box = QGroupBox("Stint Plan")
        plan_layout = QVBoxLayout(plan_box)

        self._strategy_stint_table = QTableWidget()
        self._strategy_stint_table.setColumnCount(6)
        self._strategy_stint_table.setHorizontalHeaderLabels([
            "Stint", "Compound", "Planned Laps", "Ref Lap (M:SS.mmm)",
            "Tyre Threshold (s)", "Fuel Load (L)",
        ])
        self._strategy_stint_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._strategy_stint_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._strategy_stint_table.setStyleSheet(
            f"QTableWidget {{ background: {_DARK_CARD}; color: {_TEXT}; "
            f"gridline-color: #444; }}"
            f"QHeaderView::section {{ background: #1F4E78; color: white; "
            f"font-weight: bold; padding: 4px; }}"
        )
        plan_layout.addWidget(self._strategy_stint_table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Stint")
        btn_remove = QPushButton("Remove Stint")
        btn_apply = QPushButton("Apply Plan")
        # Primary action of the Strategy Builder — loads the built stint plan into
        # the strategy engine for the Live Race Engineer. Not a setup change and
        # not a pit command. Consistent NGR primary CTA styling.
        from ui import ngr_theme as _ngr_ap
        btn_apply.setStyleSheet(_ngr_ap.primary_button_qss())
        btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset = QPushButton("Reset")
        btn_add.clicked.connect(self._strategy_add_stint)
        btn_remove.clicked.connect(self._strategy_remove_stint)
        btn_apply.clicked.connect(self._strategy_apply_plan)
        btn_reset.clicked.connect(self._strategy_reset_plan)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_reset)
        plan_layout.addLayout(btn_row)

        # --- Save Race Plan section ---
        _sep2 = QFrame()
        _sep2.setFrameShape(QFrame.Shape.HLine)
        _sep2.setStyleSheet("color: #444;")
        plan_layout.addWidget(_sep2)

        # Saved plans combo
        saved_plans_row = QHBoxLayout()
        saved_plans_row.addWidget(QLabel("Saved Plans:", styleSheet=f"color: {_TEXT};"))
        self._sb_saved_plans_combo = QComboBox()
        self._sb_saved_plans_combo.setMinimumWidth(280)
        self._sb_saved_plans_combo.setToolTip("Previously saved race plans for the active event and car.")
        self._sb_saved_plans_combo.currentIndexChanged.connect(self._sb_on_saved_plan_selected)
        saved_plans_row.addWidget(self._sb_saved_plans_combo, 1)
        plan_layout.addLayout(saved_plans_row)

        # Plan name input
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Plan Name:", styleSheet=f"color: {_TEXT};"))
        self._sb_plan_name_input = QLineEdit()
        self._sb_plan_name_input.setPlaceholderText("Enter a name for this plan…")
        self._sb_plan_name_input.textChanged.connect(self._sb_on_plan_name_changed)
        name_row.addWidget(self._sb_plan_name_input, 1)
        plan_layout.addLayout(name_row)

        # Driver notes
        plan_layout.addWidget(QLabel("Driver Notes:", styleSheet=f"color: {_TEXT};"))
        self._sb_driver_notes_input = QTextEdit()
        self._sb_driver_notes_input.setPlaceholderText("Optional notes for this race plan…")
        self._sb_driver_notes_input.setMaximumHeight(80)  # ~4 rows
        self._sb_driver_notes_input.setStyleSheet(
            f"background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #444;")
        plan_layout.addWidget(self._sb_driver_notes_input)

        # Save button
        save_btn_row = QHBoxLayout()
        save_btn_row.addStretch()
        self._sb_btn_save_plan = QPushButton("Save Race Plan")
        self._sb_btn_save_plan.setStyleSheet(
            "background: #2E7D32; color: white; font-weight: bold; padding: 6px 16px;")
        self._sb_btn_save_plan.setEnabled(False)
        self._sb_btn_save_plan.clicked.connect(self._sb_save_race_plan)
        save_btn_row.addWidget(self._sb_btn_save_plan)
        plan_layout.addLayout(save_btn_row)

        return plan_box

    def _build_practice_lap_bank_group(self) -> QGroupBox:
        bank_box = QGroupBox("Session Loader")
        bank_box.setStyleSheet(self._group_style())
        bank_box.setToolTip(
            "Load a past race or practice session.\n"
            "• Load Config — restores car, track and race settings for that session.\n"
            "• Add Laps to Table — imports saved lap times + compound tags for AI analysis.\n"
            "Practice laps are saved automatically — this list updates after every lap."
        )
        bank_layout = QVBoxLayout(bank_box)
        bank_layout.setContentsMargins(8, 8, 8, 8)
        bank_layout.setSpacing(6)

        # Recording status (auto-updated each lap)
        self._lbl_bank_recording = QLabel("")
        self._lbl_bank_recording.setStyleSheet(
            f"color: #8BC34A; font-weight: bold; padding: 2px 0;"
        )
        bank_layout.addWidget(self._lbl_bank_recording)

        # Cascading Track → Car filter
        track_row = QHBoxLayout()
        track_row.addWidget(QLabel("Track:", styleSheet=f"color: {_TEXT};"))
        self._bank_track_combo = QComboBox()
        self._bank_track_combo.setMinimumWidth(220)
        self._bank_track_combo.setToolTip("Filter sessions by track.  'All' shows every saved session.")
        self._bank_track_combo.currentTextChanged.connect(self._on_bank_track_changed)
        track_row.addWidget(self._bank_track_combo, 1)
        track_row.addSpacing(12)
        track_row.addWidget(QLabel("Car:", styleSheet=f"color: {_TEXT};"))
        self._bank_car_combo = QComboBox()
        self._bank_car_combo.setMinimumWidth(220)
        self._bank_car_combo.setToolTip("Filter sessions by car.  'All' shows every car for the selected track.")
        self._bank_car_combo.currentTextChanged.connect(self._refresh_lap_bank)
        track_row.addWidget(self._bank_car_combo, 1)
        bank_layout.addLayout(track_row)

        session_row = QHBoxLayout()
        session_row.addWidget(QLabel("Session:", styleSheet=f"color: {_TEXT};"))
        self._lap_bank_combo = QComboBox()
        self._lap_bank_combo.setMinimumWidth(320)
        self._lap_bank_combo.setToolTip("Matching sessions, newest first.  ★ = same race config as currently selected.")
        session_row.addWidget(self._lap_bank_combo, 1)
        bank_layout.addLayout(session_row)

        btn_row = QHBoxLayout()
        self._btn_bank_load_config = QPushButton("Load Race Config")
        self._btn_bank_load_config.setFixedHeight(26)
        self._btn_bank_load_config.setToolTip(
            "Restore car, track, race type, lap count AND saved car setup from this session.\n"
            "Saves you re-entering settings for the same race setup."
        )
        self._btn_bank_load_config.clicked.connect(self._load_session_config)
        btn_row.addWidget(self._btn_bank_load_config)

        self._btn_bank_add = QPushButton("Add Laps to Table")
        self._btn_bank_add.setFixedHeight(26)
        self._btn_bank_add.setToolTip("Import the session's lap times and compound tags into the Lap Data table below.")
        self._btn_bank_add.clicked.connect(self._import_bank_session)
        btn_row.addWidget(self._btn_bank_add)

        self._btn_bank_clear = QPushButton("Clear Lap Table")
        self._btn_bank_clear.setFixedHeight(26)
        self._btn_bank_clear.setToolTip("Remove all rows from the Lap Data table and reset compound tags.")
        self._btn_bank_clear.clicked.connect(self._clear_lap_table)
        btn_row.addWidget(self._btn_bank_clear)

        btn_row.addStretch()

        self._btn_delete_session = QPushButton("Delete Session")
        self._btn_delete_session.setFixedHeight(26)
        self._btn_delete_session.setStyleSheet(
            "QPushButton { color: #FF9800; border: 1px solid #FF9800; border-radius: 3px; padding: 0 6px; }"
            "QPushButton:hover { background: #3A2000; }"
        )
        self._btn_delete_session.setToolTip(
            "Permanently delete the currently selected session and its lap records.\n"
            "Select a session from the dropdown above first."
        )
        self._btn_delete_session.clicked.connect(self._delete_selected_session)
        btn_row.addWidget(self._btn_delete_session)

        self._btn_wipe_sessions = QPushButton("Wipe All")
        self._btn_wipe_sessions.setFixedHeight(22)
        self._btn_wipe_sessions.setStyleSheet(
            "QPushButton { color: #F44336; border: 1px solid #F44336; border-radius: 3px; padding: 0 4px; font-size: 10px; }"
            "QPushButton:hover { background: #3A1010; }"
        )
        self._btn_wipe_sessions.setToolTip(
            "Permanently delete ALL saved sessions and lap records from the database.\n"
            "Use this to clear old/invalid data and start fresh."
        )
        self._btn_wipe_sessions.clicked.connect(self._wipe_all_sessions)
        btn_row.addWidget(self._btn_wipe_sessions)
        bank_layout.addLayout(btn_row)

        self._lbl_bank_status = QLabel("", styleSheet=f"color: #888;")
        bank_layout.addWidget(self._lbl_bank_status)
        return bank_box

    def _build_tyre_ref_group(self) -> QGroupBox:
        ref_box = QGroupBox("Tyre Reference Paces")
        ref_layout = QVBoxLayout(ref_box)
        ref_layout.addWidget(QLabel(
            "After tagging laps in the Lap Data tab, click  Calculate  to see average "
            "reference pace per compound, then  Apply to Plan  to fill in the stint ref times.",
            styleSheet=f"color: #999;"))

        self._tyre_ref_table = QTableWidget()
        self._tyre_ref_table.setColumnCount(7)
        self._tyre_ref_table.setHorizontalHeaderLabels(
            ["Compound", "Avg Lap", "Best Lap", "Laps", "Opt. Stint (race)", "Total Life (race)", "Degradation"])
        self._tyre_ref_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._tyre_ref_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._tyre_ref_table.setStyleSheet(
            f"QTableWidget {{ background: {_DARK_CARD}; color: {_TEXT}; "
            f"gridline-color: #444; }}"
            f"QHeaderView::section {{ background: #1F4E78; color: white; "
            f"font-weight: bold; padding: 4px; }}"
        )
        self._tyre_ref_table.setMaximumHeight(180)
        ref_layout.addWidget(self._tyre_ref_table)

        ref_btn_row = QHBoxLayout()
        btn_calc_refs = QPushButton("Calculate from Tagged Laps")
        btn_apply_refs = QPushButton("Apply to Plan")
        self._btn_analyse_deg = QPushButton("Analyse Degradation")
        self._btn_analyse_deg.setStyleSheet(
            "background: #4A2E00; color: white; font-weight: bold; padding: 4px 12px;")
        self._btn_analyse_deg.setToolTip(
            "AI finds the performance cliff for each compound from your tagged practice laps.\n"
            "Optimal stint (when pace drops) vs total life will appear in the table.\n"
            "Race Strategy Analysis will use these values instead of generic GT7 estimates.")
        btn_calc_refs.clicked.connect(self._strategy_calc_refs)
        btn_apply_refs.clicked.connect(self._strategy_apply_refs)
        self._btn_analyse_deg.clicked.connect(self._run_analyse_degradation)
        ref_btn_row.addWidget(btn_calc_refs)
        ref_btn_row.addWidget(btn_apply_refs)
        ref_btn_row.addWidget(self._btn_analyse_deg)
        ref_btn_row.addStretch()
        ref_layout.addLayout(ref_btn_row)

        # Pace outlier filter per compound — excludes spins AND worn-out laps
        no_grip_desc = QLabel(
            "Outlier filter — exclude laps slower than compound best by more than this many seconds.  "
            "Removes spin laps (10 s+ off), incidents, and end-of-life worn laps without touching "
            "genuine gradual degradation data.  0 = off (use all laps).")
        no_grip_desc.setStyleSheet("color: #999; font-style: italic;")
        no_grip_desc.setWordWrap(True)
        ref_layout.addWidget(no_grip_desc)

        no_grip_row = QHBoxLayout()
        self._tyre_no_grip_spins: dict[str, QDoubleSpinBox] = {}
        from data.tyres import compound_codes as _cc2
        for _cpd in _cc2():
            _lbl = QLabel(f"{_cpd}:")
            _lbl.setStyleSheet(f"color: {_TEXT};")
            _sb = QDoubleSpinBox()
            _sb.setRange(0.0, 60.0)
            _sb.setSingleStep(1.0)
            _sb.setDecimals(1)
            _sb.setValue(0.0)
            _sb.setSpecialValueText("off")
            _sb.setSuffix(" s")
            _sb.setFixedWidth(90)
            _sb.setToolTip(
                f"Exclude {_cpd} laps where lap time exceeds the compound's best clean lap by this many seconds.\n"
                "A spin on lap 5 (10 s off) → excluded.  A worn-out tyre at the end (5 s off) → excluded.\n"
                "Gradual degradation (1–2 s off) → kept, so the AI sees the real drop-off curve.\n"
                "0 = off (no filter).")
            self._tyre_no_grip_spins[_cpd] = _sb
            no_grip_row.addWidget(_lbl)
            no_grip_row.addWidget(_sb)
        no_grip_row.addStretch()
        ref_layout.addLayout(no_grip_row)
        return ref_box


    def _strategy_add_stint(self, *, preset: dict | None = None) -> None:
        row = self._strategy_stint_table.rowCount()
        self._strategy_stint_table.insertRow(row)

        stint_item = QTableWidgetItem(str(row + 1))
        stint_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._strategy_stint_table.setItem(row, 0, stint_item)

        compound_edit = QLineEdit(preset.get("compound", "Soft") if preset else "Soft")
        compound_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._strategy_stint_table.setCellWidget(row, 1, compound_edit)

        laps_spin = QSpinBox()
        laps_spin.setRange(1, 200)
        laps_spin.setValue(int(preset.get("laps", 10)) if preset else 10)
        self._strategy_stint_table.setCellWidget(row, 2, laps_spin)

        ref_ms = int(preset.get("ref_lap_ms", 0)) if preset else 0
        if ref_ms > 0:
            total_s = ref_ms / 1000.0
            m = int(total_s // 60)
            s = total_s - m * 60
            ref_str = f"{m}:{s:06.3f}"
        else:
            ref_str = ""
        ref_edit = QLineEdit(ref_str)
        ref_edit.setPlaceholderText("M:SS.mmm (blank = session best)")
        ref_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._strategy_stint_table.setCellWidget(row, 3, ref_edit)

        thresh_spin = QDoubleSpinBox()
        thresh_spin.setRange(0.0, 30.0)
        thresh_spin.setSingleStep(0.5)
        thresh_spin.setValue(float(preset.get("pace_threshold_ms", 2000)) / 1000.0
                             if preset else 2.0)
        self._strategy_stint_table.setCellWidget(row, 4, thresh_spin)

        fuel_item = QTableWidgetItem("—")
        fuel_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._strategy_stint_table.setItem(row, 5, fuel_item)

    def _strategy_remove_stint(self) -> None:
        row = self._strategy_stint_table.currentRow()
        if row < 0:
            row = self._strategy_stint_table.rowCount() - 1
        if row >= 0:
            self._strategy_stint_table.removeRow(row)
        # Re-number remaining stints
        for r in range(self._strategy_stint_table.rowCount()):
            item = self._strategy_stint_table.item(r, 0)
            if item:
                item.setText(str(r + 1))

    def _strategy_reset_plan(self) -> None:
        self._strategy_stint_table.setRowCount(0)
        if self._strategy_engine is not None:
            self._strategy_engine.set_plan([])

    def _strategy_apply_plan(self) -> None:
        from strategy.engine import Stint
        stops_data = []
        for row in range(self._strategy_stint_table.rowCount()):
            compound_w = self._strategy_stint_table.cellWidget(row, 1)
            laps_w     = self._strategy_stint_table.cellWidget(row, 2)
            ref_w      = self._strategy_stint_table.cellWidget(row, 3)
            thresh_w   = self._strategy_stint_table.cellWidget(row, 4)
            compound = compound_w.text().strip() if compound_w else "Unknown"
            laps = laps_w.value() if laps_w else 10
            ref_ms = self._parse_ref_lap(ref_w.text().strip() if ref_w else "")
            thresh_ms = int((thresh_w.value() if thresh_w else 2.0) * 1000)
            stops_data.append({
                "laps": laps,
                "compound": compound,
                "ref_lap_ms": ref_ms,
                "pace_threshold_ms": thresh_ms,
            })

        sc = self._config.setdefault("strategy", {})
        sc["stops"] = stops_data
        # track/race_type/laps/duration/tyre_wear/refuel already in sc from active event
        sc["fuel_burn_per_lap"] = self._computed_fuel_burn_lpl()
        self._persist_config()

        if self._strategy_engine is not None:
            stints = [Stint.from_dict(d, i + 1) for i, d in enumerate(stops_data)]
            self._strategy_engine.set_plan(stints)
        self._bridge.event_log_entry.emit(
            f"[Strategy] plan applied: {len(stops_data)} stints")
        # Immediately apply tyre thresholds for the first stint's compound
        if stops_data:
            self._on_tyre_preset_changed(stops_data[0].get("compound", ""))
        self._update_live_plan(stops_data)

    # ------------------------------------------------------------------
    # Save Race Plan helpers
    # ------------------------------------------------------------------

    def _sb_on_plan_name_changed(self, text: str) -> None:
        self._sb_btn_save_plan.setEnabled(bool(text.strip()))

    def _sb_save_race_plan(self) -> None:
        """Persist the current stint plan to the database."""
        from PyQt6.QtWidgets import QMessageBox
        import json as _json

        plan_name = self._sb_plan_name_input.text().strip()
        if not plan_name:
            return

        driver_notes = self._sb_driver_notes_input.toPlainText()

        evt = self._active_event()
        if not evt:
            QMessageBox.warning(self, "No Active Event",
                                "No active event is set. Please activate an event first.")
            return

        event_id = evt.get("id") or self._db.get_event_id(evt.get("name", "")) if self._db else 0
        if not event_id:
            QMessageBox.warning(self, "No Active Event",
                                "Could not resolve active event ID.")
            return

        # Car ID resolution
        car_id = 0
        if self._db is not None:
            car_name = self._config.get("strategy", {}).get("car", "")
            car_id = self._db.get_car_id(car_name) if car_name else 0
        if not car_id:
            QMessageBox.warning(self, "No Active Car",
                                "No active car set. Please start a telemetry session for "
                                "this car before saving a race plan.")
            return

        # Setup ID (best-effort)
        setup_id = None
        setup_name = None

        # Strategy option fields (best-effort)
        strategy_rank = None
        strategy_name = None
        estimated_time_s = None
        ai_summary = None
        ai_risks = None
        ai_positives = None
        ai_negatives = None

        sel_idx = -1
        for i, btn in enumerate(self._ai_apply_btns):
            if btn.isVisible() and i < len(self._strategy_options):
                sel_idx = i
                break
        if sel_idx >= 0 and sel_idx < len(self._strategy_options):
            opt = self._strategy_options[sel_idx]
            strategy_rank = getattr(opt, "rank", None)
            strategy_name = getattr(opt, "name", None)
            estimated_time_s = getattr(opt, "estimated_time_s", None)
            ai_summary = getattr(opt, "summary", None)
            ai_risks = getattr(opt, "risks", None)
            ai_positives = getattr(opt, "positives", None)
            ai_negatives = getattr(opt, "negatives", None)

        # Build stints list from table
        fuel_burn = self._computed_fuel_burn_lpl()
        stints = []
        cumulative_laps = 0
        total_rows = self._strategy_stint_table.rowCount()
        for row in range(total_rows):
            compound_w = self._strategy_stint_table.cellWidget(row, 1)
            laps_w     = self._strategy_stint_table.cellWidget(row, 2)
            ref_w      = self._strategy_stint_table.cellWidget(row, 3)
            thresh_w   = self._strategy_stint_table.cellWidget(row, 4)
            compound = compound_w.text().strip() if compound_w else "Unknown"
            laps = laps_w.value() if laps_w else 10
            ref_ms = self._parse_ref_lap(ref_w.text().strip() if ref_w else "")
            thresh_ms = int((thresh_w.value() if thresh_w else 2.0) * 1000)
            cumulative_laps += laps
            is_last = (row == total_rows - 1)
            stints.append({
                "laps": laps,
                "compound": compound,
                "ref_lap_ms": ref_ms,
                "pace_threshold_ms": thresh_ms,
                "pit_lap": None if is_last else cumulative_laps,
                "target_lap_ms": ref_ms,
                "fuel_target_l": round(laps * fuel_burn, 3),
            })

        stints_json = _json.dumps(stints)

        try:
            self._db.save_race_plan(
                event_id=event_id,
                car_id=car_id,
                setup_id=setup_id,
                plan_name=plan_name,
                stints_json=stints_json,
                strategy_rank=strategy_rank,
                strategy_name=strategy_name,
                estimated_time_s=estimated_time_s,
                ai_summary=ai_summary,
                ai_risks=ai_risks,
                ai_positives=ai_positives,
                ai_negatives=ai_negatives,
                driver_notes=driver_notes,
                setup_name=setup_name,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self._sb_refresh_saved_plans_combo()
        self._bridge.event_log_entry.emit(f"[Strategy] Race plan '{plan_name}' saved.")

    def _sb_refresh_saved_plans_combo(self) -> None:
        """Repopulate the saved plans combo for the active event+car."""
        if not hasattr(self, "_sb_saved_plans_combo"):
            return
        if self._db is None:
            self._sb_saved_plans_combo.clear()
            return

        evt = self._active_event()
        if not evt:
            self._sb_saved_plans_combo.clear()
            return

        event_id = evt.get("id") or self._db.get_event_id(evt.get("name", ""))
        car_name = self._config.get("strategy", {}).get("car", "")
        car_id = self._db.get_car_id(car_name) if car_name else 0
        if not event_id or not car_id:
            self._sb_saved_plans_combo.clear()
            return

        plans = self._db.get_race_plans(event_id, car_id)
        self._sb_saved_plans_combo.blockSignals(True)
        self._sb_saved_plans_combo.clear()
        for plan in plans:
            label = f"{plan['plan_name']} ({plan['created_at'][:10]})"
            self._sb_saved_plans_combo.addItem(label)
            self._sb_saved_plans_combo.setItemData(
                self._sb_saved_plans_combo.count() - 1,
                plan,
            )
        self._sb_saved_plans_combo.blockSignals(False)

    def _sb_on_saved_plan_selected(self, index: int) -> None:
        """Restore driver notes when a saved plan is selected from the combo."""
        if index < 0 or self._sb_saved_plans_combo.count() == 0:
            return
        plan = self._sb_saved_plans_combo.itemData(index)
        if not plan:
            return
        if hasattr(self, "_sb_driver_notes_input"):
            self._sb_driver_notes_input.setPlainText(plan.get("driver_notes", "") or "")

    def _live_init_from_plan(self) -> None:
        """Load the most recent saved race plan for the active event+car into the engine."""
        from strategy.engine import Stint as _Stint
        if self._db is None or self._strategy_engine is None:
            return

        evt = self._active_event()
        if not evt:
            return
        event_id = evt.get("id") or self._db.get_event_id(evt.get("name", ""))
        car_name = self._config.get("strategy", {}).get("car", "")
        car_id = self._db.get_car_id(car_name) if car_name else 0
        if not event_id or not car_id:
            return

        plan = self._db.get_latest_race_plan(event_id, car_id)
        if not plan:
            return

        import json as _json
        try:
            stint_dicts = _json.loads(plan.get("stints_json", "[]"))
        except Exception:
            return

        _STINT_KEYS = {"laps", "compound", "ref_lap_ms", "pace_threshold_ms"}
        stints = [
            _Stint(**{k: v for k, v in d.items() if k in _STINT_KEYS}, stint_num=i + 1)
            for i, d in enumerate(stint_dicts)
        ]
        self._strategy_engine.set_plan(stints)


    @staticmethod
    def _parse_ref_lap(text: str) -> int:
        if not text:
            return 0
        try:
            if ":" in text:
                m_str, s_str = text.split(":", 1)
                return int(round((int(m_str) * 60 + float(s_str)) * 1000))
            else:
                return int(round(float(text) * 1000))
        except (ValueError, TypeError):
            return 0

    def _strategy_calc_refs(self) -> None:
        from statistics import mean as _mean

        def _ms_fmt(ms: float) -> str:
            total_s = ms / 1000.0
            m = int(total_s // 60)
            s = total_s - m * 60
            return f"{m}:{s:06.3f}"

        raw_by_compound: dict[str, list[tuple[int, float]]] = {}
        for row in range(self._lap_table.rowCount()):
            compound     = self._compound_at_row(row)
            laptime_item = self._lap_table.item(row, 3)
            if not compound or laptime_item is None:
                continue
            try:
                lt_ms = float(laptime_item.text())
            except ValueError:
                continue
            if lt_ms > 0:
                raw_by_compound.setdefault(compound, []).append((row, lt_ms))

        self._tyre_ref_table.setRowCount(0)
        for compound, laps_with_idx in sorted(raw_by_compound.items()):
            laps_with_idx.sort(key=lambda x: x[0])
            times_all = [t for _, t in laps_with_idx]

            # Detect stints via >2 s sudden improvement (new tyres / new stint).
            # Skip the first lap of each stint — it is an outlap from the pits
            # and may have an artificially short time if the S/F line is close
            # to the pit exit.
            stints: list[list[float]] = [[times_all[0]]]
            for prev, curr in zip(times_all, times_all[1:]):
                if curr < prev - 2000:
                    stints.append([curr])
                else:
                    stints[-1].append(curr)
            flying: list[float] = []
            for stint in stints:
                flying.extend(stint[1:] if len(stint) > 1 else stint)
            times = flying if flying else times_all

            avg_ms  = _mean(times)
            best_ms = min(times)
            r = self._tyre_ref_table.rowCount()
            self._tyre_ref_table.insertRow(r)
            self._tyre_ref_table.setItem(r, 0, QTableWidgetItem(compound))
            self._tyre_ref_table.setItem(r, 1, QTableWidgetItem(_ms_fmt(avg_ms)))
            self._tyre_ref_table.setItem(r, 2, QTableWidgetItem(_ms_fmt(best_ms)))
            self._tyre_ref_table.setItem(r, 3, QTableWidgetItem(str(len(times))))

            deg = self._tyre_degradation_cache.get(compound)
            method = deg.get("degradation_method", "cliff_detection") if deg else "cliff_detection"
            if deg:
                opt   = str(deg.get("optimal_stint_race", "—"))
                life  = str(deg.get("total_life_race", "—"))
                cliff = deg.get("cliff_lap_practice", 0)
                loss  = deg.get("pace_loss_at_cliff_s", 0.0)
                conf  = deg.get("confidence", "low")
                if method == "relative_baseline":
                    harder_ms = deg.get("harder_baseline_ms")
                    not_yet = deg.get("not_yet_degraded", False)
                    if not_yet:
                        note = f"Degrades vs harder compound baseline · {conf}"
                    elif harder_ms is not None:
                        delta_s = loss if loss else 0.0
                        note = f"Degrades vs harder compound baseline · -{delta_s:.1f}s · {conf}"
                    else:
                        note = f"Degrades vs harder compound baseline · {conf}"
                elif cliff:
                    note = f"Cliff lap {cliff} · -{loss:.1f}s · {conf}"
                else:
                    note = "No cliff detected" if conf != "low" else "Insufficient data"
            else:
                opt  = "—"
                life = "—"
                note = "Run Analyse Degradation"
            self._tyre_ref_table.setItem(r, 4, QTableWidgetItem(opt))
            self._tyre_ref_table.setItem(r, 5, QTableWidgetItem(life))
            cliff_item = QTableWidgetItem(note)
            if deg and method == "relative_baseline":
                harder_ms = deg.get("harder_baseline_ms")
                tip_parts = ["Optimal stint derived from harder-compound baseline comparison."]
                if harder_ms is not None:
                    tip_parts.append(f"Harder compound baseline: {harder_ms / 1000:.3f}s/lap.")
                if loss:
                    tip_parts.append(f"Pace delta vs baseline: -{loss:.1f}s/lap.")
                tip_parts.append(f"Confidence: {conf}.")
                cliff_item.setToolTip("\n".join(tip_parts))
            elif deg and cliff:
                cliff_item.setToolTip(
                    f"Performance cliff occurs at lap {cliff} of the stint.\n"
                    f"Pace loss after cliff: {loss:.1f}s/lap slower than laps 1–{cliff - 1}.\n"
                    f"Confidence: {conf} — pit before lap {cliff} per Opt. Stint."
                )
            self._tyre_ref_table.setItem(r, 6, cliff_item)

    def _strategy_apply_refs(self) -> None:
        refs: dict[str, int] = {}
        for row in range(self._tyre_ref_table.rowCount()):
            c_item = self._tyre_ref_table.item(row, 0)
            r_item = self._tyre_ref_table.item(row, 1)
            if c_item and r_item:
                refs[c_item.text().strip()] = self._parse_ref_lap(r_item.text().strip())

        for row in range(self._strategy_stint_table.rowCount()):
            compound_w = self._strategy_stint_table.cellWidget(row, 1)
            ref_w      = self._strategy_stint_table.cellWidget(row, 3)
            if compound_w is None or ref_w is None:
                continue
            compound = compound_w.text().strip()
            if compound in refs:
                ms = refs[compound]
                total_s = ms / 1000.0
                m = int(total_s // 60)
                s = total_s - m * 60
                ref_w.setText(f"{m}:{s:06.3f}")

    def _refresh_strategy_fuel_column(self) -> None:
        if not hasattr(self, "_strategy_stint_table"):
            return
        avg = (self._tracker.avg_fuel_per_lap
               if self._tracker is not None else 0.0)
        safety = self._config.get("fuel", {}).get("safety_margin_laps", 1.0)
        for row in range(self._strategy_stint_table.rowCount()):
            fuel_item = self._strategy_stint_table.item(row, 5)
            if fuel_item is None:
                continue
            if row == 0:
                fuel_item.setText("Race start")
            else:
                laps_w = self._strategy_stint_table.cellWidget(row, 2)
                laps = laps_w.value() if laps_w else 0
                if avg > 0:
                    fuel_item.setText(f"{math.ceil(avg * (laps + safety))} L")
                else:
                    fuel_item.setText("—")

    def _on_strategy_status(self, status: str) -> None:
        self._lbl_strategy_status.setText(status)

    def _on_tyre_preset_changed(self, compound: str) -> None:
        """Apply tyre temperature thresholds for the given compound.

        Called when the strategy engine starts a new stint (pit exit or race start)
        or when the user manually selects a preset from the Settings tab dropdown.
        """
        key = normalise_compound(compound)
        if not key:
            return
        preset = TYRE_TEMP_PRESETS[key]

        # Apply to tracker immediately (takes effect on next telemetry packet)
        if self._tracker is not None:
            t = TyreThresholds()
            t.cold_max    = preset["cold_max"]
            t.warming_max = preset["warming_max"]
            t.optimal_max = preset["optimal_max"]
            t.hot_max     = preset["hot_max"]
            self._tracker._thresholds = t

        # Update config (in-memory; saved next time user clicks Save Settings)
        tt = self._config.setdefault("tyre_thresholds", {})
        tt.update(preset)
        tt["compound"] = key

        self._bridge.event_log_entry.emit(
            f"[Tyres] thresholds updated for {key}: "
            f"warm={preset['warming_max']}°C  opt={preset['optimal_max']}°C  "
            f"hot={preset['hot_max']}°C"
        )
        self._refresh_live_tyre_label()

    def _get_current_tyre_compound(self) -> str:
        """Return the active fitted compound using priority order:
        1. Active race plan — current (first incomplete) stint compound.
        2. Setup Builder front tyre selection.
        3. 'Not Set' if neither source provides a value.
        """
        # Priority 1: active race plan current stint
        if hasattr(self, "_strategy_engine") and self._strategy_engine is not None:
            try:
                stints = self._strategy_engine.stints()
                active = next((s for s in stints if not s.completed), None)
                if active and active.compound:
                    return active.compound
            except Exception:
                pass
        # Priority 2: Setup Builder front tyre
        if hasattr(self, "_setup_tyre_f"):
            tyre = self._setup_tyre_f.currentText().strip()
            if tyre:
                return tyre
        return "Not Set"


    # ------------------------------------------------------------------
    # Car Setup helpers
    # ------------------------------------------------------------------

    def _populate_car_combo(self, category: str) -> None:
        pass  # car combo removed — car sourced from active event

    def _autofill_car_specs(self, car_name: str) -> None:
        """Populate setup fields and info label from car_specs.json if available."""
        if not car_name:
            return
        from pathlib import Path
        specs_path = Path(__file__).parent.parent / "data" / "car_specs.json"
        try:
            all_specs: dict = json.loads(specs_path.read_text(encoding="utf-8"))
        except Exception:
            return
        specs = all_specs.get(car_name)
        if not specs:
            if hasattr(self, "_lbl_car_specs_info"):
                self._lbl_car_specs_info.setText("")
                self._lbl_car_specs_info.setVisible(False)
            return
        if "drivetrain" in specs and hasattr(self, "_setup_drivetrain"):
            idx = self._setup_drivetrain.findText(specs["drivetrain"])
            if idx >= 0:
                self._setup_drivetrain.setCurrentIndex(idx)
        if "num_gears" in specs and hasattr(self, "_setup_num_gears"):
            self._setup_num_gears.setValue(int(specs["num_gears"]))
        if "power_hp" in specs and hasattr(self, "_setup_actual_bhp"):
            self._setup_actual_bhp.setValue(int(specs["power_hp"]))
        # Build and show a compact info line with stock specs
        if hasattr(self, "_lbl_car_specs_info"):
            parts: list[str] = []
            if specs.get("pp_rating"):   parts.append(f"PP {specs['pp_rating']:.2f}")
            if specs.get("drivetrain"):  parts.append(specs["drivetrain"])
            if specs.get("aspiration"): parts.append(specs["aspiration"])
            if specs.get("power_hp"):   parts.append(f"{specs['power_hp']} hp")
            if specs.get("weight_kg"):  parts.append(f"{specs['weight_kg']} kg")
            if parts:
                self._lbl_car_specs_info.setText(" | ".join(parts))
                self._lbl_car_specs_info.setVisible(True)
            else:
                self._lbl_car_specs_info.setVisible(False)

    def _on_car_detected(self, car_id: int, car_name: str) -> None:
        """Handle auto-detection of car from telemetry — auto-fill specs only."""
        if not car_name:
            return
        self._autofill_car_specs(car_name)
        print(f"[CarDetect] auto-detected: {car_name}")

    def _on_grip_loss_signal(self, score: int, level: str) -> None:
        if not hasattr(self, "_lbl_grip_status"):
            return
        if level == "normal" or score == 0:
            self._lbl_grip_status.setText("")
        elif level == "watch":
            self._lbl_grip_status.setStyleSheet(
                "color: #FFD600; padding: 2px 4px; font-size: 10px;")
            self._lbl_grip_status.setText(f"Grip: Watch — {score}/100")
        elif level == "warning":
            self._lbl_grip_status.setStyleSheet(
                "color: #FF8C00; padding: 2px 4px; font-size: 10px;")
            self._lbl_grip_status.setText(f"Grip: Reduced — brake earlier ({score}/100)")
        elif level == "significant":
            self._lbl_grip_status.setStyleSheet(
                "color: #FF4444; padding: 2px 4px; font-size: 10px;")
            self._lbl_grip_status.setText(f"Grip: Significant loss detected ({score}/100)")

    def _find_car_category(self, car: str) -> str:
        """Return the GT7_CARS_BY_CATEGORY key for *car*, or 'All' if unknown."""
        for cat, cars in GT7_CARS_BY_CATEGORY.items():
            if car in cars:
                return cat
        return "All"

    # ------------------------------------------------------------------
    # BOP helpers
    # ------------------------------------------------------------------

    def _load_bop_json(self) -> dict:
        from pathlib import Path
        p = Path(__file__).parent.parent / "data" / "bop_data.json"
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _on_bop_toggled(self, enabled: bool) -> None:
        gearbox_widgets = (
            list(getattr(self, "_gear_ratio_spins", []))
            + [self._spin_final_drive, self._spin_top_speed, self._btn_reread_gears]
        )
        for w in gearbox_widgets:
            w.setEnabled(not enabled)
        self._lbl_bop_info.setVisible(enabled)
        self._btn_bop_edit.setVisible(enabled)
        self._btn_bop_reload.setVisible(enabled)
        self._bop_info_row_label.setVisible(enabled)
        if enabled:
            self._refresh_bop_label()

    def _refresh_bop_label(self) -> None:
        car = self._config.get("strategy", {}).get("car", "")
        bop = self._load_bop_json()
        found = None
        for _cat, cars in bop.get("cars", {}).items():
            if car in cars:
                found = cars[car]
                break
        if found:
            if "power_pct" in found:
                power_str = f"{found['power_pct']}% power"
            elif "power_hp" in found:
                power_str = f"{found['power_hp']} HP"
            else:
                power_str = "power unknown"
            self._lbl_bop_info.setText(
                f"{found.get('weight_kg', '?')} kg min weight  /  {power_str}"
            )
        elif car:
            self._lbl_bop_info.setText("Car not found in bop_data.json — edit file to add it")
        else:
            self._lbl_bop_info.setText("Select a car to see BOP data")

    def _open_bop_file(self) -> None:
        import os, subprocess
        from pathlib import Path
        p = Path(__file__).parent.parent / "data" / "bop_data.json"
        try:
            os.startfile(str(p))
        except AttributeError:
            subprocess.Popen(["xdg-open", str(p)])

    def _reload_bop_data(self) -> None:
        self._refresh_bop_label()

    def _refresh_data_from_web(self) -> None:
        """Launch background scrape of cars, tracks, and BOP; update UI on completion."""
        import threading as _th
        self._btn_refresh_web.setEnabled(False)
        self._lbl_reload_status.setText("Connecting…")

        def _run() -> None:
            from data.gt7_updater import update_all
            from PyQt6.QtCore import QTimer

            def _progress(msg: str) -> None:
                self._bridge.event_log_entry.emit(f"[DataRefresh] {msg}")
                QTimer.singleShot(0, lambda m=msg: self._lbl_reload_status.setText(m))

            try:
                ok, summary = update_all(
                    bop_path="data/bop_data.json",
                    extra_path="data/gt7_extra.json",
                    progress_cb=_progress,
                )
            except Exception as exc:
                ok, summary = False, f"Refresh error: {exc}"
            QTimer.singleShot(0, lambda: self._on_refresh_done(ok, summary))

        _th.Thread(target=_run, daemon=True).start()

    def _on_refresh_done(self, ok: bool, summary: str) -> None:
        """Called on the Qt main thread after the web scrape completes."""
        self._btn_refresh_web.setEnabled(True)
        self._lbl_reload_status.setText(summary)

        # Merge gt7_extra.json into live module globals and refresh combos
        from ui.gt7_data import reload_extra, GT7_TRACKS, GT7_TRACK_INFO, GT7_CARS
        reload_extra()

        # Reload BOP label if BOP mode is active (Phase 5: EventContext, DB-first)
        if self._build_event_context().bop_enabled:
            self._refresh_bop_label()

    def _open_extra_json(self) -> None:
        import os, subprocess
        from pathlib import Path
        p = Path("data/gt7_extra.json").resolve()
        if os.name == "nt":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _get_bop_data_for_car(self) -> dict | None:
        """Return BOP dict for the currently selected car, or None if BOP not active.

        Phase 5: BoP flag + car from the canonical EventContext (DB-first) —
        byte-identical in sync, consistent with the setup-permission gating.
        """
        ev_ctx = self._build_event_context()
        if not ev_ctx.bop_enabled:
            return None
        car = ev_ctx.car
        bop = self._load_bop_json()
        for _cat, cars in bop.get("cars", {}).items():
            if car in cars:
                return cars[car]
        return None

    def _update_lsd_visibility(self) -> None:
        is_awd = self._setup_drivetrain.currentText() == "AWD"
        self._lbl_lsd_front.setVisible(is_awd)
        self._lsd_front_widget.setVisible(is_awd)

    def _run_feeling_advice(self) -> None:
        if self._driving_advisor is None:
            self._setup_result_text.setPlainText("Driving advisor not available.")
            return
        feeling = self._setup_feeling_input.toPlainText().strip()
        if not feeling:
            self._setup_result_text.setPlainText(
                "Describe how the car feels first, then click Ask AI for Fix.")
            return
        d = self._current_setup_dict()
        _car_name, _car_specs = self._load_car_specs_for_current()
        self._setup_result_text.setPlainText("Analysing handling issue… please wait.")
        self._btn_setup_feeling.setEnabled(False)
        import threading as _threading

        def _worker():
            try:
                resp = self._driving_advisor.build_driver_feeling_response(
                    feeling, d, car_name=_car_name, car_specs=_car_specs)
                self._setup_result_queue.put(("ok", resp, "feeling_fix", feeling))
            except Exception as exc:
                self._setup_result_queue.put(("error", str(exc), "feeling_fix", feeling))

        _threading.Thread(target=_worker, daemon=True).start()

    def _run_analyse_degradation(self) -> None:
        """Compute the tyre degradation cliff for each tagged compound (deterministic)."""
        import threading as _threading
        from strategy.tyre_degradation import analyse_tyre_degradation
        from statistics import mean as _mean

        # Build per-compound sequences from the lap table.
        # Use table row index (not lap_no from column 0) as the ordering key —
        # lap_no resets to 1 at each session boundary, so sorting by it
        # interleaves practice and race laps when both use the same compound.
        raw: dict[str, list[tuple[int, float]]] = {}
        for row in range(self._lap_table.rowCount()):
            compound     = self._compound_at_row(row)
            laptime_item = self._lap_table.item(row, 3)
            if not (compound and laptime_item):
                continue
            try:
                lt_ms = float(laptime_item.text())
            except ValueError:
                continue
            if lt_ms > 0:
                raw.setdefault(compound, []).append((row, lt_ms))

        # Sort each compound by lap number, detect stint resets (>2s sudden improvement),
        # use the longest consecutive sequence
        lap_sequences: dict[str, list[float]] = {}
        for compound, laps in raw.items():
            laps.sort(key=lambda x: x[0])
            times = [t for _, t in laps]
            if len(times) < 2:
                lap_sequences[compound] = times
                continue
            # Split into stints on sudden improvement
            stints: list[list[float]] = [[times[0]]]
            for prev, curr in zip(times, times[1:]):
                if curr < prev - 2000:   # >2s faster = new tyres
                    stints.append([curr])
                else:
                    stints[-1].append(curr)
            longest = max(stints, key=len)
            lap_sequences[compound] = longest[1:] if len(longest) > 1 else longest

        if not lap_sequences:
            return

        # Apply per-compound pace outlier filter — removes spin laps and worn-out laps
        if hasattr(self, "_tyre_no_grip_spins"):
            for _cpd, _sb in self._tyre_no_grip_spins.items():
                threshold_s = _sb.value()
                if threshold_s > 0.0 and _cpd in lap_sequences:
                    seq = lap_sequences[_cpd]
                    if seq:
                        best_ms = min(seq)
                        cutoff_ms = best_ms + threshold_s * 1000.0
                        filtered = [t for t in seq if t <= cutoff_ms]
                        if filtered:
                            lap_sequences[_cpd] = filtered

        # Require at least 5 laps per compound (after outlap exclusion) to
        # prevent a single slow outlier lap from being misread as a cliff.
        lap_sequences = {c: s for c, s in lap_sequences.items() if len(s) >= 5}
        if not lap_sequences:
            if hasattr(self, "_btn_analyse_deg"):
                self._btn_analyse_deg.setEnabled(True)
                self._btn_analyse_deg.setText("Analyse Degradation")
            print("[Degradation] Need 5+ representative laps per compound to analyse.")
            return

        # Phase 5: degradation parameters from the canonical contexts —
        # tyre wear is event truth (EventContext, DB-first), the consecutive-lap
        # window is strategy-plan state (StrategyContext). Byte-identical
        # defaults (1.0 / 2). Read on the UI thread before the worker spawns.
        wear_mult = float(self._build_event_context().tyre_wear_multiplier)
        consecutive_laps = int(self._build_strategy_context().degradation_consecutive_laps)

        if hasattr(self, "_btn_analyse_deg"):
            self._btn_analyse_deg.setEnabled(False)
            self._btn_analyse_deg.setText("Analysing…")

        def _worker():
            try:
                result = analyse_tyre_degradation(lap_sequences, wear_mult,
                                                  consecutive_laps=consecutive_laps)
                self._degradation_result_queue.put(("ok", result))
            except Exception as exc:
                self._degradation_result_queue.put(("err", str(exc)))

        _threading.Thread(target=_worker, daemon=True).start()

    def _display_degradation_result(self, result: tuple) -> None:
        if hasattr(self, "_btn_analyse_deg"):
            self._btn_analyse_deg.setEnabled(True)
            self._btn_analyse_deg.setText("Analyse Degradation")
        status, payload = result
        if status == "err":
            print(f"[Degradation] analysis failed: {payload}")
            return
        self._tyre_degradation_cache = payload
        if self._strategy_engine is not None:
            self._strategy_engine.set_degradation_cache(payload)
        self._strategy_calc_refs()   # redraw table with new columns

    # ------------------------------------------------------------------
    # Driver Profile methods
    # ------------------------------------------------------------------

    def _run_refresh_stats(self) -> None:
        if self._db is None:
            self._lbl_profile_stats.setText("No session database available.")
            return
        from strategy.profile_updater import save_stats_doc
        try:
            text = save_stats_doc(self._db)
        except Exception as e:
            self._lbl_profile_stats.setText(f"Failed to generate stats: {e}")
            return
        if not text:
            self._lbl_profile_stats.setText("No sessions recorded yet — drive some laps first.")
            return
        # Show a brief summary on the label
        import re
        m = re.search(r"\*\*Total laps:\*\* (\d+)", text)
        m2 = re.search(r"\*\*Sessions:\*\* (\d+)", text)
        laps = m.group(1) if m else "?"
        sess = m2.group(1) if m2 else "?"
        self._lbl_profile_stats.setText(f"Stats updated — {laps} laps across {sess} sessions.")

    def _display_profile_update_result(self, result: tuple) -> None:
        status, payload = result
        if status == "err":
            self._lbl_profile_stats.setText(f"Update failed: {payload}")
            return
        self._profile_proposal_text.setPlainText(payload)
        self._profile_proposal_text.setVisible(True)
        self._profile_action_row.setVisible(True)
        self._lbl_profile_stats.setText("Review proposed changes below, then Apply or Discard.")

    def _apply_profile_update(self) -> None:
        from strategy.profile_updater import apply_profile_update
        new_part2 = self._profile_proposal_text.toPlainText()
        try:
            apply_profile_update(new_part2)
        except Exception as e:
            self._lbl_profile_stats.setText(f"Failed to apply: {e}")
            return
        self._profile_proposal_text.setVisible(False)
        self._profile_action_row.setVisible(False)
        self._profile_proposal_text.clear()
        self._lbl_profile_stats.setText("Profile updated. All AI calls now use the new profile.")

    def _discard_profile_update(self) -> None:
        self._profile_proposal_text.setVisible(False)
        self._profile_action_row.setVisible(False)
        self._profile_proposal_text.clear()
        self._lbl_profile_stats.setText("Changes discarded.")

    # ------------------------------------------------------------------

    def _refresh_gear_ratios(self) -> None:
        """Fill gear spinboxes from telemetry on first valid packet only."""
        if self._gear_ratios_captured or not hasattr(self, "_gear_ratio_spins"):
            return
        p = self._last_packet
        if p is None:
            return
        ratios = p.gear_ratios
        any_valid = any(r is not None and r > 0.0 for r in ratios)
        if not any_valid:
            return
        for i, spin in enumerate(self._gear_ratio_spins):
            if i < len(ratios) and ratios[i] is not None and ratios[i] > 0.0:
                spin.setValue(ratios[i])
        if hasattr(self, "_spin_top_speed"):
            ms = p.transmission_max_speed_kmh
            if ms >= 50:  # < 50 km/h is a raw-field artefact, not a valid GT7 top speed
                self._spin_top_speed.setValue(ms)
        self._gear_ratios_captured = True

    def _reread_gear_ratios(self) -> None:
        """Force a fresh telemetry capture on the next packet."""
        self._gear_ratios_captured = False

    # ------------------------------------------------------------------
    # Push-to-talk helpers
    # ------------------------------------------------------------------


    def _find_track_idx(self, combo: "QComboBox", canonical: str) -> int:
        """Return the combo index whose item data matches canonical, or -1."""
        for i in range(combo.count()):
            if combo.itemData(i) == canonical:
                return i
        return -1

    def _track_val(self, combo: "QComboBox") -> str:
        """Return the canonical track name from an annotated track combo.

        When an item from the dropdown is selected, itemData holds the clean
        canonical name.  When the user has typed a custom value, fall back to
        the raw text (so free-text tracks still work).
        """
        data = combo.currentData()
        if data is not None:
            return str(data)
        return combo.currentText().strip()

    def _populate_microphones(self) -> None:
        try:
            from voice.query_listener import QueryListener as _QL
            for idx, name in _QL.list_microphones():
                self._combo_microphone.addItem(f"[{idx}] {name}", idx)
        except Exception:
            pass

    def _populate_output_devices(self) -> None:
        try:
            import sounddevice as _sd
            all_devs = _sd.query_devices()
            default_out = _sd.default.device[1]
            for i, d in enumerate(all_devs):
                if d.get("max_output_channels", 0) > 0:
                    marker = " *" if i == default_out else ""
                    self._combo_beep_device.addItem(f"[{i}] {d['name']}{marker}", i)
        except Exception:
            pass

    def _on_ptt_status(self, status: str) -> None:
        if not hasattr(self, "_ptt_status_lbl"):
            return
        _styles = {
            "RADIO READY":          ("color: #2EA043; background: #0D1B10; border-color: #2EA043;"),
            "TRANSMITTING":         ("color: #F5A623; background: #2A1800; border-color: #F5A623;"),
            "PROCESSING":           ("color: #F5C542; background: #1A1800; border-color: #F5C542;"),
            "ENGINEER RESPONDING":  ("color: #4FC3F7; background: #001A2A; border-color: #4FC3F7;"),
        }
        base = "border: 1px solid; border-radius: 3px; padding: 3px 10px; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        style = _styles.get(status, _styles["RADIO READY"])
        self._ptt_status_lbl.setStyleSheet(f"{style} {base}")
        self._ptt_status_lbl.setText(status)
        if hasattr(self, "_live_ptt_status_lbl"):
            self._live_ptt_status_lbl.setStyleSheet(f"{style} {base}")
            self._live_ptt_status_lbl.setText(status)




    def _on_find_mic(self) -> None:
        """Scan all input devices and auto-select the one that produces audio."""
        self._btn_find_mic.setEnabled(False)
        self._lbl_mic_rms.setText("scanning…")
        self._lbl_mic_rms.setStyleSheet("color: #F5C542;")

        def _run():
            found_idx: Optional[int] = None
            found_name = ""
            found_rms  = 0.0
            try:
                from voice.query_listener import _sd, _np, _RECORD_SAMPLE_RATE
                devices = _sd.query_devices()
                for i, d in enumerate(devices):
                    if d.get("max_input_channels", 0) <= 0:
                        continue
                    try:
                        r = _sd.rec(int(0.3 * _RECORD_SAMPLE_RATE),
                                    samplerate=_RECORD_SAMPLE_RATE,
                                    channels=1, dtype="int16", device=i)
                        _sd.wait()
                        flat = r.flatten().astype(_np.float32)
                        rms  = float(_np.sqrt(_np.mean(flat ** 2)))
                        print(f"[FindMic] [{i}] {d['name']}  RMS={rms:.0f}")
                        if rms > 50 and rms > found_rms:
                            found_idx  = i
                            found_name = d["name"]
                            found_rms  = rms
                            break  # take first device that produces audio
                    except Exception:
                        continue
            except Exception as e:
                print(f"[FindMic] scan error: {e}")

            if found_idx is not None:
                result = f"[{found_idx}] {found_name}  RMS {found_rms:.0f} — selected"
                colour = "#2EA043"
            else:
                result = "No active mic found — speak while scanning"
                colour = "#C0392B"

            from PyQt6.QtCore import QTimer
            def _apply():
                self._btn_find_mic.setEnabled(True)
                self._lbl_mic_rms.setText(result)
                self._lbl_mic_rms.setStyleSheet(f"color: {colour};")
                if found_idx is not None:
                    for j in range(self._combo_microphone.count()):
                        if self._combo_microphone.itemData(j) == found_idx:
                            self._combo_microphone.setCurrentIndex(j)
                            break
                    self._config.setdefault("query", {})["mic_index"] = found_idx
            QTimer.singleShot(0, _apply)

        threading.Thread(target=_run, daemon=True).start()

    def _export_excel(self) -> None:
        records = self._logger.records()
        if not records:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Lap Data", "gt7_session.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not path:
            return

        def _do_export():
            try:
                export_to_excel(records, path, "GT7 Session")
            except Exception as e:
                print(f"Export error: {e}")

        t = threading.Thread(target=_do_export, daemon=True)
        t.start()

    def _clear_laps(self) -> None:
        self._logger.clear()
        self._lap_table.setRowCount(0)
        self._lbl_lap_count.setText("No laps recorded")

    def _persist_config(self) -> None:
        """Write self._config to disk. Called from all save sites.

        Delegates to config_paths.save_config: atomic (temp-file + os.replace),
        keeps a .bak backup, and is guarded so that under tests it refuses to
        overwrite the user's real config.json (raises ConfigSafetyError, caught
        and logged here so construction/saves never crash). Normal app runs are
        unaffected — they write the real config exactly as before.
        """
        from config_paths import save_config, ConfigSafetyError
        try:
            save_config(self._config_path, self._config, backup=True)
        except ConfigSafetyError as e:
            print(f"[Config] BLOCKED real-config write under tests: {e}")
        except Exception as e:
            print(f"[Config] save error: {e}")




    # Curated natural (Piper) voices offered by the in-app downloader.



    # ------------------------------------------------------------------ wiring

    def _connect_signals(self) -> None:
        self._bridge.lap_completed.connect(self.on_lap_completed)
        self._bridge.lap_completed.connect(lambda _: self._refresh_lap_bank())
        self._bridge.lap_completed.connect(lambda _: self._auto_refresh_gearbox_debug())
        self._bridge.connection_changed.connect(self.on_connection_status)
        self._bridge.race_state_changed.connect(self.on_race_state)
        self._bridge.event_log_entry.connect(self.on_event_log)
        self._bridge.strategy_status_changed.connect(self._on_strategy_status)
        self._bridge.tyre_preset_changed.connect(self._on_tyre_preset_changed)
        self._bridge.car_detected.connect(self._on_car_detected)
        self._bridge.grip_loss_detected.connect(self._on_grip_loss_signal)
        self._bridge.calibration_packet.connect(self._tm_on_calibration_packet)
        self._tm_btn_start_cal.clicked.connect(self._tm_start_session)
        self._tm_btn_stop_cal.clicked.connect(self._tm_stop_session)
        self._tm_btn_build_path.clicked.connect(self._tm_build_path)
        self._tm_btn_save_path.clicked.connect(self._tm_save_path)
        self._tm_btn_detect_segs.clicked.connect(self._tm_detect_segments)
        # AI Corner Verify (Group 20A)
        self._tm_btn_ai_corner_verify.clicked.connect(self._tm_run_ai_corner_verify)
        self._tm_ai_corner_verify_signal.connect(self._tm_ai_corner_verify_done)
        # Segment diagnostics (Group 17F)
        self._tm_seg_table.cellClicked.connect(self._tm_on_seg_selected)
        # Track model alignment (Group 17P)
        self._tm_btn_accept.clicked.connect(self._tm_accept_track_model)
        self._tm_btn_rebuild.clicked.connect(self._tm_rebuild_model)
        # Lap offset calibration (Group 17M)
        self._tm_btn_create_zero_offset.clicked.connect(self._tm_create_zero_offset)
        self._tm_btn_load_offset.clicked.connect(self._tm_load_offset)
        self._tm_btn_save_offset.clicked.connect(self._tm_save_offset)
        # Seed Geometry (Group 17V)
        self._tm_btn_generate_seed.clicked.connect(self._tm_generate_seed_geometry)
        self._tm_btn_save_seed.clicked.connect(self._tm_save_seed_geometry)
        self._tm_btn_reload_seed.clicked.connect(self._tm_reload_seed_geometry)

    def update_debug_stats(self, rate: float, total: int, errors: int,
                           hex_dump: str) -> None:
        self._lbl_pkt_rate.setText(f"Rate: {rate:.1f} Hz")
        self._lbl_pkt_total.setText(f"Pkts: {total:,}")
        self._lbl_pkt_errors.setText(f"Errors: {errors}")

        # ── Tracker state ────────────────────────────────────────────────
        if self._tracker is not None:
            tr = self._tracker
            rem_comp = tr.computed_remaining_ms()
            if rem_comp >= 0:
                rem_str = f"{rem_comp // 60000}:{(rem_comp % 60000) // 1000:02d}"
            else:
                rem_str = "—"
            self._lbl_dbg_phase.setText(f"Phase: {tr.phase.value}")
            self._lbl_dbg_race_type.setText(f"RaceType: {tr.race_type.value}")
            self._lbl_dbg_session.setText(f"Session: {tr.session_type.value}")
            self._lbl_dbg_laps.setText(f"Laps: {tr.laps_recorded}/{tr.laps_in_race}")
            self._lbl_dbg_rem_comp.setText(f"Time left: {rem_str}")

        # ── Raw packet fields ────────────────────────────────────────────
        p = self._last_packet
        if p is not None:
            self._lbl_dbg_cars_raw.setText(f"cars_in_race: {p.cars_in_race}")
            self._lbl_dbg_laps_raw.setText(f"laps_in_race: {p.laps_in_race}")
            self._lbl_dbg_rem_raw.setText(f"remaining_time_ms: {p.remaining_time_ms}")
            self._lbl_dbg_ontrack.setText(f"on_track: {p.car_on_track}")
            self._lbl_dbg_loading.setText(f"loading: {p.loading}")
            self._lbl_dbg_pos_raw.setText(f"pos: {p.current_position}/{p.cars_in_race}")

        # ── Announcer state ──────────────────────────────────────────────
        if self._announcer is not None:
            q = self._announcer.queue_depth
            mu = self._announcer.muted_until
            mute_str = f"{mu - time.time():.1f}s" if mu > time.time() else "No"
            self._lbl_dbg_ann_q.setText(f"Voice queue: {q}")
            self._lbl_dbg_ann_mute.setText(f"Muted: {mute_str}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._refresh_timer.stop()
        event.accept()

    # ------------------------------------------------------------------ theme / style

    def _apply_dark_theme(self) -> None:
        # NGR Enterprise pit-wall theme. The QPalette gives Fusion a cinematic
        # charcoal base; the additive global stylesheet (ui/ngr_theme.app_stylesheet)
        # then lifts the chrome that would otherwise render as generic default
        # widgets — the top tab bar, buttons, inputs, tables, scrollbars, tooltips
        # and status bar. It styles specific widget classes only (no blanket
        # QWidget rule), so the app's existing inline stylesheets always win for
        # their own widgets and nothing that already worked can change.
        from ui import ngr_theme as _ngr
        app = QApplication.instance()
        app.setStyle("Fusion")
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window,          QColor(_ngr.CARBON))
        pal.setColor(QPalette.ColorRole.WindowText,      QColor(_ngr.TEXT))
        pal.setColor(QPalette.ColorRole.Base,            QColor(_ngr.CARBON_RAISED))
        pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(_ngr.CARBON))
        pal.setColor(QPalette.ColorRole.ToolTipBase,     QColor(_ngr.INK_BLACK))
        pal.setColor(QPalette.ColorRole.ToolTipText,     QColor(_ngr.TEXT_HI))
        pal.setColor(QPalette.ColorRole.Text,            QColor(_ngr.TEXT))
        pal.setColor(QPalette.ColorRole.Button,          QColor(_ngr.CARBON_HI))
        pal.setColor(QPalette.ColorRole.ButtonText,      QColor(_ngr.TEXT))
        pal.setColor(QPalette.ColorRole.Highlight,       QColor(_ngr.NGR_GREEN_DIM))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_ngr.TEXT_HI))
        app.setPalette(pal)
        try:
            app.setStyleSheet(_ngr.app_stylesheet())
        except Exception as e:  # pragma: no cover - never block startup on styling
            logging.warning("NGR global stylesheet not applied: %s", e)

    @staticmethod
    def _group_style() -> str:
        return (
            f"QGroupBox {{ color: #AAAAAA; border: 1px solid #444; "
            f"border-radius: 6px; margin-top: 8px; padding-top: 4px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
        )

    @staticmethod
    def _make_dspin(val: float, lo: float = 0.0, hi: float = 200.0) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(1)
        s.setValue(val)
        return s

    @staticmethod
    def _make_slider(lo: int, hi: int, val: int, unit: str) -> tuple[QSlider, QWidget]:
        row = QWidget()
        hl  = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(val)
        lbl = QLabel(f"{val} {unit}")
        lbl.setMinimumWidth(60)
        slider.valueChanged.connect(lambda v: lbl.setText(f"{v} {unit}"))
        hl.addWidget(slider)
        hl.addWidget(lbl)
        return slider, row

    # -----------------------------------------------------------------------
    # Tab-change handler
    # -----------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        # Tab Navigation Refactor (2026-07-03): dispatch by stable tab KEY, not
        # raw numeric index — the registry mirrors the addTab creation order,
        # so reordering tabs later only means updating DEFAULT_TAB_ORDER in
        # ui/tab_registry.py alongside the addTab calls. Per-tab behaviour on
        # activation is unchanged from the index-based dispatch it replaces.
        reg = getattr(self, "_tab_registry", None)
        key = reg.key_at(index) if reg is not None else None
        if key == TAB_HISTORY:            self._refresh_history()
        elif key == TAB_LIVE:             self._refresh_running_setup_combos()
        elif key == TAB_SETUP_BUILDER:    self._sync_setup_builder_from_event()
        elif key == TAB_STRATEGY_BUILDER:
            self._sync_strategy_from_event()
            # Group 51: refresh the read-only Race Plan session selector + readiness.
            if hasattr(self, "_rp_session_combo"):
                self._populate_race_plan_sessions()
            # UAT: keep the Race Plan pit-loss field seeded from config (was stuck at 0).
            self._sync_race_plan_pit_loss()
        elif key == TAB_PRACTICE_REVIEW:  self._sync_practice_from_event()
        elif key == TAB_TELEMETRY:        self._refresh_telemetry_context()
        elif key == TAB_TRACK_MODELLING:  self._tm_on_tab_shown()
        elif key == TAB_HOME:             self._home_refresh()

    # -----------------------------------------------------------------------
    # Event-centred sync methods (called from _on_tab_changed)
    # -----------------------------------------------------------------------

    def _sync_strategy_from_event(self) -> None:
        try:
            evt = self._active_event()
            if not evt:
                if hasattr(self, "_lbl_strategy_event_ctx"):
                    # Working Race Config sprint: the no-event missing checks
                    # read the named working-config model (same bridge source;
                    # falsiness semantics identical to the raw dict reads).
                    wrc = self._working_race_config()
                    missing = []
                    if not wrc.track:
                        missing.append("✗ No track — set in Event Planner")
                    if not wrc.car:
                        missing.append("✗ No car — select from Garage")
                    msg = ("No active event — set one in Event Planner first."
                           + ("\n" + "\n".join(missing) if missing else ""))
                    self._lbl_strategy_event_ctx.setText(msg)
                return
            # Legacy Fan-Out Removal Phase 2 (display labels only): this context
            # line reflects the canonical EventContext (DB-event-first — matching
            # the strategy AI inputs since the AI Snapshot Migration). int()
            # preserves the integer QSpinBox formatting so the line is
            # byte-identical when the DB event and config["strategy"] are in sync.
            # _update_race_config() (writer) below is unchanged.
            ev_ctx = self._build_event_context()
            name  = evt.get("name", "?")
            track = ev_ctx.track or "?"
            car   = ev_ctx.car or "—"
            rt    = ev_ctx.race_type
            if rt == "timed":
                length_str = f"{int(ev_ctx.race_duration_minutes)} min"
            else:
                length_str = f"{int(ev_ctx.laps)} laps"
            tw   = int(ev_ctx.tyre_wear_multiplier)
            fm   = int(ev_ctx.fuel_multiplier)
            rfl  = int(ev_ctx.refuel_rate_lps)
            cpds = self._get_mandatory_compounds()
            cpd_str = f"  |  Required: {', '.join(cpds)}" if cpds else ""
            missing = []
            if not track or track == "?":
                missing.append("✗ No track — set in Event Planner")
            if not car or car == "—":
                missing.append("✗ No car — select from Garage")
            ctx = (f"Event: {name}  |  Track: {track}  |  Car: {car}  |  "
                   f"{length_str}  |  Wear: {tw}×  |  Fuel: {fm}×  |  Refuel: {rfl} L/s{cpd_str}")
            if missing:
                ctx += "\n" + "\n".join(missing)
            if hasattr(self, "_lbl_strategy_event_ctx"):
                self._lbl_strategy_event_ctx.setText(ctx)
            if hasattr(self, "_lbl_fuel_mult_display"):
                self._lbl_fuel_mult_display.setText(f"×{int(fm)} (from Event)")
            self._update_race_config()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # "Setup running this stint" — declared in Live practice, editable in
    # Practice Review, passed to the AI with driver feedback (no schema change).
    # -----------------------------------------------------------------------

    def _running_setup_label_for(self, s: dict) -> str:
        """Concise, stable label for a saved-setup dict used by the running-setup combos."""
        lbl = s.get("setup_label") or "Setup"
        st = s.get("setup_type") or s.get("session") or ""
        return f"{lbl} [{st}]" if st else lbl

    def _refresh_running_setup_combos(self) -> None:
        """Repopulate both running-setup combos from saved setups, preserving the
        declared selection (``_live_running_setup``). Safe to call before either
        combo exists."""
        labels = [self._running_setup_label_for(s) for s in getattr(self, "_saved_setups", [])]
        current = getattr(self, "_live_running_setup", "") or ""
        for combo in (getattr(self, "_live_running_setup_combo", None),
                      getattr(self, "_prac_running_setup_combo", None)):
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— none —")
            for lbl in labels:
                combo.addItem(lbl)
            idx = combo.findText(current) if current else -1
            combo.setCurrentIndex(idx if idx > 0 else 0)
            combo.blockSignals(False)

    def _on_running_setup_changed(self, text: str) -> None:
        """Store the declared running setup and keep both combos in sync."""
        self._live_running_setup = "" if (not text or text == "— none —") else text
        self._refresh_running_setup_combos()

    # ------------------------------------------------------------------ #
    # UAT Finding 1 — canonical applied-setup authority integration.
    # ------------------------------------------------------------------ #

    def _current_setup_identity(self):
        """The (car, track, layout) identity of the current session/event."""
        from data.setup_state_authority import SetupIdentity
        try:
            ev = self._build_event_context()
            return SetupIdentity(
                car=str(getattr(ev, "car", "") or ""),
                track=str(getattr(ev, "track", "") or ""),
                layout_id=str(getattr(ev, "layout_id", "") or ""),
            )
        except Exception:
            return SetupIdentity()

    def _active_setup_for_current(self, purpose: str = "Race"):
        """The canonical active applied setup for this session, or None.

        Prefers the requested purpose, then the other, so the Live baseline is
        populated whichever discipline was last applied for this car/track."""
        auth = getattr(self, "_setup_authority", None)
        if auth is None:
            return None
        ident = self._current_setup_identity()
        other = "Qualifying" if purpose == "Race" else "Race"
        return auth.active_setup(ident, purpose) or auth.active_setup(ident, other)

    def _refresh_active_setup_display(self) -> None:
        """Render the Live baseline (canonical active setup) honestly, kept
        visibly separate from the manual running-setup override combo."""
        lbl = getattr(self, "_live_active_setup_lbl", None)
        auth = getattr(self, "_setup_authority", None)
        if lbl is None or auth is None:
            return
        ident = self._current_setup_identity()
        active = self._active_setup_for_current("Race")
        if active is not None:
            at = f" · applied {active.applied_at}" if active.applied_at else ""
            lbl.setText(
                f"Live baseline: {active.name} · rev {active.revision} "
                f"[{active.purpose}]{at}")
            lbl.setStyleSheet("color:#8BC34A; font-size:10px; padding:2px 0;")
            return
        gate = auth.analysis_gate(ident, "Race")
        if gate.reason.name == "IDENTITY_MISMATCH" and gate.active is not None:
            lbl.setText(
                "Live baseline: none for this car/track — the applied setup "
                f"“{gate.active.name}” is for a different session.")
        else:
            lbl.setText(
                "Live baseline: none applied yet — apply a setup in game "
                "to set the Live Race Engineer baseline.")
        lbl.setStyleSheet("color:#F0C070; font-size:10px; padding:2px 0;")

    def _sync_practice_from_event(self) -> None:
        # Keep the "setup run this stint" selector current with saved setups +
        # whatever was declared live.
        self._refresh_running_setup_combos()
        try:
            evt = self._active_event()
            if not evt:
                return
            # Phase 1: read the car from the canonical EventContext (car is
            # sourced strategy-first there, so byte-identical to the raw read)
            # instead of reaching into config["strategy"].
            car   = self._build_event_context().car
            track = evt.get("track", "")
            if car and hasattr(self, "_bank_car_combo"):
                idx = self._bank_car_combo.findText(car)
                if idx >= 0:
                    self._bank_car_combo.setCurrentIndex(idx)
            if track and hasattr(self, "_bank_track_combo"):
                idx = self._bank_track_combo.findText(track)
                if idx >= 0:
                    self._bank_track_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _refresh_telemetry_context(self) -> None:
        try:
            if not hasattr(self, "_telem_lbl_event"):
                return
            evt = self._active_event()
            # State Consolidation 1: read event/car/track from the canonical
            # EventContext read model instead of reaching into config["strategy"].
            ctx = self._build_event_context()
            self._telem_lbl_event.setText(
                (ctx.event_name or "None — set in Event Planner") if evt else "—"
            )
            self._telem_lbl_car.setText(ctx.car or "—")
            self._telem_lbl_track.setText((ctx.track or "—") if evt else "—")
            # SessionContext sprint: connection / packet / recording / telemetry
            # fuel now come from the canonical SessionContext read model instead
            # of reaching into tracker internals. Byte-identical labels.
            sctx = self._build_session_context()
            self._telem_lbl_connection.setText(sctx.connection_text())
            self._telem_lbl_packets.setText(str(sctx.packet_count))
            self._telem_lbl_recording.setText(sctx.recording_text())
            if hasattr(self, "_lbl_fuel_burn_display"):
                if sctx.telemetry_avg_fuel_per_lap > 0:
                    self._lbl_fuel_burn_display.setText(
                        f"{sctx.telemetry_avg_fuel_per_lap:.2f} L/lap (from telemetry)")
            self._update_telemetry_labels()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # New tab build methods — 9-tab spec layout (REQUIREMENTS.md §12)
    # -----------------------------------------------------------------------

    def _build_strategy_builder_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(self._build_workflow_guide_group())
        layout.addWidget(self._build_race_plan_group())
        layout.addWidget(self._build_ai_analysis_group())
        layout.addWidget(self._build_stint_plan_group())
        layout.addWidget(self._build_tyre_ref_group())
        layout.addStretch()

        self._update_race_config()

        scroll.setWidget(container)
        return scroll

    def _build_practice_review_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(self._tab_intro_header(
            "Practice Review",
            "Review your practice laps, tag which setup and compound you ran per "
            "lap, analyse tyre degradation, and log how each stint felt. "
            "Next: tag your laps, click Analyse Degradation, then submit "
            "Driver Feedback after the stint."))

        summary_group = QGroupBox("Session Summary")
        summary_group.setStyleSheet(self._group_style())
        summary_h = QHBoxLayout(summary_group)
        self._lbl_pr_best = QLabel("—")
        self._lbl_pr_best.setStyleSheet(f"color: {_TEXT};")
        self._lbl_pr_avg = QLabel("—")
        self._lbl_pr_avg.setStyleSheet(f"color: {_TEXT};")
        self._lbl_pr_fuel = QLabel("—")
        self._lbl_pr_fuel.setStyleSheet(f"color: {_TEXT};")
        self._lbl_pr_laps = QLabel("—")
        self._lbl_pr_laps.setStyleSheet(f"color: {_TEXT};")
        for lbl, caption in [
            (self._lbl_pr_best, "Best Lap:"),
            (self._lbl_pr_avg, "Avg Lap:"),
            (self._lbl_pr_fuel, "Avg Fuel/Lap:"),
            (self._lbl_pr_laps, "Laps:"),
        ]:
            pair = QHBoxLayout()
            cap_lbl = QLabel(caption)
            cap_lbl.setStyleSheet(f"color: {_TEXT}; font-weight: bold;")
            pair.addWidget(cap_lbl)
            pair.addWidget(lbl)
            pair.addSpacing(16)
            summary_h.addLayout(pair)
        summary_h.addStretch()
        layout.addWidget(summary_group)

        lap_data_group = QGroupBox("Lap Data")
        lap_data_group.setStyleSheet(self._group_style())
        lap_data_layout = QVBoxLayout(lap_data_group)

        toolbar = QHBoxLayout()
        self._lbl_lap_count = QLabel("0 laps")
        self._lbl_lap_count.setStyleSheet(f"color: {_TEXT};")
        toolbar.addWidget(self._lbl_lap_count)
        toolbar.addStretch()

        from ui import ngr_theme as _ngr
        btn_save_session = QPushButton("Save Session")
        btn_save_session.setStyleSheet(_ngr.secondary_button_qss())
        btn_save_session.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_session.clicked.connect(self._save_session_to_db)
        toolbar.addWidget(btn_save_session)

        btn_save_setup = QPushButton("Save Setup")
        btn_save_setup.setStyleSheet(_ngr.primary_button_qss())
        btn_save_setup.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_setup.clicked.connect(self._save_setup_from_lapdata)
        toolbar.addWidget(btn_save_setup)

        btn_export = QPushButton("Export")
        btn_export.setStyleSheet(
            "QPushButton { background: #3A3A1A; color: white; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background: #5A5A2A; }"
        )
        btn_export.clicked.connect(self._export_excel)
        toolbar.addWidget(btn_export)

        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet(
            "QPushButton { background: #5C1A1A; color: white; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background: #8C2A2A; }"
        )
        btn_clear.clicked.connect(self._clear_laps)
        toolbar.addWidget(btn_clear)

        lap_data_layout.addLayout(toolbar)

        columns = [
            "Lap", "Session", "Lap Time", "Lap Time (ms)", "Delta (s)",
            "Best Lap", "Fuel Start (L)", "Fuel End (L)", "Fuel Used (L)",
            "Avg Fuel/Lap (L)", "Position", "Pit Stop", "Timestamp",
            "Compound ✎", "Setup ✎",
        ]
        self._lap_table = QTableWidget()
        self._lap_table.setColumnCount(len(columns))
        self._lap_table.setHorizontalHeaderLabels(columns)
        self._lap_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._lap_table.setAlternatingRowColors(True)
        # Inherit the global NGR table styling for a consistent pit-wall look.
        self._lap_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._lap_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lap_data_layout.addWidget(self._lap_table)

        hint_lbl = QLabel(
            "Tip: use the Compound column dropdown to tag the tyre used on each lap. "
            "Tagged laps are used by the Strategy Builder AI analysis."
        )
        hint_lbl.setStyleSheet("color: #888; font-size: 11px; padding: 4px 0;")
        hint_lbl.setWordWrap(True)
        lap_data_layout.addWidget(hint_lbl)
        layout.addWidget(lap_data_group)

        analysis_group = QGroupBox("Practice AI Analysis")
        analysis_group.setStyleSheet(self._group_style())
        analysis_layout = QVBoxLayout(analysis_group)

        self._practice_results_text = QTextEdit()
        self._practice_results_text.setReadOnly(True)
        self._practice_results_text.setMinimumHeight(320)
        self._practice_results_text.setPlaceholderText(
            "Practice session analysis results will appear here.\n"
            "Includes: aero/fuel trade-off, setup change recommendations, "
            "and further practice suggestions.")
        self._practice_results_text.setStyleSheet(
            f"QTextEdit {{ background: {_DARK_CARD}; color: {_TEXT}; "
            "border-left: 3px solid #4B2E78; border-radius: 4px; padding: 8px; }"
        )
        self._practice_results_text.setVisible(False)
        analysis_layout.addWidget(self._practice_results_text)
        layout.addWidget(analysis_group)

        layout.addWidget(self._build_driver_feedback_form())
        # UAT Finding 2: dedicated Practice Analysis surface AFTER driver feedback.
        layout.addWidget(self._build_practice_analysis_panel())
        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------ #
    # UAT Finding 2 — Practice Analysis structured surface.
    # ------------------------------------------------------------------ #

    def _build_practice_analysis_panel(self) -> QGroupBox:
        """Structured cross-lap pattern analysis (session summary + per-corner
        table + repeatable/strong/isolated lists + targeted tests). Deliberately
        NOT one plain-text box."""
        from ui import ngr_theme as _ngr_pa_btn
        group = QGroupBox("Practice Analysis — Patterns Across Laps")
        group.setStyleSheet(self._group_style())
        v = QVBoxLayout(group)
        v.setSpacing(8)

        intro = QLabel(
            "Analyses repeated vs isolated issues, consistently strong corners, "
            "and agreement with your feedback — across clean laps only.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#9AA0A6; font-size:10px;")
        v.addWidget(intro)

        btn_row = QHBoxLayout()
        self._btn_analyse_practice = QPushButton("Analyse Practice Patterns")
        self._btn_analyse_practice.setStyleSheet(_ngr_pa_btn.primary_button_qss())
        self._btn_analyse_practice.clicked.connect(self._analyse_practice_patterns)
        btn_row.addWidget(self._btn_analyse_practice)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self._pa_empty_lbl = QLabel(
            "Click “Analyse Practice Patterns” after a stint of clean laps.")
        self._pa_empty_lbl.setWordWrap(True)
        self._pa_empty_lbl.setStyleSheet(
            f"color:{_ngr_pa_btn.TEXT_DIM}; font-size:{_ngr_pa_btn.FS_BODY}pt;")
        v.addWidget(self._pa_empty_lbl)

        # 1) Session summary (grid of label/value).
        self._pa_summary_grid = QGridLayout()
        summary_box = QGroupBox("Session Summary")
        summary_box.setStyleSheet(self._group_style())
        summary_box.setLayout(self._pa_summary_grid)
        self._pa_summary_box = summary_box
        summary_box.setVisible(False)
        v.addWidget(summary_box)

        # 2) Per-corner pattern table (sortable; numeric columns tabular).
        from ui.practice_analysis_vm import CORNER_TABLE_COLUMNS
        from ui import ngr_theme as _ngr_pa
        self._pa_table = QTableWidget(0, len(CORNER_TABLE_COLUMNS))
        self._pa_table.setHorizontalHeaderLabels(list(CORNER_TABLE_COLUMNS))
        self._pa_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self._pa_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._pa_table.setSortingEnabled(True)             # P6: sortable table
        self._pa_table.setAlternatingRowColors(True)
        self._pa_table.setVisible(False)
        self._pa_table_caption = QLabel("Per-corner pattern")
        self._pa_table_caption.setStyleSheet(_ngr_pa.heading_qss(3))
        self._pa_table_caption.setVisible(False)
        v.addWidget(self._pa_table_caption)
        v.addWidget(self._pa_table)

        # 3-7) Lists: repeatable issues, strong corners, isolated events,
        #      driver-feedback agreement, targeted next tests.
        def _make_list(title: str):
            cap = QLabel(title)
            cap.setStyleSheet("color:#C8CDD2; font-weight:bold;")
            cap.setVisible(False)
            lst = QListWidget()
            lst.setMaximumHeight(110)
            lst.setVisible(False)
            v.addWidget(cap)
            v.addWidget(lst)
            return cap, lst

        self._pa_repeat_cap, self._pa_repeat_list = _make_list("Repeatable issues")
        self._pa_strong_cap, self._pa_strong_list = _make_list("Strong & consistent corners")
        self._pa_isolated_cap, self._pa_isolated_list = _make_list("Isolated events")
        self._pa_feedback_cap, self._pa_feedback_list = _make_list("Driver-feedback agreement")
        self._pa_tests_cap, self._pa_tests_list = _make_list("Targeted next tests")

        # Holistic brain Phase 2: per-corner driving coach (your perfect lap).
        coach_box = QGroupBox("Driving Coach — Your Perfect Lap")
        coach_box.setStyleSheet(self._group_style())
        cv = QVBoxLayout(coach_box)
        cv.setSpacing(6)
        coach_intro = QLabel(
            "Your best clean-lap corner targets (brake point · gears · apex "
            "speed · throttle-on), and where your normal laps leave time.")
        coach_intro.setWordWrap(True)
        coach_intro.setStyleSheet("color:#9AA0A6; font-size:10px;")
        cv.addWidget(coach_intro)
        self._btn_coach_lap = QPushButton("Coach My Perfect Lap")
        self._btn_coach_lap.setStyleSheet(_ngr_pa_btn.primary_button_qss())
        self._btn_coach_lap.clicked.connect(self._coach_perfect_lap)
        _crow = QHBoxLayout()
        _crow.addWidget(self._btn_coach_lap)
        _crow.addStretch()
        cv.addLayout(_crow)
        self._coach_summary_lbl = QLabel(
            "Click “Coach My Perfect Lap” after some clean laps.")
        self._coach_summary_lbl.setWordWrap(True)
        self._coach_summary_lbl.setStyleSheet(_ngr_pa_btn.banner_qss("success"))
        cv.addWidget(self._coach_summary_lbl)
        _ideal_cap = QLabel("Ideal lap — corner targets")
        _ideal_cap.setStyleSheet("color:#C8CDD2; font-weight:bold;")
        cv.addWidget(_ideal_cap)
        self._coach_ideal_list = QListWidget()
        self._coach_ideal_list.setMaximumHeight(130)
        self._coach_ideal_list.setVisible(False)
        cv.addWidget(self._coach_ideal_list)
        _adv_cap = QLabel("Where to find time")
        _adv_cap.setStyleSheet("color:#C8CDD2; font-weight:bold;")
        cv.addWidget(_adv_cap)
        self._coach_advice_list = QListWidget()
        self._coach_advice_list.setMaximumHeight(150)
        self._coach_advice_list.setVisible(False)
        cv.addWidget(self._coach_advice_list)
        v.addWidget(coach_box)

        # Holistic brain Phase 3: cross-session setup verdict.
        verdict_box = QGroupBox("Setup vs Previous — Did It Improve?")
        verdict_box.setStyleSheet(self._group_style())
        vv = QVBoxLayout(verdict_box)
        vv.setSpacing(6)
        v_intro = QLabel(
            "Compares your two most-recent setups on this car/track: lap-time, "
            "per-corner apex speed, wheelspin/lock-ups, and your own feedback.")
        v_intro.setWordWrap(True)
        v_intro.setStyleSheet("color:#9AA0A6; font-size:10px;")
        vv.addWidget(v_intro)
        self._btn_setup_verdict = QPushButton("Compare Setups (session history)")
        self._btn_setup_verdict.setStyleSheet(_ngr_pa_btn.primary_button_qss())
        self._btn_setup_verdict.clicked.connect(self._analyse_setup_verdict)
        _vrow = QHBoxLayout()
        _vrow.addWidget(self._btn_setup_verdict)
        _vrow.addStretch()
        vv.addLayout(_vrow)
        self._verdict_summary_lbl = QLabel(
            "Click “Compare Setups” once you've run two setups here.")
        self._verdict_summary_lbl.setWordWrap(True)
        self._verdict_summary_lbl.setStyleSheet(_ngr_pa_btn.banner_qss("info"))
        vv.addWidget(self._verdict_summary_lbl)
        self._verdict_reasons_list = QListWidget()
        self._verdict_reasons_list.setMaximumHeight(150)
        self._verdict_reasons_list.setVisible(False)
        vv.addWidget(self._verdict_reasons_list)
        v.addWidget(verdict_box)

        return group

    def _render_practice_analysis(self, report) -> None:
        """Populate the structured Practice Analysis widgets from a report."""
        from ui import practice_analysis_vm as pav

        empty = pav.empty_state(report)
        self._pa_empty_lbl.setText(empty or "")
        self._pa_empty_lbl.setVisible(bool(empty))

        # Session summary.
        while self._pa_summary_grid.count():
            item = self._pa_summary_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        rows = pav.session_summary_rows(report)
        for i, (label, value) in enumerate(rows):
            r, c = divmod(i, 3)
            cell = QLabel(f"{label}: {value}")
            cell.setStyleSheet(f"color: {_TEXT};")
            self._pa_summary_grid.addWidget(cell, r, c)
        self._pa_summary_box.setVisible(True)

        # Per-corner table. Numeric columns (Laps, Recur %) use tabular figures
        # + right alignment so they line up; sorting is toggled off during the
        # fill so rows aren't reordered mid-populate.
        from PyQt6.QtGui import QFont as _QFont
        from PyQt6.QtCore import Qt as _Qt
        from ui import ngr_theme as _ngr_pa
        _tab_font = _QFont("Consolas")
        _tab_font.setStyleHint(_QFont.StyleHint.Monospace)
        _numeric_cols = {3, 4}   # Laps, Recur %
        _PA_TONES = {"success": _ngr_pa.STATUS_TONES["success"][1],
                     "neutral": _ngr_pa.TEXT_DIM}
        pav_cols = pav.CORNER_TABLE_COLUMNS
        table_rows = pav.corner_table_rows(report)
        self._pa_table.setSortingEnabled(False)
        self._pa_table.setRowCount(len(table_rows))
        for ri, row in enumerate(table_rows):
            for ci, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if ci in _numeric_cols:
                    item.setFont(_tab_font)
                    item.setTextAlignment(_Qt.AlignmentFlag.AlignRight
                                          | _Qt.AlignmentFlag.AlignVCenter)
                # Colour the Author? cell by eligibility (never colour-only —
                # the text still reads Yes/No).
                if pav_cols[ci] == "Author?":
                    tone = "success" if str(val) == "Yes" else "neutral"
                    item.setForeground(QColor(_PA_TONES[tone]))
                self._pa_table.setItem(ri, ci, item)
        self._pa_table.setSortingEnabled(True)
        has_rows = bool(table_rows)
        self._pa_table.setVisible(has_rows)
        self._pa_table_caption.setVisible(has_rows)

        # Lists.
        for cap, lst, lines in (
            (self._pa_repeat_cap, self._pa_repeat_list, pav.repeatable_lines(report)),
            (self._pa_strong_cap, self._pa_strong_list, pav.strong_lines(report)),
            (self._pa_isolated_cap, self._pa_isolated_list, pav.isolated_lines(report)),
            (self._pa_feedback_cap, self._pa_feedback_list, pav.feedback_lines(report)),
            (self._pa_tests_cap, self._pa_tests_list, pav.targeted_test_lines(report)),
        ):
            lst.clear()
            for line in lines:
                lst.addItem(line)
            cap.setVisible(bool(lines))
            lst.setVisible(bool(lines))

    def _current_car_id(self) -> int:
        """Best-effort DB car_id for the active car (0 if unknown).

        Historical aggregates (setup comparison, car/track summary, corner-slip
        rows) are scoped by car_id; passing 0 matches nothing, which was why
        setup history read as empty. Resolve the real id from the live dispatcher
        ref first, then the event-context car name."""
        try:
            ref = getattr(self, "_car_id_ref", None)
            if ref and int(ref[0]) > 0:
                return int(ref[0])
        except Exception:
            pass
        try:
            car = str(getattr(self._build_event_context(), "car", "") or "")
            if car and self._db is not None:
                return int(self._db.get_car_id(car) or 0)
        except Exception:
            pass
        return 0

    def _reset_practice_capture(self) -> None:
        """Clear the per-lap practice buffers (call when a new practice session
        starts so cross-session evidence never mixes)."""
        self._practice_lap_episodes = {}
        self._practice_clean_laps = set()
        self._practice_total_laps = set()

    def _practice_track_identity(self):
        """(track_location_id, layout_id) for the active event, or ("","")."""
        try:
            ev = self._build_event_context()
            return (str(getattr(ev, "track_location_id", "") or ""),
                    str(getattr(ev, "layout_id", "") or ""))
        except Exception:
            return "", ""

    def _practice_reviewed_segments(self, loc: str, lay: str):
        """Best-effort reviewed segments for (loc, lay): the Track Modelling review
        state if present, else the best model on disk (same one the XYZ resolver
        uses). Returns [] when nothing is available."""
        review = getattr(self, "_tm_review_result", None)
        segs = list(getattr(review, "segments", []) or []) if review is not None else []
        if segs:
            return segs
        if not (loc and lay):
            return []
        try:
            from data.track_model_resolver import resolve_best_track_model
            res = resolve_best_track_model(loc, lay)
            model = getattr(res, "resolved_model", None)
            rev = getattr(model, "reviewed_model", None) if model is not None else None
            return list(getattr(rev, "segments", []) or []) if rev is not None else []
        except Exception:
            return []

    def _practice_segments_cache(self):
        """Legacy accessor kept for the progress-resolver fallback:
        (reviewed_segments, lap_length_m, offset_m) for the active track."""
        loc, lay = self._practice_track_identity()
        segs = self._practice_reviewed_segments(loc, lay)
        lap_len = 0.0
        try:
            lap_len = float(self._tm_get_track_length_m() or 0.0)
        except Exception:
            lap_len = 0.0
        offset = 0.0
        cal = getattr(self, "_tm_offset_calibration", None)
        if cal is not None:
            offset = float(getattr(cal, "offset_m", 0.0) or 0.0)
        return segs, lap_len, offset

    def _capture_practice_lap(self, record) -> None:
        """Extract the just-completed lap's slip episodes and fold them into the
        Practice Analysis buffers. Best-effort — never raises into the lap path.
        """
        try:
            rec = getattr(self, "_recorder", None)
            if rec is None:
                return
            lap_num = int(getattr(record, "lap", getattr(record, "lap_number", 0)) or 0)
            stats = None
            try:
                stats = rec.get_lap(lap_num) if lap_num else None
            except Exception:
                stats = None
            if stats is None and hasattr(rec, "last_lap"):
                stats = rec.last_lap()
            frames = getattr(stats, "frames", None) if stats is not None else None
            if not frames:
                return
            lap_num = int(getattr(stats, "lap_num", lap_num) or lap_num)

            drivetrain = ""
            try:
                if hasattr(self, "_setup_drivetrain"):
                    drivetrain = self._setup_drivetrain.currentText() or ""
            except Exception:
                drivetrain = ""

            from strategy.practice_capture import (
                build_progress_segment_resolver, build_xyz_segment_resolver,
                compute_lap_capture, segments_to_corner_names,
                segments_to_track_corners)
            loc, lay = self._practice_track_identity()
            segs = self._practice_reviewed_segments(loc, lay)
            offset = 0.0
            cal = getattr(self, "_tm_offset_calibration", None)
            if cal is not None:
                offset = float(getattr(cal, "offset_m", 0.0) or 0.0)

            resolver = None
            if loc and lay:
                # PRIMARY: XYZ → reference-path matcher (accumulates corner names).
                resolver = build_xyz_segment_resolver(
                    loc, lay, offset_calibration=cal,
                    name_sink=self._practice_corner_names)
            if resolver is None and segs:
                # Fallback: road-distance → lap-progress over reviewed segments.
                lap_len = 0.0
                try:
                    lap_len = float(self._tm_get_track_length_m() or 0.0)
                except Exception:
                    lap_len = 0.0
                if lap_len > 0:
                    resolver = build_progress_segment_resolver(segs, lap_len, offset)

            best = 0
            try:
                best = int(self._logger.best_lap_ms() or 0)
            except Exception:
                best = 0
            episodes, is_clean = compute_lap_capture(
                frames, drivetrain, resolver,
                lap_time_ms=int(getattr(record, "lap_time_ms", 0) or 0),
                best_ms=best, valid=bool(getattr(record, "is_valid", True)))
            self._practice_lap_episodes[lap_num] = episodes
            self._practice_total_laps.add(lap_num)
            if is_clean:
                self._practice_clean_laps.add(lap_num)

            if segs:
                # Merge disk names with any the XYZ resolver accumulated.
                for sid, nm in segments_to_corner_names(segs).items():
                    if nm:
                        self._practice_corner_names.setdefault(sid, nm)
                self._practice_track_corners = segments_to_track_corners(segs)

            # Holistic brain Phase 0: turn on cross-session per-corner collection
            # by persisting this lap's episodes to corner_issue_occurrences
            # (dormant table, 0 rows before) so history accrues across sessions.
            self._persist_practice_episodes(lap_num, episodes)
        except Exception as e:
            print(f"[PracticeCapture] {e}")

    def _persist_practice_episodes(self, lap_num: int, episodes) -> None:
        """Persist a lap's slip episodes to corner_issue_occurrences (best-effort).
        Never raises; no-op without a DB or a resolved car/track."""
        if self._db is None or not episodes:
            return
        try:
            loc, lay = self._practice_track_identity()
            track = str(getattr(self._build_event_context(), "track", "") or "")
            car_id = self._current_car_id()
            if not (car_id and track):
                return
            sid = int(getattr(getattr(self, "_dispatcher", None), "_session_id", 0) or 0)
            from strategy.practice_capture import episodes_to_occurrences
            occ = episodes_to_occurrences(episodes, lap_number=lap_num, session_id=sid)
            self._db.save_issue_occurrences(car_id, track, lay, occ)
        except Exception as ex:
            print(f"[PracticeCapture] persist episodes: {ex}")

    def _perfect_lap_frame_resolver(self, loc: str, lay: str):
        """A frame->(segment_id, phase) resolver over the XYZ path, for offline
        per-corner extraction of stored lap frames."""
        from strategy.practice_capture import build_xyz_segment_resolver
        cal = getattr(self, "_tm_offset_calibration", None)
        xyz = build_xyz_segment_resolver(loc, lay, offset_calibration=cal)

        def _fr(frame):
            get = (frame.get if isinstance(frame, dict)
                   else lambda k, d=None: getattr(frame, k, d))
            px, py, pz = get("pos_x", None), get("pos_y", None), get("pos_z", None)
            pos = (px, py, pz) if None not in (px, py, pz) else None
            return xyz(get("road_distance", 0.0), get("speed_kmh", 0.0),
                       get("throttle", 0.0), get("brake", 0.0), pos=pos)

        return _fr

    def _build_perfect_lap_report(self):
        """Holistic brain Phases 1-2: read recent practice laps' stored frames,
        extract per-corner reference points, and coach against the driver's own
        best clean laps. Returns None when there's no usable data."""
        from strategy.perfect_lap_pipeline import coach_from_laps
        if self._db is None:
            return None
        loc, lay = self._practice_track_identity()
        car_id = self._current_car_id()
        track = str(getattr(self._build_event_context(), "track", "") or "")
        if not (car_id and track):
            return None
        laps = self._db.get_laps_with_telemetry(
            car_id, track, session_type="Practice", limit=30)
        if not laps:
            return None
        segs = self._practice_reviewed_segments(loc, lay)
        resolver = self._perfect_lap_frame_resolver(loc, lay)
        return coach_from_laps(laps, resolver, segs)

    def _run_analysis_async(self, build_fn, render_fn, button, busy_text: str):
        """Run a (potentially slow, DB-reading) analysis off the UI thread with
        loading feedback, then render on the main thread. Keeps the UI responsive
        (skill: loading-buttons + progressive-loading). SessionDB is opened with
        check_same_thread=False and lock-guarded, so cross-thread reads are safe.
        """
        from ui.track_model_build_worker import TrackModelBuildWorker
        orig = button.text() if button is not None else ""
        if button is not None:
            button.setEnabled(False)
            button.setText(busy_text)

        def _work(_report, _is_cancelled):
            return build_fn()

        worker = TrackModelBuildWorker(_work)

        def _restore():
            if button is not None:
                button.setEnabled(True)
                button.setText(orig)
            self._analysis_workers.discard(worker)

        def _done(result):
            try:
                render_fn(result)
            finally:
                _restore()

        def _failed(msg):
            print(f"[Analysis] {msg}")
            try:
                render_fn(None)
            finally:
                _restore()

        worker.finished_ok.connect(_done)
        worker.failed.connect(_failed)
        self._analysis_workers.add(worker)   # hold a ref so the QThread survives
        worker.start()
        return worker

    def _coach_perfect_lap(self) -> None:
        """Button handler: build + render the perfect-lap coaching (off-thread)."""
        self._run_analysis_async(
            self._build_perfect_lap_report, self._render_perfect_lap,
            getattr(self, "_btn_coach_lap", None), "Coaching…")

    def _render_perfect_lap(self, report) -> None:
        lbl = getattr(self, "_coach_summary_lbl", None)
        ideal_list = getattr(self, "_coach_ideal_list", None)
        advice_list = getattr(self, "_coach_advice_list", None)
        if lbl is None:
            return
        if report is None or not report.ideal_corners:
            lbl.setText(
                "No coached laps yet — drive clean practice laps on a track with "
                "an approved model, then click again. (Corner identity needs the "
                "track model.)")
            for lst in (ideal_list, advice_list):
                if lst is not None:
                    lst.clear()
                    lst.setVisible(False)
            return
        lbl.setText(report.session_consistency)
        if ideal_list is not None:
            ideal_list.clear()
            for line in report.ideal_lap_lines:
                ideal_list.addItem(line)
            ideal_list.setVisible(True)
        if advice_list is not None:
            advice_list.clear()
            for c in report.coaching:
                for a in c.advice:
                    advice_list.addItem(a)
            advice_list.setVisible(True)

    def _setup_id_labels(self) -> dict:
        """Map DB setup_id -> display label from saved setups."""
        out = {}
        try:
            from ui.setup_name_helper import setup_display_label
            for s in (getattr(self, "_saved_setups", []) or []):
                sid = s.get("setup_id")
                if sid:
                    out[sid] = setup_display_label(s) or f"Setup {sid}"
        except Exception:
            pass
        return out

    def _build_setup_verdict(self):
        """Holistic brain Phase 3: compare the two most-recent setups on this
        car/track using lap-time + per-corner + slip deltas and feedback."""
        from strategy.setup_verdict_pipeline import build_verdict_from_laps
        if self._db is None:
            return None
        loc, lay = self._practice_track_identity()
        car_id = self._current_car_id()
        track = str(getattr(self._build_event_context(), "track", "") or "")
        if not (car_id and track):
            return None
        laps = self._db.get_laps_with_telemetry(
            car_id, track, session_type="Practice", limit=60)
        if not laps:
            return None
        segs = self._practice_reviewed_segments(loc, lay)
        resolver = self._perfect_lap_frame_resolver(loc, lay)
        # Best-effort latest vs-previous feedback.
        fb = ""
        try:
            recent = self._db.get_recent_feedback(car_id, track, limit=1)
            if recent:
                fb = str(recent[0].get("vs_previous", "") or "")
        except Exception:
            fb = ""
        return build_verdict_from_laps(
            laps, resolver, segs, labels=self._setup_id_labels(),
            feedback_vs_previous=fb)

    def _analyse_setup_verdict(self) -> None:
        self._run_analysis_async(
            self._build_setup_verdict, self._render_setup_verdict,
            getattr(self, "_btn_setup_verdict", None), "Comparing…")

    def _render_setup_verdict(self, verdict) -> None:
        lbl = getattr(self, "_verdict_summary_lbl", None)
        reasons = getattr(self, "_verdict_reasons_list", None)
        if lbl is None:
            return
        if verdict is None:
            lbl.setText(
                "Need at least two setups with clean laps on this car/track "
                "(with a track model for corner detail) to compare.")
            if reasons is not None:
                reasons.clear()
                reasons.setVisible(False)
            return
        lbl.setText(verdict.headline())
        if reasons is not None:
            reasons.clear()
            for r in verdict.reasons:
                reasons.addItem(r)
            reasons.setVisible(True)

    def _analyse_practice_patterns(self) -> None:
        """Gather this session's slip episodes, run the deterministic engine and
        render the structured result. Honest empty-state when data is thin."""
        from strategy.practice_pattern_analysis import analyze_practice
        try:
            report = self._build_practice_analysis_report()
        except Exception as e:
            print(f"[PracticeAnalysis] {e}")
            report = analyze_practice([], clean_lap_numbers=[], total_lap_numbers=[])
        self._render_practice_analysis(report)

    def _build_practice_analysis_report(self):
        """Assemble a PracticeAnalysisReport from the current session's laps.

        Best-effort: uses per-lap slip episodes + the driver feedback that was
        just submitted. Returns an empty (honest) report when no clean-lap
        episode data is available yet.
        """
        from strategy.practice_pattern_analysis import analyze_practice
        from strategy.practice_observation_builder import build_observations

        lap_episodes = getattr(self, "_practice_lap_episodes", None) or {}
        clean = getattr(self, "_practice_clean_laps", None)
        clean = sorted(int(l) for l in clean) if clean else []
        if not clean:
            # No lap passed the clean-lap gate (or none tracked) — fall back to
            # every captured lap so the surface still analyses what exists.
            clean = sorted(int(l) for l in lap_episodes.keys())
        total = getattr(self, "_practice_total_laps", None)
        total = sorted(int(l) for l in total) if total else sorted(
            int(l) for l in lap_episodes.keys())
        corner_names = getattr(self, "_practice_corner_names", None) or {}
        driver_feedback = getattr(self, "_last_feedback_dict", None)

        observations = build_observations(
            lap_episodes, clean_lap_numbers=clean, corner_names=corner_names)
        return analyze_practice(
            observations, clean_lap_numbers=clean, total_lap_numbers=total,
            track_corners=getattr(self, "_practice_track_corners", None),
            driver_feedback=driver_feedback)

    def _build_driver_feedback_form(self) -> QGroupBox:
        group = QGroupBox("Driver Feedback — After Stint")
        group.setStyleSheet(self._group_style())
        form = QFormLayout(group)
        form.setSpacing(8)

        self._feedback_combos: dict[str, QComboBox] = {}

        feedback_rows = [
            ("Corner Entry", ["—", "Good balance", "Too much understeer", "Too much oversteer", "Rear unstable under braking"]),
            ("Mid-Corner", ["—", "Good rotation", "Pushes wide", "Too much rotation", "Snaps on lift-off"]),
            ("Exit Stability", ["—", "Good traction", "Rear loose on throttle", "Poor traction", "Stable but sluggish"]),
            ("Rear Under Braking", ["—", "Stable", "Steps out", "Locks up rear"]),
            ("Tyre Condition", ["—", "Fine", "Front overheating", "Rear overheating", "Both overheating", "Too cold to grip"]),
            ("Fuel Use", ["—", "On target", "Higher than expected", "Lower than expected"]),
        ]

        for label, options in feedback_rows:
            combo = QComboBox()
            combo.addItems(options)
            combo.setStyleSheet(
                f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; "
                "border-radius: 3px; padding: 2px 6px; }"
                f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
            )
            self._feedback_combos[label] = combo
            lbl_widget = QLabel(label + ":")
            lbl_widget.setStyleSheet(f"color: {_TEXT};")
            form.addRow(lbl_widget, combo)

        # Which saved setup was run this stint — defaults to whatever was
        # declared in the Live practice panel, editable here. Passed to the AI
        # with the feedback so the setup fix knows which setup was on the car.
        setup_run_lbl = QLabel("Setup run this stint:")
        setup_run_lbl.setStyleSheet(f"color: {_TEXT};")
        self._prac_running_setup_combo = QComboBox()
        self._prac_running_setup_combo.setStyleSheet(
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; "
            "border-radius: 3px; padding: 2px 6px; }"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )
        self._prac_running_setup_combo.setToolTip(
            "The setup you ran this stint (carried over from the Live tab). "
            "Change it here if needed before submitting feedback.")
        self._prac_running_setup_combo.currentTextChanged.connect(self._on_running_setup_changed)
        form.addRow(setup_run_lbl, self._prac_running_setup_combo)
        self._refresh_running_setup_combos()

        # Overall subjective take on the setup run this stint. Moved here from
        # the Setup Builder so the "did I like it?" rating sits with the rest of
        # the per-run feedback; it is attributed to the setup that was running.
        rating_lbl = QLabel("How did this setup feel?:")
        rating_lbl.setStyleSheet(f"color: {_TEXT};")
        self._feedback_rating_combo = QComboBox()
        self._feedback_rating_combo.addItems(["—", "Liked", "Hated", "Neutral"])
        self._feedback_rating_combo.setStyleSheet(
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; "
            "border-radius: 3px; padding: 2px 6px; }"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )
        self._feedback_rating_combo.setToolTip(
            "Your overall take on the setup you ran this stint — the app learns "
            "from this to shape future setup advice.")
        form.addRow(rating_lbl, self._feedback_rating_combo)

        # Phase 7: explicit directional outcome vs the previous setup — closes the loop
        # (feeds the setup development timeline + rollback). Distinct from the absolute
        # Liked/Hated feel above.
        vs_lbl = QLabel("Compared to your last setup:")
        vs_lbl.setStyleSheet(f"color: {_TEXT};")
        self._feedback_vs_prev_combo = QComboBox()
        self._feedback_vs_prev_combo.addItems(["—", "Better", "Unchanged", "Worse"])
        self._feedback_vs_prev_combo.setStyleSheet(
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; "
            "border-radius: 3px; padding: 2px 6px; }"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )
        self._feedback_vs_prev_combo.setToolTip(
            "Did this setup make the car better or worse than the one before it? The app "
            "records this on the setup timeline and will not repeat a change that made it "
            "worse.")
        form.addRow(vs_lbl, self._feedback_vs_prev_combo)

        notes_lbl = QLabel("Notes:")
        notes_lbl.setStyleSheet(f"color: {_TEXT};")
        self._feedback_notes = QTextEdit()
        self._feedback_notes.setMaximumHeight(70)
        self._feedback_notes.setPlaceholderText("Any extra detail about handling...")
        self._feedback_notes.setStyleSheet(
            f"QTextEdit {{ background: {_DARK_CARD}; color: {_TEXT}; "
            "border: 1px solid #333; border-radius: 3px; padding: 4px; }"
        )
        form.addRow(notes_lbl, self._feedback_notes)

        from ui import ngr_theme as _ngr_fb
        btn_submit = QPushButton("Analyse Feedback → Setup Fix")
        btn_submit.setStyleSheet(_ngr_fb.primary_button_qss())
        btn_submit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_submit.clicked.connect(self._on_driver_feedback_submit)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_submit)
        form.addRow("", btn_row)

        return group

    def _on_driver_feedback_submit(self) -> None:
        from datetime import datetime, timezone

        parts = []
        feedback_dict: dict = {}

        # Which setup was on the car this stint (declared in Live practice /
        # editable here). Prepended to the feedback text so it flows into the
        # setup-fix AI prompt via _setup_feeling_input, and recorded in the dict.
        running_setup = ""
        if hasattr(self, "_prac_running_setup_combo"):
            _rs = self._prac_running_setup_combo.currentText()
            running_setup = "" if (not _rs or _rs == "— none —") else _rs
        elif getattr(self, "_live_running_setup", ""):
            running_setup = self._live_running_setup
        # UAT Finding 1: with no manual override, attach feedback to the canonical
        # active applied setup (the Live baseline) so it's associated with the
        # exact setup revision on the car — no duplicate manual selection.
        setup_revision = 0
        if not running_setup:
            _active = self._active_setup_for_current("Race")
            if _active is not None:
                running_setup = _active.label()
                setup_revision = _active.revision
        else:
            _active = self._active_setup_for_current("Race")
            if _active is not None:
                setup_revision = _active.revision
        feedback_dict["setup_run"] = running_setup
        feedback_dict["setup_revision"] = setup_revision
        if running_setup:
            parts.append(f"Setup run this stint: {running_setup}")

        for label, combo in self._feedback_combos.items():
            val = combo.currentText()
            key = label.lower().replace(" ", "_").replace("/", "_")
            feedback_dict[key] = val if (val and val != "—") else ""
            if val and val != "—":
                parts.append(f"{label}: {val}")

        notes = self._feedback_notes.toPlainText().strip()
        feedback_dict["notes"] = notes
        if notes:
            parts.append(f"Notes: {notes}")

        rating = ""
        if hasattr(self, "_feedback_rating_combo"):
            _rt = self._feedback_rating_combo.currentText()
            rating = {"Liked": "liked", "Hated": "hated", "Neutral": "neutral"}.get(_rt, "")

        # Phase 7: directional outcome vs the previous setup.
        _vs_prev = ""
        if hasattr(self, "_feedback_vs_prev_combo"):
            _vsp = self._feedback_vs_prev_combo.currentText()
            _vs_prev = {"Better": "better", "Unchanged": "unchanged",
                        "Worse": "worse"}.get(_vsp, "")
        feedback_dict["vs_previous"] = _vs_prev
        if _vs_prev:
            parts.append(f"Compared to last setup: {_vsp}")
        # Remember the latest feedback so Practice Analysis can check telemetry
        # agreement/contradiction against the driver's own words.
        self._last_feedback_dict = dict(feedback_dict)

        # Submit if there's any structured feedback, notes, a rating, or a vs-previous call.
        if not parts and not rating and not _vs_prev:
            return

        feedback_str = "\n".join(parts)
        if hasattr(self, "_setup_feeling_input"):
            existing = self._setup_feeling_input.toPlainText().strip()
            if existing:
                self._setup_feeling_input.setPlainText(
                    existing + "\n\n--- Driver Feedback ---\n" + feedback_str)
            else:
                self._setup_feeling_input.setPlainText("--- Driver Feedback ---\n" + feedback_str)

        log = self._config.setdefault("driver_feedback_log", [])
        log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "feedback": feedback_str,
        })
        if len(log) > 200:
            self._config["driver_feedback_log"] = log[-200:]

        if self._db is not None:
            try:
                # config_id lives at config["strategy"]["config_id"] — read it via
                # the canonical accessor. The old top-level self._config["config_id"]
                # never exists, so feedback rows were stored with an empty config_id.
                config_id = self._active_config_id()
                # Session id from the dispatcher matches the id used when tagging
                # laps with a setup, so the dominant-setup lookup lines up.
                _sid = 0
                if getattr(self, "_dispatcher", None) is not None:
                    _sid = getattr(self._dispatcher, "_session_id", 0) or 0
                if not _sid:
                    _sid = getattr(self, "_session_id", 0) or 0
                # Attribute the feedback to the setup actually driven this stint;
                # fall back to the most-recently-saved setup when no laps tagged.
                _setup_id = self._db.get_dominant_setup_id(_sid)
                if not _setup_id:
                    try:
                        _setup_id = self._resolve_setup_id_for_lap()
                    except Exception:
                        _setup_id = 0
                self._db.write_feedback(
                    session_id=_sid,
                    lap_num=self._logger.lap_count() if self._logger else 0,
                    feedback=feedback_dict,
                    config_id=config_id,
                    setup_id=_setup_id,
                    rating=rating,
                )
                # Phase 7: an explicit better/worse-vs-previous call stamps the latest
                # setup-lineage node (feeds the timeline + rollback + failed-direction
                # lockout). Best-effort; only fills an unscored node.
                if _vs_prev:
                    try:
                        from strategy.setup_lineage import vs_previous_to_verdict
                        _verdict = vs_previous_to_verdict(_vs_prev)
                        _cid = int(self._car_id_ref[0]) if getattr(self, "_car_id_ref", None) else 0
                        # Canonical EventContext (DB-first) — not a raw config["strategy"]
                        # read (frozen fan-out allowlist).
                        _evc = self._build_event_context()
                        if _verdict and _cid > 0:
                            self._db.record_latest_lineage_outcome(
                                _cid, _evc.track, _evc.layout_id, _verdict, _sid)
                            # A 'worse' verdict may now warrant a rollback — refresh
                            # the editor's revert controls so they surface.
                            if hasattr(self, "_refresh_revert_buttons"):
                                self._refresh_revert_buttons()
                    except Exception:
                        pass
            except Exception:
                pass

        self._persist_config()

    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        filter_bar = QHBoxLayout()
        car_lbl = QLabel("Car:")
        car_lbl.setStyleSheet(f"color: {_TEXT};")
        filter_bar.addWidget(car_lbl)
        self._hist_car_combo = QComboBox()
        self._hist_car_combo.addItem("All")
        self._hist_car_combo.currentIndexChanged.connect(lambda _: self._refresh_history())
        filter_bar.addWidget(self._hist_car_combo)

        track_lbl = QLabel("Track:")
        track_lbl.setStyleSheet(f"color: {_TEXT};")
        filter_bar.addWidget(track_lbl)
        self._hist_track_combo = QComboBox()
        self._hist_track_combo.addItem("All")
        self._hist_track_combo.currentIndexChanged.connect(lambda _: self._refresh_history())
        filter_bar.addWidget(self._hist_track_combo)

        type_lbl = QLabel("Type:")
        type_lbl.setStyleSheet(f"color: {_TEXT};")
        filter_bar.addWidget(type_lbl)
        self._hist_type_combo = QComboBox()
        self._hist_type_combo.addItems(["All", "Race", "Practice"])
        self._hist_type_combo.currentIndexChanged.connect(lambda _: self._refresh_history())
        filter_bar.addWidget(self._hist_type_combo)
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        from ui import ngr_theme as _ngr
        self._tbl_history = QTableWidget()
        self._tbl_history.setColumnCount(6)
        self._tbl_history.setHorizontalHeaderLabels(["Date", "Car", "Track", "Type", "Laps", "Best Lap"])
        self._tbl_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_history.setAlternatingRowColors(True)
        # Inherit the global NGR table styling (dark header / carbon rows / neon
        # selection) rather than a one-off inline style.
        self._tbl_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_history.currentCellChanged.connect(
            lambda row, _col, _prow, _pcol: self._on_history_row_selected(row))
        layout.addWidget(self._tbl_history)

        # Driver-facing empty state — tells the user exactly what to do next when
        # no sessions are recorded (or none match the current filter). Hidden
        # whenever the table has rows (toggled in _refresh_history).
        self._hist_empty_lbl = _ngr.empty_state_label(
            "No saved sessions yet. Drive a practice or race session with the app "
            "connected — completed laps are recorded automatically and will appear "
            "here.")
        self._hist_empty_lbl.setVisible(False)
        layout.addWidget(self._hist_empty_lbl)

        detail_group = QGroupBox("Session Detail")
        detail_group.setStyleSheet(self._group_style())
        detail_layout = QVBoxLayout(detail_group)
        self._tbl_history_detail = QTableWidget()
        self._tbl_history_detail.setColumnCount(4)
        self._tbl_history_detail.setHorizontalHeaderLabels(["Lap", "Time", "Compound", "Fuel Used"])
        self._tbl_history_detail.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl_history_detail.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_history_detail.setMaximumHeight(250)
        # Inherit global NGR table styling.
        detail_layout.addWidget(self._tbl_history_detail)

        btn_load = QPushButton("Load into Practice Review")
        btn_load.setStyleSheet(_ngr.secondary_button_qss())
        btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_load.clicked.connect(self._on_history_load_session)
        load_row = QHBoxLayout()
        load_row.addStretch()
        load_row.addWidget(btn_load)
        detail_layout.addLayout(load_row)
        layout.addWidget(detail_group)

        self._hist_selected_session_id = None
        self._refresh_history()
        return widget

    def _refresh_history(self) -> None:
        if not hasattr(self, "_tbl_history"):
            return
        if self._db is None:
            self._set_history_empty_state(
                "Session database unavailable — recorded laps can't be loaded "
                "right now.")
            return
        try:
            sessions = self._db.get_all_sessions(limit=60)
        except Exception:
            self._set_history_empty_state(
                "Couldn't read the session database. Try reopening the app; your "
                "recorded laps are not lost.")
            return

        car_filter   = self._hist_car_combo.currentText()
        track_filter = self._hist_track_combo.currentText()
        type_filter  = self._hist_type_combo.currentText()

        cars = set()
        tracks = set()
        for s in sessions:
            if s.get("car_name"):
                cars.add(s["car_name"])
            if s.get("track"):
                tracks.add(s["track"])

        for combo, current, items in [
            (self._hist_car_combo,   car_filter,   sorted(cars)),
            (self._hist_track_combo, track_filter, sorted(tracks)),
        ]:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("All")
            for item in items:
                combo.addItem(item)
            idx = combo.findText(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        filtered = [
            s for s in sessions
            if (car_filter   == "All" or s.get("car_name", "")        == car_filter)
            and (track_filter == "All" or s.get("track", "")           == track_filter)
            and (type_filter  == "All" or s.get("session_type", "").lower() == type_filter.lower())
        ]

        self._tbl_history.setRowCount(0)
        session_ids = []
        for s in filtered:
            row = self._tbl_history.rowCount()
            self._tbl_history.insertRow(row)
            laps = self._db.get_session_laps(s["id"]) if self._db else []
            best_ms = min((l["lap_time_ms"] for l in laps if l.get("lap_time_ms")), default=None)
            best_str = ms_to_str(best_ms) if best_ms is not None else "—"
            for col, val in enumerate([
                str(s.get("date_utc", "")),
                str(s.get("car_name", "")),
                str(s.get("track", "")),
                str(s.get("session_type", "")),
                str(s.get("total_laps", "")),
                best_str,
            ]):
                self._tbl_history.setItem(row, col, QTableWidgetItem(val))
            session_ids.append(s["id"])
        self._tbl_history.setProperty("_session_ids", session_ids)

        # Empty-state guidance: distinguish "nothing recorded yet" from "nothing
        # matches this filter" so the next step is always clear.
        if filtered:
            self._set_history_empty_state(None)
        elif sessions:
            self._set_history_empty_state(
                "No sessions match these filters. Widen Car / Track / Type — or set "
                "them back to “All” — to see your recorded sessions.")
        else:
            self._set_history_empty_state(
                "No saved sessions yet. Drive a practice or race session with the "
                "app connected — completed laps are recorded automatically and will "
                "appear here.")

    def _set_history_empty_state(self, message: "str | None") -> None:
        """Show the driver-facing empty-state message (None hides it).

        Display-only; safe if the label was never built.
        """
        lbl = getattr(self, "_hist_empty_lbl", None)
        if lbl is None:
            return
        if message:
            lbl.setText(message)
            lbl.setVisible(True)
        else:
            lbl.setVisible(False)

    def _on_history_row_selected(self, row: int) -> None:
        if row < 0:
            return
        try:
            session_ids = self._tbl_history.property("_session_ids") or []
            if row >= len(session_ids):
                return
            session_id = session_ids[row]
            self._hist_selected_session_id = session_id
            if self._db is None:
                return
            laps = self._db.get_session_laps(session_id)
            self._tbl_history_detail.setRowCount(0)
            for lap in laps:
                r = self._tbl_history_detail.rowCount()
                self._tbl_history_detail.insertRow(r)
                time_str = ms_to_str(lap["lap_time_ms"]) if lap.get("lap_time_ms") else "—"
                for col, val in enumerate([
                    str(lap.get("lap_num", "")),
                    time_str,
                    str(lap.get("compound", "")),
                    str(lap.get("fuel_used", "")),
                ]):
                    self._tbl_history_detail.setItem(r, col, QTableWidgetItem(val))
        except Exception:
            pass

    def _on_history_load_session(self) -> None:
        """Load laps from the selected History session into Practice Review."""
        sid = getattr(self, "_hist_selected_session_id", None)
        if not sid or self._db is None:
            return
        try:
            laps = self._db.get_session_laps(sid)
        except Exception:
            return
        if not laps:
            self._refresh_practice_summary()
            return
        best_ms = min((l["lap_time_ms"] for l in laps if l["lap_time_ms"] > 0), default=0)
        existing_nums: set[int] = set()
        for r in range(self._lap_table.rowCount()):
            item = self._lap_table.item(r, 0)
            if item:
                try:
                    existing_nums.add(int(item.text()))
                except ValueError:
                    pass

        # Clear stale compound tags for laps we are about to load (DEF-P1-006)
        for _lap in laps:
            if _lap["lap_num"] not in existing_nums:
                self._lap_compound_tags.pop(_lap["lap_num"], None)

        for lap in laps:
            ln = lap["lap_num"]
            if ln in existing_nums:
                continue
            self._add_bank_lap_row(
                lap_num=ln,
                lap_time_ms=lap["lap_time_ms"],
                fuel_used=float(lap.get("fuel_used") or 0),
                compound=lap.get("compound") or "",
                best_ms=best_ms,
                session_date="",
                fuel_start=float(lap.get("fuel_start") or 0),
                fuel_end=float(lap.get("fuel_end") or 0),
                is_pit_lap=bool(lap.get("is_pit_lap", 0)),
                is_out_lap=bool(lap.get("is_out_lap", 0)),
            )

        # Compute session-scoped fuel average for Practice Analysis (DEF-P1-007)
        _fuel_vals = [float(l.get("fuel_used") or 0) for l in laps
                      if float(l.get("fuel_used") or 0) > 0
                      and not bool(l.get("is_pit_lap", 0))
                      and not bool(l.get("is_out_lap", 0))]
        self._loaded_session_avg_fuel = (sum(_fuel_vals) / len(_fuel_vals)) if _fuel_vals else 0.0

        # DEF-P2-009: refresh Strategy Builder fuel burn label immediately after load
        if hasattr(self, "_lbl_fuel_burn_display") and self._loaded_session_avg_fuel > 0:
            self._lbl_fuel_burn_display.setText(
                f"{self._loaded_session_avg_fuel:.2f} L/lap (loaded session)")

        self.select_tab(TAB_PRACTICE_REVIEW)
        self._refresh_practice_summary()

    def _refresh_practice_summary(self) -> None:
        """Recalculate Practice Review session summary from all rows in _lap_table."""
        total = self._lap_table.rowCount()
        if total == 0:
            self._lbl_pr_laps.setText("0")
            for lbl in (self._lbl_pr_best, self._lbl_pr_avg, self._lbl_pr_fuel):
                lbl.setText("—")
            return

        times_ms: list[int] = []
        fuels: list[float] = []
        for row in range(total):
            first_item = self._lap_table.item(row, 0)
            row_flags = (first_item.data(Qt.ItemDataRole.UserRole) or {}) if first_item else {}
            is_out = row_flags.get("is_out_lap", False)

            time_item = self._lap_table.item(row, 3)
            fuel_item = self._lap_table.item(row, 8)
            # Outlaps are shown in the table but excluded from best/avg/fuel calculations
            if not is_out and time_item:
                try:
                    ms = int(time_item.text())
                    if ms > 0:
                        times_ms.append(ms)
                except (ValueError, TypeError):
                    pass
            if not is_out and fuel_item:
                try:
                    f = float(fuel_item.text())
                    if f > 0:
                        fuels.append(f)
                except (ValueError, TypeError):
                    pass

        self._lbl_pr_laps.setText(str(total))
        if times_ms:
            self._lbl_pr_best.setText(format_laptime_display(min(times_ms)))
            avg_ms = int(sum(times_ms) / len(times_ms))
            self._lbl_pr_avg.setText(format_laptime_display(avg_ms))
        else:
            self._lbl_pr_best.setText("—")
            self._lbl_pr_avg.setText("—")
        if fuels:
            self._lbl_pr_fuel.setText(f"{sum(fuels) / len(fuels):.2f} L")
        else:
            self._lbl_pr_fuel.setText("—")


    def _active_event(self) -> dict:
        aid = self._config.get("active_event_id")
        if not aid:
            return {}
        if self._db is not None:
            evt = self._db.get_event(aid)
            if evt:
                return evt
        return next(
            (e for e in self._config.get("events", []) if e.get("name") == aid),
            {}
        )

    def _build_event_context(self):
        """Canonical read model of the active event/race configuration.

        State Consolidation 1: normalises the durable DB event record and the
        legacy ``config["strategy"]`` snapshot into one immutable EventContext
        (see ``data/event_context.py``). This is the preferred read path for
        event/race truth; ``config["strategy"]`` remains as legacy compatibility.
        Never raises — returns an EMPTY-source context if state is unavailable.
        """
        try:
            from data.event_context import build_event_context
            return build_event_context(
                event=self._active_event() or None,
                strategy=self._config.get("strategy", {}),
                active_event_id=self._config.get("active_event_id"),
            )
        except Exception:  # pragma: no cover - defensive; must never break the UI
            from data.event_context import empty_event_context
            return empty_event_context()

    def _build_strategy_context(self):
        """Canonical read model of the active strategy plan.

        State Consolidation 2: separates strategy-plan state (stint plan, stops,
        fuel burn per lap, config_id, degradation assumptions, tolerances) from
        the event/race configuration truth now owned by EventContext (see
        ``data/strategy_context.py``). Reads strategy-specific fields from the
        legacy ``config["strategy"]`` snapshot and event/race rules from
        ``_build_event_context()``. ``config["strategy"]`` remains as legacy
        compatibility. Never raises — returns an EMPTY-source context on failure.
        """
        try:
            from data.strategy_context import build_strategy_context
            return build_strategy_context(
                strategy=self._config.get("strategy", {}),
                event_context=self._build_event_context(),
                tyre_degradation=getattr(self, "_tyre_degradation_cache", None),
            )
        except Exception:  # pragma: no cover - defensive; must never break the UI
            from data.strategy_context import empty_strategy_context
            return empty_strategy_context()

    def _active_config_id(self) -> str:
        """The active race ``config_id`` (session match key) read from the
        canonical StrategyContext instead of raw ``config["strategy"]``.

        Legacy Fan-Out Removal Phase 1: ``config_id`` is strategy-plan state
        owned by StrategyContext, so display/history consumers read it here.
        Byte-identical to ``config["strategy"].get("config_id", "")`` — the
        context coerces the same value with ``str(...)`` (proven by test in
        tests/test_legacy_fanout_phase_1.py). Never raises.
        """
        return self._build_strategy_context().config_id

    def _push_session_tag(self) -> None:
        """Push a fresh frozen SessionTag into the telemetry dispatcher.

        Legacy Fan-Out Removal Phase 6a: the dispatcher no longer reads
        config["strategy"] in its telemetry event path — the UI pushes this
        immutable tag (track/car/config_id/event_id, built from the canonical
        EventContext + StrategyContext — byte-identical to the old raw reads
        when in sync, and since Phase 4 always in sync) whenever a tag-relevant
        field changes. Called at the end of _update_race_config (covers
        Set-as-Active, garage car select, and the session-config restore, all
        of which funnel through it) and from _on_event_save's active-event
        re-sync branch. Never raises.
        """
        try:
            if self._dispatcher is None:
                return
            from data.session_context import build_session_tag
            ev_ctx = self._build_event_context()
            self._dispatcher.set_session_tag(build_session_tag(
                track=ev_ctx.track,
                car=ev_ctx.car,
                config_id=self._active_config_id(),
                event_id=int(ev_ctx.event_id or 0),
            ))
        except Exception:  # pragma: no cover - defensive; must never break the UI
            pass

    def _build_session_context(self, *, has_practice_laps: bool = False,
                               has_valid_laps: bool = False):
        """Canonical read model of live telemetry / session status.

        SessionContext sprint: normalises the volatile tracker/session reads
        (connection, packet count, laps recorded, active session id, live mode)
        and the fuel-burn 3-tier fallback into one immutable snapshot, so
        consumers stop reaching into ``self._tracker`` internals and the legacy
        ``config["strategy"]`` fuel fallback. Byte-identical to the expressions
        it replaces (see data/session_context.py). The DB-derived practice-lap
        flags are caller-supplied (that query is owned by the dashboard/DB).
        Never raises.
        """
        try:
            from data.session_context import build_session_context
            tracker = self._tracker
            # Connection-signal sprint (2026-07-04): the REAL connection state
            # and packet count come from the UDPListener when wired (the
            # documented one-place change — Home's live_active and the
            # telemetry labels become real). Without a listener the legacy
            # tracker fallbacks apply (byte-identical: those attrs never
            # existed on the tracker, resolving False/0 — the old behaviour).
            listener = getattr(self, "_udp_listener", None)
            if listener is not None:
                connected = bool(getattr(listener, "connected", False))
                packet_count = getattr(listener, "total_received", 0)
            else:
                connected = bool(tracker is not None and getattr(tracker, "_connected", False))
                packet_count = getattr(tracker, "_packet_count", 0) if tracker is not None else 0
            return build_session_context(
                connected=connected,
                packet_count=packet_count,
                laps_recorded=getattr(tracker, "laps_recorded", 0) if tracker is not None else 0,
                telemetry_avg_fuel_per_lap=(
                    getattr(tracker, "avg_fuel_per_lap", 0.0) if tracker is not None else 0.0),
                active_session_id=getattr(self, "_active_session_id", None),
                loaded_session_avg_fuel=getattr(self, "_loaded_session_avg_fuel", 0.0),
                config_fuel_burn_per_lap=self._config.get("strategy", {}).get("fuel_burn_per_lap", 2.0),
                live_mode=self._config.get("live", {}).get("mode", "Race"),
                has_practice_laps=has_practice_laps,
                has_valid_laps=has_valid_laps,
            )
        except Exception:  # pragma: no cover - defensive; must never break the UI
            from data.session_context import empty_session_context
            return empty_session_context()

    def _build_strategy_inputs(self, fuel_burn_override=None):
        """Frozen AI-input snapshot for race-strategy analysis.

        AI Snapshot Migration: freezes one consistent set of race parameters
        from the canonical read models (EventContext race rules,
        StrategyContext plan fields, TrackContext identity) instead of live
        ``config["strategy"]`` reads at prompt time. Byte-identical to the
        legacy expressions when the stores are in sync; returns the fresh DB
        event values when the event was edited after "Set as Active" (the
        intentional difference — see docs/AI_SNAPSHOT_MIGRATION.md). Never
        raises; falls back to exact legacy expressions when no event context
        exists (recorded as a snapshot warning).
        """
        try:
            from data.analysis_inputs import build_strategy_inputs
            return build_strategy_inputs(
                event_context=self._build_event_context(),
                strategy_context=self._build_strategy_context(),
                track_context=self._build_track_context(),
                legacy_strategy=self._config.get("strategy", {}),
                fuel_burn_override=fuel_burn_override,
            )
        except Exception:  # pragma: no cover - defensive; must never break AI calls
            from data.analysis_inputs import build_strategy_inputs
            return build_strategy_inputs(
                legacy_strategy=self._config.get("strategy", {}),
                fuel_burn_override=fuel_burn_override,
            )

    def _build_practice_inputs(self, fuel_burn_override=None):
        """Frozen AI-input snapshot for practice analysis.

        Same as ``_build_strategy_inputs`` but preserves the practice
        path's DEF-P1-005 safe default (unknown tuning flag → locked).
        ``fuel_burn_override`` carries ``_computed_fuel_burn_lpl()``
        (telemetry-owned until a TelemetryContext sprint).
        """
        try:
            from data.analysis_inputs import build_practice_inputs
            return build_practice_inputs(
                event_context=self._build_event_context(),
                strategy_context=self._build_strategy_context(),
                track_context=self._build_track_context(),
                legacy_strategy=self._config.get("strategy", {}),
                fuel_burn_override=fuel_burn_override,
            )
        except Exception:  # pragma: no cover - defensive; must never break AI calls
            from data.analysis_inputs import build_practice_inputs
            return build_practice_inputs(
                legacy_strategy=self._config.get("strategy", {}),
                fuel_burn_override=fuel_burn_override,
            )







    def _fanout_event_to_strategy(self, evt_name: str) -> dict:
        """Write the WORKING-CONFIG core from the Event Planner widgets into
        ``config["strategy"]`` and return it.

        Fan-Out Rule-Cache Deletion (2026-07-04): the 12 event-RULE cache
        fields this helper used to duplicate (tyre wear, fuel mult, mandatory
        stops, weather, damage, refuel rate, required/available tyres,
        mandatory_compounds, bop, tuning, allowed categories) are **no longer
        written** — every consumer reads them DB-first through the canonical
        contexts (Phases 1–5 + Working Race Config), with ``config["events"]``
        covering the no-DB fallback. What remains is the legitimate
        working-config core: **track, race format/lengths (the match-key hash +
        lap-bank restore inputs) and event_id (session tagging)**.

        Phase 4 contract unchanged: config-dict only — no tracker / advisor /
        query-listener / UI-sync side effects, no persist (callers own those);
        strategy-PLAN fields (car, config_id, stops, fuel/tolerances) never
        touched.
        """
        strat = self._config.setdefault("strategy", {})
        strat["track"]               = self._evt_track.currentText()
        rt_str = self._evt_race_type.currentText()
        strat["race_type"]           = "timed" if "timed" in rt_str.lower() else "lap"
        strat["laps"]                = self._evt_laps.value()
        strat["total_laps"]          = self._evt_laps.value()
        strat["race_duration_minutes"] = self._evt_duration.value()
        strat["event_id"] = self._db.get_event_id(evt_name) if self._db is not None else 0
        return strat


    def _build_garage_tab(self) -> QWidget:
        widget = QWidget()
        outer_layout = QVBoxLayout(widget)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(6)
        outer_layout.addWidget(self._tab_intro_header(
            "Garage",
            "Browse cars, specs and BOP data. Next: find the car for your event "
            "and click Load to Event to send it to the active event and Setup "
            "Builder."))
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)
        outer_layout.addLayout(main_layout, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(6)

        self._garage_cat_combo = QComboBox()
        self._garage_cat_combo.addItems(["All", "Gr.1", "Gr.2", "Gr.3", "Gr.4", "Road Car"])
        self._garage_cat_combo.setStyleSheet(
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; border-radius: 3px; padding: 2px 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )
        self._garage_cat_combo.currentIndexChanged.connect(self._on_garage_filter_changed)
        left_layout.addWidget(self._garage_cat_combo)

        self._garage_car_list = QListWidget()
        self._garage_car_list.setStyleSheet(
            f"QListWidget {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; }}"
            "QListWidget::item:selected { background: #2A4A6A; }"
        )
        self._garage_car_list.currentRowChanged.connect(self._on_garage_car_selected)
        left_layout.addWidget(self._garage_car_list)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setSpacing(10)

        self._garage_car_name_lbl = QLabel("")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self._garage_car_name_lbl.setFont(title_font)
        self._garage_car_name_lbl.setStyleSheet(f"color: {_TEXT};")
        right_layout.addWidget(self._garage_car_name_lbl)

        self._garage_car_specs_lbl = QLabel("")
        self._garage_car_specs_lbl.setStyleSheet("color: #AAA; font-size: 12px;")
        self._garage_car_specs_lbl.setWordWrap(True)
        right_layout.addWidget(self._garage_car_specs_lbl)

        from ui import ngr_theme as _ngr_g
        self._btn_garage_select_event = QPushButton("Load to Event ↩")
        self._btn_garage_select_event.setStyleSheet(_ngr_g.primary_button_qss())
        self._btn_garage_select_event.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_garage_select_event.setVisible(False)
        self._btn_garage_select_event.clicked.connect(self._on_garage_select_for_event)
        right_layout.addWidget(self._btn_garage_select_event)

        setups_group = QGroupBox("Setups")
        setups_group.setStyleSheet(self._group_style())
        setups_layout = QVBoxLayout(setups_group)
        self._garage_setups_table = QTableWidget()
        self._garage_setups_table.setColumnCount(4)
        self._garage_setups_table.setHorizontalHeaderLabels(["Name", "Track", "Date", "Action"])
        self._garage_setups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._garage_setups_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Inherit the global NGR table styling.
        setups_layout.addWidget(self._garage_setups_table)
        right_layout.addWidget(setups_group)

        history_group = QGroupBox("Track Setup History")
        history_group.setStyleSheet(self._group_style())
        history_layout = QVBoxLayout(history_group)
        self._garage_track_combo = QComboBox()
        self._garage_track_combo.setStyleSheet(
            f"QComboBox {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; border-radius: 3px; padding: 2px 6px; }}"
            f"QComboBox QAbstractItemView {{ background: {_DARK_CARD}; color: {_TEXT}; }}"
        )
        self._garage_track_combo.currentIndexChanged.connect(self._garage_on_track_selected)
        history_layout.addWidget(self._garage_track_combo)
        self._garage_history_text = QTextEdit()
        self._garage_history_text.setReadOnly(True)
        self._garage_history_text.setMinimumHeight(120)
        self._garage_history_text.setStyleSheet(
            f"QTextEdit {{ background: {_DARK_CARD}; color: {_TEXT}; border: 1px solid #333; }}"
        )
        history_layout.addWidget(self._garage_history_text)
        right_layout.addWidget(history_group)

        sessions_group = QGroupBox("Session History")
        sessions_group.setStyleSheet(self._group_style())
        sessions_layout = QVBoxLayout(sessions_group)
        self._garage_sessions_table = QTableWidget()
        self._garage_sessions_table.setColumnCount(5)
        self._garage_sessions_table.setHorizontalHeaderLabels(["Date", "Track", "Type", "Laps", "Best Lap"])
        self._garage_sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._garage_sessions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._garage_sessions_table.setAlternatingRowColors(True)
        # Inherit the global NGR table styling.
        sessions_layout.addWidget(self._garage_sessions_table)
        right_layout.addWidget(sessions_group)

        right_layout.addStretch()
        right_scroll.setWidget(right_container)

        main_layout.addWidget(left_widget, 1)
        main_layout.addWidget(right_scroll, 2)

        self._refresh_garage_cars()
        return widget

    def _refresh_garage_cars(self) -> None:
        try:
            car_specs_path = Path(__file__).parent.parent / "data" / "car_specs.json"
            if not car_specs_path.exists():
                self._garage_car_list.clear()
                return
            with open(car_specs_path, "r", encoding="utf-8") as f:
                specs = json.load(f)
            cat_filter = self._garage_cat_combo.currentText()
            self._garage_car_list.clear()
            for car_name, car_data in sorted(specs.items()):
                if cat_filter != "All" and car_data.get("category", "") != cat_filter:
                    continue
                self._garage_car_list.addItem(car_name)
        except Exception:
            pass

    def _on_garage_filter_changed(self) -> None:
        self._refresh_garage_cars()

    def _on_garage_car_selected(self, row: int) -> None:
        if row < 0:
            return
        try:
            item = self._garage_car_list.item(row)
            if item is None:
                return
            car_name = item.text()
            self._garage_car_name_lbl.setText(car_name)

            car_specs_path = Path(__file__).parent.parent / "data" / "car_specs.json"
            specs_data = {}
            if car_specs_path.exists():
                with open(car_specs_path, "r", encoding="utf-8") as f:
                    specs_data = json.load(f).get(car_name, {})

            if specs_data:
                parts = []
                if "category"  in specs_data: parts.append(f"Category: {specs_data['category']}")
                if "pp_rating"  in specs_data: parts.append(f"PP: {specs_data['pp_rating']}")
                if "power_hp"   in specs_data: parts.append(f"Power: {specs_data['power_hp']} hp")
                if "weight_kg"  in specs_data: parts.append(f"Weight: {specs_data['weight_kg']} kg")
                if "drivetrain" in specs_data: parts.append(f"Drivetrain: {specs_data['drivetrain']}")
                self._garage_car_specs_lbl.setText("  |  ".join(parts))
            else:
                self._garage_car_specs_lbl.setText("No spec data available")

            if hasattr(self, "_btn_garage_select_event"):
                self._btn_garage_select_event.setVisible(bool(self._config.get("active_event_id")))

            # Reset track combo and history before repopulating
            self._garage_track_combo.blockSignals(True)
            self._garage_track_combo.clear()
            self._garage_track_combo.blockSignals(False)
            self._garage_history_text.clear()

            setups = self._config.get("car_setup", {}).get("setups", [])
            car_setups = [s for s in setups if s.get("name", "") == car_name or s.get("car", "") == car_name]
            self._garage_setups_table.setRowCount(0)
            from ui.setup_name_helper import setup_display_label
            for setup in car_setups:
                r = self._garage_setups_table.rowCount()
                self._garage_setups_table.insertRow(r)
                name_item = QTableWidgetItem(setup_display_label(setup))
                name_item.setData(Qt.ItemDataRole.UserRole, setup.get("id"))
                self._garage_setups_table.setItem(r, 0, name_item)
                for col, val in enumerate([setup.get("track", ""), setup.get("captured_at", setup.get("date", ""))], start=1):
                    self._garage_setups_table.setItem(r, col, QTableWidgetItem(str(val)))
                btn_load = QPushButton("Load")
                btn_load.setStyleSheet(
                    "QPushButton { background: #1A3A5C; color: white; border-radius: 3px; padding: 2px 8px; }"
                    "QPushButton:hover { background: #2A5A8C; }"
                )
                btn_load.clicked.connect(self._garage_load_setup)
                self._garage_setups_table.setCellWidget(r, 3, btn_load)

            self._garage_sessions_table.setRowCount(0)
            if self._db is not None:
                try:
                    car_sessions = [s for s in self._db.get_all_sessions(limit=60)
                                    if s.get("car_name") == car_name]
                    for s in car_sessions:
                        r = self._garage_sessions_table.rowCount()
                        self._garage_sessions_table.insertRow(r)
                        laps    = self._db.get_session_laps(s["id"])
                        best_ms = min((l["lap_time_ms"] for l in laps
                                       if l.get("lap_time_ms")), default=None)
                        best_str = ms_to_str(best_ms) if best_ms is not None else "—"
                        for col, val in enumerate([
                            str(s.get("date_utc", ""))[:16],
                            str(s.get("track", "")),
                            str(s.get("session_type", "")).capitalize(),
                            str(s.get("total_laps", "")),
                            best_str,
                        ]):
                            self._garage_sessions_table.setItem(r, col, QTableWidgetItem(val))
                except Exception:
                    import traceback; traceback.print_exc()

            # Also show DB-stored setups (from AI or manual save) alongside config ones
            if self._db is not None:
                try:
                    # Look up a car_id from recent sessions for this car name
                    _all = self._db.get_all_sessions(limit=10)
                    _car_id_db = next(
                        (s["car_id"] for s in _all if s.get("car_name") == car_name
                         and s.get("car_id", 0) > 0), 0)
                    if _car_id_db:
                        for db_setup in self._db.get_setups_for_car(_car_id_db):
                            r = self._garage_setups_table.rowCount()
                            self._garage_setups_table.insertRow(r)
                            label = db_setup.get("name") or db_setup.get("ai_notes", "")[:40] or "DB Setup"
                            created = str(db_setup.get("created_at", ""))[:16]
                            name_item = QTableWidgetItem(str(label))
                            name_item.setData(Qt.ItemDataRole.UserRole, db_setup.get("id"))
                            self._garage_setups_table.setItem(r, 0, name_item)
                            for col, val in enumerate(["", created], start=1):
                                self._garage_setups_table.setItem(r, col, QTableWidgetItem(val))
                            btn_load_db = QPushButton("Load")
                            btn_load_db.setStyleSheet(
                                "QPushButton { background: #1A3A5C; color: white; border-radius: 3px; padding: 2px 8px; }"
                                "QPushButton:hover { background: #2A5A8C; }"
                            )
                            btn_load_db.clicked.connect(self._garage_load_setup)
                            self._garage_setups_table.setCellWidget(r, 3, btn_load_db)
                        # Populate track combo from setup_recommendations
                        tracks = self._db.get_tracks_for_car_recommendations(_car_id_db)
                        if tracks:
                            self._garage_track_combo.addItems(tracks)
                            self._garage_track_combo.setEnabled(True)
                        else:
                            self._garage_track_combo.addItem("No recommendations yet")
                            self._garage_track_combo.setEnabled(False)
                            self._garage_history_text.setPlainText("No recommendations yet.")
                except Exception:
                    import traceback; traceback.print_exc()
        except Exception:
            import traceback; traceback.print_exc()

    def _garage_load_setup(self) -> None:
        selected = self._garage_setups_table.selectedItems()
        if not selected:
            return
        row = self._garage_setups_table.currentRow()
        item = self._garage_setups_table.item(row, 0)
        if item is None:
            return
        setup_id = item.data(Qt.ItemDataRole.UserRole)
        if not setup_id:
            return
        if self._db is None:
            return
        result = self._db.get_setup(setup_id)
        if result is None:
            QMessageBox.warning(self, "Load Failed", "Setup not found in database.")
            return
        self._fill_setup_fields(result["setup_dict"])
        self.select_tab(TAB_SETUP_BUILDER)

    def _garage_on_track_selected(self, index: int) -> None:
        track = self._garage_track_combo.currentText()
        if not track or track == "No recommendations yet":
            self._garage_history_text.clear()
            return
        if self._db is None:
            return
        car_name = self._garage_car_name_lbl.text()
        car_id = self._db.get_car_id(car_name)
        if not car_id:
            self._garage_history_text.clear()
            return
        text = self._db.get_setup_history_for_car_track(car_id, track, limit=10)
        self._garage_history_text.setPlainText(text if text else "No recommendations yet.")

    def _on_garage_select_for_event(self) -> None:
        try:
            car_name = self._garage_car_name_lbl.text()
            if not car_name:
                return
            self._config.setdefault("strategy", {})["car"] = car_name
            self._persist_config()
            self._sync_setup_builder_from_event()
            self._sync_strategy_from_event()
            # Refresh the advisor's event context + analysed-car scope so a
            # pre-drive Analyse for the newly selected car uses the correct
            # learning scope rather than a stale/zero car. A live packet will
            # re-sync _car_id_ref[0] the moment driving starts.
            if getattr(self, "_driving_advisor", None) is not None:
                try:
                    self._driving_advisor.set_event_context(self._active_event() or {})
                    if self._db is not None and car_name and car_name != "Unknown":
                        _cid = self._db.get_car_id(car_name)
                        _ref = getattr(self._driving_advisor, "_car_id_ref", None)
                        if _cid and isinstance(_ref, list) and _ref:
                            _ref[0] = int(_cid)
                except Exception:
                    pass
            self._bridge.event_log_entry.emit(f"Active car set: {car_name}")
            self.select_tab(TAB_EVENT_PLANNER)  # return to Event Planner
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Push-to-talk button detection now lives in its own canonical module so that
# ui/settings_ui.py (which owns the Settings handlers after the decomposition)
# and ui/dashboard.py share exactly ONE implementation. Re-exported here under
# the historical private name for any external references.
# ---------------------------------------------------------------------------
from ui.button_detect_dialog import (  # noqa: E402
    ButtonDetectDialog as _ButtonDetectDialog,
    _QT_TO_PYNPUT,
    _QT_MODIFIERS,
)
