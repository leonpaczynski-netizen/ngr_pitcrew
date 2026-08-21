"""Both sides of the radio, recorded and then handed to the debrief.

The calls ledger has only ever held one side. It says what the engineer said
and whether a pit stop followed - which cannot separate **a call that was right
and ignored** from **a call that was noise and ignored**, and that difference is
the whole of "which calls help". It is almost always in the reply.
"""
from __future__ import annotations

from pitcrew.store.db import Store
from pitcrew.telemetry.session_state import Lap


def a_session(store: Store) -> tuple[int, int]:
    event_id = store.create_event(
        name="Monza", track="Autodromo Nazionale Monza", layout="Full",
        car_name="Porsche 911 RSR (991) '17", race_type="laps", race_laps=20,
        game_version="1.71")
    return event_id, store.start_session(event_id, "race", game_version="1.71")


def test_an_exchange_is_kept_with_both_sides_and_its_lap(store: Store):
    _event_id, session_id = a_session(store)
    store.log_radio(session_id, heard="how much fuel", said="Two laps spare.",
                    lap_num=7, intent="fuel")
    got = store.list_radio(session_id)
    assert len(got) == 1
    assert got[0]["heard"] == "how much fuel"
    assert got[0]["said"] == "Two laps spare."
    assert got[0]["lap_num"] == 7 and got[0]["intent"] == "fuel"


def test_an_exchange_the_gate_could_not_classify_is_still_kept(store: Store):
    """**The vocabulary missing him is a finding about the vocabulary.**
    Dropping it would delete the only evidence that it happened."""
    _event_id, session_id = a_session(store)
    store.log_radio(session_id, heard="the rear is stepping out on entry",
                    said="Say again.", lap_num=3, intent=None)
    got = store.list_radio(session_id)
    assert got[0]["intent"] is None
    assert got[0]["heard"].startswith("the rear")


def test_a_broken_database_costs_the_record_and_not_the_reply(store: Store):
    """Written from the answer callback while he is on track. A hiccup must
    not cost him the reply he has already heard."""
    store.close()                       # every write from here on will fail
    store.log_radio(1, heard="fuel", said="Fine.")      # must not raise


def test_the_event_view_spans_its_sessions_in_order(store: Store):
    event_id, first = a_session(store)
    second = store.start_session(event_id, "practice", game_version="1.71")
    store.log_radio(first, heard="one", said="a", lap_num=1)
    store.log_radio(second, heard="two", said="b", lap_num=2)
    got = store.event_radio(event_id)
    assert [r["heard"] for r in got] == ["one", "two"]
    assert got[0]["session_kind"] == "race"
    assert got[1]["session_kind"] == "practice"


def test_the_debrief_prompt_carries_the_radio_verbatim(store: Store):
    """His words are not tidied. `CLAUDE.md` §4.1 makes the driver's report
    primary evidence, and a paraphrase of primary evidence is secondary."""
    from pitcrew.prompts.build import _radio_section

    class Lines:
        def __init__(self):
            self.out = []

        def add(self, *items):
            self.out.extend(items)

    class Context:
        radio = [{"lap_num": 12, "session_kind": "race", "intent": "box-when",
                  "heard": "how many to go", "said": "Two to go."}]

    lines = Lines()
    _radio_section(lines, Context())
    text = "\n".join(lines.out)
    assert "## Radio" in text
    assert '"how many to go"' in text and '"Two to go."' in text
    assert "Lap 12" in text and "box-when" in text


def test_a_session_with_no_radio_adds_no_heading(store: Store):
    """An empty section reads as "nothing was said", which is a claim. An
    absent one does not."""
    from pitcrew.prompts.build import _radio_section

    class Lines:
        def __init__(self):
            self.out = []

        def add(self, *items):
            self.out.extend(items)

    class Context:
        radio: list = []

    lines = Lines()
    _radio_section(lines, Context())
    assert lines.out == []
