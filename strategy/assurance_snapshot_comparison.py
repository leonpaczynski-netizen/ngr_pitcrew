"""Assurance Snapshot Comparison — deterministic baseline-vs-candidate comparison (Phase 34).

Compares two already-built assurance-chain exports (or snapshots) in an EXPLICIT direction
(baseline -> candidate) and reports what changed across domains, findings, assumptions,
contradictions, readiness and evidence priorities, plus whether assurance improved, regressed or is
unchanged.

Doctrine (enforced):
- Newer is NOT better; no timestamp decides which snapshot is authoritative; the direction is always
  explicit baseline -> candidate.
- A contradiction that disappears because its domain/evidence disappeared is NOT resolved.
- A finding removed because a domain disappeared is NOT an improvement.
- An assumption that vanishes without establishing evidence is NOT an improvement.
- More evidence rows without more independence is NOT progress.
- A readiness increase must be traceable to an actual freshness / coverage / contradiction /
  assumption change, else it is flagged unverified.
- A grade movement is only called improved/regressed when it is CORROBORATED by a material change;
  otherwise it is reported as moved-but-unverified.
- An incompatible or unverifiable comparison never renders an assurance trend.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.assurance_chain_serialization import (
    ASSURANCE_CHAIN_SERIALIZATION_VERSION, CHAIN_PHASE_KEYS, short_fingerprint,
    serialization_versions,
)

ASSURANCE_SNAPSHOT_COMPARISON_VERSION = "assurance_snapshot_comparison_v1"
ASSURANCE_SNAPSHOT_COMPARISON_SCHEMA = 1


class AssuranceComparisonDirection(str, Enum):
    BASELINE_TO_CANDIDATE = "baseline_to_candidate"


class AssuranceCompatibility(str, Enum):
    COMPATIBLE = "compatible"
    PARTIALLY_COMPATIBLE = "partially_compatible"
    INCOMPATIBLE = "incompatible"
    UNVERIFIABLE = "unverifiable"


class AssuranceChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    REOPENED = "reopened"
    RESOLVED = "resolved"
    INCOMPARABLE = "incomparable"


# assurance grade ordinal (higher = more assured). insufficient_evidence is lowest and special.
_GRADE_ORDINAL = {"insufficient_evidence": 0, "not_assured": 1, "partially_assured": 2,
                  "assured_with_limitations": 3, "assured": 4}
_READINESS_ORDINAL = {"unknown": 0, "insufficient_evidence": 0, "conflicted": 1, "regressed": 1,
                      "superseded": 1, "needs_revalidation": 2, "needs_more_evidence": 2,
                      "provisional": 3, "context_bound_only": 4, "ready_with_limitations": 5,
                      "ready": 6}
_SEVERITY_RANK = {"blocking": 4, "major": 3, "moderate": 2, "minor": 1, "informational": 0}

_ADVISORY = ("Read-only, advisory-only deterministic comparison in the explicit direction baseline "
             "-> candidate. Newer is not treated as better and no timestamp decides authority. An "
             "incompatible or unverifiable comparison shows no assurance trend. It changes no "
             "knowledge, resolves no finding, establishes no assumption, and is not a certification.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


# ---------------------------------------------------------------------------------------------
# delta models
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Delta:
    key: str
    domain: str
    change_type: str
    baseline: str
    candidate: str
    detail: str

    def to_dict(self) -> dict:
        return {"key": self.key, "domain": self.domain, "change_type": self.change_type,
                "baseline": self.baseline, "candidate": self.candidate, "detail": self.detail}


class FindingDelta(_Delta):
    pass


class AssumptionDelta(_Delta):
    pass


class ContradictionDelta(_Delta):
    pass


class ReadinessDelta(_Delta):
    pass


class PriorityDelta(_Delta):
    pass


@dataclass(frozen=True)
class DomainAssuranceDelta:
    domain: str
    change_type: str
    finding_changes: int
    assumption_changes: int
    contradiction_changes: int
    readiness_change: str
    priority_changes: int
    present_in_baseline: bool
    present_in_candidate: bool

    def to_dict(self) -> dict:
        return {"domain": self.domain, "change_type": self.change_type,
                "finding_changes": self.finding_changes,
                "assumption_changes": self.assumption_changes,
                "contradiction_changes": self.contradiction_changes,
                "readiness_change": self.readiness_change, "priority_changes": self.priority_changes,
                "present_in_baseline": self.present_in_baseline,
                "present_in_candidate": self.present_in_candidate}


@dataclass(frozen=True)
class AssuranceSnapshotComparison:
    schema_version: int
    direction: str
    compatibility: str
    compatibility_reasons: Tuple[str, ...]
    baseline_identity: dict
    candidate_identity: dict
    baseline_chain_fingerprint: str
    candidate_chain_fingerprint: str
    baseline_grade: str
    candidate_grade: str
    assurance_direction: str
    assurance_direction_reason: str
    domain_deltas: Tuple[dict, ...]
    finding_deltas: Tuple[dict, ...]
    assumption_deltas: Tuple[dict, ...]
    contradiction_deltas: Tuple[dict, ...]
    readiness_deltas: Tuple[dict, ...]
    priority_deltas: Tuple[dict, ...]
    fingerprint_changes: Tuple[dict, ...]
    totals: dict
    ordering: dict
    advisory_statement: str
    content_fingerprint: str
    comparison_versions: dict
    eval_version: str = ASSURANCE_SNAPSHOT_COMPARISON_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version, "direction": self.direction,
                "compatibility": self.compatibility,
                "compatibility_reasons": list(self.compatibility_reasons),
                "baseline_identity": dict(self.baseline_identity),
                "candidate_identity": dict(self.candidate_identity),
                "baseline_chain_fingerprint": self.baseline_chain_fingerprint,
                "candidate_chain_fingerprint": self.candidate_chain_fingerprint,
                "baseline_grade": self.baseline_grade, "candidate_grade": self.candidate_grade,
                "assurance_direction": self.assurance_direction,
                "assurance_direction_reason": self.assurance_direction_reason,
                "domain_deltas": [dict(d) for d in self.domain_deltas],
                "finding_deltas": [dict(d) for d in self.finding_deltas],
                "assumption_deltas": [dict(d) for d in self.assumption_deltas],
                "contradiction_deltas": [dict(d) for d in self.contradiction_deltas],
                "readiness_deltas": [dict(d) for d in self.readiness_deltas],
                "priority_deltas": [dict(d) for d in self.priority_deltas],
                "fingerprint_changes": [dict(d) for d in self.fingerprint_changes],
                "totals": dict(self.totals), "ordering": dict(self.ordering),
                "advisory_statement": self.advisory_statement,
                "content_fingerprint": self.content_fingerprint,
                "comparison_versions": dict(self.comparison_versions),
                "eval_version": self.eval_version}


_ORDERING = {"deltas": "sorted by (change_type_priority, domain, key)",
             "change_type_priority": ["regressed", "reopened", "added", "removed", "modified",
                                      "resolved", "improved", "unchanged", "incomparable"],
             "note": "deterministic; no timestamp affects ordering or the fingerprint"}
_CHANGE_PRIORITY = {t: i for i, t in enumerate(_ORDERING["change_type_priority"])}


# ---------------------------------------------------------------------------------------------
# section extraction
# ---------------------------------------------------------------------------------------------

def _section(export: Mapping, phase_key: str) -> dict:
    for s in (export.get("sections") or []):
        if isinstance(s, Mapping) and _lc(s.get("phase_key")) == phase_key:
            c = s.get("content")
            return dict(c) if isinstance(c, Mapping) else {}
    return {}


def _identity(export: Mapping) -> dict:
    m = export.get("manifest") or {}
    pid = m.get("programme_identity") or {}
    return {"car": _lc(pid.get("car")), "discipline": _lc(pid.get("discipline")),
            "gt7_version": _lc(pid.get("gt7_version")), "driver": _lc(pid.get("driver")),
            "layout_id": _lc((m.get("context_identity") or {}).get("layout_id")),
            "compound": _lc((m.get("context_identity") or {}).get("compound")),
            "db_schema_version": m.get("db_schema_version"),
            "rule_engine_version": _lc(m.get("rule_engine_version")),
            "export_schema": export.get("schema_version")}


def _domains_of(export: Mapping) -> set:
    doms = set()
    for it in (_section(export, "phase28_readiness").get("items") or []):
        if isinstance(it, Mapping):
            doms.add(_lc(it.get("domain")))
    for c in (_section(export, "phase27_coverage").get("domain_coverage") or []):
        if isinstance(c, Mapping):
            doms.add(_lc(c.get("domain")))
    for a in (_section(export, "phase30_assumptions").get("assumptions") or []):
        if isinstance(a, Mapping):
            doms.add(_lc(a.get("domain")))
    for c in (_section(export, "phase29_contradiction").get("contradictions") or []):
        if isinstance(c, Mapping):
            doms.add(_lc(c.get("domain")))
    doms.discard("")
    return doms


def _independent_by_domain(export: Mapping) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in (_section(export, "phase27_coverage").get("domain_coverage") or []):
        if isinstance(c, Mapping):
            ev = c.get("evidence_totals") or {}
            out[_lc(c.get("domain"))] = int(ev.get("independent") or 0)
    return out


# ---------------------------------------------------------------------------------------------
# compatibility
# ---------------------------------------------------------------------------------------------

def _compatibility(bl: Mapping, cd: Mapping) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    bi, ci = _identity(bl), _identity(cd)
    required = ("car", "discipline", "gt7_version", "driver")
    if any(not bi.get(k) for k in required) or any(not ci.get(k) for k in required):
        reasons.append("programme identity is incomplete on one side - cannot verify comparability")
        return AssuranceCompatibility.UNVERIFIABLE.value, reasons
    if bi.get("export_schema") != ci.get("export_schema"):
        reasons.append("export schema versions differ")
        return AssuranceCompatibility.INCOMPATIBLE.value, reasons
    for k in ("car", "discipline", "driver"):
        if bi.get(k) != ci.get(k):
            reasons.append(f"{k} differs ({bi.get(k)} vs {ci.get(k)})")
            return AssuranceCompatibility.INCOMPATIBLE.value, reasons
    partial = False
    if bi.get("gt7_version") != ci.get("gt7_version"):
        reasons.append(f"GT7 version differs ({bi.get('gt7_version')} vs {ci.get('gt7_version')}) - "
                       "assurance meaning may differ")
        partial = True
    if bi.get("rule_engine_version") != ci.get("rule_engine_version"):
        reasons.append("rule-engine version differs - assurance meaning may differ")
        partial = True
    for k in ("layout_id", "compound"):
        if bi.get(k) != ci.get(k):
            reasons.append(f"{k} differs ({bi.get(k) or '-'} vs {ci.get(k) or '-'})")
            partial = True
    if partial:
        return AssuranceCompatibility.PARTIALLY_COMPATIBLE.value, reasons
    reasons.append("programme, context, schema and version identity match")
    return AssuranceCompatibility.COMPATIBLE.value, reasons


# ---------------------------------------------------------------------------------------------
# per-category deltas
# ---------------------------------------------------------------------------------------------

def _finding_key(f: Mapping) -> Tuple[str, str, str]:
    return (_lc(f.get("finding_type")), _lc(f.get("domain")), _lc(f.get("source_phase")))


def _findings(export: Mapping) -> Dict[Tuple[str, str, str], dict]:
    out = {}
    for f in (_section(export, "phase31_assurance").get("findings") or []):
        if isinstance(f, Mapping):
            out[_finding_key(f)] = dict(f)
    return out


def _finding_deltas(bl: Mapping, cd: Mapping, cand_domains: set) -> List[FindingDelta]:
    b, c = _findings(bl), _findings(cd)
    out: List[FindingDelta] = []
    for key in sorted(set(b) | set(c)):
        ftype, dom, phase = key
        kstr = f"{ftype}|{dom}|{phase}"
        if key in b and key not in c:
            if dom and dom not in cand_domains:
                ct, detail = (AssuranceChangeType.INCOMPARABLE.value,
                              "finding gone because its domain disappeared - not an improvement")
            else:
                ct, detail = (AssuranceChangeType.REMOVED.value,
                              "finding no longer reported (may be resolved - corroborate via grade / "
                              "evidence)")
            out.append(FindingDelta(kstr, dom, ct, _lc(b[key].get("severity")), "", detail))
        elif key in c and key not in b:
            sev = _lc(c[key].get("severity"))
            ct = (AssuranceChangeType.REGRESSED.value if sev in ("blocking", "major")
                  else AssuranceChangeType.ADDED.value)
            out.append(FindingDelta(kstr, dom, ct, "", sev, "new finding in candidate"))
        else:
            bs, cs = _lc(b[key].get("severity")), _lc(c[key].get("severity"))
            if bs != cs:
                worse = _SEVERITY_RANK.get(cs, 0) > _SEVERITY_RANK.get(bs, 0)
                out.append(FindingDelta(kstr, dom, AssuranceChangeType.MODIFIED.value, bs, cs,
                                        "severity worsened" if worse else "severity eased"))
    return out


def _assumptions(export: Mapping) -> Dict[Tuple[str, str], dict]:
    out = {}
    for a in (_section(export, "phase30_assumptions").get("assumptions") or []):
        if isinstance(a, Mapping):
            out[(_lc(a.get("domain")), _lc(a.get("assumption_type")))] = dict(a)
    return out


def _assumption_deltas(bl: Mapping, cd: Mapping, cand_domains: set,
                       bl_indep: Dict[str, int], cd_indep: Dict[str, int],
                       readiness_up: set) -> List[AssumptionDelta]:
    b, c = _assumptions(bl), _assumptions(cd)
    out: List[AssumptionDelta] = []
    for key in sorted(set(b) | set(c)):
        dom, atype = key
        kstr = f"{dom}|{atype}"
        if key in b and key not in c:
            established = (dom in cand_domains and dom in readiness_up
                          and cd_indep.get(dom, 0) > bl_indep.get(dom, 0))
            if dom and dom not in cand_domains:
                ct, detail = (AssuranceChangeType.INCOMPARABLE.value,
                              "assumption gone because its domain disappeared")
            elif established:
                ct, detail = (AssuranceChangeType.RESOLVED.value,
                              "assumption established by new independent evidence")
            else:
                ct, detail = (AssuranceChangeType.REMOVED.value,
                              "assumption dropped without establishing evidence - not an improvement")
            out.append(AssumptionDelta(kstr, dom, ct, _lc(b[key].get("status")), "", detail))
        elif key in c and key not in b:
            out.append(AssumptionDelta(kstr, dom, AssuranceChangeType.ADDED.value, "",
                                       _lc(c[key].get("status")), "new reliance assumption"))
        else:
            bs, cs = _lc(b[key].get("status")), _lc(c[key].get("status"))
            if bs != cs:
                out.append(AssumptionDelta(kstr, dom, AssuranceChangeType.MODIFIED.value, bs, cs,
                                           "assumption status changed"))
    return out


def _contradictions(export: Mapping) -> Dict[str, dict]:
    out = {}
    for c in (_section(export, "phase29_contradiction").get("contradictions") or []):
        if isinstance(c, Mapping):
            out[_lc(c.get("domain"))] = dict(c)
    return out


def _contradiction_deltas(bl: Mapping, cd: Mapping, cand_domains: set,
                          bl_indep: Dict[str, int], cd_indep: Dict[str, int]
                          ) -> List[ContradictionDelta]:
    b, c = _contradictions(bl), _contradictions(cd)
    out: List[ContradictionDelta] = []
    for dom in sorted(set(b) | set(c)):
        bopen = bool(b.get(dom, {}).get("is_open")) if dom in b else None
        copen = bool(c.get(dom, {}).get("is_open")) if dom in c else None
        if dom in b and dom not in c:
            if dom not in cand_domains:
                out.append(ContradictionDelta(dom, dom, AssuranceChangeType.INCOMPARABLE.value,
                                              "open" if bopen else "resolved", "",
                                              "contradiction gone because its domain disappeared - "
                                              "not resolved"))
            else:
                out.append(ContradictionDelta(dom, dom, AssuranceChangeType.REMOVED.value,
                                              "open" if bopen else "resolved", "",
                                              "no longer reported (corroborate before calling it "
                                              "resolved)"))
        elif dom in c and dom not in b:
            out.append(ContradictionDelta(dom, dom, AssuranceChangeType.ADDED.value, "",
                                          "open" if copen else "resolved", "new contradiction"))
        else:
            if bopen and not copen:
                resolved = cd_indep.get(dom, 0) > bl_indep.get(dom, 0)
                out.append(ContradictionDelta(
                    dom, dom, AssuranceChangeType.RESOLVED.value if resolved
                    else AssuranceChangeType.MODIFIED.value, "open", "closed",
                    "resolved by increased independent evidence" if resolved
                    else "closed without an increase in independent evidence - unverified"))
            elif copen and not bopen:
                out.append(ContradictionDelta(dom, dom, AssuranceChangeType.REOPENED.value,
                                              "closed", "open", "contradiction reopened"))
            elif _lc(b[dom].get("status")) != _lc(c[dom].get("status")):
                out.append(ContradictionDelta(dom, dom, AssuranceChangeType.MODIFIED.value,
                                              _lc(b[dom].get("status")), _lc(c[dom].get("status")),
                                              "contradiction state changed"))
    return out


def _readiness(export: Mapping) -> Dict[str, dict]:
    out = {}
    for it in (_section(export, "phase28_readiness").get("items") or []):
        if isinstance(it, Mapping):
            out[_lc(it.get("domain"))] = dict(it)
    return out


def _readiness_deltas(bl: Mapping, cd: Mapping, bl_indep: Dict[str, int], cd_indep: Dict[str, int]
                      ) -> Tuple[List[ReadinessDelta], set]:
    b, c = _readiness(bl), _readiness(cd)
    out: List[ReadinessDelta] = []
    improved_domains = set()
    for dom in sorted(set(b) | set(c)):
        bstat = _lc(b.get(dom, {}).get("readiness_status"))
        cstat = _lc(c.get(dom, {}).get("readiness_status"))
        if dom in b and dom not in c:
            out.append(ReadinessDelta(dom, dom, AssuranceChangeType.REMOVED.value, bstat, "",
                                      "domain no longer assessed"))
        elif dom in c and dom not in b:
            out.append(ReadinessDelta(dom, dom, AssuranceChangeType.ADDED.value, "", cstat,
                                      "domain newly assessed"))
        else:
            bo, co = _READINESS_ORDINAL.get(bstat, 0), _READINESS_ORDINAL.get(cstat, 0)
            if co > bo:
                corroborated = cd_indep.get(dom, 0) > bl_indep.get(dom, 0)
                if corroborated:
                    improved_domains.add(dom)
                out.append(ReadinessDelta(
                    dom, dom, AssuranceChangeType.IMPROVED.value if corroborated
                    else AssuranceChangeType.MODIFIED.value, bstat, cstat,
                    "readiness up, corroborated by more independent evidence" if corroborated
                    else "readiness up but not traceable to more independent evidence - unverified"))
            elif co < bo:
                out.append(ReadinessDelta(dom, dom, AssuranceChangeType.REGRESSED.value, bstat,
                                          cstat, "readiness decreased"))
    return out, improved_domains


def _priorities(export: Mapping) -> Dict[Tuple[str, str], dict]:
    out = {}
    pri = _section(export, "phase32_priority")
    for c in (list(pri.get("prioritised_candidates") or [])
              + list(pri.get("deferred_candidates") or [])):
        if isinstance(c, Mapping):
            dom = ",".join(sorted(_lc(d) for d in (c.get("domains") or []))) or "programme"
            out[(dom, _lc(c.get("investigation_type")))] = dict(c)
    return out


def _priority_deltas(bl: Mapping, cd: Mapping) -> List[PriorityDelta]:
    b, c = _priorities(bl), _priorities(cd)
    out: List[PriorityDelta] = []
    for key in sorted(set(b) | set(c)):
        dom, itype = key
        kstr = f"{dom}|{itype}"
        if key in b and key not in c:
            out.append(PriorityDelta(kstr, dom, AssuranceChangeType.REMOVED.value,
                                     _lc(b[key].get("priority_band")), "",
                                     "priority gone - may be resolved, superseded, invalidated or "
                                     "hidden; distinguish where evidence allows"))
        elif key in c and key not in b:
            out.append(PriorityDelta(kstr, dom, AssuranceChangeType.ADDED.value, "",
                                     _lc(c[key].get("priority_band")), "new evidence priority"))
        else:
            bb, cb = _lc(b[key].get("priority_band")), _lc(c[key].get("priority_band"))
            bid, cid = _lc(b[key].get("candidate_id")), _lc(c[key].get("candidate_id"))
            if bb != cb or bid != cid:
                detail = ("priority band moved" if bb != cb else "justification changed "
                          "(linked findings changed)")
                out.append(PriorityDelta(kstr, dom, AssuranceChangeType.MODIFIED.value, bb, cb,
                                         detail))
    return out


# ---------------------------------------------------------------------------------------------
# top-level
# ---------------------------------------------------------------------------------------------

def compare_assurance_snapshots(baseline_export: Optional[Mapping],
                                candidate_export: Optional[Mapping]
                                ) -> AssuranceSnapshotComparison:
    """Compare two assurance-chain exports, baseline -> candidate. Deterministic; never raises."""
    try:
        return _compare(baseline_export or {}, candidate_export or {})
    except Exception as exc:   # never raise into the caller
        cv = comparison_versions()
        return AssuranceSnapshotComparison(
            schema_version=ASSURANCE_SNAPSHOT_COMPARISON_SCHEMA,
            direction=AssuranceComparisonDirection.BASELINE_TO_CANDIDATE.value,
            compatibility=AssuranceCompatibility.UNVERIFIABLE.value,
            compatibility_reasons=(f"comparison unavailable ({type(exc).__name__})",),
            baseline_identity={}, candidate_identity={}, baseline_chain_fingerprint="",
            candidate_chain_fingerprint="", baseline_grade="", candidate_grade="",
            assurance_direction="incomparable", assurance_direction_reason="error",
            domain_deltas=(), finding_deltas=(), assumption_deltas=(), contradiction_deltas=(),
            readiness_deltas=(), priority_deltas=(), fingerprint_changes=(), totals={},
            ordering=_ORDERING, advisory_statement=_ADVISORY,
            content_fingerprint=short_fingerprint(ASSURANCE_SNAPSHOT_COMPARISON_VERSION,
                                                  {"error": type(exc).__name__}),
            comparison_versions=cv)


def _grade(export: Mapping) -> str:
    return _lc((export.get("manifest") or {}).get("assurance_grade")
               or _section(export, "phase31_assurance").get("assurance_grade"))


def _chain_fp(export: Mapping) -> str:
    return str((export.get("manifest") or {}).get("assurance_chain_fingerprint") or "")


def _compare(bl: Mapping, cd: Mapping) -> AssuranceSnapshotComparison:
    compat, reasons = _compatibility(bl, cd)
    bi, ci = _identity(bl), _identity(cd)
    b_grade, c_grade = _grade(bl), _grade(cd)
    comparable = compat in (AssuranceCompatibility.COMPATIBLE.value,
                            AssuranceCompatibility.PARTIALLY_COMPATIBLE.value)

    cand_domains = _domains_of(cd)
    base_domains = _domains_of(bl)
    bl_indep, cd_indep = _independent_by_domain(bl), _independent_by_domain(cd)

    if comparable:
        readiness_deltas, improved_domains = _readiness_deltas(bl, cd, bl_indep, cd_indep)
        finding_deltas = _finding_deltas(bl, cd, cand_domains)
        assumption_deltas = _assumption_deltas(bl, cd, cand_domains, bl_indep, cd_indep,
                                               improved_domains)
        contradiction_deltas = _contradiction_deltas(bl, cd, cand_domains, bl_indep, cd_indep)
        priority_deltas = _priority_deltas(bl, cd)
    else:
        readiness_deltas = finding_deltas = assumption_deltas = contradiction_deltas = []
        priority_deltas = []
        improved_domains = set()

    # fingerprint changes across the chain sections.
    fp_changes: List[dict] = []
    b_secs = {_lc(s.get("phase_key")): s for s in (bl.get("sections") or []) if isinstance(s, Mapping)}
    c_secs = {_lc(s.get("phase_key")): s for s in (cd.get("sections") or []) if isinstance(s, Mapping)}
    for key in CHAIN_PHASE_KEYS:
        bd = _lc((b_secs.get(key) or {}).get("content_digest"))
        cdg = _lc((c_secs.get(key) or {}).get("content_digest"))
        if bd != cdg:
            fp_changes.append({"section": key, "baseline_digest": bd[:16], "candidate_digest": cdg[:16],
                               "changed": True})

    # overall assurance direction (only when comparable), corroboration-gated.
    all_deltas = (finding_deltas + assumption_deltas + contradiction_deltas + readiness_deltas
                  + priority_deltas)
    if not comparable:
        direction, dir_reason = "incomparable", ("snapshots are not compatible - no assurance trend "
                                                 "is shown")
    else:
        bo, co = _GRADE_ORDINAL.get(b_grade, 0), _GRADE_ORDINAL.get(c_grade, 0)
        positive = any(d.change_type in (AssuranceChangeType.RESOLVED.value,
                                         AssuranceChangeType.IMPROVED.value) for d in all_deltas) \
            or any(d.change_type == AssuranceChangeType.REMOVED.value
                   and d.baseline in ("blocking", "major") for d in finding_deltas)
        negative = any(d.change_type in (AssuranceChangeType.REGRESSED.value,
                                         AssuranceChangeType.REOPENED.value) for d in all_deltas)
        if co > bo and positive:
            direction, dir_reason = "improved", ("grade improved and corroborated by material "
                                                 "positive changes")
        elif co > bo:
            direction, dir_reason = "moved_unverified", ("grade rose but no corroborating material "
                                                         "improvement was found")
        elif co < bo or negative:
            direction, dir_reason = "regressed", ("grade fell or a regression/reopening was recorded")
        elif not all_deltas and b_grade == c_grade:
            direction, dir_reason = "unchanged", "identical assurance state"
        else:
            direction, dir_reason = "changed_neutral", ("changes recorded without a net assurance "
                                                        "grade movement")

    # domain rollup.
    def _dom_of(dlist):
        m: Dict[str, int] = {}
        for d in dlist:
            m[d.domain] = m.get(d.domain, 0) + 1
        return m
    fc, ac, cc, pc = (_dom_of(finding_deltas), _dom_of(assumption_deltas),
                      _dom_of(contradiction_deltas), _dom_of(priority_deltas))
    rd_map = {d.domain: d.change_type for d in readiness_deltas}
    domain_deltas: List[DomainAssuranceDelta] = []
    for dom in sorted(base_domains | cand_domains):
        if not dom:
            continue
        pib, pic = dom in base_domains, dom in cand_domains
        n = fc.get(dom, 0) + ac.get(dom, 0) + cc.get(dom, 0) + pc.get(dom, 0) + (1 if dom in rd_map else 0)
        if not pib and pic:
            ct = AssuranceChangeType.ADDED.value
        elif pib and not pic:
            ct = AssuranceChangeType.REMOVED.value
        elif n == 0:
            ct = AssuranceChangeType.UNCHANGED.value
        else:
            ct = AssuranceChangeType.MODIFIED.value
        domain_deltas.append(DomainAssuranceDelta(
            domain=dom, change_type=ct, finding_changes=fc.get(dom, 0),
            assumption_changes=ac.get(dom, 0), contradiction_changes=cc.get(dom, 0),
            readiness_change=rd_map.get(dom, "none"), priority_changes=pc.get(dom, 0),
            present_in_baseline=pib, present_in_candidate=pic))

    def _sort(dlist):
        return sorted(dlist, key=lambda d: (_CHANGE_PRIORITY.get(d.change_type, 99), d.domain, d.key))

    finding_deltas = _sort(finding_deltas)
    assumption_deltas = _sort(assumption_deltas)
    contradiction_deltas = _sort(contradiction_deltas)
    readiness_deltas = _sort(readiness_deltas)
    priority_deltas = _sort(priority_deltas)

    totals = {"finding_deltas": len(finding_deltas), "assumption_deltas": len(assumption_deltas),
              "contradiction_deltas": len(contradiction_deltas),
              "readiness_deltas": len(readiness_deltas), "priority_deltas": len(priority_deltas),
              "domain_deltas": len(domain_deltas), "changed_sections": len(fp_changes)}

    cv = comparison_versions()
    fp = short_fingerprint(ASSURANCE_SNAPSHOT_COMPARISON_VERSION, {
        "dir": AssuranceComparisonDirection.BASELINE_TO_CANDIDATE.value, "compat": compat,
        "b_fp": _chain_fp(bl), "c_fp": _chain_fp(cd), "b_grade": b_grade, "c_grade": c_grade,
        "assurance_direction": direction,
        "fd": [d.to_dict() for d in finding_deltas], "ad": [d.to_dict() for d in assumption_deltas],
        "cd": [d.to_dict() for d in contradiction_deltas],
        "rd": [d.to_dict() for d in readiness_deltas], "pd": [d.to_dict() for d in priority_deltas],
        "dom": [d.to_dict() for d in domain_deltas], "fpc": fp_changes, "cv": cv})

    return AssuranceSnapshotComparison(
        schema_version=ASSURANCE_SNAPSHOT_COMPARISON_SCHEMA,
        direction=AssuranceComparisonDirection.BASELINE_TO_CANDIDATE.value, compatibility=compat,
        compatibility_reasons=tuple(reasons), baseline_identity=bi, candidate_identity=ci,
        baseline_chain_fingerprint=_chain_fp(bl), candidate_chain_fingerprint=_chain_fp(cd),
        baseline_grade=b_grade, candidate_grade=c_grade, assurance_direction=direction,
        assurance_direction_reason=dir_reason,
        domain_deltas=tuple(d.to_dict() for d in domain_deltas),
        finding_deltas=tuple(d.to_dict() for d in finding_deltas),
        assumption_deltas=tuple(d.to_dict() for d in assumption_deltas),
        contradiction_deltas=tuple(d.to_dict() for d in contradiction_deltas),
        readiness_deltas=tuple(d.to_dict() for d in readiness_deltas),
        priority_deltas=tuple(d.to_dict() for d in priority_deltas),
        fingerprint_changes=tuple(fp_changes), totals=totals, ordering=_ORDERING,
        advisory_statement=_ADVISORY, content_fingerprint=fp, comparison_versions=cv)


def comparison_versions() -> dict:
    return {"assurance_snapshot_comparison": ASSURANCE_SNAPSHOT_COMPARISON_VERSION,
            "schema": ASSURANCE_SNAPSHOT_COMPARISON_SCHEMA, **serialization_versions()}
