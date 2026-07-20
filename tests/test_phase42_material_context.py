"""Phase 42 — material context requirements, field trust, domain eligibility, legacy handling."""
from strategy.material_context import (
    build_material_context_trust, field_trust, ContextFieldTrust, ContextTrust, DOMAIN_REQUIRED,
    context_snapshot_fingerprint,
)
from strategy.legacy_evidence_trust import build_legacy_evidence_trust


_CUR = {"driver": "Leon", "car": "Porsche", "car_variant": "RSR", "track": "Fuji", "layout_id": "fc",
        "discipline": "race", "compound": "RH", "tuning_permitted": "yes", "bop_state": "on",
        "power_restriction": "95", "weight_restriction": "0", "gt7_version": "1.49",
        "applied_setup_id": "S1", "tyre_multiplier": "1", "fuel_multiplier": "1", "event_id": "E1",
        "race_objective": "laps:12"}
# a legacy record with known identity but UNKNOWN BoP and tyre/fuel multipliers
_LEGACY = {"driver": "Leon", "car": "Porsche", "track": "Fuji", "layout_id": "fc",
           "discipline": "race", "compound": "RH", "gt7_version": "1.49"}


# ---- 1/2. material requirements + field-level trust ----------------------------------------- #
def test_field_trust_states():
    assert field_trust("a", "a") is ContextFieldTrust.KNOWN_MATCH
    assert field_trust("a", "b") is ContextFieldTrust.KNOWN_DIFFERENT
    assert field_trust("", "b") is ContextFieldTrust.UNKNOWN_CURRENT
    assert field_trust("a", "") is ContextFieldTrust.UNKNOWN_HISTORICAL
    assert field_trust("", "") is ContextFieldTrust.UNKNOWN_BOTH


# ---- 3. unknown vs mismatch ----------------------------------------------------------------- #
def test_unknown_is_neither_match_nor_difference():
    # unknown BoP: not exact (can't prove match) and not incompatible (can't prove difference)
    t = build_material_context_trust(_CUR, _LEGACY, "gearing_aero")
    assert t.overall_trust == ContextTrust.PARTIAL_CONTEXT.value
    assert not t.exact_eligible


# ---- 4/6. domain eligibility + exact capping ------------------------------------------------ #
def test_unknown_tyre_multiplier_caps_tyre_degradation_only():
    td = build_material_context_trust(_CUR, _LEGACY, "tyre_degradation")
    assert td.overall_trust == ContextTrust.PARTIAL_CONTEXT.value
    assert "tyre_multiplier" in {f["field"] for f in td.limiting_fields}
    # a trail-braking lesson (driver_technique) is NOT blocked
    dt = build_material_context_trust(_CUR, _LEGACY, "driver_technique")
    assert dt.overall_trust == ContextTrust.EXACT_VERIFIED.value and dt.exact_eligible


def test_unknown_fuel_multiplier_caps_fuel_use():
    fu = build_material_context_trust(_CUR, _LEGACY, "fuel_use")
    assert not fu.exact_eligible and "fuel_multiplier" in {f["field"] for f in fu.limiting_fields}


def test_materially_different_and_incompatible():
    diff_tyre = build_material_context_trust(_CUR, {**_CUR, "tyre_multiplier": "5"}, "tyre_degradation")
    assert diff_tyre.overall_trust == ContextTrust.REFERENCE_ONLY.value
    diff_car = build_material_context_trust(_CUR, {**_CUR, "car": "Mazda"}, "setup_working_windows")
    assert diff_car.overall_trust == ContextTrust.INCOMPATIBLE.value


# ---- verified equivalent event -------------------------------------------------------------- #
def test_equivalent_event_conditions():
    eq = build_material_context_trust(_CUR, {**_CUR, "event_id": "E2"}, "setup_working_windows")
    assert eq.overall_trust == ContextTrust.EQUIVALENT_VERIFIED.value


# ---- 5. legacy evidence visibility ---------------------------------------------------------- #
def test_legacy_records_visible_never_discarded():
    recs = [{"record_key": "r1", "context": _LEGACY, "recorded_at": "2026-01-01"},
            {"record_key": "r2", "context": _LEGACY, "recorded_at": "2026-01-02"}]
    le = build_legacy_evidence_trust(_CUR, recs)
    assert le.visible_record_count == 2 and le.discarded_record_count == 0
    # exact for driver_technique/working-windows, capped for tyre/fuel/gearing
    assert le.domain_exact_counts["driver_technique"] == 2
    assert le.domain_exact_counts["tyre_degradation"] == 0


# ---- property/metamorphic ------------------------------------------------------------------- #
def test_unknown_cannot_become_known_by_reordering():
    a = build_material_context_trust(_CUR, _LEGACY, "gearing_aero").content_fingerprint
    b = build_material_context_trust(_CUR, dict(reversed(list(_LEGACY.items()))),
                                     "gearing_aero").content_fingerprint
    assert a == b


def test_more_unknown_records_cannot_make_context_exact():
    base = [{"record_key": "r1", "context": _LEGACY, "recorded_at": "2026-01-01"}]
    more = base + [{"record_key": f"u{i}", "context": _LEGACY, "recorded_at": f"2026-02-0{i+1}"}
                   for i in range(9)]
    a = build_legacy_evidence_trust(_CUR, base).domain_exact_counts["tyre_degradation"]
    b = build_legacy_evidence_trust(_CUR, more).domain_exact_counts["tyre_degradation"]
    assert a == 0 and b == 0   # more unknowns never create exact tyre-degradation evidence


def test_snapshot_fingerprint_deterministic():
    assert context_snapshot_fingerprint(_CUR) == context_snapshot_fingerprint(dict(_CUR))
