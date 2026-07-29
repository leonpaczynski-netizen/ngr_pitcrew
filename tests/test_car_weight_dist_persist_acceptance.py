"""Acceptance tests — Save weight distribution to car library (end-to-end).

Maps each AC to existing tests (referenced by name) or adds new integration tests here.

EXISTING COVERAGE (not duplicated here):
  AC1  persist round-trip (2nd instance reads value)
       → test_car_weight_dist_store.py::TestSetAndPersist::test_round_trip_second_instance_reads_same_value
  AC1  multiple cars persisted
       → test_car_weight_dist_store.py::TestSetAndPersist::test_multiple_cars_all_persisted
  AC1  update overwrites previous value
       → test_car_weight_dist_store.py::TestSetAndPersist::test_updating_a_car_overwrites_previous_value
  AC3  overlay wins over seed (resolver)
       → test_car_weight_distribution.py::TestOverlay::test_overlay_wins_over_seed
  AC3  car-only-in-overlay resolves
       → test_car_weight_distribution.py::TestOverlay::test_car_only_in_overlay_resolves
  AC3  invalidate forces re-read
       → test_car_weight_distribution.py::TestOverlay::test_invalidate_causes_re_read
  AC3  set_overlay_path invalidates cache
       → test_car_weight_distribution.py::TestOverlay::test_set_overlay_path_invalidates_cache
  AC4  "car data file" reason label (not "override")
       → test_spring_frequencies.py::TestReasonStringSourceLabel::test_car_data_file_reason_says_car_data_not_override
  AC4  file data overrides drivetrain prior (split direction)
       → test_spring_frequency_acceptance.py::TestPOWeightDistResolutionOrder::test_file_data_overrides_drivetrain_prior
  AC5  frac validation: zero/one/negative/above-one rejected
       → test_car_weight_dist_store.py::TestValidation (7 tests)
  AC5  bridge converts pct÷100 to fraction before store.set
       → test_live_shell_bridge.py::TestSaveFrontWeightDist::test_save_calls_store_and_invalidates
  AC6  empty car → no save + guard fires
       → test_live_shell_bridge.py::TestSaveFrontWeightDist::test_no_car_name_does_not_save
  AC6  zero/None pct → no save + guard fires
       → test_live_shell_bridge.py::TestSaveFrontWeightDist::test_zero_pct_does_not_save
  AC6  success → status names car and %
       → test_live_shell_bridge.py::TestSaveFrontWeightDist::test_status_reported_on_success
  AC7  corrupt store file → empty overlay, never raises
       → test_car_weight_dist_store.py::TestPersistence::test_corrupt_file_degrades_to_empty_no_raise
  AC7  corrupt overlay file → resolver falls back to seed, never raises
       → test_car_weight_distribution.py::TestOverlay::test_corrupt_overlay_falls_back_to_seed
  AC7  missing overlay → seed-only fallback
       → test_car_weight_distribution.py::TestOverlay::test_missing_overlay_falls_back_to_seed
  AC7  empty store path → in-memory, set returns True
       → test_car_weight_dist_store.py::TestPersistence::test_empty_path_set_returns_true
  AC8  spring regression: neutral seeds unchanged without overrides
       → test_spring_frequency_acceptance.py::TestAC10DirectCallNeutralSprings (5 tests)
  AC8  seed-only resolver when no overlay registered
       → test_car_weight_distribution.py::TestOverlay::test_no_overlay_path_seed_only
  config.json safety guard (session-autouse)
       → tests/conftest.py::_guard_real_config

NEW TESTS ADDED HERE:
  AC2  seed file bytes unchanged after overlay write  → TestAC2SeedUnchanged (2 tests)
  AC3+AC4 integration chain: store → resolver → spring generator
       → TestIntegrationChain (4 tests — KEY GAP)
  AC6  store.set returns False → failure garage status (Qt)
       → TestAC6StoreFailure (1 test)
  AC7  empty path in-memory at bridge-equivalent level
       → TestAC7SafetyGuards::test_empty_path_store_never_writes_file
  AC7  corrupt overlay via the real set_overlay_path() call → seed-only
       → TestAC7SafetyGuards::test_corrupt_overlay_via_set_overlay_path_falls_back_to_seed
  AC7  missing overlay via set_overlay_path → seed-only
       → TestAC7SafetyGuards::test_missing_overlay_via_set_overlay_path_falls_back_to_seed

All Qt-free unless in TestAC6StoreFailure (which requires QApplication).
No production code is modified here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from services.car_weight_dist_store import CarWeightDistStore, default_car_weight_dist_path
from strategy.setup_engineering import (
    build_vehicle_model,
    derive_spring_frequencies,
    OBJ_BASE,
)

# Git-tracked seed file — tests must never write to this path.
_SEED_PATH = ROOT / "data" / "car_weight_distribution.json"

# "Porsche 911 RSR (991) '17" is NOT in the real seed (which has only 3 entries).
# Using a car absent from the seed gives a clean integration test: without an overlay
# the resolver returns None → drivetrain prior RR = 0.38 (rear-heavy, rear_hz ≥ front_hz).
# Saving frac=0.62 (front-heavy) to the overlay reverses the split, proving the overlay
# was picked up by the resolver and passed through to the spring generator.
_TEST_CAR = "Porsche 911 RSR (991) '17"
_TEST_DRIVETRAIN = "rr"
_TEST_SPECS = {"weight_kg": 1243, "power_hp": 509, "category": "Gr.3"}

# "Toyota AE86 Levin D-Tuned" IS in the real seed at 0.55 — used to verify overlay
# wins over an existing seed entry.
_SEED_CAR = "Toyota AE86 Levin D-Tuned"
_SEED_CAR_FRAC = 0.55


# ===========================================================================
# AC2 — The seed file on disk is NOT modified when the user saves to the overlay
# ===========================================================================

class TestAC2SeedUnchanged:
    """Saving the user's % front must write only the overlay file (beside config.json),
    never the git-tracked seed at data/car_weight_distribution.json."""

    def test_seed_bytes_unchanged_after_overlay_write(self, tmp_path):
        """AC2 primary: CarWeightDistStore.set() writes to its configured path;
        the git-tracked seed is byte-identical before and after."""
        seed_before = _SEED_PATH.read_bytes()

        overlay_path = str(tmp_path / "car_weight_distribution.user.json")
        store = CarWeightDistStore(overlay_path)
        store.set(_TEST_CAR, 0.42)

        seed_after = _SEED_PATH.read_bytes()
        assert seed_before == seed_after, (
            f"CarWeightDistStore.set() must NOT modify the git-tracked seed at {_SEED_PATH}. "
            "The seed changed, which means the write was routed to the wrong path."
        )

    def test_overlay_written_to_configured_path_not_seed_location(self, tmp_path):
        """AC2 provenance: the overlay file appears at the configured tmp path and
        contains the saved value — ruling out accidental write-to-seed scenarios."""
        overlay_path = str(tmp_path / "car_weight_distribution.user.json")
        store = CarWeightDistStore(overlay_path)
        store.set(_TEST_CAR, 0.42)

        assert Path(overlay_path).exists(), (
            "Overlay file must exist at the configured path after store.set()"
        )
        content = json.loads(Path(overlay_path).read_text(encoding="utf-8"))
        assert _TEST_CAR in content, "Saved car must appear in the overlay file"
        assert content[_TEST_CAR] == pytest.approx(0.42), (
            f"Overlay file must store the exact fraction; expected 0.42, got {content[_TEST_CAR]!r}"
        )


# ===========================================================================
# AC3+AC4 — Integration chain: store.set → resolver → derive_spring_frequencies
#
# KEY GAP: unit tests prove each component in isolation; no existing test drives
# the three together as the production code wires them.  The bridge calls:
#   __init__:         set_overlay_path(overlay_path)
#   _on_save…:        store.set(car, pct/100) → invalidate()
# This class reproduces that exact sequence and asserts at the far end.
# ===========================================================================

class TestIntegrationChain:
    """End-to-end: CarWeightDistStore.set() → invalidate() →
    resolve_front_weight_dist() → derive_spring_frequencies() sees the overlay value.

    All tests use monkeypatch to save/restore the module-level _OVERLAY_PATH and
    _CACHE globals so this file can be run repeatedly without state leak.
    """

    @staticmethod
    def _vehicle():
        return build_vehicle_model(_TEST_CAR, _TEST_DRIVETRAIN, 6, _TEST_SPECS)

    # ------------------------------------------------------------------ #
    # AC3: resolver returns the overlay fraction after store.set          #
    # ------------------------------------------------------------------ #

    def test_resolver_returns_overlay_fraction_after_store_write(
        self, tmp_path, monkeypatch
    ):
        """AC3 integration: store.set() writes the file; invalidate() clears the cache;
        resolve_front_weight_dist() reads seed + overlay and returns the saved fraction.

        Sequence mirrors what the bridge does:
          __init__  → set_overlay_path(path)   [registers path, invalidates]
          _on_save  → store.set(car, frac)      [writes file]
                    → invalidate()              [forces re-read on next resolve]
        """
        import data.car_weight_distribution as mod
        from data.car_weight_distribution import (
            set_overlay_path, invalidate, resolve_front_weight_dist,
        )

        monkeypatch.setattr(mod, "_OVERLAY_PATH", mod._OVERLAY_PATH)
        monkeypatch.setattr(mod, "_CACHE", mod._CACHE)

        overlay_path = str(tmp_path / "car_weight_distribution.user.json")
        store = CarWeightDistStore(overlay_path)

        # Step 1: bridge startup — register overlay path
        set_overlay_path(overlay_path)

        # Step 2: driver saves 62 % front (bridge divides by 100 → 0.62)
        assert store.set(_TEST_CAR, 0.62) is True

        # Step 3: bridge calls invalidate() so next resolve picks up the new file
        invalidate()

        result = resolve_front_weight_dist(_TEST_CAR)
        assert result == pytest.approx(0.62), (
            f"After store.set(0.62) + invalidate(), resolver must return 0.62 "
            f"(no restart needed — AC3 requires immediate visibility); got {result!r}"
        )

    # ------------------------------------------------------------------ #
    # AC4a: spring generator uses overlay fraction, not drivetrain prior  #
    # ------------------------------------------------------------------ #

    def test_spring_frequencies_use_overlay_fraction_not_drivetrain_prior(
        self, tmp_path, monkeypatch
    ):
        """AC4 direction: the RR drivetrain prior is 0.38 (rear-heavy → rear_hz ≥ front_hz).
        Saving overlay frac=0.62 (front-heavy) must reverse the split to front_hz > rear_hz.
        A wrong result (rear still stiffer) means the overlay was ignored and the prior used.
        """
        import data.car_weight_distribution as mod
        from data.car_weight_distribution import set_overlay_path, invalidate

        monkeypatch.setattr(mod, "_OVERLAY_PATH", mod._OVERLAY_PATH)
        monkeypatch.setattr(mod, "_CACHE", mod._CACHE)

        overlay_path = str(tmp_path / "car_weight_distribution.user.json")
        store = CarWeightDistStore(overlay_path)
        set_overlay_path(overlay_path)
        store.set(_TEST_CAR, 0.62)
        invalidate()

        sf = derive_spring_frequencies(self._vehicle(), OBJ_BASE)

        assert sf.front_hz > sf.rear_hz, (
            f"Overlay frac=0.62 (front-heavy) must make front_hz > rear_hz; "
            f"got front={sf.front_hz}, rear={sf.rear_hz}.  "
            "If rear is still stiffer the RR drivetrain prior (0.38) was used instead of the overlay."
        )

    # ------------------------------------------------------------------ #
    # AC4b: reason string labels the source as "car data file"            #
    # ------------------------------------------------------------------ #

    def test_spring_frequency_reason_labels_overlay_as_car_data_source(
        self, tmp_path, monkeypatch
    ):
        """AC4 reason: when the fraction is resolved from the overlay (no explicit arg),
        the reason string must say 'car data file', NOT 'override' (that label is only for
        the explicit front_weight_dist= keyword argument path)."""
        import data.car_weight_distribution as mod
        from data.car_weight_distribution import set_overlay_path, invalidate

        monkeypatch.setattr(mod, "_OVERLAY_PATH", mod._OVERLAY_PATH)
        monkeypatch.setattr(mod, "_CACHE", mod._CACHE)

        overlay_path = str(tmp_path / "car_weight_distribution.user.json")
        store = CarWeightDistStore(overlay_path)
        set_overlay_path(overlay_path)
        store.set(_TEST_CAR, 0.62)   # non-50 so bias_desc includes frac_label
        invalidate()

        sf = derive_spring_frequencies(self._vehicle(), OBJ_BASE)

        assert "car data" in sf.front_reason.lower(), (
            f"Fraction from the overlay must be labelled 'car data file' in the reason; "
            f"got front_reason={sf.front_reason!r}"
        )
        assert "override" not in sf.front_reason.lower(), (
            f"'override' label is reserved for the explicit front_weight_dist= kwarg path; "
            f"got front_reason={sf.front_reason!r}"
        )

    # ------------------------------------------------------------------ #
    # AC3 variant: overlay wins over an existing seed entry               #
    # ------------------------------------------------------------------ #

    def test_overlay_wins_over_seed_entry_for_resolver(self, tmp_path, monkeypatch):
        """AC3 seed-car variant: 'Toyota AE86 Levin D-Tuned' is in the real seed at 0.55.
        Writing 0.38 to the overlay must make the resolver return 0.38 (overlay wins),
        not 0.55 (seed).  This is the clearest proof of the merge order: OVERLAY-ON-SEED.
        """
        import data.car_weight_distribution as mod
        from data.car_weight_distribution import (
            set_overlay_path, invalidate, resolve_front_weight_dist,
        )

        monkeypatch.setattr(mod, "_OVERLAY_PATH", mod._OVERLAY_PATH)
        monkeypatch.setattr(mod, "_CACHE", mod._CACHE)

        overlay_path = str(tmp_path / "car_weight_distribution.user.json")
        store = CarWeightDistStore(overlay_path)
        set_overlay_path(overlay_path)

        # Confirm seed value is still 0.55 (no overlay written yet)
        invalidate()
        seed_resolved = resolve_front_weight_dist(_SEED_CAR)
        assert seed_resolved == pytest.approx(_SEED_CAR_FRAC), (
            f"Baseline: resolver should return seed value {_SEED_CAR_FRAC!r} "
            f"for {_SEED_CAR!r}; got {seed_resolved!r}"
        )

        # Save a different value (rear-heavy) to the overlay
        assert store.set(_SEED_CAR, 0.38) is True
        invalidate()

        overlay_resolved = resolve_front_weight_dist(_SEED_CAR)
        assert overlay_resolved == pytest.approx(0.38), (
            f"After overlay write of 0.38, resolver must return 0.38 (overlay wins over seed 0.55); "
            f"got {overlay_resolved!r}"
        )


# ===========================================================================
# AC6 gap — store.set returning False → failure garage status (Qt required)
# ===========================================================================
# Existing tests cover: empty car, zero pct, and success status.
# The missing branch: store.set() returns False (e.g. filesystem error or value
# rejected by the store's own guard) → the bridge emits a failure status.
# ===========================================================================

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Auth:
    class _Active:
        def label(self):
            return "Race v2"

        @property
        def is_active_on_car(self):
            return True

    def active_setup(self, identity, purpose="Race"):
        return self._Active() if purpose == "Race" else None


class _Form:
    def current_setup_dict(self):
        return {"arb_front": 5, "arb_rear": 4,
                "tyre_front": "Racing: Hard", "tyre_rear": "Racing: Hard"}

    def apply_ai_fields(self, fields):
        pass


class _FakeWindow:
    def __init__(self):
        self._race_form = _Form()
        self._setup_authority = _Auth()

    def _build_event_context(self):
        from data.event_context import build_event_context
        return build_event_context(
            event={"id": 1, "name": "Test Event"},
            strategy={"car": "GT-R", "track_location_id": "fuji"},
        )

    def _build_session_context(self):
        from data.session_context import build_session_context
        return build_session_context(connected=True, packet_count=5, laps_recorded=2)

    def _build_strategy_context(self):
        return None

    def _autosave_applied_setup(self, form):
        pass

    def _revert_last_change_for_form(self, form):
        pass


def _make_bridge(qapp):
    from ui.live_shell_bridge import LiveShellBridge
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    win = _FakeWindow()
    cfg = {"strategy": {"car": "GT-R", "track": "Fuji Speedway"}}
    b = LiveShellBridge(shell, ctrl, window=win, config=cfg)
    b.refresh()
    return b, shell


class TestAC6StoreFailure:
    """AC6 gap: when CarWeightDistStore.set() returns False the bridge must emit a
    failure status message that communicates the problem to the driver.

    The other AC6 branches are covered by test_live_shell_bridge.py::TestSaveFrontWeightDist.
    """

    class _FailingStore:
        """A store stub that always returns False from set() — simulates a write failure
        (e.g., filesystem error or the store's own fraction guard)."""

        def set(self, car_name: str, frac: float) -> bool:
            return False

    def test_store_set_false_produces_failure_status(self, qapp, monkeypatch):
        """AC6: store.set returns False → garage status must communicate the failure,
        NOT silently succeed or show nothing."""
        b, shell = _make_bridge(qapp)
        b._car_wt_store = self._FailingStore()
        monkeypatch.setattr(b._car_wt_mod, "invalidate", lambda: None)

        b._front_weight_dist_pct = 99.0
        monkeypatch.setattr(
            b._setups, "inputs",
            lambda: type("I", (), {"car": "Test Car For Failure"})(),
        )

        b._on_save_front_weight_dist()

        status = shell.garage_page._status.text().lower()
        assert "could not" in status, (
            f"When store.set returns False the garage status must contain "
            f"'could not'; got {status!r}"
        )

    def test_store_set_false_status_does_not_say_saved(self, qapp, monkeypatch):
        """AC6 negative: the failure path must never emit a 'saved' confirmation
        (which would mislead the driver into thinking the value was persisted)."""
        b, shell = _make_bridge(qapp)
        b._car_wt_store = self._FailingStore()
        monkeypatch.setattr(b._car_wt_mod, "invalidate", lambda: None)

        b._front_weight_dist_pct = 55.0
        monkeypatch.setattr(
            b._setups, "inputs",
            lambda: type("I", (), {"car": "Another Car"})(),
        )

        b._on_save_front_weight_dist()

        status = shell.garage_page._status.text().lower()
        # The success path says "Saved X% front for <car>"
        assert "saved" not in status, (
            f"A store failure must not produce a 'saved' confirmation; got {status!r}"
        )


# ===========================================================================
# AC7 — Safety guards (integration level via the real set_overlay_path path)
# ===========================================================================
# Unit-level coverage already exists in test_car_weight_dist_store.py and
# test_car_weight_distribution.py.  These tests exercise the same code via
# the set_overlay_path() entry point that the bridge uses at startup.
# ===========================================================================

class TestAC7SafetyGuards:
    """AC7: degraded inputs (corrupt file, missing file, empty path) must never raise
    and must produce a usable fallback — the real set_overlay_path() entry point used."""

    def test_empty_path_store_never_writes_a_file(self, tmp_path):
        """AC7: CarWeightDistStore("") keeps the value in memory only.
        set() returns True (so callers do not treat it as a failure), the value is
        readable via overlay(), but no file is created in the filesystem."""
        store = CarWeightDistStore("")
        result = store.set("Any Car", 0.42)
        assert result is True, "empty-path store.set must return True (in-memory success)"
        assert store.overlay().get("Any Car") == pytest.approx(0.42), (
            "Value must be readable from the in-memory store immediately after set()"
        )
        # No file written inside tmp_path (or anywhere the test controls)
        files = list(tmp_path.iterdir())
        assert files == [], (
            f"empty-path store must not write any file; found {files} in tmp_path"
        )

    def test_corrupt_overlay_via_set_overlay_path_falls_back_to_seed(
        self, tmp_path, monkeypatch
    ):
        """AC7: a corrupt overlay registered via the REAL set_overlay_path() is silently
        ignored; the resolver still returns the correct seed value (never raises).

        This covers the exact startup sequence the bridge uses:
          bridge.__init__ → set_overlay_path(overlay_path)
        If the file at that path is corrupt, the app must degrade gracefully."""
        import data.car_weight_distribution as mod
        from data.car_weight_distribution import (
            set_overlay_path, resolve_front_weight_dist,
        )

        monkeypatch.setattr(mod, "_OVERLAY_PATH", mod._OVERLAY_PATH)
        monkeypatch.setattr(mod, "_CACHE", mod._CACHE)

        corrupt_overlay = tmp_path / "car_weight_distribution.user.json"
        corrupt_overlay.write_text("{ this is not : valid JSON !", encoding="utf-8")

        # set_overlay_path is the bridge's startup call
        set_overlay_path(str(corrupt_overlay))

        # "Toyota AE86 Levin D-Tuned" is in the real seed at 0.55; it must still resolve.
        result = resolve_front_weight_dist(_SEED_CAR)
        assert result == pytest.approx(_SEED_CAR_FRAC), (
            f"Corrupt overlay must be silently ignored; seed car {_SEED_CAR!r} "
            f"must still resolve to {_SEED_CAR_FRAC}; got {result!r}"
        )

    def test_missing_overlay_via_set_overlay_path_falls_back_to_seed(
        self, tmp_path, monkeypatch
    ):
        """AC7: a non-existent overlay path registered via set_overlay_path() is silently
        tolerated; the resolver returns the seed value without error."""
        import data.car_weight_distribution as mod
        from data.car_weight_distribution import (
            set_overlay_path, resolve_front_weight_dist,
        )

        monkeypatch.setattr(mod, "_OVERLAY_PATH", mod._OVERLAY_PATH)
        monkeypatch.setattr(mod, "_CACHE", mod._CACHE)

        nonexistent = str(tmp_path / "does_not_exist.json")
        set_overlay_path(nonexistent)

        result = resolve_front_weight_dist(_SEED_CAR)
        assert result == pytest.approx(_SEED_CAR_FRAC), (
            f"Missing overlay must not block seed resolution; "
            f"expected {_SEED_CAR_FRAC}, got {result!r}"
        )
