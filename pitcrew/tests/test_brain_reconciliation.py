"""Keep the knowledge base and the code from drifting apart silently.

`brain/RECONCILIATION.md` records where the two records of this system agreed
and disagreed on 21 Aug 2026. Six defects the knowledge base still listed as
open were already closed in the code, and one mechanism the knowledge base
believed had been disproved by the telemetry four days earlier. **Neither
record knew, because nothing checked.**

So this file is the check. Each test encodes one claim from that reconciliation
as an executable assertion, and **a failure here is not necessarily a bug** —
it means the code moved and `brain/RECONCILIATION.md` is now out of date. The
failure message says which section to amend.

Two directions, both loud:

* Section A claims are things the code **does** do. If one breaks, the app has
  regressed to a state the knowledge base already describes as a defect.
* Section B claims are things the code **does not yet** do. If one breaks, the
  defect has been fixed and the knowledge base should stop warning about it.

**A test that asserts a defect still exists is deliberate.** The alternative is
that a fix lands, nobody updates the knowledge base, and a document keeps
telling a race engineer to work around something that no longer happens.
"""
from __future__ import annotations

import inspect

from pitcrew.analysis import gearing, thresholds
from pitcrew.export import build, payload
from pitcrew.store import schema

AMEND = "brain/RECONCILIATION.md"


# --------------------------------------------------------------- section A
# Closed in the code. The knowledge base still lists them as open.

def test_a1_drivetrain_is_used_not_merely_stored():
    """`15` §3: "tell Pit Crew this car is MR - outstanding since 14 Aug"."""
    assert thresholds.wheelspin_wheels("MR") == ("rl", "rr"), (
        f"drivetrain no longer narrows the wheelspin test. {AMEND} §A1 says it "
        f"does; if that is deliberate, amend it.")
    assert thresholds.wheelspin_wheels(None) == thresholds.ALL_WHEELS
    # And the catalogue answers when nobody has declared, with its source.
    assert "from the car catalogue" in thresholds.wheelspin_wheels_note(
        "MR", "catalogue")
    assert "declared" in thresholds.wheelspin_wheels_note("MR", "declared")


def test_a2_gearing_constant_prefers_the_sheets_final_drive():
    """`15` §5.1: computed with the derived final gear, not the sheet's.

    The reported 1126.4 against a correct 1092.5 - 3% out, on the number that
    drives gearbox changes.
    """
    source = inspect.getsource(gearing.gearing_constant)
    assert "sheet_final_gear or derived_final_gear" in source, (
        f"gearingConstantK no longer prefers the sheet's final drive. "
        f"{AMEND} §A2 says it does.")


def test_a3_the_calls_ledger_has_more_than_a_boolean():
    """`15` §5.2: `accepted` false on all 14 calls, including "Green, green"."""
    source = inspect.getsource(payload)
    assert '"disposition"' in source, (
        f"the calls ledger lost its disposition field and is a boolean again. "
        f"{AMEND} §A3 says it has one. An informational call cannot be "
        f"'declined'.")


def test_a4_the_packets_wheelbase_is_stored():
    """`15` §2: understeer judged every car against the RSR's 2.516 m."""
    columns = dict(schema.ADDED_COLUMNS["sessions"])
    assert "wheelbase_m" in columns, (
        f"sessions.wheelbase_m is gone. {AMEND} §A4 says the packet's own "
        f"wheelbase is stored; without it every car is judged against "
        f"{thresholds.DEFAULT_WHEELBASE_M} m again.")
    # The fallback may exist, but it must never be silent about being one.
    assumed = thresholds.as_export(wheelbase_m=None)
    assert "assumed" in assumed["understeerWheelbaseSource"].lower()
    measured = thresholds.as_export(wheelbase_m=2.62)
    assert measured["understeerWheelbaseM"] == 2.62


def test_a6_the_export_refuses_a_payload_with_no_game_version():
    """`17` §8 and Standing Rule 10: "gameVersion is missing from the packet".

    It is required, and has been since contract 1.4. What was missing was
    anything *filling* it - a different defect, fixed 21 Aug.
    """
    source = inspect.getsource(payload)
    assert "meta.gameVersion is required" in source, (
        f"the export no longer refuses a versionless payload. {AMEND} §A6 "
        f"says it does, and Standing Rule 10 depends on it.")


def test_d2_an_event_that_straddles_a_patch_still_refuses():
    """`RECONCILIATION.md` §D2. Event 1 spans the 20 Aug patch."""
    def run(sid, when, version):
        return {"id": sid, "started_at": when, "game_version": version,
                "packet_format": "C", "setup_sheet_id": None,
                "practice_intent": None, "practice_mode": None,
                "car_category": "GR3", "fuel_capacity_l": 100.0,
                "identity_status": "ok"}
    try:
        build._merged_session([run(1, "2026-08-19T10:00:00", "1.70"),
                               run(2, "2026-08-21T10:00:00", "1.71")])
    except ValueError:
        return
    raise AssertionError(
        f"an event spanning two GT7 versions exported as one body of evidence. "
        f"{AMEND} §D2 says it refuses.")


# --------------------------------------------------------------- section B
# Open in the code. The knowledge base is right to warn about them.
#
# **These assert that a defect is still present.** When one starts failing the
# news is good: delete the test and strike the row from section B.

def test_b2_the_bottoming_flag_still_has_no_mean_heave_figure():
    """`15` §1 fix 2: report mean heave across the four wheels.

    Roll cancels in the mean and contact does not, which is the cheapest way to
    tell them apart. The polarity error underneath it is fixed (§C1); this
    improvement is not.
    """
    exported = thresholds.as_export()
    assert not any("heave" in str(k).lower() for k in exported), (
        f"a mean-heave figure has appeared in the thresholds block. That closes "
        f"{AMEND} §B2 - delete this test and strike the row.")
