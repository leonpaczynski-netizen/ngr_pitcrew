"""Program 3 Phase E1 — the single engineer-mode authority."""

from strategy.engineer_mode import EngineerMode, resolve_engineer_mode
from strategy.live_engineer_session import normalise_session_mode


def test_track_modelling_wins():
    assert resolve_engineer_mode(
        live_session_mode="race", track_modelling_active=True) == EngineerMode.TRACK_MODELLING


def test_race_by_declared_mode_or_phase():
    assert resolve_engineer_mode(live_session_mode="race") == EngineerMode.RACE
    assert resolve_engineer_mode(live_session_mode="practice", race_phase="RACING") == EngineerMode.RACE


def test_qualifying_and_practice_default():
    assert resolve_engineer_mode(live_session_mode="qualifying") == EngineerMode.QUALIFYING
    assert resolve_engineer_mode(live_session_mode=None) == EngineerMode.PRACTICE
    assert resolve_engineer_mode(live_session_mode="") == EngineerMode.PRACTICE


def test_enum_values_match_legacy_strings():
    # the enum drops into existing lowercase-string call sites unchanged
    assert EngineerMode.PRACTICE.value == "practice"
    assert EngineerMode.QUALIFYING.value == "qualifying"
    assert EngineerMode.RACE.value == "race"
    assert EngineerMode.TRACK_MODELLING.value == "track_modelling"


def test_preserves_normalise_session_mode_truth_table():
    """For the three modes normalise_session_mode knows, the resolver must agree
    (track modelling is the only addition)."""
    for live, phase in [("race", ""), ("qualifying", ""), ("practice", ""),
                        (None, ""), ("practice", "RACING"), (None, "RACING")]:
        legacy = normalise_session_mode(live, phase)
        resolved = resolve_engineer_mode(live_session_mode=live, race_phase=phase)
        assert resolved.value == legacy, f"{live!r},{phase!r}: {resolved.value} != {legacy}"


def test_never_raises_on_garbage():
    assert resolve_engineer_mode(live_session_mode=123) == EngineerMode.PRACTICE  # type: ignore
    assert resolve_engineer_mode(race_phase=None) == EngineerMode.PRACTICE  # type: ignore
