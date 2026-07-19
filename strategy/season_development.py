"""Season Development — programme-wide engineering summary (Program 2, Phase 21).

A deterministic, READ-ONLY roll-up of the whole engineering programme: how many campaigns, how
much has been learned, how much engineering value and remaining value there is, and how much
testing remains. Every value carries a **reason / source / calculation** - no hidden maths.

It aggregates existing measures only (Phase-17 value, Phase-18 status/completion, Phase-19
cost, Phase-20 confidence/opportunity). It ranks, prioritises, schedules and decides NOTHING.
Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock;
deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

SEASON_DEVELOPMENT_VERSION = "season_development_v1"

_CONFIDENT = ("high", "very_high")
_LOW_CONFIDENCE = ("unknown", "very_low", "low")
# Knowledge-map states that count as "engineering knowledge secured".
_UNDERSTOOD_STATES = ("engineering_complete", "well_understood")


@dataclass(frozen=True)
class SeasonMetric:
    value: object
    reason: str
    source: str
    calculation: str

    def to_dict(self) -> dict:
        return {"value": self.value, "reason": self.reason, "source": self.source,
                "calculation": self.calculation}


@dataclass(frozen=True)
class SeasonDevelopment:
    metrics: dict                        # name -> SeasonMetric.to_dict()
    engineering_summary: str
    eval_version: str = SEASON_DEVELOPMENT_VERSION

    def to_dict(self) -> dict:
        return {"metrics": {k: dict(v) for k, v in self.metrics.items()},
                "engineering_summary": self.engineering_summary,
                "eval_version": self.eval_version}

    def value(self, name: str):
        m = self.metrics.get(name)
        return m.get("value") if isinstance(m, Mapping) else None


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _round(v) -> float:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return 0.0


def summarize_season(records: Sequence[Mapping],
                     knowledge_states: Sequence[Mapping]) -> SeasonDevelopment:
    """Build the season-wide engineering summary from the normalised campaign records + their
    Phase-21 knowledge states. Every metric exposes reason/source/calculation. Never raises."""
    try:
        return _summarize([r for r in (records or []) if isinstance(r, Mapping)],
                          [k for k in (knowledge_states or []) if isinstance(k, Mapping)])
    except Exception:   # never raise into the caller
        return SeasonDevelopment(metrics={}, engineering_summary="")


def _summarize(records: List[Mapping], knowledge_states: List[Mapping]) -> SeasonDevelopment:
    n = len(records)
    states = {str(k.get("campaign_id") or ""): _lc(k.get("state")) for k in knowledge_states}

    active = [r for r in records if _lc(r.get("status")) == "active"]
    completed = [r for r in records if _lc(r.get("status")) == "completed"]
    needing_conf = [r for r in records
                    if _lc(r.get("opportunity")) == "worth_another_confirmation"]
    plateaued = [r for r in records if _lc(r.get("opportunity")) == "knowledge_plateau"]
    high_conf = [r for r in records if _lc(r.get("confidence_level")) in _CONFIDENT]
    low_conf = [r for r in records if _lc(r.get("confidence_level")) in _LOW_CONFIDENCE]

    total_value = _round(sum(_round(r.get("total_value")) for r in records))
    remaining_value = _round(sum(_round(r.get("remaining_value")) for r in records))
    rem_laps = int(sum(int(r.get("remaining_laps") or 0) for r in records))
    rem_tyres = _round(sum(_round(r.get("remaining_tyre_sets")) for r in records))
    rem_minutes = _round(sum(_round(r.get("remaining_minutes")) for r in records))

    understood = [cid for cid, st in states.items() if st in _UNDERSTOOD_STATES]
    knowledge_completion = _round(len(understood) / n) if n else 0.0

    def M(value, reason, source, calc) -> dict:
        return SeasonMetric(value=value, reason=reason, source=source,
                            calculation=calc).to_dict()

    metrics = {
        "campaign_count": M(n, "total engineering campaigns this season", "Phase 18 campaigns",
                            "count of campaigns"),
        "active_campaigns": M(len(active), "campaigns still under active investigation",
                              "Phase 18 status", "count where status == active"),
        "completed_campaigns": M(len(completed), "campaigns Phase 18 marks completed",
                                 "Phase 18 completion", "count where status == completed"),
        "campaigns_needing_confirmation": M(
            len(needing_conf), "campaigns confirmed once but not yet repeated",
            "Phase 20 opportunity", "count where opportunity == worth_another_confirmation"),
        "campaigns_plateaued": M(len(plateaued), "campaigns where knowledge has plateaued",
                                 "Phase 20 opportunity",
                                 "count where opportunity == knowledge_plateau"),
        "high_confidence_campaigns": M(len(high_conf), "campaigns with trustworthy conclusions",
                                       "Phase 20 confidence",
                                       "count where confidence in (high, very_high)"),
        "low_confidence_campaigns": M(len(low_conf), "campaigns with little trustworthy evidence",
                                      "Phase 20 confidence",
                                      "count where confidence in (unknown, very_low, low)"),
        "total_engineering_value": M(
            total_value, "sum of Phase-17 engineering value across all campaign experiments",
            "Phase 17 valuation (via Phase 19)", "sum of per-campaign total_value"),
        "total_remaining_value": M(
            remaining_value, "engineering value still available from untested experiments",
            "Phase 17 valuation (via Phase 19)", "sum of per-campaign remaining_value"),
        "estimated_remaining_cost": M(
            {"laps": rem_laps, "tyre_sets": rem_tyres, "time_minutes": rem_minutes},
            "estimated effort to run all remaining experiments", "Phase 19 cost model",
            "sum of per-campaign remaining laps / tyre sets / minutes"),
        "knowledge_completion": M(
            knowledge_completion, "fraction of campaigns whose engineering is understood/complete",
            "Phase 21 knowledge map", f"{len(understood)} understood / {n} campaigns"),
    }

    summary = (f"{n} campaign(s): {len(completed)} completed, {len(active)} active, "
               f"{len(high_conf)} high-confidence, {len(low_conf)} low-confidence; "
               f"{len(needing_conf)} need another confirmation, {len(plateaued)} plateaued. "
               f"Knowledge completion {knowledge_completion} ({len(understood)}/{n}); "
               f"remaining engineering value {remaining_value}; estimated remaining testing "
               f"{rem_laps} laps.") if n else "No engineering campaigns this season yet."

    return SeasonDevelopment(metrics=metrics, engineering_summary=summary)


def development_versions() -> dict:
    return {"season_development": SEASON_DEVELOPMENT_VERSION}
