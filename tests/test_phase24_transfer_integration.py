"""Phase 24 — transfer-integration tests.

Phase 23 transfer levels are consumed UNCHANGED; NOT_TRANSFERABLE stays non-transferable;
SUPPORTED produces no setup values; gearbox stays car/track-specific; track/fuel don't cross
cars; driver technique needs the same driver; version caps respected; unknown attrs conservative;
proxy labelled; no setup field values in the playbook.
"""
import json

import pytest

from strategy.knowledge_transfer import evaluate_transfer
from strategy.programme_transfer_report import build_transfer_report
from strategy.engineering_playbook import build_engineering_playbook

SRC = {"car": "Porsche 911 RSR (991) '17", "discipline": "Race", "gt7_version": "1.49",
       "driver": "leon"}
CUP = {"car": "Porsche 911 GT3 Cup", "discipline": "Race", "gt7_version": "1.49", "driver": "leon"}
TOY = {"car": "Toyota GR Supra Racing Concept Gr.3", "discipline": "Race", "gt7_version": "1.49",
       "driver": "leon"}
PORSCHE_V2 = {"car": "Porsche 911 RSR (991) '17", "discipline": "Race", "gt7_version": "2.0",
              "driver": "leon"}
SAM = {"car": "Porsche 911 GT3 Cup", "discipline": "Race", "gt7_version": "1.49", "driver": "sam"}


def _pk_domain(name, maturity="mature", conf="high", mechs=("load_transfer",), state="well_understood"):
    return {"domain": name, "knowledge_state": {"value": state}, "confidence": {"value": conf},
            "maturity": {"value": maturity}, "remaining_uncertainty": {"value": "low"},
            "supporting_campaigns": ["c1"], "supporting_experiments": [],
            "supporting_mechanisms": list(mechs),
            "supporting_evidence": {"confirmations": 2, "regressions": 0, "executed": 2},
            "known_limitations": []}


def _programme(domains, targets):
    return {"content_fingerprint": "p22",
            "knowledge_graph": {"domains": domains, "known_domains": [d["domain"] for d in domains],
                                "missing_domains": []},
            "compatibility": {"primary_key": SRC,
                              "other_groups": [{"compatibility_key": t} for t in targets]}}


def _playbook_for(domains, targets):
    """Build the playbook via the SAME pure Phase-23 build the orchestrator uses."""
    prog = _programme(domains, targets)
    transfer = build_transfer_report(prog["knowledge_graph"], SRC, targets).to_dict()
    return build_engineering_playbook(prog, transfer).to_dict(), transfer


def _levels(playbook, domain):
    for t in playbook["stable_themes"]:
        if t["engineering_domain"] == domain:
            return t
    return None


def test_transfer_levels_consumed_unchanged():
    domains = [_pk_domain("springs")]
    pb, transfer = _playbook_for(domains, [CUP])
    # the level the theme reports must equal the Phase-23 candidate level verbatim
    cand = next(c for c in transfer["candidates"] if c["engineering_domain"] == "springs")
    theme = _levels(pb, "springs")
    assert theme["transfer_eligibility_summary"]["best_level"] == cand["transfer_level"]


def test_not_transferable_stays_non_transferable():
    domains = [_pk_domain("gearbox", mechs=("final_drive",))]
    pb, transfer = _playbook_for(domains, [TOY])
    theme = _levels(pb, "gearbox")
    # gearbox to a different manufacturer must be not_transferable and excluded from reuse
    assert theme["transfer_eligibility_summary"]["best_level"] == "not_transferable"
    assert theme["compatible_target_programmes"] == []


def test_supported_produces_no_setup_values():
    domains = [_pk_domain("springs")]
    pb, _ = _playbook_for(domains, [CUP])
    blob = json.dumps(pb).lower()
    for banned in ("arb_front\":", "lsd_accel\":", "springs_front\":", "set value", "starting setup",
                   "baseline setup value"):
        assert banned not in blob


def test_gearbox_car_track_specific_boundary():
    domains = [_pk_domain("gearbox", mechs=("final_drive",))]
    pb, _ = _playbook_for(domains, [CUP])
    assert any(b["boundary_type"] == "car_specific" and b["domain"] == "gearbox"
               for b in pb["knowledge_boundaries"])


def test_track_and_fuel_do_not_cross_cars():
    domains = [_pk_domain("track_segments", mechs=("corner_specific",)),
               _pk_domain("fuel", mechs=("fuel",))]
    pb, _ = _playbook_for(domains, [CUP])
    types = {(b["domain"], b["boundary_type"]) for b in pb["knowledge_boundaries"]}
    assert ("track_segments", "track_specific") in types
    assert ("fuel", "fuel_rule_specific") in types


def test_driver_technique_requires_same_driver():
    domains = [_pk_domain("driver_technique", mechs=("throttle_application",))]
    pb_same, _ = _playbook_for(domains, [CUP])          # same driver 'leon'
    pb_diff, _ = _playbook_for(domains, [SAM])          # different driver 'sam'
    same = _levels(pb_same, "driver_technique")
    diff = _levels(pb_diff, "driver_technique")
    assert diff["transfer_eligibility_summary"]["best_level"] == "not_transferable"
    assert same["transfer_eligibility_summary"]["best_level"] != "not_transferable"


def test_version_mismatch_cap_respected():
    domains = [_pk_domain("springs")]
    pb, _ = _playbook_for(domains, [PORSCHE_V2])
    theme = _levels(pb, "springs")
    assert theme["transfer_eligibility_summary"]["best_level"] in ("very_low", "not_transferable")


def test_unknown_attribute_conservative():
    domains = [_pk_domain("springs")]
    pb, _ = _playbook_for(domains, [TOY])   # Toyota drivetrain unknown
    assert any(b["boundary_type"] == "unknown_vehicle_attribute"
               for b in pb["knowledge_boundaries"])


def test_suspension_proxy_labelled():
    domains = [_pk_domain("springs")]
    pb, _ = _playbook_for(domains, [CUP])   # same Porsche -> proxy suspension architecture used
    assert any(b["boundary_type"] == "unverified_transfer_proxy"
               for b in pb["knowledge_boundaries"])


def test_no_setup_field_values_anywhere():
    domains = [_pk_domain("differential"), _pk_domain("springs"),
               _pk_domain("vehicle_balance", mechs=("balance",))]
    pb, _ = _playbook_for(domains, [CUP, TOY])
    blob = json.dumps(pb)
    # no "field: number" style assignments and no obvious numeric setup recommendations
    import re
    assert not re.search(r'"(arb_front|arb_rear|lsd_accel|lsd_decel|springs_front|springs_rear|'
                         r'brake_bias|ride_height|toe_front|camber)"\s*:\s*-?\d', blob)
