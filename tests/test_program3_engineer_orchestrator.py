"""Program 3 Phase E12 — Engineer Orchestrator (composition + parity)."""

from strategy.engineer_mode import EngineerMode
from strategy.engineer_orchestrator import EngineerContext, EngineerOutput, orchestrate
from strategy.live_engineer_session import session_engineer_call
from strategy.practice_brief import start_practice_brief, on_valid_lap
from strategy.qualifying_state_machine import QualifyingState, QualifyingPhase


def test_race_defers_to_strategy():
    out = orchestrate(EngineerContext(live_session_mode="race", connected=True))
    assert out.mode == EngineerMode.RACE
    assert out.line == "" and out.defers_to_strategy is True


def test_track_modelling_passes_callout_through():
    out = orchestrate(EngineerContext(
        track_modelling_active=True, connected=True,
        track_callout="Good lap — that's 3 clean, 2 more to go."))
    assert out.mode == EngineerMode.TRACK_MODELLING
    assert "clean" in out.line


def test_disconnected_yields_no_line():
    assert orchestrate(EngineerContext(live_session_mode="practice", connected=False)).line == ""
    assert orchestrate(EngineerContext(live_session_mode="qualifying", connected=False)).line == ""


def test_practice_falls_back_to_session_call_without_a_brief():
    ctx = EngineerContext(live_session_mode="practice", connected=True, lap_count=2)
    out = orchestrate(ctx)
    assert out.mode == EngineerMode.PRACTICE
    # parity with the existing thin function when no richer brief is supplied
    assert out.line == session_engineer_call("practice", connected=True, lap_count=2)


def test_practice_prefers_the_live_brief_when_present():
    brief = on_valid_lap(on_valid_lap(start_practice_brief(domain="setup_base")))
    out = orchestrate(EngineerContext(live_session_mode="practice", connected=True,
                                      practice_brief=brief))
    assert out.mode == EngineerMode.PRACTICE
    assert out.line and ("lap" in out.line.lower())   # brief-driven progress line


def test_qualifying_prefers_the_state_machine():
    st = QualifyingState(phase=QualifyingPhase.FLYING_LAP)
    out = orchestrate(EngineerContext(live_session_mode="qualifying", connected=True,
                                      qualifying_state=st))
    assert out.mode == EngineerMode.QUALIFYING
    assert out.line == "This is your lap — commit."   # minimal flying-lap cue


def test_practice_never_mentions_strategy():
    out = orchestrate(EngineerContext(live_session_mode="practice", connected=True, lap_count=5))
    for banned in ("pit", "stint", "fuel", "stop"):
        assert banned not in out.line.lower()


def test_deterministic_and_never_raises():
    ctx = EngineerContext(live_session_mode="qualifying", connected=True, lap_count=3,
                          last_lap_s=90.1, best_lap_s=89.9)
    assert orchestrate(ctx) == orchestrate(ctx)     # deterministic
    assert isinstance(orchestrate(EngineerContext()), EngineerOutput)  # empty is safe
