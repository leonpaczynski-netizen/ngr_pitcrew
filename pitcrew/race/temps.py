"""The measured tyre-temperature range, from this event's own laps.

The strategy layer used to carry a per-compound band that was never measured
in GT7 - real-world slick figures at 85-110 degC. On the measured cars the
game runs a full ten degrees cooler: fronts 72-77, rears 78-88 over eighteen
laps across four sessions. Judged against that band those tyres read "below
window" for an entire race, and a fresh set is fitted at exactly the Racing
Soft cold ceiling, so a Soft could never once reach its own window. It has
since been deleted from `store/tyres.py` rather than flagged, because a flag
did not stop it being read.

This module builds the band the honest way: from the per-lap mean surface
temperatures of the event's own practice laps. **It is a running range, not a
window** - see the note on `RUNNING_RANGE` for the two measurements that rule
out reading it as one.

Missing is None throughout. No practice frames means no range, and no range
means the race engineer's temperature comparisons are not made - never made
against a default.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median

# The measured cars take about two laps to come up to temperature from cold,
# so each session's opening laps describe the warm-up, not the working range.
# They are dropped from the band and kept for the time-to-window figure,
# which is exactly the question they answer.
WARM_UP_LAPS = 2

# The band is the 10th-90th percentile of the steady laps' means: wide enough
# to be the working range, trimmed enough that one hot incident lap does not
# stretch the ceiling.
WINDOW_LO_PCT = 10.0
WINDOW_HI_PCT = 90.0

# Fewer steady laps than this and the percentiles describe noise, not a
# window. The answer is then None, not a thinner claim.
MIN_WINDOW_LAPS = 4

# **What this band is, and what it is not.**
#
# It is a description of where he has been running the tyres. It is NOT a
# performance window, and the measurement says so twice over:
#
# * Tested directly on 17 of his own gate-passed laps, the fastest five are
#   NOT in a narrower absolute-temperature band than the rest - the fastest-5
#   front range (4.9 degC) is WIDER than the full 10th-90th percentile spread
#   (4.6 degC). Front absolute temperature carries no pace information at all
#   (within-session r = -0.13, p = 0.61) and rear absolute temperature flips
#   sign between practice and race.
# * Nobody outside has one either: no optimal tyre-temperature window has ever
#   been published for GT7, by Polyphony or by anyone else.
#
# So no call built on this band may imply a physical optimum. The pace signal
# that DOES survive every split is the front-to-rear gap, and it lives with
# the calls that use it in `race/calls.py`; the compound's one sourced upper
# figure - a wear-onset threshold, not a window - lives in `store/tyres.py`.
# What this band is for is the warm-up comparison at the green, which is a
# question about where he started relative to where he ends up, and for that
# a descriptive range is exactly the right instrument.
RUNNING_RANGE = ("running range - 10th-90th percentile of this event's steady "
                 "practice laps; descriptive, not a performance window")

# Frame blobs cost ~65 ms each to decode, so the sample is capped. The cap is
# generous against a race evening's practice (ten laps on the measured
# nights) and the window barely moves lap to lap.
MAX_DECODED_LAPS = 15


@dataclass(frozen=True)
class TempWindow:
    """A measured working window per axle, and how it was measured."""
    front: tuple[float, float]
    rear: tuple[float, float]
    # Measured laps from a cold start to both axles inside the window, or
    # None where no sampled session started cold enough to show it.
    laps_to_window: int | None
    laps_sampled: int
    # **What kind of band this is**, which decides what a call may claim about
    # it. There is exactly one kind, and it is descriptive - see the note
    # above the constant for the two measurements that rule out the other
    # kind. The field exists so that anything reading a stored window can see
    # what it was built from rather than having to assume.
    basis: str = RUNNING_RANGE


def lap_axle_means(frames: list[dict]) -> tuple[float, float] | None:
    """One lap's mean surface temperature per axle, or None without temps."""
    fronts, rears = [], []
    for frame in frames:
        fl, fr = frame.get("temp_fl"), frame.get("temp_fr")
        rl, rr = frame.get("temp_rl"), frame.get("temp_rr")
        if None in (fl, fr, rl, rr):
            continue
        fronts.append((fl + fr) / 2.0)
        rears.append((rl + rr) / 2.0)
    if not fronts:
        return None
    return round(mean(fronts), 1), round(mean(rears), 1)


def _pct(values: list[float], p: float) -> float:
    """Linear-interpolated percentile; the sample is small by design."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p / 100.0
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def window_from_samples(samples: list[tuple[int, float, float]]
                        ) -> TempWindow | None:
    """The measured window from `(session_id, front_mean, rear_mean)` rows.

    Rows arrive in drive order. Each session's first `WARM_UP_LAPS` laps are
    excluded from the band - they measure the warm-up - and then used for the
    one thing they are evidence of: how many laps the warm-up takes.
    """
    if not samples:
        return None
    by_session: dict[int, list[tuple[float, float]]] = {}
    for session_id, front, rear in samples:
        by_session.setdefault(session_id, []).append((front, rear))

    steady = [pair for laps in by_session.values()
              for pair in laps[WARM_UP_LAPS:]]
    if len(steady) < MIN_WINDOW_LAPS:
        return None

    fronts = [front for front, _ in steady]
    rears = [rear for _, rear in steady]
    front_band = (round(_pct(fronts, WINDOW_LO_PCT), 1),
                  round(_pct(fronts, WINDOW_HI_PCT), 1))
    rear_band = (round(_pct(rears, WINDOW_LO_PCT), 1),
                 round(_pct(rears, WINDOW_HI_PCT), 1))

    # Time to window, from the sessions that actually started below it.
    # A session whose first lap is already in the band has nothing to say
    # about warming up - a lobby rejoin on hot tyres is not a cold start.
    warmups: list[int] = []
    for laps in by_session.values():
        first_front, first_rear = laps[0]
        if first_front >= front_band[0] and first_rear >= rear_band[0]:
            continue
        for index, (front, rear) in enumerate(laps):
            if front >= front_band[0] and rear >= rear_band[0]:
                warmups.append(index)   # laps *before* the in-window lap
                break

    return TempWindow(
        front=front_band,
        rear=rear_band,
        laps_to_window=(max(1, round(median(warmups))) if warmups else None),
        laps_sampled=len(steady),
    )


def measured_temp_window(store, event_id: int) -> TempWindow | None:
    """The window for this event, decoded from its practice laps' frames.

    Runs once, when the race is armed - not per lap - because each lap's
    blob costs real time to decode. Excluded, out- and in-laps stay out for
    the same reason they stay out of every other aggregate.
    """
    rows = [row for row in store.list_event_laps(event_id, "practice")
            if not row.get("excluded")
            and not row.get("is_out_lap") and not row.get("is_pit_lap")]
    from pitcrew.store import frame_memo

    samples: list[tuple[int, float, float]] = []
    for row in rows[-MAX_DECODED_LAPS:]:
        # Through the memo: the same bytes give the same means, and the
        # qualifying arm and the race arm both ask - see `store/frame_memo`.
        means = frame_memo.derived(
            store, row["id"], "lap_axle_means",
            lambda stored: lap_axle_means(stored["frames"]))
        if means is frame_memo.NO_FRAMES or means is None:
            continue
        samples.append((row["session_id"], means[0], means[1]))
    return window_from_samples(samples)
