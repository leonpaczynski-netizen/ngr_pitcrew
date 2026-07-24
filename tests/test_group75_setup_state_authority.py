"""UAT Finding 1 — canonical applied-setup-state authority (deterministic core).

Pure, Qt-free tests of the setup-state model + policy that makes the applied
setup the Live Race Engineer's baseline. Covers required tests:

  1. Applied setup automatically becomes the active (Live) setup.
  2. Proposed setup does NOT become active before confirmation.
  3. Active setup persists and restores after restart.
  4. Car/track/layout mismatch blocks setup-specific analysis.
  5. Telemetry and feedback attach to the correct setup revision.
  7. Applied status changes without altering the recommendation snapshot.
"""
from __future__ import annotations

from data.setup_state_authority import (
    ActiveSetupAuthority, SetupIdentity, SetupState, AnalysisBlockReason,
    evaluate_analysis_gate, ActiveSetup,
)
from data.active_setup_store import InMemoryActiveSetupStore
from data.applied_checkpoint import compute_setup_hash


FUJI = SetupIdentity(car="Porsche 911 RSR", track="Fuji", layout_id="full_course")
SUZUKA = SetupIdentity(car="Porsche 911 RSR", track="Suzuka", layout_id="full_course")

COMPLETE = {"front_ride_height": 70, "rear_ride_height": 75, "front_arb": 5,
            "rear_arb": 4, "front_wing": 3, "rear_wing": 6}
REQUIRED = ("front_ride_height", "rear_ride_height", "front_wing", "rear_wing")


# --------------------------------------------------------------------------- #
# Test 1 — applied setup automatically becomes the active setup
# --------------------------------------------------------------------------- #

def test_applied_setup_becomes_active():
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    assert auth.active_setup(FUJI) is None

    applied = auth.mark_applied(
        FUJI, setup_id="R-Baseline-1", name="Race Baseline",
        fields=COMPLETE, purpose="Race", applied_at="2026-07-18 10:00")

    active = auth.active_setup(FUJI, "Race")
    assert active is not None
    assert active.state is SetupState.APPLIED
    assert active.is_active_on_car
    assert active.setup_id == "R-Baseline-1"
    assert active.revision == 1
    assert active is applied or active.to_record() == applied.to_record()

    # The gate opens for the exact matching session identity.
    gate = auth.analysis_gate(FUJI, "Race", required_fields=REQUIRED)
    assert gate.allowed
    assert gate.reason is AnalysisBlockReason.OK
    assert gate.active.setup_id == "R-Baseline-1"


# --------------------------------------------------------------------------- #
# Test 2 — proposed setup does not become active before confirmation
# --------------------------------------------------------------------------- #

def test_proposed_setup_is_not_active():
    # A merely proposed recommendation, never marked applied.
    proposed = ActiveSetup(
        identity=FUJI, setup_id="rec-1", name="Proposed fix", revision=1,
        state=SetupState.PROPOSED, fields=COMPLETE,
        setup_hash=compute_setup_hash(COMPLETE))
    assert not proposed.is_active_on_car

    gate = evaluate_analysis_gate(proposed, FUJI, required_fields=REQUIRED)
    assert gate.blocked
    assert gate.reason is AnalysisBlockReason.NOT_APPLIED

    # And an authority that never had mark_applied called has no active setup.
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    assert auth.active_setup(FUJI) is None
    assert auth.analysis_gate(FUJI, "Race").reason is AnalysisBlockReason.NO_ACTIVE_SETUP


# --------------------------------------------------------------------------- #
# Test 3 — active setup persists and restores after restart
# --------------------------------------------------------------------------- #

def test_active_setup_persists_and_restores():
    store = InMemoryActiveSetupStore()
    auth = ActiveSetupAuthority(store=store)
    auth.mark_applied(FUJI, setup_id="R-Baseline-1", name="Race Baseline",
                      fields=COMPLETE, applied_at="2026-07-18 10:00")

    # "Restart": a brand-new authority reading the same store.
    restored = ActiveSetupAuthority(store=store)
    active = restored.active_setup(FUJI, "Race")
    assert active is not None
    assert active.setup_id == "R-Baseline-1"
    assert active.name == "Race Baseline"
    assert active.revision == 1
    assert active.state is SetupState.APPLIED
    assert active.fields == COMPLETE


def test_json_store_roundtrip(tmp_path):
    from data.active_setup_store import JsonActiveSetupStore
    store = JsonActiveSetupStore(tmp_path / "active_setup_state.json")
    auth = ActiveSetupAuthority(store=store)
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
    assert store.path.exists()

    reloaded = ActiveSetupAuthority(store=JsonActiveSetupStore(store.path))
    assert reloaded.active_setup(FUJI).setup_id == "R1"


# --------------------------------------------------------------------------- #
# Test 4 — car/track/layout mismatch blocks setup-specific analysis
# --------------------------------------------------------------------------- #

def test_identity_mismatch_blocks_analysis():
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)

    # Same car, different track -> mismatch, not "no active setup".
    gate = auth.analysis_gate(SUZUKA, "Race", required_fields=REQUIRED)
    assert gate.blocked
    assert gate.reason is AnalysisBlockReason.IDENTITY_MISMATCH


def test_layout_mismatch_blocks_analysis():
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
    other_layout = SetupIdentity(car="Porsche 911 RSR", track="Fuji",
                                 layout_id="short_course")
    gate = auth.analysis_gate(other_layout, "Race")
    assert gate.blocked
    assert gate.reason is AnalysisBlockReason.IDENTITY_MISMATCH


def test_incomplete_snapshot_blocks_analysis():
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    partial = {"front_ride_height": 70}  # missing required fields
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=partial)
    gate = auth.analysis_gate(FUJI, "Race", required_fields=REQUIRED)
    assert gate.blocked
    assert gate.reason is AnalysisBlockReason.INCOMPLETE_SNAPSHOT


def test_stale_editor_blocks_analysis():
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
    # Editor drifted from the applied snapshot.
    drifted = dict(COMPLETE)
    drifted["rear_wing"] = 9
    gate = auth.analysis_gate(FUJI, "Race", required_fields=REQUIRED,
                              editor_fields=drifted)
    assert gate.blocked
    assert gate.reason is AnalysisBlockReason.STALE

    # Unchanged editor passes.
    ok = auth.analysis_gate(FUJI, "Race", required_fields=REQUIRED,
                            editor_fields=dict(COMPLETE))
    assert ok.allowed


# --------------------------------------------------------------------------- #
# Test 5 — telemetry/feedback attach to the correct setup revision
# --------------------------------------------------------------------------- #

def test_attach_target_tracks_revision():
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    assert auth.attach_target(FUJI) == ("", 0)  # nothing applied yet

    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
    assert auth.attach_target(FUJI, "Race") == ("R1", 1)

    # Apply a revised setup -> revision increments, attachment follows.
    revised = dict(COMPLETE)
    revised["rear_wing"] = 7
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=revised)
    assert auth.attach_target(FUJI, "Race") == ("R1", 2)
    assert auth.active_setup(FUJI).revision == 2

    # Qualifying is a separate scope with its own revision line.
    auth.mark_applied(FUJI, setup_id="Q1", name="Quali", fields=COMPLETE,
                      purpose="Qualifying")
    assert auth.attach_target(FUJI, "Qualifying") == ("Q1", 1)
    assert auth.attach_target(FUJI, "Race") == ("R1", 2)


# --------------------------------------------------------------------------- #
# UAT-6 — re-confirming an UNCHANGED setup is not a new setup
# --------------------------------------------------------------------------- #

def test_reconfirming_an_unchanged_setup_keeps_the_revision():
    """UAT-6: "even when setup isn't changed if I click I have entered this in GT7 to
    activate current setup it saves it as a new setup".

    The driver presses this whenever they re-enter the sheet in GT7 — after switching
    discipline, after a restart, or just to be sure. Every press minted a revision, so a
    setup that had never been edited reached "rev 13".
    """
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    first = auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
    assert first.revision == 1

    for _ in range(5):
        again = auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
        assert again.revision == 1
    assert auth.active_setup(FUJI).revision == 1
    assert auth.attach_target(FUJI, "Race") == ("R1", 1)

    # A real change still advances the revision — this must not freeze the lineage.
    changed = dict(COMPLETE)
    changed["rear_wing"] = 8
    assert auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=changed).revision == 2
    # ...and re-confirming THAT one holds at 2.
    assert auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=changed).revision == 2


def test_reconfirming_still_refreshes_the_confirmation():
    """Holding the revision must not lose WHEN the driver confirmed it, or its state."""
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE,
                      applied_at="2026-07-24 10:00")
    auth.start_validation(FUJI)
    again = auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE,
                              applied_at="2026-07-24 11:30")
    assert again.revision == 1
    assert again.applied_at == "2026-07-24 11:30"
    assert again.state is SetupState.APPLIED
    assert again.setup_hash == compute_setup_hash(COMPLETE)


def test_a_different_setup_id_at_the_same_values_is_still_a_new_revision():
    """Same numbers under a different name is a different setup being confirmed."""
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
    other = auth.mark_applied(FUJI, setup_id="R2", name="Copy", fields=COMPLETE)
    assert other.revision == 2 and other.setup_id == "R2"


# --------------------------------------------------------------------------- #
# Test 7 — applied status changes without altering the recommendation snapshot
# --------------------------------------------------------------------------- #

def test_state_transitions_preserve_snapshot():
    auth = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
    applied = auth.mark_applied(FUJI, setup_id="R1", name="Base", fields=COMPLETE)
    snapshot = dict(applied.fields)
    rev = applied.revision
    h = applied.setup_hash

    val = auth.start_validation(FUJI, "Race")
    assert val.state is SetupState.VALIDATION
    assert val.fields == snapshot and val.revision == rev and val.setup_hash == h
    assert val.is_active_on_car

    acc = auth.accept(FUJI, "Race")
    assert acc.state is SetupState.ACCEPTED
    assert acc.fields == snapshot and acc.revision == rev and acc.setup_hash == h
    assert acc.is_active_on_car

    # VALIDATION / ACCEPTED still permit setup-specific analysis (on the car).
    assert auth.analysis_gate(FUJI, "Race", required_fields=REQUIRED).allowed
