"""Campaign Persistence — long-term engineering memory for campaigns (Program 2, Phase 19).

Phase-18 campaigns reconstruct every run. This module adds an ADDITIVE, metadata-only
registry so a campaign's identity survives across many sessions — creation session, first /
last seen, engineering notes, a manual archive flag, and links to the development records /
experiments / outcomes that informed it. The registry OWNS NO ENGINEERING LOGIC: it is a
professional engineering notebook's index, not a decision maker.

It also assembles the read-only "Engineering Efficiency" advisory view by composing the
Phase-18 campaign programme with the Phase-19 evidence-saturation and cost-of-knowledge
estimators plus the registry (campaign age). It ranks nothing, applies nothing, mutates
nothing, and never completes / freezes a campaign.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock (dates are
passed in as data); deterministic; never raises.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.evidence_saturation import (
    EVIDENCE_SATURATION_VERSION, assess_saturation,
)
from strategy.engineering_cost_model import (
    ENGINEERING_COST_VERSION, estimate_experiment_cost, plan_budget,
)

CAMPAIGN_PERSISTENCE_VERSION = "campaign_persistence_v1"
CAMPAIGN_PERSISTENCE_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


# --------------------------------------------------------------------------- #
# Registry entry (metadata only)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CampaignRegistryEntry:
    campaign_id: str
    car: str
    track: str
    layout: str
    discipline: str
    objective_family: str
    objective_region: str
    gt7_version: str
    creation_session: str
    first_seen: str
    last_seen: str
    last_updated: str
    notes: str
    manual_archive_flag: bool
    completion_state: str
    abandonment_reason: str
    linked_development_records: Tuple[str, ...]
    linked_experiments: Tuple[str, ...]
    linked_outcomes: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "car": self.car, "track": self.track,
                "layout": self.layout, "discipline": self.discipline,
                "objective_family": self.objective_family,
                "objective_region": self.objective_region, "gt7_version": self.gt7_version,
                "creation_session": self.creation_session, "first_seen": self.first_seen,
                "last_seen": self.last_seen, "last_updated": self.last_updated,
                "notes": self.notes, "manual_archive_flag": self.manual_archive_flag,
                "completion_state": self.completion_state,
                "abandonment_reason": self.abandonment_reason,
                "linked_development_records": list(self.linked_development_records),
                "linked_experiments": list(self.linked_experiments),
                "linked_outcomes": list(self.linked_outcomes)}

    @classmethod
    def from_row(cls, row: Mapping) -> "CampaignRegistryEntry":
        def _tuple(v):
            try:
                return tuple(json.loads(v)) if v else ()
            except Exception:
                return ()
        return cls(
            campaign_id=_norm(row.get("campaign_id")), car=_norm(row.get("car")),
            track=_norm(row.get("track")), layout=_norm(row.get("layout")),
            discipline=_norm(row.get("discipline")),
            objective_family=_norm(row.get("objective_family")),
            objective_region=_norm(row.get("objective_region")),
            gt7_version=_norm(row.get("gt7_version")),
            creation_session=_norm(row.get("creation_session")),
            first_seen=_norm(row.get("first_seen")), last_seen=_norm(row.get("last_seen")),
            last_updated=_norm(row.get("last_updated")), notes=_norm(row.get("notes")),
            manual_archive_flag=bool(int(row.get("manual_archive_flag") or 0)),
            completion_state=_norm(row.get("completion_state")),
            abandonment_reason=_norm(row.get("abandonment_reason")),
            linked_development_records=_tuple(row.get("linked_development_records")),
            linked_experiments=_tuple(row.get("linked_experiments")),
            linked_outcomes=_tuple(row.get("linked_outcomes")))


def registry_entry_from_campaign(campaign: Mapping, *, session_id: str = "",
                                 recorded_at: str = "",
                                 linked_records: Sequence[str] = ()) -> CampaignRegistryEntry:
    """Build the registry metadata for a live Phase-18 campaign. ``recorded_at`` is supplied
    (never read from the clock). Pure; deterministic."""
    ident = campaign.get("identity") or {}
    exps = campaign.get("experiments") or []
    return CampaignRegistryEntry(
        campaign_id=_norm(ident.get("campaign_id")), car=_norm(ident.get("car")),
        track=_norm(ident.get("track")), layout=_norm(ident.get("layout")),
        discipline=_norm(ident.get("discipline")),
        objective_family=_norm(ident.get("objective_family")),
        objective_region=_norm(ident.get("objective_region")),
        gt7_version=_norm(ident.get("gt7_version")), creation_session=_norm(session_id),
        first_seen=_norm(recorded_at), last_seen=_norm(recorded_at),
        last_updated=_norm(recorded_at), notes="", manual_archive_flag=False,
        completion_state=_norm(campaign.get("status")), abandonment_reason="",
        linked_development_records=tuple(_norm(r) for r in (linked_records or ()) if _norm(r)),
        linked_experiments=tuple(dict.fromkeys(_norm(e.get("candidate_id")) for e in exps
                                               if _norm(e.get("candidate_id")))),
        linked_outcomes=())


# --------------------------------------------------------------------------- #
# Campaign age (dates are data — no wall-clock)
# --------------------------------------------------------------------------- #
def _date(s: str):
    s = _norm(s)[:10]
    try:
        return _dt.date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def campaign_age_days(first_seen: str, now_date: str) -> Optional[int]:
    a, b = _date(first_seen), _date(now_date)
    if a is None or b is None:
        return None
    return (b - a).days


def _age_label(days: Optional[int]) -> str:
    if days is None:
        return "new (not yet recorded)"
    if days <= 0:
        return "this session"
    if days == 1:
        return "1 day"
    if days < 7:
        return f"{days} days"
    if days < 30:
        return f"{days // 7} week(s)"
    return f"{days // 30} month(s)"


# --------------------------------------------------------------------------- #
# Engineering Efficiency assembly (read-only advisory composition)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EngineeringEfficiency:
    context_summary: dict
    campaigns: Tuple[dict, ...]
    budget: dict
    totals: dict
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = CAMPAIGN_PERSISTENCE_SCHEMA
    eval_version: str = CAMPAIGN_PERSISTENCE_VERSION

    def to_dict(self) -> dict:
        return {"context_summary": dict(self.context_summary),
                "campaigns": [dict(c) for c in self.campaigns], "budget": dict(self.budget),
                "totals": dict(self.totals), "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_SAFETY = ("Read-only engineering notebook. Campaign age, evidence saturation and cost-of-"
           "knowledge are ADVISORY only - they never complete, freeze, rank, apply, create "
           "or execute anything. Saturation is independent of campaign status; completion "
           "remains governed by Phase 18 and the frozen Apply gate remains the sole route to "
           "the car.")


def build_engineering_efficiency(programme: Optional[Mapping], *,
                                 registry: Optional[Sequence[Mapping]] = None,
                                 session_budget: Optional[Mapping] = None,
                                 now_date: str = "") -> EngineeringEfficiency:
    """Compose the Phase-18 campaign programme + registry age + evidence saturation +
    cost-of-knowledge into a read-only Engineering Efficiency view. Deterministic; never
    raises; mutates nothing; completes/freezes nothing."""
    try:
        return _build(programme or {}, list(registry or ()), dict(session_budget or {}),
                      _norm(now_date))
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return EngineeringEfficiency(
            context_summary={}, campaigns=(), budget={}, totals={},
            safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(programme: Mapping, registry: List[Mapping], session_budget: Mapping,
           now_date: str) -> EngineeringEfficiency:
    reg_by_id = {}
    for r in registry:
        entry = r if isinstance(r, CampaignRegistryEntry) else (
            CampaignRegistryEntry.from_row(r) if isinstance(r, Mapping) else None)
        if entry is not None:
            reg_by_id[entry.campaign_id] = entry

    campaigns = list(programme.get("campaigns") or [])
    lap_time_seconds = session_budget.get("lap_time_seconds")
    mpl = None
    try:
        mpl = float(lap_time_seconds) / 60.0 if lap_time_seconds else None
    except (TypeError, ValueError):
        mpl = None

    out_campaigns: List[dict] = []
    all_estimates = []            # (rank, estimate) across all campaigns, for the budget
    tot_laps = tot_tyres = tot_minutes = 0.0
    for c in campaigns:
        cid = _norm((c.get("identity") or {}).get("campaign_id"))
        entry = reg_by_id.get(cid)
        age_days = campaign_age_days(entry.first_seen, now_date) if entry else None
        saturation = assess_saturation(c).to_dict()
        exps = c.get("experiments") or []
        estimates = [estimate_experiment_cost(e, minutes_per_lap=mpl) for e in exps]
        testable = [e for e in estimates if e.testable]
        rem_laps = sum(e.laps for e in testable)
        rem_tyres = round(sum(e.tyre_sets for e in testable), 3)
        rem_minutes = round(sum(e.time_minutes for e in testable), 2)
        tot_laps += rem_laps
        tot_tyres += rem_tyres
        tot_minutes += rem_minutes
        for i, est in enumerate(estimates):
            # keep the Phase-17 rank order for the programme-level budget fit
            rank = next((int(e.get("phase17_rank") or 0) for e in exps
                         if _norm(e.get("candidate_id")) == est.candidate_id), i)
            if est.testable:
                all_estimates.append((rank, est.candidate_id, est))
        out_campaigns.append({
            "campaign_id": cid,
            "objective": (c.get("objective") or {}).get("title", ""),
            "status": _norm(c.get("status")),
            "age_days": age_days, "age_label": _age_label(age_days),
            "first_seen": entry.first_seen if entry else "",
            "notes": entry.notes if entry else "",
            "archived": bool(entry.manual_archive_flag) if entry else False,
            "saturation": saturation,
            "remaining_information_gain": saturation.get("information_gain_remaining"),
            "estimated_remaining_laps": rem_laps,
            "estimated_remaining_tyre_sets": rem_tyres,
            "estimated_remaining_time_minutes": rem_minutes,
            "estimated_remaining_fuel_laps": rem_laps,
            "experiment_costs": [est.to_dict() for est in estimates],
            "reasoning": ("; ".join(saturation.get("reasons") or [])
                          + f"; campaign age: {_age_label(age_days)}"),
        })

    ordered = [e for _, _, e in sorted(all_estimates, key=lambda t: (t[0], t[1]))]
    budget = plan_budget(ordered, session_budget=session_budget).to_dict()

    kv = knowledge_versions()
    totals = {
        "campaigns": len(out_campaigns),
        "estimated_remaining_laps": int(tot_laps),
        "estimated_remaining_tyre_sets": round(tot_tyres, 3),
        "estimated_remaining_time_minutes": round(tot_minutes, 2),
        "saturated_campaigns": sum(1 for c in out_campaigns
                                   if c["saturation"]["status"] in ("saturated", "overtested")),
        "archived_campaigns": sum(1 for c in out_campaigns if c["archived"]),
    }
    fp = _fp({"prog": _norm(programme.get("content_fingerprint")),
              "camps": [(c["campaign_id"], c["saturation"]["status"],
                         c["estimated_remaining_laps"], c["age_days"]) for c in out_campaigns],
              "budget": [r.get("candidate_id") for r in budget.get("recommended") or []],
              "now": now_date, "kv": kv})
    return EngineeringEfficiency(
        context_summary=dict(programme.get("context_summary") or {}),
        campaigns=tuple(out_campaigns), budget=budget, totals=totals,
        safety_statement=_SAFETY, content_fingerprint=fp, knowledge_versions=kv)


def knowledge_versions() -> dict:
    return {"campaign_persistence": CAMPAIGN_PERSISTENCE_VERSION,
            "evidence_saturation": EVIDENCE_SATURATION_VERSION,
            "engineering_cost": ENGINEERING_COST_VERSION,
            "schema": CAMPAIGN_PERSISTENCE_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{CAMPAIGN_PERSISTENCE_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
