"""Program 3 Phase E14 — live practice brief."""

from strategy.practice_brief import (
    start_practice_brief, on_valid_lap, on_invalid_lap, stop_practice,
    practice_status, conclude_practice,
)


def test_brief_carries_objective_and_target():
    st = start_practice_brief(domain="setup_base")
    assert st.brief.objective                       # static content present
    assert st.target_min >= 1                        # parsed from "5-8"
    assert st.needs_another_lap and not st.is_complete


def test_valid_laps_progress_to_completion():
    st = start_practice_brief(domain="setup_base")
    target = st.target_min
    for _ in range(target):
        st = on_valid_lap(st)
    assert st.valid_laps == target
    assert st.is_complete and not st.needs_another_lap
    assert "target met" in practice_status(st).lower()


def test_one_anomalous_lap_does_not_dominate():
    """An invalid lap is tracked but never counts toward the target."""
    st = start_practice_brief(domain="setup_base")
    st = on_valid_lap(st)
    st = on_invalid_lap(st, reason="off at turn 3")
    st = on_valid_lap(st)
    assert st.valid_laps == 2 and st.invalid_laps == 1
    # completion is driven by valid laps only
    assert not st.is_complete or st.target_min <= 2
    status = practice_status(st)
    assert "didn't count" in status


def test_stop_condition_halts_progress():
    st = start_practice_brief(domain="setup_base")
    st = on_valid_lap(st)
    st = stop_practice(st, "rain started")
    assert st.stopped and not st.needs_another_lap and not st.is_complete
    st = on_valid_lap(st)                            # ignored after stop
    assert st.valid_laps == 1
    assert "stopped" in practice_status(st).lower() and "rain" in practice_status(st).lower()


def test_structured_conclusion():
    st = start_practice_brief(domain="setup_base")
    st = on_valid_lap(on_valid_lap(st))
    st = on_invalid_lap(st)
    result = conclude_practice(st)
    assert result["valid_laps"] == 2
    assert result["invalid_laps"] == 1
    assert result["objective"]
    assert "complete" in result and "reports" in result


def test_never_raises_on_unknown_domain():
    st = start_practice_brief(domain="nonsense-domain")
    assert practice_status(st) is not None
    assert conclude_practice(st)["valid_laps"] == 0
