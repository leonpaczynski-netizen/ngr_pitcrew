"""Program 3 Phase E16 — qualifying state machine."""

from strategy.qualifying_state_machine import (
    QualifyingPhase, QualifyingState, on_pit_exit, on_lap_completed, on_cooldown,
    on_box, qualifying_cue, qualifying_tyre_warmup,
)


def test_full_attempt_lifecycle():
    s = QualifyingState.initial()
    assert s.phase == QualifyingPhase.PREPARATION and s.attempt == 0

    s = on_pit_exit(s)                       # leave the pits
    assert s.phase == QualifyingPhase.OUT_LAP and s.attempt == 1

    s = on_lap_completed(s, 0)               # out-lap done → flying lap underway
    assert s.phase == QualifyingPhase.FLYING_LAP

    s = on_lap_completed(s, 89_500, valid=True)   # flying lap done
    assert s.phase == QualifyingPhase.LAP_COMPLETE
    assert s.last_lap_ms == 89_500 and s.last_lap_was_pb and s.best_lap_ms == 89_500

    s = on_cooldown(s)
    assert s.phase == QualifyingPhase.COOLDOWN


def test_second_attempt_beats_pb():
    s = QualifyingState.initial()
    s = on_lap_completed(on_lap_completed(on_pit_exit(s), 0), 90_000)  # attempt 1: 90.0
    s = on_cooldown(s)
    # attempt 2
    s = on_pit_exit(s)
    assert s.attempt == 2 and s.phase == QualifyingPhase.OUT_LAP
    s = on_lap_completed(s, 0)               # out-lap
    s = on_lap_completed(s, 89_000)          # faster flying lap
    assert s.last_lap_was_pb and s.best_lap_ms == 89_000


def test_slower_lap_is_not_a_pb():
    s = QualifyingState.initial()
    s = on_lap_completed(on_lap_completed(on_pit_exit(s), 0), 88_000)   # PB 88.0
    s = on_pit_exit(on_cooldown(s))
    s = on_lap_completed(on_lap_completed(s, 0), 88_500)               # slower
    assert not s.last_lap_was_pb and s.best_lap_ms == 88_000


def test_invalid_lap_is_not_a_pb_and_reports_reason():
    s = QualifyingState.initial()
    s = on_lap_completed(on_pit_exit(s), 0)      # out-lap → flying
    s = on_lap_completed(s, 87_000, valid=False, invalidation_reason="track limits, turn 9")
    assert s.phase == QualifyingPhase.LAP_COMPLETE
    assert not s.last_lap_valid and s.best_lap_ms == 0
    cue = qualifying_cue(s)
    assert "deleted" in cue.lower() and "track limits" in cue.lower()


def test_cues_are_phase_appropriate():
    prep = qualifying_cue(QualifyingState.initial(), practice_best_ms=88_000)
    assert "practice best" in prep.lower() and "88.000" in prep

    out = qualifying_cue(QualifyingState(phase=QualifyingPhase.OUT_LAP))
    assert "out-lap" in out.lower() and "temperature" in out.lower()

    flying = qualifying_cue(QualifyingState(phase=QualifyingPhase.FLYING_LAP))
    assert flying == "This is your lap — commit."   # minimal / non-distracting

    pb = qualifying_cue(QualifyingState(phase=QualifyingPhase.LAP_COMPLETE,
                                        last_lap_ms=89_500, last_lap_valid=True,
                                        last_lap_was_pb=True))
    assert "personal best" in pb.lower()


def test_box_returns_to_preparation():
    s = on_pit_exit(QualifyingState.initial())
    assert on_box(s).phase == QualifyingPhase.PREPARATION


def test_never_raises_on_garbage():
    assert qualifying_cue(QualifyingState.initial(), practice_best_ms=None) is not None  # type: ignore
    assert on_lap_completed(QualifyingState.initial(), None).phase is not None  # type: ignore


# --- out-lap tyre warm-up guidance (Live Activation 2 enhancement) --------------

def _tyres(fl="cold", fr="cold", rl="cold", rr="cold"):
    return {"fl": fl, "fr": fr, "rl": rl, "rr": rr}


def test_out_lap_cue_prompts_optimal_window():
    cue = qualifying_cue(QualifyingState(phase=QualifyingPhase.OUT_LAP))
    low = cue.lower()
    assert "optimal" in low and ("heat" in low or "temp" in low)


def test_warmup_cold_building_ready_progression():
    assert qualifying_tyre_warmup(_tyres())[0] == "cold"
    assert qualifying_tyre_warmup(_tyres("warming", "warming", "optimal", "warming"))[0] == "building"
    assert qualifying_tyre_warmup(_tyres("optimal", "optimal", "optimal", "optimal"))[0] == "ready"


def test_warmup_ready_line_says_up_to_temp():
    status, line = qualifying_tyre_warmup(_tyres("optimal", "optimal", "optimal", "optimal"))
    assert status == "ready" and "up to temp" in line.lower()


def test_warmup_overheating_backs_off():
    status, line = qualifying_tyre_warmup(_tyres("hot", "optimal", "optimal", "optimal"))
    assert status == "hot" and ("ease" in line.lower() or "cook" in line.lower())
    # overheating on any corner wins even over an otherwise-ready set
    assert qualifying_tyre_warmup(_tyres("overheating", "optimal", "optimal", "optimal"))[0] == "hot"


def test_warmup_unknown_is_silent():
    assert qualifying_tyre_warmup({}) == ("", "")
    assert qualifying_tyre_warmup(None) == ("", "")


def test_warmup_accepts_enum_values():
    from telemetry.state import TyreState
    states = {c: TyreState.OPTIMAL for c in ("fl", "fr", "rl", "rr")}
    assert qualifying_tyre_warmup(states)[0] == "ready"
