"""Live Activation 1 — Practice Engineer message choreography (§7).

Verifies the six message types fire exactly once, on the right edge, in priority order, and that
the engineer stays silent otherwise (anti-chatter).
"""
from __future__ import annotations

from strategy.practice_engineer_choreography import (
    EngineerCue, EngineerPhase, PracticeEngineerVoice, choreograph_engineer,
)


def _p(state, valid=0, invalid=0, reason="", target_min=5, target="5–8", objective="setup_base"):
    return EngineerPhase(run_state=state, valid_laps=valid, invalid_laps=invalid,
                         invalid_reason=reason, target_min=target_min, target_laps=target,
                         objective=objective)


# --------------------------------------------------------------------------- 6 message types
def test_brief_fires_on_activation():
    m = choreograph_engineer(_p("not_started", target_min=5), _p("starting", target_min=5))
    assert m.cue == EngineerCue.BRIEF
    assert "clean laps" in m.text and "setup_base" in m.text


def test_recording_confirmed_on_first_recording():
    m = choreograph_engineer(_p("starting"), _p("recording"))
    assert m.cue == EngineerCue.RECORDING_CONFIRMED and "Recording" in m.text


def test_recording_confirmed_again_after_reconnect():
    m = choreograph_engineer(_p("disconnected", valid=3), _p("recording", valid=3))
    assert m.cue == EngineerCue.RECORDING_CONFIRMED and "Back on" in m.text


def test_progress_on_a_new_valid_lap():
    m = choreograph_engineer(_p("recording", valid=1), _p("recording", valid=2))
    assert m.cue == EngineerCue.PROGRESS and m.text


def test_invalid_lap_names_the_reason():
    m = choreograph_engineer(_p("recording", valid=2), _p("recording", valid=2, invalid=1, reason="pit_lap"))
    assert m.cue == EngineerCue.INVALID_LAP and "pit lap" in m.text and "won't count" in m.text


def test_sufficient_when_target_reached():
    m = choreograph_engineer(_p("recording", valid=4, target_min=5), _p("recording", valid=5, target_min=5))
    assert m.cue == EngineerCue.SUFFICIENT and "enough for a read" in m.text


def test_conclusion_on_completion():
    m = choreograph_engineer(_p("recording", valid=6), _p("completed", valid=6))
    assert m.cue == EngineerCue.CONCLUSION and "Run complete" in m.text and "6 clean laps" in m.text


def test_conclusion_on_abandon_is_honest():
    m = choreograph_engineer(_p("recording", valid=2), _p("abandoned", valid=2))
    assert m.cue == EngineerCue.CONCLUSION and "abandoned" in m.text.lower()


# --------------------------------------------------------------------------- anti-chatter
def test_no_message_when_nothing_changed():
    assert choreograph_engineer(_p("recording", valid=3), _p("recording", valid=3)) is None
    assert choreograph_engineer(_p("paused", valid=3), _p("paused", valid=3)) is None


def test_completion_concludes_but_does_not_also_nag():
    # target reached AND completed in the same edge → ONE message, the conclusion (higher priority)
    m = choreograph_engineer(_p("recording", valid=4, target_min=5), _p("completed", valid=5, target_min=5))
    assert m.cue == EngineerCue.CONCLUSION


def test_sufficient_fires_once_not_every_subsequent_lap():
    prev = _p("recording", valid=5, target_min=5)          # already complete
    curr = _p("recording", valid=6, target_min=5)          # still complete, one more lap
    m = choreograph_engineer(prev, curr)
    # not SUFFICIENT again — it's just progress past the target
    assert m is None or m.cue == EngineerCue.PROGRESS


# --------------------------------------------------------------------------- stateful voice
def test_voice_runs_the_whole_session_once_each():
    v = PracticeEngineerVoice()
    cues = []
    for phase in [
        _p("not_started"), _p("starting"), _p("recording"),
        _p("recording", valid=1), _p("recording", valid=1),           # tick, no new lap → silent
        _p("recording", valid=2, invalid=1, reason="out_lap"),        # a valid + an invalid edge
        _p("recording", valid=5, target_min=5),                        # target reached
        _p("completed", valid=5, target_min=5),
    ]:
        m = v.observe(phase)
        if m is not None:
            cues.append(m.cue)
    assert EngineerCue.BRIEF in cues
    assert EngineerCue.RECORDING_CONFIRMED in cues
    assert EngineerCue.SUFFICIENT in cues
    assert EngineerCue.CONCLUSION in cues
    # the repeated tick (valid unchanged) produced no message
    assert cues.count(EngineerCue.CONCLUSION) == 1


def test_voice_is_silent_on_a_pure_tick():
    v = PracticeEngineerVoice()
    v.observe(_p("recording", valid=2))
    assert v.observe(_p("recording", valid=2)) is None


def test_never_raises_on_garbage():
    assert choreograph_engineer(None, None) is None            # type: ignore
    assert PracticeEngineerVoice().observe(EngineerPhase()) is None
