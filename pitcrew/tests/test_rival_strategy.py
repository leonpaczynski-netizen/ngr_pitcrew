"""The seven failure modes the rival-strategy spec asks to be covered.

Not the happy path. Each of these is a way the subsystem produces a confident
wrong answer, and each is numbered against section 10 of the spec.
"""
from __future__ import annotations

import pytest

from pitcrew.race.gap_signal import (
    GAP_STALE_S,
    MAX_GAP_RATE_S_PER_S,
    GapSample,
    GapSignal,
)
from pitcrew.race.ledger import Pace, cover_deadline, undercut
from pitcrew.race.rival_answers import (
    SURE,
    THIN,
    UNKNOWN,
    RivalView,
    can_undercut,
    catching,
    everything,
    his_fuel,
    his_stop,
    must_cover,
    where_we_gain,
)
from pitcrew.race.rival_fuel import (
    Litres,
    calibrate,
    fill_from_readings,
    fill_from_standing,
    reconcile,
)
from pitcrew.race.rival_pace import RivalPace, attribute

CAL = calibrate([(64.0, 81.0, True), (0.0, 17.0, True)])


def a_signal(gaps, *, start=0.0, step=0.5, subject="rocky"):
    signal = GapSignal(side="ahead")
    at = start
    for gap in gaps:
        at += step
        signal.note(GapSample(at_s=at, gap_s=gap, subject=subject))
    return signal, at


# --- 1. slot change invalidates every derived value ------------------------

def test_a_rival_overtaking_another_car_resets_the_derived_state():
    """The single highest-risk defect in this subsystem: "car ahead" is a slot
    and the occupant changes."""
    signal, at = a_signal([8.0, 7.8, 7.6, 7.4, 7.2, 7.0])
    assert signal.rate_s_per_s(at)[0] is not None

    signal.note(GapSample(at_s=at + 0.5, gap_s=20.0, subject="punished"))
    assert len(signal.samples) == 1
    assert signal.rate_s_per_s(at + 0.5)[0] is None


def test_a_slot_change_resets_the_derived_lap_times_too():
    pace = RivalPace()
    for lap in range(1, 6):
        pace.note_lap(lap, 140.0, 8.0, 8.2, subject="rocky")
    assert pace.lap_times_s
    pace.note_lap(6, 140.0, 20.0, 20.2, subject="punished")
    assert list(pace.lap_times_s) == [6]


def test_his_lap_is_ours_less_what_we_took_out_of_the_gap():
    """rival_pace had both signs inverted: a car we were catching was derived
    as the faster one."""
    pace = RivalPace()
    assert pace.note_lap(5, 120.0, 4.0, 5.0, ahead=True) == 121.0
    behind = RivalPace()
    assert behind.note_lap(5, 120.0, 4.0, 5.0, ahead=False) == 119.0


# --- 2. a single OCR misread must not corrupt the rate ---------------------

def test_one_garbled_frame_is_rejected_and_the_rate_survives():
    """Rejected, not clamped: a clamp turns "I misread" into a confident
    value, which is CLAUDE.md rule 9."""
    signal, at = a_signal([8.0, 7.8, 7.6, 7.4, 7.2, 7.0, 6.8])
    before = signal.rate_s_per_s(at)[0]

    assert signal.note(GapSample(at_s=at + 0.5, gap_s=93.0,
                                 subject="rocky")) is False
    assert signal.rejected == 1
    assert signal.rate_s_per_s(at + 0.5)[0] == pytest.approx(before)


def test_the_gate_is_a_rate_not_a_fixed_step():
    signal = GapSignal()
    signal.note(GapSample(at_s=0.0, gap_s=8.0))
    # Two seconds later a big move is physically possible; half a second later
    # the same move is not.
    assert signal.note(GapSample(at_s=2.0, gap_s=8.0 + MAX_GAP_RATE_S_PER_S))
    assert not signal.note(GapSample(at_s=2.5, gap_s=40.0))


def test_no_rate_is_computed_from_two_adjacent_samples():
    signal, at = a_signal([8.0, 7.5])
    rate, _, samples = signal.rate_s_per_s(at)
    assert rate is None and samples == 2


# --- 3. a tyre-limited stop yields a bound, never a value ------------------

def test_a_stop_no_longer_than_a_tyre_change_bounds_the_fuel():
    """The fill was shorter than the tyre change, so all that is known is a
    ceiling. A point estimate here is fabricated."""
    bound = fill_from_standing(18.0, CAL)
    assert bound.kind == "lower-bound"
    assert bound.point is None
    assert bound.low == 0.0


def test_a_long_stop_is_a_point_because_the_hose_governed_it():
    assert fill_from_standing(98.0, CAL).point == pytest.approx(81.0)


def test_the_calibration_comes_from_our_own_stops():
    """`r` and `t_tyres` are measured against a tyres-only stop, not
    hardcoded - ours are the only fully observed ones."""
    assert CAL.refuel_rate_lps == pytest.approx(1.0)
    assert CAL.tyres_only_s == pytest.approx(17.0)
    assert CAL.known


# --- 4. estimators that disagree widen the window --------------------------

def test_disagreement_widens_rather_than_picking_a_winner():
    """A pit event plus a fuel reading plus a standing time that agree is
    truth. Two out of three is a hypothesis."""
    wide = reconcile(fill_from_readings(8.0, 93.0), fill_from_standing(60.0, CAL))
    assert wide.kind == "lower-bound"
    assert wide.low == pytest.approx(43.0) and wide.high == pytest.approx(85.0)
    assert "disagree" in wide.why


def test_agreement_stays_a_point():
    tight = reconcile(fill_from_readings(8.0, 93.0),
                      fill_from_standing(102.0, CAL))
    assert tight.point == pytest.approx(85.0)


def test_a_widened_window_widens_the_forced_stop_lap_too():
    view = RivalView(fuel_aboard=Litres(low=40.0, high=80.0,
                                        kind="lower-bound"),
                     burn_per_lap_l=8.0, lap=11)
    answer = his_fuel(view)
    assert answer.confidence == THIN
    assert answer.value == (16, 21)


# --- 5. losing the screen reader collapses cleanly -------------------------

def test_the_reader_dying_mid_race_reports_blind_not_stale():
    signal, at = a_signal([8.0, 7.8, 7.6, 7.4, 7.2, 7.0])
    live = RivalView(signal=signal, now_s=at, reader_alive=True,
                     ours=_pace(), theirs=_pace(), pit_loss_s=79.5, lap=11)
    assert catching(live).known

    dead = RivalView(signal=signal, now_s=at, reader_alive=False,
                     ours=_pace(), theirs=_pace(), pit_loss_s=79.5, lap=11)
    for answer in (catching(dead), must_cover(dead), can_undercut(dead)):
        assert answer.confidence == UNKNOWN
        assert "screen reader has stopped" in answer.reason


def test_a_stale_gap_is_unknown_and_not_last_known():
    signal, at = a_signal([8.0, 7.8, 7.6, 7.4, 7.2, 7.0])
    view = RivalView(signal=signal, now_s=at + GAP_STALE_S + 1,
                     ours=_pace(), theirs=_pace(), pit_loss_s=79.5)
    assert not view.available
    assert catching(view).confidence == UNKNOWN


def test_a_pit_event_survives_the_reader_dying():
    """An event is a point, not a level, so it does not expire with the
    stream."""
    dead = RivalView(reader_alive=False, stop_lap=11,
                     fuel_added=Litres(low=85.0, high=85.0, kind="point"))
    answer = his_stop(dead)
    assert answer.confidence == SURE and "lap 11" in answer.reason


# --- 6. the cover deadline converges and then says box now -----------------

def _pace(deg=0.02, laps=8, warmup=0.0, stint=0):
    return Pace(base_s=140.0, deg_s_per_lap=deg, warmup_s=warmup,
                laps_of_evidence=laps, error_s=0.4, stint_lap=stint)


def test_the_cover_deadline_shrinks_as_the_lead_does():
    ours, theirs = _pace(deg=0.30, stint=10), _pace(deg=0.02, warmup=1.2)
    deadlines = [cover_deadline(lead, ours, theirs, 79.5)[0]
                 for lead in (95.0, 90.0, 85.0, 82.0)]
    assert deadlines == sorted(deadlines, reverse=True)


def test_when_the_margin_falls_inside_the_model_error_the_call_is_box_now():
    """At that point the model cannot tell waiting from stopping, and a lap
    number quoted past it is invented precision."""
    ours, theirs = _pace(deg=0.30, stint=10), _pace(deg=0.02, warmup=1.2)
    _, margin, now = cover_deadline(79.8, ours, theirs, 79.5)
    assert now and margin is not None and margin <= 0.4


def test_a_deadline_already_past_says_box_now_rather_than_a_negative_lap():
    ours, theirs = _pace(deg=0.30, stint=10), _pace(deg=0.02, warmup=1.2)
    laps, _, now = cover_deadline(70.0, ours, theirs, 79.5)
    assert laps == 0 and now


def test_a_thin_deg_fit_refuses_the_whole_ledger():
    """CLAUDE.md: below the evidence threshold the answer is unknown, not a
    ledger run on a two-lap fit."""
    thin = Pace(base_s=140.0, deg_s_per_lap=0.3, laps_of_evidence=2)
    assert cover_deadline(90.0, thin, _pace(), 79.5) == (None, None, False)
    assert undercut(2.0, _pace(), thin, 79.5) == (None, None)


def test_the_pit_loss_cancels_in_an_undercut_and_not_in_a_cover():
    """Both cars pay the toll once, so it cancels once both have stopped. A
    version that always subtracted it made an undercut require recovering
    eighty seconds on pace alone, and so never returned one."""
    ours, theirs = _pace(warmup=1.2), _pace(deg=0.30, stint=10)
    lap, _ = undercut(2.0, ours, theirs, 79.5)
    assert lap is not None and lap <= 3


# --- 7. attribution --------------------------------------------------------

def test_a_gap_closing_purely_on_their_degradation_reports_us_at_zero():
    """"Catching at 0.4, 0.3 of it his tyres" leads to hold station. Reporting
    only the 0.4 is how a correct number gives the wrong idea."""
    split = attribute(0.4, ours_now_s=140.0, ours_reference_s=140.0,
                      theirs_now_s=140.4, theirs_reference_s=140.0)
    assert split.ours_s_per_lap == pytest.approx(0.0)
    assert split.theirs_s_per_lap == pytest.approx(0.4)
    assert split.mostly_theirs and "his tyres" in split.why()


def test_a_gap_closing_because_we_found_time_reports_them_at_zero():
    split = attribute(0.4, ours_now_s=139.6, ours_reference_s=140.0,
                      theirs_now_s=140.0, theirs_reference_s=140.0)
    assert split.theirs_s_per_lap == pytest.approx(0.0)
    assert not split.mostly_theirs and "you" in split.why()


def test_an_unknown_reference_is_not_a_contribution_of_zero():
    """"We do not know who is responsible" and "it is evenly split" are very
    different things to say under a helmet."""
    split = attribute(0.4, 140.0, 140.0, 140.4, None)
    assert not split.known and split.why() == ""


# --- the output contract ---------------------------------------------------

def test_every_answer_carries_a_value_a_reason_and_a_confidence():
    view = RivalView(reader_alive=False)
    for name, answer in everything(view).items():
        assert hasattr(answer, "value") and hasattr(answer, "reason")
        assert answer.confidence in (SURE, THIN, UNKNOWN), name


def test_the_sector_answer_refuses_without_a_map_rather_than_guessing():
    """It was reported as blocked once and it was not - GT7 broadcasts no
    lap-distance channel, but the recorder has always integrated one from
    speed. What it still refuses is answering with no map at all."""
    answer = where_we_gain(RivalView())
    assert answer.confidence == UNKNOWN
    assert "no sector map" in answer.reason


# --- the sector map, which was reported as blocked and was not -------------

def _a_lap(length_m=7004.0, samples=240, gain_in=None, gain_s=0.25,
           start_gap=1.5):
    gap, out = start_gap, []
    for i in range(samples):
        d = i * length_m / samples
        here = int(d / (length_m / 12))
        if gain_in is not None and here == gain_in:
            gap -= gain_s / (samples / 12)
        out.append((d, gap))
    return out


def test_a_sector_map_finds_where_the_gap_moves():
    from pitcrew.race.sectors import SectorMap

    sectors = SectorMap(circuit_length_m=7004.0)
    for _ in range(8):
        assert sectors.note_lap(_a_lap(gain_in=7), subject="rocky")
    best = sectors.worth_saying(1)
    assert best and best[0].gaining
    assert best[0].index == 7


def test_a_teleported_lap_is_dropped_rather_than_binned_wrongly():
    """About 7% of laps teleport and speed integration cannot see it. What it
    CAN see is that the lap did not come out the length of the circuit."""
    from pitcrew.race.sectors import SectorMap

    sectors = SectorMap(circuit_length_m=7004.0)
    short = [(d * 0.6, g) for d, g in _a_lap()]
    assert sectors.note_lap(short, subject="rocky") is False
    assert sectors.laps_dropped == 1 and sectors.laps_used == 0


def test_a_bin_inside_its_own_noise_is_not_surfaced():
    """Reporting noise is how a driver learns to distrust the tool."""
    from pitcrew.race.sectors import SectorMap

    sectors = SectorMap(circuit_length_m=7004.0)
    for _ in range(8):
        sectors.note_lap(_a_lap(), subject="rocky")   # no gain anywhere
    assert sectors.worth_saying() == []


def test_a_slot_change_clears_the_sector_map():
    from pitcrew.race.sectors import SectorMap

    sectors = SectorMap(circuit_length_m=7004.0)
    for _ in range(6):
        sectors.note_lap(_a_lap(gain_in=7), subject="rocky")
    sectors.note_lap(_a_lap(gain_in=2), subject="punished")
    assert sectors.laps_used == 1


def test_a_gap_too_large_to_attribute_switches_the_feature_off():
    """At half a lap of separation the offset correction is larger than the
    thing being corrected."""
    from pitcrew.race.sectors import MAX_USEFUL_GAP_S, SectorMap

    sectors = SectorMap(circuit_length_m=7004.0)
    far = _a_lap(start_gap=MAX_USEFUL_GAP_S + 5.0, gain_in=7)
    assert sectors.note_lap(far, subject="rocky") is False


def test_where_we_gain_answers_now_that_track_position_is_joined():
    from pitcrew.race.sectors import SectorMap

    sectors = SectorMap(circuit_length_m=7004.0)
    for _ in range(8):
        sectors.note_lap(_a_lap(gain_in=7), subject="rocky")
    answer = where_we_gain(RivalView(sectors=sectors))
    assert answer.confidence == SURE and answer.value


def test_where_we_gain_without_a_map_says_so_rather_than_guessing():
    assert where_we_gain(RivalView()).confidence == UNKNOWN


# --- the lap ruler ---------------------------------------------------------

class _Packet:
    def __init__(self, packet_id, speed_ms):
        self.packet_id, self.speed_ms = packet_id, speed_ms


def test_the_ruler_integrates_distance_because_gt7_broadcasts_none():
    from pitcrew.race.lap_ruler import LapRuler

    ruler = LapRuler(circuit_length_m=600.0)
    for i in range(1, 601):
        ruler.note_packet(_Packet(i, 50.0))
    assert ruler.where() == pytest.approx(500.0)


def test_a_lap_that_did_not_come_out_the_right_length_is_not_believable():
    from pitcrew.race.lap_ruler import LapRuler

    ruler = LapRuler(circuit_length_m=7004.0)
    for i in range(1, 601):
        ruler.note_packet(_Packet(i, 50.0))
    ruler.crossed_line(1)
    assert not ruler.believable


def test_a_dropout_refuses_a_position_rather_than_guessing_across_it():
    """Adding speed times the gap would assert the car held this speed through
    a stretch nobody saw."""
    from pitcrew.race.lap_ruler import LapRuler

    ruler = LapRuler(circuit_length_m=7004.0)
    for i in range(1, 60):
        ruler.note_packet(_Packet(i, 50.0))
    ruler.note_packet(_Packet(500, 50.0))     # a long dropout
    assert ruler.dropped_packets == 1
    assert ruler.where() is None


def test_the_ruler_never_raises_on_a_bad_packet():
    from pitcrew.race.lap_ruler import LapRuler

    ruler = LapRuler(circuit_length_m=7004.0)
    ruler.note_packet(None)
    ruler.note_packet(_Packet("x", "y"))
    # **Unknown, not the start line** (rule 3): nothing it was handed was a
    # packet, so it has measured nothing. It answered 0.0 here, and 0.0 is
    # what five races of `gap_reads` were filed at.
    assert ruler.where() is None


def test_a_ruler_nobody_has_fed_does_not_say_zero_metres():
    """Sessions 143-176: the bridge was asked to feed a ruler it was never
    given, and every gap reading was filed at `track_m = 0.0`."""
    from pitcrew.race.lap_ruler import LapRuler

    ruler = LapRuler(circuit_length_m=7004.0)
    assert ruler.where() is None
    ruler.note_packet(_Packet(1, 50.0))
    assert ruler.where() == pytest.approx(50.0 / 60.0)
    ruler.crossed_line(1)
    assert ruler.where() == 0.0          # fed, and genuinely at the line


def test_the_bridge_is_handed_the_ruler_it_feeds():
    """**The defect was two objects, not arithmetic.** `TelemetryBridge.
    _on_packet` reads `self._lap_ruler`; the controller built the ruler on
    ITSELF. The wiring is asserted in the source because building a whole
    controller for one attribute costs a QApplication."""
    import inspect

    from pitcrew import controller

    bridge_src = inspect.getsource(controller.TelemetryBridge)
    assert 'getattr(self, "_lap_ruler", None)' in bridge_src
    start_src = inspect.getsource(controller.PitCrewController)
    assert "self.bridge._lap_ruler = self._lap_ruler" in start_src


# --- the rival pit pattern -------------------------------------------------

def test_his_pit_pattern_pools_races_as_a_fraction():
    """A stop on lap 11 means something different in a 20-lap race and a
    40-lap one."""
    from pitcrew.race.rival_answers import his_pit_pattern

    answer = his_pit_pattern(RivalView(stop_history=(0.50, 0.55, 0.51)))
    assert answer.confidence == SURE and "52%" in answer.reason


def test_one_stop_is_not_a_pattern():
    from pitcrew.race.rival_answers import his_pit_pattern

    assert his_pit_pattern(RivalView(stop_history=(0.5,))).confidence == THIN
    assert his_pit_pattern(RivalView()).confidence == UNKNOWN
