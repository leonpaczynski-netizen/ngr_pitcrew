"""PitCrewShell — the new NGR Pit Crew application shell (F1).

Composes the persistent chrome (nav rail, event header, progress rail, guided-
action column with the Engineer Guidance card) around a stack of pages, all driven
by a single ``PitCrewController``. This is the visible replacement surface; it runs
behind a launch flag alongside the old dashboard until the F9 cutover.

The shell renders state — it holds no engineering logic. It reads ``AppState`` from
the controller for chrome, and is handed the Event Command Centre view dict for the
guidance card via ``set_guidance_view`` (the integration layer builds that dict off
the Qt thread and passes it in).
"""

from __future__ import annotations

from typing import Optional, Mapping

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QLabel,
)

from ui import ngr_theme as _t
from ui.app_state import AppState, NAV_DESTINATIONS
from ui.pit_crew_controller import PitCrewController
from ui.components import (
    NavRail, EventHeaderBar, ProgressRail, EngineerGuidanceCard, EngineerGuidanceVM,
    SectionHeading, SetupWorkspace, RunCard,
)
from ui.components.practice_feedback import StructuredFeedbackForm
from ui.components.practice_outcome import PracticeOutcome
from ui.components.qualifying_readiness import QualifyingReadiness
from ui.components.strategy_plan import StrategyPlanView
from ui.components.live_pit_wall import LivePitWall
from ui.components.debrief_view import DebriefView
from ui.components.engineering_library import EngineeringLibrary
from ui.components.home_page import HomePage
from ui.components.setup_workspace import SetupDisciplineSelector as _Seg
from ui.components.nav_rail import NAV_LABELS


# A programme stage → the nav destination that hosts it.
STAGE_TO_NAV: dict[str, str] = {
    "briefing": "active_event",
    "garage": "garage",
    "practice": "practice",
    "review": "practice",
    "qualifying": "qualifying",
    "strategy": "race_strategy",
    "race": "live_pit_wall",
    "debrief": "debrief",
}

# A command-centre target_surface → the nav destination that performs it.
SURFACE_TO_NAV: dict[str, str] = {
    "setup": "garage", "garage": "garage",
    "practice": "practice", "coaching": "practice",
    "strategy": "race_strategy",
    "live": "live_pit_wall",
    "debrief": "debrief",
    "active_event": "active_event", "home": "home",
    "programme": "programme",
    "qualifying": "qualifying", "settings": "settings",
    "engineering_library": "engineering_library",
    "track_model": "track_model", "track_modelling": "track_model",
}


class _SimplePage(QWidget):
    """A minimal page: a title + a body area other stages fill in later."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)
        lay.addWidget(SectionHeading(title, level=1))
        self._subtitle = QLabel(subtitle)
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._subtitle)
        self.body = lay
        lay.addStretch(1)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text or "")


class ActiveEventPage(_SimplePage):
    """Event Arrival / Briefing — shows the active event identity + progress."""

    def __init__(self, parent=None):
        super().__init__("ACTIVE EVENT", "No active event.", parent)
        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
        # Insert detail above the trailing stretch.
        self.body.insertWidget(self.body.count() - 1, self._detail)

    def render(self, app_state: AppState, view: Optional[Mapping]) -> None:
        if not isinstance(app_state, AppState):
            app_state = AppState.empty()
        if app_state.has_active_event:
            self.set_subtitle(
                f"{app_state.event_name} — {app_state.car} at {app_state.track}"
            )
        else:
            self.set_subtitle("No active event. Create or select an NGR event to begin.")
        # Progress summary (defensive) from the command-centre view.
        if isinstance(view, Mapping):
            prog = view.get("progress") or {}
            try:
                self._detail.setText(
                    f"Practice sessions: {int(prog.get('practice_sessions', 0) or 0)}   ·   "
                    f"Valid laps: {int(prog.get('valid_laps', 0) or 0)}   ·   "
                    f"Setup experiments: {int(prog.get('setup_experiments', 0) or 0)}"
                )
            except Exception:
                self._detail.setText("")
        else:
            self._detail.setText("")


class PitCrewShell(QMainWindow):
    #: Emitted when the user asks for the classic tools/dashboard (setup analysis,
    #: track modelling, full settings) that the new shell does not yet own.
    classic_ui_requested = pyqtSignal()

    def __init__(self, controller: Optional[PitCrewController] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrPitCrewShell")
        self.setWindowTitle("NGR Pit Crew")
        self._controller = controller or PitCrewController(self)

        self.setStyleSheet(_t.app_stylesheet())

        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left: nav rail
        self.nav = NavRail()
        self.nav.setFixedWidth(184)
        outer.addWidget(self.nav)

        # Right of nav: header + rail + (content | guidance)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self.header = EventHeaderBar()
        right.addWidget(self.header)

        self.rail = ProgressRail()
        self.rail.setStyleSheet(f"background: {_t.CARBON};")
        right.addWidget(self.rail)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self.pages = QStackedWidget()
        self.pages.setStyleSheet(f"background: {_t.CARBON};")
        self._page_by_dest: dict[str, QWidget] = {}
        self._build_pages()
        content.addWidget(self.pages, 1)

        # Guided-action column (persistent right) hosting the guidance card
        guided = QWidget()
        guided.setObjectName("ngrGuidedColumn")
        guided.setFixedWidth(360)
        guided.setStyleSheet(f"#ngrGuidedColumn {{ background: {_t.INK_BLACK}; }}")
        gcol = QVBoxLayout(guided)
        gcol.setContentsMargins(_t.SPACE_MD, _t.SPACE_MD, _t.SPACE_MD, _t.SPACE_MD)
        self.guidance = EngineerGuidanceCard()
        gcol.addWidget(self.guidance)
        gcol.addStretch(1)
        content.addWidget(guided, 0)

        right.addLayout(content, 1)
        outer.addLayout(right, 1)
        self.setCentralWidget(central)

        # Wiring
        self.nav.navigate.connect(self._navigate)
        self.rail.stage_selected.connect(self._on_stage_selected)
        self.guidance.primary_requested.connect(self._on_guidance_surface)
        self.guidance.secondary_requested.connect(self._on_guidance_surface)
        self._controller.state_changed.connect(self._on_state)

        self._current_dest = "home"
        self._navigate("home")
        self._on_state(self._controller.state())

    # ---- page construction -----------------------------------------------
    def _build_pages(self) -> None:
        self.active_event_page = ActiveEventPage()
        titles = {
            "home": ("HOME", "What should I do next?"),
            "garage": ("GARAGE", "Which setup should I run?"),
            "practice": ("PRACTICE", "What are we testing — and did it work?"),
            "qualifying": ("QUALIFYING", "Am I ready?"),
            "race_strategy": ("RACE STRATEGY", "What is the plan?"),
            "live_pit_wall": ("LIVE PIT WALL", "What do I need to do now?"),
            "debrief": ("DEBRIEF", "What did we learn?"),
            "track_model": ("TRACK MODEL", "Teach the app a circuit."),
            "engineering_library": ("ENGINEERING LIBRARY", "Evidence, rules and advanced detail."),
            "settings": ("SETTINGS", "Configuration."),
        }
        from ui.components.programme_map import ProgrammeMapPage
        self.programme_page = ProgrammeMapPage()
        self.garage_page = SetupWorkspace()
        self.practice_page = self._build_practice_page()
        self.qualifying_page = QualifyingReadiness()
        self.strategy_page = StrategyPlanView()
        self.live_page = LivePitWall()
        self.debrief_page = DebriefView()
        from ui.components.track_modelling import TrackModellingPage
        self.track_model_page = TrackModellingPage()
        self.library_page = EngineeringLibrary()
        self.settings_page = self._build_settings_page()
        self.home_page = HomePage()
        self.home_page.navigate_requested.connect(self._on_guidance_surface)
        # Event setup is native: creating or switching an event never opens the old UI.
        from ui.components.event_setup import EventSetupPage
        from ui.gt7_data import GT7_CARS, GT7_TRACKS
        self.event_setup_page = EventSetupPage(tracks=GT7_TRACKS, cars=GT7_CARS)
        self.event_setup_page.cancelled.connect(lambda: self._navigate("home"))
        self.home_page.manage_events_requested.connect(
            lambda: self._navigate("event_setup"))
        self._page_by_dest["event_setup"] = self._scrollable(self.event_setup_page)
        self.pages.addWidget(self._page_by_dest["event_setup"])
        for dest in NAV_DESTINATIONS:
            if dest == "home":
                page = self.home_page
            elif dest == "programme":
                page = self.programme_page
            elif dest == "active_event":
                page = self.active_event_page
            elif dest == "garage":
                page = self.garage_page
            elif dest == "practice":
                page = self.practice_page
            elif dest == "qualifying":
                page = self.qualifying_page
            elif dest == "race_strategy":
                page = self.strategy_page
            elif dest == "live_pit_wall":
                page = self.live_page
            elif dest == "debrief":
                page = self.debrief_page
            elif dest == "track_model":
                page = self.track_model_page
            elif dest == "engineering_library":
                page = self.library_page
            elif dest == "settings":
                page = self.settings_page
            else:
                t, sub = titles.get(dest, (NAV_LABELS.get(dest, dest), ""))
                page = _SimplePage(t, sub)
            wrapper = self._scrollable(page)
            self._page_by_dest[dest] = wrapper
            self.pages.addWidget(wrapper)

    def _scrollable(self, page: QWidget) -> QWidget:
        """Wrap a page so its content scrolls when it is taller than the viewport.

        Without this the QStackedWidget sized to the tallest page and the window opened
        taller than the screen — everything "fit", so nothing scrolled and the bottom of
        long pages (Garage sheet, Strategy, Programme) was simply off-screen. Every page
        is wrapped uniformly; a page that already scrolls internally just nests harmlessly
        (the inner area handles the wheel).
        """
        from PyQt6.QtWidgets import QScrollArea, QFrame
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.setWidget(page)
        return area

    def _build_practice_page(self) -> QWidget:
        from PyQt6.QtWidgets import (
            QStackedWidget, QToolButton, QButtonGroup, QScrollArea, QFrame,
        )
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)

        top = QHBoxLayout()
        top.addWidget(SectionHeading("PRACTICE", level=1))
        top.addSpacing(_t.SPACE_LG)
        grp = QButtonGroup(page)
        grp.setExclusive(True)
        self._practice_stack = QStackedWidget()
        self._btn_runcard = QToolButton()
        self._btn_runcard.setText("Run card")
        self._btn_review = QToolButton()
        self._btn_review.setText("Review")
        self._btn_outcome = QToolButton()
        self._btn_outcome.setText("Outcome")
        for b in (self._btn_runcard, self._btn_review, self._btn_outcome):
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_Seg._qss())
            grp.addButton(b)
            top.addWidget(b)
        top.addStretch(1)
        self._btn_runcard.setChecked(True)
        self._btn_runcard.clicked.connect(lambda: self._practice_stack.setCurrentIndex(0))
        self._btn_review.clicked.connect(lambda: self._practice_stack.setCurrentIndex(1))
        self._btn_outcome.clicked.connect(lambda: self._practice_stack.setCurrentIndex(2))
        lay.addLayout(top)

        self.run_card = RunCard()
        # Review = what the run MEASURED, then how it felt. The feedback form on its own
        # asked the driver to rate a run they had no record of.
        from ui.components.run_laps import RunLapsPanel
        review_page = QWidget()
        rp = QVBoxLayout(review_page)
        rp.setContentsMargins(0, 0, 0, 0)
        rp.setSpacing(_t.SPACE_LG)
        self.run_laps = RunLapsPanel()
        rp.addWidget(self.run_laps)
        self.feedback_form = StructuredFeedbackForm()
        rp.addWidget(self.feedback_form)
        rp.addStretch(1)
        review_scroll = QScrollArea()
        review_scroll.setWidgetResizable(True)
        review_scroll.setFrameShape(QFrame.Shape.NoFrame)
        review_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        review_scroll.setWidget(review_page)

        self.practice_outcome = PracticeOutcome()
        self._practice_stack.addWidget(self.run_card)
        self._practice_stack.addWidget(review_scroll)
        self._practice_stack.addWidget(self.practice_outcome)
        lay.addWidget(self._practice_stack, 1)
        # After submitting feedback, surface the Outcome view.
        self.feedback_form.submitted.connect(
            lambda _d: (self._btn_outcome.setChecked(True),
                        self._practice_stack.setCurrentIndex(2)))
        return page

    def _build_settings_page(self) -> QWidget:
        from ui.components.settings_page import SettingsPage
        page = SettingsPage()
        page.open_classic_requested.connect(lambda: self.classic_ui_requested.emit())
        return page

    # ---- navigation -------------------------------------------------------
    def _navigate(self, dest: str) -> None:
        if dest not in self._page_by_dest:
            dest = "home"
        self._current_dest = dest
        self.pages.setCurrentWidget(self._page_by_dest[dest])
        self.nav.set_active(dest)

    def current_destination(self) -> str:
        return self._current_dest

    def _on_stage_selected(self, stage_key: str) -> None:
        self._navigate(STAGE_TO_NAV.get(stage_key, "active_event"))

    def _on_guidance_surface(self, surface: str) -> None:
        if not surface:
            return
        self._navigate(SURFACE_TO_NAV.get(surface, "home"))

    # ---- state rendering --------------------------------------------------
    def _on_state(self, app_state: AppState) -> None:
        if not isinstance(app_state, AppState):
            app_state = AppState.empty()
        # PyQt6 ABORTS the process on an unhandled exception inside a slot, so a single
        # bad field in a context would take the whole app down mid-session. Each chrome
        # render is isolated: one failing surface must never kill the others or the app.
        for render in (
            lambda: self.header.bind(app_state),
            lambda: self.rail.set_state(app_state),
            lambda: self.active_event_page.render(app_state, self._last_view),
            lambda: self.home_page.render(app_state, self._last_view),
        ):
            try:
                render()
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[PitCrewShell] chrome render failed: {exc}")

    _last_view: Optional[Mapping] = None

    def set_guidance_view(self, view: Optional[Mapping]) -> None:
        """Feed the Event Command Centre view dict; updates guidance + active-event."""
        self._last_view = view
        state = self._controller.state()
        for render in (
            lambda: self.guidance.set_vm(EngineerGuidanceVM.from_command_centre(
                view, active_setup_label=state.active_setup_label,
                active_setup_applied=state.active_setup_applied)),
            lambda: self.active_event_page.render(state, view),
            lambda: self.home_page.render(state, view),
        ):
            try:
                render()
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[PitCrewShell] guidance render failed: {exc}")
