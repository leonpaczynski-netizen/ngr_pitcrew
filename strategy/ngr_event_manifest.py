"""Future NGR League Hub event manifest — contract ONLY (Program 2, Phase 48-50 section 12).

This defines a STABLE future import contract for an NGR League Hub. It implements NO API, NO network,
NO authentication and NO automatic import. Manual offline event creation is never removed and the Hub is
never required for offline use. When a Hub eventually provides event data it must become an IMMUTABLE
local event snapshot; a Hub revision must never silently rewrite completed Practice, setup or Race
history — a revision is detected and its compatibility with existing evidence is determined explicitly.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, no network, never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

NGR_EVENT_MANIFEST_VERSION = "ngr_event_manifest_v1"
NGR_EVENT_MANIFEST_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{NGR_EVENT_MANIFEST_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class NgrEventManifestVersion(str, Enum):
    V1 = "v1"


@dataclass(frozen=True)
class NgrRegisteredDriverReference:
    """A reference to a Hub-registered driver. A reference only — Pit Crew never stores Hub credentials."""
    driver_ref: str
    display_name: str = ""
    race_number: str = ""
    team: str = ""

    def as_payload(self) -> dict:
        return {"driver_ref": _norm(self.driver_ref), "display_name": _norm(self.display_name),
                "race_number": _norm(self.race_number), "team": _norm(self.team)}


@dataclass(frozen=True)
class NgrEventManifest:
    """The immutable local snapshot of a Hub-provided event. Field set is intentionally broad but every
    field is optional — an absent Hub yields an empty manifest and offline creation still works."""
    manifest_version: NgrEventManifestVersion
    event_ref: str
    series: str = ""
    round_label: str = ""
    driver: Optional[NgrRegisteredDriverReference] = None
    track: str = ""
    layout: str = ""
    official_quali_date: str = ""
    official_race_date: str = ""
    practice_opportunities: Tuple[str, ...] = field(default_factory=tuple)
    official_sessions: Tuple[str, ...] = field(default_factory=tuple)
    car: str = ""
    bop: str = ""
    tuning: str = ""
    power: str = ""
    weight: str = ""
    tyres: str = ""
    tyre_multiplier: str = ""
    fuel_multiplier: str = ""
    refuel_rate: str = ""
    pit_rules: str = ""
    qualifying_format: str = ""
    race_format: str = ""
    grid_rules: str = ""
    penalties: str = ""
    weather: str = ""
    livery_requirements: str = ""
    revision: int = 0

    def as_payload(self) -> dict:
        return {
            "manifest_version": self.manifest_version.value, "event_ref": _norm(self.event_ref),
            "series": _norm(self.series), "round": _norm(self.round_label),
            "driver": self.driver.as_payload() if self.driver else None,
            "track": _norm(self.track), "layout": _norm(self.layout),
            "official_quali_date": _norm(self.official_quali_date),
            "official_race_date": _norm(self.official_race_date),
            "practice_opportunities": [_norm(p) for p in self.practice_opportunities],
            "official_sessions": [_norm(s) for s in self.official_sessions],
            "car": _norm(self.car), "bop": _norm(self.bop), "tuning": _norm(self.tuning),
            "power": _norm(self.power), "weight": _norm(self.weight), "tyres": _norm(self.tyres),
            "tyre_multiplier": _norm(self.tyre_multiplier), "fuel_multiplier": _norm(self.fuel_multiplier),
            "refuel_rate": _norm(self.refuel_rate), "pit_rules": _norm(self.pit_rules),
            "qualifying_format": _norm(self.qualifying_format), "race_format": _norm(self.race_format),
            "grid_rules": _norm(self.grid_rules), "penalties": _norm(self.penalties),
            "weather": _norm(self.weather), "livery_requirements": _norm(self.livery_requirements),
            "revision": int(self.revision)}

    def fingerprint(self) -> str:
        # revision is metadata, not environment content: two manifests with identical environment but
        # different revision numbers have the SAME content fingerprint (so a no-op revision is detectable)
        payload = {k: v for k, v in self.as_payload().items() if k != "revision"}
        return _fp(payload)


class NgrEventManifestValidationCode(str, Enum):
    OK = "ok"
    MISSING_EVENT_REF = "missing_event_ref"
    UNKNOWN_VERSION = "unknown_version"
    INVALID_DATE = "invalid_date"


@dataclass(frozen=True)
class NgrEventManifestValidation:
    ok: bool
    codes: Tuple[NgrEventManifestValidationCode, ...]
    messages: Tuple[str, ...]

    def as_payload(self) -> dict:
        return {"ok": self.ok, "codes": [c.value for c in self.codes], "messages": list(self.messages)}


def validate_manifest(manifest: NgrEventManifest) -> NgrEventManifestValidation:
    """Deterministic structural validation. Never touches the network; never raises."""
    from datetime import date as _date
    codes = []
    msgs = []
    if not _norm(manifest.event_ref):
        codes.append(NgrEventManifestValidationCode.MISSING_EVENT_REF)
        msgs.append("event_ref is required")
    if not isinstance(manifest.manifest_version, NgrEventManifestVersion):
        codes.append(NgrEventManifestValidationCode.UNKNOWN_VERSION)
        msgs.append("unknown manifest version")
    for label, val in (("quali", manifest.official_quali_date), ("race", manifest.official_race_date)):
        s = _norm(val)
        if s:
            try:
                _date.fromisoformat(s[:10])
            except (ValueError, TypeError):
                codes.append(NgrEventManifestValidationCode.INVALID_DATE)
                msgs.append(f"invalid {label} date: {s}")
    ok = not codes
    return NgrEventManifestValidation(ok=ok, codes=tuple(codes), messages=tuple(msgs))


@dataclass(frozen=True)
class NgrEventRevision:
    """The result of comparing a new manifest against a previously-imported one. It NEVER mutates
    history — it reports whether the environment content changed and whether prior evidence stays
    compatible (an environment change may invalidate exact evidence but never rewrites completed rows)."""
    event_ref: str
    previous_revision: int
    new_revision: int
    environment_changed: bool
    prior_evidence_compatible: bool
    changed_fields: Tuple[str, ...]

    def as_payload(self) -> dict:
        return {"event_ref": _norm(self.event_ref), "previous_revision": int(self.previous_revision),
                "new_revision": int(self.new_revision), "environment_changed": self.environment_changed,
                "prior_evidence_compatible": self.prior_evidence_compatible,
                "changed_fields": list(self.changed_fields)}


# environment fields whose change invalidates exact prior evidence compatibility
_EVIDENCE_SENSITIVE_FIELDS = frozenset({
    "car", "track", "layout", "bop", "tuning", "power", "weight", "tyres",
    "tyre_multiplier", "fuel_multiplier",
})


def diff_revision(previous: NgrEventManifest, new: NgrEventManifest) -> NgrEventRevision:
    """Compare two manifests of the same event. Deterministic. Completed history is untouched; this only
    reports what changed and whether prior exact evidence remains compatible."""
    pa, na = previous.as_payload(), new.as_payload()
    changed = tuple(sorted(k for k in na if k != "revision" and pa.get(k) != na.get(k)))
    environment_changed = previous.fingerprint() != new.fingerprint()
    evidence_compatible = not any(f in _EVIDENCE_SENSITIVE_FIELDS for f in changed)
    return NgrEventRevision(
        event_ref=_norm(new.event_ref), previous_revision=int(previous.revision),
        new_revision=int(new.revision), environment_changed=environment_changed,
        prior_evidence_compatible=evidence_compatible, changed_fields=changed)


class NgrEventImportPort:
    """The abstract import boundary a future Hub adapter would implement. The default is an OFFLINE port
    that imports nothing — Pit Crew never requires the Hub. A real adapter would return an
    ``NgrEventManifest`` from a local, already-downloaded file; this contract never performs network I/O.
    """

    def fetch_manifest(self, event_ref: str) -> Optional[NgrEventManifest]:  # pragma: no cover - contract
        raise NotImplementedError


class OfflineNgrEventImportPort(NgrEventImportPort):
    """Default offline port: no Hub, no network, imports nothing. Offline creation is unaffected."""

    def fetch_manifest(self, event_ref: str) -> Optional[NgrEventManifest]:
        return None


def manifest_to_cycle_identity(manifest: NgrEventManifest) -> dict:
    """Project an imported manifest into the fields of a preparation-cycle identity (a local, immutable
    snapshot). Deterministic; the Hub remains the league authority, Pit Crew the engineering authority."""
    return {
        "event_name": f"{_norm(manifest.series)} {_norm(manifest.round_label)}".strip() or _norm(manifest.event_ref),
        "series": _norm(manifest.series), "round_label": _norm(manifest.round_label),
        "driver_id": _norm(manifest.driver.driver_ref) if manifest.driver else "",
        "team": _norm(manifest.driver.team) if manifest.driver else "",
        "car": _norm(manifest.car), "track": _norm(manifest.track), "layout": _norm(manifest.layout),
        "official_quali_date": _norm(manifest.official_quali_date),
        "official_race_date": _norm(manifest.official_race_date),
    }
