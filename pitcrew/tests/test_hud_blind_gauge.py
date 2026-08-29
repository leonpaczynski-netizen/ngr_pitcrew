"""When the gauge stops answering, the app has to say so.

**Road Atlanta, 23 Aug 2026 - the sampler's first live race.** Twenty-two laps,
twenty-two grabs, six readings. The other sixteen were refused, and every single
one of them reported the identical message:

    hud-wear: lap 408: frame is dimmed (gauge peaks at 81)

*Exactly 81*, sixteen times, across forty minutes - in two blocks of eight
either side of stretches that read perfectly (laps 404-407 and 416-417). A
dimmed game frame does not do that. A pause menu sits over a scene that is
still moving, a transition is part-way through; both vary between grabs. A peak
identical to the unit is the same pixels every time.

The refusal itself was right and stays - `hud.py`'s own rule is *detect the dim
and skip the frame, never relax the thresholds to meet it*, because a wrong wear
figure is worse than a missing one. Two things were wrong around it:

1. The message named three causes - paused, in a menu, VR - and the actual one
   was probably none of them.
2. Nothing said it out loud. He raced believing the instrument was watching,
   while the wear plan ran the whole race on a practice figure.
"""
from __future__ import annotations

import inspect

from pitcrew.telemetry.hud import (
    BLIND_CROSSINGS_BEFORE_SAYING,
    IDENTICAL_PEAKS_MEAN_STATIC,
    LiveWearSampler,
    Reading,
    read_gauge,
)


def a_sampler(**over):
    said = []
    kw = dict(source=None, write=lambda *a, **k: None, on_status=said.append)
    kw.update(over)
    return LiveWearSampler(**kw), said


def dim(peak: int = 81) -> Reading:
    return Reading(None, f"frame is dimmed (gauge peaks at {peak})", peak=peak)


# ---------------------------------------------------------------------------
# The refusal itself must not have moved
# ---------------------------------------------------------------------------

def test_read_gauge_still_populates_the_peak_from_a_real_frame():
    """Without this the whole diagnosis dies silently: `_dim_peaks` stays
    empty, `stuck` is never true, and nothing says why."""
    from pitcrew.tests.test_hud_wear import a_canvas

    reading = read_gauge(a_canvas({"fl": 0.4}, dim=0.54))
    assert not reading.ok, "a dimmed frame is still refused"
    assert reading.peak is not None, "the peak has to travel on the refusal"
    assert str(reading.peak) in reading.reason


def test_the_dim_refusal_itself_has_not_moved():
    """The thresholds are the point of the module. A change that let a dimmed
    frame through would be far worse than the silence it replaced."""
    from pitcrew.tests.test_hud_wear import a_canvas

    assert not read_gauge(a_canvas({"fl": 0.4}, dim=0.54)).ok
    assert read_gauge(a_canvas({"fl": 0.4})).ok


def test_a_good_reading_carries_no_peak():
    assert Reading({"fl": 0.4}).peak is None


# ---------------------------------------------------------------------------
# Saying it
# ---------------------------------------------------------------------------

def test_the_driver_is_told_once_the_gauge_has_gone_blind():
    sampler, said = a_sampler()
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING - 1):
        sampler._note_blind(dim())
    assert said == [], "not before the threshold"
    sampler._note_blind(dim())
    assert len(said) == 1
    assert not said[0].ok, "a refusal, not a reading"
    assert said[0].wear is None, "never zeros - CLAUDE.md rule 3"
    assert "No tyre gauge" in said[0].reason


def test_it_does_not_repeat_the_same_diagnosis_every_lap():
    """An engineer that repeats one message every lap is the nine-box-calls
    defect with a second mouth."""
    sampler, said = a_sampler()
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING + 12):
        sampler._note_blind(dim())
    assert len(said) == 1


def test_a_sharper_diagnosis_is_said_even_after_the_first_one():
    """The first announcement can land before enough peaks exist to tell the
    two faults apart - one refusal with no peak is enough to delay it. Being
    told "unreadable" when the answer is "something is over your projector"
    is being given the wrong job."""
    sampler, said = a_sampler()
    sampler._note_blind(Reading(None, "canvas is 1920x1080", peak=None))
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING + IDENTICAL_PEAKS_MEAN_STATIC):
        sampler._note_blind(dim(81))
    assert len(said) >= 2, "the corrected diagnosis has to get through"
    assert "gauge is not in the frame" in said[-1].reason


def test_the_message_never_quotes_a_lap_count_it_cannot_keep_current():
    """It is only ever said at the threshold, so any count in it is a
    constant wearing the clothes of a live number."""
    sampler, said = a_sampler()
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING + 13):
        sampler._note_blind(dim())
    assert str(BLIND_CROSSINGS_BEFORE_SAYING) not in said[0].reason


# ---------------------------------------------------------------------------
# Telling the two faults apart
# ---------------------------------------------------------------------------

def test_an_identical_peak_is_diagnosed_as_the_wrong_rectangle():
    """The Road Atlanta signature: sixteen refusals, all peaking at 81."""
    sampler, said = a_sampler()
    for _ in range(max(BLIND_CROSSINGS_BEFORE_SAYING,
                       IDENTICAL_PEAKS_MEAN_STATIC)):
        sampler._note_blind(dim(81))
    assert "gauge is not in the frame" in said[0].reason


def test_the_spoken_note_states_the_symptom_and_not_a_cause():
    """**He is in VR.** GT7 draws the HUD on the car's dashboard in 3D, so the
    gauge leaves the rectangle whenever he looks away and a left-hander can
    hide it completely. "The capture is wrong" would be actively misleading
    there - the capture is fine. The note names what is observed; the log has
    room to separate the VR case from the flat-screen one."""
    sampler, said = a_sampler()
    for _ in range(max(BLIND_CROSSINGS_BEFORE_SAYING,
                       IDENTICAL_PEAKS_MEAN_STATIC)):
        sampler._note_blind(dim(81))
    reason = said[0].reason
    assert "gauge is not in the frame" in reason
    for blamed in ("capture region", "MFD", "projector"):
        assert blamed not in reason, (
            f"the spoken note must not blame {blamed} - in VR it is none of "
            f"those")


def test_a_varying_peak_carries_the_readers_own_reason_instead():
    """A genuinely dim frame varies. Blaming the capture region there sends
    him hunting a bug that is not in the app - and the reader's own message
    is more actionable than any substitute for it."""
    sampler, said = a_sampler()
    for peak in (137, 90, 41, 120, 66):
        sampler._note_blind(
            Reading(None, f"canvas is 1920x1080, not 1720x916", peak=peak))
    assert said
    assert "gauge is not in the frame" not in said[0].reason
    assert "1920x1080" in said[0].reason, "the fixable reason has to survive"


def test_the_two_blind_blocks_are_separate_events():
    """Laps 404-407 read fine. The blocks either side must not add up."""
    sampler, said = a_sampler()
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING - 1):
        sampler._note_blind(dim())
    sampler.new_session()
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING - 1):
        sampler._note_blind(dim())
    assert said == []


def test_a_new_session_forgets_what_was_already_said():
    """**The sampler outlives the session** - it is cached on the controller
    and built once. Without this, a practice run that went blind spends the
    announcement and the race that follows says nothing at all, which is the
    Road Atlanta failure moved one session later."""
    sampler, said = a_sampler()
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING):
        sampler._note_blind(dim())
    assert len(said) == 1
    sampler.new_session()
    for _ in range(BLIND_CROSSINGS_BEFORE_SAYING):
        sampler._note_blind(dim())
    assert len(said) == 2, "the next session gets its own warning"


# ---------------------------------------------------------------------------
# The wiring. Without these the mechanism can be perfect and still never run.
# ---------------------------------------------------------------------------

def test_the_sampler_is_built_with_a_status_consumer():
    """The first version of this change passed every test while `on_status`
    was never once supplied in production, so nothing ever reached him.

    The gauge came out of the controller on 29 Aug 2026 - see
    `telemetry/hud_session.py`. Same code, one class along.
    """
    from pitcrew.telemetry.hud_session import HudSession

    body = inspect.getsource(HudSession.sampler)
    assert "on_status" in body, (
        "LiveWearSampler is built without a status consumer, so every refusal "
        "goes nowhere")


def test_the_blind_path_calls_note_blind():
    from pitcrew.telemetry.hud import LiveWearSampler as S

    assert "_note_blind" in inspect.getsource(S._sample)


def test_a_refusal_clears_the_stale_wear_reading():
    """The reading was only ever written on a good sample and never cleared,
    so a blind gauge left the radio quoting a transcription many laps old as
    though it were current.

    **This used to read the source, because there was nothing to build.** The
    gauge session is its own object now, so the test drives the real thing:
    a good reading, then a refusal, and what the radio would be handed.
    """
    from pitcrew.telemetry.hud import Reading
    from pitcrew.telemetry.hud_session import HudSession

    class Store:
        def set_lap_wear(self, *a, **k):
            pass

    hud = HudSession(settings=lambda: None, store=Store())
    hud.note_lap(1, 7)
    hud._write_wear(1, {"fl": 0.4, "fr": 0.4, "rl": 0.5, "rr": 0.4})
    assert hud.latest_wear() == ({"fl": 0.4, "fr": 0.4, "rl": 0.5, "rr": 0.4}, 7)

    hud._status(Reading({}, reason="gauge not on the canvas"))

    assert hud.latest_wear() == (None, None),         "a blind gauge left a stale transcription standing"
    assert hud.take_blind_note() == "gauge not on the canvas"
    assert hud.take_blind_note() is None, "the note is said once"
