"""The measured tyre-temperature window, from this event's own laps.

The strategy layer still carries a per-compound band that was never measured
in GT7 - real-world slick figures at 85-110 degC, travelling with
`windowMeasured: false` precisely so nothing treats them as a finding. On the
measured cars the game runs a full ten degrees cooler: fronts 72-77, rears
78-88 over eighteen laps across four sessions. Judged against the fabricated
band those tyres read "below window" for an entire race, so the live tyre
voice must never import it. This module builds the band the honest way: from
the per-lap mean surface temperatures of the event's own practice laps.

Missing is None throughout. No practice frames means no window, and no window
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
    samples: list[tuple[int, float, float]] = []
    for row in rows[-MAX_DECODED_LAPS:]:
        stored = store.get_lap_frames(row["id"])
        if not stored:
            continue
        means = lap_axle_means(stored["frames"])
        if means is None:
            continue
        samples.append((row["session_id"], means[0], means[1]))
    return window_from_samples(samples)
