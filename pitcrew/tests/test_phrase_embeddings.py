"""The phrase embeddings are computed once, not once per launch.

**Measured 22 Aug 2026: `SemanticMatcher.__init__` cost 15 s of every start,
on the Qt thread, before the window was shown.** 230 phrases at 66-99 ms
each, recomputed from scratch every time. The comment above `_load` reasons
about "forty-six short phrases" - the list has grown five times since and the
cost assumption never moved with it.

The output is a pure function of two things that rarely change: `PHRASES`,
a frozen module constant, and the model file. So this is a caching problem
rather than a threading one - no worker, no handoff, no "still loading" state
to get wrong, and no failure delayed past the point the driver could act on
it.

Measured after: 15.03 s cold, 0.65 s warm. 23x.

These tests use a stand-in model rather than the real 200 MB one. What is
being tested is the cache's contract - that it round-trips exactly, that it
notices a changed phrase list or model, and that it never turns a slow start
into a broken one - and none of that needs real weights.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer.ptt import SemanticMatcher


class FakeModel:
    """Deterministic vectors, and a count of how much work it was asked for."""

    model_path = "fake-model-v1"

    def __init__(self) -> None:
        self.calls = 0

    def calculate_embedding(self, phrase: str) -> list[float]:
        self.calls += 1
        # Stable, phrase-dependent, and float32-representable so the round
        # trip through the cache is exact rather than nearly exact.
        seed = float(sum(phrase.encode("utf-8")) % 997)
        return [seed, len(phrase) * 1.0, seed * 0.5, -seed]

    @staticmethod
    def distance(a, b) -> float:
        return 1.0 - min(1.0, abs(a[0] - b[0]) / 1000.0)


PHRASES = {"box-when": ["when do i box", "box this lap"],
           "tyres": ["how are my tyres", "tyre wear"],
           "fuel": ["how much fuel"]}


@pytest.fixture()
def cache_path(tmp_path, monkeypatch):
    """Somewhere to write that is not the driver's data directory."""
    path = tmp_path / "ptt_embeddings.npz"
    monkeypatch.setattr(SemanticMatcher, "_cache_path", staticmethod(
        lambda: path))
    return path


def test_the_second_matcher_does_no_model_work(cache_path):
    first = FakeModel()
    cold = SemanticMatcher(PHRASES, model=first)
    assert cold.available
    assert first.calls == 5, "every phrase should have been embedded once"
    assert cache_path.exists(), "nothing was written to reuse"

    second = FakeModel()
    warm = SemanticMatcher(PHRASES, model=second)
    assert warm.available
    assert second.calls == 0, (
        f"the model was asked to embed {second.calls} phrases again - the "
        f"cache did not take")


def test_the_cached_vectors_are_the_same_vectors(cache_path):
    cold = SemanticMatcher(PHRASES, model=FakeModel())
    warm = SemanticMatcher(PHRASES, model=FakeModel())

    assert set(cold._embeddings) == set(warm._embeddings)
    for phrase, (intent, vector) in cold._embeddings.items():
        cached_intent, cached_vector = warm._embeddings[phrase]
        assert cached_intent == intent
        assert list(cached_vector) == list(vector), (
            f"{phrase!r} came back changed: {vector} -> {cached_vector}")
        # The model returns a list, so `distance` has always been handed one.
        assert isinstance(cached_vector, list)


def test_an_edited_phrase_list_is_not_answered_from_the_old_cache(cache_path):
    SemanticMatcher(PHRASES, model=FakeModel())

    grown = dict(PHRASES, pace={"what is my pace"})
    after = FakeModel()
    matcher = SemanticMatcher(grown, model=after)
    assert after.calls == 6, (
        "a phrase was added and the stale cache was used anyway - the new "
        "phrase would never match")
    assert "what is my pace" in matcher._embeddings


def test_a_different_model_is_not_answered_from_the_old_cache(cache_path):
    SemanticMatcher(PHRASES, model=FakeModel())

    other = FakeModel()
    other.model_path = "fake-model-v2"
    SemanticMatcher(PHRASES, model=other)
    assert other.calls == 5, (
        "the model changed and its vectors were read from the old one's "
        "cache - every distance would be measured against the wrong space")


def test_an_unreadable_cache_is_a_slow_start_and_nothing_worse(cache_path):
    """A cache that will not load must never be more than a slow start. It is
    an optimisation; the app has to work without it."""
    cache_path.write_bytes(b"not an npz file at all")

    model = FakeModel()
    matcher = SemanticMatcher(PHRASES, model=model)
    assert matcher.available, "a corrupt cache broke the matcher"
    assert model.calls == 5, "it did not fall back to computing them"
    # And it repairs itself rather than tripping on the same file next time.
    again = FakeModel()
    SemanticMatcher(PHRASES, model=again)
    assert again.calls == 0, "the bad cache was not replaced"


def test_a_cache_that_cannot_be_written_is_not_fatal(tmp_path, monkeypatch):
    """A read-only data directory, a full disk, a locked file. None of them
    are reasons not to have haptics and an engineer."""
    monkeypatch.setattr(SemanticMatcher, "_cache_path", staticmethod(
        lambda: tmp_path / "no" / "such" / "dir" / "x.npz"))

    def refuse(*_a, **_k):
        raise OSError("read-only file system")

    monkeypatch.setattr("pathlib.Path.mkdir", refuse)
    matcher = SemanticMatcher(PHRASES, model=FakeModel())
    assert matcher.available, "an unwritable cache stopped the matcher working"


def test_no_model_means_no_cache_and_no_crash(cache_path):
    matcher = SemanticMatcher(PHRASES, model=None)
    if matcher._model is None:
        assert not matcher.available
        assert not cache_path.exists(), (
            "wrote a cache with nothing to cache")
