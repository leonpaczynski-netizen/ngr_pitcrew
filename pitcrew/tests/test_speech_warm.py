"""The background speech warm-up, and the lock that keeps it single-file.

Two things are pinned here, and they are the two that would be silent.

**The fallback.** `start_warm_up` runs on a daemon thread under `pythonw`,
where a failure has no console to reach. If a warm-up that produced nothing
were taken as an answer, `PushToTalk` would get `recogniser=None`, report
`available` False, and say "Speech isn't available on this machine" for a
whole race - a determined negative for a state that was never determined.
So a barren warm-up must fall through to the inline build, and that is
asserted on *call counts*: `best_recogniser_for` returns None under pytest by
design (see `_under_pytest`), so no test can assert on a real model arriving.

**The lock.** `_MOONSHINE_LOAD` guards a race inside the vendor package that
killed the recogniser in four launches out of five. A lock with no test is a
guard with no caller - this repo has shipped one of those before.
"""
from __future__ import annotations

import threading
import time

import pytest

from pitcrew.engineer import ptt


# ----------------------------------------------------------------- warm-up

def test_the_warm_thread_is_a_daemon():
    """`main()` can return through its `finally` without reaching the event
    loop. A non-daemon thread holding 250 MB of ONNX would keep a windowless
    process alive with nothing to show for it."""
    _outcome, thread = ptt.start_warm_up("moonshine")
    assert thread.daemon is True
    thread.join(30)
    assert not thread.is_alive()


def test_a_failed_warm_up_leaves_none_and_says_so(monkeypatch, caplog):
    """Never a stub. A recogniser-shaped object that answers `""` is
    indistinguishable from a driver who said nothing."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("no model here")

    monkeypatch.setattr(ptt, "best_recogniser_for", boom)
    monkeypatch.setattr(ptt, "matcher_for", boom)
    with caplog.at_level("ERROR"):
        outcome, thread = ptt.start_warm_up("moonshine")
        thread.join(30)

    assert outcome["recogniser"] is None
    assert outcome["matcher"] is None
    # Under pythonw this log line is the only evidence that will ever exist.
    assert any("did not load" in record.message for record in caplog.records)


def test_a_barren_warm_up_falls_through_to_the_inline_build(monkeypatch):
    """The condition the correctness critic set: no arrangement of failures
    may hand `PushToTalk` a None that the un-warmed code would have filled."""
    calls: list[str] = []

    def recording(backend, phrases=None):
        calls.append(backend)
        return None

    monkeypatch.setattr(ptt, "best_recogniser_for", recording)
    outcome, thread = ptt.start_warm_up("moonshine")
    thread.join(30)
    assert outcome["recogniser"] is None
    warmed = len(calls)

    recogniser, matcher = ptt.speech_from((outcome, thread), "moonshine")
    # Built again inline rather than accepting the empty warm-up.
    assert len(calls) == warmed + 1
    assert recogniser is None and matcher is None


def test_no_warm_up_at_all_still_builds(monkeypatch):
    """`warm` is None for every test, every replay and the bench."""
    calls: list[str] = []
    monkeypatch.setattr(ptt, "best_recogniser_for",
                        lambda backend, phrases=None: calls.append(backend))
    ptt.speech_from(None, "moonshine")
    assert calls == ["moonshine"]


def test_the_warm_up_does_not_reimplement_the_fallback_order(monkeypatch):
    """It must call the factories by name. Reimplementing the order here
    would silently lose the SAPI fallback and the closed-grammar rule."""
    seen = {}

    def recogniser_for(backend, phrases=None):
        seen["backend"] = backend
        return "recogniser"

    def matcher_for(recogniser):
        seen["asked_with"] = recogniser
        return "matcher"

    monkeypatch.setattr(ptt, "best_recogniser_for", recogniser_for)
    monkeypatch.setattr(ptt, "matcher_for", matcher_for)
    outcome, thread = ptt.start_warm_up("sapi")
    thread.join(30)
    assert seen["backend"] == "sapi"
    assert seen["asked_with"] == "recogniser"


# -------------------------------------------------------------------- lock

def test_the_two_moonshine_loads_cannot_overlap(caplog):
    """The vendor publishes its singleton before it has loaded it. Two
    threads in that window leave `ptt.available` False for the session."""
    spans: list[tuple[float, float]] = []

    def load() -> None:
        lock = ptt._hold_moonshine_load()
        try:
            began = time.perf_counter()
            time.sleep(0.05)
            spans.append((began, time.perf_counter()))
        finally:
            lock.release()

    with caplog.at_level("WARNING"):
        threads = [threading.Thread(target=load) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)

    assert len(spans) == 2
    first, second = sorted(spans)
    assert first[1] <= second[0], "the two loads overlapped"
    # The wait is charged against RECOGNISER_TIMEOUT_S by the caller above,
    # so a contended lock must not be readable as a slow model.
    assert any("moonshine load lock" in record.message
               for record in caplog.records)


def test_an_uncontended_load_says_nothing(caplog):
    """The normal path is one thread. It must not log a wait it did not do."""
    with caplog.at_level("WARNING"):
        lock = ptt._hold_moonshine_load()
        lock.release()
    assert not any("moonshine load lock" in record.message
                   for record in caplog.records)


@pytest.mark.parametrize("held", [True, False])
def test_the_lock_is_released_either_way(held):
    """A lock leaked on the failure path would hang the next launch."""
    if held:
        lock = ptt._hold_moonshine_load()
        lock.release()
    assert ptt._MOONSHINE_LOAD.acquire(blocking=False)
    ptt._MOONSHINE_LOAD.release()
