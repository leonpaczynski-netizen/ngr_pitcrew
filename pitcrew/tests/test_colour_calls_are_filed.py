"""Every call the engineer makes reaches the ledger, not just the instructions.

**Road Atlanta, 23 Aug 2026.** The race's ledger held fourteen calls. The log
held roughly twice that, and the difference was entirely numbers:

    20:25:19  Fuel: -5.2 laps in hand.
    20:26:41  9 to the box.
    20:34:59  FL 33.
    20:46:47  Fuel: 3.1 laps in hand.
    20:49:28  Fuel: 2.9 laps in hand.

None of those were filed. They are the fuel model and the wear sampler saying
out loud what they believed, at the moment they believed it - which is the only
thing that lets either be marked right or wrong afterwards. CLAUDE.md §5.5 asks
the export to carry the calls the engineer made *and the assumptions behind
them*, and half of that was going to the speakers and nowhere else.

The instructions were never the problem: "Box next lap", "Fuel to 77 litres"
and the chequered flag were all on the ledger, with their reasons in
`plan_json`. This is about the other half.
"""
from __future__ import annotations

from pitcrew.race.colour import ColourCall, ColourCalls


class _Store:
    def __init__(self):
        self.filed = []

    def append_revision(self, run_id, lap, reason, payload, accepted=False):
        self.filed.append({"run_id": run_id, "lap": lap, "reason": reason,
                           "payload": payload, "accepted": accepted})


class _State:
    lap = 14
    finished = False
    in_pit = False
    last_said_lap = None


class _Race:
    running = True

    def __init__(self):
        self.state = _State()


class _Controller:
    """The filing helper, lifted off the real class with nothing else."""
    from pitcrew.controller import PitCrewController
    _file_informational = PitCrewController._file_informational

    def __init__(self, store, run_id=9, race=None):
        self.store = store
        self.race_run_id = run_id
        self.race = race if race is not None else _Race()


def a_call(**over) -> ColourCall:
    """**The type the production paths actually produce.**

    `ColourCalls.consider` and `ColourCalls.data_line` both return
    `ColourCall`, which has no `as_export()` and no `confidence`. The first
    version of this test built a `race.calls.Call` instead - the one type
    those paths can never emit - and passed green over a feature that wrote
    zero rows in every race.
    """
    fields = dict(kind="colour-data", call="Fuel: 3.1 laps in hand.",
                  reason="")
    fields.update(over)
    return ColourCall(**fields)


def test_the_type_under_test_is_the_type_production_emits():
    """The assertion that would have caught the first version."""
    assert not hasattr(ColourCall, "as_export")
    assert not hasattr(a_call(), "confidence")


def test_a_colour_call_reaches_the_ledger():
    store = _Store()
    _Controller(store)._file_informational(a_call())
    assert len(store.filed) == 1
    row = store.filed[0]
    assert row["reason"] == "Fuel: 3.1 laps in hand."
    assert row["run_id"] == 9
    assert row["lap"] == 14


def test_a_real_generated_call_files():
    """Not a hand-built one - whatever `ColourCalls` actually produces."""
    store = _Store()
    made = ColourCalls(level="chatty").data_line(
        lap=14, fuel_laps_in_hand=3.1, wear_worst=None, wear_corner=None,
        stint_ends_on_lap=None)
    assert made is not None, "the generator produced nothing to file"
    _Controller(store)._file_informational(made)
    assert len(store.filed) == 1
    assert store.filed[0]["reason"] == made.call


def test_it_is_filed_as_informational_and_never_as_a_declined_offer():
    """A number read out is not a plan the driver refused. Recording it as one
    would tell the audit he ignored the engineer every lap of the race."""
    store = _Store()
    _Controller(store)._file_informational(a_call())
    row = store.filed[0]
    assert row["payload"]["informational"] is True
    assert row["accepted"] is False


def test_the_export_reads_it_as_informational():
    """The filed shape has to survive the reader, not just the writer."""
    from pitcrew.export.build import _disposition
    store = _Store()
    _Controller(store)._file_informational(a_call())
    disposition, accepted = _disposition(
        {"plan": store.filed[0]["payload"], "accepted": 0,
         "lap_num": 14}, set())
    assert accepted is None
    assert "inform" in disposition


def test_the_reason_travels_with_it():
    """`reason` carries the numbers behind the call - "Fronts 77, rears 82"
    to "Tyres are up to temperature"."""
    store = _Store()
    _Controller(store)._file_informational(
        a_call(kind="tyre-temp", call="Tyres are up to temperature.",
               reason="Fronts 77, rears 82, settled."))
    assert (store.filed[0]["payload"]["call"]["reason"]
            == "Fronts 77, rears 82, settled.")


def test_nothing_is_filed_outside_a_race():
    store = _Store()
    _Controller(store, run_id=None)._file_informational(a_call())
    assert store.filed == []


def test_nothing_is_filed_after_the_flag():
    race = _Race()
    race.state.finished = True
    store = _Store()
    _Controller(store, race=race)._file_informational(a_call())
    assert store.filed == []


def test_a_ledger_that_raises_stops_trying_and_says_so_once():
    """A fault here is permanent more often than transient. The first version
    logged the same error every lap and wrote nothing."""
    calls = {"n": 0}

    class _Broken(_Store):
        def append_revision(self, *a, **k):
            calls["n"] += 1
            raise RuntimeError("disk full")

    controller = _Controller(_Broken())
    for _ in range(5):
        controller._file_informational(a_call())    # must not raise
    assert calls["n"] == 1, "disarmed after the first failure"


# ---------------------------------------------------------------------------
# The wiring. Without these, deleting either call site is invisible.
# ---------------------------------------------------------------------------

def test_both_colour_paths_file():
    """`_voice_colour` and the straight's data line both have to file. The
    helper being correct is worth nothing if nothing calls it."""
    import inspect

    from pitcrew.controller import PitCrewController

    for name in ("_voice_colour", "_on_straight_reached"):
        body = inspect.getsource(getattr(PitCrewController, name))
        assert "_file_informational" in body, (
            f"{name} speaks a colour call and never files it")
