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


def test_the_gate_verdict_is_kept_beside_the_words(store: Store):
    _event_id, session_id = a_session(store)
    store.log_radio(session_id, heard="how far behind is he",
                    said="Say again.", intent="unknown", action="reject",
                    distance=0.61, lap_num=4)
    row = store.list_radio(session_id)[0]
    assert row["action"] == "reject"
    assert row["distance"] == 0.61


def test_a_press_with_no_words_is_still_a_row(store: Store):
    """A brushed button and a microphone that never opened are different.

    Both arrive here with an empty transcript, and the reason is the only
    thing that separates them. Recording the press without it would leave the
    two indistinguishable, which is the state `gate.py` exists to end.
    """
    _event_id, session_id = a_session(store)
    store.log_radio(session_id, heard="", said="I didn't catch that.",
                    intent="unknown", action="reject",
                    reason="no speech in the capture")
    row = store.list_radio(session_id)[0]
    assert row["reason"] == "no speech in the capture"


def test_a_caller_without_a_verdict_writes_null_rather_than_a_guess(
        store: Store):
    """Null is "not recorded". It must never read as "acted"."""
    _event_id, session_id = a_session(store)
    store.log_radio(session_id, heard="fuel", said="Fine.", intent="fuel")
    row = store.list_radio(session_id)[0]
    assert row["action"] is None
    assert row["distance"] is None


def test_the_review_tool_puts_the_refusals_first_and_counts_repeats():
    """What `tools/radio_review.py` is for: the misses are the additions."""
    import tools.radio_review as review

    rows = [
        {"session_id": 9, "lap_num": 5, "heard": "how are my tyres",
         "said": "Fronts 62 percent.", "intent": "tyres", "action": "act",
         "distance": 0.11},
        {"session_id": 9, "lap_num": 7, "heard": "how far behind is he",
         "said": "Say again.", "intent": "unknown", "action": "reject",
         "distance": 0.59},
        {"session_id": 9, "lap_num": 4, "heard": "how far behind is he",
         "said": "Say again.", "intent": "unknown", "action": "reject",
         "distance": 0.61},
    ]
    text = "\n".join(review.report(rows, misses_only=False))
    assert text.index("REFUSED") < text.index("ANSWERED")

    asked = "\n".join(review.suggestions(rows))
    assert '2x  "how far behind is he"' in asked
    # An answered question is not a candidate: it already has an intent.
    assert "how are my tyres" not in asked


def test_a_row_with_no_verdict_is_reported_as_unrecorded_not_as_acted():
    """The distinction the whole schema change exists to make."""
    import tools.radio_review as review

    rows = [{"session_id": 1, "lap_num": None, "heard": "old row",
             "said": "x", "intent": "fuel", "action": None,
             "distance": None}]
    text = "\n".join(review.report(rows, misses_only=False))
    assert "unrecorded" in text
    assert "predate the verdict" in text
