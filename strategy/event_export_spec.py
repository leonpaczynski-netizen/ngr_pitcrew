"""Event export spec builder — pure, Qt-free, DB-free. Never raises.

Builds the deterministic export spec dict for an event. The spec contains
both owner baselines, all proposals, session evidence, suppressed changes,
unresolved riders and a driver-profile evolution delta (or a stated reason
it could not run).

CORRECTION 1 compliance: this module is PURE — it takes ALREADY-FETCHED data
as plain arguments and returns a spec dict. ALL database access is delegated
to the thin caller in ``services/event_export_service.py``.

Determinism guarantees (C18):
  - No timestamps in the fingerprint (``generated_at_human`` is excluded).
  - Fixed float precision via ``assurance_chain_serialization.content_digest``.
  - Deterministically ordered fields via the SCHEMA_KEY_ORDER tuple.
  - Embedded DB_VERSION / RULE_ENGINE_VERSION / EXPORT_FORMAT_VERSION.
  - Content digest = sha256 over the document WITHOUT the fingerprint field
    (``content_fingerprint`` excluded from its own hash).

Provenance tags (C19): every proposal carries exactly one of
  MEASURED_FACT / DETERMINISTIC_INFERENCE / DRIVER_REPORT / UNRESOLVED.
  These come verbatim from the arbiter's provenance field.

C20 compliance: driving-style content comes EXCLUSIVELY from ``evolve_profile``
  and only when it cleared the minimum criteria (4 sessions, 3-session
  corroboration, 2x dominance). When blocked, ``driver_profile_delta`` carries
  ``blocked_reason`` and ``delta_fields`` is empty — no partial/extrapolated content.

C21 compliance: the spec is written only to an explicit caller-chosen destination
  by ``data/event_export_writer.py``.
"""
from __future__ import annotations

import re
from typing import Any, List, Mapping, Optional, Sequence

from strategy._setup_constants import DB_VERSION, EXPORT_FORMAT_VERSION, RULE_ENGINE_VERSION
from strategy.assurance_chain_serialization import canonical_obj, content_digest

# The fingerprint version from the engineering context key spine.
from data.engineering_context_key import FINGERPRINT_VERSION

# ---------------------------------------------------------------------------
# Deterministic field order in the exported document (C18).
# Matches the brief's schema verbatim.
# ---------------------------------------------------------------------------
SCHEMA_KEY_ORDER: tuple = (
    "export_format_version",
    "db_version",
    "rule_engine_version",
    "fingerprint_version",
    "scope_fingerprint",
    "memory_context_key_race",
    "memory_context_key_qualifying",
    "event_id",
    "event_name",
    "car",
    "track",
    "owner_baselines",
    "proposals",
    "unresolved_riders",
    "suppressed_changes",
    "session_evidence",
    "driver_profile_delta",
    "generated_at_human",
    "content_fingerprint",
)

# ---------------------------------------------------------------------------
# M1: canonical fingerprint exclusion set.
# Both the spec builder (below) and the writer (data/event_export_writer.py)
# must exclude the SAME keys from their hash computation.  Define the set here
# once and import it in the writer so the two never drift apart.
# ---------------------------------------------------------------------------
_FINGERPRINT_EXCLUDED_KEYS: frozenset = frozenset({
    "content_fingerprint",  # excluded from its own computation (always)
    "generated_at_human",   # timestamp must not affect the deterministic hash
})

# Windows-illegal path characters to strip from event_name in the filename.
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitise_filename_part(name: str) -> str:
    """Strip characters illegal in Windows filenames. Never raises."""
    try:
        cleaned = _ILLEGAL_CHARS.sub("_", str(name or ""))
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "event"
    except Exception:
        return "event"


def export_filename(event_name: str, scope_fingerprint: str) -> str:
    """Deterministic filename for the export file (C21).

    ``{sanitised_event_name}_{scope_fp_12chars}_event_export.json``
    """
    safe_name = _sanitise_filename_part(event_name)
    fp12 = str(scope_fingerprint or "")[:12].replace(":", "_")
    return f"{safe_name}_{fp12}_event_export.json"


# ---------------------------------------------------------------------------
# Profile-delta builder
# ---------------------------------------------------------------------------

def _build_profile_delta(
    feedback_rows: Sequence[Mapping],
    lap_cov_list: Sequence,
) -> dict:
    """Attempt to run ``evolve_profile`` and return a delta dict.

    C20: only emits style content when ``evolve_profile`` clears its minimum
    criteria (``_MIN_SESSIONS=4``, ``_CORROBORATION=3``, ``_DOMINANCE=2.0``).
    When blocked, ``delta_fields`` is ``{}`` and ``blocked_reason`` is non-empty.
    Never raises.
    """
    try:
        from strategy.driver_profile_evolution import observe_feedback, observe_consistency, evolve_profile
        from strategy.setup_driver_profile import build_driver_profile

        tendencies = observe_feedback(list(feedback_rows or []))
        consistent = observe_consistency(list(lap_cov_list or []))
        base = build_driver_profile()
        evolved, rationale = evolve_profile(base, tendencies, consistent=consistent)

        # Compute what actually changed between base and evolved.
        changed: dict = {}
        for attr in ("prefers_rear_stability", "dislikes_snap_exit", "trail_braker",
                     "rotation_without_snap", "prefers_front_bite", "dislikes_floaty_front",
                     "protects_downforce", "race_values_consistency"):
            b_val = getattr(base, attr, None)
            e_val = getattr(evolved, attr, None)
            if b_val != e_val:
                changed[attr] = {"from": b_val, "to": e_val}

        # Minimum-criteria gate (C20): evolve_profile returns base unchanged
        # when the criteria are not met (the rationale list is empty).
        if not rationale and not changed:
            n_sessions = getattr(tendencies, "sessions", 0)
            return {
                "delta_fields": {},
                "blocked_reason": (
                    f"evolve_profile requires at least {4} sessions with "
                    f"{3}-session corroboration and {2}x dominance; "
                    f"only {n_sessions} session(s) available."
                ),
            }
        return {
            "delta_fields": changed,
            "rationale": list(rationale),
            "blocked_reason": None,
        }
    except Exception as exc:
        return {
            "delta_fields": {},
            "blocked_reason": f"evolve_profile could not run: {type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_event_export_spec(
    *,
    event_id: int,
    event_name: str,
    car: str,
    track: str,
    scope_fingerprint: str,
    memory_context_key_race: str,
    memory_context_key_qualifying: str,
    owner_baselines: Mapping,          # {"race": dict|None, "qualifying": dict|None}
    proposals: Sequence[Mapping],      # list of proposal dicts (as_dict())
    unresolved_riders: Sequence[Mapping],
    suppressed_changes: Sequence[Mapping],
    session_evidence: Sequence[Mapping],
    feedback_rows: Sequence[Mapping] = (),  # for evolve_profile (C20)
    lap_cov_list: Sequence = (),            # for observe_consistency (C20)
    generated_at_human: str = "",           # ISO string — EXCLUDED from fingerprint
) -> dict:
    """Build the deterministic export spec. Never raises.

    Parameters
    ----------
    event_id, event_name, car, track
        Event identity.
    scope_fingerprint
        ``EngineeringContextKey.scope_fingerprint()`` — the stable cross-event
        physical scope key.  12 chars of this appear in the filename.
    memory_context_key_race / _qualifying
        ``MemoryContextKey.key()`` per discipline — the development-history join key.
    owner_baselines
        ``{"race": {field: value, ...} | null, "qualifying": {field: value, ...} | null}``.
        Null when the discipline has no entered baseline.
    proposals
        List of ``OwnerProposal.as_dict()`` dicts, covering all proposals for the event
        across all sessions and disciplines (proposed / accepted / rejected / unresolved).
    unresolved_riders
        List of ``UnresolvedRider.as_dict()`` dicts.
    suppressed_changes
        List of ``SuppressedChange.as_dict()`` dicts.
    session_evidence
        List of ``{session_run_id, discipline, clean_lap_count, feedback_signals}``
        per recorded practice session.
    feedback_rows, lap_cov_list
        Aggregated feedback rows and per-session coefficient-of-variation values
        for ``evolve_profile`` / ``observe_consistency`` (C20 gate).
    generated_at_human
        ISO-format timestamp string.  EXCLUDED from the content fingerprint (C18).

    Returns
    -------
    dict with all ``SCHEMA_KEY_ORDER`` fields.  ``content_fingerprint`` is
    ``sha256:<hex>`` over the document without ``content_fingerprint`` itself.
    """
    try:
        return _build_spec_inner(
            event_id=int(event_id or 0),
            event_name=str(event_name or ""),
            car=str(car or ""),
            track=str(track or ""),
            scope_fingerprint=str(scope_fingerprint or ""),
            memory_context_key_race=str(memory_context_key_race or ""),
            memory_context_key_qualifying=str(memory_context_key_qualifying or ""),
            owner_baselines=dict(owner_baselines or {}),
            proposals=list(proposals or []),
            unresolved_riders=list(unresolved_riders or []),
            suppressed_changes=list(suppressed_changes or []),
            session_evidence=list(session_evidence or []),
            feedback_rows=list(feedback_rows or []),
            lap_cov_list=list(lap_cov_list or []),
            generated_at_human=str(generated_at_human or ""),
        )
    except Exception:
        return _empty_spec(int(event_id or 0), str(event_name or ""))


def _empty_spec(event_id: int, event_name: str) -> dict:
    """Minimal valid spec for error-degradation path."""
    doc: dict = {}
    for k in SCHEMA_KEY_ORDER:
        doc[k] = None
    doc.update({
        "export_format_version": EXPORT_FORMAT_VERSION,
        "db_version": DB_VERSION,
        "rule_engine_version": RULE_ENGINE_VERSION,
        "fingerprint_version": FINGERPRINT_VERSION,
        "event_id": event_id,
        "event_name": event_name,
        "proposals": [],
        "unresolved_riders": [],
        "suppressed_changes": [],
        "session_evidence": [],
        "owner_baselines": {"race": None, "qualifying": None},
        "driver_profile_delta": {"delta_fields": {}, "blocked_reason": "export failed"},
        "content_fingerprint": "",
    })
    return doc


def _build_spec_inner(
    *,
    event_id: int,
    event_name: str,
    car: str,
    track: str,
    scope_fingerprint: str,
    memory_context_key_race: str,
    memory_context_key_qualifying: str,
    owner_baselines: dict,
    proposals: list,
    unresolved_riders: list,
    suppressed_changes: list,
    session_evidence: list,
    feedback_rows: list,
    lap_cov_list: list,
    generated_at_human: str,
) -> dict:
    """Inner implementation — may raise; always wrapped by build_event_export_spec."""

    profile_delta = _build_profile_delta(feedback_rows, lap_cov_list)

    # Normalise owner_baselines: always a dict with "race" and "qualifying" keys.
    baselines_out: dict = {
        "race": canonical_obj(owner_baselines.get("race")),
        "qualifying": canonical_obj(owner_baselines.get("qualifying")),
    }

    # Build the document without the content fingerprint first (C18).
    doc_without_fp: dict = {
        "export_format_version": EXPORT_FORMAT_VERSION,
        "db_version": DB_VERSION,
        "rule_engine_version": RULE_ENGINE_VERSION,
        "fingerprint_version": FINGERPRINT_VERSION,
        "scope_fingerprint": scope_fingerprint,
        "memory_context_key_race": memory_context_key_race,
        "memory_context_key_qualifying": memory_context_key_qualifying,
        "event_id": event_id,
        "event_name": event_name,
        "car": car,
        "track": track,
        "owner_baselines": baselines_out,
        "proposals": [canonical_obj(p) for p in proposals],
        "unresolved_riders": [canonical_obj(r) for r in unresolved_riders],
        "suppressed_changes": [canonical_obj(s) for s in suppressed_changes],
        "session_evidence": [canonical_obj(e) for e in session_evidence],
        "driver_profile_delta": canonical_obj(profile_delta),
        # generated_at_human intentionally excluded from the fingerprint input.
    }

    fp = "sha256:" + content_digest(doc_without_fp)

    # Assemble the final document in schema order with the fingerprint and
    # the human timestamp appended last.
    final: dict = {}
    for key in SCHEMA_KEY_ORDER:
        if key == "content_fingerprint":
            final[key] = fp
        elif key == "generated_at_human":
            final[key] = generated_at_human
        else:
            final[key] = doc_without_fp.get(key)

    return final
