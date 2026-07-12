"""Adversarial Setup-Brain quality audit — permanent regression tests.

Added by the 2026-07-12 principal-engineer adversarial audit. These tests encode
the audit's non-negotiable engineering standards so the defects it found can never
silently return:

Defect A (fixed) — from-scratch baseline clamped flat neutral seeds to a car's
    MIN/MAX on narrow or shifted car-specific ranges (e.g. Porsche 963 aero and
    springs pinned to their minimum), surfacing range-valid but engineering-poor
    values with no provenance. strategy/setup_baseline.py now re-places a
    boundary-hugging seed by its generic-range INTENT (see _place_seed_in_range).

Defect B (fixed) — physics rule C3_mid_arb_rear SOFTENED the rear ARB to cure
    mid-corner understeer, which adds rear grip and makes understeer WORSE. It now
    STIFFENS the rear ARB (arb_rear +1), the physically correct direction.

The baseline-quality audit is intentionally reusable: it fails on unjustified
boundary values, undisclosed near-boundary clamps, max ride height as a generic
baseline, and blind cross-car value duplication — while ALLOWING a small set of
engineering-justified boundary defaults (power_restrictor=max, ballast=min) and
the disclosed, car-authority-free gearbox shape.
"""
from __future__ import annotations

import pytest

from strategy.setup_baseline import build_baseline_setup, _LABEL_CAR_RANGE
from strategy.setup_ranges import resolve_ranges, GENERIC_DEFAULTS
import strategy.setup_knowledge_base as kb


# ---------------------------------------------------------------------------
# Gearbox fields are audited separately (monotonicity + disclosed no-car-authority)
# ---------------------------------------------------------------------------
_GEARBOX_FIELDS = frozenset({
    "final_drive", "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
    "transmission_max_speed_kmh",
})

# Boundary values that ARE engineering-justified as a from-scratch default and so
# are exempt from the "no unjustified extreme" rule. Each is a (field, end) pair.
#   power_restrictor @ max  → 100% = engine unrestricted (the correct default)
#   ballast_kg      @ min  → 0 kg = no added ballast (the correct default)
_JUSTIFIED_BOUNDARY = {
    ("power_restrictor", "max"),
    ("ballast_kg", "min"),
}

# Labels that honestly disclose a value was placed relative to the car range
# rather than being a blind clamp of an out-of-range seed.
_ADAPTED_LABELS = frozenset({_LABEL_CAR_RANGE})

_NEAR = 0.05  # lowest/highest 5% of a range counts as "near boundary"


def _car_matrix():
    """Representative matrix: archetypes on generic ranges, the two shipped
    car-specific ranges, plus synthetic narrow/shifted ranges that stress the
    seed-placement logic the way a real tight race-car range does."""
    generic = resolve_ranges("")

    # Synthetic car whose ranges are deliberately narrow/shifted so a flat seed
    # would clamp to a boundary on many fields at once (the Defect-A population).
    narrow = dict(generic)
    narrow.update({
        "springs_front": (6.0, 9.0),      # seed 3.5 is BELOW min
        "springs_rear": (6.0, 9.0),       # seed 3.0 is BELOW min
        "aero_front": (750, 850),         # seed 400 is BELOW min
        "aero_rear": (900, 1300),         # seed 600 is BELOW min
        "camber_front": (2.0, 4.0),       # seed 1.0 is BELOW min
        "lsd_decel": (12, 60),            # seed 5 is BELOW min
        "arb_front": (6, 10),             # seed 5 is BELOW min
        "ride_height_front": (55, 70),    # tight race-car front
        "ride_height_rear": (60, 75),
    })

    return [
        ("RR/generic", "", "RR", 6, generic),
        ("FR/generic", "", "FR", 6, generic),
        ("MR/generic", "", "MR", 6, generic),
        ("FF/generic", "", "FF", 5, generic),
        ("AWD/generic", "", "AWD", 6, generic),
        ("Porsche 911 RSR '17", "Porsche 911 RSR (991) '17", "MR", 6,
         resolve_ranges("Porsche 911 RSR (991) '17")),
        ("Porsche 963 '24", "Porsche 963 '24", "MR", 7,
         resolve_ranges("Porsche 963 '24")),
        ("synthetic narrow race", "Synthetic Narrow", "MR", 6, narrow),
    ]


def _norm(value, lo, hi):
    if hi == lo:
        return None
    return (float(value) - lo) / (hi - lo)


def _build(car, ranges, drivetrain, num_gears):
    return build_baseline_setup(
        car=car or "generic", ranges=ranges, drivetrain=drivetrain,
        num_gears=num_gears, profile=None, allowed_tuning=None, tuning_locked=False,
    )


# ---------------------------------------------------------------------------
# Defect A — baseline-quality audit
# ---------------------------------------------------------------------------

class TestBaselineQualityAudit:

    def _iter_non_gearbox(self, rd, ranges):
        for ch in rd["changes"]:
            f = ch["field"]
            if f in _GEARBOX_FIELDS or f not in ranges:
                continue
            val = ch["to_clamped"]
            if not isinstance(val, (int, float)):
                continue
            lo, hi = ranges[f]
            n = _norm(val, lo, hi)
            if n is None:  # degenerate range (min == max) — nothing to author
                continue
            yield f, val, lo, hi, n, ch

    @pytest.mark.parametrize("label,car,dt,ng", [
        (m[0], m[1], m[2], m[3]) for m in _car_matrix()
    ])
    def test_no_unjustified_boundary_value(self, label, car, dt, ng):
        """No authored non-gearbox field sits exactly at its min or max unless the
        boundary is an explicitly justified engineering default."""
        ranges = dict([m for m in _car_matrix() if m[0] == label][0][4])
        rd = _build(car, ranges, dt, ng)
        offenders = []
        for f, val, lo, hi, n, ch in self._iter_non_gearbox(rd, ranges):
            if n <= 0.0 and (f, "min") not in _JUSTIFIED_BOUNDARY:
                offenders.append(f"{f}={val} at MIN ({lo}) label={ch.get('source_label')!r}")
            if n >= 1.0 and (f, "max") not in _JUSTIFIED_BOUNDARY:
                offenders.append(f"{f}={val} at MAX ({hi}) label={ch.get('source_label')!r}")
        assert not offenders, (
            f"[{label}] unjustified boundary value(s) in from-scratch baseline:\n  "
            + "\n  ".join(offenders)
        )

    @pytest.mark.parametrize("label,car,dt,ng", [
        (m[0], m[1], m[2], m[3]) for m in _car_matrix()
    ])
    def test_near_boundary_values_disclose_provenance(self, label, car, dt, ng):
        """A value pushed into the outer 5% of a car range must disclose that it was
        car-range adapted (or be a justified default) — never a silent clamp wearing
        a plain 'neutral default' label."""
        ranges = dict([m for m in _car_matrix() if m[0] == label][0][4])
        rd = _build(car, ranges, dt, ng)
        offenders = []
        for f, val, lo, hi, n, ch in self._iter_non_gearbox(rd, ranges):
            near_min = n <= _NEAR and (f, "min") not in _JUSTIFIED_BOUNDARY
            near_max = n >= (1.0 - _NEAR) and (f, "max") not in _JUSTIFIED_BOUNDARY
            if near_min or near_max:
                lbl = ch.get("source_label", "")
                if lbl not in _ADAPTED_LABELS:
                    offenders.append(
                        f"{f}={val} at norm {n*100:.1f}% but label={lbl!r} "
                        "(undisclosed near-boundary clamp)")
        assert not offenders, (
            f"[{label}] near-boundary value(s) without provenance:\n  "
            + "\n  ".join(offenders)
        )

    @pytest.mark.parametrize("label,car,dt,ng", [
        (m[0], m[1], m[2], m[3]) for m in _car_matrix()
    ])
    def test_ride_height_never_at_or_near_max(self, label, car, dt, ng):
        """A generic no-telemetry baseline must never default ride height to (or near)
        the maximum — the headline defect the audit guards against."""
        ranges = dict([m for m in _car_matrix() if m[0] == label][0][4])
        rd = _build(car, ranges, dt, ng)
        for ch in rd["changes"]:
            if ch["field"] in ("ride_height_front", "ride_height_rear"):
                lo, hi = ranges[ch["field"]]
                n = _norm(ch["to_clamped"], lo, hi)
                assert n is None or n < (1.0 - _NEAR), (
                    f"[{label}] {ch['field']}={ch['to_clamped']} is at/near MAX "
                    f"({hi}); a generic baseline must bias ride height low.")

    def test_field_provenance_present_on_every_change(self):
        """Every authored change carries a non-empty source_label (provenance)."""
        for label, car, dt, ng, ranges in _car_matrix():
            rd = _build(car, ranges, dt, ng)
            for ch in rd["changes"]:
                assert ch.get("source_label"), (
                    f"[{label}] {ch['field']} has no source_label provenance")

    def test_narrow_ranges_do_not_pin_aero_or_springs_to_min(self):
        """Regression for Defect A: on a high-floor race-car range the neutral aero
        and spring seeds must be re-placed off the minimum, not clamped onto it."""
        narrow = [m for m in _car_matrix() if m[0] == "synthetic narrow race"][0][4]
        rd = _build("Synthetic Narrow", narrow, "MR", 6)
        by_field = {ch["field"]: ch for ch in rd["changes"]}
        for f in ("aero_front", "aero_rear", "springs_front", "springs_rear",
                  "camber_front", "lsd_decel"):
            lo, hi = narrow[f]
            n = _norm(by_field[f]["to_clamped"], lo, hi)
            assert n is not None and n > _NEAR, (
                f"{f} pinned to/near min ({by_field[f]['to_clamped']}, norm "
                f"{None if n is None else round(n*100,1)}%) on a narrow race range")
            assert by_field[f]["source_label"] == _LABEL_CAR_RANGE, (
                f"{f} re-placed but not disclosed as car-range adapted")

    def test_no_blind_absolute_duplication_across_different_ranges(self):
        """Materially different aero ranges must yield materially different aero
        VALUES — the intent (normalised position) may repeat, blind absolute
        duplication must not."""
        rsr = _build("Porsche 911 RSR (991) '17", resolve_ranges("Porsche 911 RSR (991) '17"), "MR", 6)
        p963 = _build("Porsche 963 '24", resolve_ranges("Porsche 963 '24"), "MR", 7)
        def val(rd, field):
            return {c["field"]: c["to_clamped"] for c in rd["changes"]}[field]
        # 963 runs far more rear downforce than the RSR; the baseline must reflect it.
        assert val(p963, "aero_rear") != val(rsr, "aero_rear")
        assert val(p963, "aero_front") != val(rsr, "aero_front")


# ---------------------------------------------------------------------------
# Baseline gearbox — disclosed, monotonic, usable (no car-authority available)
# ---------------------------------------------------------------------------

class TestBaselineGearbox:

    def test_gearbox_strictly_monotonic_decreasing(self):
        for label, car, dt, ng, ranges in _car_matrix():
            rd = _build(car, ranges, dt, ng)
            gears = [ch["to_clamped"] for ch in rd["changes"]
                     if ch["field"].startswith("gear_")]
            for a, b in zip(gears, gears[1:]):
                assert b < a, f"[{label}] gearbox not strictly decreasing: {gears}"

    def test_final_drive_present_and_in_range(self):
        for label, car, dt, ng, ranges in _car_matrix():
            rd = _build(car, ranges, dt, ng)
            fds = [ch["to_clamped"] for ch in rd["changes"] if ch["field"] == "final_drive"]
            assert fds and 2.5 <= fds[0] <= 6.0, f"[{label}] final_drive {fds}"


# ---------------------------------------------------------------------------
# Defect B — physics direction guard for C3 (rear ARB vs understeer)
# ---------------------------------------------------------------------------

class TestPhysicsDirection:

    def _rule(self, rule_id):
        return next(r for r in kb.get_all_rules() if r.rule_id == rule_id)

    def test_c3_stiffens_rear_arb_for_understeer(self):
        """Mid-corner understeer must STIFFEN the rear ARB (delta > 0). Softening it
        (delta < 0) adds rear grip and worsens understeer — a wrong-direction defect."""
        c3 = self._rule("C3_mid_arb_rear")
        assert c3.field == "arb_rear"
        delta = kb._DELTA_RESOLVERS[c3.delta_fn]({}, {}, {})
        assert delta > 0, (
            f"C3_mid_arb_rear delta={delta}: rear ARB must be STIFFENED for "
            "understeer, not softened.")

    def test_c7_still_softens_rear_arb_for_kerb_compliance(self):
        """C7 (kerb/compliance) correctly SOFTENS the rear ARB — unchanged."""
        c7 = self._rule("C7_kerb_arb_rear")
        assert c7.field == "arb_rear"
        delta = kb._DELTA_RESOLVERS[c7.delta_fn]({}, {}, {})
        assert delta < 0, f"C7_kerb_arb_rear delta={delta}: kerb compliance softens rear ARB."
