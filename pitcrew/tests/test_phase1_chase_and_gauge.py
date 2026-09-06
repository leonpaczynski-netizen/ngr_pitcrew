"""Phase 1: the chase call (1.2), one remaining-laps expression (1.4), and a
gauge fresh-set cut that needs two readings (1.9).

Deep Forest, 6 Sep 2026: seven laps chasing P2 with the pit wall reading the
gap on 154 frames and nothing spoken; the gauge series cut nine times on
single all-zero misreads while honest readings were refused twelve at a time.
"""
from __future__ import annotations

from pitcrew.race.calls import CHASE, RaceState, _chase
from pitcrew.race.gaps import GapTrend


def _chasing(gap=6.2, laps_total=20, lap=14, sigma=0.9, **over):
    trend = GapTrend(side="ahead")
    trend.note(lap, gap)
    fields = dict(lap=lap, laps_total=laps_total, gap_ahead=trend,
                  gap_ahead_name="Boxhead", lap_sigma_s=sigma)
    fields.update(over)
    return RaceState(**fields)


def test_the_chase_says_the_gap_the_laps_and_the_pace_it_takes():
    call = _chase(_chasing())
    assert call is not None and call.kind == CHASE
    assert call.call == "Boxhead 6.2 ahead, 6 laps to go."
    assert call.reason == ("You need 1.0 a lap. That's more than your "
                           "lap-to-lap spread.")


def test_a_target_inside_his_own_spread_is_said_as_one():
    call = _chase(_chasing(gap=2.4, sigma=0.9))
    assert "inside your lap-to-lap spread" in call.reason


def test_no_spread_measured_means_no_claim_about_it():
    call = _chase(_chasing(sigma=None))
    assert call.reason == "You need 1.0 a lap."


def test_every_other_lap_and_never_in_the_window_edges():
    state = _chasing()
    assert _chase(state) is not None
    state.lap = 15
    assert _chase(state) is None, "the lap after is quiet"
    state.lap = 16
    assert _chase(state) is not None
    assert _chase(_chasing(gap=25.0)) is None, "outside the window"
    assert _chase(_chasing(lap=5)) is None, "15 laps left is not a chase yet"
    assert _chase(_chasing(in_pit=True)) is None


def test_no_gap_read_means_no_chase():
    assert _chase(RaceState(lap=14, laps_total=20)) is None


# ------------------------------------------------------- one expression

def test_rival_calls_count_laps_left_the_way_the_state_does():
    from pitcrew.race import rival_calls
    import inspect

    source = inspect.getsource(rival_calls.candidates)
    assert "state.laps_remaining()" in source
    assert "state.laps_total - lap" not in source


# --------------------------------------------------------- the gauge

def _sampler():
    from pitcrew.telemetry.hud import LiveWearSampler, Reading

    class _Source:
        def grab(self):
            return None, "test"

    sampler = LiveWearSampler(_Source(), lambda *_a, **_k: None)
    return sampler, Reading


def _reading(Reading, worst):
    return Reading(wear={"fl": worst - 0.02, "fr": worst,
                         "rl": worst - 0.03, "rr": worst - 0.01})


def test_a_fresh_set_is_cut_on_two_readings_not_one():
    sampler, Reading = _sampler()
    assert sampler._keep(1.0, _reading(Reading, 0.42))
    assert sampler._keep(2.0, _reading(Reading, 0.44))
    assert len(sampler.series) == 2
    # One all-zero read: held, series untouched.
    assert sampler._keep(3.0, _reading(Reading, 0.03)) is False
    assert len(sampler.series) == 2
    assert sampler._latest[1].wear["fr"] == 0.44
    # A second agreeing read: the cut happens, both readings start the set.
    assert sampler._keep(4.0, _reading(Reading, 0.04)) is True
    assert [round(w["fr"], 2) for _, w in sampler.series] == [0.03, 0.04]


def test_a_held_fresh_reading_that_does_not_repeat_is_discarded():
    sampler, Reading = _sampler()
    sampler._keep(1.0, _reading(Reading, 0.42))
    sampler._keep(2.0, _reading(Reading, 0.44))
    assert sampler._keep(3.0, _reading(Reading, 0.03)) is False
    # The old set again: the held reading was the locator.
    assert sampler._keep(4.0, _reading(Reading, 0.46)) is True
    assert sampler._pending_fresh is None
    assert [round(w["fr"], 2) for _, w in sampler.series] == [0.42, 0.44, 0.46]


def test_new_session_drops_a_held_fresh_reading():
    sampler, Reading = _sampler()
    sampler._keep(1.0, _reading(Reading, 0.42))
    sampler._keep(2.0, _reading(Reading, 0.03))
    assert sampler._pending_fresh is not None
    sampler.new_session()
    assert sampler._pending_fresh is None
