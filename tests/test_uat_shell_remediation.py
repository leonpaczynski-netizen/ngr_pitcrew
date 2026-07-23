"""UAT remediation for the new NGR Pit Crew shell (2026-07-23 session).

Covers the six defects raised against the rebuilt shell:

  U-1  Garage Base/Qualifying snapped straight back to Race (the 750ms feed forced
       discipline="race"), so a base setup could never be built.
  U-2  "Read aloud" was silent — the announcer was called with the wrong signature.
  U-3  The guidance CTA was centre-clipped ("ld setup_base evide") in the 360px column.
  U-4  Home was an empty title page.
  U-5  No route to change or create an event.
  U-6  "Analyse setup" gave no feedback at all when pressed.
"""

import pytest

from PyQt6.QtWidgets import QApplication, QVBoxLayout

from ui.live_shell_bridge import LiveShellBridge
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Announcer:
    """Duck of VoiceAnnouncer.announce(text, priority, cooldown_key, ...)."""

    def __init__(self):
        self.calls = []

    def announce(self, text, priority, cooldown_key, cooldown_secs=0.0,
                 interrupt=False, version_key=""):
        self.calls.append((text, priority, cooldown_key))


class _Form:
    def __init__(self, values=None):
        self.values = dict(values or {"body_height_front": 80})
        self.applied = None

    def current_setup_dict(self):
        return dict(self.values)

    def apply_ai_fields(self, fields):
        self.applied = dict(fields)


class _Item:
    def __init__(self, text):
        self._t = text

    def text(self):
        return self._t


class _EventList:
    def __init__(self, names):
        self._names = list(names)
        self.current = -1

    def count(self):
        return len(self._names)

    def item(self, row):
        return _Item(self._names[row]) if 0 <= row < len(self._names) else None

    def setCurrentRow(self, row):
        self.current = row


class _Win:
    """A duck-typed MainWindow exposing only what the bridge legitimately uses."""

    def __init__(self):
        self._race_form = _Form({"body_height_front": 80})
        self._qual_form = _Form({"body_height_front": 60})
        self._announcer = _Announcer()
        self._event_list = _EventList(["GR Enduro Rd1", "GR Enduro Rd2"])
        self._driving_advisor = object()
        self.analysed = []
        self.baseline_built = 0
        self.activated = 0
        self.persisted = 0
        self.selected_tab = None

    def _setup_analyse_ai(self):
        self.analysed.append("race")

    def _setup_analyse_ai_for_form(self, form):
        self.analysed.append("qualifying" if form is self._qual_form else "other")

    def _generate_baseline_setup_both(self):
        self.baseline_built += 1

    def _on_event_set_active(self):
        self.activated += 1

    def _persist_config(self):
        self.persisted += 1

    def select_tab(self, key):
        self.selected_tab = key
        return True


@pytest.fixture
def wired(qapp):
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    win = _Win()
    bridge = LiveShellBridge(shell, ctrl, window=win, config={"voice": {"enabled": True}})
    return shell, win, bridge


def _cc_view():
    """A realistic Event Command Centre view dict."""
    return {
        "ok": True,
        "resolution_state": "one_active_event",
        "event": {"event_name": "GR Enduro Rd2", "series": "GR Enduro",
                  "round": "Rd2", "state": "", "current_phase": "practice"},
        "days_until_race": 3,
        "next_action": {"headline": "Build setup_base evidence",
                        "detail": "setup_base is the weakest domain (confidence: none).",
                        "target_surface": "setup", "tone": "warn"},
        "attention": [{"message": "Base Setup has no evidence yet.", "tone": "warn"}],
        "readiness": [["base_setup", "missing", "no evidence"],
                      ["race_setup", "thin", "1 run"]],
        "progress": {"practice_sessions": 2, "valid_laps": 14, "setup_experiments": 1},
        "timeline": [],
        "quick_actions": [{"label": "Event Briefing", "target_surface": "active_event"}],
        "candidates": [{"cycle_id": "cycle-gr-enduro-rd1", "event_name": "GR Enduro Rd1",
                        "series": "GR Enduro", "round": "Rd1"},
                       {"cycle_id": "cycle-gr-enduro-rd2", "event_name": "GR Enduro Rd2",
                        "series": "GR Enduro", "round": "Rd2"}],
        "recent_learning": ["Softer rear ARB helped mid-corner rotation."],
        "fingerprint": "fp-1",
    }


class TestU1GarageDisciplineIsSticky:
    def test_selecting_qualifying_survives_a_refresh(self, wired):
        shell, win, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        assert bridge._discipline == "qualifying"
        bridge.refresh()
        bridge.refresh()
        assert shell.garage_page.current_discipline() == "qualifying"

    def test_qualifying_shows_the_qualifying_sheet(self, wired):
        shell, win, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        bridge.refresh()
        assert shell.garage_page.current_discipline() == "qualifying"
        # The values fed to the sheet came from the QUALIFYING form, not the Race one.
        assert bridge._form_for_discipline() is win._qual_form

    def test_building_the_initial_setup_is_always_available(self, wired):
        """UAT-5: the Base TAB is gone (there is no third sheet); authoring both sheets
        is an action, always reachable from either discipline."""
        shell, win, bridge = wired
        bridge.refresh()
        assert shell.garage_page._baseline.isVisibleTo(shell.garage_page) is True
        assert "initial setup" in shell.garage_page._baseline.text().lower()
        shell.garage_page._baseline.click()
        assert win.baseline_built == 1

    def test_there_is_no_base_discipline(self, wired):
        shell, _win, _bridge = wired
        assert set(shell.garage_page._selector._buttons) == {"race", "qualifying"}

    def test_a_race_recommendation_is_not_shown_under_qualifying(self, wired):
        """The window keeps ONE recommendation VM; showing the Race one on the
        Qualifying tab would let Apply write Race deltas into the Qualifying sheet."""
        shell, win, bridge = wired
        from ui.setup_recommendation_vm import build_recommendation_vm
        rec = build_recommendation_vm({
            "status": "approved",
            "changes": [{"field": "body_height_front", "from": 80, "to": 70,
                         "reason": "reduce understeer"}],
        })
        win.current_recommendation_vm = lambda: rec
        bridge.refresh()
        assert shell.garage_page._vm.proposed_rows()          # Race: shown
        shell.garage_page._selector._buttons["qualifying"].click()
        assert shell.garage_page._vm.proposed_rows() == ()    # Qualifying: withheld
        shell.garage_page._selector._buttons["race"].click()
        assert shell.garage_page._vm.proposed_rows()          # back on its own sheet

    def test_apply_targets_the_selected_discipline_form(self, wired):
        shell, win, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        shell.garage_page.apply_requested.emit({"body_height_front": 55})
        assert win._qual_form.applied == {"body_height_front": 55}
        assert win._race_form.applied is None


class TestU2ReadAloud:
    def test_uses_the_real_announcer_signature(self, wired):
        shell, win, bridge = wired
        shell.guidance.read_aloud_requested.emit("Box this lap")
        assert len(win._announcer.calls) == 1
        text, _priority, cooldown_key = win._announcer.calls[0]
        assert text == "Box this lap"
        assert cooldown_key == "shell_read_aloud"

    def test_voice_disabled_is_reported_not_silent(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _Win()
        bridge = LiveShellBridge(shell, ctrl, window=win,
                                 config={"voice": {"enabled": False}})
        shell.guidance.read_aloud_requested.emit("Box this lap")
        assert win._announcer.calls == []
        assert "Settings" in shell.guidance._status.text()

    def test_empty_text_never_speaks(self, wired):
        shell, win, bridge = wired
        shell.guidance.read_aloud_requested.emit("")
        assert win._announcer.calls == []


class TestU3GuidanceCtaFits:
    def test_actions_are_stacked_full_width(self, wired):
        shell, _win, _bridge = wired
        card = shell.guidance
        parent_layout = card._primary.parentWidget().layout()
        # Both CTAs live in the same vertical sub-layout (not a shared row).
        found = None
        for i in range(parent_layout.count()):
            sub = parent_layout.itemAt(i).layout()
            if sub is not None and sub.indexOf(card._primary) >= 0:
                found = sub
        assert isinstance(found, QVBoxLayout)
        assert found.indexOf(card._secondary) >= 0

    def test_long_label_is_not_lost(self, wired):
        shell, _win, _bridge = wired
        view = _cc_view()
        # A long non-evidence CTA (evidence objectives are relabelled to a run action).
        view["next_action"]["headline"] = "Confirm and protect the current best-known setup"
        shell.set_guidance_view(view)
        card = shell.guidance
        assert card._primary.text() == "Confirm and protect the current best-known setup"
        # Even if the pixel width clipped it, the full wording stays reachable.
        assert card._primary.toolTip() == card._primary.text()


class TestU4HomeSaysSomething:
    def test_home_renders_the_command_centre(self, wired):
        shell, _win, _bridge = wired
        shell.set_guidance_view(_cc_view())
        home = shell.home_page
        assert home._event_title.text() == "GR Enduro Rd2"
        assert "3 days to race" in home._event_state.text()
        # An evidence objective is restated as the run that actually produces it.
        assert home._next_headline.text() == "Start a baseline run"
        assert "no recorded runs yet" in home._attention.text()
        assert home._readiness_box.count() == 2
        assert "14 valid laps" in home._evidence.text()
        assert "rear ARB" in home._learning.text()

    def test_home_without_a_view_says_so(self, wired):
        shell, _win, _bridge = wired
        shell.set_guidance_view(None)
        assert shell.home_page._event_title.text() == "No active event"
        assert shell.home_page._btn_next.text() == ""

    def test_next_action_navigates(self, wired):
        """An evidence objective routes to Practice — the run card is the only place
        that can produce the evidence. It used to send the driver back to the Garage
        they were already standing in (UAT-3)."""
        shell, _win, _bridge = wired
        shell.set_guidance_view(_cc_view())
        shell.home_page._btn_next.click()
        assert shell.current_destination() == "practice"

    def test_repeat_render_is_a_no_op(self, wired):
        """The 750ms feed must not rebuild the event combo under the cursor."""
        shell, _win, bridge = wired
        shell.set_guidance_view(_cc_view())
        shell.home_page._event_combo.setCurrentIndex(1)
        shell.set_guidance_view(_cc_view())
        assert shell.home_page._event_combo.currentIndex() == 1


class TestU5EventSelection:
    def test_switch_activates_through_the_classic_path(self, wired):
        shell, win, _bridge = wired
        shell.set_guidance_view(_cc_view())
        shell.home_page._event_combo.setCurrentIndex(0)
        shell.home_page._btn_switch.click()
        assert win._event_list.current == 0          # picked "GR Enduro Rd1"
        assert win.activated == 1                    # via _on_event_set_active
        assert win.persisted == 1

    def test_manage_opens_the_event_planner(self, wired):
        shell, win, _bridge = wired
        classic = []
        shell.classic_ui_requested.connect(lambda: classic.append(True))
        shell.home_page._btn_manage.click()
        assert classic == [True]
        assert win.selected_tab == "event_planner"

    def test_no_candidates_hides_the_switcher(self, wired):
        shell, _win, _bridge = wired
        view = _cc_view()
        view["candidates"] = []
        view["fingerprint"] = "fp-2"
        shell.set_guidance_view(view)
        assert shell.home_page._event_combo.isVisibleTo(shell.home_page) is False


class TestU6AnalyseFeedback:
    def test_analyse_reports_it_started(self, wired):
        shell, win, _bridge = wired
        shell.garage_page.analyse_requested.emit()
        assert win.analysed == ["race"]
        assert "Analysing" in shell.garage_page._status.text()

    def test_analyse_uses_the_qualifying_path(self, wired):
        shell, win, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        shell.garage_page.analyse_requested.emit()
        assert win.analysed == ["qualifying"]

    def test_missing_advisor_is_reported(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _Win()
        win._driving_advisor = None
        LiveShellBridge(shell, ctrl, window=win, config={})
        shell.garage_page.analyse_requested.emit()
        assert win.analysed == []
        assert "unavailable" in shell.garage_page._status.text()

    def test_switching_discipline_clears_stale_status(self, wired):
        shell, _win, _bridge = wired
        shell.garage_page.analyse_requested.emit()
        assert shell.garage_page._status.text() != ""
        shell.garage_page._selector._buttons["qualifying"].click()
        assert shell.garage_page._status.text() == ""
