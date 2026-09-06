"""The wall's gap readings: kept with their side, drained once a lap, filed."""
from __future__ import annotations

from pitcrew.race.gap_signal import GapSample
from pitcrew.race.sectors import SectorMap


def _sample(**over):
    fields = dict(at_s=1.0, gap_s=1.2, track_s=300.0, lap=4, position=3,
                  subject="p2", side="ahead")
    fields.update(over)
    return GapSample(**fields)


def test_take_samples_drains_the_wall():
    from pitcrew.race.pit_wall import PitWall

    wall = PitWall()
    wall.samples.append(_sample())
    wall.samples.append(_sample(side="behind", gap_s=2.0))
    taken = wall.take_samples()
    assert [s.side for s in taken] == ["ahead", "behind"]
    assert wall.samples == [] and wall.take_samples() == []


def test_the_store_files_them_and_reads_them_back(tmp_path):
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        event_id = store.create_event(name="x", track="Deep Forest Raceway",
                                      layout="Full Course", car_name="car",
                                      race_type="laps", race_laps=20)
        session_id = store.start_session(event_id, "race")
        n = store.record_gap_reads(session_id, [
            _sample(at_s=1.0, track_s=300.0),
            _sample(at_s=2.0, track_s=None, gap_s=1.1),
            _sample(at_s=3.0, gap_s=None),              # not a reading
            _sample(at_s=4.0, side="behind", gap_s=3.0),
        ])
        assert n == 3
        rows = store.gap_reads(session_id, side="ahead")
        assert [r["gap_s"] for r in rows] == [1.2, 1.1]
        assert rows[1]["track_m"] is None, "unknown is NULL, never the start line"
        assert rows[0]["subject"] == "p2"
        assert len(store.gap_reads(session_id)) == 3
    finally:
        store.close()


def test_a_session_with_no_id_files_nothing(tmp_path):
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        assert store.record_gap_reads(None, [_sample()]) == 0
    finally:
        store.close()


# --------------------------------------------------------- the roll-up

def _lap(gain_by_third, every_m=200.0, length=4253.0):
    """(track_m, gap_s) round one lap, the gap moving by `gain_by_third[i]`
    across third i (negative = we gain)."""
    out, m, gap = [], 0.0, 1.0
    cuts = (length / 3, 2 * length / 3)
    while m < length:
        third = 0 if m < cuts[0] else 1 if m < cuts[1] else 2
        start = (0.0, cuts[0], cuts[1])[third]
        end = (cuts[0], cuts[1], length)[third]
        base = 1.0 + sum(gain_by_third[:third])
        gap = base + gain_by_third[third] * ((m - start) / (end - start))
        out.append((m, gap))
        m += every_m
    return out


def test_sectors_roll_the_bins_up_on_the_circuits_own_lines():
    length = 4253.0
    sectors = SectorMap(circuit_length_m=length)
    for _ in range(5):
        assert sectors.note_lap(_lap((-0.2, -0.2, 0.4)), subject="p2")
    rolled = sectors.sectors((length / 3, 2 * length / 3))
    assert [s.index for s in rolled] == [0, 1, 2]
    assert [round(s.mean_s, 1) for s in rolled] == [-0.2, -0.2, 0.4]
    assert all(s.laps == 5 for s in rolled)
    assert [s.gaining for s in rolled] == [True, True, False]


def test_a_lap_whose_first_read_is_past_the_line_bins_the_same():
    """Critic pass 5: bins were keyed off the first read, so a lap read
    from 180 m put every bin 180 m late against sector lines cut from 0."""
    length = 4253.0
    cuts = (length / 3, 2 * length / 3)
    from_zero = SectorMap(circuit_length_m=length)
    from_180 = SectorMap(circuit_length_m=length)
    for _ in range(5):
        lap = _lap((-0.2, -0.2, 0.4))
        from_zero.note_lap(lap, subject="p2")
        # The same lap, the first read taken 180 m past the line.
        late = [(m + 180.0, g) for m, g in lap if m + 180.0 < length]
        assert from_180.note_lap(late, subject="p2")
    a = [round(s.mean_s, 2) for s in from_zero.sectors(cuts)]
    b = [round(s.mean_s, 2) for s in from_180.sectors(cuts)]
    # What differs is the road not read - the first 180 m of sector 1 and
    # the last 180 m of sector 3 (0.025 and 0.05 of their built-in moves) -
    # and nothing moves between sectors: sector 2 is the same to a hundredth.
    assert abs(a[1] - b[1]) <= 0.015, (a, b)
    assert all(abs(x - y) <= 0.08 for x, y in zip(a, b)), (a, b)


def test_a_new_subject_drops_the_lap_sums_too():
    sectors = SectorMap(circuit_length_m=4253.0)
    sectors.note_lap(_lap((-0.2, -0.2, 0.4)), subject="p2")
    sectors.note_lap(_lap((-0.2, -0.2, 0.4)), subject="p4")
    assert len(sectors.lap_sums) == 1
    sectors.new_session()
    assert sectors.lap_sums == []
