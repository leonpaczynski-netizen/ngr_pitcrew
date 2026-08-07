"""Phase 2: close the feedback loop — B2, B3, B5, B6, B7, B8, B9.

Phase 0 made new-shell feedback reach the database (B1) and widened the schema to hold
all fourteen fields (B4). Everything else about the loop was still broken: the analysis
read a stale copy, an internal error turned a reported problem into an all-clear, two
classic fields were destroyed on every write, the acknowledgement could not reach the
new shell, three reported states had no representation at all, a verdict about one run
drove the analysis of the next, and a suppressed rule left no trace.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.session_db import (
    FEEDBACK_LABEL_KEYS, normalise_feedback, normalise_feedback_values,
)
from strategy.setup_diagnosis import (
    build_feedback_dispositions, build_setup_diagnosis,
    driver_feel_flags_from_feedback,
)


# ---------------------------------------------------------------------------
# B5 — the classic form destroyed two fields on every write
# ---------------------------------------------------------------------------
def test_the_two_mangled_labels_now_have_explicit_keys():
    """label.lower().replace(" ","_") yields "mid-corner" (the hyphen survives) and
    "rear_under_braking", while every reader wants "mid_corner"/"rear_braking". Those
    two fields persisted as empty string on EVERY write since the form was built."""
    assert FEEDBACK_LABEL_KEYS["Mid-Corner"] == "mid_corner"
    assert FEEDBACK_LABEL_KEYS["Rear Under Braking"] == "rear_braking"


def test_no_key_is_derived_from_a_display_label():
    """A display label is not a data key. Every classic row states its key."""
    for label, key in FEEDBACK_LABEL_KEYS.items():
        assert key == key.lower()
        assert " " not in key and "-" not in key


def test_the_classic_form_emits_the_canonical_keys():
    import inspect

    import ui.dashboard as dash
    src = inspect.getsource(dash)
    assert "FEEDBACK_LABEL_KEYS" in src, "the classic form no longer uses the key map"


# ---------------------------------------------------------------------------
# B7 — capture wording the brain could not read
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("Too much understeer", "understeer"),
    ("Too much oversteer", "oversteer"),
    ("Pushes wide", "understeer"),
    ("Rear loose on throttle", "oversteer"),
    ("Steps out", "oversteer"),
])
def test_classic_wording_maps_to_the_brains_vocabulary(raw, expected):
    assert normalise_feedback_values({"corner_entry": raw})["corner_entry"] == expected


def test_unmapped_wording_passes_through_rather_than_becoming_something_else():
    """A state nobody has taught the brain is reported as-is, not silently coerced."""
    out = normalise_feedback_values({"corner_entry": "some new state"})
    assert out["corner_entry"] == "some new state"


def test_free_text_is_never_rewritten():
    notes = "Too much understeer everywhere, felt awful"
    assert normalise_feedback_values({"notes": notes})["notes"] == notes


def test_a_classic_form_dict_reaches_the_brain_end_to_end():
    """The whole point: mangled keys AND classic wording, straight into the diagnosis."""
    raw = {"corner_entry": "Too much understeer", "mid-corner": "Pushes wide",
           "rear_under_braking": "Steps out"}
    flags = build_setup_diagnosis([], {}, "X", {}, None, feedback=raw)["driver_feel_flags"]
    assert flags["entry_understeer"] is True
    assert flags["mid_corner_understeer"] is True


@pytest.mark.parametrize("field,value,flag", [
    ("mid_corner", "Oversteer", "mid_corner_oversteer"),
    ("exit_stability", "Understeer", "exit_understeer"),
    ("gear_choice", "Too short", "gearing_too_short"),
])
def test_the_three_swallowed_states_are_now_represented(field, value, flag):
    """Each was documented "intentionally unmapped" and simply vanished between the
    dropdown and the diagnosis."""
    assert driver_feel_flags_from_feedback({field: value})[flag] is True


def test_a_swallowed_state_is_reported_back_as_deferred_not_treated():
    """They deliberately have no addressing fields — inventing a lever would be worse
    than admitting there is not one yet. What matters is that it is SAID."""
    flags = driver_feel_flags_from_feedback({"mid_corner": "Oversteer"})
    dispositions = build_feedback_dispositions({"driver_feel_flags": flags}, set())
    assert [d["state"] for d in dispositions] == ["deferred"]
    assert "Mid-corner oversteer" in dispositions[0]["feedback"]


def test_mid_corner_oversteer_is_not_routed_to_the_exit_flag():
    """Routing it to rear_loose_on_exit would apply an exit fix to a mid-corner
    problem — a wrong answer dressed as a right one."""
    flags = driver_feel_flags_from_feedback({"mid_corner": "Oversteer"})
    assert flags["rear_loose_on_exit"] is False
    assert flags["snap_oversteer_exit"] is False


# ---------------------------------------------------------------------------
# B3 — an internal error must not become an all-clear
# ---------------------------------------------------------------------------
def _force_inner_failure(monkeypatch, exc=ValueError("bad lap")):
    import strategy.setup_diagnosis as sd
    monkeypatch.setattr(sd, "_build_setup_diagnosis_inner",
                        lambda *a, **k: (_ for _ in ()).throw(exc))


def test_a_failed_diagnosis_keeps_the_drivers_answers(monkeypatch):
    """One bad value made the whole diagnosis throw, and the fallback shipped
    driver_feel_flags: {} — so a driver who reported five problems saw "no change
    recommended" with no error anywhere."""
    _force_inner_failure(monkeypatch)
    fb = {"corner_entry": "Understeer", "mid_corner": "Understeer",
          "exit_stability": "Oversteer"}
    d = build_setup_diagnosis([], {}, "X", {}, None, feedback=fb)
    assert d["driver_feel_flags"]["entry_understeer"] is True
    assert d["driver_feel_flags"]["mid_corner_understeer"] is True
    assert d["driver_feel_flags"]["rear_loose_on_exit"] is True


def test_a_failed_diagnosis_says_it_failed(monkeypatch):
    _force_inner_failure(monkeypatch)
    d = build_setup_diagnosis([], {}, "X", {}, None, feedback={})
    assert d["diagnosis_degraded"] is True
    assert "bad lap" in d["diagnosis_degraded_reason"]


def test_a_healthy_diagnosis_is_not_marked_degraded():
    d = build_setup_diagnosis([], {}, "X", {}, None, feedback={})
    assert d["diagnosis_degraded"] is False
    assert d["diagnosis_degraded_reason"] == ""


def test_the_degraded_flag_survives_a_junk_feedback_dict(monkeypatch):
    _force_inner_failure(monkeypatch)
    d = build_setup_diagnosis([], {}, "X", {}, None, feedback={"corner_entry": object()})
    assert d["diagnosis_degraded"] is True
    assert isinstance(d["driver_feel_flags"], dict)


def test_the_analysis_headline_never_reads_as_a_clean_bill_of_health():
    from services.setup_service import AnalysisResult
    r = AnalysisResult(ok=True, diagnosis_degraded=True,
                       diagnosis_degraded_reason="ValueError: bad lap")
    assert "PARTIAL evidence" in r.headline
    assert "unproven" in r.headline


# ---------------------------------------------------------------------------
# B6 — the acknowledgement the new shell could not show
# ---------------------------------------------------------------------------
def test_analysis_result_carries_the_dispositions():
    from services.setup_service import AnalysisResult
    r = AnalysisResult(ok=True, feedback_dispositions=(
        {"feedback": "Mid-corner understeer", "state": "addressed",
         "detail": "Change(s) applied: arb_front."},
        {"feedback": "High fuel use", "state": "strategy", "detail": "..."},
    ))
    ack = r.acknowledgement
    assert "addressed: Mid-corner understeer" in ack
    assert "strategy: High fuel use" in ack


def test_no_dispositions_means_no_acknowledgement_rather_than_a_fake_one():
    from services.setup_service import AnalysisResult
    assert AnalysisResult(ok=True).acknowledgement == ""


def test_the_service_extracts_dispositions_from_the_engine_payload():
    import inspect

    import services.setup_service as svc
    src = inspect.getsource(svc)
    assert 'data.get("feedback_dispositions")' in src


# ---------------------------------------------------------------------------
# B9 — a suppressed rule must leave a trace
# ---------------------------------------------------------------------------
def test_suppression_records_a_rejection_with_a_reason():
    from strategy.setup_rule_engine import _record_suppression
    rejected: list = []
    rule = SimpleNamespace(field="arb_front", symptom="understeer", rule_id="C3",
                           risk="low", base_confidence="medium", pack="B")
    _record_suppression(rejected, rule, "locked by the event",
                        "the event rules do not permit tuning arb_front")
    assert len(rejected) == 1
    assert rejected[0].field == "arb_front"
    assert "SUPPRESSED (locked by the event)" in rejected[0].rationale
    assert rejected[0].delta == 0.0


@pytest.mark.parametrize("reason", [
    "contraindicated", "field protected", "locked by the event",
    "already at the limit",
])
def test_every_named_suppression_path_is_wired(reason):
    """The four the register names. Preconditions-not-met is deliberately NOT one:
    a rule that does not apply is not a suppression."""
    import inspect

    import strategy.setup_rule_engine as eng
    src = inspect.getsource(eng._process_rule)
    assert f'"{reason}"' in src


def test_a_rule_that_simply_does_not_apply_is_not_recorded():
    import inspect

    import strategy.setup_rule_engine as eng
    src = inspect.getsource(eng._process_rule)
    precondition_block = src.split("Evaluate preconditions")[1].split("return")[0]
    assert "_record_suppression" not in precondition_block


# ---------------------------------------------------------------------------
# B2 / B8 — the bridge reads the live form, and drops stale verdicts
# ---------------------------------------------------------------------------
class _Form:
    def __init__(self, values=None):
        self._v = dict(values or {})
        self.reset_calls = 0

    def current_feedback(self):
        return dict(self._v)

    def reset(self):
        self.reset_calls += 1
        self._v = {}


def _bridge(form=None, last=None):
    from ui.live_shell_bridge import LiveShellBridge
    stub = SimpleNamespace()
    stub._shell = SimpleNamespace(feedback_form=form)
    stub._last_feedback = dict(last or {})
    stub._current_feedback = LiveShellBridge._current_feedback.__get__(stub)
    stub._reset_feedback_form = LiveShellBridge._reset_feedback_form.__get__(stub)
    stub._run_status = lambda _m: None
    stub._clear_feedback = LiveShellBridge._clear_feedback.__get__(stub)
    return stub


def test_analyse_reads_answers_that_were_never_submitted():
    """Fill in all fourteen dropdowns, go to the Garage, press Analyse without
    pressing Submit — 100% of it was ignored, and the headline blamed missing
    evidence rather than the missing click."""
    b = _bridge(form=_Form({"corner_entry": "Understeer"}))
    assert b._current_feedback() == {"corner_entry": "Understeer"}


def test_a_submitted_verdict_survives_navigating_away_from_the_form():
    b = _bridge(form=_Form({}), last={"corner_entry": "Oversteer"})
    assert b._current_feedback() == {"corner_entry": "Oversteer"}


def test_what_is_on_screen_now_wins_over_what_was_submitted():
    b = _bridge(form=_Form({"corner_entry": "Understeer"}),
                last={"corner_entry": "Oversteer", "notes": "old"})
    merged = b._current_feedback()
    assert merged["corner_entry"] == "Understeer"
    assert merged["notes"] == "old"


def test_blank_dropdowns_do_not_erase_a_submitted_verdict():
    b = _bridge(form=_Form({"corner_entry": "   "}), last={"corner_entry": "Oversteer"})
    assert b._current_feedback()["corner_entry"] == "Oversteer"


def test_no_form_is_not_an_error():
    assert _bridge(form=None, last={"a": "b"})._current_feedback() == {"a": "b"}


def test_clearing_drops_the_verdict_and_the_form():
    """Feedback is evidence about ONE run on ONE setup; carrying it past that boundary
    is not continuity, it is contamination."""
    form = _Form({"corner_entry": "Understeer"})
    b = _bridge(form=form, last={"corner_entry": "Understeer"})
    b._clear_feedback("a new run is open")
    assert b._last_feedback == {}
    assert form.reset_calls == 1


def test_clearing_when_there_is_nothing_held_still_resets_the_form():
    form = _Form({"corner_entry": "Understeer"})
    b = _bridge(form=form, last={})
    b._clear_feedback("a new run is open")
    assert form.reset_calls == 1


@pytest.mark.parametrize("handler", [
    "_on_start_run", "_on_record_run", "_on_discard_run", "_on_discipline",
    "_on_begin_qualifying",
])
def test_every_run_and_discipline_boundary_clears_feedback(handler):
    """None of these cleared it, so a qualifying analysis could quietly reuse a
    practice verdict."""
    import inspect

    from ui.live_shell_bridge import LiveShellBridge
    src = inspect.getsource(getattr(LiveShellBridge, handler))
    assert "_clear_feedback" in src, f"{handler} does not clear stale feedback"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def qapp_form(qapp):
    """Module-scoped and held for the module's lifetime.

    A per-test widget is created and dropped inside the test, and Python then frees it
    while Qt still holds references — the documented Win/Py3.14 teardown-order segfault
    this project already carries. Holding one for the module avoids it; it is a test
    harness detail, not a product behaviour.
    """
    from ui.components.practice_feedback import StructuredFeedbackForm
    form = StructuredFeedbackForm()
    yield form


def test_the_feedback_form_can_actually_reset(qapp_form):
    form = qapp_form
    form._set_overall(list(form._overall_buttons)[0])
    form._notes.setText("felt loose")
    assert form.current_feedback()
    form.reset()
    assert form.current_feedback() == {}


# ---------------------------------------------------------------------------
# B10 — the learning loop that could never fire from real data
# ---------------------------------------------------------------------------
def test_the_learning_loop_reads_classic_form_wording():
    """It matched the bare word "understeer" while the classic form wrote "Too much
    understeer", so every row from that surface scored as neither. Combined with the
    rows mostly never being written (B1/B4/B5), the loop could not fire at all."""
    from strategy.driver_profile_evolution import _row_signals
    assert _row_signals({"corner_entry": "Too much understeer"}) == (True, False)
    assert _row_signals({"exit_stability": "Rear loose on throttle"}) == (False, True)


def test_the_learning_loop_reads_mangled_classic_keys():
    from strategy.driver_profile_evolution import _row_signals
    assert _row_signals({"mid-corner": "Pushes wide"}) == (True, False)


def test_a_corroborated_tendency_now_evolves_the_profile():
    """This is load-bearing: the fabricated preference flags were deleted in Phase 1
    (defect A9), so profile evolution is the ONLY thing that can populate a driver
    profile now."""
    from strategy.driver_profile_evolution import evolve_profile, observe_feedback
    from strategy.setup_driver_profile import build_driver_profile
    base = build_driver_profile()
    assert not base.prefers_front_bite, "premise changed: the base profile now asserts a style"

    rows = [{"corner_entry": "Too much understeer"}] * 4
    evolved, rationale = evolve_profile(base, observe_feedback(rows))
    assert evolved.prefers_front_bite is True
    assert rationale and "4 of the last 4" in rationale[0]


def test_uncorroborated_feedback_does_not_move_the_profile():
    """Style is a slow-moving property — one session must not rewrite it."""
    from strategy.driver_profile_evolution import evolve_profile, observe_feedback
    from strategy.setup_driver_profile import build_driver_profile
    base = build_driver_profile()
    evolved, rationale = evolve_profile(
        base, observe_feedback([{"corner_entry": "Too much understeer"}]))
    assert evolved == base
    assert rationale == []


def test_row_signals_never_raise_on_junk():
    from strategy.driver_profile_evolution import _row_signals
    for junk in ({}, {"corner_entry": None}, {"corner_entry": object()}):
        assert _row_signals(junk) == (False, False)


# ---------------------------------------------------------------------------
# B6 rendering — the acknowledgement is visible, not buried
# ---------------------------------------------------------------------------
def test_the_garage_renders_the_acknowledgement(qapp):
    from ui.components.setup_workspace import SetupWorkspace
    from ui.setup_recommendation_vm import build_recommendation_vm
    w = SetupWorkspace()
    w.set_recommendation(build_recommendation_vm({}), feedback_dispositions=[
        {"feedback": "Mid-corner understeer", "state": "addressed",
         "detail": "Change(s) applied: arb_front."},
        {"feedback": "Mid-corner oversteer", "state": "deferred",
         "detail": "No safe rule-based change."}])
    text = w._ack.text()
    assert "What I did with what you told me" in text
    assert "Mid-corner understeer" in text and "Acted on" in text
    assert "Mid-corner oversteer" in text and "Heard, not changed" in text


def test_the_acknowledgement_is_not_behind_the_why_toggle(qapp):
    """In the classic UI it rendered inside a COLLAPSED <details>. An acknowledgement
    the driver has to go looking for is not an acknowledgement."""
    from ui.components.setup_workspace import SetupWorkspace
    from ui.setup_recommendation_vm import build_recommendation_vm
    w = SetupWorkspace()
    w.set_recommendation(build_recommendation_vm({}), feedback_dispositions=[
        {"feedback": "X", "state": "addressed", "detail": "y"}])
    assert w._ack is not w._why
    assert w._explain.isChecked() is False
    assert w._ack.text()


def test_a_degraded_diagnosis_is_shown_to_the_driver(qapp):
    from ui.components.setup_workspace import SetupWorkspace
    from ui.setup_recommendation_vm import build_recommendation_vm
    w = SetupWorkspace()
    w.set_recommendation(build_recommendation_vm({}),
                         degraded_reason="ValueError: bad lap")
    assert "PARTIAL evidence" in w._ack.text()


def test_nothing_reported_means_no_acknowledgement_box(qapp):
    from ui.components.setup_workspace import SetupWorkspace
    from ui.setup_recommendation_vm import build_recommendation_vm
    w = SetupWorkspace()
    w.set_recommendation(build_recommendation_vm({}))
    assert w._ack.text() == ""


def test_the_acknowledgement_takes_part_in_the_rerender_skip(qapp):
    """The Garage repaints every 750ms and skips identical renders. Without the
    dispositions in the fingerprint, a new set on an otherwise-identical
    recommendation is silently dropped — the same disappearing act in a new place."""
    from ui.components.setup_workspace import SetupWorkspace
    from ui.setup_recommendation_vm import build_recommendation_vm
    w = SetupWorkspace()
    vm = build_recommendation_vm({})
    w.set_recommendation(vm, feedback_dispositions=[
        {"feedback": "A", "state": "addressed", "detail": "x"}])
    assert "A" in w._ack.text()
    w.set_recommendation(vm, feedback_dispositions=[
        {"feedback": "B", "state": "deferred", "detail": "y"}])
    assert "B" in w._ack.text()


def test_the_bridge_only_shows_the_acknowledgement_for_its_own_sheet():
    """A race analysis must not speak for the qualifying sheet."""
    import inspect

    from ui.live_shell_bridge import LiveShellBridge
    src = inspect.getsource(LiveShellBridge._feed_garage)
    assert "feedback_dispositions" in src
    assert 'getattr(_res, "discipline", "") == self._discipline' in src


# ---------------------------------------------------------------------------
# B11 — the arbiter's deprecation note claimed a supersession that did not happen
# ---------------------------------------------------------------------------
def test_the_successor_does_not_weigh_driver_feedback():
    """resolve_setup_decision composes lifecycle/outcome status into one driver-facing
    state; it never reads feedback. So it did NOT supersede the arbiter's job, which is
    deciding who wins when telemetry and the driver disagree."""
    import inspect

    from strategy.setup_decision_status import resolve_setup_decision
    params = inspect.signature(resolve_setup_decision).parameters
    assert not any("feedback" in p for p in params)


def test_the_arbiter_states_why_it_stays_dormant():
    import inspect

    import strategy.setup_decision as sd
    doc = inspect.getdoc(sd.arbitrate_setup_decision) or ""
    assert "B11" in doc
    assert "conflict" in doc.lower()
